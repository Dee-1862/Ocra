"""The gateway: the one agent that talks to Agentverse and to agents outside this computer.

    python -m orca.agent_gateway          (run it next to agents_main)

It is a standalone uAgent with a mailbox, set up the way Fetch.ai's chat-protocol example does
it, so Agentverse's Inspector can find and connect it (port 8001). It does two jobs:
  1. Data in: when an agent you have allowed (ORCA_ALLOWED_SENDERS, for example one on the
     Raspberry Pi) sends it JSON {"source": "hand" | "face" | "round", "role": "...", "data": {...}},
     it checks the message and hands it to the Filter agent over the same local channel the games
     use. The games' own hand and face numbers never go through the mailbox.
  2. Questions out: any other text, for example from ASI:One chat, is a question ("why is the
     verdict that?"). It is answered read-only from the agents' own step log (see explain.py), and
     only if ORCA_PUBLIC_ANSWERS=1, because that data is a real person's. No AI model is used
     and no API key is needed.

Not yet run against a real uAgents install: see Card 26, part D, in notebook/manual-tests.md.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

from .agent_link import AgentIngress, fresh_status
from .env import load_env
from .explain import explain

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
                                                         EndSessionContent, TextContent,
                                                         chat_protocol_spec)
    except ImportError as exc:
        raise SystemExit("uAgents is not installed in this environment. Run:\n"
                         "    python -m pip install uagents\n"
                         f"({type(exc).__name__}: {exc})")

    seed = os.environ.get("ORCA_SEED") or "wilirehab-local-development-seed"
    allowed = {a.strip() for a in os.environ.get("ORCA_ALLOWED_SENDERS", "").split(",")
               if a.strip()}
    ingress = AgentIngress()
    public = os.environ.get("ORCA_PUBLIC_ANSWERS", "").strip().lower() in ("1", "true", "yes", "on")

    agent = Agent(name="orca_gateway", seed=seed + "-gateway", port=PORT,
                  mailbox=True, publish_agent_details=True)
    protocol = Protocol(spec=chat_protocol_spec)

    @protocol.on_message(ChatMessage)
    async def _received(ctx: Context, sender: str, msg: ChatMessage):
        # Acknowledge first, as the chat protocol expects, so the sender is not left waiting.
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(),
                                                   acknowledged_msg_id=msg.msg_id))
        text = "".join(item.text for item in msg.content if isinstance(item, TextContent))
        parsed = parse_external(text)
        if parsed is not None:                   # data: only from agents you have allowed
            if sender not in allowed:
                ctx.logger.warning(f"ignored data from {sender[:20]}...: it is not in "
                                   "ORCA_ALLOWED_SENDERS")
                return
            source, role, data = parsed
            ingress.publish(source, role, data)
            ctx.logger.info(f"passed a '{source}' message from {sender[:20]}... to the agents program")
            return
        # Anything else is a question (from ASI:One, say). It is answered read-only from the agents'
        # own step log, and only if the operator has switched public answers on.
        answer = explain(text, fresh_status(), public=public)
        ctx.logger.info(f"answered a question from {sender[:20]}...: {text[:60]!r}")
        await ctx.send(sender, ChatMessage(timestamp=datetime.now(), msg_id=uuid4(), content=[
            TextContent(type="text", text=answer), EndSessionContent(type="end-session")]))

    @protocol.on_message(ChatAcknowledgement)
    async def _ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass                                     # we send nothing that needs a receipt

    agent.include(protocol, publish_manifest=True)

    print(f"Gateway {agent.address}")
    print("Public answers (what the agents did, for ASI:One):",
          "ON, from the live step log" if public else
          "OFF (set ORCA_PUBLIC_ANSWERS=1 in .env to turn them on)")
    print("Allowed senders:", ", ".join(sorted(allowed)) if allowed else
          "none yet (set ORCA_ALLOWED_SENDERS in .env; until then every message is ignored)")
    uri = quote(f"http://127.0.0.1:{PORT}", safe="/")
    print("To show it in Agentverse: open this while it runs, click Connect, then Mailbox:\n"
          f"  https://agentverse.ai/inspect/?uri={uri}&address={agent.address}")
    agent.run()


if __name__ == "__main__":
    main()
