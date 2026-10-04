"""Beat Flick's notes, judging and scoring. Pure logic: no window, no audio, no OG.

The note format follows the Beat Saber map format (BeatSaver "v2": a `_notes` list of
`_time` in beats, `_type` 0 = left hand / 1 = right hand / 3 = bomb, and `_cutDirection` 0 to 8),
so a downloaded map could be loaded later. The scoring idea is BeepSaber's (MIT, studied in
past_projects): points from how well timed the hit is, times a combo multiplier that grows
every 10 hits. What an OG cannot do is dropped: it gives tilt, not a 3D position, so there is
no swing-distance or swing-angle score, and diagonal cuts are accepted as either of their two
straight flicks.

The built-in song is a map made here (`demo_map`), 84 BPM, about 91 seconds.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .bilateral import LEFT, RIGHT

BPM = 84
BEATS = 128                                   # 32 bars of 4 beats
SONG_SECONDS = BEATS * 60.0 / BPM

# `_cutDirection` -> (flicks that count, arrow shown). Numbers as in the Beat Saber map
# format (0 up, 1 down, 2 left, 3 right, 4-7 the diagonals, 8 any direction).
CUT = {
    0: (("up",), "↑"), 1: (("down",), "↓"),
    2: (("left",), "←"), 3: (("right",), "→"),
    4: (("up", "left"), "↖"), 5: (("up", "right"), "↗"),
    6: (("down", "left"), "↙"), 7: (("down", "right"), "↘"),
    8: (("up", "down", "left", "right"), "●"),
}
HAND_OF_TYPE = {0: LEFT, 1: RIGHT}            # `_type` 3 (bombs) is skipped


@dataclass
class Note:
    t: float                                   # seconds from the start of the song
    hand: str                                  # LEFT or RIGHT
    accepts: tuple                             # flicks that hit it
    glyph: str
    state: str = "live"                        # live | done
    err_s: float = field(default=0.0)


def notes_from_map(data: dict, bpm: float = BPM) -> list:
    """Notes from a Beat Saber v2 map dict, sorted by time. Bombs and unknown types are skipped."""
    out = []
    for n in data.get("_notes", ()):
        hand = HAND_OF_TYPE.get(n.get("_type"))
        cut = CUT.get(n.get("_cutDirection"))
        if hand is None or cut is None:
            continue
        out.append(Note(t=float(n["_time"]) * 60.0 / bpm, hand=hand, accepts=cut[0], glyph=cut[1]))
    out.sort(key=lambda note: note.t)
    return out


# One cut direction per note, cycling, for each hand. Later sections add diagonals.
_BASIC = {0: (2, 1, 2, 0), 1: (3, 1, 3, 0)}               # left: ← ↓ ← ↑   right: → ↓ → ↑
_DIAG = {0: (4, 2, 6, 0), 1: (5, 3, 7, 1)}                # adds ↖ ↙ / ↗ ↘


def demo_map() -> dict:
    """The built-in song's notes, as a Beat Saber v2 map.

    Two bars of intro with no notes, then one note every 2 beats (bars 2-9), then one per beat,
    alternating hands, with diagonals in bars 18-25 and no notes in the last 2 bars. The slowest
    stretch gives each hand a note about every 1.4 s."""
    notes, per_hand = [], [0, 0]
    for beat in range(8, BEATS - 8):
        bar = beat // 4
        if bar < 10 and beat % 2:
            continue
        hand = len(notes) % 2
        table = _DIAG if 18 <= bar <= 25 else _BASIC
        cycle = table[hand]
        cut = 8 if per_hand[hand] % 8 == 7 else cycle[per_hand[hand] % len(cycle)]
        per_hand[hand] += 1
        notes.append({"_time": float(beat), "_lineIndex": 1 + hand, "_lineLayer": 0,
                      "_type": hand, "_cutDirection": cut})
    return {"_version": "2.0.0", "_notes": notes, "_events": [], "_obstacles": []}


def judge_flick(notes, direction: str, now: float, window: float, hand=None):
    """Which note does a flick at song time `now` belong to?

    Returns ("hit" | "wrong" | "wrong_hand" | "none", note), like flick.match_flick but a note
    can accept two directions (diagonals). `hand` None means any hand may take any note."""
    due = [n for n in notes if n.state == "live" and abs(n.t - now) <= window]
    if not due:
        return "none", None
    if hand is not None:
        mine = [n for n in due if n.hand == hand]
        if not mine:
            return "wrong_hand", None
        due = mine
    note = min(due, key=lambda n: abs(n.t - now))
    return ("hit" if direction in note.accepts else "wrong"), note


def timing_accuracy(err_s: float, window: float) -> float:
    """1.0 for dead on the beat, falling in a straight line to 0.0 at the edge of the window."""
    return max(0.0, min(1.0, 1.0 - abs(err_s) / window))


def verdict(err_s: float) -> str:
    err = abs(err_s)
    return "PERFECT" if err < 0.08 else "GOOD" if err < 0.2 else "OK"


class Scorer:
    """Score, combo and accuracy.

    A hit is worth 50 for the right direction plus up to 50 for timing, times a multiplier of
    1 + one per 10 hits in a row (at most 8). A miss or a wrong-way flick resets the combo."""

    def __init__(self):
        self.score = 0
        self.combo = 0
        self.best_combo = 0
        self.hits = 0
        self.misses = 0
        self._right = 0.0
        self._wrong = 0.0

    @property
    def multiplier(self) -> int:
        return 1 + min(self.combo // 10, 7)

    def hit(self, err_s: float, window: float) -> int:
        """Record a hit; returns the points it earned (multiplier included)."""
        base = round(50 + 50 * timing_accuracy(err_s, window))
        self.combo += 1
        self.best_combo = max(self.best_combo, self.combo)
        self.hits += 1
        earned = base * self.multiplier
        self.score += earned
        self._right += base / 100.0
        self._wrong += 1.0 - base / 100.0
        return earned

    def miss(self) -> None:
        self.combo = 0
        self.misses += 1
        self._wrong += 1.0

    @property
    def accuracy(self):
        """Percent, or None before the first note."""
        total = self._right + self._wrong
        return None if total == 0 else 100.0 * self._right / total
