# traffic

Microscopic traffic simulator. Python core writes a trace file; a vanilla-JS canvas
viewer plays it back over real streets. See [ROADMAP.md](ROADMAP.md).

## Setup

    uv sync
    .venv/bin/pytest
    node --test tests/
    .venv/bin/python -m traffic ring --vehicles 40 --duration 600 --out traces/ring.json
    .venv/bin/python -m traffic grid --rows 3 --cols 3 --control signal --rate 0.08 --out traces/grid.json
    .venv/bin/python -m traffic place --name vernon_ferndale --rules dallas --rate 1.0 --out traces/vernon.json
    .venv/bin/python -m traffic place --summary results/vernon.json
    .venv/bin/python -m traffic sweep grid --param control=signal,actuated,stop --param rate=0.04,0.08 --seeds 5 --workers 4 --out results/sweep.csv

Scenarios: `ring` reproduces phantom traffic jams (a near-uniform flow breaks into stop-and-go
waves from a tiny perturbation); `grid` is a street grid with controlled intersections
(`--control signal|actuated|stop|none`, `--lanes N`); `place` is real streets from
OpenStreetMap. `--out` writes a trace for the viewer, `--summary` writes run metrics, and
`sweep` runs every combination of the given parameter values across seeds, writes one CSV
row per run and prints the means.

## Viewer

Open `www/index.html` directly (bundled samples in `www/samples/`) or serve `www/` and pass
`?trace=path.json`. Drag a trace onto the page or use "open trace" to load another.
Space plays, arrows step (shift for ten ticks), `[` `]` change speed, scroll zooms, drag
pans, `f` refits, `m` toggles the map. Cars are coloured by speed and show brake lights;
lamps on the kerb at each stop line show signal state (red, yellow, green), stop signs and
yields. Traces with a geographic origin get OpenStreetMap tiles underneath, inverted to stay
dark. The strip at the bottom is a scrubber: for a ring road it is a space-time diagram (time
across, position up); for a network it is mean speed over time with the vehicle count as the
area behind.

Regenerate the bundled samples with

    .venv/bin/python -m traffic ring --duration 400 --record-every 10 --js-var SAMPLES --label "ring road" --out www/samples/ring.js
    .venv/bin/python -m traffic grid --rate 0.08 --duration 300 --js-var SAMPLES --label "3×3 grid, signals" --out www/samples/grid.js
    .venv/bin/python -m traffic place --name oak_cliff --rate 0.6 --duration 300 --record-every 10 --js-var SAMPLES --label "Oak Cliff, Dallas" --out www/samples/oak_cliff.js
    .venv/bin/python -m traffic place --name vernon_ferndale --rate 1.0 --duration 300 --record-every 10 --js-var SAMPLES --label "Vernon & Ferndale, Oak Cliff" --out www/samples/vernon_ferndale.js

## Real streets

`place` builds a network from an OpenStreetMap extract. Extracts are fetched from the
Overpass API once and cached under `data/` (the Dallas ones are checked in). Ways are clipped
to the bbox and split at shared nodes into intersection-to-intersection roads with their
polyline geometry; two-way ways become two roads; coordinates are projected to metres around
the bbox centre (x east, y north) and the trace carries the origin as `network.geo`.

A `Rules` object (`traffic/rules.py`) supplies what the map doesn't: default speed limits and
lanes per road class, the unit of a bare `maxspeed`, whether right on red is allowed, signal
timing, and when to assume a signal (Dallas OSM data rarely tags them: a signal is assumed
where a road of at least `secondary` crosses one of at least `tertiary`). Dallas, New York and
Netherlands rule sets are data.

Controls come from tags and classes: `traffic_signals` nodes (or inferred crossings) get an
actuated two-phase signal grouped by bearing; `stop` nodes give an all-way stop; where classes
differ, the minor road yields (`Priority`, a four-second gap); same-class junctions of three or
more approaches are all-way stops. Traffic enters and leaves at dead ends within 40 m of the
bbox edge, weighted by road class and lanes.

Places so far: `vernon_ferndale` (Oak Cliff from Illinois Avenue north to 12th Street,
centred on Vernon and Ferndale; the default) and `oak_cliff` (Bishop Arts). Add one by putting
its bbox in `PLACES` in `traffic/scenarios.py`; the extract is fetched on first use.

## Demand and metrics

Demand is an origin-destination matrix `{(origin_node, dest_node): vehicles_per_second}`
(`grid(demand=...)`; `uniform_demand()` builds the grid default, `place` weights boundary
nodes by road class). Arrivals are Poisson; an arrival that finds its entry road full waits in
a queue and keeps its destination.

`Metrics` reports totals (throughput per hour, mean travel time, mean delay against
free-flow time, space-mean speed), per road (throughput, mean vehicles, mean stopped,
density per km), per node (throughput, mean queue within 50 m of the line) and one row
per completed trip.

## Layout

- `traffic/models.py` — `CarFollowingModel` protocol and the IDM implementation
- `traffic/network.py` — `Network` of `Node`s and directed polyline `Road`s (lanes, speed limits, node radius), shortest paths, turn classification
- `traffic/control.py` — intersection control: `Signal` (fixed or actuated, optional right on red), all-way `StopSign`, `Priority`
- `traffic/osm.py` — Overpass fetch and OSM-to-`Network` import
- `traffic/rules.py` — jurisdiction `Rules` (Dallas, New York, Netherlands)
- `traffic/sim.py` — `Vehicle`, `Lane`, `Simulation`: car following, route lookahead, MOBIL-style lane changes, road transitions
- `traffic/demand.py` — origin-destination `Demand`, `Spawner` (Poisson arrivals, routed by shortest path)
- `traffic/metrics.py` — `Metrics` collector (delay, throughput, queues)
- `traffic/experiment.py` — `sweep` over parameters and seeds, CSV output
- `traffic/scenarios.py` — scenario builders (`ring_road`, `grid`, `osm_area`/`place`), `PLACES`, the `SCENARIOS` registry
- `traffic/trace.py` — `TraceWriter`
- `traffic/__main__.py` — CLI
- `www/core.js` — pure trace logic (indexing, interpolation, road geometry, tile maths, colour ramp); tested with `node --test`
- `www/app.js` — canvas rendering, map tiles, playback, controls
- `data/*.json` — cached OSM extracts
- `www/samples/*.js` — **generated** sample traces; never hand-edit

## Model notes

- Intersections have no interior length: a vehicle leaves one road and appears at the start of
  the next in the same step. Roads are trimmed back by the node's `radius` so stop lines sit at
  the edge of the drawn box, and the viewer runs a crossing vehicle straight on across it.
- A vehicle looks up to 80 m along its route past the end of its road. It sees the first
  vehicle on a later road, competing entrants from other approaches headed into the same lane
  (closer to the node goes first; entrants held at their own stop line are ignored), and the
  first stop line where a control says stop. Right on red also waits for a gap in the traffic
  bound for the same road.
- Lane changes are MOBIL-style (safety limit, politeness, cooldown) and are not attempted
  within 20 m of either end of a road.
- Braking is capped at 9 m/s²; vehicles aim to halt a metre short of a stop line because IDM
  only reaches zero speed asymptotically.
- Crossing conflicts inside the box are not modelled; signals and all-way stops keep conflicting
  streams apart. Uncontrolled and priority nodes only serialise merges.

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
  "static_states": [[4, 9, "s"]],
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
- `static_states` — `[node_index, road_index, state]` for controls that never change
  (`s` stop sign, `p` yield, `m` major road with priority)
- `vehicles` — static per-vehicle data, keyed by `id`
- `ticks[].v` — one row per vehicle present: `[id, road_index, lane, position, speed, accel]`
- `ticks[].s` — signal states this tick: `[node_index, road_index, state]` with `g`, `y` or `r`

Vehicles may be absent from a tick (they have not entered or have exited). The viewer still
reads version 1 traces.

## Background

- https://en.wikipedia.org/wiki/Traffic_simulation
- Intelligent Driver Model (Treiber, Hennecke, Helbing 2000)
- Gipps' model, Nagel–Schreckenberg cellular automaton (planned as alternative models)
