import math

import pytest

from traffic.control import Priority, Signal, StopSign
from traffic.models import IDM
from traffic.network import Network, trim_polyline
from traffic.osm import build_network, signal_phases
from traffic.rules import DALLAS, NETHERLANDS, NEW_YORK, class_rank
from traffic.sim import Simulation, Vehicle

LAT, LON = 32.75, -96.83
DLAT = 0.001  # ~111 m
DLON = 0.001 / math.cos(math.radians(LAT))  # ~111 m too


def node(i, dlat, dlon, tags=None):
    e = {"type": "node", "id": i, "lat": LAT + dlat * DLAT, "lon": LON + dlon * DLON}
    if tags:
        e["tags"] = tags
    return e


def way(i, nodes, **tags):
    return {"type": "way", "id": i, "nodes": nodes, "tags": tags}


# A signalised crossing at node 2 (primary E-W oneway x residential N-S), a T where the
# residential meets a secondary at node 6, and a stop-controlled crossing at node 9.
#
#        3            8
#        |            |
#  1 --- 2 --- 5      |
#        |            |
#        4 --- 6 ---- 9 --- 10
#              |      |
#              7      11
OSM = {
    "elements": [
        node(1, 0, -1),
        node(2, 0, 0, {"highway": "traffic_signals"}),
        node(5, 0, 1),
        node(3, 1, 0),
        node(4, -1, 0),
        node(6, -1, 1),
        node(7, -2, 1),
        node(8, 1, 3),
        node(9, -1, 3),
        node(10, -1, 4),
        node(11, -2, 3),
        node(12, -1.2, 3, {"highway": "stop"}),  # on way 105 just north of node 9
        way(101, [1, 2, 5], highway="primary", oneway="yes", maxspeed="35 mph", lanes="2"),
        way(102, [3, 2, 4], highway="residential"),
        way(103, [4, 6, 9, 10], highway="secondary", lanes="4"),
        way(104, [6, 7], highway="residential"),
        way(105, [8, 9, 12, 11], highway="residential"),
    ]
}
BBOX = (LAT - 2.2 * DLAT, LON - 1.2 * DLON, LAT + 1.2 * DLAT, LON + 4.2 * DLON)


@pytest.fixture
def net():
    return build_network(OSM, DALLAS, BBOX)


def test_ways_split_at_junctions_and_directions(net):
    ids = set(net.roads)
    assert "w101.0" in ids and "w101.0r" not in ids, "oneway primary has no reverse road"
    assert "w102.1r" in ids, "two-way residential has both directions"
    assert net.roads["w101.0"].lanes == 2
    assert net.roads["w101.0"].speed_limit == pytest.approx(35 * 0.44704)
    assert net.roads["w102.1"].speed_limit == pytest.approx(30 * 0.44704), "Dallas default"
    assert net.roads["w103.0"].lanes == 2, "4 lanes total -> 2 per direction"
    assert net.roads["w103.0"].kind == "secondary"
    assert net.roads["w102.0"].src == "n3" and net.roads["w102.0"].dst == "n2"
    assert 100 < net.roads["w102.0"].length < 111, "trimmed by the node radius at n2"
    assert len(net.roads["w103.1"].points) == 2 and net.roads["w103.1"].dst == "n9"


def test_controls_from_tags_and_classes(net):
    assert isinstance(net.nodes["n2"].control, Signal)
    phases = net.nodes["n2"].control.phases
    assert len(phases) == 2 and {"w101.0"} in phases, "primary alone in one phase (oneway)"
    assert net.nodes["n2"].control.right_on_red is True
    assert isinstance(net.nodes["n6"].control, Priority)
    assert net.nodes["n6"].control.major == {"w103.0", "w103.1r"}
    assert isinstance(net.nodes["n9"].control, StopSign), "stop node on the approach from n8"
    assert net.nodes["n7"].control is None


def test_boundary_and_geo(net):
    assert set(net.boundary) == {"n1", "n3", "n7", "n8", "n10", "n11"}, "n5 dead-ends inside"
    assert net.geo == pytest.approx(((BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2))
    assert net.shortest_path("n1", "n10") is not None


def test_signal_phases_group_by_axis():
    net = Network()
    for nid, x, y in [("c", 0, 0), ("w", -100, 0), ("e", 100, 0), ("s", 0, -100), ("d", 70, 70)]:
        net.add_node(nid, x, y)
    roads = [
        net.add_road(f"{a}c", a, "c", lanes=l) for a, l in [("w", 2), ("e", 2), ("s", 1), ("d", 1)]
    ]
    phases = signal_phases(roads)
    assert phases == [{"wc", "ec", "dc"}, {"sc"}] or phases == [{"wc", "ec"}, {"sc", "dc"}]


def test_rules_parse_and_rank():
    assert DALLAS.parse_maxspeed("45 mph") == pytest.approx(45 * 0.44704)
    assert DALLAS.parse_maxspeed("50") == pytest.approx(50 * 0.44704)
    assert NETHERLANDS.parse_maxspeed("50") == pytest.approx(50 / 3.6)
    assert DALLAS.parse_maxspeed("signals") is None
    assert NEW_YORK.right_on_red is False and NETHERLANDS.right_on_red is False
    assert class_rank("primary") > class_rank("primary_link") > class_rank("secondary")
    assert DALLAS.speed_for("tertiary_link") == pytest.approx(30 * 0.44704)


def test_trim_polyline():
    pts = [(0, 0), (10, 0), (10, 10)]
    assert trim_polyline(pts, 2, 3) == [(2, 0), (10, 0), (10, 7)]
    assert trim_polyline(pts, 12, 0) == [(10, 2), (10, 10)]
    short = trim_polyline([(0, 0), (4, 0)], 3, 3)
    assert math.dist(short[0], short[-1]) == pytest.approx(1.0)


def t_junction(control_factory):
    net = Network()
    net.add_node("w", -150, 0)
    net.add_node("e", 150, 0)
    net.add_node("s", 0, -100)
    net.add_node("x", 0, 0)
    net.add_road("wx", "w", "x")
    net.add_road("xe", "x", "e")
    net.add_road("sx", "s", "x")
    net.nodes["x"].control = control_factory(net)
    return net


def test_priority_minor_yields_to_major():
    net = t_junction(lambda n: Priority({"wx"}))
    sim = Simulation(net)
    major = Vehicle(0, IDM(desired_speed=15), position=100.0, speed=15.0)  # 50 m out, 3.3 s away
    minor = Vehicle(1, IDM(desired_speed=15), position=70.0, speed=10.0)  # 30 m out
    sim.add_vehicle(major, "wx", route=["wx", "xe"])
    sim.add_vehicle(minor, "sx", route=["sx", "xe"])
    order = []
    min_gap = math.inf

    def watch(s):
        nonlocal min_gap
        for v, frm, to in s.transitions:
            order.append(v.id)
        min_gap = min(min_gap, s.min_gap())

    sim.run(40.0, on_step=watch)
    assert order[:2] == [0, 1], "minor waited for the major vehicle"
    assert min_gap >= 0
    assert len(sim.exited) == 2


def test_right_on_red_only_when_allowed():
    def build(right_on_red):
        net = Network()
        for nid, x, y in [("s", 0, -100), ("x", 0, 0), ("n", 0, 100), ("e", 100, 0)]:
            net.add_node(nid, x, y)
        net.add_road("sx", "s", "x")
        net.add_road("xn", "x", "n")
        net.add_road("xe", "x", "e")
        net.nodes["x"].control = Signal([{"nothing"}], min_green=1000, right_on_red=right_on_red)
        sim = Simulation(net)
        v = Vehicle(0, IDM(), position=5.0, speed=10.0)
        sim.add_vehicle(v, "sx", route=["sx", "xe"])  # northbound then east: a right turn
        sim.run(60.0)
        return v, sim

    assert net_turn() == "right"
    v, sim = build(True)
    assert v.id in [e.id for e in sim.exited], "turned right on red after stopping"
    v, sim = build(False)
    assert v.road == "sx" and v.speed < 0.05, "held at the red"


def net_turn():
    net = Network()
    for nid, x, y in [("s", 0, -100), ("x", 0, 0), ("e", 100, 0), ("w", -100, 0)]:
        net.add_node(nid, x, y)
    net.add_road("sx", "s", "x")
    net.add_road("xe", "x", "e")
    net.add_road("xw", "x", "w")
    assert net.turn("sx", "xw") == "left"
    return net.turn("sx", "xe")


def test_signal_inferred_where_important_roads_cross():
    osm = {
        "elements": [
            node(1, 0, -1),
            node(2, 0, 0),
            node(3, 0, 1),
            node(4, 1, 0),
            node(5, -1, 0),
            way(201, [1, 2, 3], highway="secondary"),
            way(202, [4, 2, 5], highway="tertiary"),
        ]
    }
    assert isinstance(build_network(osm, DALLAS).nodes["n2"].control, Signal)
    from dataclasses import replace

    quiet = replace(DALLAS, infer_signals_major_class=None)
    assert isinstance(build_network(osm, quiet).nodes["n2"].control, Priority)
    osm["elements"][5]["tags"]["highway"] = "tertiary"  # tertiary x tertiary: no signal assumed
    assert isinstance(build_network(osm, DALLAS).nodes["n2"].control, StopSign)


def test_right_on_red_waits_for_a_gap():
    from traffic.control import Signal

    net = Network()
    for nid, x, y in [("s", 0, -100), ("x", 0, 0), ("n", 0, 100), ("w", -150, 0), ("e", 150, 0)]:
        net.add_node(nid, x, y)
    net.add_road("sx", "s", "x")
    net.add_road("xn", "x", "n")
    net.add_road("wx", "w", "x")
    net.add_road("xe", "x", "e")
    net.nodes["x"].control = Signal([{"wx"}], min_green=1000, right_on_red=True)
    sim = Simulation(net)
    turner = Vehicle(0, IDM(), position=95.0, speed=0.0)  # already at the line
    through = Vehicle(1, IDM(desired_speed=15), position=100.0, speed=15.0)  # 50 m out, green
    sim.add_vehicle(turner, "sx", route=["sx", "xe"])
    sim.add_vehicle(through, "wx", route=["wx", "xe"])
    order = []
    min_gap = math.inf

    def watch(s):
        nonlocal min_gap
        order.extend(v.id for v, _, _ in s.transitions)
        min_gap = min(min_gap, s.min_gap())

    sim.run(30.0, on_step=watch)
    assert order[:2] == [1, 0], "the through vehicle went first"
    assert min_gap >= 0


def test_ways_are_clipped_to_the_bbox():
    osm = {
        "elements": [
            node(1, 0, -5),
            node(2, 0, -1),
            node(3, 0, 0),
            node(4, 0, 1),
            node(5, 0, 6),
            node(6, 1, 0),
            node(7, -1, 0),
            way(301, [1, 2, 3, 4, 5], highway="secondary"),
            way(302, [6, 3, 7], highway="residential"),
        ]
    }
    bbox = (LAT - 1.3 * DLAT, LON - 1.3 * DLON, LAT + 1.3 * DLAT, LON + 1.3 * DLON)
    net = build_network(osm, DALLAS, bbox)
    assert set(net.nodes) == {"n2", "n3", "n4", "n6", "n7"}, "nodes 1 and 5 lie outside"
    assert set(net.boundary) == {"n2", "n4", "n6", "n7"}
