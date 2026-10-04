"""Difficulty adaptation between rounds.

Deliberately simple and conservative: a rule table, not a model, so every
change in difficulty can be explained to a therapist. The thresholds are
placeholders from the design notes, NOT clinically validated -- the project
makes no effectiveness claim (Page 9).

Safety direction: any sign of pain, strain or physiological load only ever
eases difficulty. Pushing requires every signal to be calm at once.
"""
from __future__ import annotations

from dataclasses import dataclass

EASE = "ease"
HOLD = "hold"
PUSH = "push"
BREAK = "break"


@dataclass
class RoundResult:
    hit_rate: float                 # 0..1 fraction of targets hit
    compensation_events: int = 0
    heart_rate: float | None = None
    rest_heart_rate: float | None = None
    hr_quality: float = 0.0         # 0..1; low-quality HR is ignored
    strain: float | None = None     # 0..1 facial strain score
    pain: int | None = None         # 0..10 self-report


@dataclass
class Decision:
    action: str
    target_fraction: float          # share of the personal ROM to ask for
    reason: str


class AdaptationEngine:
    def __init__(self, start: float = 0.6, step: float = 0.05,
                 lo: float = 0.3, hi: float = 1.0,
                 pain_break: int = 7, pain_ease: int = 4,
                 strain_ease: float = 0.6, hr_ratio_ease: float = 1.4,
                 comp_ease: int = 3, hr_min_quality: float = 0.5,
                 push_hit_rate: float = 0.8):
        self.fraction = start
        self.step, self.lo, self.hi = step, lo, hi
        self.pain_break, self.pain_ease = pain_break, pain_ease
        self.strain_ease, self.hr_ratio_ease = strain_ease, hr_ratio_ease
        self.comp_ease, self.hr_min_quality = comp_ease, hr_min_quality
        self.push_hit_rate = push_hit_rate

    def _clamp(self, x: float) -> float:
        return max(self.lo, min(self.hi, x))

    def update(self, r: RoundResult) -> Decision:
        if r.pain is not None and r.pain >= self.pain_break:
            self.fraction = self._clamp(self.fraction - 2 * self.step)
            return Decision(BREAK, self.fraction, f"pain {r.pain}/10")

        reasons = []
        if r.pain is not None and r.pain >= self.pain_ease:
            reasons.append(f"pain {r.pain}/10")
        if r.strain is not None and r.strain >= self.strain_ease:
            reasons.append("facial strain")
        if (r.heart_rate is not None and r.rest_heart_rate
                and r.hr_quality >= self.hr_min_quality
                and r.heart_rate >= self.hr_ratio_ease * r.rest_heart_rate):
            reasons.append("heart rate high")
        if r.compensation_events >= self.comp_ease:
            reasons.append("compensation")
        if reasons:
            self.fraction = self._clamp(self.fraction - self.step)
            return Decision(EASE, self.fraction, ", ".join(reasons))

        # "Calm" must be positively established for pushing: a missing signal
        # is not evidence of calm, so require pain to have been reported.
        calm_known = r.pain is not None
        if r.hit_rate >= self.push_hit_rate and calm_known:
            self.fraction = self._clamp(self.fraction + self.step)
            return Decision(PUSH, self.fraction, "accurate and calm")

        return Decision(HOLD, self.fraction, "no change")
