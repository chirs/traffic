"""Monte Carlo sweeps: run a scenario over a parameter grid and several seeds, one row per run."""

import csv
import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .metrics import Metrics
from .scenarios import SCENARIOS


def run_one(scenario: str, params: dict, seed: int, duration: float) -> dict:
    sim = SCENARIOS[scenario](seed=seed, **params)
    metrics = Metrics(sim)
    sim.run(duration, on_step=metrics.on_step)
    return {"scenario": scenario, **params, "seed": seed, **metrics.summary()["totals"]}


def _run_one(args: tuple) -> dict:
    return run_one(*args)


def sweep(
    scenario: str,
    grid: dict[str, list],
    seeds: range,
    duration: float,
    workers: int = 1,
) -> list[dict]:
    """Every combination of grid values x seeds. grid maps a scenario kwarg to its values."""
    keys = list(grid)
    configs = [
        (scenario, dict(zip(keys, values)), seed, duration)
        for values in itertools.product(*(grid[k] for k in keys))
        for seed in seeds
    ]
    if workers > 1:
        with ProcessPoolExecutor(workers) as pool:
            return list(pool.map(_run_one, configs))
    return [_run_one(c) for c in configs]


def write_csv(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows: list[dict], keys: list[str], fields: list[str]) -> list[dict]:
    """Mean of `fields` over seeds for each distinct combination of `keys`."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    out = []
    for combo, rs in groups.items():
        row = dict(zip(keys, combo))
        row["runs"] = len(rs)
        for f in fields:
            vals = [r[f] for r in rs if r[f] is not None]
            row[f] = sum(vals) / len(vals) if vals else None
        out.append(row)
    return out
