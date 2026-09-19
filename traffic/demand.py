"""Vehicle sources: origin-destination demand realised as Poisson arrivals."""

import random
from collections import defaultdict
from dataclasses import replace

from .models import IDM
from .sim import Simulation, Vehicle

ENTRY_GAP = 12.0  # metres of clear road needed behind the last vehicle to insert a new one

Demand = dict[tuple[str, str], float]  # (origin node, destination node) -> vehicles per second


def uniform_demand(nodes: list[str], rate: float) -> Demand:
    """Every node sends `rate` veh/s in total, spread evenly over all the other nodes."""
    n = len(nodes) - 1
    return {(o, d): rate / n for o in nodes for d in nodes if o != d}


def jittered_driver(base: IDM, rng: random.Random, spread: float = 0.1) -> IDM:
    """Copy of `base` with desired speed and headway varied by ±spread."""
    return replace(
        base,
        desired_speed=base.desired_speed * rng.uniform(1 - spread, 1 + spread),
        time_headway=base.time_headway * rng.uniform(1 - spread, 1 + spread),
    )


class Spawner:
    """Poisson arrivals at one origin node. Each vehicle draws a destination by weight and
    enters on the first road of its shortest path."""

    def __init__(
        self,
        origin: str,
        rate: float,
        destinations: dict[str, float],
        model: IDM,
        rng: random.Random,
    ):
        self.origin = origin
        self.rate = rate  # vehicles per second
        self.dests = list(destinations)
        self.weights = list(destinations.values())
        self.model = model
        self.rng = rng
        self.queue: list[str] = []  # destinations of arrivals waiting for room to enter
        self.spawned = 0

    @property
    def pending(self) -> int:
        return len(self.queue)

    @classmethod
    def from_demand(cls, demand: Demand, model: IDM, rng: random.Random) -> list["Spawner"]:
        by_origin: dict[str, dict[str, float]] = defaultdict(dict)
        for (o, d), rate in demand.items():
            if rate > 0:
                by_origin[o][d] = rate
        return [cls(o, sum(ds.values()), ds, model, rng) for o, ds in by_origin.items()]

    def step(self, sim: Simulation) -> None:
        if self.rng.random() < self.rate * sim.dt:
            self.queue.append(self.rng.choices(self.dests, self.weights)[0])
        while self.queue:
            route = sim.network.shortest_path(self.origin, self.queue[0])
            if not route:
                self.queue.pop(0)
                continue
            road = sim.network.roads[route[0]]
            lane = self._free_lane(sim, road)
            if lane is None:
                return
            self.queue.pop(0)
            _, lead_speed = sim.entry_gap(road.id, lane)
            model = jittered_driver(self.model, self.rng)
            speed = min(model.desired_speed, road.speed_limit or model.desired_speed)
            if lead_speed is not None:
                speed = min(speed, lead_speed)
            v = Vehicle(id=sim.new_id(), model=model, position=5.0, speed=speed)
            sim.add_vehicle(v, road.id, lane, route)
            self.spawned += 1

    def _free_lane(self, sim: Simulation, road) -> int | None:
        lanes = list(range(road.lanes))
        self.rng.shuffle(lanes)
        for lane in lanes:
            if sim.entry_gap(road.id, lane)[0] >= ENTRY_GAP:
                return lane
        return None
