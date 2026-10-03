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
**Where:** same terminal, board plugged in by USB.
```
python tools/fw.py flash wilirehab_main
```
**Expect:** the flash tool reports success and the OG screen shows `WiliRehab` / `waiting for host`.
Then, with your finger: **hold the red button for 6 seconds.**
**Expect:** an LED countdown on the bar, then the board powers off.
**To wake it:** hold **gray**, or unplug and re-plug USB.
**If the screen never lights:** do not flash anything else. Restore stock: FREE-WILi GUI, Setup, FreeWili OG updater, Firmware tab, Update and verify.
**Report:** "Card 2: screen ok / not ok; power-off ok / not ok".

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
**Expect (pytest):** `5 passed`.
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

## Results log
| Date | Card | Result | Notes |
|---|---|---|---|
| | | | |
