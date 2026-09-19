import math

import pytest

from traffic.demand import Spawner, uniform_demand
from traffic.metrics import Metrics
from traffic.models import IDM
from traffic.network import Network
from traffic.scenarios import grid
from traffic.sim import Simulation, Vehicle


def corridor():
    net = Network()
    net.add_node("a", 0, 0)
    net.add_node("b", 100, 0)
    net.add_node("c", 200, 0)
    net.add_road("ab", "a", "b", speed_limit=10)
    net.add_road("bc", "b", "c", speed_limit=10)
    return net


def test_free_flow_trip_has_small_delay():
    sim = Simulation(corridor())
    v = Vehicle(0, IDM(desired_speed=20), position=5.0, speed=10.0)
    sim.add_vehicle(v, "ab", route=["ab", "bc"])
    m = Metrics(sim)
    sim.run(30.0, on_step=m.on_step)
    s = m.summary()
    assert s["totals"]["exited"] == 1
    trip = s["trips"][0]
    assert trip["origin"] == "a" and trip["destination"] == "c"
    assert trip["free_flow_time"] == pytest.approx(20.0)
    assert 19.0 < trip["travel_time"] < 20.5  # started 5 m in, so a touch under free-flow
    assert abs(trip["delay"]) < 1.0
    assert trip["distance"] == pytest.approx(195.0, abs=1.0)
    assert s["totals"]["mean_speed"] == pytest.approx(10.0, abs=0.2)
    assert {r["id"]: r["throughput_per_hour"] for r in s["roads"]} == {
        "ab": pytest.approx(120.0),
        "bc": pytest.approx(120.0),
    }


def test_queue_is_counted_at_a_red_light():
    from traffic.control import Signal

    net = corridor()
    net.nodes["b"].control = Signal([{"nothing"}], min_green=1000)
    sim = Simulation(net)
    for i in range(3):
        sim.add_vehicle(
            Vehicle(i, IDM(), position=60.0 - 10 * i, speed=5.0), "ab", route=["ab", "bc"]
        )
    m = Metrics(sim)
    sim.run(60.0, on_step=m.on_step)
    node_b = next(n for n in m.summary()["nodes"] if n["id"] == "b")
    assert node_b["throughput_per_hour"] == 0
    assert 2.0 < node_b["mean_queue"] <= 3.0
    road_ab = next(r for r in m.summary()["roads"] if r["id"] == "ab")
    assert road_ab["mean_stopped"] > 2.0


def test_grid_summary_is_consistent():
    sim = grid(rows=2, cols=2, rate=0.1, seed=4)
    m = Metrics(sim)
    sim.run(200.0, on_step=m.on_step)
    s = m.summary()
    t = s["totals"]
    assert t["exited"] == len(sim.exited) == len(s["trips"])
    assert t["spawned"] == t["exited"] + t["on_road"]
    assert t["mean_delay"] > 0
    assert len(s["roads"]) == len(sim.network.roads)
    assert all(r["mean_vehicles"] >= 0 and math.isfinite(r["density_per_km"]) for r in s["roads"])
    assert sum(n["throughput_per_hour"] for n in s["nodes"]) > 0


def test_uniform_demand_and_weighted_destinations():
    d = uniform_demand(["a", "b", "c"], 0.3)
    assert d[("a", "b")] == pytest.approx(0.15)
    assert len(d) == 6
    net = Network()
    net.add_node("o", 0, 0)
    net.add_node("x", 100, 0)
    net.add_node("y", 0, 100)
    net.add_road("ox", "o", "x")
    net.add_road("oy", "o", "y")
    sim = Simulation(net)
    sim.spawners = Spawner.from_demand({("o", "x"): 0.3, ("o", "y"): 0.1}, IDM(), sim.rng)
    assert len(sim.spawners) == 1 and sim.spawners[0].rate == pytest.approx(0.4)
    sim.run(300.0)  # 0.4 veh/s is well under one lane's capacity, so nothing queues at the entry
    trips = sim.exited
    to_x = sum(1 for v in trips if v.route == ["ox"])
    assert len(trips) > 80 and sim.spawners[0].pending < 5
    assert 0.65 < to_x / len(trips) < 0.85, "roughly 3:1 split, and the origin picks the right road"


def test_trace_splits_static_and_signal_states():
    from traffic.trace import TraceWriter

    sim = grid(rows=2, cols=2, control="stop")
    d = TraceWriter(sim).to_dict()
    assert len(d["static_states"]) == 4 * 4 and "s" not in d["ticks"][0]
    sim = grid(rows=2, cols=2, control="signal")
    d = TraceWriter(sim).to_dict()
    assert d["static_states"] == [] and len(d["ticks"][0]["s"]) == 16
