# Manual test cards

> **Note (2026-10-04):** the games now use a single OG. Cards 10 and 11 describe the earlier two-OG setup and no longer apply. The Catch, Mirror Hand and Beat Saber games were removed on 2026-10-04, and their cards with them.

You run these; the assistant does not (see rules-book R1). Paste back the "Report" line.

## Card 1: Build the Orca firmware
**Where:** VS Code terminal, repo root `C:\Users\Reddy\wiliOGbsp`, `.venv` active.
```
cmake --preset target -Dpicotool_DIR="C:/Users/Reddy/.pico-sdk/picotool/2.3.0/picotool"
python tools/fw.py build orca_main
```
**Expect:** it finishes with no `FAILED`, and these exist:
```
build/apps/orca/orca_main.uf2
build/apps/orca/orca_display.uf2
```
**If it fails:** copy the first line containing `FAILED` or `error`. A "No CMAKE_C_COMPILER" message means picotool is being built from source: re-run the configure line with the `-Dpicotool_DIR` flag.
**Report:** "Card 1: pass" or the first error line.

## Card 2: Power-off on a 6 s red hold (do this before anything else on hardware)
**Why first:** AGENTS.md. The board's recovery is software; this proves it works.
**Important:** with USB plugged in, the board does **not** go dark. The 6 s hold writes the charger's "battery off" bit (BATFET_DIS), but USB keeps powering the board. The BSP's hardware notes record the board going dark only **when USB is then removed**. So "nothing happened" with the cable in is expected.
**Where:** terminal at the repo root, board plugged in. Use the console so you can see the firmware's own messages.
```
python tools/fw.py build orca_main
python tools/fw.py flash orca_main
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
**Where:** a second terminal. The display CPU enumerates as `FWOG display orca 001`.
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
cd orca/host
python -m pytest tests -q
python -m orca.mapping_demo
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
python -m orca.mapping_demo --port COM5
```
(use the display CPU's port). **Expect:** pressing a real OG button animates the same ring, and the log shows source `OG`.
**If the window is blank or errors:** paste the traceback. If pytest says `No module named orca`, you are not in `orca/host`.
**Report:** "Card 5: pytest pass/fail; demo ok / what looked wrong".

## Card 8: Rhythm Flick
**Where:** `orca/host`, `.venv` active. No reflash needed (uses the same `STREAM` as Card 7).
```
python -m pytest tests -q
python -m orca.rhythm_flick
```
**Expect (pytest):** `185 passed`.
**Part A, keyboard and buttons only.** Arrows fall one per beat toward a grey line. Press yellow (key 2) for a left arrow and blue (key 4) for a right arrow as it reaches the line.
**Expect:** a correct press near the line shows HIT and raises Hits; the wrong direction shows WRONG WAY; an arrow that passes unanswered shows MISS. Top-left shows Hits, Misses and Tempo. Get 8 hits in a row: Tempo rises by 5. Miss 3 in a row: it drops by 5. Press gray (Pain now): Tempo drops by 10. The pause, end, pain and summary screens behave as in the catch game.
**Part B, flick the real OG** (close any console first):
```
python -m orca.rhythm_flick --port COM5
```
Hold or strap the OG and flick it left and right as arrows land.
**Fixes:** left and right swapped: add `--invert`. No flicks register: add `--flick-dps 90` (lower is easier). Flicks fire by accident: raise `--flick-dps 220`. A different tilt direction works instead of the sideways one: add `--axis x`. Up and down too: add `--dirs all` (keys u / d work without the OG; `--invert-fwd` swaps them).
**Report:** "Card 8: part A ok / problem; part B ok / which flags I needed".

## Card 9: Data sidebar (any game)
**Where:** `orca/host`, `.venv` active. No reflash needed.
```
python -m pytest tests -q
python -m orca.brick_break
```
**Expect (pytest):** `185 passed`.
**Expect (window):** a third panel on the right (the window is about 1300 px wide) with two tables.
- **Live sensors** (top): one row per data channel with source, channel, latest value and age. Move the OG: `og acc` shows `x_mg= y_mg= z_mg=` changing and an age near 0.0s, and `og tilt` shows the angle. Press a button: `og button` shows the colour, the action and the screen. Rows older than 2 s turn grey. Sensors we plan but do not have yet show as `not connected` (forearm accelerometer, BNO085 IMU, haptic driver, force sensor).
- **Timeline** (bottom): newest row first, each with a time in seconds from when the window opened. Fast sensors (acc, tilt) show about 4 rows a second so you can read them; buttons and game events (catch, miss, pain score) show every time. The **freeze** box stops the scrolling so you can read it.
**Check the timestamps line up:** press a button, then look at its timeline row and at the game's log line under the game; the times should agree to within a fraction of a second.
**The CSV:** close the window, then open `orca/host/sessions/data-<time>.csv`. It has every row at full rate (about 50 acc rows a second), with columns `t_s, source, channel, dev_ms, fields`. `dev_ms` is the OG's own clock for OG rows.
**Without the OG:** `python -m orca.brick_break --no-og` works too. Only keyboard and game rows appear; `og acc` and `og tilt` are simply absent.
**If the window is too wide for your screen:** tell me the resolution.
**Report:** "Card 9: pytest pass/fail; live table ok / problem; timeline ok / problem; CSV ok / problem".

## Card 10: Two OGs, one per hand (assign the roles)
**Where:** `orca/host`, `.venv` active, both OGs plugged in and running the Orca firmware (flash the second one the same way as the first, one at a time: AGENTS.md says only one CPU in BOOTSEL at a time).
```
python -m pytest tests -q
python -m orca.devices
```
**Expect (pytest):** `185 passed`.
**Expect (devices):** `OG display CPUs found: 2` and a line per OG with its port and USB serial. (If you see 1, the second OG is not enumerating: paste `python -m serial.tools.list_ports -v`.)
Then assign them:
```
python -m orca.devices --setup
```
It says "Press any button on the left hand OG now...". Press a button on the OG you want as the left hand, then on the other when asked for the right hand.
**Expect:** `-> left_hand = serial ...`, `-> right_hand = serial ...`, `Saved devices.json`, and the final list showing a COM port for each role. Run `python -m orca.devices` again after unplugging and re-plugging both: the roles should follow the OGs even if the COM numbers changed.
**If a role says "No press seen":** the OG is not printing button lines (not running the Orca firmware), or another program holds its port.
**Report:** "Card 10: found N OGs; setup ok / problem; roles still correct after re-plug yes / no".

## Card 11: Rhythm Flick with two hands
**Where:** `orca/host`. No reflash.
```
python -m orca.rhythm_flick --devices devices.json
```
**Expect:** two lanes, LEFT and RIGHT. Arrows fall in a lane with a small L or R on the block. Flick the matching hand's OG sideways as the arrow reaches the line: HIT. Flick the wrong hand's OG: `WRONG HAND` (no penalty). The data panel's **hand** column shows L and R on the rows, and the live table has an `og acc` and `og tilt` row for each hand.
**Fixes:** a hand's left and right are swapped: `--invert-roles left_hand` (or `right_hand`, or both comma separated). Nothing registers: `--flick-dps 90`. Fires by accident: `--flick-dps 220`. Without OGs the buttons and keys 2 / 4 flick for either hand.
Finish a round (red, then green on "End session?", pain, confirm). **Expect on the summary:** a small table with Range, Peak deg/s and Hit rate for L and R, a ratio, and which side is weaker.
**Report:** "Card 11: lanes ok / problem; hand tagging ok / problem; symmetry table ok / problem; flags needed".

## Card 13: Dial
**Where:** `orca/host`. Rest the forearm flat (a towel roll), OG on the back of the hand or forearm, screen up.
```
python -m orca.dial_game --port COM5
```
(or `--devices devices.json --driver left_hand`). Press **z** first for neutral.
**Expect:** a semicircle dial. A yellow marker and band show the target; the green needle follows the OG's roll. Hold the needle inside the band for 1.5 s to score (a bar fills while you hold). After each success the band gets 1 degree narrower; a target not reached in 15 s widens it by 2.
**Fixes:** needle moves the wrong way: `--invert-roles right_hand`. No movement but another tilt moves it: `--axis x`. Range too large or small: `--dial-range 30`.
**Report:** "Card 13: needle ok / problem; holding and scoring ok / problem; flags needed".

## Card 14: Launcher and the new games (no reflash needed)
**Where:** `orca/host`, `.venv` active, numpy installed (`pip install numpy`; it is probably there already).
```
python -m pytest tests -q
python -m orca.launcher
```
**Expect (pytest):** `185 passed`.
**Expect (launcher):** a window listing five games, each with a Start button, a one-line description and the movement it uses, plus the connected OGs and their roles. Only one program can hold an OG's serial port, so **start one game at a time** and close it before opening another that uses the OGs.
The options box adds command-line options for the next game, for example `--invert-roles left_hand`.
**Report:** "Card 14: pytest pass/fail; launcher opens ok / problem; device list correct yes / no".

## Card 15: Brick Break (fixed after your recorded session)
**What your session showed:** the steering pitch only went one way from the starting pose (0 down to about -18 degrees, never above 0), so the paddle could only reach the left half of the field. 8 drops against 13 bricks in 27 seconds. Two changes: the game now **learns your tilt range as you play** and stretches it over the whole field, and the ball **waits on the paddle for 0.8 s** before every serve.
```
cd orca/host
python -m pytest tests -q
python -m orca.brick_break
```
**Expect (pytest):** `185 passed`.
**Expect (game):** a wall of bricks, a ball and a paddle. The ball sits on the paddle for a moment before each serve, then launches. Tilt the OG **sideways**, however far you can manage, even only one way from where you started: the paddle should reach **both** edges of the field, and the top line shows `Range NN deg`, the span it has learned. A small wrist range gives a small span; the paddle still covers the whole field.
Check: (1) move to your two extremes; the paddle should be at the left edge at one and the right edge at the other; (2) hold still for several seconds; the paddle should not creep; (3) press **z** to learn the range again from where you are.
**Direction:** the game now steers by sideways tilt (roll). It first steered by forward/back tilt (pitch); your recording showed you tilt mostly sideways (roll moved 2.7 times as much as pitch) and pitch then moved against you about a third of the time, which is what "sometimes the wrong direction" was. If the paddle goes the wrong way every time, add `--invert-roles right_hand`; to steer by forward/back tilt instead, `--movement pitch`.
**Fixes:** The paddle still jitters: tell me, with how big the movement of the board is at the time. To get the old fixed mapping: `--fixed-range --range-deg 18` (l and r then set your range).
**Report:** "Card 15: paddle reaches both edges yes / no; serve delay ok; drops per minute roughly; range shown N deg".

## Card 16: Steady Hand
```
python -m orca.steady_hand --devices devices.json
```
**Expect:** a crosshair field, a yellow ring and a white cursor. The cursor moves sideways with roll and up/down with pitch. Hold it inside the ring (it turns green and a bar fills for 2 s); a new ring appears. The top line shows Roll, Pitch and, after a few seconds of play, `Tremor N mg`. The ring narrows after each success.
**Without an OG:** keys 2 / 4 nudge roll, keys u / d nudge pitch.
**Fixes:** cursor moves the wrong way up/down: `--invert-fwd-roles right_hand`; sideways: `--invert-roles right_hand`.
**Report:** "Card 16: both axes move the cursor yes / no; tremor value appears yes / no".

## Card 17: Colour Reflex
```
python -m orca.color_reflex --devices devices.json
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
cd orca/host
python -m pytest tests -q
python -m orca.brick_break --devices devices.json
python -m orca.rhythm_flick --devices devices.json
python -m orca.steady_hand --devices devices.json
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
python tools/fw.py build orca_main
python tools/fw.py flash orca_main
```
Wait until the OG screen shows `Orca`, then open the **main CPU's** port (product ID 2054, it was COM4; re-list ports first if unsure):
```
python tools/fw.py console --port COM4
```
**Expect:** first, every two seconds, `[orca_main] I2C0 devices (1): 0x14` (Bosch's driver gives 0x14 or 0x15 as the chip's two addresses), then `[orca_main] BMM350 running at 0x14, 50 Hz`, then 50 lines a second like `MAG 120 6040 812 -1530 2204 50321 1` (sequence, milliseconds, raw X, Y, Z, raw temperature, data-ready flag). Turn the board: the three numbers change. With nothing wired: `I2C0 devices (0): none` forever. If it prints `answered, chip id 0x.. (want 0x33)`, paste that line.
**If it says none with the sensor wired:** re-check SDA and SCL are not swapped, that 3V3 is on the 3.3 V pin, and that each jumper is seated. Paste the lines you see.
**Report:** "Card 20: found N device(s), address 0x...".

## Card 21: Magnetometer vs accelerometer tester
**First, with no hardware at all:**
```
cd orca/host
python -m pytest tests -q
python -m orca.mag_accel_tester --simulate
```
**Expect (pytest):** `185 passed`. **Expect (simulate):** a table of five actions (still, spin, tilt, shake, magnet) with `ok yes` on every row. Read it as the pattern a working pair should show: spinning flat moves only the magnetometer; shaking moves only the accelerometer; tilting moves both; a magnet changes the field *strength* while gravity stays put. It says SIMULATED at the top; it is not your sensors.
**Then with the real sensors (Card 20 working, MAG lines streaming):** fix the BMM350 board to the OG with tape or a rubber band so they always move together, keep the jumper wires slack, then:
```
python -m orca.mag_accel_tester --og-port COM5 --mag-port COM4 --csv-out mag_test.csv
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
cd orca/host
python -m pytest tests -q
python -m orca.mag_accel_tester --calibrate --mag-port COM4
```
**Expect (pytest):** `185 passed`. When it says GO, turn the board slowly through **every** orientation for 25 seconds: flip it over, spin it, point each edge up and down. **Expect:** an offset line, then `Field strength after removing it: NN uT`, which should land roughly between 25 and 65 (Earth's field), and a small fit error. It saves `mag_offset.json`. If the strength is far outside that, or it says the fit is poor, repeat somewhere clearer and cover more directions.
**Step 2, watch.** Tape the BMM350 board to the OG so they move together, then:
```
python -m orca.mag_accel_tester --watch --og-port COM5 --mag-port COM4
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
cd orca/host
python -m pytest tests/test_pspi.py tests/test_face_strain.py tests/test_hrv.py tests/test_rppg.py -q
```
**Expect:** `34 passed`. No download, no webcam, no weight file. These use made-up faces and pulses with known answers, so they prove the arithmetic, not that it works on a real face.
**If it fails:** paste the first `FAILED` block. `No module named numpy` means the venv is missing numpy (`python -m pip install numpy`). `No module named orca` means the shell is not in `orca/host`.
**Report:** "Card 24: pass" or the first failure line.

## Card 25: The OG as the screen (menu, games, face view, dark/light, brightness, sound)
**Camera needs OpenCV** (for the Face view and the Face page): with the venv active, `python -m pip install opencv-python`. If it is missing, the screen says so instead of showing a picture.

**Needs a rebuild and reflash** (the OG gained `BRIGHT` and `BEEP`, and the red-hold light changed). Do this first, with only the OG plugged in:
```
fw build orca_main
fw flash orca_main
```
**Expect:** the build ends without errors, the flash copies, and the OG shows "Orca / waiting for host". **If the build fails:** paste the first `error:` line. Close every other program that has the OG port open (launcher games, the demo, a serial terminal) before step C: only one program can hold it.

**Red button (do this once after flashing):**
1. Tap red quickly several times: **no LED should light**.
2. Hold red: nothing for about half a second, then the red bar starts filling. Let go before 6 s: the LEDs go back to how they were.
3. Hold red for the full 6 s with USB unplugged: the OG powers off (this is the original power-off test, still required).
**Report:** which of 1-3 behaved differently.

**A. Host tests first (no board):**
```
cd orca/host
python -m pytest tests/test_og_shell_parts.py tests/test_og_display.py tests/test_og_screen.py -q
```
**Expect:** all pass. **If it fails:** paste the first `FAILED` block.

**B. Laptop only (no OG):**
```
python -m orca.og_shell --no-og
```
**Expect:** a window showing the menu. Press `2` or Down arrow: the highlight moves. Press `4`: it flips light/dark. Press `3` on a game: the game opens in its own window; the shell window keeps showing what the OG would show.

**C. With the OG:**
```
python -m orca.og_shell
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
6. **Close** the shell window: the OG shows "Orca closed on the laptop".
7. **Brightness:** Settings (yellow), down to Brightness, green. It steps 25, 50, 75, 100 % and the backlight should visibly change. The OG never goes fully dark.
8. **Sound:** down to Sound, green. It steps off, low, medium, high, with a sample beep each time (silent on off). Then every button press in the menu ticks. If there is never any sound at any level, say so: the boot line `[orca_display] ... audio=ok` can be read from a serial terminal on the OG's port before the shell starts.
9. **Saved:** close the shell and start it again. Theme, brightness and sound should come back as you left them (they are kept in `orca/host/og_settings.json`).
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
2. Supabase: create a project (supabase.com, free tier is fine). Open **SQL Editor**, paste all of `orca/host/supabase_schema.sql`, run it. Expect "Success. No rows returned".
3. Supabase **Project Settings -> API**: copy the **Project URL** and the **anon public** key. Do **not** use the service_role key.
4. Copy `orca/host/.env.example` to `orca/host/.env` and fill in: `SUPABASE_URL`, `SUPABASE_KEY` (the anon key), `ORCA_PARTICIPANT` (a code like P001, not a name), `ORCA_SEED` (any long random phrase). Nothing else is needed: no ASI:One key, no Agentverse mailbox.
   Leave the two Supabase lines empty to try everything first without a database.

**B. Host tests (no network)**
```
cd orca/host
python -m pytest tests/test_agent_parts.py tests/test_og_shell_parts.py -q
```
**Expect:** all pass. **If it fails:** paste the first `FAILED` block.

**C. Run it (three terminals, from `orca/host`, venv active)**
1. `python -m orca.agents_main`
   **Expect:** three lines "Orchestrator agent1...", "Hand agent agent1...", "Face agent agent1...", then "Supabase: configured" (or "not configured"). Warnings about registering with the Almanac are fine without internet. **If it stops with an error,** paste it: this is the first run against a real uAgents install.
2. `python -m orca.og_shell` -> OG menu -> down to **Agents** -> green.
   **Expect:** four rows of boxes (Devices / Sensing / Policy / Storage). Before you play: Orchestrator may show idle, others "no data", Supabase "sent n" or "not configured". The hint line says "No finished round yet".
3. Play a game from the menu (green), then watch the agent terminal. While you play, `OG hand` and `Hand agent` should go green with a message rate. End the game: **End** (red), **End now** (green), set the pain with the -2 -1 OK +1 +2 buttons, **OK**.
   **Expect in the agents terminal:** a line `round: brick_break hit_rate=... -> push/hold/ease (...)`. Back on the OG Agents page the hint shows `Policy: <action> (<reason>)`.
4. In Supabase: **Table Editor -> rounds**. **Expect** one new row per finished round, within about 5 seconds.
**If rows do not arrive:** the agents terminal prints `Supabase send failed: ...`. The rows stay queued in `agents_queue.jsonl` and are sent later; paste the message. A 401 or 403 means the wrong key or the SQL policy was not run.

**D. Optional: show a gateway agent in your Agentverse (mailbox)**
Only do this if you are happy for one agent to be registered with Fetch.ai's Agentverse. The first attempt put a mailbox on the orchestrator inside the Bureau, and Agentverse's Inspector answered "Could not find this Agent on your local host": it expects a standalone agent on its own port. So there is now a separate **gateway agent** (`agent_gateway.py`, port 8001). It only receives messages from outside agents you allow and hands them to the local program. The games' hand and face numbers never go through it.
1. Sign up at agentverse.ai.
2. Keep `python -m orca.agents_main` running. In a second terminal (same folder, venv active): `python -m orca.agent_gateway`.
3. **Expect** `Gateway agent1q...`, an `Allowed senders:` line (it says "none yet" until you fill in `ORCA_ALLOWED_SENDERS`), uAgents' own `Agent inspector available at ...` line, and my `https://agentverse.ai/inspect/...` link. Open the link while it runs, click **Connect**, choose **Mailbox**, follow the steps.
4. **Expect** the terminal to say it registered as a mailbox agent, and `orca_gateway` to appear in your Agentverse agents.
5. To let the Pi in later: put the Pi agent's `agent1q...` address in `ORCA_ALLOWED_SENDERS` in `.env`, restart the gateway. A message it accepts is logged as `passed a 'round' message from ...`.
**If it fails:** paste the terminal output from the gateway.

**E. Send a message in through the gateway (the Pi's job, rehearsed on the laptop)**
1. Gateway and `agents_main` running. In a third terminal: `python -m orca.agent_test_client agent1q...` (the gateway's address from its `Gateway ...` line).
2. **Expect:** the client logs `my address (add it to ORCA_ALLOWED_SENDERS): agent1q...`. Copy that address into `ORCA_ALLOWED_SENDERS=` in `.env`, stop and restart **only the gateway**, then run the client again.
3. **Expect, in order:** client `sent one test round...`; gateway `passed a 'round' message from agent1q...`; client `the gateway acknowledged...`; `agents_main` terminal `round: gateway_test hit_rate=0.8 -> ...`. In Supabase a `rounds` row with game `gateway_test` (delete it after).
**If the gateway says `ignored a message from ... not in ORCA_ALLOWED_SENDERS`:** the address was not saved or the gateway was not restarted. **If nothing arrives at all:** paste the client and gateway output.

**F. One table per agent, and picking the data up**
Three tables now: `rounds` (orchestrator), `hand_readings` (hand agent), `face_readings` (face agent). The hand and face agents save one snapshot every `ORCA_SAMPLE_S` seconds (default 5). The face table holds webcam-derived numbers: only with the person's informed consent.
1. **Create the two new tables:** in Supabase SQL Editor, paste the whole of `supabase_schema.sql` again and run it (every statement is safe to repeat). **Expect** `hand_readings` and `face_readings` in Table Editor.
2. Restart `python -m orca.agents_main`. **Expect** the `Supabase:` line to name the three tables and the snapshot interval.
3. Play a game from the OG menu for about 30 seconds. **Expect** `sent N hand row(s) to Supabase` in the agents terminal every 5 seconds or so (and `face` rows if the webcam is on), and new rows in `hand_readings` with `jerk_peak`, `rom` and the full reading in `data`.
4. **Picking up (a trusted machine only):** in Supabase, **Project Settings, API, service_role key**. Put it in `SUPABASE_SERVICE_KEY` in the `.env` of the trusted machine (the Pi), never on the laptop that plays, never in git. Then `python -m orca.supabase_pull hand_readings 5`. **Expect** the 5 newest rows printed.
**If a table's send fails:** the warning names the table (`Supabase send failed (hand): ...`) and its rows stay queued locally.

**Report:** paste the three address lines, one `round:` line, what the Agents page showed (a photo is fine), and whether a row appeared in Supabase.

## Card 29: Record a demo with a SIMULATED patient (synthetic data, say so in the video)
**What it is:** a made-up patient, DEMO01, played through the real agents so the OG's Chain and Steps pages show genuine filtering, checks and decisions, plus backdated rows in Supabase so the dashboard shows a trend. **Everything is synthetic.** Say "simulated patient" on camera. The live player refuses to run unless the agents are running as a DEMO participant, so it cannot be saved into a real person's record.

**The story (seven sessions over two weeks, left hand weaker than the right):** sessions 1-4 the usual picture, noted but not verified (nothing unusual for this person yet); session 5 a tired day, **watch** (the game is not made harder); session 6 a bad day, **concerning (verified)** and the difficulty is **eased**; session 7 recovered.

**A. Check the story first (no hardware):**
```
cd orca\host
python -m pytest tests/test_demo_story.py -q
```
**Expect:** all pass. It plays the whole story through the real filters, checks and decisions and checks the verdicts and decisions come out as above.

**B. Dashboard rows (Supabase, once):** in the SQL Editor paste all of `orca\host\demo_seed.sql` and run it. **Expect** 7 rows in `rounds`, about 70 in `hand_readings` and 70 in `face_readings`, all participant `DEMO01`, dated over the last 15 days. To remove them: uncomment the three `delete` lines at the top of the file and run it.

**C. The live demo (the real agents, fast):** first make sure no older `agents_main` is running (a "port in use" error means one is: close its terminal, or see below).
1. Terminal 1, from `orca\host` with the venv on, set the three settings, then start the agents:
   ```
   $env:ORCA_PARTICIPANT = "DEMO01"
   $env:ORCA_WINDOW_S = "2"
   $env:ORCA_SAMPLE_S = "0.5"
   python -m orca.agents_main
   ```
2. Terminal 2: `python -m orca.og_shell`, open **Agents** (the chain) on the screen OG.
3. Terminal 3: `python -m orca.demo_data` plays all seven sessions in about two minutes (each is about 7 s of readings, a short wait for the last window to be checked, and a 4 s gap). Use `--only 6` to play just the bad day, `--speed 2` to slow it down for the camera, `--gap 8` for longer pauses. Note the verdicts for sessions 1-6 build on each other, so play 1 to 6 in order at least once before using `--only 6`.
   **Expect:** the chain lights up and dots run down Filter, Check, Decide, Act; the **Steps** page (gray) fills with FILTERED / CHECKED / DECIDED / DID lines; each session ends with a verdict as in the story. Terminal 1 prints the same steps.
4. After the demo, close terminal 1 so the next real session starts as the real participant (the simulated settings only live in that terminal).

**If agents_main says "Only one usage of each socket address":** an older agents_main is still running. Find it with `Get-NetTCPConnection -LocalPort 8000 | Select OwningProcess`, then `Stop-Process -Id <that number>`.

**Report:** a photo of the Chain and Steps pages during session 6, and the `[check]`/`[decide]` lines for it.

## Card 28: The agent chain (Filter, Check, Decide, Act): a demo you can justify
**What it is:** four agents in a chain, one per stage. **Filter** drops implausible hand readings and readings with no face, and says what it dropped; **Check** fact-checks a possible imbalance between the hands four ways when a round ends; **Decide** gives the verdict, then the difficulty recommendation and the rule behind it; **Act** saves the round and the clean readings. Every step is printed, kept in `agents_trace.jsonl`, shown on the OG, and (if you switch it on) answered in the ASI:One chat. The thresholds are placeholders, not clinically validated; nothing here is medical advice.

**A. Host tests (no network):**
```
cd orca\host
python -m pytest tests/test_agent_chain.py tests/test_agent_parts.py -q
```
**Expect:** all pass. **If it fails:** paste the first `FAILED` block.

**B. Run it (needs both hand OGs; see Card 27):**
1. Terminal 1: `python -m orca.agents_main`. **Expect** four address lines: `Filter agent`, `Check agent`, `Decide agent`, `Act agent`.
2. Terminal 2: `python -m orca.og_shell`. Open **Agents** (the chain) and press **gray** to flip to **Steps**.
3. Play Brick Break with both hands connected, about 40 seconds, and tilt the two hands differently (one with a small range, one wide).
   **Expect in terminal 1, every 10 s:** `[filter] left hand: kept 9 of 10, dropped 1 implausible jerk`, `[filter] hands compared: 0.52 (left weaker; range 18 vs 35)`, and `[filter] face: ...` if the webcam is on.
4. End the round (red, then green, then the pain scale and **OK**).
   **Expect, in order:** `[check]` lines `1/4 enough data`, `2/4 persists`, `3/4 unusual for them` (it says `unknown (no baseline yet)` until about 3 earlier rounds), `4/4 other signals agree`; then `[decide] verdict: ...` and `[decide] difficulty: ... (rule)`; then `[act] round saved` and `[act] recommendation: ...`.
5. On the OG **Steps** page each line carries a tag: **FILTERED**, **CHECKED**, **DECIDED**, **DID**. Text is green (fine), amber (worth a look) or red (a verified concern). The **chain** view shows the dots moving down Filter, Check, Decide, Act.
6. Play three or more rounds with the same imbalance: the verdict should climb from `noted, not verified` or `watch` to `concerning (verified)` only once the baseline exists and the other signals agree. A finding that is only `watch` must never make the game harder (the decision says `hold: imbalance not fully verified`).

**C. On ASI:One (optional, and OFF by default):**
1. In `.env` set `ORCA_PUBLIC_ANSWERS=1`, then run `python -m orca.agent_gateway` (it prints `Public answers ... ON`).
2. In the Agentverse chat with your gateway agent, ask: `what are the agents doing?`, `why is the verdict that?`, `what did you decide?`, `how balanced are the hands?`.
   **Expect:** the same steps as on the OG, tagged FILTERED/CHECKED/DECIDED/DID; for "why" each of the four tests with its evidence; a closing line that it is a research prototype. The answers never contain the participant code.
3. Turn `ORCA_PUBLIC_ANSWERS` off (empty) afterwards unless the person has consented.

**Report:** paste the `[filter]`, `[check]`, `[decide]` and `[act]` lines from one round, and a photo of the Steps page.

## Card 27: Three OGs on cables: left hand, right hand, screen
**The idea:** two OGs are worn (their accelerometers steer the games), one OG is the screen (the menu, the game picture and the buttons). Each needs its own USB port on the laptop (or a powered USB hub). No new firmware: each OG needs only the current `orca_main` firmware, which streams tilt and button presses.

**A. Make sure all three run the Orca firmware**
1. Plug in all three. In the venv: `python -m serial.tools.list_ports -v`
   **Expect** three entries with `VID:PID=093C:2055` (the display CPUs) and different `SER=` numbers. (Three more `093C:2054` entries are the main CPUs; ignore them.)
2. An OG that is not showing "Orca / waiting for host" or a game name on its screen may not have the firmware. Flash it: unplug the other two, then `python tools\fw.py build orca_main` (once) and `python tools\fw.py flash orca_main`. **One OG at a time**: two in the bootloader cannot be told apart.
3. Put a sticker on each OG: **L**, **R**, **S** (screen). You will tell the software which is which in a moment.

**B. Assign the roles on the OGs' own screens (once, from `orca\host`)**
1. Close `agents_main`, any game and any other `og_shell`: only one program can hold an OG's port.
2. `python -m orca.og_shell --setup` (it also starts by itself when several OGs are plugged in and no roles are saved).
3. **Expect:** a window "Orca: assign the OGs", and **every OG** shows "Which OG is the SCREEN? Press GRAY on the OG that will show the menu and games."
   - Press **gray** on the OG that should be the screen. **Expect:** it now shows "Pick the LEFT HAND OG", and the other two show "Is this the LEFT HAND OG? Press GRAY here if it is."
   - Press **gray** on the left-hand OG (the one with the L sticker). **Expect:** it shows "This is the LEFT HAND"; the screen OG now asks for the RIGHT HAND.
   - Press **gray** on the right-hand OG. **Expect:** "Setup done" on the OGs, then the window closes and the normal shell starts, with its first printed line reading `screen COM..; left hand COM..; right hand COM..`.
   - **Yellow** on any OG skips the role being asked (for example if you only have one hand OG). **Red** on any OG starts again. Other buttons only show "Press GRAY to choose".
4. It saved `devices.json` in `orca\host`. Delete that file to go back to one OG doing everything, or run `--setup` again to redo it.
**Fallback in the terminal:** `python -m orca.devices --setup` does the same, asking in the terminal.

**C. Run everything**
1. Terminal 1: `python -m orca.agents_main`
2. Terminal 2: `python -m orca.og_shell`
   **Expect** the first line printed to read like `screen COM7; left hand COM5; right hand COM6`, the same in the window's status line, and the menu on the **screen** OG.
3. On the screen OG, open a game (green). **Expect:** the game picture on the screen OG; the two hand OGs show small text screens (game name, their own hand numbers).
4. **Which hand plays:** Brick Break, Steady Hand and Dial (one-hand games) first show a **Hand select** screen with two cards, LEFT HAND and RIGHT HAND (the one that will play is outlined and marked PLAYS; each shows whether its OG is connected). Press **yellow** for the left hand or **blue** for the right, then **green** (Confirm) to start; red goes back. Then tilt that hand's OG: the paddle moves; the other hand does nothing. The screen only appears when both hands are connected, and `--driver` sets which one is pre-selected. Rhythm Flick uses both hands and Colour Reflex only the buttons, so they do not ask.
5. The screen OG's buttons do pause, resume, end and the pain scale, as before. Pressing a button on a *hand* OG also counts as a press.
6. Play to the end and open Supabase: `hand_readings` should get rows for **both** hands (the `role` column), and `rounds` one row per finished round.

**An OG worn the other way up (its picture is upside down) needs a firmware update, once**
The picture rotation is a new firmware command (`ROT 180`, which flips the screen's column and row order). Rebuild and flash the OG that is worn upside down: `python tools\fw.py build orca_main`, then unplug the other OGs and `python tools\fw.py flash orca_main` (**one OG at a time**; the other hand can be done the same way later). Until an OG has this firmware it ignores the command and stays the old way up.
Then set it: **Settings -> Left hand screen** (or Right hand screen), green until it reads *turned 180*. It is separate from the tilt rows, so the tilt can stay *normal*. It is sent when a game starts (and during `--setup`, so the title reads the right way up as soon as you choose that OG). **Not yet seen on hardware:** if the picture comes out mirrored instead of turned, tell me which way.

**Options if something is the wrong way round**
- A hand's tilt goes the wrong way (for example a hand OG worn turned 180 degrees): open **Settings** in the shell menu (laptop keys or the screen OG), go down to **Left hand tilt** or **Right hand tilt** and press green to cycle: *normal*, *both reversed* (a 180 degree turn: left/right AND forward/back), *roll reversed* (only left/right), *pitch reversed* (only forward/back). It is saved. Test with Brick Break and `--driver left_hand`: tilt the left OG to the right; the paddle should go right. The flags `--invert-roles` and `--invert-fwd-roles` still work and are added to the saved choice.
- Tilt is read on the wrong axis for how you wear it: `--axis x`.
- Rhythm Flick uses both hands automatically when both are connected.

**If it fails:** paste the first line the shell printed, and any `Note:` lines. A hand OG that does nothing usually has no Orca firmware, is on a different port than expected, or another program has it open.

## Card 26: Beat Flick (new game, one built-in song)
**Needs:** nothing flashed. Sound uses Windows' own audio (no install); on a Pi it needs `aplay` (package `alsa-utils`, normally present).

**A. Logic tests first (no board, no sound):**
```
cd orca/host
python -m pytest tests/test_beat_flick.py -q
```
**Expect:** all pass. The first run of the song test builds a 4 MB WAV in `~/.orca/`. **If it fails:** paste the first `FAILED` block.

**B. Keyboard only:**
```
python -m orca.beat_flick --no-og
```
Press green (3) to start. Red blocks fall in the left lane and blue in the right. Flick with keys `a` left, `s` right, `u` up, `d` down as a block reaches the line (any hand works with no OG). **Expect:** the music plays from the start, HIT/MISS words appear, Score and Combo rise, and the multiplier goes to x2 after 10 hits in a row. Pause (green) stops the music and Resume carries on. After about 91 s it goes to the pain check-in by itself.

**C. One OG, then two:**
```
python -m orca.beat_flick                              # the one OG that is plugged in
python -m orca.beat_flick --devices devices.json       # both OGs, one per hand
```
(`devices.json` comes from `python -m orca.devices --setup`.) With two OGs a flick from the wrong hand shows WRONG HAND and costs nothing. Flick with the OG as in Rhythm Flick; tune `--flick-dps` lower if flicks are missed. Without `--devices`, two plugged-in OGs are refused with a message saying so.

**Report:** whether the music starts with the first beat in time with the first blocks (the kick should land as a block reaches the line), whether pause and resume keep them in step, and the Score and Accuracy at the end. If the music drifts from the blocks after a pause, say how many seconds by the end.

## Results log
| Date | Card | Result | Notes |
|---|---|---|---|
| | | | |
