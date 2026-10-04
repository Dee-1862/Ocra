import numpy as np
import pytest

from wilirehab.rppg import chrom, estimate_hr, pos


def pulse_trace(fs=30.0, seconds=12.0, hz=1.2):
    """A clean skin-colour trace with a 72 bpm pulse stronger in green."""
    t = np.arange(int(fs * seconds)) / fs
    wave = np.sin(2 * np.pi * hz * t)
    rgb = np.stack([
        90.0 + 1.0 * wave,
        70.0 + 3.0 * wave,
        60.0 - 0.5 * wave,
    ], axis=1)
    return rgb, wave


def test_flat_trace_has_no_rate():
    rgb = np.ones((120, 3))
    hr = estimate_hr(rgb, 30.0)
    assert hr.bpm is None
    assert hr.quality == 0.0


def test_pos_and_chrom_match_the_trace_length():
    rgb, _ = pulse_trace()
    assert len(pos(rgb, 30.0)) == len(rgb)
    assert len(chrom(rgb, 30.0)) == len(rgb)


def _correlation(sig, wave):
    sig = sig - sig.mean()
    wave = wave - wave.mean()
    denom = np.linalg.norm(sig) * np.linalg.norm(wave)
    return float(np.dot(sig, wave) / denom)


def test_pos_tracks_a_planted_pulse():
    rgb, wave = pulse_trace()
    # The sign of the waveform is arbitrary for rate; only its shape matters.
    assert abs(_correlation(pos(rgb, 30.0), wave)) > 0.8
    hr = estimate_hr(rgb, 30.0, method="pos")
    assert hr.bpm == pytest.approx(72.0, abs=6.0)
    assert hr.quality > 0.5


def test_chrom_tracks_a_planted_pulse():
    rgb, wave = pulse_trace()
    assert abs(_correlation(chrom(rgb, 30.0), wave)) > 0.8
    hr = estimate_hr(rgb, 30.0, method="chrom")
    assert hr.bpm == pytest.approx(72.0, abs=6.0)


def test_unknown_method_is_rejected():
    with pytest.raises(ValueError):
        estimate_hr(np.ones((60, 3)), 30.0, method="deep")
