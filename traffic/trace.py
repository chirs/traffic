"""Trace file: everything the viewer needs to replay a run. Format documented in README."""

import json
from pathlib import Path

from .sim import Simulation

VERSION = 2


class TraceWriter:
    def __init__(self, sim: Simulation, record_every: int = 1):
        self.sim = sim
        self.record_every = record_every
        self._step = 0
        self.road_index = {rid: i for i, rid in enumerate(sim.network.roads)}
        self.node_index = {nid: i for i, nid in enumerate(sim.network.nodes)}
        self.vehicles: dict[int, dict] = {}
        self.ticks: list[dict] = []
        self.record()

    def record(self) -> None:
        sim = self.sim
        rows = []
        for v in sim.vehicles.values():
            if v.id not in self.vehicles:
                self.vehicles[v.id] = {"id": v.id, "length": v.length}
            rows.append(
                [
                    v.id,
                    self.road_index[v.road],
                    v.lane,
                    round(v.position, 3),
                    round(v.speed, 3),
                    round(v.accel, 3),
                ]
            )
        rows.sort()
        tick = {"t": round(sim.time, 6), "v": rows}
        signals = self._states(dynamic=True)
        if signals:
            tick["s"] = signals
        self.ticks.append(tick)

    def _states(self, dynamic: bool) -> list:
        """[node_index, road_index, state] for every controlled approach; signals are the only
        controls whose state changes, so they go in each tick and the rest go in the header."""
        out = []
        for node in self.sim.network.nodes.values():
            if node.control is None or (node.control.kind == "signal") != dynamic:
                continue
            for road in self.sim.network.in_roads(node.id):
                out.append(
                    [
                        self.node_index[node.id],
                        self.road_index[road.id],
                        node.control.state(road.id),
                    ]
                )
        return out

    def on_step(self, sim: Simulation) -> None:
        self._step += 1
        if self._step % self.record_every == 0:
            self.record()

    def to_dict(self) -> dict:
        return {
            "version": VERSION,
            "dt": self.sim.dt * self.record_every,
            "network": self.sim.network.to_dict(),
            "static_states": self._states(dynamic=False),
            "vehicles": sorted(self.vehicles.values(), key=lambda d: d["id"]),
            "ticks": self.ticks,
        }

    def write(self, path: str | Path, js_var: str | None = None, name: str | None = None) -> None:
        """Write JSON. With js_var, write a JS file that pushes {name, trace} onto that array
        (so the viewer can bundle samples and load them over file://)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(self.to_dict(), separators=(",", ":"))
        if js_var:
            body = f"{js_var}.push({{name: {json.dumps(name or path.stem)}, trace: {body}}});\n"
        path.write_text(body)
