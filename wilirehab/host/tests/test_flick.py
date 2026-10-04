import math

from wilirehab.flick import FlickDetector, match_flick

DT = 0.02


def feed(det, samples):
    """samples: (t_s, side, fwd). Returns the list of non-None results."""
    return [r for r in (det.update(*s) for s in samples) if r]


def ramp(t0, a, b, duration, axis="side", dt=DT):
    """Samples that move one axis from a to b over `duration`, the other staying at 0."""
    n = max(1, round(duration / dt))
    out = []
    for i in range(1, n + 1):
        v = a + (b - a) * i / n
        out.append((t0 + i * dt, v if axis == "side" else 0.0, v if axis == "fwd" else 0.0))
    return out


def hold(t0, side, fwd, duration, dt=DT):
    n = round(duration / dt)
    return [(t0 + i * dt, side, fwd) for i in range(1, n + 1)]


def start(side=0.0, fwd=0.0):
    return [(0.0, side, fwd)]


# ---- what should be a flick ------------------------------------------------

def test_a_slow_tilt_is_not_a_flick():
    det = FlickDetector()
    assert feed(det, start() + ramp(0.0, 0, 40, 1.6)) == []        # 25 deg/s


def test_a_fast_move_right():
    det = FlickDetector()
    assert feed(det, start() + ramp(0.0, 0, 20, 0.10)) == ["right"]    # 200 deg/s


def test_a_fast_move_left():
    det = FlickDetector()
    assert feed(det, start() + ramp(0.0, 0, -20, 0.10)) == ["left"]


def test_forward_axis_gives_up_and_down():
    assert feed(FlickDetector(), start() + ramp(0.0, 0, 20, 0.10, "fwd")) == ["up"]
    assert feed(FlickDetector(), start() + ramp(0.0, 0, -20, 0.10, "fwd")) == ["down"]


def test_the_larger_axis_wins():
    det = FlickDetector()
    samples = start()
    for i in range(1, 6):
        samples.append((i * DT, 1.0 * i, 4.0 * i))                  # side 5, forward 20
    assert feed(det, samples) == ["up"]


def test_it_fires_as_soon_as_the_excursion_is_reached():
    det = FlickDetector(min_excursion_deg=8.0)
    out = [det.update(*s) for s in start() + ramp(0.0, 0, 20, 0.10)]
    assert out.index("right") <= 3             # by the third sample, not after the move ends


# ---- what must not be a flick ---------------------------------------------

def test_a_small_bump_that_stops_short_is_not_a_flick():
    det = FlickDetector()
    samples = start() + ramp(0.0, 0, 5, 0.025) + hold(0.025, 5, 0, 0.5)
    assert feed(det, samples) == []


def test_a_move_smaller_than_the_minimum_excursion_is_ignored():
    one_fast_step = start() + ramp(0.0, 0, 6, 0.02)           # 6 degrees in 20 ms = 300 deg/s
    assert feed(FlickDetector(), one_fast_step) == []
    assert feed(FlickDetector(min_excursion_deg=5.0), one_fast_step) == ["right"]


def test_tremor_sized_wobble_is_ignored():
    det = FlickDetector()
    wobble = [(i * DT, math.sin(2 * math.pi * 10 * i * DT) * 1.0, 0.0) for i in range(100)]
    assert feed(det, wobble) == []                       # 1 degree at 10 Hz is about 63 deg/s


def test_an_immediate_return_stroke_is_not_a_second_flick():
    det = FlickDetector()
    out_and_back = (start() + ramp(0.0, 0, 20, 0.10) + ramp(0.10, 20, 0, 0.10))
    assert feed(det, out_and_back) == ["right"]          # the way back was the old false hit


def test_settling_wobble_after_a_flick_is_ignored():
    det = FlickDetector()
    samples = start() + ramp(0.0, 0, 20, 0.10)
    samples += [(0.10 + (i + 1) * DT, 20 + (3 if i % 2 else -3), 0.0) for i in range(8)]
    assert feed(det, samples) == ["right"]


# ---- re-arming ------------------------------------------------------------

def test_a_second_flick_after_the_hand_settles_counts():
    det = FlickDetector()
    samples = start() + ramp(0.0, 0, 20, 0.10)
    samples += hold(0.10, 20, 0, 0.5)                    # calm for half a second
    samples += ramp(0.60, 20, 0, 0.10)                   # a deliberate flick back
    assert feed(det, samples) == ["right", "left"]


def test_it_stays_blocked_while_the_hand_keeps_moving():
    det = FlickDetector()
    samples = start() + ramp(0.0, 0, 20, 0.10)
    t = 0.10
    for _ in range(6):                                   # swinging, never calm
        samples += ramp(t, 20, 0, 0.10)
        samples += ramp(t + 0.10, 0, 20, 0.10)
        t += 0.20
    assert feed(det, samples) == ["right"]


def test_bad_time_steps_are_ignored():
    det = FlickDetector()
    det.update(1.0, 0, 0)
    assert det.update(1.0, 50, 0) is None      # dt == 0
    assert det.update(0.5, 90, 0) is None      # time went backwards


# ---- matching a flick to an arrow ------------------------------------------

def blk(direction, t_hit, state="live"):
    return {"dir": direction, "t_hit": t_hit, "state": state}


def test_match_hit():
    result, b = match_flick([blk("left", 10.0)], "left", 10.1, 0.35)
    assert result == "hit" and b["t_hit"] == 10.0


def test_match_wrong_direction():
    result, _ = match_flick([blk("left", 10.0)], "right", 10.0, 0.35)
    assert result == "wrong"


def test_match_outside_window_is_none():
    result, b = match_flick([blk("left", 10.0)], "left", 11.0, 0.35)
    assert result == "none" and b is None


def test_match_takes_the_closest_block():
    blocks = [blk("left", 10.0), blk("right", 10.4)]
    result, b = match_flick(blocks, "right", 10.35, 0.5)
    assert result == "hit" and b["dir"] == "right"


def test_match_skips_resolved_blocks():
    result, _ = match_flick([blk("left", 10.0, state="done")], "left", 10.0, 0.35)
    assert result == "none"


def hblk(direction, t_hit, hand):
    return {"dir": direction, "t_hit": t_hit, "state": "live", "hand": hand}


def test_the_matching_hand_hits():
    blocks = [hblk("left", 10.0, "left_hand")]
    result, b = match_flick(blocks, "left", 10.0, 0.35, hand="left_hand")
    assert result == "hit" and b is blocks[0]


def test_the_other_hand_cannot_take_the_block():
    blocks = [hblk("left", 10.0, "left_hand")]
    result, b = match_flick(blocks, "left", 10.0, 0.35, hand="right_hand")
    assert result == "wrong_hand" and b is None


def test_each_hand_gets_its_own_block_when_both_are_due():
    blocks = [hblk("left", 10.0, "left_hand"), hblk("right", 10.1, "right_hand")]
    result, b = match_flick(blocks, "right", 10.05, 0.35, hand="right_hand")
    assert result == "hit" and b["hand"] == "right_hand"


def test_unknown_hand_matches_any_block():
    blocks = [hblk("left", 10.0, "left_hand")]
    result, _ = match_flick(blocks, "left", 10.0, 0.35, hand=None)
    assert result == "hit"


def test_blocks_without_a_hand_match_any_hand():
    result, _ = match_flick([blk("left", 10.0)], "left", 10.0, 0.35, hand="right_hand")
    assert result == "hit"


def test_wrong_direction_from_the_right_hand_is_wrong_not_wrong_hand():
    blocks = [hblk("left", 10.0, "left_hand")]
    result, _ = match_flick(blocks, "right", 10.0, 0.35, hand="left_hand")
    assert result == "wrong"
