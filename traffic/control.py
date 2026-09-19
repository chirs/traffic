"""Intersection control. A control decides, per approaching vehicle, whether the end of its
road is currently a stop line. States: g/y/r for signals, s for stop signs."""

COMFORT_STOP = 3.0  # m/s^2: a driver stops for yellow if they can do it within this
MOVING = 2.0  # m/s: below this a vehicle is treated as stopped for stop-line decisions


class Signal:
    """Phases cycle green -> yellow -> all-red -> next phase. Each phase is the set of road ids
    that have green. Fixed-time when min_green == max_green; otherwise actuated: green ends after
    min_green once no vehicle is within `detector` metres of the line on a green approach."""

    kind = "signal"

    def __init__(
        self,
        phases: list[set[str]],
        min_green: float = 20.0,
        max_green: float | None = None,
        yellow: float = 3.0,
        all_red: float = 1.0,
        detector: float = 30.0,
        right_on_red: bool = False,
    ):
        self.phases = [set(p) for p in phases]
        self.right_on_red = right_on_red
        self.min_green = min_green
        self.max_green = min_green if max_green is None else max_green
        self.yellow = yellow
        self.all_red = all_red
        self.detector = detector
        self.phase = 0
        self.stage = "g"
        self.stage_start = 0.0

    def update(self, sim, node) -> None:
        elapsed = sim.time - self.stage_start
        if self.stage == "g":
            done = elapsed >= self.max_green or (
                elapsed >= self.min_green and not self._demand(sim)
            )
            if done:
                self.stage, self.stage_start = "y", sim.time
        elif self.stage == "y" and elapsed >= self.yellow:
            self.stage, self.stage_start = "r", sim.time
        elif self.stage == "r" and elapsed >= self.all_red:
            self.phase = (self.phase + 1) % len(self.phases)
            self.stage, self.stage_start = "g", sim.time

    def _demand(self, sim) -> bool:
        for rid in self.phases[self.phase]:
            road = sim.network.roads[rid]
            for lane in sim.lanes[rid]:
                if lane.vehicles and road.length - lane.vehicles[-1].position <= self.detector:
                    return True
        return False

    def state(self, road_id: str) -> str:
        return self.stage if road_id in self.phases[self.phase] else "r"

    def must_stop(self, vehicle, dist: float, sim, road_id: str | None = None) -> bool:
        """Should `vehicle`, `dist` metres from the end of `road_id` (its own road by default),
        treat that end as a stop line right now?"""
        road_id = road_id or vehicle.road
        s = self.state(road_id)
        if s == "g":
            return False
        if s == "r":
            # Stopped at the line and turning right where that is allowed: may go once there
            # is a gap in the traffic bound for the same road.
            nxt = vehicle.next_road
            return not (
                self.right_on_red
                and road_id == vehicle.road
                and nxt is not None
                and vehicle.speed < 0.5
                and dist < 3.0
                and sim.network.turn(road_id, nxt) == "right"
                and sim.merge_clear(sim.network.roads[road_id].dst, nxt, vehicle)
            )
        if vehicle.speed < MOVING:
            return True
        return dist > vehicle.speed**2 / (2 * COMFORT_STOP)


class StopSign:
    """All-way stop. Vehicles that have halted at the line queue up and are released one at a
    time; the grant is held until the vehicle is clear of the node."""

    kind = "stop"
    CLEAR = 8.0  # metres past the node before the next vehicle may go
    AT_LINE = 1.5

    def __init__(self):
        self.queue: list[int] = []
        self.granted: int | None = None

    def update(self, sim, node) -> None:
        if self.granted is not None:
            v = sim.vehicles.get(self.granted)
            approaches = sim.network._in[node.id]
            if v is None or (v.road not in approaches and v.position > self.CLEAR):
                self.granted = None
        if self.granted is None and self.queue:
            self.granted = self.queue.pop(0)

    def state(self, road_id: str) -> str:
        return "s"

    def must_stop(self, vehicle, dist: float, sim, road_id: str | None = None) -> bool:
        if vehicle.id == self.granted:
            return False
        if dist < self.AT_LINE and vehicle.speed < 0.3 and vehicle.id not in self.queue:
            self.queue.append(vehicle.id)
        return True


class Priority:
    """Major roads have right of way; vehicles on minor approaches yield to any major-road
    vehicle within `gap_time` seconds (or `min_gap` metres) of the node."""

    kind = "priority"

    def __init__(self, major: set[str], gap_time: float = 4.0, min_gap: float = 12.0):
        self.major = set(major)
        self.gap_time = gap_time
        self.min_gap = min_gap

    def update(self, sim, node) -> None:
        pass

    def state(self, road_id: str) -> str:
        return "m" if road_id in self.major else "p"

    def must_stop(self, vehicle, dist: float, sim, road_id: str | None = None) -> bool:
        if (road_id or vehicle.road) in self.major:
            return False
        for rid in self.major:
            road = sim.network.roads[rid]
            for lane in sim.lanes[rid]:
                if not lane.vehicles:
                    continue
                u = lane.vehicles[-1]
                du = road.length - u.position
                if du < self.min_gap or (u.speed > 0.5 and du / u.speed < self.gap_time):
                    return True
        return False
