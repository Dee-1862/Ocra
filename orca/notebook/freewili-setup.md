# FREE-WILi setup, board facts and example projects

Source: the workshop slides, pasted. Condensed and reordered; steps are as given.

## Three ways to program the OG
| Way | What | Where it runs |
|---|---|---|
| **OneWili API** | Control the board from your computer (Python over USB serial) | Laptop |
| **WASM scripts** | Small programs on the stock firmware (WiliWasm engine) | On the board, stock firmware |
| **wiliOGbsp** | Write your own firmware (C, Pico SDK) | Replaces stock firmware |

The FREE-WILi GUI is one desktop app for all of it. Stock firmware can be restored from it (see "Back to stock").

## One board, two brains
| Display CPU | Main CPU |
|---|---|
| Screen and buttons | Sub-GHz radios |
| LEDs and speaker | FPGA |
| Accelerometer | I/O header |

One file flashes both CPUs. **Always flash the `_main` file.**

## Setup, in order
1. **Tools:** FREE-WILi GUI (github.com/freewili/freewili-gui), VS Code, Git, Python 3 (Windows: python.org; Linux: `sudo apt install python3-venv`).
2. **Pico extension:** VS Code, Extensions, search "Raspberry Pi Pico", install the one by Raspberry Pi. Then Pico sidebar icon, New C/C++ Project, set **SDK version 2.3.0**, Create, wait a few minutes.
3. **Get the BSP:** `git clone https://github.com/freewili/wiliOGbsp.git`, then File, Open Folder.
4. **Python venv:** Windows `python -m venv .venv` then `.venv\Scripts\activate`; Mac/Linux `python3 -m venv .venv` then `source .venv/bin/activate`. You should see `(.venv)`. Then `pip install -r requirements.txt`.
5. **Build and flash the template:** `python tools/fw.py build template_main`, then `python tools/fw.py flash template_main`.
6. **Make your own app:** `python tools/fw.py new-app <name>` creates `apps/<name>/` with `display/` and `main/`.

Inside the BSP: `apps/template/` is the starting point (`display/main.c` for the screen CPU, `main/main.c` for the I/O CPU), `bsp/` holds drivers, `tools/fw.py` builds and flashes.

### Workshop exercise: button lights
Display `main.c`: add a colour table for gray, yellow, green, blue, red; call `ws2812_init(pio0, 0);` right after `board_init();`; in the loop, keep the result of `fwog_power_poll(now)` and on each button release set all LEDs to that button's colour (divided by 16) and call `ws2812_process();`. Then `fw build button_lights_main` and `fw flash button_lights_main`.

Note: the BSP's root `CMakeLists.txt` lists `apps/button_lights`, which only exists after someone runs this exercise. It is now guarded so a fresh clone still configures.

### Back to stock
FREE-WILi GUI, Setup, FreeWili OG updater, Firmware tab, Update and verify.

### Where to get help
freewili.com (product docs), freewili.com/onewili (OneWili API), github.com/freewili/wiliOGbsp, github.com/freewili/freewili-gui, or the FREE-WILi table at the event. *(Last line truncated in paste.)*

## Local machine notes (this laptop)
- Pico SDK 2.3.0 and toolchain are under `~/.pico-sdk`.
- No host C compiler, so the SDK cannot build `picotool` from source. Configure with `-Dpicotool_DIR=C:/Users/Reddy/.pico-sdk/picotool/2.3.0/picotool`.
- So `fw test` (host C tests) cannot run here until a C compiler is installed.

## 20-pin I/O header (from the product image)
Notch between pins 10 and 12. Top row is even pins, bottom row is odd.

| Pin | Signal | | Pin | Signal |
|---|---|---|---|---|
| 1 | GPIO13, SPI1 CS (out) | | 2 | 5 V out |
| 3 | GPIO27 (out) | | 4 | V PINS in |
| 5 | GPIO9, UART1 Rx (in) | | 6 | 3.3 V out |
| 7 | GPIO10, UART1 CTS (in) | | 8 | GPIO17, I2C0 SCL |
| 9 | GPIO8, UART1 Tx (out) | | 10 | GPIO16, I2C0 SDA |
| 11 | GPIO11, UART1 RTS (out) | | 12 | GPIO12, SPI1 Rx (in) |
| 13 | GPIO15, SPI1 Tx (out) | | 14 | GPIO26 (in) |
| 15 | GPIO14, SPI1 SCLK (out) | | 16 | SWCLK (in) |
| 17 | GPIO25 (out) | | 18 | SWDIO |
| 19 | GND | | 20 | GND |

Transcribed from a photo by hand. Check against `docs/hardware/pinmap.md` before wiring anything. For us, the useful part is **I2C0 on pins 8 and 10 with 3.3 V on pin 6**: that is where an external IMU would connect. These pins belong to the **main CPU**, not the display CPU.

## Example FREE-WILi projects and their best parts
| Project | Key features | Useful to Orca for |
|---|---|---|
| thereMINI | Python API, accelerometer | Streaming the OG's accelerometer to a laptop (roadmap Step 2) |
| WILi-Party | Python API, screen, LEDs | Laptop-driven screen and LED feedback (Step 1) |
| WILi Watch | Radio, LEDs | Not needed |
| WILi-Pass | Radio, screen, speaker | Speaker for audio cues, maybe |

thereMINI and WILi-Party both used the **Python API** (OneWili). That is evidence the laptop-drives-the-OG route works for exactly what Steps 1 and 2 need, but I have not read their code. Look at them before writing our own streaming.

## Changelog
| Date | Change |
|---|---|
| 2026-10-03 | Page created from the workshop slides. |
