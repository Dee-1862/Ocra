"""A SIMULATED patient, played through the real agent chain, for demos and videos.

    python -m orca.demo_data [--speed 5] [--only 6] [--gap 4] [--seed 7]

EVERYTHING HERE IS SYNTHETIC. It is made up to tell a story the agents can be shown handling; it is
not a person and it is not evidence of anything. Say "simulated patient" in anything you record. The
rows it causes are saved under the participant code DEMO01, and this program REFUSES to run unless
the agents program is running as a DEMO participant, so it cannot be mixed into a real participant's
data by accident.

How to run it (agents_main must be started with these three settings, in the same terminal first):
    $env:ORCA_PARTICIPANT = "DEMO01"      who the rows belong to
    $env:ORCA_WINDOW_S    = "2"           the 10 s windows shortened so a session plays fast
    $env:ORCA_SAMPLE_S    = "0.5"         save a reading snapshot every half second
    python -m orca.agents_main
then, in another terminal:  python -m orca.demo_data

The story (seven sessions over two weeks, left hand weaker than the right):
    1-4  the usual picture: the left hand reaches about 60% of the right, calm face, low pain. The
         agents note it but cannot verify a concern: nothing unusual for THIS person yet.
    5    a tired day: the left hand drops to about 46% but the face and pain stay calm. The finding
         is unusual for them but nothing else agrees, so the verdict is "watch" and the agents will
         not make the game harder.
    6    a bad day: about 37%, the face shows rising discomfort and pain is 5. All four tests pass:
         "concerning (verified)", and the difficulty is eased.
    7    recovered: about 68%, calm again; nothing unusual and the game may be pushed again.

The generators are pure (seeded random numbers), so the same seed always tells the same story.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time

from .agent_link import AgentIngress, read_status

GAME = "brick_break"
SECONDS = 36                       # simulated seconds per session
ATTEMPTS = 30
GLITCH_P = 0.03                    # share of hand readings that are sensor glitches (to be filtered)
NO_FACE_P = 0.04                   # share of face readings with no face in view

# One row per session: what the simulated patient does that day.
PLAN = (
    {"label": "Day 1",  "left": 22.0, "right": 38.0, "face": "calm",   "pain": 1, "hit": 0.72},
    {"label": "Day 3",  "left": 23.0, "right": 38.0, "face": "calm",   "pain": 1, "hit": 0.75},
    {"label": "Day 5",  "left": 24.0, "right": 39.0, "face": "calm",   "pain": 2, "hit": 0.78},
    {"label": "Day 8",  "left": 24.0, "right": 39.0, "face": "calm",   "pain": 1, "hit": 0.80},
    {"label": "Day 10", "left": 17.5, "right": 38.0, "face": "calm",   "pain": 1, "hit": 0.88},
    {"label": "Day 12", "left": 14.0, "right": 38.0, "face": "rising", "pain": 5, "hit": 0.63},
    {"label": "Day 15", "left": 26.0, "right": 38.0, "face": "calm",   "pain": 2, "hit": 0.83},
)

# What the agents should conclude for each session, in order (checked by the tests).
EXPECTED_VERDICTS = ("noted, not verified", "noted, not verified", "noted, not verified",
                     "noted, not verified", "watch", "concerning (verified)", "noted, not verified")


def hand_reading(rng: random.Random, rom_base: float, t: int) -> dict:
    """One simulated hand reading, shaped like the hand monitor's (jerk_peak, rom, ...)."""
    rom = None if t < 3 else round(rom_base * rng.uniform(0.93, 1.07), 1)   # no range for the first 3 s
    jerk = rng.lognormvariate(math.log(9.0 * (40.0 / rom_base) ** 0.6), 0.3)  # a weaker hand is rougher
    if rng.random() < GLITCH_P:
        jerk = rng.choice([9000.0, -3.0])                                      # a glitch: the filter drops it
    return {"jerk_peak": round(jerk, 1), "jerk_mean": round(jerk * 0.4, 1),
            "roll_rom": rom, "pitch_rom": None if rom is None else round(rom * 0.35, 1), "rom": rom,
            "rom_base": rom_base, "rom_ratio": None if rom is None else round(rng.uniform(0.92, 1.05), 2),
            "roll": round(rng.uniform(-rom_base / 2, rom_base / 2), 1),
            "pitch": round(rng.uniform(-5.0, 5.0), 1)}


def face_reading(rng: random.Random, t: int, level: str) -> dict:
    """One simulated face reading (the first ten seconds are calm: that is the person's baseline)."""
    if rng.random() < NO_FACE_P:
        return {"state": "no_face", "pspi_mean": None, "bpm": None, "q": 0.0}
    rising = level == "rising" and t >= int(SECONDS * 0.4)
    pspi = abs(rng.gauss(2.3 if rising else 0.75, 0.3 if rising else 0.15))
    quality = 0.85 if rng.random() > 0.1 else 0.3                # now and then a poor pulse reading
    return {"state": "ok", "pspi_mean": round(pspi, 2), "bpm": round(rng.gauss(74.0, 2.5), 1),
            "q": quality}


def session(plan: dict, session_id: str, seed: int) -> tuple:
    """(ticks, round message) for one simulated session.

    `ticks` is a list with one entry per simulated second, each a list of messages
    (source, role, data, session): the left hand, the right hand and the face."""
    rng = random.Random(seed)
    ticks, last_face = [], {}
    for t in range(SECONDS):
        last_face = face_reading(rng, t, plan["face"]) or last_face
        ticks.append([
            ("hand", "left_hand", hand_reading(rng, plan["left"], t), session_id),
            ("hand", "right_hand", hand_reading(rng, plan["right"], t), session_id),
            ("face", None, last_face, session_id)])
    hits = round(plan["hit"] * ATTEMPTS)
    final = {"game": GAME, "session_id": session_id, "seconds": float(SECONDS), "hits": hits,
             "attempts": ATTEMPTS, "roll_range_deg": plan["right"], "pitch_range_deg": 12.0,
             "peak_dps": round(rng.uniform(70, 110), 1), "tremor_rms_mg": round(rng.uniform(5, 8), 1),
             "pain_events": 2 if plan["pain"] >= 4 else (1 if plan["pain"] >= 2 else 0),
             "pain_score": plan["pain"],
             "face_pspi": last_face.get("pspi_mean"), "face_bpm": last_face.get("bpm")}
    return ticks, ("round", "right_hand", final, session_id)


def guard(status, force: bool = False):
    """Why the demo must not run right now, or None if it is safe."""
    if status is None:
        return "the agents are not running (start python -m orca.agents_main first)"
    if not force and not str(status.get("participant", "")).upper().startswith("DEMO"):
        return (f"the agents are running as participant {status.get('participant')!r}, not a DEMO "
                "one, so simulated data would be saved into that person's record. Restart "
                "agents_main with $env:ORCA_PARTICIPANT = \"DEMO01\"")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Play a simulated patient through the real agents")
    ap.add_argument("--speed", type=float, default=5.0, help="simulated seconds per real second")
    ap.add_argument("--gap", type=float, default=4.0, help="real seconds to wait between sessions")
    ap.add_argument("--only", type=int, help="play just this session number (1-7)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--force", action="store_true", help="skip the DEMO-participant safety check")
    args = ap.parse_args(argv)

    status = read_status()
    if status is not None and time.time() - status["generated_at"] > 10:
        status = None                                           # a stale file means it is not running
    problem = guard(status, args.force)
    if problem:
        print("Not starting:", problem, file=sys.stderr)
        return 1
    window_s = float(status.get("window_s", 10.0))
    if window_s > 3.0 and args.speed > 1.5:
        print(f"note: the agents' windows are {window_s:g} s. For a fast demo restart agents_main with "
              "$env:ORCA_WINDOW_S = \"2\"; at this speed the sessions will be too short to check.")

    ingress = AgentIngress()
    numbers = [args.only] if args.only else list(range(1, len(PLAN) + 1))
    print("SIMULATED PATIENT (synthetic data, participant", status.get("participant"), ")")
    for n in numbers:
        plan = PLAN[n - 1]
        print(f"\nSession {n}: {plan['label']} (left {plan['left']:g}, right {plan['right']:g}, "
              f"face {plan['face']}, pain {plan['pain']})")
        ticks, final = session(plan, f"demo-{n}", args.seed + n)
        for tick in ticks:
            for source, role, data, sid in tick:
                ingress.publish(source, role, data, session=sid)
            time.sleep(1.0 / args.speed)
        time.sleep(window_s + 0.8)                              # let the last window close and be checked
        source, role, data, sid = final
        ingress.publish(source, role, data, session=sid)
        time.sleep(max(args.gap, 2.0))
    print("\nDone. Look at the OG's Steps page, and Supabase (participant DEMO01).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
