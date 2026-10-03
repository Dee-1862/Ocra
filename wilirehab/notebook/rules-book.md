# Rules book

Standing rules for working on WiliRehab, human or AI. Add a rule with the date and the reason. Never delete one; strike it through and say why.

## R1. Tests are run by a person; the assistant gives the commands
*2026-10-03, from Deekshith.*

When something needs testing, the assistant does **not** run it. It writes the exact commands to copy and paste, and says what output to expect and what a failure looks like. You run them and report back.

Applies to: hardware tests, flashing, serial/console sessions, `pytest`, `fw test`, and any other check. Builds follow the same rule unless you ask for one.

Each test card must have:
1. **Where to run it** (VS Code terminal, venv active, which folder).
2. **The commands**, one block, in order.
3. **Expected result**, as literal text where possible.
4. **If it fails**, the first thing to check.
5. **A line to paste back** to the assistant (what you saw).

Cards live in [manual-tests.md](manual-tests.md).

## R2. Bring-up order for the OG (from the BSP's AGENTS.md)
1. Display app declares `FWOG_POWER_DEFAULT()` and calls `fwog_power_poll(now_ms)` every loop.
2. **You observe the board power off on a 6 s red hold.** Code alone is not evidence.
3. Main app declares `FWOG_WATCHDOG_DEFAULT()` and calls `board_watchdog_kick()` every loop.
4. Only then add features.

## R3. Flashing
- **Always flash the `_main` target** (`wilirehab_main`). It carries the display image and writes the display's metadata.
- **Never flash a display `.uf2` directly.** The display CPU has no BOOTSEL button; a bad flash takes it off USB.
- Put **one CPU** in BOOTSEL at a time.
- To get back to stock firmware: FREE-WILi GUI, Setup, FreeWili OG updater, Firmware tab, Update and verify.
- Never add a watchdog to the display CPU. Never `printf` in driver code (use `DIAG()`). Never pass `-DPICO_BOARD`.

## R4. Honest status
- Say "built" when it compiled, "tested" only when a person ran a test and reported the result, "works on hardware" only when observed on a board.
- Numbers in the paper come from the lab tables, nothing else.
- Papers are cited only after someone opened the PDF.
- AI-generated text is tagged `[AI-assisted]` for the disclosure.

## R5. Privacy
Numbers only in the session log. No frames, landmarks or face crops are stored.

## R6. Notebook upkeep
Date every entry. When the design changes, update `diagrams.md` and add a line to `design-log-and-abstract.md` the same day. Do not guess pasted text that was cut off; mark it `[truncated in paste]`.

## Changelog
| Date | Change |
|---|---|
| 2026-10-03 | R1 to R6 created. |
