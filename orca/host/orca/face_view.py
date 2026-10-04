"""A live camera picture for the OG's face view.

Only a preview: frames are shown and dropped, never written anywhere. The camera is held
only while the face screen is open (`stop()` releases it), because the games' face
monitor needs the same camera.
"""
from __future__ import annotations

import sys
import threading
import time

from PIL import Image

OUT_W, OUT_H = 426, 320            # the face box on the OG screen, at drawing size
FPS = 12


def cover_box(src_w: int, src_h: int, dst_w: int = OUT_W, dst_h: int = OUT_H) -> tuple:
    """The centred crop (x0, y0, x1, y1) of a src_w x src_h picture with the aspect of the target."""
    want = dst_w / dst_h
    if src_w / src_h > want:                     # too wide: trim the sides
        w = round(src_h * want)
        x0 = (src_w - w) // 2
        return x0, 0, x0 + w, src_h
    h = round(src_w / want)                      # too tall: trim top and bottom
    y0 = (src_h - h) // 2
    return 0, y0, src_w, y0 + h


def to_preview(rgb: Image.Image, mirror: bool = True) -> Image.Image:
    """A camera frame cropped and scaled to the face box, flipped like a mirror."""
    img = rgb.crop(cover_box(*rgb.size)).resize((OUT_W, OUT_H), Image.BILINEAR)
    return img.transpose(Image.FLIP_LEFT_RIGHT) if mirror else img


class FacePreview:
    def __init__(self, camera: int = 0):
        self.camera = camera
        self.error = None
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        self.error, self._frame = None, None
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.5)       # the camera must be free before a game opens it
            self._thread = None

    def latest(self):
        """(picture, serial number), or None before the first frame; the number changes with the picture."""
        with self._lock:
            return self._frame

    def _run(self) -> None:
        try:
            import cv2
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.camera, backend)
            if not cap.isOpened():
                self.error = f"Cannot open camera {self.camera}"
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            try:
                n = 0
                while not self._stop.is_set():
                    t0 = time.monotonic()
                    ok, bgr = cap.read()
                    if not ok:
                        self.error = "The camera returned no picture"
                        return
                    picture = to_preview(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
                    n += 1
                    with self._lock:
                        self._frame = (picture, n)
                    self._stop.wait(max(0.0, 1.0 / FPS - (time.monotonic() - t0)))
            finally:
                cap.release()
        except ImportError:
            self.error = "The camera needs OpenCV. In the venv: python -m pip install opencv-python"
        except Exception as exc:                 # shown on the OG, not swallowed
            self.error = f"{type(exc).__name__}: {exc}"
