import math

from traffic.models import IDM
from traffic.network import Network
from traffic.scenarios import grid
from traffic.sim import Simulation, Vehicle


def test_vehicle_transitions_along_route_and_exits():
    net = Network()
    net.add_node("a", 0, 0)
    net.add_node("b", 100, 0)
    net.add_node("c", 100, 100)
    net.add_road("ab", "a", "b", speed_limit=10)
    net.add_road("bc", "b", "c", speed_limit=10)
    sim = Simulation(net)
    v = Vehicle(0, IDM(), position=5.0, speed=10.0)
    sim.add_vehicle(v, "ab", route=["ab", "bc"])
    sim.run(12.0)
    assert v.road == "bc"
    assert 0 < v.position < 100
    sim.run(15.0)
    assert not sim.vehicles and sim.exited == [v]


def test_speed_limit_caps_free_speed():
    net = Network()
    net.add_node("a", 0, 0)
    net.add_node("b", 5000, 0)
    net.add_road("ab", "a", "b", speed_limit=10)
    sim = Simulation(net)
    v = Vehicle(0, IDM(desired_speed=30), position=5.0, speed=0.0)
    sim.add_vehicle(v, "ab")
    sim.run(60.0)
    assert 9.5 < v.speed <= 10.0


def test_lane_change_to_pass_slow_leader():
    net = Network()
    net.add_node("a", 0, 0)
    net.add_node("b", 2000, 0)
    net.add_road("ab", "a", "b", lanes=2)
    sim = Simulation(net)
    slow = Vehicle(0, IDM(desired_speed=8), position=60.0, speed=8.0)
    fast = Vehicle(1, IDM(desired_speed=25), position=10.0, speed=20.0)
    sim.add_vehicle(slow, "ab", lane=0)
    sim.add_vehicle(fast, "ab", lane=0)
    sim.run(20.0)
    assert fast.lane == 1
    assert fast.position > slow.position
    assert slow.lane == 0


def test_follower_does_not_cut_in_unsafely():
    net = Network()
    net.add_node("a", 0, 0)
    net.add_node("b", 2000, 0)
    net.add_road("ab", "a", "b", lanes=2)
    sim = Simulation(net)
    sim.add_vehicle(Vehicle(0, IDM(desired_speed=8), position=60.0, speed=8.0), "ab", lane=0)
    sim.add_vehicle(Vehicle(1, IDM(desired_speed=25), position=40.0, speed=20.0), "ab", lane=0)
    sim.add_vehicle(Vehicle(2, IDM(desired_speed=25), position=38.0, speed=25.0), "ab", lane=1)
    min_gap = math.inf

    def watch(s):
        nonlocal min_gap
        min_gap = min(min_gap, s.min_gap())

    sim.run(30.0, on_step=watch)
    assert min_gap >= 0


def run_grid(**kw):
    sim = grid(**kw)
    min_gap = math.inf

    def watch(s):
        nonlocal min_gap
        min_gap = min(min_gap, s.min_gap())

    sim.run(kw.pop("duration", 240.0), on_step=watch)
    return sim, min_gap


def test_grid_signal_smoke():
    sim, min_gap = run_grid(rows=2, cols=2, control="signal", rate=0.2, seed=1)
    assert min_gap >= 0
    assert len(sim.exited) > 20
    assert all(math.isfinite(v.position) and math.isfinite(v.speed) for v in sim.vehicles.values())


def test_grid_stop_and_two_lane_smoke():
    sim, min_gap = run_grid(rows=2, cols=2, control="stop", rate=0.1, seed=2)
    assert min_gap >= 0 and len(sim.exited) > 10
    sim, min_gap = run_grid(rows=2, cols=2, lanes=2, control="actuated", rate=0.3, seed=3)
    assert min_gap >= 0 and len(sim.exited) > 20
    assert any(v.lane == 1 for v in list(sim.vehicles.values()) + sim.exited)


def test_lookahead_sees_past_short_roads():
    """A 1 m stub between two roads must not hide a queue on the road after it."""
    net = Network()
    for nid, x in [("a", 0), ("b", 200), ("c", 201), ("d", 400)]:
        net.add_node(nid, x, 0)
    net.add_road("ab", "a", "b", speed_limit=15)
    net.add_road("bc", "b", "c", speed_limit=15)
    net.add_road("cd", "c", "d", speed_limit=15)
    sim = Simulation(net)
    parked = Vehicle(0, IDM(desired_speed=0.01), position=6.0, speed=0.0)
    sim.add_vehicle(parked, "cd", route=["cd"])
    v = Vehicle(1, IDM(), position=5.0, speed=15.0)
    sim.add_vehicle(v, "ab", route=["ab", "bc", "cd"])
    min_gap = math.inf

    def watch(s):
        nonlocal min_gap
        min_gap = min(min_gap, s.min_gap())

    sim.run(40.0, on_step=watch)
    assert min_gap >= 0
    assert v.speed < 0.1 and v.position < 2.0, "halted just short of the parked car"
