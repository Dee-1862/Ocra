# Manual test cards

You run these; the assistant does not (see rules-book R1). Paste back the "Report" line.

## Card 1: Build the WiliRehab firmware
**Where:** VS Code terminal, repo root `C:\Users\Reddy\wiliOGbsp`, `.venv` active.
```
cmake --preset target -Dpicotool_DIR="C:/Users/Reddy/.pico-sdk/picotool/2.3.0/picotool"
python tools/fw.py build wilirehab_main
```
**Expect:** it finishes with no `FAILED`, and these exist:
```
build/apps/wilirehab/wilirehab_main.uf2
build/apps/wilirehab/wilirehab_display.uf2
```
**If it fails:** copy the first line containing `FAILED` or `error`. A "No CMAKE_C_COMPILER" message means picotool is being built from source: re-run the configure line with the `-Dpicotool_DIR` flag.
**Report:** "Card 1: pass" or the first error line.

## Card 2: Power-off on a 6 s red hold (do this before anything else on hardware)
**Why first:** AGENTS.md. The board's recovery is software; this proves it works.
**Important:** with USB plugged in, the board does **not** go dark. The 6 s hold writes the charger's "battery off" bit (BATFET_DIS), but USB keeps powering the board. The BSP's hardware notes record the board going dark only **when USB is then removed**. So "nothing happened" with the cable in is expected.
**Where:** terminal at the repo root, board plugged in. Use the console so you can see the firmware's own messages.
```
python tools/fw.py build wilirehab_main
python tools/fw.py flash wilirehab_main
python tools/fw.py console --port COM5
```
Then **hold red for 6 seconds** and watch the console.
**Expect:** a red LED bar filling on the OG (needs the `ws2812_init` line, added after the first build, so rebuild and reflash), then these lines:
```
OK ship entering (red held 6000 ms)
[ship] BATFET_DIS: REG09 00 -> 20
```
(the first number may differ). Then **unplug the USB cable**: the OG should go dark.
**To wake it:** hold **gray** for 2 to 3 seconds, or plug USB back in.
**If the console shows `[ship] charger did not answer` or `ERR ship charger-write-failed`:** that is a real failure; paste it. **If it shows nothing at all while red is held:** also paste, with whether the red LED bar appeared.
**If the screen never lights after flashing:** do not flash anything else. Restore stock: FREE-WILi GUI, Setup, FreeWili OG updater, Firmware tab, Update and verify.
**Report:** the console lines you saw, and whether it went dark after unplugging.

## Card 3: Talk to the OG screen
**Where:** a second terminal. The display CPU enumerates as `FWOG display wilirehab 001`.
```
python tools/fw.py console
```
If it asks which port, or finds two, use `python tools/fw.py console --port COMx` with the display one.
Type each line and press Enter:
```
PING
TXT 1 hello
BAR 50
MODE limb
CLS
```
**Expect:** `OK pong`, then `OK` for each of the others. `hello` appears on row 1, a half-width bar appears at the bottom, `CLS` clears the screen.
Then press each of the five buttons.
**Expect:** lines like `BTN green down` and `BTN green up` printed in the console.
Then try bad input: `TXT 9 x` and `FROB`.
**Expect:** `ERR bad-row` and `ERR unknown-command`.
**Report:** paste the console output.

## Card 4: Protocol parser unit test (needs a C compiler)
**Not runnable on this laptop** (no host C compiler). On a machine with one:
```
python tools/fw.py test
```
**Expect:** `test_rehab_proto` passes among the CTest results.
**Report:** "Card 4: pass / fail / skipped (no compiler)".

## Card 5: Button map demo (no board needed)
**Where:** VS Code terminal, `.venv` active, from the host folder.
```
cd wilirehab/host
python -m pytest tests -q
python -m wilirehab.mapping_demo
```
**Expect (pytest):** `25 passed`.
**Expect (demo):** a window with a screen list on the left and an OG-style screen on the right. Along the bottom of that screen are five coloured circles (gray, yellow, green, blue, red), each with a one or two word label. Unused buttons are dashed circles marked "not used".
Check on **every** screen (click a screen name, or Left/Right arrows):
1. The labels match the table in `button-map-and-motion-data.md`.
2. Click each circle, or press keys 1 to 5. A ring in that colour should expand and fade around the circle, the circle flashes white, a banner like `GREEN  Confirm  recorded` appears, and a line is added to the log.
3. Pressing an unused button gives a dim ring and "not used on this screen", and is logged as ignored.
4. On "Pain check-in", gray/blue add 1 and yellow/red subtract 1 (stays between 0 and 10).
**Optional, with the OG flashed and Card 3 working:**
```
python -m wilirehab.mapping_demo --port COM5
```
(use the display CPU's port). **Expect:** pressing a real OG button animates the same ring, and the log shows source `OG`.
**If the window is blank or errors:** paste the traceback. If pytest says `No module named wilirehab`, you are not in `wilirehab/host`.
**Report:** "Card 5: pytest pass/fail; demo ok / what looked wrong".

## Card 6: Catch game, first with the keyboard, then with the OG
**Where:** terminal in `wilirehab/host`, `.venv` active.
```
python -m pytest tests -q
python -m wilirehab.catch_game
```
**Expect (pytest):** `25 passed`.
**Expect (game):** the OG-style screen titled "Gameplay". Yellow stars fall inside a box, a green basket sits at the bottom, a counter shows Caught / Missed / Speed. The legend now reads: gray **Pain now**, yellow **Left**, green **Pause**, blue **Right**, red **End**.
Check, using keys 1 to 5 (2 = Left, 4 = Right):
1. Left and Right move the basket; each press also plays the ring animation.
2. Catching a star raises Caught; letting one hit the floor raises Missed and slows the game a little.
3. Pause (3) shows PAUSED and the legend changes to Resume / End. Resume continues.
4. Red (5) goes to "End session?". Keep going returns to the game; End now goes to the pain screen.
5. Pain screen: +1 / -1 change the number, Confirm goes to the summary showing caught, missed, pain-now presses, pain score, time.
6. Done (3 on the summary) starts a fresh round.
A file `sessions/session-<time>.jsonl` appears in `wilirehab/host`. Open it: every line should be numbers and short words only.
**With the real OG** (close any console first):
```
python -m wilirehab.catch_game --port COM5
```
**Expect:** the OG yellow and blue buttons move the basket; the sidebar says `Listening to the OG on COM5`.
**If the sidebar says `Serial stopped: ...`:** paste that line. **If nothing moves on real presses:** run Card 3 first to confirm the OG prints `BTN ... down`.
**Report:** "Card 6: pytest pass/fail; keyboard ok / problem; OG ok / problem".

## Card 7: Tilt steering (new firmware: rebuild and reflash first)
**Where:** repo root, `.venv` active, USB connected.
```
python tools/fw.py build wilirehab_main
python tools/fw.py flash wilirehab_main
```
Wait until the OG shows `WiliRehab`, then re-list ports and use the `093C:2055` one (see Card 2).
**Part A, raw stream.**
```
python tools/fw.py console --port COM5
```
Type `STREAM 10`.
**Expect:** `OK`, then about ten lines a second like `ACC 3 20450 120 -64 16008`. With the OG flat and screen up, the third number (z) is near 16000 and x, y near 0. Tilt the OG: x or y changes by thousands. Type `STREAM 0`: the lines stop. Close the console.
**If** you get `ERR accel not-initialised`: paste it, the accelerometer did not start.
**Part B, the game steered by tilt.**
```
cd wilirehab/host
python -m pytest tests -q
python -m wilirehab.catch_game --port COM5 --tilt
```
Hold or strap the OG in a comfortable pose, then press **z** in the window to set that as neutral. Tilt left and right.
**Expect:** the basket follows the tilt; the top-left counter shows `Tilt +NN deg`. Leave it still and the basket stays centred. Shake it hard and the counter adds `(shaky)`.
**Set your own range** (a therapist or you): tilt as far **left** as is comfortable and press **l**; tilt as far **right** and press **r**. The status line (left sidebar) confirms the angles. After that the basket should reach each edge at your limits. The start range is 12 degrees each way.
**Steadiness check:** hold the OG still for 10 seconds. The basket should stay put, not drift or twitch. A tilt under about 1.5 degrees is ignored on purpose.
**Fixes:** basket moves the wrong way: add `--invert`. Tilting does nothing but a different tilt direction does: add `--axis x`. Still too twitchy: strap the OG instead of holding it, and tell me. Too sluggish: tell me.
In this mode yellow and blue (Left/Right) do nothing; the other buttons still work.
A `sessions/*.jsonl` file should now contain `tilt` lines with a number and `steady`.
**Report:** "Card 7: part A ok / output; part B ok / which flag needed".

## Results log
| Date | Card | Result | Notes |
|---|---|---|---|
| | | | |
