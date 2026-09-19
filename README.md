# traffic

Microscopic traffic simulator. Python core writes a trace file; a vanilla-JS canvas
viewer plays it back. See [ROADMAP.md](ROADMAP.md).

## Setup

    uv sync
    .venv/bin/pytest
    node --test tests/
    .venv/bin/python -m traffic ring --vehicles 40 --duration 600 --out traces/ring.json

## Viewer

Open `www/index.html` directly (it loads `www/sample-trace.js`) or serve `www/` and pass
`?trace=path.json`. Drag a trace onto the page or use "open trace" to load another.
Space plays, arrows step, `[` `]` change speed, scroll zooms, `f` refits. The strip at
the bottom is a space-time diagram (time across, position up, colour by speed); click or
drag it to scrub.

Regenerate the bundled sample with

    .venv/bin/python -m traffic ring --duration 400 --record-every 10 --out www/sample-trace.js

The ring scenario reproduces phantom traffic jams: a near-uniform flow breaks into
stop-and-go waves from a tiny perturbation.

## Layout

- `traffic/models.py` — `CarFollowingModel` protocol and the IDM implementation
- `traffic/sim.py` — `Vehicle`, `Road`, `Lane`, `Simulation` (fixed timestep)
- `traffic/scenarios.py` — scenario builders (`ring_road`)
- `traffic/trace.py` — `TraceWriter`
- `traffic/__main__.py` — CLI
- `www/core.js` — pure trace logic (indexing, interpolation, ring geometry, colour ramp); tested with `node --test`
- `www/app.js` — canvas rendering, playback, controls
- `www/sample-trace.js` — **generated** sample trace; never hand-edit

## Trace format (version 1)

JSON. All units SI (metres, seconds). Positions are front bumpers measured along the road.

```json
{
  "version": 1,
  "dt": 0.5,
  "network": {"roads": [{"id": "ring", "length": 1000.0, "ring": true}]},
  "vehicles": [{"id": 0, "length": 5.0}],
  "ticks": [
    {"t": 0.0, "v": [[0, 0, 12.345, 11.9, -0.02]]}
  ]
}
```

- `dt` — seconds between consecutive ticks
- `network.roads` — indexed by position in the array
- `vehicles` — static per-vehicle data, keyed by `id`
- `ticks[].v` — one row per vehicle present: `[id, road_index, position, speed, accel]`

Vehicles may be absent from a tick (they have not entered or have exited).

## Background

- https://en.wikipedia.org/wiki/Traffic_simulation
- Intelligent Driver Model (Treiber, Hennecke, Helbing 2000)
- Gipps' model, Nagel–Schreckenberg cellular automaton (planned as alternative models)
