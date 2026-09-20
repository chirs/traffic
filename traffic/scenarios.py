import random
from pathlib import Path

from . import osm
from .control import Signal, StopSign
from .demand import Spawner, uniform_demand
from .models import IDM
from .network import LANE_WIDTH, Network
from .rules import DALLAS, RULES, Rules
from .sim import Simulation, Vehicle

DATA = Path(__file__).resolve().parent.parent / "data"
PLACES = {
    # south, west, north, east
    "vernon_ferndale": (
        32.7195,
        -96.8496,
        32.7422,
        -96.8240,
    ),  # Illinois to 12th, centred on Vernon
    "oak_cliff": (32.742, -96.836, 32.756, -96.820),  # Bishop Arts and surroundings
}
# Optional (lat, lon) polygons that trim a place inside its bbox.
PLACE_CLIPS = {
    # Everything west of I-35E: the east side runs about 60 m west of the mainlanes, which
    # also drops Zang (the frontage road here) and Brookhaven.
    "vernon_ferndale": [
        (32.7195, -96.8496),
        (32.7195, -96.8289),
        (32.7230, -96.8280),
        (32.7260, -96.8268),
        (32.7290, -96.8263),
        (32.7320, -96.8256),
        (32.7350, -96.8249),
        (32.7390, -96.8247),
        (32.7422, -96.8247),
        (32.7422, -96.8496),
    ],
}

# Low max_accel puts IDM in its string-unstable regime at moderate density, so a
# small perturbation grows into stop-and-go waves. Treiber's ring-road demo settings.
JAM_PRONE = IDM(desired_speed=30.0, time_headway=1.5, min_gap=2.0, max_accel=0.3, comfort_decel=3.0)
URBAN = IDM(desired_speed=15.0, time_headway=1.2, min_gap=2.0, max_accel=1.2, comfort_decel=2.0)
CITY = IDM(desired_speed=22.0, time_headway=1.3, min_gap=2.0, max_accel=1.2, comfort_decel=2.0)


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
    demand: dict[tuple[str, str], float] | None = None,
    seed: int = 0,
    dt: float = 0.1,
) -> Simulation:
    """rows x cols of controlled intersections on a street grid. Every edge intersection has a
    stub road out to a boundary node, which acts as source and sink. control: signal (fixed),
    actuated, stop, or none. demand is an origin-destination matrix {(origin, dest): veh/s}
    over boundary nodes (s0.., N0.., w0.., e0..); by default every boundary node sends `rate`
    vehicles/second spread evenly over all the others."""
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
    if demand is None:
        demand = uniform_demand([s[0] for s in stubs], rate)
    sim.spawners = Spawner.from_demand(demand, model, rng)
    return sim


def osm_area(
    bbox: tuple[float, float, float, float],
    cache: str | Path,
    rules: Rules | str = DALLAS,
    rate: float = 0.5,
    model: IDM = CITY,
    clip: list[tuple[float, float]] | None = None,
    seed: int = 0,
    dt: float = 0.1,
) -> Simulation:
    """Real streets from OpenStreetMap inside bbox (south, west, north, east), trimmed to the
    `clip` polygon if given. Traffic enters and leaves at dead ends on the edge; `rate` is the
    total vehicles/second entering, shared out by each entry's road class and lanes."""
    if isinstance(rules, str):
        rules = RULES[rules]
    rng = random.Random(seed)
    net = osm.build_network(osm.fetch(bbox, cache), rules, bbox, clip)
    sim = Simulation(net, dt=dt, seed=seed)
    weights = osm.boundary_weights(net)
    origins = [n for n in weights if net.out_roads(n)]
    dests = [n for n in weights if net.in_roads(n)]
    total = sum(weights[o] for o in origins)
    demand = {}
    for o in origins:
        others = [d for d in dests if d != o]
        wsum = sum(weights[d] for d in others)
        for d in others:
            demand[(o, d)] = rate * weights[o] / total * weights[d] / wsum
    sim.spawners = Spawner.from_demand(demand, model, rng)
    return sim


def place(name: str = "vernon_ferndale", rules: Rules | str = DALLAS, **kw) -> Simulation:
    return osm_area(
        PLACES[name], DATA / f"{name}.json", rules=rules, clip=PLACE_CLIPS.get(name), **kw
    )


SCENARIOS = {"ring": ring_road, "grid": grid, "place": place}
