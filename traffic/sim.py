import math
import random
from bisect import bisect_right
from dataclasses import dataclass, field

from .models import CarFollowingModel
from .network import Network, Road

# Lane-change (MOBIL-style) parameters
B_SAFE = 4.0  # max deceleration imposed on anyone by a lane change, m/s^2
POLITENESS = 0.3
A_THRESHOLD = 0.2  # m/s^2 of net gain needed to bother changing
LC_COOLDOWN = 3.0  # seconds between lane changes by one vehicle
LC_KEEP_OUT = 20.0  # no lane changes within this many metres of a road's end
MAX_DECEL = 9.0  # m/s^2: physical braking limit
STOP_MARGIN = 1.0  # metres short of a stop line that vehicles aim to halt (IDM creeps otherwise)


@dataclass
class Vehicle:
    id: int
    model: CarFollowingModel
    position: float  # front bumper, metres along the road
    speed: float
    length: float = 5.0
    accel: float = 0.0
    road: str = ""
    lane: int = 0
    route: list[str] = field(default_factory=list)  # road ids, starting with the current one
    route_index: int = 0
    lc_timer: float = 0.0
    entered_at: float = 0.0
    exited_at: float | None = None
    distance: float = 0.0  # metres driven since entering

    @property
    def next_road(self) -> str | None:
        i = self.route_index + 1
        return self.route[i] if i < len(self.route) else None


@dataclass(eq=False)
class Lane:
    road: Road
    index: int
    vehicles: list[Vehicle] = field(default_factory=list)  # sorted by position ascending

    def sort(self) -> None:
        self.vehicles.sort(key=lambda v: v.position)

    def leader(self, i: int) -> tuple[float, float]:
        """Gap and speed of the vehicle ahead of vehicles[i] in this lane; (inf, 0) if none."""
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
    def __init__(self, network: Network, dt: float = 0.1, seed: int = 0):
        self.network = network
        self.dt = dt
        self.time = 0.0
        self.rng = random.Random(seed)
        self.lanes: dict[str, list[Lane]] = {
            rid: [Lane(road, i) for i in range(road.lanes)] for rid, road in network.roads.items()
        }
        self.vehicles: dict[int, Vehicle] = {}
        self.exited: list[Vehicle] = []
        self.spawners: list = []
        self.transitions: list[tuple[Vehicle, str, str | None]] = []  # last step's road changes
        self._next_id = 0
        self._pending: dict[str, list] = {}

    # ---- population -----------------------------------------------------------------------
    def new_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def add_vehicle(self, v: Vehicle, road: str, lane: int = 0, route: list[str] | None = None):
        v.road, v.lane = road, lane
        v.route = route if route is not None else [road]
        v.route_index = 0
        v.entered_at = self.time
        self.vehicles[v.id] = v
        self.lanes[road][lane].vehicles.append(v)
        self.lanes[road][lane].sort()
        self._next_id = max(self._next_id, v.id + 1)

    def entry_gap(self, road: str, lane: int) -> tuple[float, float | None]:
        """Free metres behind the last vehicle at the start of a lane, and that vehicle's speed."""
        vs = self.lanes[road][lane].vehicles
        if not vs:
            return math.inf, None
        return vs[0].position - vs[0].length, vs[0].speed

    def all_lanes(self):
        for lanes in self.lanes.values():
            yield from lanes

    def min_gap(self) -> float:
        return min((lane.min_gap() for lane in self.all_lanes()), default=math.inf)

    # ---- stepping -------------------------------------------------------------------------
    def step(self) -> None:
        dt = self.dt
        for node in self.network.nodes.values():
            if node.control is not None:
                node.control.update(self, node)
        self._pending = self._collect_pending()
        self._lane_changes()
        self._pending = self._collect_pending()
        for lane in self.all_lanes():
            for i, v in enumerate(lane.vehicles):
                gap, lead_speed = self._leader(v, lane, i)
                a = v.model.acceleration(v.speed, gap, lead_speed, self._v0(v, lane.road))
                v.accel = max(a, -MAX_DECEL)
        for v in self.vehicles.values():
            new_speed = max(0.0, v.speed + v.accel * dt)
            moved = 0.5 * (v.speed + new_speed) * dt
            v.position += moved
            v.distance += moved
            v.speed = new_speed
            v.lc_timer -= dt
        self._transitions()
        for spawner in self.spawners:
            spawner.step(self)
        self.time += dt

    def run(self, duration: float, on_step=None) -> None:
        for _ in range(round(duration / self.dt)):
            self.step()
            if on_step is not None:
                on_step(self)

    @staticmethod
    def _v0(v: Vehicle, road: Road) -> float:
        if road.speed_limit is None:
            return v.model.desired_speed
        return min(v.model.desired_speed, road.speed_limit)

    def _collect_pending(self) -> dict[str, list]:
        """Per node: the lane-leading vehicles approaching it, with distance and target lane."""
        pending: dict[str, list] = {}
        for lane in self.all_lanes():
            road = lane.road
            if road.ring or not lane.vehicles or road.dst is None:
                continue
            v = lane.vehicles[-1]
            nxt = v.next_road
            target = min(v.lane, self.network.roads[nxt].lanes - 1) if nxt else None
            pending.setdefault(road.dst, []).append((v, road.length - v.position, nxt, target))
        return pending

    def _leader(self, v: Vehicle, lane: Lane, i: int) -> tuple[float, float]:
        gap, lead_speed = lane.leader(i)
        if gap != math.inf or lane.road.ring:
            return gap, lead_speed
        return self._downstream(v, lane.road, lane.index)

    def _downstream(self, v: Vehicle, road: Road, lane_index: int) -> tuple[float, float]:
        """Leader seen past the end of `road` from `lane_index`: first vehicle on the next road,
        a competing entrant from another approach, or the stop line if the control says stop."""
        dist = road.length - v.position
        nxt = v.next_road
        best_gap, best_speed = math.inf, 0.0
        control = self.network.nodes[road.dst].control if road.dst else None
        if control is not None and control.must_stop(v, dist, self):
            best_gap = dist + v.model.min_gap - STOP_MARGIN
        if nxt is not None:
            nroad = self.network.roads[nxt]
            target = min(lane_index, nroad.lanes - 1)
            vs = self.lanes[nxt][target].vehicles
            if vs:
                lead = vs[0]
                g = dist + lead.position - lead.length
                if g < best_gap:
                    best_gap, best_speed = g, lead.speed
            # Competing entrants from other approaches heading into the same lane: whoever is
            # closer to the node goes first. Entrants held at their own stop line don't count.
            for u, du, unxt, utarget in self._pending.get(road.dst, ()):
                if u is v or unxt != nxt or utarget != target:
                    continue
                if du > dist or (du == dist and u.id > v.id):
                    continue
                if control is not None and control.must_stop(u, du, self):
                    continue
                g = dist - du - u.length
                if g < best_gap:
                    best_gap, best_speed = g, u.speed
        return best_gap, best_speed

    def _lane_changes(self) -> None:
        for rid, lanes in self.lanes.items():
            road = self.network.roads[rid]
            if road.lanes < 2:
                continue
            for lane in lanes:
                for v in list(lane.vehicles):
                    if v.lc_timer > 0 or road.length - v.position < LC_KEEP_OUT:
                        continue
                    if v.position < v.length:
                        continue
                    best, best_target = A_THRESHOLD, None
                    for target in (v.lane - 1, v.lane + 1):
                        if not 0 <= target < road.lanes:
                            continue
                        gain = self._lane_change_gain(v, road, lanes[target])
                        if gain is not None and gain > best:
                            best, best_target = gain, target
                    if best_target is not None:
                        lane.vehicles.remove(v)
                        v.lane = best_target
                        v.lc_timer = LC_COOLDOWN
                        lanes[best_target].vehicles.append(v)
                        lanes[best_target].sort()

    def _lane_change_gain(self, v: Vehicle, road: Road, target: Lane) -> float | None:
        """MOBIL incentive for v moving into `target`, or None if unsafe."""
        positions = [u.position for u in target.vehicles]
        j = bisect_right(positions, v.position)
        v0 = self._v0(v, road)
        if j < len(target.vehicles):
            lead = target.vehicles[j]
            gap, lead_speed = lead.position - lead.length - v.position, lead.speed
        else:
            gap, lead_speed = self._downstream(v, road, target.index)
        if gap < 0:
            return None
        a_new = v.model.acceleration(v.speed, gap, lead_speed, v0)
        if a_new < -B_SAFE:
            return None
        follower_cost = 0.0
        if j > 0:
            f = target.vehicles[j - 1]
            fgap = v.position - v.length - f.position
            if fgap < 0:
                return None
            a_f = f.model.acceleration(f.speed, fgap, v.speed, self._v0(f, road))
            if a_f < -B_SAFE:
                return None
            follower_cost = f.accel - a_f
        return a_new - v.accel - POLITENESS * follower_cost

    def _transitions(self) -> None:
        self.transitions = []
        touched: set[Lane] = set()
        for lane in self.all_lanes():
            road = lane.road
            if road.ring:
                for v in lane.vehicles:
                    if v.position >= road.length:
                        v.position -= road.length
                touched.add(lane)
                continue
            staying = []
            for v in lane.vehicles:
                if v.position < road.length:
                    staying.append(v)
                    continue
                nxt = v.next_road
                self.transitions.append((v, road.id, nxt))
                if nxt is None:
                    v.exited_at = self.time + self.dt
                    del self.vehicles[v.id]
                    self.exited.append(v)
                    continue
                v.position -= road.length
                v.route_index += 1
                v.road = nxt
                v.lane = min(v.lane, self.network.roads[nxt].lanes - 1)
                new_lane = self.lanes[nxt][v.lane]
                new_lane.vehicles.append(v)
                touched.add(new_lane)
            lane.vehicles = staying
        for lane in touched:
            lane.sort()
