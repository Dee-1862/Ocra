"""Draw pictures on the OG's 320x240 screen.

The OG firmware understands `IMG x y w h` followed by w*h*2 raw bytes (RGB565,
little-endian, row by row; see apps/orca/display/rehab_proto.h). Sending a
whole screen is 153,600 bytes, far too slow to animate, so only the rectangles
that changed since the last picture are sent.

`OgDisplay.present()` may be called from the game's thread at any rate. A
sender thread keeps only the newest picture: if the OG cannot keep up, frames
in between are dropped and the next one is compared against what the screen
really shows, so the picture never drifts out of step.
"""
from __future__ import annotations

import threading
import time

import numpy as np
from PIL import Image

W, H = 320, 240
MAX_PIXELS = 320 * 48            # the firmware's receive buffer
BAND = 8                         # rows compared at a time


def rgb565(img: Image.Image) -> np.ndarray:
    """A 320x240 picture as an (H, W) array of RGB565 values, the way the panel packs them."""
    if img.size != (W, H):
        raise ValueError(f"the OG screen is {W}x{H}, got {img.size[0]}x{img.size[1]}")
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    return ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)


def split_rect(x: int, y: int, w: int, h: int, max_pixels: int = MAX_PIXELS) -> list:
    """Cut a rectangle into pieces the firmware can take (full width, few rows)."""
    rows = max(1, max_pixels // w)
    return [(x, yy, w, min(rows, y + h - yy)) for yy in range(y, y + h, rows)]


def changed_rects(old, new, band: int = BAND, max_pixels: int = MAX_PIXELS) -> list:
    """The rectangles (x, y, w, h) that must be sent to turn `old` into `new`.

    `old` is None for a screen of unknown content, which sends everything.
    Runs of changed bands are joined; each joined run is cut down to the columns
    that changed, then split to fit the firmware's buffer.
    """
    if old is None:
        return split_rect(0, 0, W, H, max_pixels)
    diff = old != new
    bands = diff.any(axis=1).reshape(H // band, band).any(axis=1)
    rects, i = [], 0
    while i < len(bands):
        if not bands[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(bands) and bands[j + 1]:
            j += 1
        y0, y1 = i * band, (j + 1) * band
        cols = np.flatnonzero(diff[y0:y1].any(axis=0))
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        rects += split_rect(x0, y0, x1 - x0, y1 - y0, max_pixels)
        i = j + 1
    return rects


def encode(arr: np.ndarray, rect) -> bytes:
    """The bytes that draw `rect` of `arr`: a newline (to drop any stray bytes), the header, the pixels."""
    x, y, w, h = rect
    header = f"\nIMG {x} {y} {w} {h}\n".encode("ascii")
    return header + np.ascontiguousarray(arr[y:y + h, x:x + w]).astype("<u2").tobytes()


class OgDisplay:
    def __init__(self, write):
        """`write(bytes)` sends bytes to the OG, e.g. OgLink.send_raw."""
        self._write = write
        self._shown = None                   # what the screen shows, None = unknown
        self._latest = None
        self._cv = threading.Condition()
        self._stop = False
        self._busy = False                   # a picture is being sent right now
        self.error = None
        self.frames = self.rects = self.bytes = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def present(self, img: Image.Image) -> None:
        """Show this picture soon. Replaces any picture still waiting to be sent."""
        arr = rgb565(img)
        with self._cv:
            self._latest = arr
            self._cv.notify()

    def invalidate(self) -> None:
        """Forget what the screen shows (after a reconnect, or the OG redrew itself)."""
        with self._cv:
            self._shown = None

    def send_frame(self, arr: np.ndarray) -> int:
        """Send `arr` now, on this thread; returns how many IMG commands that took."""
        rects = changed_rects(self._shown, arr)
        for rect in rects:
            data = encode(arr, rect)
            self._write(data)
            self.bytes += len(data)
        self._shown = arr.copy()
        self.frames += 1
        self.rects += len(rects)
        return len(rects)

    def flush(self, timeout: float = 3.0) -> bool:
        """Wait until the newest picture has been sent. False if it took longer than `timeout`."""
        end = time.monotonic() + timeout
        with self._cv:
            while (self._latest is not None or self._busy) and time.monotonic() < end \
                    and self.error is None:
                self._cv.wait(0.05)
            return self._latest is None and not self._busy

    def close(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                while self._latest is None and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                arr, self._latest = self._latest, None
                self._busy = True
            try:
                self.send_frame(arr)
            except Exception as exc:         # kept for the caller to show; the thread ends
                self.error = exc
                return
            finally:
                with self._cv:
                    self._busy = False
                    self._cv.notify_all()
