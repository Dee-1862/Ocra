"""Brick-break (breakout) physics. Pure logic, no drawing, no input.

Coordinates are pixels of an arena `width` x `height`, y pointing down. The
paddle's horizontal position is given to step() each frame, so the game does
not care whether it comes from tilt, a button or a test.
"""
from __future__ import annotations

import math
import random

MIN_SPEED, MAX_SPEED = 90.0, 320.0


class Breakout:
    def __init__(self, width: float = 592.0, height: float = 178.0, cols: int = 10,
                 rows: int = 3, speed: float = 170.0, paddle_w: float = 84.0, rng=None,
                 serve_delay: float = 0.0):
        self.width, self.height = width, height
        self.cols, self.rows = cols, rows
        self.speed = speed
        self.paddle_w = paddle_w
        self.paddle_h = 8.0
        self.paddle_y = height - 14.0           # centre line of the paddle
        self.paddle_x = width / 2
        self.ball_r = 5.0
        self.serve_delay = serve_delay      # seconds the ball rides the paddle before each serve
        self.serve_left = 0.0
        self.score = 0
        self.drops = 0
        self.levels = 0
        self._rng = rng or random.Random()
        self.bricks: list = []
        self._build_bricks()
        self.relaunch(angle_deg=20.0)

    def _build_bricks(self) -> None:
        margin, gap, top, bh = 10.0, 3.0, 24.0, 12.0
        bw = (self.width - 2 * margin - (self.cols - 1) * gap) / self.cols
        self.bricks = []
        for r in range(self.rows):
            for c in range(self.cols):
                x0 = margin + c * (bw + gap)
                y0 = top + r * (bh + gap)
                self.bricks.append([x0, y0, x0 + bw, y0 + bh, r])   # last item: its row

    def relaunch(self, angle_deg=None) -> None:
        """Put the ball on the paddle and send it up, a little off vertical. With a serve
        delay the ball first rides the paddle for that long, so the player can get ready."""
        a = math.radians(self._rng.uniform(-30, 30) if angle_deg is None else angle_deg)
        self.ball_x = self.paddle_x
        self.ball_y = self.paddle_y - self.paddle_h / 2 - self.ball_r - 1
        self.vx = self.speed * math.sin(a)
        self.vy = -self.speed * math.cos(a)
        self.serve_left = self.serve_delay

    def step(self, dt: float, paddle_x: float) -> list:
        """Advance by dt seconds. Returns events: "wall", "paddle", "brick",
        "lost" (ball dropped) and "cleared" (all bricks gone, next level)."""
        half = self.paddle_w / 2
        self.paddle_x = max(half, min(self.width - half, paddle_x))
        events: list = []
        if self.serve_left > 0.0:                  # waiting to serve: the ball rides the paddle
            self.serve_left = max(0.0, self.serve_left - dt)
            self.ball_x = self.paddle_x
            self.ball_y = self.paddle_y - self.paddle_h / 2 - self.ball_r - 1
            return events
        # Small sub-steps so a fast ball cannot pass through a brick or the paddle.
        n = max(1, int(math.ceil(self.speed * dt / self.ball_r)))
        for _ in range(n):
            if self._substep(dt / n, events):
                break
        return events

    def _substep(self, h: float, events: list) -> bool:
        """One small move. Returns True if the ball was relaunched."""
        r = self.ball_r
        x, y = self.ball_x + self.vx * h, self.ball_y + self.vy * h
        if x - r < 0:
            x, self.vx = r, abs(self.vx)
            events.append("wall")
        elif x + r > self.width:
            x, self.vx = self.width - r, -abs(self.vx)
            events.append("wall")
        if y - r < 0:
            y, self.vy = r, abs(self.vy)
            events.append("wall")

        top = self.paddle_y - self.paddle_h / 2
        if (self.vy > 0 and y + r >= top and y - r <= top + self.paddle_h
                and abs(x - self.paddle_x) <= self.paddle_w / 2 + r):
            offset = max(-1.0, min(1.0, (x - self.paddle_x) / (self.paddle_w / 2)))
            a = offset * math.radians(60)
            self.vx, self.vy = self.speed * math.sin(a), -self.speed * math.cos(a)
            y = top - r
            events.append("paddle")

        if y - r > self.height:                     # fell past the paddle
            self.drops += 1
            self.speed = max(MIN_SPEED, self.speed * 0.9)
            self.relaunch()
            events.append("lost")
            return True

        self.ball_x, self.ball_y = x, y
        for brick in self.bricks:
            cx = max(brick[0], min(x, brick[2]))
            cy = max(brick[1], min(y, brick[3]))
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= r * r:
                self.bricks.remove(brick)
                self.score += 1
                if abs(dx) > abs(dy):
                    self.vx = -self.vx
                else:
                    self.vy = -self.vy
                events.append("brick")
                break
        if not self.bricks:
            self.levels += 1
            self.speed = min(MAX_SPEED, self.speed * 1.08)
            self._build_bricks()
            self.relaunch()
            events.append("cleared")
            return True
        return False
