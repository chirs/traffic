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

    def direction(self) -> tuple[float, float]:
        (x0, y0), (x1, y1) = self.points[0], self.points[-1]
        d = math.hypot(x1 - x0, y1 - y0) or 1.0
        return (x1 - x0) / d, (y1 - y0) / d


class Network:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.roads: dict[str, Road] = {}
        self._out: dict[str, list[str]] = {}
        self._in: dict[str, list[str]] = {}

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
    ) -> Road:
        a, b = self.nodes[src], self.nodes[dst]
        dist = math.hypot(b.x - a.x, b.y - a.y) or 1.0
        ux, uy = (b.x - a.x) / dist, (b.y - a.y) / dist
        p0 = (a.x + ux * a.radius, a.y + uy * a.radius)
        p1 = (b.x - ux * b.radius, b.y - uy * b.radius)
        if length is None:
            length = max(1.0, dist - a.radius - b.radius)
        road = Road(id, length, src, dst, lanes, speed_limit, points=[p0, p1])
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
                    "points": [list(p) for p in r.points],
                }
                for r in self.roads.values()
            ],
        }
