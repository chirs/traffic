"""Vehicle sources."""

import random
from dataclasses import replace

from .models import IDM
from .sim import Simulation, Vehicle

ENTRY_GAP = 12.0  # metres of clear road needed behind the last vehicle to insert a new one


def jittered_driver(base: IDM, rng: random.Random, spread: float = 0.1) -> IDM:
    """Copy of `base` with desired speed and headway varied by ±spread."""
    return replace(
        base,
        desired_speed=base.desired_speed * rng.uniform(1 - spread, 1 + spread),
        time_headway=base.time_headway * rng.uniform(1 - spread, 1 + spread),
    )


class Spawner:
    """Poisson arrivals on one road, each routed to a random destination node."""

    def __init__(
        self, road: str, rate: float, destinations: list[str], model: IDM, rng: random.Random
    ):
        self.road = road
        self.rate = rate  # vehicles per second
        self.destinations = destinations
        self.model = model
        self.rng = rng
        self.pending = 0
        self.spawned = 0

    def step(self, sim: Simulation) -> None:
        if self.rng.random() < self.rate * sim.dt:
            self.pending += 1
        road = sim.network.roads[self.road]
        while self.pending:
            lane = self._free_lane(sim, road)
            if lane is None:
                return
            _, lead_speed = sim.entry_gap(self.road, lane)
            model = jittered_driver(self.model, self.rng)
            speed = min(model.desired_speed, road.speed_limit or model.desired_speed)
            if lead_speed is not None:
                speed = min(speed, lead_speed)
            v = Vehicle(id=sim.new_id(), model=model, position=5.0, speed=speed)
            dest = self.rng.choice(self.destinations)
            tail = sim.network.shortest_path(road.dst, dest)
            if tail is None:
                self.pending -= 1
                continue
            sim.add_vehicle(v, self.road, lane, [self.road, *tail])
            self.pending -= 1
            self.spawned += 1

    def _free_lane(self, sim: Simulation, road) -> int | None:
        lanes = list(range(road.lanes))
        self.rng.shuffle(lanes)
        for lane in lanes:
            if sim.entry_gap(self.road, lane)[0] >= ENTRY_GAP:
                return lane
        return None
