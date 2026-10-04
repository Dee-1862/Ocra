"""A stand-in for an outside agent (the Raspberry Pi, later): sends one fake round to the gateway.

    python -m wilirehab.agent_test_client [gateway address]

The gateway address is the `Gateway agent1q...` line printed by agent_gateway; give it on the
command line or as WILIREHAB_GATEWAY_ADDRESS in .env. This client prints its own address when
it starts: put that address in WILIREHAB_ALLOWED_SENDERS in .env and restart the gateway, or the
gateway will (correctly) ignore the message.

The round it sends is marked game "gateway_test" so it is easy to find and delete in Supabase.
Press Ctrl+C when you have seen the acknowledgement.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from uuid import uuid4

from .env import load_env


def main() -> None:
    load_env()
    gateway = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WILIREHAB_GATEWAY_ADDRESS", "")).strip()
    if not gateway.startswith("agent1"):
        raise SystemExit("Give the gateway's address (agent1q...): either as an argument, or as "
                         "WILIREHAB_GATEWAY_ADDRESS in .env. It is on the 'Gateway ...' line "
                         "printed by python -m wilirehab.agent_gateway")
    try:
        from uagents import Agent, Context
        from uagents_core.contrib.protocols.chat import (ChatAcknowledgement, ChatMessage,
                                                         TextContent)
    except ImportError as exc:
        raise SystemExit("uAgents is not installed in this environment. Run:\n"
                         "    python -m pip install uagents\n"
                         f"({type(exc).__name__}: {exc})")

    seed = os.environ.get("WILIREHAB_SEED") or "wilirehab-local-development-seed"
    agent = Agent(name="wilirehab_test_client", seed=seed + "-test-client", port=8002,
                  endpoint=["http://127.0.0.1:8002/submit"])

    payload = {"source": "round", "role": "right_hand", "data": {
        "game": "gateway_test", "session_id": "gateway-test", "seconds": 30.0,
        "hits": 8, "attempts": 10, "pain_events": 0, "pain_score": 2}}

    @agent.on_event("startup")
    async def _send(ctx: Context):
        ctx.logger.info(f"my address (add it to WILIREHAB_ALLOWED_SENDERS): {agent.address}")
        await ctx.send(gateway, ChatMessage(timestamp=datetime.now(), msg_id=uuid4(),
                                            content=[TextContent(type="text",
                                                                 text=json.dumps(payload))]))
        ctx.logger.info("sent one test round to the gateway")

    @agent.on_message(ChatAcknowledgement)
    async def _ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        ctx.logger.info(f"the gateway acknowledged the message (from {sender[:20]}...)")

    agent.run()


if __name__ == "__main__":
    main()
