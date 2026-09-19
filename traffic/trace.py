"""Trace file: everything the viewer needs to replay a run. Format documented in README."""

import json
from pathlib import Path

from .sim import Simulation

VERSION = 1


class TraceWriter:
    def __init__(self, sim: Simulation, record_every: int = 1):
        self.sim = sim
        self.record_every = record_every
        self._step = 0
        self.vehicles = {v.id: {"id": v.id, "length": v.length} for v in sim.vehicles}
        self.ticks: list[dict] = []
        self.record()

    def record(self) -> None:
        sim = self.sim
        self.ticks.append(
            {
                "t": round(sim.time, 6),
                "v": [
                    [v.id, 0, round(v.position, 3), round(v.speed, 3), round(v.accel, 3)]
                    for v in sim.vehicles
                ],
            }
        )

    def on_step(self, sim: Simulation) -> None:
        self._step += 1
        if self._step % self.record_every == 0:
            self.record()

    def to_dict(self) -> dict:
        road = self.sim.road
        return {
            "version": VERSION,
            "dt": self.sim.dt * self.record_every,
            "network": {"roads": [{"id": road.id, "length": road.length, "ring": road.ring}]},
            "vehicles": list(self.vehicles.values()),
            "ticks": self.ticks,
        }

    def write(self, path: str | Path, js_var: str | None = None) -> None:
        """Write JSON, or a JS file assigning the JSON to `js_var` (for loading over file://)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(self.to_dict(), separators=(",", ":"))
        if js_var:
            body = f"const {js_var} = {body};\n"
        path.write_text(body)
