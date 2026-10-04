"""Play a WAV file with pause and resume, using nothing but what the computer already has.

Windows: the built-in MCI audio calls through ctypes (supports start-from, pause, resume).
Linux, Raspberry Pi and macOS: `aplay` / `paplay` / `afplay` as a child process; pause stops
the process (SIGSTOP) and resume continues it (SIGCONT). That cannot start part-way in, and the
sound card's own buffer keeps playing for a moment after a pause, so a pause can overshoot a
little. If nothing can play, `error` says why and the game runs silent.

Not tested on hardware: this was written without a machine to listen on.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys

WINDOWS = sys.platform == "win32"
ALIAS = "orca_song"


class SongPlayer:
    def __init__(self, path):
        self.path = str(path)
        self.error = None
        self._proc = None
        self._opened = False
        if not WINDOWS:
            for name, args in (("aplay", ["-q"]), ("paplay", []), ("afplay", [])):
                found = shutil.which(name)
                if found:
                    self._cmd = [found, *args, self.path]
                    break
            else:
                self._cmd = None
                self.error = "no audio player found (install alsa-utils for aplay)"

    # ---- Windows (MCI) -------------------------------------------------------

    def _mci(self, command: str) -> bool:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        code = ctypes.windll.winmm.mciSendStringW(command, buf, 255, 0)
        if code:
            msg = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(code, msg, 255)
            self.error = msg.value
        return code == 0

    # ---- the four calls --------------------------------------------------------

    def start(self, at_s: float = 0.0) -> None:
        self.stop()
        try:
            if WINDOWS:
                if self._mci(f'open "{self.path}" type waveaudio alias {ALIAS}'):
                    self._opened = True
                    self._mci(f"play {ALIAS} from {int(at_s * 1000)}")
            elif self._cmd:
                self._proc = subprocess.Popen(self._cmd, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL)
        except Exception as exc:                  # never take the game down for the music
            self.error = f"{type(exc).__name__}: {exc}"

    def pause(self) -> None:
        try:
            if WINDOWS and self._opened:
                self._mci(f"pause {ALIAS}")
            elif self._proc and self._proc.poll() is None and hasattr(signal, "SIGSTOP"):
                os.kill(self._proc.pid, signal.SIGSTOP)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def resume(self) -> None:
        try:
            if WINDOWS and self._opened:
                self._mci(f"resume {ALIAS}")
            elif self._proc and self._proc.poll() is None and hasattr(signal, "SIGCONT"):
                os.kill(self._proc.pid, signal.SIGCONT)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def stop(self) -> None:
        try:
            if WINDOWS and self._opened:
                self._mci(f"stop {ALIAS}")
                self._mci(f"close {ALIAS}")
                self._opened = False
            if self._proc is not None:
                if self._proc.poll() is None:
                    if hasattr(signal, "SIGCONT"):
                        os.kill(self._proc.pid, signal.SIGCONT)   # a stopped process ignores terminate
                    self._proc.terminate()
                self._proc = None
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
