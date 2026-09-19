import statistics

import pytest

from traffic.scenarios import ring_road


def run_checked(sim, duration):
    min_gap = float("inf")

    def check(s):
        nonlocal min_gap
        min_gap = min(min_gap, s.min_gap())

    sim.run(duration, on_step=check)
    return min_gap


@pytest.mark.parametrize("n", [5, 40])
def test_no_collisions_and_count_conserved(n):
    sim = ring_road(n, seed=1)
    min_gap = run_checked(sim, 300.0)
    assert min_gap >= 0.0
    assert len(sim.vehicles) == n
    assert sorted(sim.vehicles) == list(range(n))


def test_positions_stay_on_ring():
    sim = ring_road(30, seed=2)
    sim.run(100.0)
    assert all(0.0 <= v.position < 1000.0 for v in sim.vehicles.values())


def test_sparse_ring_stays_free_flowing():
    sim = ring_road(5, seed=0)
    sim.run(600.0)
    speeds = [v.speed for v in sim.vehicles.values()]
    assert min(speeds) > 28.0
    assert statistics.pstdev(speeds) < 0.5


def test_dense_ring_develops_jam():
    sim = ring_road(40, seed=0)
    sim.run(600.0)
    speeds = [v.speed for v in sim.vehicles.values()]
    assert statistics.pstdev(speeds) > 3.0
    assert min(speeds) < 2.0
