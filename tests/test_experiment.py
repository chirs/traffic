import csv

from traffic.experiment import aggregate, run_one, sweep, write_csv


def test_sweep_crosses_params_and_seeds(tmp_path):
    rows = sweep("grid", {"control": ["signal", "none"], "rows": [2]}, range(2), 60.0)
    assert len(rows) == 4
    assert {(r["control"], r["seed"]) for r in rows} == {
        ("signal", 0),
        ("signal", 1),
        ("none", 0),
        ("none", 1),
    }
    assert all(r["rows"] == 2 and r["scenario"] == "grid" for r in rows)
    out = tmp_path / "sweep.csv"
    write_csv(rows, out)
    with out.open() as f:
        back = list(csv.DictReader(f))
    assert len(back) == 4 and "throughput_per_hour" in back[0]
    agg = aggregate(rows, ["control"], ["throughput_per_hour", "mean_delay"])
    assert {a["control"]: a["runs"] for a in agg} == {"signal": 2, "none": 2}


def test_run_one_is_deterministic():
    a = run_one("grid", {"rows": 2, "cols": 2, "rate": 0.1}, 7, 60.0)
    b = run_one("grid", {"rows": 2, "cols": 2, "rate": 0.1}, 7, 60.0)
    assert a == b
    assert a["exited"] > 0
