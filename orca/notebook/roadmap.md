# Roadmap, steps and branches

Supersedes the phase list in `../README.md`. Docs only so far: no step below is started. Date every status change (YYYY-MM-DD).

## How the work is split

```
main
 |-- Step 0  shared contract (both branches need it)
 |
 |-- feat/og-addons      Steps 1, 2, 5        firmware + OG sensors
 |-- feat/vision-face    Steps 3, 4           laptop camera, heart rate, strain
 |
 '-- Step 6  merge: fusion + games + OG UI    (back on main)
```

The two branches share nothing except the **Step 0 contract** (message formats and the numbers-only log schema). That is what lets them run in parallel and merge cleanly. If the contract changes, change it on `main` first and rebase both.

Why this split: the OG branch needs a board and a C toolchain (this laptop has neither gcc nor the Pico SDK). The vision branch needs only Python and a webcam. So the vision branch is not blocked by firmware, and the other way round.

## Step 0: Shared contract (on main, before branching)

**Do:** write down the host<->OG line protocol and a `Frame` record (timestamp, wrist angle, source = camera / OG / fused, quality) and the session-log fields.
**Deliverables:** `notebook/11-contract.md`; the protocol header already drafted in `apps/orca/display/rehab_proto.h`.
**Works when:** both branches can read the same doc and nothing else.
**Not yet verified:** the protocol is drafted, not run.

## Branch A: `feat/og-addons`

### Step 1: A small runnable thing on the OG
**Do:** build `orca_main` (carries the display image), flash it, and use the OG as a screen and button pad driven from a serial terminal.
**Order matters (AGENTS.md):** first observe the **6 s red-hold power-off** on the real board. Only then trust anything else.
**Deliverables:**
- Firmware pair in `apps/orca/` building clean.
- `PING`, `TXT`, `BAR`, `MODE` working; button edges echoed back.
- C parser test (`tests/test_rehab_proto.c`) passing via `fw test`.
- A short lab entry: what was observed, board, date.
**Works when:** you type `TXT 1 hello` in `fw console` and it appears on the OG, and pressing green prints `BTN green down`.
**Needs:** a C compiler and Pico SDK on some machine. Do not `fw flash` the display app directly; flash the main app.

### Step 2: Track hand changes with the OG itself
**Do:** the display CPU already has an accelerometer (LIS3DH, `bsp/display_cpu/sensors/lis3dh.h`). Strap or hold the OG on the back of the hand or forearm and stream tilt.
**Honest limits:** the LIS3DH is accelerometer-only, so it gives pitch/roll from gravity (wrist flexion/extension, forearm rotation) but **no yaw and it drifts under fast motion**. That is enough for a first angle signal and for tremor, not for full orientation.
**Deliverables:**
- OG streams timestamped acceleration lines to the laptop.
- Host converts to a tilt angle and a simple tremor measure.
- Test 1 (goniometer table) run with "OG only" column.
**Works when:** moving the wrist through 0 / 20 / 40 degrees changes the streamed angle by a plausible amount, compared against a goniometer.

### Step 5: OG add-ons, only if Step 2 falls short
**Do:** BNO085 IMU pods on the Maestro Qwiic port (main CPU), forwarded to the laptop. Optional: FSR squeeze, ESP32 table station.
**Deliverables:** main-CPU reader that **kicks the watchdog every loop**; pod data in the same `Frame` record; Test 2 ablation data.
**Gate:** only start if Step 2's error is too large or the camera loses the hand too often. Buying and wiring parts is a decision, not a default.

## Branch B: `feat/vision-face`

### Step 3: Laptop camera tracks the hand
**Do:** webcam to MediaPipe Hands (and Pose for trunk) to wrist angle and compensation flags.
**Deliverables:**
- Live wrist angle on screen, with a quality score.
- Range of motion, smoothness (SPARC), compensation detection.
- Test 1 "webcam only" column; Test 3 scripted compensation trials.
**Works when:** angle roughly tracks a goniometer for 0 / 20 / 40 degrees, and elbow cheats and trunk leans are flagged in the scripted trials.
**Needs:** `mediapipe` installed (it is not on this machine; opencv and numpy are).

### Step 4: Non-invasive face signals
**Do:** heart rate from the face (rPPG, POS algorithm) and a facial strain score, from the same camera.
**Deliverables:**
- Heart rate with a signal-quality flag; Test 4 against a fingertip pulse oximeter.
- Strain score and its known limits written down (motion, lighting, skin tone, class imbalance in the UNBC data).
- Test 5 frame rate and latency with everything running.
**Works when:** resting heart rate is within a few bpm of the oximeter under steady light, and the system reports "low quality" instead of a wrong number when it cannot tell.
**Caution:** this is a research signal, not a medical measurement. Do not show it to a patient as a clinical reading.
**Privacy:** frames are never stored; only numbers go to the session log.

## Step 6: Integration (back on main)

**Do:** merge both branches.
- Fusion: camera angle plus OG angle, with dropout handling.
- Adaptation: difficulty from range of motion, smoothness, heart rate, strain, pain report.
- Games: wrist-path game first; OG screen shows target angle, rep counter, pain check-in (button mapping per AGENTS.md).
**Deliverables:** one full patient session as drawn in the user flow diagram; Test 2 ablation (camera only / OG only / fused).
**Works when:** you can sit down, calibrate in about a minute, play a round, give a pain score on the OG, and get a numbers-only summary.

## Step 7: Evaluation and paper

**Do:** run Tests 1 to 5 on the author only (simulated impairments), then draft.
**Deliverables:** filled evaluation tables; plots; draft. Every number in the paper comes from those tables.
**Gate:** every cited paper has been opened and read in full.

## Summary table

| Step | Branch | Needs hardware | Needs C toolchain | Blocked by |
|---|---|---|---|---|
| 0 contract | main | no | no | nothing |
| 1 OG screen and buttons | feat/og-addons | OG | yes | Step 0 |
| 2 OG tracks hand | feat/og-addons | OG + strap | yes | Step 1 |
| 3 camera hand | feat/vision-face | webcam | no | Step 0 |
| 4 face signals | feat/vision-face | webcam, oximeter | no | Step 3 |
| 5 OG add-ons | feat/og-addons | IMU pods | yes | Step 2 result |
| 6 integration | main | all | yes | Steps 2 and 4 |
| 7 evaluation, paper | main | all | no | Step 6 |

## Code already on disk (written before the no-code request)

Uncommitted and never run. It maps onto the steps like this, so it is a head start, not a finished layer:
- `apps/orca/` firmware and `tests/test_rehab_proto.c`: Step 1.
- `host/orca/metrics.py`, `fusion.py`: Steps 2, 3, 6.
- `rppg.py`: Step 4. `adapt.py`, `games.py`: Step 6. `session.py`: all steps.

Decision needed: keep it and review it step by step, or delete it and rewrite each piece when its step starts.

## Changelog
| Date | Change |
|---|---|
| 2026-10-03 | Page created. No step started. |
