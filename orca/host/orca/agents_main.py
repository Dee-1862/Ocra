"""The Orca agent network, built on Fetch.ai's uAgents: one agent per stage, in a chain.

    python -m orca.agents_main

    Filter agent  -> drops implausible hand readings and readings with no face, says what it
                     dropped, summarises each 10 s window (the balance between the two hands, the
                     person's discomfort against their own baseline) and passes it on.
    Check agent   -> when a round ends, fact-checks any imbalance between the hands four ways
                     (enough data? persistent? unusual for THIS person? do other signals agree?).
    Decide agent  -> gives the verdict, then the difficulty recommendation and the rule behind it. A
                     finding that is not fully verified can never make the game harder.
    Act agent     -> saves the round and the clean readings (local queue, then Supabase) and
                     states the recommendation.

This is the LOCAL mode: all four agents run in one program on this computer, private, with no
internet needed. To put all four on Agentverse (so they can be seen and chatted with in ASI:One),
use `python -m orca.agent_stage` instead; that mode sends the agents' messages through
Agentverse, so use it with simulated data only. The stages' behaviour is the same in both: it lives
in stage_agents.py.

The games and the OGs feed the Filter agent over a local UDP port; the stages pass chat messages
(JSON text) down the chain, each only accepting messages from the stage before it. Every step is
printed here, kept in the status file (the OG's pages and the gateway read it), and appended to
agents_trace.jsonl so a session can be audited line by line.

Settings come from orca/host/.env (see .env.example). The thresholds in skills.CHECKS are
placeholders, not clinically validated.

No ASI:One key, no mailbox and no internet are needed for the agents to talk to each other: they
share this process. Outside agents (the Pi, ASI:One) reach the chain only through agent_gateway.
The OG is not an agent and does not run one.
"""
from __future__ import annotations

import os
import socket
import threading

from .agent_graph import Registry
from .agent_link import PORT, decode
from .env import load_env
from .stage_agents import STAGES, build_world, install


def listen(registry: Registry, inbox: dict) -> None:
    """Receive the games' datagrams and sort them to the Filter agent. Runs on its own thread."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", PORT))
    while True:
        raw, _addr = sock.recvfrom(65535)
        msg = decode(raw)
        if msg is None:
            continue
        if msg["source"] == "hand":
            registry.beat("og")                       # hand numbers only flow while a game plays
            inbox["hand"].put(msg)
        elif msg["source"] == "round":
            print("[listener] received a 'round' message from a game or the gateway")
            inbox["hand"].put(msg)                    # a round comes from the same OG session
        elif msg["source"] == "face":
            registry.beat("cam")
            inbox["face"].put(msg)


def main() -> None:
    load_env()
    try:
        from uagents import Agent, Bureau
    except ImportError as exc:
        raise SystemExit("uAgents is not installed in this environment. Run:\n"
                         "    python -m pip install uagents\n"
                         f"({type(exc).__name__}: {exc})")

    seed = os.environ.get("ORCA_SEED")
    if not seed:
        print("note: ORCA_SEED is not set; using a fixed development seed. Set your own "
              "in .env so the agents have your own identities.")
        seed = "wilirehab-local-development-seed"

    agents = {s: Agent(name=f"orca_{s}", seed=f"{seed}-{s}") for s in STAGES}
    addresses = {s: a.address for s, a in agents.items()}
    w = build_world(addresses, local=True, transport="uAgents, local")
    threading.Thread(target=listen, args=(w.registry, w.inbox), daemon=True).start()
    for stage in STAGES:
        install(agents[stage], w, stage, mailbox=False)

    for stage in STAGES:
        print(f"{stage.capitalize() + ' agent':<14}{addresses[stage]}")
    store = w.stores["rounds"]
    print("Supabase:", f"configured; tables rounds, hand_readings, face_readings; a snapshot "
                       f"every {w.hand_sampler.interval:g} s" if store.configured else
          "not configured (rows queue in the agents_queue*.jsonl files)")
    print("Every agent step is printed here and saved in agents_trace.jsonl. To put the four agents "
          "on Agentverse: python -m orca.agent_stage (simulated data only).")
    # The address other machines use to reach these agents. The default only works on this
    # computer. For the Pi on the same Wi-Fi use the laptop's own address, for example
    # http://192.168.1.20:8000/submit (and allow Python through the Windows firewall when it
    # asks). The Bureau also registers the agents in Fetch.ai's public Almanac with it.
    endpoint = os.environ.get("ORCA_ENDPOINT") or "http://127.0.0.1:8000/submit"
    print("Endpoint:", endpoint)
    try:
        bureau = Bureau(port=8000, endpoint=[endpoint])
    except TypeError:                       # some versions take a single string
        bureau = Bureau(port=8000, endpoint=endpoint)
    for agent in agents.values():
        bureau.add(agent)
    bureau.run()


if __name__ == "__main__":
    main()
