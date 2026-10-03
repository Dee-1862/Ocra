# WiliRehab

A low-cost rehab station that turns hand, wrist and arm exercises into games, using a laptop webcam, a FREE-WILi OG and a few cheap sensors. Working name; rename anytime.

**Status: early.** Nothing here has been run on hardware, and the C firmware has not been compiled.

## Layout

| Path | What |
|---|---|
| `notebook/` | Roadmap, diagrams, design log and abstract, rules book, manual tests, setup notes, button map. Older pages were merged into the diagrams file. |
| `host/wilirehab/` | Laptop-side Python: metrics, fusion, rPPG, adaptation, game logic, numbers-only session log. |
| `../apps/wilirehab/` | OG firmware pair. The display half is a dumb terminal driven over USB CDC. |

## Phases
0. Notebook as files (this folder's `notebook/`) - done
1. Prove the OG as a screen: observe the 6 s red-hold power-off, then drive it from a serial terminal
2. Laptop core, no camera: OG link, simulator, pytest
3. Webcam sensing (MediaPipe)
4. Games and OG UI
5. IMU pods on the main CPU
6. Evaluation and paper

Read `../AGENTS.md` before touching `apps/wilirehab/`.
