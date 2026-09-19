import argparse

from .scenarios import ring_road
from .trace import TraceWriter


def main() -> None:
    p = argparse.ArgumentParser(prog="traffic")
    sub = p.add_subparsers(dest="cmd", required=True)
    ring = sub.add_parser("ring", help="run a ring-road scenario and write a trace")
    ring.add_argument("--vehicles", type=int, default=40)
    ring.add_argument("--length", type=float, default=1000.0)
    ring.add_argument("--duration", type=float, default=600.0)
    ring.add_argument("--seed", type=int, default=0)
    ring.add_argument("--record-every", type=int, default=5, help="steps per recorded tick")
    ring.add_argument("--out", default="traces/ring.json")
    args = p.parse_args()

    sim = ring_road(args.vehicles, length=args.length, seed=args.seed)
    writer = TraceWriter(sim, record_every=args.record_every)
    sim.run(args.duration, on_step=writer.on_step)
    writer.write(args.out, js_var="SAMPLE_TRACE" if args.out.endswith(".js") else None)
    speeds = [v.speed for v in sim.vehicles]
    print(
        f"wrote {args.out}: {len(writer.ticks)} ticks, "
        f"final speed min {min(speeds):.1f} max {max(speeds):.1f} m/s"
    )


if __name__ == "__main__":
    main()
