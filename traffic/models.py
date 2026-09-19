"""Car-following models. Each maps (own speed, gap to leader, leader speed) to an acceleration."""

import math
from dataclasses import dataclass
from typing import Protocol


class CarFollowingModel(Protocol):
    desired_speed: float

    def acceleration(self, speed: float, gap: float, leader_speed: float) -> float:
        """Return acceleration in m/s^2. gap is bumper-to-bumper; math.inf means free road."""
        ...


@dataclass(frozen=True)
class IDM:
    """Intelligent Driver Model (Treiber, Hennecke, Helbing 2000). SI units."""

    desired_speed: float = 30.0
    time_headway: float = 1.5
    min_gap: float = 2.0
    max_accel: float = 1.0
    comfort_decel: float = 1.5
    delta: float = 4.0

    def acceleration(self, speed: float, gap: float, leader_speed: float) -> float:
        dv = speed - leader_speed
        dynamic = speed * self.time_headway + speed * dv / (
            2 * math.sqrt(self.max_accel * self.comfort_decel)
        )
        s_star = self.min_gap + max(0.0, dynamic)
        gap = max(gap, 0.01)
        return self.max_accel * (
            1 - (speed / self.desired_speed) ** self.delta - (s_star / gap) ** 2
        )
