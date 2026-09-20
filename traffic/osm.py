"""Build a Network from an OpenStreetMap extract (Overpass JSON). Ways are split at shared
nodes into intersection-to-intersection roads; two-way ways become two roads. Coordinates are
projected to metres around the extract's centre, x east and y north."""

import json
import math
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from .control import Priority, Signal, StopSign
from .network import LANE_WIDTH, Network
from .rules import CLASSES, Rules, class_rank

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "traffic-sim/0.1 (github.com/chirs/traffic)"
EARTH_R = 6371008.8
BOUNDARY_MARGIN = 40.0  # metres inside the bbox edge within which a dead end counts as an exit
CLIP_MARGIN = 0.0003  # degrees (~30 m) of slack when clipping ways to the bbox

BBox = tuple[float, float, float, float]  # south, west, north, east
Polygon = list[tuple[float, float]]  # (lat, lon) vertices


def point_in_polygon(lat: float, lon: float, poly: Polygon) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (y0, x0), (y1, x1) = poly[i], poly[(i + 1) % n]
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def dist_to_edges(x: float, y: float, ring: list[tuple[float, float]]) -> float:
    """Distance from (x, y) to the nearest edge of a closed ring of projected points."""
    best = math.inf
    n = len(ring)
    for i in range(n):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        t = (
            0.0
            if dx == dy == 0
            else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        )
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def overpass_query(bbox: BBox) -> str:
    classes = "|".join(CLASSES + [c + "_link" for c in CLASSES[:5]])
    s, w, n, e = bbox
    return (
        f'[out:json][timeout:120];(way["highway"~"^({classes})$"]({s},{w},{n},{e}););'
        "out body;>;out skel qt;"
    )


def fetch(bbox: BBox, cache: str | Path, url: str = OVERPASS_URL) -> dict:
    """Overpass JSON for bbox, read from `cache` if present, else downloaded and saved there."""
    cache = Path(cache)
    if cache.exists():
        return json.loads(cache.read_text())
    data = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return json.loads(body)


class Projection:
    """Local equirectangular projection: metres east/north of (lat0, lon0)."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = EARTH_R * math.cos(math.radians(lat0)) * math.pi / 180
        self.ky = EARTH_R * math.pi / 180

    def __call__(self, lat: float, lon: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky


def _lanes(tags: dict, rules: Rules, kind: str, oneway: bool) -> tuple[int, int]:
    """(forward, backward) lanes."""
    default = rules.lanes_for(kind)

    def num(key):
        try:
            return max(1, int(float(tags[key])))
        except (KeyError, ValueError):
            return None

    total, fwd, bwd = num("lanes"), num("lanes:forward"), num("lanes:backward")
    if oneway:
        return (fwd or total or default, 0)
    if fwd and bwd:
        return fwd, bwd
    if total:
        half = max(1, total // 2)
        return (fwd or half, bwd or max(1, total - (fwd or half)))
    return (fwd or default, bwd or default)


def build_network(
    osm: dict, rules: Rules, bbox: BBox | None = None, clip: Polygon | None = None
) -> Network:
    """clip, if given, is a (lat, lon) polygon inside bbox: only ways inside it are kept and
    traffic enters and leaves at dead ends near its edge instead of the bbox's."""
    elements = osm["elements"]
    coords = {e["id"]: (e["lat"], e["lon"]) for e in elements if e["type"] == "node"}
    node_tags = {e["id"]: e.get("tags", {}) for e in elements if e["type"] == "node"}
    ways = [
        e
        for e in elements
        if e["type"] == "way"
        and e.get("tags", {}).get("highway", "").removesuffix("_link") in CLASSES
        and len(e["nodes"]) >= 2
        and all(n in coords for n in e["nodes"])
    ]
    if clip:
        ways = clip_ways(ways, coords, bbox, clip)
    elif bbox:
        ways = clip_ways(ways, coords, bbox)

    if bbox:
        lat0, lon0 = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    else:
        lat0 = sum(c[0] for c in coords.values()) / len(coords)
        lon0 = sum(c[1] for c in coords.values()) / len(coords)
    proj = Projection(lat0, lon0)

    usage = Counter()
    for w in ways:
        usage.update(w["nodes"])
        usage[w["nodes"][0]] += 1  # endpoints always split
        usage[w["nodes"][-1]] += 1
    junction = {n for n, c in usage.items() if c >= 2}

    net = Network()
    net.geo = (lat0, lon0)
    net.speed_unit = rules.speed_unit
    width_at: dict[int, float] = defaultdict(
        float
    )  # carriageway width of the widest road at a node
    segments = []  # (way, index within way, node ids of one intersection-to-intersection piece)
    for w in ways:
        nds = w["nodes"]
        start, j = 0, 0
        for i in range(1, len(nds)):
            if nds[i] in junction or i == len(nds) - 1:
                segments.append((w, j, nds[start : i + 1]))
                start, j = i, j + 1
    for w, _, nds in segments:
        tags = w["tags"]
        kind = tags["highway"]
        oneway = tags.get("oneway") in ("yes", "1", "true") or kind.startswith("motorway")
        fwd, bwd = _lanes(tags, rules, kind, oneway)
        width = (fwd + bwd) * LANE_WIDTH
        width_at[nds[0]] = max(width_at[nds[0]], width)
        width_at[nds[-1]] = max(width_at[nds[-1]], width)

    def node_id(n: int) -> str:
        return f"n{n}"

    for n in {s[2][0] for s in segments} | {s[2][-1] for s in segments}:
        x, y = proj(*coords[n])
        net.add_node(node_id(n), x, y, radius=width_at[n] / 2)

    stop_ends: set[str] = set()  # node ids with a stop sign on some approach
    for w, j, nds in segments:
        tags = w["tags"]
        kind = tags["highway"]
        oneway = tags.get("oneway") in ("yes", "1", "true") or kind.startswith("motorway")
        fwd, bwd = _lanes(tags, rules, kind, oneway)
        speed = rules.parse_maxspeed(tags.get("maxspeed")) or rules.speed_for(kind)
        pts = [proj(*coords[n]) for n in nds]
        a, b = node_id(nds[0]), node_id(nds[-1])
        if a == b:
            continue  # loop back onto itself: skip
        base = f"w{w['id']}.{j}"
        net.add_road(base, a, b, lanes=fwd, speed_limit=speed, points=pts, kind=kind)
        if bwd:
            net.add_road(
                base + "r", b, a, lanes=bwd, speed_limit=speed, points=pts[::-1], kind=kind
            )
        interior = nds[1:-1] if len(nds) > 2 else []
        if any(node_tags.get(n, {}).get("highway") == "stop" for n in interior + [nds[0]]):
            stop_ends.add(b)
            if bwd and any(node_tags.get(n, {}).get("highway") == "stop" for n in interior):
                stop_ends.add(a)

    for nid, node in net.nodes.items():
        approaches = net.in_roads(nid)
        if len(approaches) < 2:
            continue
        osm_tags = node_tags.get(int(nid[1:]), {})
        phases = signal_phases(approaches)
        inferred = False
        if rules.infer_signals_major_class is not None and len(phases) == 2:
            by_id = {r.id: r for r in approaches}
            axis_rank = sorted(max(class_rank(by_id[rid].kind) for rid in ph) for ph in phases)
            inferred = axis_rank[1] >= class_rank(rules.infer_signals_major_class) and axis_rank[
                0
            ] >= class_rank(rules.infer_signals_minor_class)
        if osm_tags.get("highway") == "traffic_signals" or inferred:
            node.control = Signal(
                phases,
                min_green=rules.signal_min_green,
                max_green=rules.signal_max_green,
                right_on_red=rules.right_on_red,
            )
        elif nid in stop_ends or osm_tags.get("highway") == "stop":
            node.control = StopSign()
        else:
            top = max(class_rank(r.kind) for r in approaches)
            major = {r.id for r in approaches if class_rank(r.kind) == top}
            if len(major) < len(approaches):
                node.control = Priority(major)
            elif len(approaches) >= 3:
                node.control = StopSign()

    if clip or bbox:
        if clip:
            ring = [proj(lat, lon) for lat, lon in clip]
        else:
            s, w, n, e = bbox
            ring = [proj(s, w), proj(s, e), proj(n, e), proj(n, w)]
        for nid, node in net.nodes.items():
            degree = len(net.in_roads(nid)) + len(net.out_roads(nid))
            if 1 <= degree <= 2 and dist_to_edges(node.x, node.y, ring) < BOUNDARY_MARGIN:
                net.boundary.append(nid)
    return net


def clip_ways(
    ways: list[dict], coords: dict, bbox: BBox, clip: Polygon | None = None
) -> list[dict]:
    """Overpass returns whole ways that touch the bbox; keep only the runs of nodes inside the
    bbox (plus a little slack) or, if given, the clip polygon, each run as its own way. Runs
    shorter than two nodes are dropped."""
    s, w, n, e = bbox
    s, w, n, e = s - CLIP_MARGIN, w - CLIP_MARGIN, n + CLIP_MARGIN, e + CLIP_MARGIN

    def inside(nid):
        lat, lon = coords[nid]
        if clip:
            return point_in_polygon(lat, lon, clip)
        return s <= lat <= n and w <= lon <= e

    out = []
    for way in ways:
        run, piece = [], 0
        for nid in way["nodes"] + [None]:
            if nid is not None and inside(nid):
                run.append(nid)
                continue
            if len(run) >= 2:
                out.append(
                    {**way, "id": way["id"] if piece == 0 else f"{way['id']}p{piece}", "nodes": run}
                )
                piece += 1
            run = []
    return out


def signal_phases(approaches) -> list[set[str]]:
    """Two phases by bearing: approaches within 45 degrees of the widest approach's axis, and
    the rest. One phase if every approach shares the axis."""
    ref = max(approaches, key=lambda r: r.lanes)
    rx, ry = ref.end_direction()
    ref_axis = math.degrees(math.atan2(ry, rx)) % 180
    same, other = set(), set()
    for r in approaches:
        dx, dy = r.end_direction()
        axis = math.degrees(math.atan2(dy, dx)) % 180
        diff = abs(axis - ref_axis)
        diff = min(diff, 180 - diff)
        (same if diff < 45 else other).add(r.id)
    return [same, other] if other else [same]


def boundary_weights(net: Network) -> dict[str, float]:
    """Relative traffic weight of each boundary node: lanes times class importance of its road."""
    weights = {}
    for nid in net.boundary:
        roads = net.in_roads(nid) + net.out_roads(nid)
        weights[nid] = max(r.lanes * class_rank(r.kind) for r in roads)
    return weights
