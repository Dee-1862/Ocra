"""Camera + IMU wrist-angle fusion.

The camera is accurate but drops out (occlusion, odd hand shapes -- the
failure Afyouni et al. saw with Leap Motion). The IMU never drops out but its
absolute angle drifts. So: trust the camera when it is there, and while it is,
learn the IMU's current offset; when the camera is gone, report the IMU plus
that last-learned offset.

The source is always reported, so the UI can show "IMU only" and the logs can
separate the two when the ablation (Page 8, Test 2) is computed.
"""
from __future__ import annotations

from dataclasses import dataclass

CAMERA = "camera"
FUSED = "fused"
IMU_ONLY = "imu-only"
NONE = "none"


@dataclass
class Estimate:
    angle: float | None
    source: str


class WristFuser:
    def __init__(self, offset_alpha: float = 0.05, max_imu_only_s: float = 30.0):
        """offset_alpha: how fast the IMU offset tracks (per camera sample).
        max_imu_only_s: after this long without the camera, stop reporting an
        angle -- IMU drift makes a long-extrapolated value untrustworthy."""
        self.offset_alpha = offset_alpha
        self.max_imu_only_s = max_imu_only_s
        self._offset: float | None = None
        self._last_cam_t: float | None = None

    def update(self, t: float, cam: float | None, imu: float | None) -> Estimate:
        if cam is not None:
            self._last_cam_t = t
            if imu is None:
                return Estimate(cam, CAMERA)
            err = cam - imu
            if self._offset is None:
                self._offset = err
            else:
                self._offset += self.offset_alpha * (err - self._offset)
            return Estimate(cam, FUSED)

        if imu is not None and self._offset is not None:
            if self._last_cam_t is not None and t - self._last_cam_t <= self.max_imu_only_s:
                return Estimate(imu + self._offset, IMU_ONLY)
        return Estimate(None, NONE)
