"""Put all four stage agents on Agentverse, each as its own agent with its own mailbox.

    python -m orca.agent_stage            start all four, one program each (the normal way)
    python -m orca.agent_stage check      start just one: filter, check, decide or act

Why separate programs: Agentverse's Inspector can only connect a standalone agent on its own port
(an agent inside a Bureau, as in agents_main, cannot be connected: "Could not find this Agent on
your local host"). So here each stage is its own uAgent with a mailbox, like the gateway.

WHAT THIS CHANGES, plainly: the four agents are each on Agentverse (mailbox, profile, ASI:One chat).
The stages' own messages to each other go DIRECTLY to each other's local endpoint on this laptop
(local_first_resolver), so the chain works even if a mailbox is not connected. Set
ORCA_STAGE_LOCAL_LINKS=0 to send them through Agentverse instead (internet needed, a second or two of
delay per hop, numbers pass through Fetch.ai's servers). Questions from ASI:One always use the
mailbox. Use this only with the SIMULATED patient (participant DEMO-Maya), never with a real
person's data. The private default stays agents_main.

One-time setup per agent (the first time only; the connection is remembered):
  1. Start this, then open the Inspector link printed for each agent (four links).
  2. In each: Connect, then Mailbox, and follow the steps.
  3. Each agent then appears in your Agentverse, with a profile page whose URL you can copy.
Do not run this and agents_main together: both want the games' local port.

The four agents also answer questions in the ASI:One chat about their own stage ("what have you been
doing?") when ORCA_PUBLIC_ANSWERS=1; see explain.py. Not yet run against a real uAgents install.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from .agents_main import listen
from .env import load_env
from .stage_agents import STAGES, build_world, install

HOST_DIR = Path(__file__).resolve().parents[1]
PORTS = {"filter": 8101, "check": 8102, "decide": 8103, "act": 8104}     # 8000 Bureau, 8001 gateway
DEFAULT_SEED = "wilirehab-local-development-seed"


def address_of(seed_text: str) -> str:
    """The address an agent with this seed will have, without starting it."""
    from uagents import Agent
    return Agent(name="address-probe", seed=seed_text).address


def local_first_resolver(local: dict):
    """Where to send a message: the four stages on this laptop are reached DIRECTLY at their local
    endpoints (instant, offline, and the numbers stay on the laptop); anyone else, such as ASI:One
    answering a question, goes through the normal Agentverse lookup and mailbox."""
    from uagents.resolver import GlobalResolver, Resolver

    class LocalFirst(Resolver):
        def __init__(self):
            self._global = GlobalResolver()

        async def resolve(self, destination):
            if destination in local:
                return destination, [local[destination]]
            return await self._global.resolve(destination)

    return LocalFirst()


def run_one(stage: str) -> None:
    """Run ONE stage as its own agent with a mailbox. Blocks until stopped."""
    load_env()
    try:
        from uagents import Agent
    except ImportError as exc:
        raise SystemExit("uAgents is not installed in this environment. Run:\n"
                         "    python -m pip install uagents\n"
                         f"({type(exc).__name__}: {exc})")
    import os
    seed = os.environ.get("ORCA_SEED") or DEFAULT_SEED
    addresses = {s: address_of(f"{seed}-{s}") for s in STAGES}
    w = build_world(addresses, local=False, transport="uAgents, Agentverse mailbox")
    # Stage-to-stage messages go straight to each other's local endpoint unless ORCA_STAGE_LOCAL_LINKS=0
    # (then they go through Agentverse, which needs every mailbox connected). Questions from ASI:One
    # always use the mailbox.
    resolver = None
    if os.environ.get("ORCA_STAGE_LOCAL_LINKS", "1").strip().lower() not in ("0", "false", "no", "off"):
        resolver = local_first_resolver({addresses[s]: f"http://127.0.0.1:{PORTS[s]}/submit" for s in STAGES})
    agent = Agent(name=f"orca_{stage}", seed=f"{seed}-{stage}", port=PORTS[stage],
                  mailbox=True, publish_agent_details=True, resolve=resolver)
    if agent.address != addresses[stage]:                 # should never differ; say so if it does
        print(f"warning: computed address {addresses[stage]} differs from the agent's {agent.address}")
        addresses[stage] = agent.address
    if stage == "filter":                                 # only the Filter agent hears the games
        threading.Thread(target=listen, args=(w.registry, w.inbox), daemon=True).start()
    install(agent, w, stage, mailbox=True)

    uri = quote(f"http://127.0.0.1:{PORTS[stage]}", safe="/")
    print(f"{stage.capitalize()} agent {agent.address}")
    print(f"  Inspector (Connect, then Mailbox): https://agentverse.ai/inspect/?uri={uri}"
          f"&address={agent.address}")
    print("  Public answers in ASI:One:", "ON" if w.public_answers else
          "OFF (ORCA_PUBLIC_ANSWERS=1 in .env turns them on)")
    agent.run()


def launch_all() -> int:
    """Start the four stages as four child programs and show their output together."""
    print("Starting the four agents as separate programs, each with its own Agentverse mailbox.")
    print("This sends their messages through Agentverse: use it with SIMULATED data only.\n")
    children = []
    for stage in STAGES:
        child = subprocess.Popen([sys.executable, "-u", "-m", f"{__package__}.agent_stage", stage],
                                 cwd=HOST_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1)
        children.append((stage, child))

        def pump(name=stage, proc=child):
            for line in proc.stdout:
                print(f"{name:<7}| {line.rstrip()}", flush=True)

        threading.Thread(target=pump, daemon=True).start()
        time.sleep(1.0)                                   # stagger the starts
    try:
        while any(c.poll() is None for _s, c in children):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping the agents...")
    finally:
        for _stage, child in children:
            if child.poll() is None:
                child.terminate()
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] not in STAGES:
            raise SystemExit(f"stage must be one of {', '.join(STAGES)}")
        run_one(sys.argv[1])
        return 0
    return launch_all()


if __name__ == "__main__":
    raise SystemExit(main())
