import pytest

from wilirehab.pspi import PSPI_MAX, pspi, unit_scale


def test_paper_example_with_both_pairs_tied():
    # AU4 B(2) + AU6 E(5) + AU7 E(5) + AU9 E(5) + AU10 D(4) + AU43 A(1):
    # 2 + max(5,5) + max(5,4) + 1 = 13 (Lucey et al. worked example).
    assert pspi(2, 5, 5, 5, 4, 1) == 13


def test_unbc_example_six():
    # AU6 c(3) + AU9 b(2) + AU43(1) = 6.
    assert pspi(0, 3, 0, 2, 0, 1) == 6


def test_maximum_is_sixteen():
    assert pspi(5, 5, 5, 5, 5, 1) == PSPI_MAX == 16


def test_zero_face_is_zero():
    assert pspi(0, 0, 0, 0, 0, 0) == 0


def test_larger_of_each_pair_is_used_not_the_sum():
    assert pspi(0, 1, 4, 0, 0, 0) == 4
    assert pspi(0, 0, 0, 3, 2, 0) == 3


def test_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        pspi(6, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError):
        pspi(-1, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError):
        pspi(float("nan"), 0, 0, 0, 0, 0)


def test_eye_closure_is_binary():
    with pytest.raises(ValueError):
        pspi(0, 0, 0, 0, 0, 2)
    with pytest.raises(ValueError):
        pspi(0, 0, 0, 0, 0, 0.5)


def test_unit_scale():
    assert unit_scale(0) == 0.0
    assert unit_scale(8) == 0.5
    assert unit_scale(99) == 1.0
