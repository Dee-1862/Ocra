# OG button map and motion data

Design only. Nothing here is implemented or tested. Facts from the BSP source are marked (BSP); everything else is a proposal.

## 1. Constraints on the buttons (BSP)
- Five buttons: gray, yellow, green, blue, red. The driver gives debounced `down`, `pressed` (edge) and `released` (edge) per button (5 ms debounce).
- **Red held 6 s powers the board off.** Keep red short-press only. Never design anything that needs a long red hold.
- **Gray held while the board is off wakes it** (hardware). Avoid long gray holds as a game input.
- Long-press and double-click are not in the driver; the app measures them.
- The BSP's recommended arrow-pad layout when porting FreeWili 2 apps: green = select/OK, yellow = left, blue = right, gray = up, red = down. Reuse it so the OG feels the same as other OG apps.

## 2. Proposed map: one meaning per colour per screen
The buttons are unlabeled, so **every screen shows a legend row** (text row 7) naming what each colour does right now. Colours keep a fixed *role* across screens; the legend says the details.

| Screen | Gray | Yellow | Green | Blue | Red |
|---|---|---|---|---|---|
| Hand select | - | Left hand | **Confirm** | Right hand | Back |
| Calibration | Restart | Prev step | **Capture** | Skip | Cancel |
| Gameplay | Pain now | Left | **Pause** | Right | End |
| Paused | - | - | **Resume** | - | End |
| End session? | - | - | **End now** | - | Keep going |
| Pain 0 to 10 | +1 | -1 | **Confirm** | +1 | -1 |
| Summary | Next | Prev | **Done** | Next | Back |

The same table is in code (`host/wilirehab/button_map.py`) and drives the on-screen legend in the mapping demo, so this table and the demo cannot disagree without a test failing.

Why this shape:
- **Green is always "yes / go".** Red is always "back / stop / less". Learnable in one minute.
- Pain entry uses two buttons per direction so a patient with one usable hand side can still reach them.
- **"Pain now" on gray during play** lets the patient report pain without leaving the game; it is logged as an event and eases difficulty.
- No double-clicks or long presses are required anywhere. People with reduced hand function may not manage them, and red cannot be long-pressed anyway.
- Ending a session takes two presses: red (End), then green on the "End session?" screen. No hold.

Handedness is handled by the Hand select screen, not by remapping colours: the colour roles stay the same for everyone.

## 3. How to do the mapping
**Keep the map on the laptop, not in firmware.** The OG display app already reports raw edges and draws whatever the laptop sends:
```
OG -> laptop:   BTN green down        BTN green up
laptop -> OG:   TXT 7 G:ok R:back Y:- B:+
```
- A table `screen -> {colour -> action}` lives in the host code. Changing the map is an edit on the laptop with **no reflash**, which matters because flashing the display CPU is the risky operation.
- The laptop measures press duration from the down/up lines if a long press is ever wanted. USB adds a few ms of jitter, fine for 300 ms or longer thresholds.
- Optional later: echo each press on the WS2812 LED bar in that button's colour (the workshop "button lights" exercise) as instant feedback, done on the OG so it does not wait for the laptop.
- To add timestamps from the OG clock, extend the line to `BTN green down <ms>` (small firmware change).

Alternative if we stay on stock firmware: the OneWili API may expose button events. I have not checked that; see the roadmap decision.

## 4. Tracking changes with the OG's own sensor
**What it is (BSP):** a 3-axis accelerometer (ST LIS3DH) on the display CPU's I2C1, address 0x19. Configured at **100 Hz**, all axes on, **normal mode (10-bit)**. The driver stores raw 16-bit values; the BSP provides `lis3dh_raw_to_mg()` which shifts right by 6 and multiplies by 4 mg per digit at the default ±2 g range.

**What it can tell us**
- Direction of gravity, so **pitch and roll** of whatever the OG is strapped to or held by.
- How much it is moving, how smooth the movement is, and **tremor** (shake in roughly the 4 to 12 Hz band; 100 Hz sampling is plenty).
- Rep counts (peaks in tilt) and "held still" (for calibration).

**What it cannot tell us**
- **No yaw** (rotation about the vertical axis) and **no gyroscope**. It drifts in meaning during fast motion because it cannot separate gravity from acceleration.
- **One sensor gives absolute tilt, not a joint angle.** Wrist flexion is the angle *between* hand and forearm. With only the OG on the hand you get hand tilt versus gravity; the forearm's tilt must come from somewhere else (the camera's pose estimate, or a second IMU on the forearm). This is the strongest reason the camera and OG are fused rather than either alone.
- Range of ±2 g saturates on vigorous shaking; fine for rehab motion.

## 5. What data to collect
Send raw, convert on the laptop, so a conversion bug can never be baked into firmware.

**Per sample, about 50 Hz** (100 Hz is available; start lower and raise if needed):

| Field | Why |
|---|---|
| sequence number | detect dropped lines |
| OG time in ms | order and sync with camera frames |
| raw x, y, z (int16) | host converts to mg |

Proposed line: `ACC <seq> <t_ms> <x> <y> <z>`, with `STREAM <hz>` / `STREAM off` to control it. At 50 Hz this is about 1.5 KB/s, trivial for USB.

**Derived on the laptop**

| Quantity | How | Use |
|---|---|---|
| magnitude, mg | sqrt(x²+y²+z²) | Sanity check: about 1000 mg when still. Far off means motion or a bad read; mark quality low. |
| pitch, roll | from the gravity vector | Hand or forearm tilt |
| angular change | difference of pitch/roll over time | Movement speed |
| smoothness | SPARC on the speed profile | Movement quality |
| tremor power | band power 4 to 12 Hz after removing gravity | Tremor trend |
| still flag | low variance over about 0.5 s | Calibration capture |
| rep count | peaks in pitch or roll | Game scoring |

**Also log (all numbers only):** button events with time, pain reports (0 to 10), stream drop count, and a heartbeat so the laptop knows the OG is alive.

**Timing:** the OG clock and the laptop clock differ. Estimate the offset at start (PING round trip) and re-check periodically. Camera frames arrive every about 33 ms, so a few ms of jitter is acceptable; say so in the limitations.

## 6. Where this plugs into the roadmap
- Roadmap Step 1: buttons and legend rows (needs only what is built).
- Roadmap Step 2: add `STREAM` and `ACC`; run the OG-only column of the wrist-angle test against a goniometer.
- If tilt-only proves too coarse, that is the evidence to buy IMU pods (Step 5).

## 7. Who this is for, and who presses the buttons
**Assumed user: one person with a single upper-limb loss.** They have one intact hand, which can press the OG's buttons, and the OG sits on that side. The **therapist uses the same buttons** (setup, calibration, and as a backup if the patient cannot answer a prompt).

This replaces the earlier idea of extra input routes (dwell, tilt-to-select, voice, external switch). Those are removed from the design. Buttons are the single input route.

What follows from that:
- Every action is a **single short press**. No holds, no double-clicks, no two-button chords.
- Pain is reported with the buttons (section 2), by the patient or by the therapist on their behalf. The log records who entered it.
- The "Hand select" screen asks which hand is intact (yellow = left, blue = right), which sets the mirrored virtual hand and which side the OG is worn on.
- Setup and calibration are done **with** the therapist.
- If a prompt gets no press, the session does not stall; it is logged as "not answered".

Not covered by this assumption: people with reduced movement in both hands. That group is out of scope for now.

## Changelog
| Date | Change |
|---|---|
| 2026-10-03 | Page created. Proposal only. |
| 2026-10-03 | Scope narrowed to one person with a single upper-limb loss; buttons are the only input; alternative routes removed. |
