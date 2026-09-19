import argparse
import json

from .experiment import aggregate, sweep, write_csv
from .metrics import Metrics
from .scenarios import PLACES, grid, place, ring_road
from .trace import TraceWriter


def parse_value(text: str):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


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
    g.add_argument("--rate", type=float, default=0.08, help="vehicles/s per boundary entry")

    o = sub.add_parser("place", help="real streets from OpenStreetMap")
    o.add_argument("--name", dest="place", choices=sorted(PLACES), default="oak_cliff")
    o.add_argument("--rules", choices=["dallas", "new_york", "netherlands"], default="dallas")
    o.add_argument("--rate", type=float, default=0.5, help="total vehicles/s entering the area")

    for sp in (ring, g, o):
        sp.add_argument("--duration", type=float, default=600.0)
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--record-every", type=int, default=5, help="steps per recorded tick")
        sp.add_argument("--js-var", default=None, help="emit JS pushing onto this array (www/)")
        sp.add_argument("--label", default=None, help="sample name shown in the viewer")
        sp.add_argument("--out", default=None, help="trace file to write")
        sp.add_argument("--summary", default=None, help="metrics JSON to write")

    sw = sub.add_parser("sweep", help="run a scenario over parameter values and seeds")
    sw.add_argument("scenario", choices=["ring", "grid", "place"])
    sw.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=V1,V2,...",
        help="scenario argument and the values to sweep (repeatable)",
    )
    sw.add_argument("--seeds", type=int, default=3, help="seeds 0..N-1 per combination")
    sw.add_argument("--duration", type=float, default=600.0)
    sw.add_argument("--workers", type=int, default=1)
    sw.add_argument("--out", required=True, help="CSV, one row per run")
    args = p.parse_args()

    if args.cmd == "sweep":
        params = {}
        for spec in args.param:
            name, _, values = spec.partition("=")
            params[name] = [parse_value(v) for v in values.split(",")]
        rows = sweep(args.scenario, params, range(args.seeds), args.duration, args.workers)
        write_csv(rows, args.out)
        fields = ["throughput_per_hour", "mean_delay", "mean_speed"]
        print(f"wrote {args.out}: {len(rows)} runs")
        for row in aggregate(rows, list(params), fields):
            label = " ".join(f"{k}={row[k]}" for k in params)
            print(
                f"  {label:40s} n={row['runs']} throughput {row['throughput_per_hour']:7.0f}/h "
                f"delay {fmt(row['mean_delay']):>6s} s  speed {fmt(row['mean_speed']):>5s} m/s"
            )
        return

    if args.cmd == "ring":
        sim = ring_road(args.vehicles, length=args.length, seed=args.seed)
    elif args.cmd == "place":
        sim = place(args.place, rules=args.rules, rate=args.rate, seed=args.seed)
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
    if args.out is None and args.summary is None:
        p.error("give --out and/or --summary")
    writer = TraceWriter(sim, record_every=args.record_every) if args.out else None
    metrics = Metrics(sim)

    def on_step(s):
        metrics.on_step(s)
        if writer:
            writer.on_step(s)

    sim.run(args.duration, on_step=on_step)
    summary = metrics.summary()
    if writer:
        writer.write(args.out, js_var=args.js_var, name=args.label)
        print(f"wrote {args.out}: {len(writer.ticks)} ticks, {len(writer.vehicles)} vehicles seen")
    if args.summary:
        with open(args.summary, "w") as f:
            json.dump(summary, f, indent=1)
        print(f"wrote {args.summary}")
    t = summary["totals"]
    print(
        f"{t['exited']} trips, {t['on_road']} on road, {t['pending']} waiting to enter · "
        f"throughput {t['throughput_per_hour']:.0f}/h · mean delay {fmt(t['mean_delay'])} s · "
        f"mean speed {fmt(t['mean_speed'])} m/s"
    )


def fmt(x) -> str:
    return "-" if x is None else f"{x:.1f}"


if __name__ == "__main__":
    main()
