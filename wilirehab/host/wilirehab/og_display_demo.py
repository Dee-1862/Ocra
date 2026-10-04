"""Draw a test card on the OG and measure how fast pictures really get there.

    python -m wilirehab.og_display_demo --port COM11

COM11 is the display CPU's port (USB product ID 2055). The OG must be running
wilirehab 002 or later. It prints the speed of three things: a full-screen
redraw (the worst case), a small moving square (a game), and a bigger box
that changes every frame (a camera preview). Press the OG buttons while it
runs; each press is printed, which proves the other direction still works.
"""
from __future__ import annotations

import argparse
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .og_display import H, W, OgDisplay, rgb565


def font(size: int):
    for name in ("segoeuisb.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def test_card() -> Image.Image:
    img = Image.new("RGB", (W, H), (11, 14, 18))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), outline=(60, 72, 84))
    d.text((16, 14), "OG SCREEN", font=font(34), fill=(232, 236, 241))
    d.text((18, 58), "320 x 240   pictures over USB", font=font(15), fill=(139, 149, 161))
    bars = [(248, 113, 113), (251, 191, 36), (52, 211, 153), (96, 165, 250), (232, 236, 241), (91, 164, 176)]
    for i, color in enumerate(bars):
        d.rectangle((16 + i * 49, 100, 16 + i * 49 + 43, 150), fill=color)
    for i in range(0, W - 32):
        v = int(255 * i / (W - 33))
        d.line((16 + i, 170, 16 + i, 186), fill=(v, v, v))
    d.text((16, 200), "top-left is 0,0   red | amber | green | blue | white | teal", font=font(11),
           fill=(139, 149, 161))
    return img


class Counter:
    def __init__(self, ser):
        self.ser, self.acks, self.errors, self.buttons = ser, 0, [], []
        self.stop = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while not self.stop:
            line = self.ser.readline().decode("ascii", "replace").strip()
            if line == "OK":
                self.acks += 1
            elif line.startswith("ERR"):
                self.errors.append(line)
            elif line.startswith("BTN") and line.endswith("down"):
                self.buttons.append(line)
                print("  pressed:", line.split()[1])

    def wait_for(self, target: int, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        while self.acks < target and time.monotonic() < end:
            time.sleep(0.002)
        return self.acks >= target


def run(display: OgDisplay, counter: Counter, name: str, frames) -> None:
    start_acks, start_bytes = counter.acks, display.bytes
    t0 = time.monotonic()
    sent = 0
    for arr in frames:
        sent += display.send_frame(arr)
    ok = counter.wait_for(start_acks + sent)
    dt = time.monotonic() - t0
    n = display.frames
    kb = (display.bytes - start_bytes) / 1024
    print(f"{name:<34} {kb:7.0f} KB in {dt:5.2f} s = {kb / dt:6.0f} KB/s"
          f"{'' if ok else '   (the OG did not confirm every picture)'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", required=True, help="the OG display CPU's port, e.g. COM11")
    args = ap.parse_args()

    import serial
    with serial.Serial(args.port, 115200, timeout=0.2) as ser:
        counter = Counter(ser)
        ser.write(b"\nPING\n")
        time.sleep(0.4)
        display = OgDisplay(ser.write)
        base = rgb565(test_card())
        display.send_frame(base)
        counter.wait_for(counter.acks + 1, 2)
        print("Test card sent. Look at the OG: colours and the top-left corner should match.\n")
        time.sleep(2.5)

        rng = np.random.default_rng(0)
        full = []
        for k in range(8):
            frame = (np.roll(base, k * 37, axis=1) ^ rng.integers(0, 65535, size=(H, W), dtype=np.uint16)).astype(np.uint16)
            full.append(frame)
        run(display, counter, "full screen, every pixel new", full)

        display.invalidate()
        display.send_frame(base)
        counter.wait_for(counter.acks + 8, 3)
        moving = []
        for k in range(120):
            f = base.copy()
            x = 20 + (k * 2) % 270
            f[200:224, x:x + 24] = 0xFFFF
            moving.append(f)
        run(display, counter, "small moving square (a game)", moving)

        display.invalidate()
        display.send_frame(base)
        counter.wait_for(counter.acks + 8, 3)
        preview = []
        for k in range(60):
            f = base.copy()
            f[100:220, 150:310] = rng.integers(0, 65535, size=(120, 160), dtype=np.uint16)
            preview.append(f)
        run(display, counter, "160x120 box, new every frame", preview)

        time.sleep(0.3)
        display.close()
        counter.stop = True
        print()
        print("errors reported by the OG:", counter.errors or "none")
        print("Press OG buttons now to see them listed above (5 s)...")
        counter.stop = False
        time.sleep(5)
        counter.stop = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
