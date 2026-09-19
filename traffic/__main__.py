import argparse

from .scenarios import grid, ring_road
from .trace import TraceWriter


def main() -> None:
    p = argparse.ArgumentParser(prog="traffic")
    sub = p.add_subparsers(dest="cmd", required=True)

    ring = sub.add_parser("ring", help="ring road: phantom jams")
    ring.add_argument("--vehicles", type=int, default=40)
    ring.add_argument("--length", type=float, default=1000.0)

    g = sub.add_parser("grid", help="street grid with controlled intersections")
    g.add_argument("--rows", type=int, default=3)
    g.add_argument("--cols", type=int, default=3)
    g.add_argument("--block", type=float, default=150.0)
    g.add_argument("--lanes", type=int, default=1)
    g.add_argument("--control", choices=["signal", "actuated", "stop", "none"], default="signal")
    g.add_argument("--rate", type=float, default=0.15, help="vehicles/s per boundary entry")

    for sp in (ring, g):
        sp.add_argument("--duration", type=float, default=600.0)
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--record-every", type=int, default=5, help="steps per recorded tick")
        sp.add_argument("--js-var", default=None, help="emit JS pushing onto this array (www/)")
        sp.add_argument("--name", default=None, help="sample name shown in the viewer")
        sp.add_argument("--out", required=True)
    args = p.parse_args()

    if args.cmd == "ring":
        sim = ring_road(args.vehicles, length=args.length, seed=args.seed)
    else:
        sim = grid(
            rows=args.rows,
            cols=args.cols,
            block=args.block,
            lanes=args.lanes,
            control=args.control,
            rate=args.rate,
            seed=args.seed,
        )
    writer = TraceWriter(sim, record_every=args.record_every)
    sim.run(args.duration, on_step=writer.on_step)
    writer.write(args.out, js_var=args.js_var, name=args.name)
    print(
        f"wrote {args.out}: {len(writer.ticks)} ticks, {len(writer.vehicles)} vehicles seen, "
        f"{len(sim.vehicles)} on road, {len(sim.exited)} exited"
    )


if __name__ == "__main__":
    main()
