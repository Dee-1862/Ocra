"""The gateway: the one agent that talks to Agentverse and to agents outside this computer.

    python -m wilirehab.agent_gateway          (run it next to agents_main)

It is a standalone uAgent with a mailbox, set up the way Fetch.ai's chat-protocol example does
it, so Agentverse's Inspector can find and connect it (port 8001). It does one job: when an
agent you have allowed (WILIREHAB_ALLOWED_SENDERS, for example one on the Raspberry Pi) sends it
a message, it checks the message and hands it to the local agents program over the same local
channel the games use. Nothing else goes through it: the hand and face numbers from the games
stay on this computer, and the mailbox is never used for them.

An outside message is JSON text: {"source": "hand" | "face" | "round", "role": "...", "data": {...}}.
It uses no AI model and needs no API key.

Not yet run against a real uAgents install: see Card 26, part D, in notebook/manual-tests.md.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from urllib.parse import quote

from .agent_link import AgentIngress
from .env import load_env

SOURCES = ("hand", "face", "round")
PORT = 8001


def parse_external(text: str):
    """(source, role, data) from an outside agent's message text, or None if it is not acceptable."""
    try:
        msg = json.loads(text)
    except ValueError:
        return None
    if not isinstance(msg, dict):
        return None
    source, role, data = msg.get("source"), msg.get("role"), msg.get("data")
    if source not in SOURCES or not isinstance(data, dict):
        return None
    if role is not None and not isinstance(role, str):
        return None
    return source, role, data


def main() -> None:
    load_env()
    try:
        from uagents import Agent, Context, Protocol
        from uagents_core.contrib.protocols.chat import (ChatAcknowledgement, ChatMessage,
                                                         TextContent, chat_protocol_spec)
    except ImportError as exc:
        raise SystemExit("uAgents is not installed in this environment. Run:\n"
                         "    python -m pip install uagents\n"
                         f"({type(exc).__name__}: {exc})")

    seed = os.environ.get("WILIREHAB_SEED") or "wilirehab-local-development-seed"
    allowed = {a.strip() for a in os.environ.get("WILIREHAB_ALLOWED_SENDERS", "").split(",")
               if a.strip()}
    ingress = AgentIngress()

    agent = Agent(name="wilirehab_gateway", seed=seed + "-gateway", port=PORT,
                  mailbox=True, publish_agent_details=True)
    protocol = Protocol(spec=chat_protocol_spec)

    @protocol.on_message(ChatMessage)
    async def _received(ctx: Context, sender: str, msg: ChatMessage):
        # Acknowledge first, as the chat protocol expects, so the sender is not left waiting.
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(),
                                                   acknowledged_msg_id=msg.msg_id))
        if sender not in allowed:
            ctx.logger.warning(f"ignored a message from {sender[:20]}...: it is not in "
                               "WILIREHAB_ALLOWED_SENDERS")
            return
        text = "".join(item.text for item in msg.content if isinstance(item, TextContent))
        parsed = parse_external(text)
        if parsed is None:
            ctx.logger.warning("ignored a message that is not a valid WiliRehab message")
            return
        source, role, data = parsed
        ingress.publish(source, role, data)
        ctx.logger.info(f"passed a '{source}' message from {sender[:20]}... to the agents program")

    @protocol.on_message(ChatAcknowledgement)
    async def _ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass                                     # we send nothing that needs a receipt

    agent.include(protocol, publish_manifest=True)

    print(f"Gateway {agent.address}")
    print("Allowed senders:", ", ".join(sorted(allowed)) if allowed else
          "none yet (set WILIREHAB_ALLOWED_SENDERS in .env; until then every message is ignored)")
    uri = quote(f"http://127.0.0.1:{PORT}", safe="/")
    print("To show it in Agentverse: open this while it runs, click Connect, then Mailbox:\n"
          f"  https://agentverse.ai/inspect/?uri={uri}&address={agent.address}")
    agent.run()


if __name__ == "__main__":
    main()
