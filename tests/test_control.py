import math

from traffic.control import Signal, StopSign
from traffic.models import IDM
from traffic.network import Network
from traffic.sim import Simulation, Vehicle


def corridor(control, lanes=1, length=200.0):
    """a -> b -> c with `control` at b."""
    net = Network()
    net.add_node("a", 0, 0)
    net.add_node("b", length, 0, control)
    net.add_node("c", 2 * length, 0)
    net.add_road("ab", "a", "b", lanes=lanes)
    net.add_road("bc", "b", "c", lanes=lanes)
    return net


def test_fixed_signal_cycles():
    sig = Signal([{"x"}, {"y"}], min_green=10, yellow=3, all_red=1)
    net = Network()
    sim = Simulation(net)

    class N:
        id = "n"

    seen = []
    for _ in range(300):
        sig.update(sim, N)
        seen.append((sig.state("x"), sig.state("y")))
        sim.time += 0.1
    assert seen[0] == ("g", "r")
    assert seen[105] == ("y", "r")
    assert seen[135] == ("r", "r")
    assert seen[145] == ("r", "g")
    assert seen[285] == ("g", "r")


def test_vehicle_stops_at_red_then_proceeds():
    sig = Signal([{"nothing"}], min_green=1000)  # ab is never green
    net = corridor(sig)
    sim = Simulation(net)
    v = Vehicle(0, IDM(), position=5.0, speed=20.0)
    sim.add_vehicle(v, "ab", route=["ab", "bc"])
    sim.run(60.0)
    assert v.road == "ab"
    assert 197.0 < v.position < 200.0
    assert v.speed < 0.05
    sig.phases = [{"ab"}]
    sim.run(30.0)
    assert v.id in [e.id for e in sim.exited]


def test_yellow_dilemma_zone():
    sig = Signal([{"ab"}], min_green=5, yellow=3)
    sim = Simulation(corridor(sig))
    fast = Vehicle(0, IDM(), position=190.0, speed=20.0)  # 10 m out at 20 m/s: cannot stop
    sim.add_vehicle(fast, "ab", route=["ab", "bc"])
    sim.time = 5.05  # yellow just started
    sig.update(sim, sim.network.nodes["b"])
    assert sig.state("ab") == "y"
    assert not sig.must_stop(fast, 10.0, sim)
    assert sig.must_stop(fast, 150.0, sim)


def test_actuated_signal_extends_for_demand_up_to_max():
    sig = Signal([{"ab"}, {"none"}], min_green=5, max_green=15, detector=30)
    sim = Simulation(corridor(sig))
    v = Vehicle(0, IDM(desired_speed=0.01), position=190.0, speed=0.0)  # parked at the line
    sim.add_vehicle(v, "ab", route=["ab", "bc"])
    node = sim.network.nodes["b"]
    t_yellow = None
    for _ in range(300):
        sig.update(sim, node)
        if sig.state("ab") == "y":
            t_yellow = sim.time
            break
        sim.time += 0.1
    assert t_yellow is not None and 14.9 < t_yellow < 15.2
    # without demand it drops after min_green
    sig2 = Signal([{"ab"}, {"none"}], min_green=5, max_green=15)
    sim2 = Simulation(corridor(sig2))
    for _ in range(300):
        sig2.update(sim2, node)
        if sig2.state("ab") == "y":
            break
        sim2.time += 0.1
    assert 4.9 < sim2.time < 5.2


def test_stop_sign_serialises_two_approaches():
    net = Network()
    net.add_node("w", -100, 0)
    net.add_node("s", 0, -100)
    net.add_node("x", 0, 0, StopSign())
    net.add_node("e", 100, 0)
    net.add_road("wx", "w", "x")
    net.add_road("sx", "s", "x")
    net.add_road("xe", "x", "e")
    sim = Simulation(net)
    a = Vehicle(0, IDM(), position=5.0, speed=15.0)
    b = Vehicle(1, IDM(), position=5.0, speed=15.0)
    sim.add_vehicle(a, "wx", route=["wx", "xe"])
    sim.add_vehicle(b, "sx", route=["sx", "xe"])
    stopped = {0: False, 1: False}
    min_gap = math.inf

    def watch(s):
        nonlocal min_gap
        for v in (a, b):
            if v.id in s.vehicles and v.road != "xe" and v.speed < 0.3:
                stopped[v.id] = True
        min_gap = min(min_gap, s.min_gap())

    sim.run(60.0, on_step=watch)
    assert stopped == {0: True, 1: True}, "both came to a halt at the sign"
    assert len(sim.exited) == 2
    assert min_gap >= 0
