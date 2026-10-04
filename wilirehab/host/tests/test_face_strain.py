import numpy as np
import pytest

from wilirehab.discomfort import reading
from wilirehab.face_strain import estimate_aus, mean_rgb, measures


def _face():
    """468 points; the ones the code reads form an open, resting face."""
    lm = [(0.5, 0.5)] * 468
    lm[33], lm[133] = (0.0, 0.0), (2.0, 0.0)
    lm[160], lm[144] = (0.7, -0.4), (0.7, 0.4)
    lm[158], lm[153] = (1.3, -0.4), (1.3, 0.4)
    lm[263], lm[362] = (4.0, 0.0), (6.0, 0.0)
    lm[387], lm[373] = (4.7, -0.4), (4.7, 0.4)
    lm[385], lm[380] = (5.3, -0.4), (5.3, 0.4)
    lm[70], lm[159] = (1.0, -1.4), (1.0, -0.4)
    lm[300], lm[386] = (5.0, -1.4), (5.0, -0.4)
    lm[2], lm[0] = (3.0, 2.0), (3.0, 2.8)
    return lm


def _with_eyes(lm, half_gap):
    out = list(lm)
    for upper, lower in ((160, 144), (158, 153), (387, 373), (385, 380)):
        out[upper] = (out[upper][0], -half_gap)
        out[lower] = (out[lower][0], half_gap)
    return out


def test_rest_face_gives_zero_pspi():
    rest = measures(_face())
    aus = estimate_aus(rest, rest)
    assert aus.pspi() == 0.0
    assert aus.au43 == 0


def test_closed_eyes_set_au43_and_au7():
    rest = measures(_face())
    shut = measures(_with_eyes(_face(), 0.02))
    aus = estimate_aus(rest, shut)
    assert aus.au43 == 1
    assert aus.au7 > 4.0
    assert aus.pspi() >= 5.0


def test_narrowed_but_open_eyes_are_au7_without_au43():
    rest = measures(_face())
    narrow = measures(_with_eyes(_face(), 0.25))
    aus = estimate_aus(rest, narrow)
    assert aus.au43 == 0
    assert 0.0 < aus.au7 < 5.0


def test_brow_lowering_raises_au4():
    lowered = _face()
    lowered[70], lowered[300] = (1.0, -0.65), (5.0, -0.65)
    aus = estimate_aus(measures(_face()), measures(lowered))
    assert aus.au4 > 2.0


def test_upper_lip_raise_raises_au10():
    raised = _face()
    raised[0] = (3.0, 2.4)
    aus = estimate_aus(measures(_face()), measures(raised))
    assert aus.au10 > 2.0


def test_opening_the_face_wider_never_scores():
    wide = _with_eyes(_face(), 0.6)
    wide[70], wide[300] = (1.0, -2.0), (5.0, -2.0)
    aus = estimate_aus(measures(_face()), measures(wide))
    assert aus.pspi() == 0.0


def test_cheek_and_nose_wrinkle_are_not_estimated():
    rest = measures(_face())
    aus = estimate_aus(rest, measures(_with_eyes(_face(), 0.02)))
    assert aus.au6 == 0.0
    assert aus.au9 == 0.0


def test_mean_rgb_averages_named_landmarks():
    frame = np.zeros((4, 4, 3))
    frame[1, 1] = (10, 20, 30)
    frame[1, 2] = (30, 40, 50)
    landmarks = [(0.0, 0.0)] * 468
    landmarks[10] = (1.0, 1.0)
    landmarks[67] = (2.0, 1.0)
    got = mean_rgb(frame, landmarks, (10, 67))
    assert got == pytest.approx([20.0, 30.0, 40.0])


def test_mean_rgb_skips_pixels_outside_the_frame():
    frame = np.zeros((2, 2, 3))
    landmarks = [(0.0, 0.0)] * 468
    landmarks[10] = (9.0, 9.0)
    assert mean_rgb(frame, landmarks, (10,)) is None


def test_reading_without_faces_returns_none_not_zero():
    got = reading(np.ones((90, 3)), 30.0, method="pos")
    assert got.pspi is None
    assert got.strain is None
    assert got.rmssd_ratio is None
    assert got.method == "pos"


def test_reading_with_faces_reports_pspi_and_strain():
    rest = measures(_face())
    shut = measures(_with_eyes(_face(), 0.02))
    got = reading(np.ones((90, 3)), 30.0, rest_face=rest, now_face=shut)
    assert got.pspi >= 5.0
    assert got.strain == pytest.approx(got.pspi / 16.0)
