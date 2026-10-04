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
**Expect (pytest):** `158 passed`.
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
**Expect (pytest):** `158 passed`.
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

## Card 8: Rhythm Flick
**Where:** `wilirehab/host`, `.venv` active. No reflash needed (uses the same `STREAM` as Card 7).
```
python -m pytest tests -q
python -m wilirehab.rhythm_flick
```
**Expect (pytest):** `158 passed`.
**Part A, keyboard and buttons only.** Arrows fall one per beat toward a grey line. Press yellow (key 2) for a left arrow and blue (key 4) for a right arrow as it reaches the line.
**Expect:** a correct press near the line shows HIT and raises Hits; the wrong direction shows WRONG WAY; an arrow that passes unanswered shows MISS. Top-left shows Hits, Misses and Tempo. Get 8 hits in a row: Tempo rises by 5. Miss 3 in a row: it drops by 5. Press gray (Pain now): Tempo drops by 10. The pause, end, pain and summary screens behave as in the catch game.
**Part B, flick the real OG** (close any console first):
```
python -m wilirehab.rhythm_flick --port COM5
```
Hold or strap the OG and flick it left and right as arrows land.
**Fixes:** left and right swapped: add `--invert`. No flicks register: add `--flick-dps 90` (lower is easier). Flicks fire by accident: raise `--flick-dps 220`. A different tilt direction works instead of the sideways one: add `--axis x`. Up and down too: add `--dirs all` (keys u / d work without the OG; `--invert-fwd` swaps them).
**Report:** "Card 8: part A ok / problem; part B ok / which flags I needed".

## Card 9: Data sidebar (catch game and Rhythm Flick)
**Where:** `wilirehab/host`, `.venv` active. No reflash needed.
```
python -m pytest tests -q
python -m wilirehab.catch_game --port COM5 --tilt
```
**Expect (pytest):** `158 passed`.
**Expect (window):** a third panel on the right (the window is about 1300 px wide) with two tables.
- **Live sensors** (top): one row per data channel with source, channel, latest value and age. Move the OG: `og acc` shows `x_mg= y_mg= z_mg=` changing and an age near 0.0s, and `og tilt` shows the angle. Press a button: `og button` shows the colour, the action and the screen. Rows older than 2 s turn grey. Sensors we plan but do not have yet show as `not connected` (forearm accelerometer, BNO085 IMU, haptic driver, force sensor).
- **Timeline** (bottom): newest row first, each with a time in seconds from when the window opened. Fast sensors (acc, tilt) show about 4 rows a second so you can read them; buttons and game events (catch, miss, pain score) show every time. The **freeze** box stops the scrolling so you can read it.
**Check the timestamps line up:** press a button, then look at its timeline row and at the game's log line under the game; the times should agree to within a fraction of a second.
**The CSV:** close the window, then open `wilirehab/host/sessions/data-<time>.csv`. It has every row at full rate (about 50 acc rows a second), with columns `t_s, source, channel, dev_ms, fields`. `dev_ms` is the OG's own clock for OG rows.
**Without the OG:** `python -m wilirehab.catch_game` works too. Only keyboard and game rows appear; `og acc` and `og tilt` are simply absent.
**If the window is too wide for your screen:** tell me the resolution.
**Report:** "Card 9: pytest pass/fail; live table ok / problem; timeline ok / problem; CSV ok / problem".

## Card 10: Two OGs, one per hand (assign the roles)
**Where:** `wilirehab/host`, `.venv` active, both OGs plugged in and running the WiliRehab firmware (flash the second one the same way as the first, one at a time: AGENTS.md says only one CPU in BOOTSEL at a time).
```
python -m pytest tests -q
python -m wilirehab.devices
```
**Expect (pytest):** `158 passed`.
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

## Card 12: Mirror hand
**Where:** `wilirehab/host`.
```
python -m wilirehab.mirror_hand --devices devices.json --driver right_hand
```
**Expect:** two drawn hands. The right one (green) turns as you tilt the right-hand OG; the left one (yellow) is its mirror image, turning the opposite way. If the left OG is worn, a dashed grey ghost shows its real tilt on top of the yellow hand, and the top line shows `Match NN%` and the error in degrees. The window shows angles magnified 2x; the table shows the real ones.
**Check:** `--driver left_hand` swaps which side drives. Without OGs, yellow/blue (keys 2 / 4) nudge the driver hand by 5 degrees.
**If the ghost moves the wrong way against the yellow hand:** `--invert-roles left_hand`.
**Report:** "Card 12: drawing ok / problem; ghost and match ok / problem; mirror direction right / flipped".

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
**Expect (pytest):** `158 passed`.
**Expect (launcher):** a window listing seven games, each with a Start button, a one-line description and the movement it uses, plus the connected OGs and their roles. Only one program can hold an OG's serial port, so **start one game at a time** and close it before opening another that uses the OGs.
The options box adds command-line options for the next game, for example `--invert-roles left_hand`.
**Report:** "Card 14: pytest pass/fail; launcher opens ok / problem; device list correct yes / no".

## Card 15: Brick Break
**Where:** `wilirehab/host`.
```
python -m wilirehab.brick_break --devices devices.json
```
Tilt the driver OG forward and back with the forearm flat; press **z** first for neutral.
**Expect:** a wall of coloured bricks, a ball and a blue paddle. The paddle moves left and right as you tilt forward and back (the top line says `Steer: wrist up/down (pitch)`). The ball breaks bricks, speeds up after each cleared wall and slows after a drop. Yellow / blue (keys 2 / 4) nudge the paddle without an OG.
**Fixes:** paddle goes the wrong way: `--invert-fwd-roles right_hand`. Nothing moves but a sideways tilt does: `--movement roll`, or `--axis x`. Range too big or small: tilt fully each way and press **l** and **r**.
**Report:** "Card 15: paddle follows pitch yes / no; ball and bricks behave yes / problem; flags needed".

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
**Expect (pytest):** `158 passed`.
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
**Expect (pytest):** `158 passed`. **Expect (simulate):** a table of five actions (still, spin, tilt, shake, magnet) with `ok yes` on every row. Read it as the pattern a working pair should show: spinning flat moves only the magnetometer; shaking moves only the accelerometer; tilting moves both; a magnet changes the field *strength* while gravity stays put. It says SIMULATED at the top; it is not your sensors.
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

## Results log
| Date | Card | Result | Notes |
|---|---|---|---|
| | | | |
