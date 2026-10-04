"""The WiliRehab agent network, built on Fetch.ai's uAgents.

    python -m wilirehab.agents_main

Three agents run together in one Bureau on this computer:
    hand agent   takes the hand numbers and finished-round summaries the games send, and
                 passes them on to the orchestrator as chat messages (JSON text);
    face agent   does the same for the webcam's face numbers;
    orchestrator receives both, turns each finished round into a database row, applies the
                 rule table (adapt.py) for a difficulty recommendation, saves rows to a local
                 queue and sends them to Supabase when it can, and writes the status file the
                 OG's Agents page draws.

Settings come from wilirehab/host/.env (see .env.example): SUPABASE_URL and SUPABASE_KEY are
optional (without them rows only queue locally), WILIREHAB_SEED sets the agents' identities,
WILIREHAB_PARTICIPANT is the pseudonymous participant code.

No ASI:One key, no mailbox and no internet are needed for the agents to talk to each other:
they share this process. They are given an endpoint (WILIREHAB_ENDPOINT, default
http://127.0.0.1:8000/submit) and registered in Fetch.ai's public Almanac with it, so another
machine can message them if it can reach that address: the Pi on the same Wi-Fi can, a cloud
host such as Render cannot reach a laptop behind a home router (that needs an Agentverse
mailbox or a public URL). The orchestrator only accepts messages from our own agents and from
WILIREHAB_ALLOWED_SENDERS. The OG is not an agent and does not run one: the "hand agent" is
software here that reads what the OG sent.

Not yet run against a real uAgents install: see Card 26 in notebook/manual-tests.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import socket
import threading
from datetime import datetime
from uuid import uuid4

from .agent_graph import Registry
from .agent_link import PORT, decode, write_status
from .env import load_env
from .orchestrator_core import Orchestrator
from .readings import Sampler, face_row, hand_row
from .round_store import QUEUE_FILE, RoundStore


def listen(registry: Registry, inbox: dict) -> None:
    """Receive the games' datagrams and sort them to the right agent. Runs on its own thread."""
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
            print("[1 listener] received a 'round' message from a game or the gateway")
            inbox["hand"].put(msg)                    # a round comes from the same OG session
        elif msg["source"] == "face":
            registry.beat("cam")
            inbox["face"].put(msg)


def main() -> None:
    load_env()
    try:
        from uagents import Agent, Bureau, Context
        from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
    except ImportError as exc:
        raise SystemExit("uAgents is not installed in this environment. Run:\n"
                         "    python -m pip install uagents\n"
                         f"({type(exc).__name__}: {exc})")

    seed = os.environ.get("WILIREHAB_SEED")
    if not seed:
        print("note: WILIREHAB_SEED is not set; using a fixed development seed. Set your own "
              "in .env so the agents have your own identities.")
        seed = "wilirehab-local-development-seed"

    registry = Registry()
    core = Orchestrator(os.environ.get("WILIREHAB_PARTICIPANT", "P000"))
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    # One table per agent, each with its own local queue file, so one table failing never holds
    # up another: rounds (orchestrator), hand_readings (hand agent), face_readings (face agent).
    store = RoundStore(url, key)
    hand_store = RoundStore(url, key, path=QUEUE_FILE.with_name("agents_queue_hand.jsonl"),
                            table="hand_readings")
    face_store = RoundStore(url, key, path=QUEUE_FILE.with_name("agents_queue_face.jsonl"),
                            table="face_readings")
    try:
        sample_s = max(0.0, float(os.environ.get("WILIREHAB_SAMPLE_S", "5")))
    except ValueError:
        sample_s = 5.0
    inbox = {"hand": queue.Queue(), "face": queue.Queue()}
    threading.Thread(target=listen, args=(registry, inbox), daemon=True).start()

    orch = Agent(name="wilirehab_orchestrator", seed=seed + "-orchestrator")
    hand = Agent(name="wilirehab_hand", seed=seed + "-hand")
    face = Agent(name="wilirehab_face", seed=seed + "-face")

    # Who the orchestrator listens to. Its address can now be reached from outside, and what it
    # receives becomes database rows, so only our own agents (and any extra ones you name in
    # WILIREHAB_ALLOWED_SENDERS, for example an agent on the Pi) are accepted.
    extra = os.environ.get("WILIREHAB_ALLOWED_SENDERS", "")
    allowed = {hand.address, face.address} | {a.strip() for a in extra.split(",") if a.strip()}

    async def flush_store(ctx: Context, st: RoundStore, label: str) -> None:
        """Send one table's queued rows to Supabase, off the event loop."""
        if not st.configured:
            return
        sent = await asyncio.get_running_loop().run_in_executor(None, st.flush)
        if sent:
            registry.beat("db", note=f"sent {sent}")
            ctx.logger.info(f"sent {sent} {label} row(s) to Supabase")
        elif st.last_error:
            registry.note("db", "send failed")
            ctx.logger.warning(f"Supabase send failed ({label}): {st.last_error}")

    def forward(agent, source_queue, key: str, own_store: RoundStore, kind: str, build) -> None:
        """Every 0.2 s, pass whatever the games sent to the orchestrator as chat messages, and
        keep a snapshot of this agent's own kind of reading (`kind`) in its own table."""
        sampler = Sampler(sample_s)

        @agent.on_interval(period=0.2)
        async def _forward(ctx: Context):
            while True:
                try:
                    msg = source_queue.get_nowait()
                except queue.Empty:
                    return
                await ctx.send(orch.address, ChatMessage(
                    timestamp=datetime.now(), msg_id=uuid4(),
                    content=[TextContent(type="text", text=json.dumps(msg))]))
                registry.beat(key)
                if msg.get("source") == "round":
                    ctx.logger.info("[2 hand/face agent] passed a 'round' message to the orchestrator")
                if msg.get("source") == kind and sampler.due(msg.get("role")):
                    own_store.add(build(core.participant, msg))

        @agent.on_interval(period=5.0)
        async def _flush_own(ctx: Context):
            await flush_store(ctx, own_store, kind)

    forward(hand, inbox["hand"], "hand_agent", hand_store, "hand", hand_row)
    forward(face, inbox["face"], "face_agent", face_store, "face", face_row)

    @orch.on_message(ChatMessage)
    async def _received(ctx: Context, sender: str, msg: ChatMessage):
        if sender not in allowed:
            ctx.logger.warning(f"ignored a message from an unknown sender ({sender[:20]}...)")
            return
        text = "".join(item.text for item in msg.content if isinstance(item, TextContent))
        try:
            data = json.loads(text)
        except ValueError:
            ctx.logger.error("received a message that is not JSON")
            return
        registry.beat("orch")
        row = core.ingest(data)
        if row is not None:
            store.add(row)
            registry.note("orch", f"{row['decision']}")
            ctx.logger.info(f"[3 orchestrator] round: {row['game']} hit_rate={row['hit_rate']} "
                            f"-> {row['decision']} ({row['decision_reason']})")

    @orch.on_interval(period=5.0)
    async def _flush(ctx: Context):
        if not store.configured:
            registry.note("db", "not configured")
            return
        await flush_store(ctx, store, "round")

    @orch.on_interval(period=0.5)
    async def _status(ctx: Context):
        snap = registry.snapshot()
        snap.update({"transport": "uAgents, local", "participant": core.participant,
                     "decision": core.last_decision, "store": store.status_text()})
        write_status(snap)

    print(f"Orchestrator {orch.address}")
    print(f"Hand agent   {hand.address}")
    print(f"Face agent   {face.address}")
    print("Supabase:", f"configured; tables rounds, hand_readings, face_readings; "
                       f"a hand and face snapshot every {sample_s:g} s" if store.configured else
          "not configured (rows queue in the agents_queue*.jsonl files)")
    print("For Agentverse and messages from outside agents, also run: "
          "python -m wilirehab.agent_gateway")
    # The address other machines use to reach these agents. The default only works on this
    # computer. For the Pi on the same Wi-Fi use the laptop's own address, for example
    # http://192.168.1.20:8000/submit (and allow Python through the Windows firewall when it
    # asks). The Bureau also registers the agents in Fetch.ai's public Almanac with it.
    endpoint = os.environ.get("WILIREHAB_ENDPOINT") or "http://127.0.0.1:8000/submit"
    print("Endpoint:", endpoint)
    try:
        bureau = Bureau(port=8000, endpoint=[endpoint])
    except TypeError:                       # some versions take a single string
        bureau = Bureau(port=8000, endpoint=endpoint)
    for agent in (orch, hand, face):
        bureau.add(agent)
    bureau.run()


if __name__ == "__main__":
    main()
