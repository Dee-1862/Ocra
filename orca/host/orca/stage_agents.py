"""The four stage agents (Filter, Check, Decide, Act), written once and hosted two ways.

    agents_main   all four in one Bureau on this computer: local, private, no internet needed.
    agent_stage   each stage as its own program with an Agentverse mailbox, so all four show up
                  in your Agentverse and can be chatted with in ASI:One. Their messages then travel
                  through Agentverse, so use that mode with SIMULATED data only.

`Deps` is everything the stages share; the runner builds it and calls `install()` for each agent.
uAgents is imported only inside the functions that need it, so this module can be imported (and its
helpers tested) without it.

Messages between stages are chat messages carrying JSON {"source", "role", "data"}:
    Filter -> Check    hand_window, face_window, round
    Check  -> Decide   finding
    Decide -> Act      decision
    Filter -> Act      store_batch   (clean readings to keep, sent in one message every few seconds)
Each stage only accepts data from the stage before it (UPSTREAM). Any other chat message is a
QUESTION: it is answered read-only from the step log (explain.py), and only when the operator has
turned answers on (ORCA_PUBLIC_ANSWERS=1) and the agent is in mailbox mode.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
from datetime import datetime
from uuid import uuid4

from .agent_graph import Registry
from .agent_link import fresh_status, write_stage_status, write_status
from .agent_steps import TRACE_FILE, StepLog
from .explain import explain
from .orchestrator_core import HISTORY_FILE, Actor, Checker, Decider, RatioHistory
from .readings import Sampler, face_row, hand_row
from .round_store import QUEUE_FILE, RoundStore
from .skills import CHECKS, FaceFilter, HandFilter, active_hands, balance

STAGES = ("filter", "check", "decide", "act")
# Who may send each stage its data. The Filter agent is fed by the games over a local port instead.
UPSTREAM = {"filter": (), "check": ("filter",), "decide": ("check",), "act": ("decide", "filter")}


def short(role) -> str:
    """'left_hand' -> 'left', for short step lines."""
    return str(role).replace("_hand", "")


def dropped_text(dropped: dict) -> str:
    return ", ".join(f"{n} {why}" for why, n in dropped.items())


def _chat():
    from uagents_core.contrib.protocols.chat import (ChatAcknowledgement, ChatMessage,
                                                     EndSessionContent, TextContent)
    return ChatAcknowledgement, ChatMessage, EndSessionContent, TextContent


async def send_json(ctx, to: str, payload: dict) -> None:
    _ack, ChatMessage, _end, TextContent = _chat()
    sent = await ctx.send(to, ChatMessage(timestamp=datetime.now(), msg_id=uuid4(),
                                          content=[TextContent(type="text", text=json.dumps(payload))]))
    # Say so when a hand-off fails, and when a finished round is handed on: otherwise a broken link
    # between two agents is silent and the later agents just never hear anything.
    state = str(getattr(getattr(sent, "status", None), "value", getattr(sent, "status", "")) or "").lower()
    kind = payload.get("source")
    if state == "failed":
        ctx.logger.warning(f"could not deliver a '{kind}' message to {to[:16]}...: "
                           f"{getattr(sent, 'detail', '')}")
    elif kind in ("round", "finding", "decision"):
        ctx.logger.info(f"handed a '{kind}' message to {to[:16]}... ({state or 'sent'})")


def text_of(msg) -> str:
    return "".join(item.text for item in msg.content if hasattr(item, "text"))


def read_json(msg):
    """The JSON object a chat message carries, or None if it is plain text (a question)."""
    try:
        data = json.loads(text_of(msg))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class Deps:
    """What the four stages share: state, addresses, and how to report."""

    def __init__(self, *, registry, steps, say, cfg, participant, checker, decider, actor, stores,
                 inbox, sample_s, addresses, transport, local, public_answers=False,
                 store_batch_s=5.0):
        self.registry, self.steps, self.say, self.cfg = registry, steps, say, cfg
        self.participant, self.checker, self.decider, self.actor = participant, checker, decider, actor
        self.stores, self.inbox, self.addresses = stores, inbox, addresses
        self.transport, self.local = transport, local          # local = all four in one program
        self.public_answers, self.store_batch_s = public_answers, store_batch_s
        self.hand_filter, self.face_filter = HandFilter(cfg), FaceFilter(cfg)
        self.hand_sampler, self.face_sampler = Sampler(sample_s), Sampler(sample_s)
        self.pending: list = []                               # clean readings waiting for the Act agent

    def upstream(self, stage: str) -> set:
        return {self.addresses[s] for s in UPSTREAM[stage]}

    def extras(self, stage: str) -> dict:
        """The status fields a stage owns (all of them in local mode, where one file holds everything)."""
        verdict, decision = self.checker.last_verdict, self.decider.last_decision
        parts = {
            "filter": {"participant": self.participant, "window_s": self.cfg["window_s"]},
            "check": {"verdict": None if verdict is None else
                      {"verdict": verdict["verdict"], "level": verdict["level"],
                       "checks": verdict["checks"], "mean_ratio": verdict["mean_ratio"]}},
            "decide": {"decision": decision},
            "act": {"store": self.stores["rounds"].status_text()},
        }
        if self.local:
            merged = {}
            for p in parts.values():
                merged.update(p)
            return merged
        return parts[stage]

    def write_status(self, stage: str) -> None:
        snap = self.registry.snapshot()
        snap.update(self.extras(stage))
        snap.update({"transport": self.transport, "steps": self.steps.recent(14)})
        if self.local:
            write_status(snap)
        else:
            write_stage_status(stage, snap)


def build_world(addresses: dict, local: bool, transport: str) -> Deps:
    """The shared state for a runner, built from the environment (see .env.example)."""
    participant = os.environ.get("ORCA_PARTICIPANT", "P000")
    registry, steps = Registry(), StepLog(TRACE_FILE)

    def say(stage: str, text: str, level: str = "info") -> None:
        """One visible step: kept for the OG's Steps page, the trace file and the terminal."""
        steps.add(stage, stage, text, level)
        print(f"[{stage}] {text}")

    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    # One table each, each with its own local queue file, so one failing never holds up another.
    stores = {
        "rounds": RoundStore(url, key),
        "hand_readings": RoundStore(url, key, path=QUEUE_FILE.with_name("agents_queue_hand.jsonl"),
                                    table="hand_readings"),
        "face_readings": RoundStore(url, key, path=QUEUE_FILE.with_name("agents_queue_face.jsonl"),
                                    table="face_readings")}
    try:
        sample_s = max(0.0, float(os.environ.get("ORCA_SAMPLE_S", "5")))
    except ValueError:
        sample_s = 5.0
    cfg = dict(CHECKS)                    # the window can be shortened (ORCA_WINDOW_S) for a demo
    try:
        cfg["window_s"] = max(0.5, float(os.environ.get("ORCA_WINDOW_S", cfg["window_s"])))
    except ValueError:
        pass
    # "Usual for this person" is kept per participant, so a demo can never join a real baseline.
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in participant) or "unknown"
    checker = Checker(RatioHistory(HISTORY_FILE.with_name(f"agents_history_{safe}.json")), say, cfg)
    public = os.environ.get("ORCA_PUBLIC_ANSWERS", "").strip().lower() in ("1", "true", "yes", "on")
    return Deps(registry=registry, steps=steps, say=say, cfg=cfg, participant=participant,
                checker=checker, decider=Decider(say=say), actor=Actor(participant, stores, say),
                stores=stores, inbox={"hand": queue.Queue(), "face": queue.Queue()},
                sample_s=sample_s, addresses=addresses, transport=transport, local=local,
                public_answers=public)


# ---- the stages ---------------------------------------------------------------------------------------------

def install_filter(agent, w: Deps) -> None:
    """FILTER: drop implausible readings, summarise each window, hand clean readings on."""
    from uagents import Context
    chk = w.addresses["check"]

    @agent.on_interval(period=0.2)
    async def _filter_work(ctx: Context):
        w.registry.alive("filter")
        while True:
            try:
                msg = w.inbox["hand"].get_nowait()
            except queue.Empty:
                break
            w.registry.beat("filter")
            if msg["source"] == "round":                  # a finished round: on to the Check agent
                await send_json(ctx, chk, msg)
                continue
            role = msg.get("role") or "unknown"
            if w.hand_filter.add(role, msg.get("data") or {}):
                continue                                  # dropped: counted, reported at the window end
            if w.hand_sampler.due(role):                  # a clean reading, kept for the table
                w.pending.append({"table": "hand_readings", "row": hand_row(w.participant, msg)})
        while True:
            try:
                msg = w.inbox["face"].get_nowait()
            except queue.Empty:
                break
            w.registry.beat("filter")
            if w.face_filter.add(msg.get("data") or {}):
                continue
            if w.face_sampler.due(msg.get("role")):
                w.pending.append({"table": "face_readings", "row": face_row(w.participant, msg)})

        if w.hand_filter.window_done():
            summary = w.hand_filter.summarize()
            kept = sum(s["kept"] for s in summary.values())
            seen = sum(s["seen"] for s in summary.values())
            for role, s in summary.items():
                drops = dropped_text(s["dropped"])
                w.say("filter", f"{short(role)} hand: kept {s['kept']} of {s['seen']}"
                      + (f", dropped {drops}" if drops else ""), "warn" if drops else "ok")
            w.registry.note("filter", f"kept {kept} of {seen}")
            bal = balance(summary, w.cfg)
            played = active_hands(summary, w.cfg)
            if bal is None and len(played) == 1:
                w.say("filter", f"only the {short(played[0])} hand played: nothing to compare")
            elif bal is None and len(summary) > 1:
                w.say("filter", "hands not compared: one of them did not move enough")
            if bal is not None:
                weak = "equal" if bal["weaker"] == "equal" else f"{short(bal['weaker'])} weaker"
                w.say("filter", f"hands compared: {bal['rom_ratio']:.2f} ({weak}; range "
                      f"{bal['left_rom']:.0f} vs {bal['right_rom']:.0f})",
                      "warn" if bal["rom_ratio"] < w.cfg["balance_watch"] else "ok")
            await send_json(ctx, chk, {"source": "hand_window", "role": None,
                                       "data": {"summary": summary, "balance": bal}})
        if w.face_filter.window_done():
            s = w.face_filter.summarize()
            drops = dropped_text(s["dropped"])
            w.say("filter", f"face: kept {s['kept']} of {s['seen']}"
                  + (f", dropped {drops}" if drops else ""), "warn" if drops else "ok")
            level = s["level"]
            if level == "learning":
                w.say("filter", "face: learning their calm baseline first")
            else:
                heart = f", pulse {s['bpm']}" if s["bpm"] is not None else ""
                w.say("filter", f"face: discomfort {level} (pspi {s['pspi']} vs their baseline "
                      f"{s['baseline']}{heart})", {"calm": "ok", "rising": "warn", "high": "alert"}[level])
            await send_json(ctx, chk, {"source": "face_window", "role": None, "data": s})

    @agent.on_interval(period=w.store_batch_s)
    async def _send_readings(ctx: Context):
        """Clean readings go to the Act agent in ONE message every few seconds, not one each."""
        if w.pending:
            items, w.pending = w.pending, []
            await send_json(ctx, w.addresses["act"], {"source": "store_batch", "data": {"items": items}})


def make_handlers(w: Deps) -> dict:
    """What Check, Decide and Act do with a data message from the stage before them."""
    async def on_check(ctx, data):
        w.registry.beat("check")
        finding = w.checker.ingest(data)
        if finding is not None:
            w.registry.note("check", finding["result"]["verdict"])
            await send_json(ctx, w.addresses["decide"], {"source": "finding", "role": finding["role"],
                                                         "data": finding})

    async def on_decide(ctx, data):
        if data.get("source") != "finding":
            return
        w.registry.beat("decide")
        decided = w.decider.decide(data["data"])
        w.registry.note("decide", decided["decision"]["action"])
        await send_json(ctx, w.addresses["act"], {"source": "decision", "role": decided.get("role"),
                                                  "data": decided})

    async def on_act(ctx, data):
        row = w.actor.handle(data)
        if row is not None:                               # a decision: count it as a message
            w.registry.beat("act")
            w.registry.note("act", f"{row['decision']}")
        elif data.get("source") in ("store", "store_batch"):
            w.registry.beat("act")

    return {"check": on_check, "decide": on_decide, "act": on_act}


def install_act(agent, w: Deps) -> None:
    """ACT: send queued rows to Supabase, say what was saved."""
    from uagents import Context

    async def flush_store(ctx, st, label: str) -> None:
        if not st.configured:
            return
        sent = await asyncio.get_running_loop().run_in_executor(None, st.flush)
        if sent:
            saved = sum(s.sent_total for s in w.stores.values())
            w.registry.beat("db", note=f"{saved} saved")      # the running total shows on the OG page
            ctx.logger.info(f"sent {sent} {label} row(s) to Supabase")
        elif st.last_error:
            w.registry.note("db", "send failed")
            ctx.logger.warning(f"Supabase send failed ({label}): {st.last_error}")

    @agent.on_interval(period=5.0)
    async def _flush(ctx: Context):
        for label, key in (("round", "rounds"), ("hand", "hand_readings"), ("face", "face_readings")):
            await flush_store(ctx, w.stores[key], label)
        if not w.stores["rounds"].configured:
            w.registry.note("db", "not configured")
        elif not any(s.last_error for s in w.stores.values()):
            w.registry.alive("db")                            # configured and nothing failing: it is up

    @agent.on_interval(period=10.0)
    async def _report(ctx: Context):
        text = w.actor.report()
        if text:
            w.say("act", text, "ok")


def extra_senders(stage: str) -> set:
    """Addresses this stage accepts data from IN ADDITION to the stage before it, from
    ORCA_ALLOWED_SENDERS_<STAGE> in .env (comma separated), for example ORCA_ALLOWED_SENDERS_CHECK."""
    raw = os.environ.get(f"ORCA_ALLOWED_SENDERS_{stage.upper()}", "")
    return {a.strip() for a in raw.split(",") if a.strip()}


def install_chat(agent, w: Deps, stage: str, data_handler, mailbox: bool) -> None:
    """One chat handler per agent: data from the stage before it, or else a question."""
    from uagents import Context, Protocol
    from uagents_core.contrib.protocols.chat import chat_protocol_spec
    ChatAcknowledgement, ChatMessage, EndSessionContent, TextContent = _chat()
    allowed = w.upstream(stage) | extra_senders(stage)

    async def on_chat(ctx: Context, sender: str, msg):
        data = read_json(msg)
        if data is not None and sender in allowed:
            if data_handler is not None:
                await data_handler(ctx, data)
            return
        if data is not None or not mailbox:
            who = ", ".join(UPSTREAM[stage]) or "the games"
            ctx.logger.warning(f"ignored a message from {sender[:20]}...: only {who} may send here")
            return
        # A question (from ASI:One, say): acknowledge it, then answer read-only from the step log.
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(),
                                                   acknowledged_msg_id=msg.msg_id))
        answer = explain(text_of(msg), fresh_status(), public=w.public_answers, stage=stage)
        ctx.logger.info(f"answered a question from {sender[:20]}...")
        await ctx.send(sender, ChatMessage(timestamp=datetime.now(), msg_id=uuid4(), content=[
            TextContent(type="text", text=answer), EndSessionContent(type="end-session")]))

    if mailbox:                                              # the chat protocol, so ASI:One can find it
        protocol = Protocol(spec=chat_protocol_spec)
        protocol.on_message(ChatMessage)(on_chat)

        @protocol.on_message(ChatAcknowledgement)
        async def _ack(ctx: Context, sender: str, msg):
            pass                                             # nothing we send needs a receipt

        agent.include(protocol, publish_manifest=True)
    else:
        agent.on_message(ChatMessage)(on_chat)


def install(agent, w: Deps, stage: str, mailbox: bool = False) -> None:
    """Give `agent` the behaviour of one stage."""
    from uagents import Context
    handlers = make_handlers(w)
    if stage == "filter":
        install_filter(agent, w)
    elif stage == "act":
        install_act(agent, w)
    install_chat(agent, w, stage, handlers.get(stage), mailbox)

    @agent.on_interval(period=1.0)
    async def _alive(ctx: Context):
        w.registry.alive(stage)

    if stage == "act" or not w.local:                        # local: one file; mailbox: one per stage
        @agent.on_interval(period=0.5)
        async def _status(ctx: Context):
            w.write_status(stage)
