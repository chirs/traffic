import math
from dataclasses import dataclass, field

from .models import CarFollowingModel


@dataclass
class Vehicle:
    id: int
    model: CarFollowingModel
    position: float  # front bumper, metres along the lane
    speed: float
    length: float = 5.0
    accel: float = 0.0


@dataclass
class Road:
    id: str
    length: float
    ring: bool = False


@dataclass
class Lane:
    road: Road
    vehicles: list[Vehicle] = field(default_factory=list)  # sorted by position ascending

    def sort(self) -> None:
        self.vehicles.sort(key=lambda v: v.position)

    def leader(self, i: int) -> tuple[float, float]:
        """Gap and speed of the vehicle ahead of vehicles[i]; (inf, 0) if none."""
        n = len(self.vehicles)
        v = self.vehicles[i]
        if i + 1 < n:
            lead = self.vehicles[i + 1]
            return lead.position - lead.length - v.position, lead.speed
        if self.road.ring and n > 1:
            lead = self.vehicles[0]
            return lead.position + self.road.length - lead.length - v.position, lead.speed
        return math.inf, 0.0

    def min_gap(self) -> float:
        if not self.vehicles:
            return math.inf
        return min(self.leader(i)[0] for i in range(len(self.vehicles)))


class Simulation:
    def __init__(self, road: Road, vehicles: list[Vehicle], dt: float = 0.1):
        self.road = road
        self.lane = Lane(road, list(vehicles))
        self.lane.sort()
        self.dt = dt
        self.time = 0.0
        self.exited: list[Vehicle] = []

    @property
    def vehicles(self) -> list[Vehicle]:
        return self.lane.vehicles

    def step(self) -> None:
        lane, dt = self.lane, self.dt
        for i, v in enumerate(lane.vehicles):
            gap, lead_speed = lane.leader(i)
            v.accel = v.model.acceleration(v.speed, gap, lead_speed)
        for v in lane.vehicles:
            new_speed = max(0.0, v.speed + v.accel * dt)
            v.position += 0.5 * (v.speed + new_speed) * dt
            v.speed = new_speed
        if self.road.ring:
            for v in lane.vehicles:
                if v.position >= self.road.length:
                    v.position -= self.road.length
            lane.sort()
        else:
            staying = []
            for v in lane.vehicles:
                (staying if v.position < self.road.length else self.exited).append(v)
            lane.vehicles = staying
        self.time += dt

    def run(self, duration: float, on_step=None) -> None:
        steps = round(duration / self.dt)
        for _ in range(steps):
            self.step()
            if on_step is not None:
                on_step(self)
