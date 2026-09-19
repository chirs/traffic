import random

from .control import Signal, StopSign
from .demand import Spawner
from .models import IDM
from .network import LANE_WIDTH, Network
from .sim import Simulation, Vehicle

# Low max_accel puts IDM in its string-unstable regime at moderate density, so a
# small perturbation grows into stop-and-go waves. Treiber's ring-road demo settings.
JAM_PRONE = IDM(desired_speed=30.0, time_headway=1.5, min_gap=2.0, max_accel=0.3, comfort_decel=3.0)
URBAN = IDM(desired_speed=15.0, time_headway=1.2, min_gap=2.0, max_accel=1.2, comfort_decel=2.0)


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
    net = Network()
    net.add_ring("ring", length)
    sim = Simulation(net, dt=dt, seed=seed)
    spacing = length / n_vehicles
    speed = min(model.desired_speed, max(0.0, (spacing - 5.0 - model.min_gap) / model.time_headway))
    for i in range(n_vehicles):
        v = Vehicle(
            id=i,
            model=model,
            position=i * spacing + rng.uniform(-perturbation, perturbation),
            speed=max(0.0, speed + rng.uniform(-perturbation, perturbation)),
        )
        sim.add_vehicle(v, "ring")
    return sim


def grid(
    rows: int = 3,
    cols: int = 3,
    block: float = 150.0,
    lanes: int = 1,
    control: str = "signal",
    rate: float = 0.15,
    stub: float = 100.0,
    speed_limit: float = 13.4,
    model: IDM = URBAN,
    seed: int = 0,
    dt: float = 0.1,
) -> Simulation:
    """rows x cols of controlled intersections on a street grid. Every edge intersection has a
    stub road out to a boundary node, which acts as source and sink. control: signal (fixed),
    actuated, stop, or none. rate is vehicles/second entering at each boundary node."""
    rng = random.Random(seed)
    net = Network()

    def name(c: int, r: int) -> str:
        return f"n{c}_{r}"

    for c in range(cols):
        for r in range(rows):
            net.add_node(name(c, r), c * block, r * block, radius=lanes * LANE_WIDTH)
    stubs = []
    for c in range(cols):
        stubs.append((f"s{c}", c * block, -stub, name(c, 0)))
        stubs.append((f"N{c}", c * block, (rows - 1) * block + stub, name(c, rows - 1)))
    for r in range(rows):
        stubs.append((f"w{r}", -stub, r * block, name(0, r)))
        stubs.append((f"e{r}", (cols - 1) * block + stub, r * block, name(cols - 1, r)))
    for sid, x, y, inner in stubs:
        net.add_node(sid, x, y)

    def link(a: str, b: str) -> None:
        net.add_road(f"{a}>{b}", a, b, lanes=lanes, speed_limit=speed_limit)
        net.add_road(f"{b}>{a}", b, a, lanes=lanes, speed_limit=speed_limit)

    for c in range(cols):
        for r in range(rows):
            if c + 1 < cols:
                link(name(c, r), name(c + 1, r))
            if r + 1 < rows:
                link(name(c, r), name(c, r + 1))
    for sid, _, _, inner in stubs:
        link(sid, inner)

    for c in range(cols):
        for r in range(rows):
            node = net.nodes[name(c, r)]
            approaches = net.in_roads(node.id)
            ns = {rd.id for rd in approaches if abs(rd.direction()[1]) > abs(rd.direction()[0])}
            ew = {rd.id for rd in approaches} - ns
            if control == "signal":
                node.control = Signal([ns, ew], min_green=20.0)
            elif control == "actuated":
                node.control = Signal([ns, ew], min_green=5.0, max_green=30.0)
            elif control == "stop":
                node.control = StopSign()

    sim = Simulation(net, dt=dt, seed=seed)
    stub_ids = [s[0] for s in stubs]
    for sid, _, _, inner in stubs:
        dests = [s for s in stub_ids if s != sid]
        sim.spawners.append(Spawner(f"{sid}>{inner}", rate, dests, model, rng))
    return sim
