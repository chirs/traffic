import pytest

from traffic.control import Signal, StopSign
from traffic.network import Network
from traffic.scenarios import grid


def test_shortest_path_prefers_faster_roads():
    net = Network()
    for nid, x in [("a", 0), ("b", 100), ("c", 200)]:
        net.add_node(nid, x, 0)
    net.add_node("d", 100, 100)
    net.add_road("ab", "a", "b", speed_limit=10)
    net.add_road("bc", "b", "c", speed_limit=10)
    net.add_road("ad", "a", "d", speed_limit=30)
    net.add_road("dc", "d", "c", speed_limit=30)
    assert net.shortest_path("a", "c") == ["ad", "dc"]
    assert net.shortest_path("a", "a") == []
    assert net.shortest_path("c", "a") is None


def test_grid_shape():
    sim = grid(rows=2, cols=3, control="signal")
    net = sim.network
    assert len(net.nodes) == 6 + 2 * 3 + 2 * 2
    # every interior node has four approaches, split into NS/EW phases
    for c in range(3):
        for r in range(2):
            node = net.nodes[f"n{c}_{r}"]
            assert len(net.in_roads(node.id)) == 4
            assert isinstance(node.control, Signal)
            assert all(len(p) == 2 for p in node.control.phases)
    assert len(sim.spawners) == 10


def test_grid_controls():
    assert all(
        isinstance(n.control, StopSign)
        for n in grid(control="stop").network.nodes.values()
        if n.id.startswith("n")
    )
    assert all(n.control is None for n in grid(control="none").network.nodes.values())


def test_node_radius_trims_roads():
    net = Network()
    net.add_node("a", 0, 0, radius=5)
    net.add_node("b", 100, 0, radius=10)
    road = net.add_road("ab", "a", "b")
    assert road.length == 85
    assert road.points == [(5.0, 0.0), (90.0, 0.0)]
    assert grid(lanes=2).network.roads["n0_0>n1_0"].length == pytest.approx(150 - 2 * 7.2)
