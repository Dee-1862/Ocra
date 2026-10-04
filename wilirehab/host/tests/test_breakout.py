import math

import pytest

from wilirehab.breakout import MAX_SPEED, MIN_SPEED, Breakout


def test_it_starts_with_a_full_wall_and_a_ball_going_up():
    g = Breakout()
    assert len(g.bricks) == 30
    assert g.vy < 0
    assert math.hypot(g.vx, g.vy) == pytest.approx(g.speed)


def test_the_ball_bounces_off_the_left_wall():
    g = Breakout()
    g.ball_x, g.ball_y, g.vx, g.vy = g.ball_r + 1, 100.0, -100.0, 0.0
    events = g.step(0.05, g.paddle_x)
    assert "wall" in events and g.vx > 0


def test_the_ball_bounces_off_the_right_wall():
    g = Breakout()
    g.ball_x, g.ball_y, g.vx, g.vy = g.width - g.ball_r - 1, 100.0, 100.0, 0.0
    g.step(0.05, g.paddle_x)
    assert g.vx < 0


def test_the_paddle_sends_the_ball_back_up():
    g = Breakout()
    g.ball_x = g.paddle_x
    g.ball_y = g.paddle_y - g.paddle_h / 2 - g.ball_r - 1
    g.vx, g.vy = 0.0, 100.0
    events = g.step(0.02, g.paddle_x)
    assert "paddle" in events and g.vy < 0


def test_hitting_the_edge_of_the_paddle_angles_the_ball():
    g = Breakout()
    g.ball_x = g.paddle_x + g.paddle_w / 2          # right edge
    g.ball_y = g.paddle_y - g.paddle_h / 2 - g.ball_r - 1
    g.vx, g.vy = 0.0, 100.0
    g.step(0.02, g.paddle_x)
    assert g.vx > 0 and g.vy < 0


def test_a_missed_ball_is_a_drop_and_slows_the_game():
    g = Breakout(speed=170.0)
    g.ball_x, g.ball_y, g.vx, g.vy = 10.0, g.height + 50, 0.0, 100.0
    events = g.step(0.02, g.width - 100)            # paddle far away
    assert "lost" in events
    assert g.drops == 1 and g.speed == pytest.approx(153.0)
    assert g.vy < 0                                  # relaunched upward


def test_a_brick_breaks_and_the_ball_turns_round():
    g = Breakout()
    b = g.bricks[20]                                # bottom row, first column
    g.ball_x = (b[0] + b[2]) / 2
    g.ball_y = b[3] + g.ball_r + 1                  # just under the brick
    g.vx, g.vy = 0.0, -120.0
    events = g.step(0.03, g.paddle_x)
    assert "brick" in events
    assert g.score == 1 and len(g.bricks) == 29
    assert g.vy > 0


def test_clearing_the_last_brick_starts_the_next_level_faster():
    g = Breakout(speed=170.0)
    g.bricks = [g.bricks[20]]
    b = g.bricks[0]
    g.ball_x = (b[0] + b[2]) / 2
    g.ball_y = b[3] + g.ball_r + 1
    g.vx, g.vy = 0.0, -120.0
    events = g.step(0.03, g.paddle_x)
    assert "cleared" in events
    assert g.levels == 1 and len(g.bricks) == g.cols * g.rows
    assert g.speed == pytest.approx(170.0 * 1.08)


def test_speed_stays_within_limits():
    g = Breakout(speed=MAX_SPEED)
    g.bricks = [g.bricks[20]]
    b = g.bricks[0]
    g.ball_x, g.ball_y = (b[0] + b[2]) / 2, b[3] + g.ball_r + 1
    g.vx, g.vy = 0.0, -120.0
    g.step(0.03, g.paddle_x)
    assert g.speed <= MAX_SPEED
    g2 = Breakout(speed=MIN_SPEED)
    g2.ball_x, g2.ball_y, g2.vx, g2.vy = 10.0, g2.height + 50, 0.0, 100.0
    g2.step(0.02, g2.width - 100)
    assert g2.speed >= MIN_SPEED


def test_the_paddle_cannot_leave_the_arena():
    g = Breakout()
    g.step(0.01, -500)
    assert g.paddle_x == pytest.approx(g.paddle_w / 2)
    g.step(0.01, 5000)
    assert g.paddle_x == pytest.approx(g.width - g.paddle_w / 2)


def test_a_fast_ball_does_not_tunnel_through_the_paddle():
    g = Breakout(speed=320.0)
    g.ball_x = g.paddle_x
    g.ball_y = g.paddle_y - 40
    g.vx, g.vy = 0.0, 320.0
    events = g.step(0.2, g.paddle_x)                # one coarse 200 ms frame
    assert "paddle" in events and "lost" not in events
