import numpy as np
import pytest

from wilirehab import hrv

FS = 30.0


def pulse_from_beats(beat_s, seconds, fs=FS, width_s=0.09):
    t = np.arange(int(seconds * fs)) / fs
    sig = np.zeros_like(t)
    for b in beat_s:
        sig += np.exp(-0.5 * ((t - b) / width_s) ** 2)
    return sig


def beats_from_ibis(ibis_s, start=0.5):
    return start + np.concatenate([[0.0], np.cumsum(ibis_s)])


def test_alternating_intervals_give_a_known_rmssd():
    # 760 / 840 ms alternating: every successive difference is 80 ms.
    ibis = np.tile([0.76, 0.84], 60)
    beats = beats_from_ibis(ibis)
    sig = pulse_from_beats(beats, beats[-1] + 1.0)
    got = hrv.from_pulse(sig, FS)
    assert got.rmssd_ms == pytest.approx(80.0, abs=15.0)
    assert got.n_beats >= 100


def test_steady_pulse_has_near_zero_rmssd():
    beats = beats_from_ibis(np.full(100, 0.8))
    sig = pulse_from_beats(beats, beats[-1] + 1.0)
    assert hrv.from_pulse(sig, FS).rmssd_ms < 15.0


def _modulated(freq_hz, seconds=200.0, mean_ibi=0.8, depth=0.06):
    beats, t = [0.5], 0.5
    while t < seconds:
        t += mean_ibi + depth * np.sin(2 * np.pi * freq_hz * t)
        beats.append(t)
    return np.asarray(beats)


def test_slow_modulation_has_more_lf_than_hf():
    beats = _modulated(0.09)
    sig = pulse_from_beats(beats, beats[-1] + 1.0)
    assert hrv.from_pulse(sig, FS).lf_hf > 1.5


def test_fast_modulation_has_more_hf_than_lf():
    beats = _modulated(0.27)
    sig = pulse_from_beats(beats, beats[-1] + 1.0)
    assert hrv.from_pulse(sig, FS).lf_hf < 0.7


def test_too_short_a_window_returns_none_not_a_number():
    beats = beats_from_ibis(np.full(30, 0.8))          # 24 s
    sig = pulse_from_beats(beats, beats[-1] + 1.0)
    got = hrv.from_pulse(sig, FS)
    assert got.rmssd_ms is None
    assert got.lf_hf is None


def test_lf_needs_longer_than_rmssd():
    beats = beats_from_ibis(np.full(100, 0.8))          # about 80 s
    sig = pulse_from_beats(beats, beats[-1] + 1.0)
    got = hrv.from_pulse(sig, FS)
    assert got.rmssd_ms is not None
    assert got.lf_hf is None


def test_flat_signal_has_no_beats():
    got = hrv.from_pulse(np.zeros(600), FS)
    assert got.n_beats == 0
    assert got.rmssd_ms is None


def test_a_missed_beat_is_not_bridged_in_the_differences():
    times = np.cumsum(np.full(80, 0.8))
    with_gap = np.delete(times, 40)                    # one beat missed: a 1.6 s interval
    assert hrv.rmssd(with_gap) == pytest.approx(0.0, abs=1e-6)
    ibi, ok = hrv.valid_intervals(with_gap)
    assert not ok[39]


def test_change_from_rest_ratios():
    rest = hrv.Hrv(80, 70.0, 50.0, 1.0)
    now = hrv.Hrv(80, 70.0, 25.0, 2.0)
    got = hrv.change_from_rest(rest, now)
    assert got["rmssd_ratio"] == pytest.approx(0.5)
    assert got["lf_hf_ratio"] == pytest.approx(2.0)


def test_change_from_rest_with_a_missing_side_is_none():
    got = hrv.change_from_rest(hrv.Hrv(10, 8.0, None, None), hrv.Hrv(80, 70.0, 30.0, 1.0))
    assert got == {"rmssd_ratio": None, "lf_hf_ratio": None}
