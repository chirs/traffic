import random

from .models import IDM
from .sim import Road, Simulation, Vehicle

# Low max_accel puts IDM in its string-unstable regime at moderate density, so a
# small perturbation grows into stop-and-go waves. Treiber's ring-road demo settings.
JAM_PRONE = IDM(desired_speed=30.0, time_headway=1.5, min_gap=2.0, max_accel=0.3, comfort_decel=3.0)


def ring_road(
    n_vehicles: int,
    length: float = 1000.0,
    model: IDM = JAM_PRONE,
    seed: int = 0,
    dt: float = 0.1,
    perturbation: float = 0.5,
) -> Simulation:
    """n vehicles evenly spaced on a ring, at a common speed, with a seeded jitter."""
    rng = random.Random(seed)
    spacing = length / n_vehicles
    speed = min(model.desired_speed, max(0.0, (spacing - 5.0 - model.min_gap) / model.time_headway))
    vehicles = [
        Vehicle(
            id=i,
            model=model,
            position=i * spacing + rng.uniform(-perturbation, perturbation),
            speed=max(0.0, speed + rng.uniform(-perturbation, perturbation)),
        )
        for i in range(n_vehicles)
    ]
    return Simulation(Road("ring", length, ring=True), vehicles, dt=dt)
