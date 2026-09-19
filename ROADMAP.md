# ROADMAP.md — Development Roadmap

Open work only; completed items are removed as they land (see git history).

---

## Architecture

Python simulation core writes a trace file; a vanilla-JS canvas viewer plays
it back. No server needed for playback, so the viewer deploys statically.
Network and trace formats are plain JSON and are the contract between the
core, the viewer, and the map repos.

## Real places

- [ ] Check inferred signals and stop control against the ground around Vernon & Ferndale; per-place overrides file
- [ ] US 67 and its ramps sit in the south-west corner of the Vernon box with no merge lanes or ramp metering
- [ ] Merge sub-5 m segments left by node trimming (62 in Oak Cliff)
- [ ] Turn restrictions from OSM relations; `turn:lanes`
- [ ] Netherlands-style priority to the right at uncontrolled equal junctions
- [ ] More places: a Netherlands town, a Manhattan grid; Dallas arterial corridor
- [ ] Demand from real counts (TxDOT AADT) instead of class weights

## Experiments

- [ ] Time-varying demand (peak profiles) and per-trip departure-time output
- [ ] Route choice under congestion (currently free-flow shortest path only)
- [ ] Viewer: colour roads by metrics (mean speed, queue) from a summary file
- [ ] Parquet output once pandas/pyarrow is worth adding

## Intersections

- [ ] Interior geometry: turn paths and crossing time instead of a zero-length node
- [ ] Crossing-conflict handling at uncontrolled nodes (currently only merges are serialised)
- [ ] Turn lanes: restrict which lanes may continue onto which next road
- [ ] Signal offsets / coordination along a corridor

## Scale

- [ ] Vectorize core with numpy arrays instead of per-vehicle objects
- [ ] Binary trace format
- [ ] Level-of-detail rendering in the viewer
- [ ] City-wide Dallas run

## Deferred

- Gipps and Nagel-Schreckenberg models: pluggable slot exists from the start, implement after IDM is solid
- Live websocket mode between core and viewer: trace playback covers the need until interactive tuning matters
