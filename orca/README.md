# Orca

A rehab-game station on [FreeWili OG](https://freewili.com) devices, with four Fetch.ai agents that
**filter, check, decide and act** on what the sensors report, and show every step on the device screen.

> **Research prototype.** Thresholds are placeholders and are **not clinically validated**. Everything
> in the demo uses a **simulated patient**. Orca makes no medical claims and is not medical advice.

## The idea

At-home rehabilitation gives clinicians very little to go on. One noisy sensor cannot tell a weak hand
from a resting one, and a false alert makes people stop trusting the system. Orca runs games on two
worn OGs (tilt sensors) and puts a chain of agents between the sensors and any conclusion:

| Agent | What it does |
|---|---|
| **Filter** | Drops readings that cannot be real (glitches, no face in view). Compares the two hands, and the face against the person's own calm baseline. |
| **Check** | Fact-checks a possible imbalance four ways: enough data, persists across windows, unusual for *this* person, other signals (face, pain) agree. Gives the evidence for each. |
| **Decide** | Turns the verdict into a difficulty recommendation with a stated rule. A finding that is not fully verified can never make the game harder, and a verified concern eases it. |
| **Act** | Saves each round and the clean readings (local queue, then Supabase) and states the recommendation. |

Verdicts: `not enough data`, `balanced`, `noted, not verified`, `watch`, `concerning (verified)`.

## What you need

- Three FreeWili OGs on USB: left hand, right hand, and the screen (menu, game picture, five buttons).
  Roles are set on the OG screens by pressing the gray button.
- A laptop (Windows tested) with Python 3.12.
- Optional: a webcam (face discomfort and pulse), a Supabase project, an Agentverse account.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install pyserial numpy pillow uagents mediapipe opencv-python
cd orca\host
copy .env.example .env      # then fill in your own values (never commit .env)
```

Settings live in `orca/host/.env` (see `.env.example`), named `ORCA_*`. Notable ones: `ORCA_PARTICIPANT`,
`ORCA_SEED` (gives your agents their identities), `ORCA_WINDOW_S`, `ORCA_SAMPLE_S`, `SUPABASE_URL` and
`SUPABASE_KEY` (an insert-only key). Create the Supabase tables with `orca/host/supabase_schema.sql`.

### OG firmware

```powershell
python tools\fw.py build orca_main
python tools\fw.py flash orca_main
```

Flash one OG at a time, and read [`AGENTS.md`](../AGENTS.md) first: never `fw flash` a display
application by UF2, and the display CPU has no watchdog.

## Run it

From `orca/host`:

```powershell
python -m orca.og_shell          # the menu and games, mirrored to the screen OG
python -m orca.agents_main       # the four agents in one program: private, offline (default)
python -m orca.agent_stage       # the four agents as separate Agentverse agents (simulated data only)
python -m orca.demo_data         # a SIMULATED patient played through the real agents
python -m orca.agent_gateway     # one agent that answers ASI:One questions about the chain
```

`agent_stage` starts Filter, Check, Decide and Act on ports 8101 to 8104, each with its own mailbox.
Connect each in the Agentverse Inspector once (Connect, then Mailbox). The stages hand work to each other
directly on the laptop. Only run one of `agents_main`, `agent_stage` or the gateway at a time per port.

## The simulated patient

`demo_data` plays seven sessions over two weeks (noted x4, watch, concerning, recovered) through the real
agents, so the verdicts shown are produced by the pipeline. It refuses to run unless the participant code
starts with `DEMO`, so it cannot be mixed into a real person's record.

## Layout

| Path | What |
|---|---|
| `host/orca/` | Laptop-side Python: games, OG link and screen, the four agents, simulator, session log. |
| `host/supabase_schema.sql` | Tables: `rounds`, `hand_readings`, `face_readings`. |
| `notebook/` | Design notes, rules, manual test cards. |
| `../apps/orca/` | OG firmware pair. The display half is a terminal driven over USB CDC. |
| `../bsp/`, `../tools/` | The FreeWili OG board-support package this builds on, and its `fw.py` task runner. |

## Credits and licence

Built on the FreeWili OG BSP in this repository (see its licence and `AGENTS.md`). Agents use the
[Fetch.ai uAgents](https://github.com/fetchai/uAgents) framework and Agentverse.
