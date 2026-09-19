# traffic

Microscopic traffic simulator. Python core writes a trace file; a vanilla-JS canvas
viewer plays it back. See [ROADMAP.md](ROADMAP.md).

## Setup

    uv sync
    .venv/bin/pytest
    node --test tests/
    .venv/bin/python -m traffic ring --vehicles 40 --duration 600 --out traces/ring.json

## Viewer

Open `www/index.html` directly (bundled samples in `www/samples/`) or serve `www/` and pass
`?trace=path.json`. Drag a trace onto the page or use "open trace" to load another.
Space plays, arrows step (shift for ten ticks), `[` `]` change speed, scroll zooms, drag
pans, `f` refits. Cars are coloured by speed and show brake lights; signal lamps sit on
the kerb at each stop line. The strip at the bottom is a scrubber: for a ring road it is a
space-time diagram (time across, position up); for a network it is mean speed over time
with the vehicle count as the area behind.

Regenerate the bundled samples with

    .venv/bin/python -m traffic ring --duration 400 --record-every 10 --js-var SAMPLES --name "ring road" --out www/samples/ring.js
    .venv/bin/python -m traffic grid --rate 0.08 --duration 300 --js-var SAMPLES --name "3×3 grid, signals" --out www/samples/grid.js

The ring scenario reproduces phantom traffic jams: a near-uniform flow breaks into
stop-and-go waves from a tiny perturbation.

## Layout

- `traffic/models.py` — `CarFollowingModel` protocol and the IDM implementation
- `traffic/network.py` — `Network` of `Node`s and directed `Road`s (lanes, speed limits, node radius), shortest paths
- `traffic/control.py` — intersection control: `Signal` (fixed or actuated, optional right on red), all-way `StopSign`, `Priority`
- `traffic/osm.py` — Overpass fetch and OSM-to-`Network` import
- `traffic/rules.py` — jurisdiction `Rules` (Dallas, New York, Netherlands)
- `traffic/sim.py` — `Vehicle`, `Lane`, `Simulation`: car following, lookahead across nodes, MOBIL-style lane changes, route transitions
- `traffic/demand.py` — origin-destination `Demand`, `Spawner` (Poisson arrivals, routed by shortest path)
- `traffic/metrics.py` — `Metrics` collector (delay, throughput, queues)
- `traffic/experiment.py` — `sweep` over parameters and seeds, CSV output
- `traffic/scenarios.py` — scenario builders (`ring_road`, `grid`) and the `SCENARIOS` registry
- `traffic/trace.py` — `TraceWriter`
- `traffic/__main__.py` — CLI
- `www/core.js` — pure trace logic (indexing, interpolation, road geometry, tile maths, colour ramp); tested with `node --test`
- `www/app.js` — canvas rendering, map tiles (OSM, inverted to dark), playback, controls
- `data/*.json` — cached OSM extracts
- `www/samples/*.js` — **generated** sample traces; never hand-edit

## Model notes

- Intersections have no interior length: a vehicle leaves one road and appears at the start of
  the next in the same step. Roads are trimmed back by the node's `radius` so stop lines sit at
  the edge of the drawn box, and the viewer runs a crossing vehicle straight on across it.
- Lookahead across a node sees the first vehicle on the next road, competing entrants from
  other approaches headed into the same lane (closer to the node goes first; entrants held at
  their own stop line are ignored), and the stop line itself when the control says stop.
- Crossing conflicts inside the box are not modelled; signals and all-way stops keep conflicting
  streams apart. Uncontrolled nodes only serialise merges.

## Trace format (version 2)

JSON. All units SI (metres, seconds). World coordinates are metres with y up. Positions are
front bumpers measured along the road. Lane 0 is the kerb lane.

```json
{
  "version": 2,
  "dt": 0.5,
  "network": {
    "geo": {"lat": 32.749, "lon": -96.828},
    "nodes": [{"id": "n0_0", "x": 0.0, "y": 0.0, "radius": 3.6, "control": "signal"}],
    "roads": [{"id": "a>b", "src": "a", "dst": "b", "length": 142.8, "lanes": 1, "ring": false,
               "kind": "residential", "points": [[3.6, 0.0], [146.4, 0.0]]}]
  },
  "vehicles": [{"id": 0, "length": 5.0}],
  "ticks": [
    {"t": 0.0, "v": [[0, 0, 0, 12.345, 11.9, -0.02]], "s": [[0, 3, "g"]]}
  ]
}
```

- `dt` — seconds between consecutive ticks
- `network.geo` — lat/lon of the world origin, or null for synthetic networks
- `network.nodes` / `network.roads` — indexed by position in their arrays; `control` is
  `signal`, `stop`, `priority` or null; a ring road has `ring: true` and no nodes
- `vehicles` — static per-vehicle data, keyed by `id`
- `ticks[].v` — one row per vehicle present: `[id, road_index, lane, position, speed, accel]`
- `ticks[].s` — signal states, one row per controlled approach: `[node_index, road_index, state]`
  with state `g`, `y`, `r`, `s` (stop sign), `p` (yield) or `m` (major road, no control)

Vehicles may be absent from a tick (they have not entered or have exited). The viewer still
reads version 1 traces.

## Background

- https://en.wikipedia.org/wiki/Traffic_simulation
- Intelligent Driver Model (Treiber, Hennecke, Helbing 2000)
- Gipps' model, Nagel–Schreckenberg cellular automaton (planned as alternative models)
