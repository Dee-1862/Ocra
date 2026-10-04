# Manual test cards

> **Note (2026-10-04):** the games now use a single OG. Cards 10 and 11 describe the earlier two-OG setup and no longer apply. The Catch, Mirror Hand and Beat Saber games were removed on 2026-10-04, and their cards with them.

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
**Expect (pytest):** `185 passed`.
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

## Card 8: Rhythm Flick
**Where:** `wilirehab/host`, `.venv` active. No reflash needed (uses the same `STREAM` as Card 7).
```
python -m pytest tests -q
python -m wilirehab.rhythm_flick
```
**Expect (pytest):** `185 passed`.
**Part A, keyboard and buttons only.** Arrows fall one per beat toward a grey line. Press yellow (key 2) for a left arrow and blue (key 4) for a right arrow as it reaches the line.
**Expect:** a correct press near the line shows HIT and raises Hits; the wrong direction shows WRONG WAY; an arrow that passes unanswered shows MISS. Top-left shows Hits, Misses and Tempo. Get 8 hits in a row: Tempo rises by 5. Miss 3 in a row: it drops by 5. Press gray (Pain now): Tempo drops by 10. The pause, end, pain and summary screens behave as in the catch game.
**Part B, flick the real OG** (close any console first):
```
python -m wilirehab.rhythm_flick --port COM5
```
Hold or strap the OG and flick it left and right as arrows land.
**Fixes:** left and right swapped: add `--invert`. No flicks register: add `--flick-dps 90` (lower is easier). Flicks fire by accident: raise `--flick-dps 220`. A different tilt direction works instead of the sideways one: add `--axis x`. Up and down too: add `--dirs all` (keys u / d work without the OG; `--invert-fwd` swaps them).
**Report:** "Card 8: part A ok / problem; part B ok / which flags I needed".

## Card 9: Data sidebar (any game)
**Where:** `wilirehab/host`, `.venv` active. No reflash needed.
```
python -m pytest tests -q
python -m wilirehab.brick_break
```
**Expect (pytest):** `185 passed`.
**Expect (window):** a third panel on the right (the window is about 1300 px wide) with two tables.
- **Live sensors** (top): one row per data channel with source, channel, latest value and age. Move the OG: `og acc` shows `x_mg= y_mg= z_mg=` changing and an age near 0.0s, and `og tilt` shows the angle. Press a button: `og button` shows the colour, the action and the screen. Rows older than 2 s turn grey. Sensors we plan but do not have yet show as `not connected` (forearm accelerometer, BNO085 IMU, haptic driver, force sensor).
- **Timeline** (bottom): newest row first, each with a time in seconds from when the window opened. Fast sensors (acc, tilt) show about 4 rows a second so you can read them; buttons and game events (catch, miss, pain score) show every time. The **freeze** box stops the scrolling so you can read it.
**Check the timestamps line up:** press a button, then look at its timeline row and at the game's log line under the game; the times should agree to within a fraction of a second.
**The CSV:** close the window, then open `wilirehab/host/sessions/data-<time>.csv`. It has every row at full rate (about 50 acc rows a second), with columns `t_s, source, channel, dev_ms, fields`. `dev_ms` is the OG's own clock for OG rows.
**Without the OG:** `python -m wilirehab.brick_break --no-og` works too. Only keyboard and game rows appear; `og acc` and `og tilt` are simply absent.
**If the window is too wide for your screen:** tell me the resolution.
**Report:** "Card 9: pytest pass/fail; live table ok / problem; timeline ok / problem; CSV ok / problem".

## Card 10: Two OGs, one per hand (assign the roles)
**Where:** `wilirehab/host`, `.venv` active, both OGs plugged in and running the WiliRehab firmware (flash the second one the same way as the first, one at a time: AGENTS.md says only one CPU in BOOTSEL at a time).
```
python -m pytest tests -q
python -m wilirehab.devices
```
**Expect (pytest):** `185 passed`.
**Expect (devices):** `OG display CPUs found: 2` and a line per OG with its port and USB serial. (If you see 1, the second OG is not enumerating: paste `python -m serial.tools.list_ports -v`.)
Then assign them:
```
python -m wilirehab.devices --setup
```
It says "Press any button on the left hand OG now...". Press a button on the OG you want as the left hand, then on the other when asked for the right hand.
**Expect:** `-> left_hand = serial ...`, `-> right_hand = serial ...`, `Saved devices.json`, and the final list showing a COM port for each role. Run `python -m wilirehab.devices` again after unplugging and re-plugging both: the roles should follow the OGs even if the COM numbers changed.
**If a role says "No press seen":** the OG is not printing button lines (not running the WiliRehab firmware), or another program holds its port.
**Report:** "Card 10: found N OGs; setup ok / problem; roles still correct after re-plug yes / no".

## Card 11: Rhythm Flick with two hands
**Where:** `wilirehab/host`. No reflash.
```
python -m wilirehab.rhythm_flick --devices devices.json
```
**Expect:** two lanes, LEFT and RIGHT. Arrows fall in a lane with a small L or R on the block. Flick the matching hand's OG sideways as the arrow reaches the line: HIT. Flick the wrong hand's OG: `WRONG HAND` (no penalty). The data panel's **hand** column shows L and R on the rows, and the live table has an `og acc` and `og tilt` row for each hand.
**Fixes:** a hand's left and right are swapped: `--invert-roles left_hand` (or `right_hand`, or both comma separated). Nothing registers: `--flick-dps 90`. Fires by accident: `--flick-dps 220`. Without OGs the buttons and keys 2 / 4 flick for either hand.
Finish a round (red, then green on "End session?", pain, confirm). **Expect on the summary:** a small table with Range, Peak deg/s and Hit rate for L and R, a ratio, and which side is weaker.
**Report:** "Card 11: lanes ok / problem; hand tagging ok / problem; symmetry table ok / problem; flags needed".

## Card 13: Dial
**Where:** `wilirehab/host`. Rest the forearm flat (a towel roll), OG on the back of the hand or forearm, screen up.
```
python -m wilirehab.dial_game --port COM5
```
(or `--devices devices.json --driver left_hand`). Press **z** first for neutral.
**Expect:** a semicircle dial. A yellow marker and band show the target; the green needle follows the OG's roll. Hold the needle inside the band for 1.5 s to score (a bar fills while you hold). After each success the band gets 1 degree narrower; a target not reached in 15 s widens it by 2.
**Fixes:** needle moves the wrong way: `--invert-roles right_hand`. No movement but another tilt moves it: `--axis x`. Range too large or small: `--dial-range 30`.
**Report:** "Card 13: needle ok / problem; holding and scoring ok / problem; flags needed".

## Card 14: Launcher and the new games (no reflash needed)
**Where:** `wilirehab/host`, `.venv` active, numpy installed (`pip install numpy`; it is probably there already).
```
python -m pytest tests -q
python -m wilirehab.launcher
```
**Expect (pytest):** `185 passed`.
**Expect (launcher):** a window listing five games, each with a Start button, a one-line description and the movement it uses, plus the connected OGs and their roles. Only one program can hold an OG's serial port, so **start one game at a time** and close it before opening another that uses the OGs.
The options box adds command-line options for the next game, for example `--invert-roles left_hand`.
**Report:** "Card 14: pytest pass/fail; launcher opens ok / problem; device list correct yes / no".

## Card 15: Brick Break (fixed after your recorded session)
**What your session showed:** the steering pitch only went one way from the starting pose (0 down to about -18 degrees, never above 0), so the paddle could only reach the left half of the field. 8 drops against 13 bricks in 27 seconds. Two changes: the game now **learns your tilt range as you play** and stretches it over the whole field, and the ball **waits on the paddle for 0.8 s** before every serve.
```
cd wilirehab/host
python -m pytest tests -q
python -m wilirehab.brick_break
```
**Expect (pytest):** `185 passed`.
**Expect (game):** a wall of bricks, a ball and a paddle. The ball sits on the paddle for a moment before each serve, then launches. Tilt the OG **sideways**, however far you can manage, even only one way from where you started: the paddle should reach **both** edges of the field, and the top line shows `Range NN deg`, the span it has learned. A small wrist range gives a small span; the paddle still covers the whole field.
Check: (1) move to your two extremes; the paddle should be at the left edge at one and the right edge at the other; (2) hold still for several seconds; the paddle should not creep; (3) press **z** to learn the range again from where you are.
**Direction:** the game now steers by sideways tilt (roll). It first steered by forward/back tilt (pitch); your recording showed you tilt mostly sideways (roll moved 2.7 times as much as pitch) and pitch then moved against you about a third of the time, which is what "sometimes the wrong direction" was. If the paddle goes the wrong way every time, add `--invert-roles right_hand`; to steer by forward/back tilt instead, `--movement pitch`.
**Fixes:** The paddle still jitters: tell me, with how big the movement of the board is at the time. To get the old fixed mapping: `--fixed-range --range-deg 18` (l and r then set your range).
**Report:** "Card 15: paddle reaches both edges yes / no; serve delay ok; drops per minute roughly; range shown N deg".

## Card 16: Steady Hand
```
python -m wilirehab.steady_hand --devices devices.json
```
**Expect:** a crosshair field, a yellow ring and a white cursor. The cursor moves sideways with roll and up/down with pitch. Hold it inside the ring (it turns green and a bar fills for 2 s); a new ring appears. The top line shows Roll, Pitch and, after a few seconds of play, `Tremor N mg`. The ring narrows after each success.
**Without an OG:** keys 2 / 4 nudge roll, keys u / d nudge pitch.
**Fixes:** cursor moves the wrong way up/down: `--invert-fwd-roles right_hand`; sideways: `--invert-roles right_hand`.
**Report:** "Card 16: both axes move the cursor yes / no; tremor value appears yes / no".

## Card 17: Colour Reflex
```
python -m wilirehab.color_reflex --devices devices.json
```
**Expect:** five coloured circles, dim, then one lights up with a ring. Press that colour's button on an OG (or key 1 to 5). The reaction time in ms appears; the wrong colour shows WRONG COLOUR; no press in time shows TOO SLOW; pressing before anything lights shows TOO EARLY. The legend at the bottom names the five colours. Key **p** pauses and **e** ends (all five buttons are answers).
After ending (e, then green, then pain), **expect on the summary:** median reaction, correct count, left/right medians (when pressed on different OGs), and the median time buttons were held.
**Report:** "Card 17: prompts and timing ok / problem; left/right medians appear yes / no".

## Card 18: The new summary lines (any game)
After finishing any game session, the summary should now show, below the game's own lines:
- a **trend** line, for example `Success rate trend  steady` or `improving +4.0 %/min`, or `needs a longer session` for sessions under about 30 seconds or with too few points;
- a **tremor** line (`Tremor 4-12 Hz  L 2.1  R 1.8 mg`) once there are a few seconds of OG data;
- with both OGs, the left/right table with **Roll range** and **Pitch range** rows.
The CSV in `sessions/` has `tremor`, `press` and `tilt` rows (with `roll_deg` and `pitch_deg`).
**Report:** "Card 18: trend line ok / problem; tremor line ok / problem; pitch row appears yes / no".

## Card 19: Noise fixes (Brick Break, Rhythm Flick, Steady Hand)
Changed after your recorded sessions showed the problems; compare with how they felt before. No reflash.
```
cd wilirehab/host
python -m pytest tests -q
python -m wilirehab.brick_break --devices devices.json
python -m wilirehab.rhythm_flick --devices devices.json
python -m wilirehab.steady_hand --devices devices.json
```
**Expect (pytest):** `185 passed`.
**Brick Break:** the paddle should look steadier with a still hand and follow a real tilt with about a third of the delay. The default range is now 18 degrees (it was 12) and the paddle is wider, so each degree moves it less. Rolling the OG sideways should no longer drag the paddle (pitch no longer picks up roll).
**Rhythm Flick:** one flick should now give one detection. The detector needs a real 8 degree move, ignores the return stroke, and re-arms only after the hand has been still for a moment. In your recorded session the old detector fired 44 times for 23 arrows; the new one fires 14 times, and from about 17 s on they land within about 0.1 s of each arrow's result. **Because of that, a flick must now be a clear, quick move and a pause before the next one.** If real flicks are missed: `--flick-dps 100`.
**Steady Hand:** the cursor is steadier and less delayed. It still moves because the OG rotates, which is what it measures: a hand movement that does not tilt the OG is invisible to it.
**Report:** "Card 19: brick steadier yes / no; rhythm one detection per flick yes / no; steady hand better yes / no; real flicks missed yes / no".

## Card 20: Wire the BMM350 magnetometer to the OG and see it on the bus
This proves the wiring and that the sensor starts. The main-CPU app scans the bus until it finds the BMM350, starts it (register values from Bosch's own driver) and then streams its raw readings. The OG's accelerometer is on the other CPU, so no heading is calculated; Card 21 compares the two sensors.
**Wiring (OG powered off: unplug USB first).** Connect these four, using the silkscreen labels on both boards:

| BMM350 board | OG side | Use |
|---|---|---|
| 3V3 | 3.3 V (OG header pin 6) | **never the 5 V pin** |
| GND | GND (header pin 19 or 20) | connect this one first |
| SDA | SDA0 / GPIO16 (header pin 10) | |
| SCL | SCL0 / GPIO17 (header pin 8) | |

**On the Maestro, read from your close-up photos:** SDA is the pin labelled `GPIO 16 - SDA0`, SCL is `GPIO 17 - SCL0`, 3V3 goes to any pin in the group of three labelled `3.3V`, and GND to any pin in the group labelled `GND`. Before powering up, check that the small **VIO Select** jumper (next to the printed `3.3V` / `5V`) sits on the **3.3V** side. If the labelled SDA0/SCL0 pins turn out to be bare pin tips rather than a plastic header, do not push jumper ends onto them: use the Qwiic socket with a Qwiic cable instead.
Leave INT and the NC pins unconnected. On the Maestro the same signals are labelled `SDA0 (IO16)` and `SCL0 (IO17)`, with a 3.3 V and a GND pin nearby; use the Maestro's labels rather than counting header pins.
**Which jumpers.** From your photo the magnetometer has male pins, so at that end use a **female** jumper end. At the OG/Maestro end, use a **female** end if that pin is a male pin, or a **male** end if it is a socket. So female-to-female jumpers join two boards that both have pins, and male-to-female ones join a pin to a socket. The Jambu's blue screw terminals take bare wire, not jumper ends, and its I2C is not on them: it is on the small white Qwiic socket at the top left (labelled QWIIC), which needs a Qwiic cable, not jumpers. So use the Maestro's labelled pins instead. Keep the wires short and double-check each against the labels before plugging USB back in.
**Build and flash the main app** (from the repo root; flash the `_main` target only):
```
python tools/fw.py build wilirehab_main
python tools/fw.py flash wilirehab_main
```
Wait until the OG screen shows `WiliRehab`, then open the **main CPU's** port (product ID 2054, it was COM4; re-list ports first if unsure):
```
python tools/fw.py console --port COM4
```
**Expect:** first, every two seconds, `[wilirehab_main] I2C0 devices (1): 0x14` (Bosch's driver gives 0x14 or 0x15 as the chip's two addresses), then `[wilirehab_main] BMM350 running at 0x14, 50 Hz`, then 50 lines a second like `MAG 120 6040 812 -1530 2204 50321 1` (sequence, milliseconds, raw X, Y, Z, raw temperature, data-ready flag). Turn the board: the three numbers change. With nothing wired: `I2C0 devices (0): none` forever. If it prints `answered, chip id 0x.. (want 0x33)`, paste that line.
**If it says none with the sensor wired:** re-check SDA and SCL are not swapped, that 3V3 is on the 3.3 V pin, and that each jumper is seated. Paste the lines you see.
**Report:** "Card 20: found N device(s), address 0x...".

## Card 21: Magnetometer vs accelerometer tester
**First, with no hardware at all:**
```
cd wilirehab/host
python -m pytest tests -q
python -m wilirehab.mag_accel_tester --simulate
```
**Expect (pytest):** `185 passed`. **Expect (simulate):** a table of five actions (still, spin, tilt, shake, magnet) with `ok yes` on every row. Read it as the pattern a working pair should show: spinning flat moves only the magnetometer; shaking moves only the accelerometer; tilting moves both; a magnet changes the field *strength* while gravity stays put. It says SIMULATED at the top; it is not your sensors.
**Then with the real sensors (Card 20 working, MAG lines streaming):** fix the BMM350 board to the OG with tape or a rubber band so they always move together, keep the jumper wires slack, then:
```
python -m wilirehab.mag_accel_tester --og-port COM5 --mag-port COM4 --csv-out mag_test.csv
```
(COM5 is the OG's display CPU, product ID 2055, the accelerometer; COM4 the main CPU, 2054, the magnetometer. Close any console first: only one program can hold a port.) It prints a sanity line first: gravity should be about 1000 mg and the field roughly 25 to 65 uT (uncompensated, so not exact). Then for each action it says what to do, waits for Enter, and measures for a few seconds. Do exactly what it asks:
- **still:** do not touch it.
- **spin:** rotate it flat like a turntable, keeping it level (tilting it makes it look like "tilting").
- **tilt:** tilt forward, back and sideways, without spinning.
- **shake:** shake back and forth, keeping it pointing the same way.
- **magnet:** move a magnet or a steel object near the magnetometer, in and out. Type `s` to skip if you have none.
**Expect:** a table like the simulated one. The "looked like" column should match "expected". Rows that say NO are informative, not failures of the tester: for example a sloppy spin that also tilts will read as "tilting".
**Report:** paste the table and the sanity line.

## Card 23: Sliding vs turning (calibrate the magnetometer, then watch)
Why: an accelerometer alone cannot tell a slide from a tilt. The magnetometer turns only when the board turns, but its large fixed offset hides that until it is measured and removed.
**Step 1, calibrate once** (BMM350 streaming as in Card 20; close any console first). Keep the board away from the laptop, metal and magnets:
```
cd wilirehab/host
python -m pytest tests -q
python -m wilirehab.mag_accel_tester --calibrate --mag-port COM4
```
**Expect (pytest):** `185 passed`. When it says GO, turn the board slowly through **every** orientation for 25 seconds: flip it over, spin it, point each edge up and down. **Expect:** an offset line, then `Field strength after removing it: NN uT`, which should land roughly between 25 and 65 (Earth's field), and a small fit error. It saves `mag_offset.json`. If the strength is far outside that, or it says the fit is poor, repeat somewhere clearer and cover more directions.
**Step 2, watch.** Tape the BMM350 board to the OG so they move together, then:
```
python -m wilirehab.mag_accel_tester --watch --og-port COM5 --mag-port COM4
```
It prints one line a second: how much the accelerometer moved **along gravity** (up/down) and **across it** (sideways), how far the field direction **turned**, and a phrase. Try, about 10 seconds each:
- **slide it up and down:** expect `sliding up/down`. If the board also turns a little, as a hand moving up and down usually makes it, the line says `sliding up/down while turning`: the movement along gravity only comes from a real vertical slide, so it is no longer hidden by the turn;
- **slide it sideways** with quick pushes: expect `sliding sideways`;
- **turn or tilt it:** expect `turning / tilting` and a field turn of 8 degrees or more. The sideways accelerometer movement caused by the turn itself is subtracted, so a pure tilt is not called a sideways slide.
**A fair test needs the right movements.** Moving a hand-held board almost always turns it, which is why a first uncalibrated run called nearly everything a turn. For a clean comparison:
- **up/down:** set the taped boards flat on a thick book and lift the book straight up and down, keeping it level (little turning);
- **sideways:** slide the boards across a smooth table with quick short pushes (no turning);
- **turning:** rotate them in your hand in place.
Each line also shows `turn explains ~N mg`: how much of the sideways movement the turning alone accounts for. Whatever is left over beyond that, and beyond half of it (the estimate is rough), is called a slide. A pure turn gives about 25 mg of sideways movement per microtesla of field change; a slide gives much less field change for the same movement.
**Limits you should expect to see:** a slow, smooth slide at steady speed is only felt as it starts and stops, so it can look still; quick short pushes show up better. Moving a hand up and down usually tilts it a little as well, so you may see `turning / tilting` when you meant a slide; keep the board level to test a pure slide. Metal or a magnet nearby also turns the field reading.
**Report:** paste about 30 lines, and say which line is which movement.

## Card 24: PSPI, HRV and heart-rate maths (no camera, no model)
**Where:** VS Code terminal, `.venv` active, from the host folder. Needs `numpy` and `pytest` in that environment.
```
cd wilirehab/host
python -m pytest tests/test_pspi.py tests/test_face_strain.py tests/test_hrv.py tests/test_rppg.py -q
```
**Expect:** `34 passed`. No download, no webcam, no weight file. These use made-up faces and pulses with known answers, so they prove the arithmetic, not that it works on a real face.
**If it fails:** paste the first `FAILED` block. `No module named numpy` means the venv is missing numpy (`python -m pip install numpy`). `No module named wilirehab` means the shell is not in `wilirehab/host`.
**Report:** "Card 24: pass" or the first failure line.

## Card 25: The OG as the screen (menu, games, face view, dark/light, brightness, sound)
**Camera needs OpenCV** (for the Face view and the Face page): with the venv active, `python -m pip install opencv-python`. If it is missing, the screen says so instead of showing a picture.

**Needs a rebuild and reflash** (the OG gained `BRIGHT` and `BEEP`, and the red-hold light changed). Do this first, with only the OG plugged in:
```
fw build wilirehab_main
fw flash wilirehab_main
```
**Expect:** the build ends without errors, the flash copies, and the OG shows "WiliRehab / waiting for host". **If the build fails:** paste the first `error:` line. Close every other program that has the OG port open (launcher games, the demo, a serial terminal) before step C: only one program can hold it.

**Red button (do this once after flashing):**
1. Tap red quickly several times: **no LED should light**.
2. Hold red: nothing for about half a second, then the red bar starts filling. Let go before 6 s: the LEDs go back to how they were.
3. Hold red for the full 6 s with USB unplugged: the OG powers off (this is the original power-off test, still required).
**Report:** which of 1-3 behaved differently.

**A. Host tests first (no board):**
```
cd wilirehab/host
python -m pytest tests/test_og_shell_parts.py tests/test_og_display.py tests/test_og_screen.py -q
```
**Expect:** all pass. **If it fails:** paste the first `FAILED` block.

**B. Laptop only (no OG):**
```
python -m wilirehab.og_shell --no-og
```
**Expect:** a window showing the menu. Press `2` or Down arrow: the highlight moves. Press `4`: it flips light/dark. Press `3` on a game: the game opens in its own window; the shell window keeps showing what the OG would show.

**C. With the OG:**
```
python -m wilirehab.og_shell
```
(or `--port COM11` with the display CPU's port.)
1. **Menu:** the OG shows the game list in the same style as the laptop. Red = down, gray = up, green = open. Blue switches dark/light. Yellow opens Settings, then yellow goes back.
2. **Game:** green on Brick Break. The OG should show the game; tilt the OG and the paddle moves on both screens. Note the frame rate you see (smooth, choppy, about N frames a second).
3. **In-game buttons (all on the OG, no laptop keys):** while a game plays, gray = Face, yellow = Hand, green = Pause, blue = Pain now (logs "this hurts"), red = End.
   - **Hand:** a full-size page of 8 numbers (roll, pitch, ranges, peak speed, tremor, jerk, range of motion). The game pauses while it shows. Press yellow again or green to close it.
   - **Face:** the live camera picture (mirrored, nothing saved). If you started with "Face numbers in games" on, the camera belongs to the face monitor, so you get pain-expression and heart-rate numbers instead of video.
   - Paused: green = Resume, blue = Re-zero (current pose becomes neutral), red = Restart (fresh round, the old one's numbers are saved).
   Check that the circles are small and the text on the pages is easy to read on the OG.
   **Leaving:** red (End) then green (End now), pain check-in, then the summary: green = Restart, red = Menu (back to the OG menu).
4. **Face view:** open "Face view" (last row). Your face should appear, mirrored. Yellow goes back and the camera light goes off.
5. **Light theme in a game:** press blue on the menu to go light, then start a game. The OG shows a light version of the game. It is an approximation (inverted brightness), so say if it looks wrong.
6. **Close** the shell window: the OG shows "WiliRehab closed on the laptop".
7. **Brightness:** Settings (yellow), down to Brightness, green. It steps 25, 50, 75, 100 % and the backlight should visibly change. The OG never goes fully dark.
8. **Sound:** down to Sound, green. It steps off, low, medium, high, with a sample beep each time (silent on off). Then every button press in the menu ticks. If there is never any sound at any level, say so: the boot line `[wilirehab_display] ... audio=ok` can be read from a serial terminal on the OG's port before the shell starts.
9. **Saved:** close the shell and start it again. Theme, brightness and sound should come back as you left them (they are kept in `wilirehab/host/og_settings.json`).
10. **A game opens on top:** pressing green on a game should bring up the game window at the top left of the main monitor, in front of VS Code, and the OG should show the game, not your editor.

**Expect problems and what they mean:**
- OG stays on "waiting for host": the shell did not connect. Read the status line in the shell window (port busy means another program has it).
- Game mirror shows the wrong picture or black: the game window is covered, minimised or on a second monitor. Keep it on the main monitor, uncovered.
- OG buttons do nothing in a tilt game while it plays: intended, they are switched off during play and back on at the end screens (Colour Reflex uses them all the time).

**Report:** paste the status line, the frame rate you saw for Brick Break, and anything from 1-6 that did not match.

## Card 26: Agents (Fetch.ai uAgents) on the laptop, the OG's Agents page, Supabase
**What it is:** three uAgents (hand, face, orchestrator) run in one program on the laptop. The games hand them numbers; the orchestrator turns each finished round into a row, applies the rule table (adapt.py) for a difficulty *recommendation* (logged and shown, not yet applied to the games), and saves rows locally and to Supabase. The OG's new **Agents** page shows the levels and links live. The OG is not an agent: the "hand agent" is software on the laptop.

**A. One-time setup (you do this)**
1. In the venv: `python -m pip install uagents`
2. Supabase: create a project (supabase.com, free tier is fine). Open **SQL Editor**, paste all of `wilirehab/host/supabase_schema.sql`, run it. Expect "Success. No rows returned".
3. Supabase **Project Settings -> API**: copy the **Project URL** and the **anon public** key. Do **not** use the service_role key.
4. Copy `wilirehab/host/.env.example` to `wilirehab/host/.env` and fill in: `SUPABASE_URL`, `SUPABASE_KEY` (the anon key), `WILIREHAB_PARTICIPANT` (a code like P001, not a name), `WILIREHAB_SEED` (any long random phrase). Nothing else is needed: no ASI:One key, no Agentverse mailbox.
   Leave the two Supabase lines empty to try everything first without a database.

**B. Host tests (no network)**
```
cd wilirehab/host
python -m pytest tests/test_agent_parts.py tests/test_og_shell_parts.py -q
```
**Expect:** all pass. **If it fails:** paste the first `FAILED` block.

**C. Run it (three terminals, from `wilirehab/host`, venv active)**
1. `python -m wilirehab.agents_main`
   **Expect:** three lines "Orchestrator agent1...", "Hand agent agent1...", "Face agent agent1...", then "Supabase: configured" (or "not configured"). Warnings about registering with the Almanac are fine without internet. **If it stops with an error,** paste it: this is the first run against a real uAgents install.
2. `python -m wilirehab.og_shell` -> OG menu -> down to **Agents** -> green.
   **Expect:** four rows of boxes (Devices / Sensing / Policy / Storage). Before you play: Orchestrator may show idle, others "no data", Supabase "sent n" or "not configured". The hint line says "No finished round yet".
3. Play a game from the menu (green), then watch the agent terminal. While you play, `OG hand` and `Hand agent` should go green with a message rate. End the game: **End** (red), **End now** (green), set the pain with the -2 -1 OK +1 +2 buttons, **OK**.
   **Expect in the agents terminal:** a line `round: brick_break hit_rate=... -> push/hold/ease (...)`. Back on the OG Agents page the hint shows `Policy: <action> (<reason>)`.
4. In Supabase: **Table Editor -> rounds**. **Expect** one new row per finished round, within about 5 seconds.
**If rows do not arrive:** the agents terminal prints `Supabase send failed: ...`. The rows stay queued in `agents_queue.jsonl` and are sent later; paste the message. A 401 or 403 means the wrong key or the SQL policy was not run.

**D. Optional: show a gateway agent in your Agentverse (mailbox)**
Only do this if you are happy for one agent to be registered with Fetch.ai's Agentverse. The first attempt put a mailbox on the orchestrator inside the Bureau, and Agentverse's Inspector answered "Could not find this Agent on your local host": it expects a standalone agent on its own port. So there is now a separate **gateway agent** (`agent_gateway.py`, port 8001). It only receives messages from outside agents you allow and hands them to the local program. The games' hand and face numbers never go through it.
1. Sign up at agentverse.ai.
2. Keep `python -m wilirehab.agents_main` running. In a second terminal (same folder, venv active): `python -m wilirehab.agent_gateway`.
3. **Expect** `Gateway agent1q...`, an `Allowed senders:` line (it says "none yet" until you fill in `WILIREHAB_ALLOWED_SENDERS`), uAgents' own `Agent inspector available at ...` line, and my `https://agentverse.ai/inspect/...` link. Open the link while it runs, click **Connect**, choose **Mailbox**, follow the steps.
4. **Expect** the terminal to say it registered as a mailbox agent, and `wilirehab_gateway` to appear in your Agentverse agents.
5. To let the Pi in later: put the Pi agent's `agent1q...` address in `WILIREHAB_ALLOWED_SENDERS` in `.env`, restart the gateway. A message it accepts is logged as `passed a 'round' message from ...`.
**If it fails:** paste the terminal output from the gateway.

**E. Send a message in through the gateway (the Pi's job, rehearsed on the laptop)**
1. Gateway and `agents_main` running. In a third terminal: `python -m wilirehab.agent_test_client agent1q...` (the gateway's address from its `Gateway ...` line).
2. **Expect:** the client logs `my address (add it to WILIREHAB_ALLOWED_SENDERS): agent1q...`. Copy that address into `WILIREHAB_ALLOWED_SENDERS=` in `.env`, stop and restart **only the gateway**, then run the client again.
3. **Expect, in order:** client `sent one test round...`; gateway `passed a 'round' message from agent1q...`; client `the gateway acknowledged...`; `agents_main` terminal `round: gateway_test hit_rate=0.8 -> ...`. In Supabase a `rounds` row with game `gateway_test` (delete it after).
**If the gateway says `ignored a message from ... not in WILIREHAB_ALLOWED_SENDERS`:** the address was not saved or the gateway was not restarted. **If nothing arrives at all:** paste the client and gateway output.

**F. One table per agent, and picking the data up**
Three tables now: `rounds` (orchestrator), `hand_readings` (hand agent), `face_readings` (face agent). The hand and face agents save one snapshot every `WILIREHAB_SAMPLE_S` seconds (default 5). The face table holds webcam-derived numbers: only with the person's informed consent.
1. **Create the two new tables:** in Supabase SQL Editor, paste the whole of `supabase_schema.sql` again and run it (every statement is safe to repeat). **Expect** `hand_readings` and `face_readings` in Table Editor.
2. Restart `python -m wilirehab.agents_main`. **Expect** the `Supabase:` line to name the three tables and the snapshot interval.
3. Play a game from the OG menu for about 30 seconds. **Expect** `sent N hand row(s) to Supabase` in the agents terminal every 5 seconds or so (and `face` rows if the webcam is on), and new rows in `hand_readings` with `jerk_peak`, `rom` and the full reading in `data`.
4. **Picking up (a trusted machine only):** in Supabase, **Project Settings, API, service_role key**. Put it in `SUPABASE_SERVICE_KEY` in the `.env` of the trusted machine (the Pi), never on the laptop that plays, never in git. Then `python -m wilirehab.supabase_pull hand_readings 5`. **Expect** the 5 newest rows printed.
**If a table's send fails:** the warning names the table (`Supabase send failed (hand): ...`) and its rows stay queued locally.

**Report:** paste the three address lines, one `round:` line, what the Agents page showed (a photo is fine), and whether a row appeared in Supabase.

## Results log
| Date | Card | Result | Notes |
|---|---|---|---|
| | | | |
