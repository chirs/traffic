"""Road network: nodes (intersections) joined by directed roads. Coordinates are metres, y up."""

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

DEFAULT_SPEED = 30.0
LANE_WIDTH = 3.6


@dataclass
class Node:
    id: str
    x: float
    y: float
    control: Any = None  # see control.py
    radius: float = 0.0  # half-width of the intersection box; roads stop this far from the centre


@dataclass
class Road:
    id: str
    length: float
    src: str | None = None
    dst: str | None = None
    lanes: int = 1
    speed_limit: float | None = None
    ring: bool = False
    points: list[tuple[float, float]] = field(default_factory=list)
    kind: str = ""  # OSM highway class, when imported

    def direction(self) -> tuple[float, float]:
        return _unit(self.points[0], self.points[-1])

    def start_direction(self) -> tuple[float, float]:
        return _unit(self.points[0], self.points[1])

    def end_direction(self) -> tuple[float, float]:
        return _unit(self.points[-2], self.points[-1])


def _unit(a, b) -> tuple[float, float]:
    d = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return (b[0] - a[0]) / d, (b[1] - a[1]) / d


def polyline_length(points) -> float:
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def trim_polyline(points, start_cut: float, end_cut: float) -> list[tuple[float, float]]:
    """Shorten a polyline by start_cut metres at the start and end_cut at the end."""
    pts = [tuple(p) for p in points]
    total = polyline_length(pts)
    if start_cut + end_cut >= total - 1.0:  # too short to trim: keep a 1 m stub in the middle
        mid = total / 2
        start_cut, end_cut = max(0.0, mid - 0.5), max(0.0, total - mid - 0.5)
    for cut, reverse in ((start_cut, False), (end_cut, True)):
        if cut <= 0:
            continue
        if reverse:
            pts.reverse()
        while len(pts) > 1:
            seg = math.dist(pts[0], pts[1])
            if seg > cut:
                f = cut / seg
                pts[0] = (
                    pts[0][0] + (pts[1][0] - pts[0][0]) * f,
                    pts[0][1] + (pts[1][1] - pts[0][1]) * f,
                )
                break
            cut -= seg
            pts.pop(0)
        if reverse:
            pts.reverse()
    return pts


class Network:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.roads: dict[str, Road] = {}
        self._out: dict[str, list[str]] = {}
        self._in: dict[str, list[str]] = {}
        self.geo: tuple[float, float] | None = None  # (lat, lon) of the world origin, if any
        self.speed_unit: str = "mph"  # how the viewer should display speeds: "mph" or "km/h"
        self.boundary: list[str] = []  # node ids where traffic enters and leaves

    def add_node(self, id: str, x: float, y: float, control=None, radius: float = 0.0) -> Node:
        node = Node(id, x, y, control, radius)
        self.nodes[id] = node
        self._out[id] = []
        self._in[id] = []
        return node

    def add_road(
        self,
        id: str,
        src: str,
        dst: str,
        lanes: int = 1,
        speed_limit: float | None = None,
        length: float | None = None,
        points: list[tuple[float, float]] | None = None,
        kind: str = "",
    ) -> Road:
        """Directed road from node src to node dst. points is the centreline polyline from node
        centre to node centre (default straight); it is trimmed back by each node's radius."""
        a, b = self.nodes[src], self.nodes[dst]
        raw = points or [(a.x, a.y), (b.x, b.y)]
        pts = trim_polyline(raw, a.radius, b.radius)
        if length is None:
            length = max(1.0, polyline_length(pts))
        road = Road(id, length, src, dst, lanes, speed_limit, points=pts, kind=kind)
        self.roads[id] = road
        self._out[src].append(id)
        self._in[dst].append(id)
        return road

    def add_ring(self, id: str, length: float, lanes: int = 1) -> Road:
        road = Road(id, length, lanes=lanes, ring=True)
        self.roads[id] = road
        return road

    def out_roads(self, node_id: str) -> list[Road]:
        return [self.roads[r] for r in self._out[node_id]]

    def in_roads(self, node_id: str) -> list[Road]:
        return [self.roads[r] for r in self._in[node_id]]

    def turn(self, from_id: str, to_id: str) -> str:
        """left, right, straight or uturn, from the heading change between the two roads."""
        d1, d2 = self.roads[from_id].end_direction(), self.roads[to_id].start_direction()
        angle = math.degrees(
            math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
        )
        if abs(angle) < 30:
            return "straight"
        if abs(angle) > 150:
            return "uturn"
        return "left" if angle > 0 else "right"

    def travel_time(self, road: Road) -> float:
        return road.length / (road.speed_limit or DEFAULT_SPEED)

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        """Road ids from node src to node dst minimising free-flow travel time; [] if src == dst."""
        best = {src: 0.0}
        prev: dict[str, str] = {}
        heap = [(0.0, src)]
        while heap:
            cost, node = heapq.heappop(heap)
            if node == dst:
                break
            if cost > best.get(node, math.inf):
                continue
            for road in self.out_roads(node):
                c = cost + self.travel_time(road)
                if c < best.get(road.dst, math.inf):
                    best[road.dst] = c
                    prev[road.dst] = road.id
                    heapq.heappush(heap, (c, road.dst))
        if dst not in best:
            return None
        path = []
        node = dst
        while node != src:
            rid = prev[node]
            path.append(rid)
            node = self.roads[rid].src
        return path[::-1]

    def to_dict(self) -> dict:
        return {
            "geo": {"lat": self.geo[0], "lon": self.geo[1]} if self.geo else None,
            "units": self.speed_unit,
            "nodes": [
                {
                    "id": n.id,
                    "x": n.x,
                    "y": n.y,
                    "radius": n.radius,
                    "control": n.control.kind if n.control else None,
                }
                for n in self.nodes.values()
            ],
            "roads": [
                {
                    "id": r.id,
                    "src": r.src,
                    "dst": r.dst,
                    "length": r.length,
                    "lanes": r.lanes,
                    "ring": r.ring,
                    "kind": r.kind,
                    "points": [[round(p[0], 2), round(p[1], 2)] for p in r.points],
                }
                for r in self.roads.values()
            ],
        }
