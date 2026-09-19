"""Run statistics: per-vehicle travel time and delay, per-road and per-node throughput and
queues. Attach with sim.run(..., on_step=metrics.on_step) and read summary() afterwards."""

from collections import Counter, defaultdict
from statistics import mean

from .sim import Simulation, Vehicle

STOPPED = 0.5  # m/s: at or below this a vehicle counts as queued
QUEUE_ZONE = 50.0  # metres before a node within which stopped vehicles count as its queue


class Metrics:
    def __init__(self, sim: Simulation):
        self.sim = sim
        self.t0 = sim.time
        self.road_veh_time: dict[str, float] = defaultdict(float)
        self.road_stopped_time: dict[str, float] = defaultdict(float)
        self.road_out: Counter = Counter()
        self.node_through: Counter = Counter()
        self.node_queue_time: dict[str, float] = defaultdict(float)
        self.trips: list[dict] = []

    def on_step(self, sim: Simulation) -> None:
        dt = sim.dt
        for lane in sim.all_lanes():
            road = lane.road
            n = len(lane.vehicles)
            if not n:
                continue
            self.road_veh_time[road.id] += n * dt
            stopped = [v for v in lane.vehicles if v.speed <= STOPPED]
            self.road_stopped_time[road.id] += len(stopped) * dt
            if road.dst is not None:
                q = sum(1 for v in stopped if road.length - v.position <= QUEUE_ZONE)
                self.node_queue_time[road.dst] += q * dt
        for v, frm, to in sim.transitions:
            self.road_out[frm] += 1
            dst = sim.network.roads[frm].dst
            if dst is not None:
                self.node_through[dst] += 1
            if to is None:
                self.trips.append(self._trip(v))

    def _trip(self, v: Vehicle) -> dict:
        net = self.sim.network
        free = 0.0
        for rid in v.route:
            road = net.roads[rid]
            v0 = v.model.desired_speed
            if road.speed_limit is not None:
                v0 = min(v0, road.speed_limit)
            free += road.length / v0
        travel = v.exited_at - v.entered_at
        return {
            "id": v.id,
            "origin": net.roads[v.route[0]].src,
            "destination": net.roads[v.route[-1]].dst,
            "travel_time": travel,
            "free_flow_time": free,
            "delay": travel - free,
            "distance": v.distance,
        }

    def summary(self) -> dict:
        sim = self.sim
        T = max(sim.time - self.t0, sim.dt)
        hours = T / 3600
        trips = self.trips
        totals = {
            "duration": T,
            "spawned": sum(s.spawned for s in sim.spawners),
            "exited": len(trips),
            "on_road": len(sim.vehicles),
            "pending": sum(s.pending for s in sim.spawners),
            "throughput_per_hour": len(trips) / hours,
            "mean_travel_time": mean(t["travel_time"] for t in trips) if trips else None,
            "mean_delay": mean(t["delay"] for t in trips) if trips else None,
            "mean_speed": (
                sum(t["distance"] for t in trips) / sum(t["travel_time"] for t in trips)
                if trips
                else None
            ),
        }
        roads = []
        for rid, road in sim.network.roads.items():
            veh = self.road_veh_time[rid] / T
            roads.append(
                {
                    "id": rid,
                    "throughput_per_hour": self.road_out[rid] / hours,
                    "mean_vehicles": veh,
                    "mean_stopped": self.road_stopped_time[rid] / T,
                    "density_per_km": veh / road.length * 1000,
                }
            )
        nodes = [
            {
                "id": nid,
                "control": node.control.kind if node.control else None,
                "throughput_per_hour": self.node_through[nid] / hours,
                "mean_queue": self.node_queue_time[nid] / T,
            }
            for nid, node in sim.network.nodes.items()
            if sim.network.in_roads(nid)
        ]
        return {"totals": totals, "roads": roads, "nodes": nodes, "trips": trips}
