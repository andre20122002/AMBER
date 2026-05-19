"""PoseTracker: обгортає PoseDetector з One-Euro smoothing + hold-last-good.

One-Euro filter — стандарт для real-time pose smoothing. При повільних рухах
сильно згладжує (стабільність), при швидких — менше (responsiveness).
Reference: https://gery.casiez.net/1euro/
"""
import logging
import math
import time
from dataclasses import replace

import numpy as np

import config
from pose import PoseDetector, PoseResult

logger = logging.getLogger(__name__)


class OneEuroFilter:
    """Адаптивний low-pass filter. Один екземпляр на одну скалярну координату."""

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev: float | None = None

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, t: float) -> float:
        if self._x_prev is None or self._t_prev is None:
            self._x_prev = x
            self._t_prev = t
            return x
        dt = max(t - self._t_prev, 1e-6)

        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


_LANDMARKS = ("left_shoulder", "right_shoulder", "head", "hips_center")


class PoseTracker:
    """Stateful wrapper: PoseDetector → smoothing → hold-last-good."""

    def __init__(
        self,
        detector: PoseDetector,
        hold_frames: int | None = None,
        min_cutoff: float | None = None,
        beta: float | None = None,
    ):
        self.detector = detector
        self.hold_frames = hold_frames if hold_frames is not None else config.POSE_HOLD_FRAMES
        mc = min_cutoff if min_cutoff is not None else config.POSE_SMOOTH_MIN_CUTOFF
        bt = beta if beta is not None else config.POSE_SMOOTH_BETA

        # Один filter на кожну координату (x, y) кожного landmark
        self._filters: dict[str, tuple[OneEuroFilter, OneEuroFilter]] = {
            name: (OneEuroFilter(mc, bt), OneEuroFilter(mc, bt)) for name in _LANDMARKS
        }
        self._last_good: PoseResult | None = None
        self._frames_since_good = 0

    def reset(self) -> None:
        for fx, fy in self._filters.values():
            fx.reset()
            fy.reset()
        self._last_good = None
        self._frames_since_good = 0

    def update(self, frame_bgr: np.ndarray) -> PoseResult | None:
        raw = self.detector.detect(frame_bgr)
        t = time.monotonic()

        if raw is None:
            # Hold last-good з confidence fade
            self._frames_since_good += 1
            if self._last_good is None or self._frames_since_good > self.hold_frames:
                return None
            fade = 1.0 - (self._frames_since_good / self.hold_frames)
            return replace(
                self._last_good,
                confidence=self._last_good.confidence * fade,
                source="hold",
            )

        # Зміна джерела (full ↔ face) → reset filters щоб не "тягнули" стару позицію
        if self._last_good is not None and self._last_good.source != raw.source:
            for fx, fy in self._filters.values():
                fx.reset()
                fy.reset()

        smoothed = self._smooth(raw, t)
        self._last_good = smoothed
        self._frames_since_good = 0
        return smoothed

    def _smooth(self, pose: PoseResult, t: float) -> PoseResult:
        new_values: dict[str, tuple[float, float]] = {}
        for name in _LANDMARKS:
            x, y = getattr(pose, name)
            fx, fy = self._filters[name]
            new_values[name] = (fx.filter(x, t), fy.filter(y, t))
        return replace(pose, **new_values)
