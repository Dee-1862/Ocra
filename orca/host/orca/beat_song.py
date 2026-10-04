"""The built-in song for Beat Flick, made here so there is nothing to download or license.

`ensure_song()` writes a mono 16-bit WAV (about 4 MB, 91 s, 84 BPM) the first time and reuses
it after. Kick on every beat, hi-hat on the off-beats, a bass note on beats 1 and 3, and an
arpeggio over an A minor, F, C, G chord loop. Beat 0 of the audio is beat 0 of the map, so a
note's time in beats is its time in the song.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .beat_map import BEATS, BPM

RATE = 22050
VERSION = 1                                  # bump when the sound changes, so the file is rebuilt
CACHE = Path.home() / ".orca"

# Chord loop, one bar each: bass root, then the three chord tones for the arpeggio (Hz).
CHORDS = (
    (110.00, (440.00, 523.25, 659.25)),      # A minor
    (87.31, (349.23, 440.00, 523.25)),       # F
    (130.81, (523.25, 659.25, 783.99)),      # C
    (98.00, (392.00, 493.88, 587.33)),       # G
)
ARP = (0, 1, 2, 1, 0, 1, 2, 2)               # tone picked on each eighth note of a bar


def synth(bpm: float = BPM, beats: int = BEATS, rate: int = RATE) -> np.ndarray:
    """The song as int16 samples."""
    spb = 60.0 / bpm
    out = np.zeros(int(round(beats * spb * rate)) + rate, dtype=np.float64)   # +1 s of tail
    rng = np.random.default_rng(1)

    def add(start_s: float, sig: np.ndarray, gain: float) -> None:
        i = int(round(start_s * rate))
        n = min(len(sig), len(out) - i)
        if n > 0:
            out[i:i + n] += gain * sig[:n]

    t = np.arange(int(0.22 * rate)) / rate
    kick = np.sin(2 * np.pi * (45 * t + (90 / 28) * (1 - np.exp(-28 * t)))) * np.exp(-14 * t)
    th = np.arange(int(0.05 * rate)) / rate
    hat = np.diff(rng.standard_normal(len(th)), prepend=0.0) * np.exp(-90 * th)

    def tone(freq: float, seconds: float, decay: float) -> np.ndarray:
        tt = np.arange(int(seconds * rate)) / rate
        env = np.exp(-decay * tt) * (1 - np.exp(-120 * tt))
        return (np.sin(2 * np.pi * freq * tt) + 0.4 * np.sin(4 * np.pi * freq * tt)) * env

    for beat in range(beats - 4):                                # the last bar is only a tail
        add(beat * spb, kick, 0.9)
        add((beat + 0.5) * spb, hat, 0.12)
    for bar in range(beats // 4 - 1):
        root, tones = CHORDS[bar % len(CHORDS)]
        add(bar * 4 * spb, tone(root, 2 * spb, 2.2), 0.45)
        add((bar * 4 + 2) * spb, tone(root, 2 * spb, 2.2), 0.40)
        if bar >= 2:                                             # melody starts after the intro
            step = 1 if bar < 6 else 0.5                         # quarter notes, then eighths
            n = int(4 / step)
            for k in range(n):
                f = tones[ARP[int(k * step * 2) % len(ARP)]]
                add((bar * 4 + k * step) * spb, tone(f, 0.3, 7.0), 0.10)

    fade = int(6 * rate)                                         # a 6 s fade-out at the end
    end = int(round(beats * spb * rate))
    out[end - fade:end] *= np.linspace(1.0, 0.0, fade)
    out[end:] = 0.0
    out *= 0.85 / max(1e-9, float(np.max(np.abs(out))))
    return (out * 32767).astype(np.int16)


def ensure_song(path: Path | None = None) -> Path:
    """The song's WAV file, written if it is not there yet."""
    path = Path(path) if path else CACHE / f"beat_flick_song_v{VERSION}.wav"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        samples = synth()
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(samples.tobytes())
    return path
