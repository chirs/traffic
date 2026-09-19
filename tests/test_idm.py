import math

import pytest

from traffic.models import IDM


def test_free_road_from_rest_gives_max_accel():
    m = IDM(max_accel=1.0)
    assert m.acceleration(0.0, math.inf, 0.0) == pytest.approx(1.0)


def test_free_road_at_desired_speed_gives_zero():
    m = IDM(desired_speed=30.0)
    assert m.acceleration(30.0, math.inf, 0.0) == pytest.approx(0.0)


def test_stopped_at_min_gap_holds_still():
    m = IDM(min_gap=2.0)
    assert m.acceleration(0.0, 2.0, 0.0) == pytest.approx(0.0)


def test_closing_on_stopped_leader_brakes():
    m = IDM()
    assert m.acceleration(20.0, 30.0, 0.0) < -1.0


def test_faster_approach_brakes_harder():
    m = IDM()
    assert m.acceleration(25.0, 40.0, 10.0) < m.acceleration(15.0, 40.0, 10.0)
