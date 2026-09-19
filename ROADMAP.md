# ROADMAP.md — Development Roadmap

Open work only; completed items are removed as they land (see git history).

---

## Architecture

Python simulation core writes a trace file; a vanilla-JS canvas viewer plays
it back. No server needed for playback, so the viewer deploys statically.
Network and trace formats are plain JSON and are the contract between the
core, the viewer, and the map repos.

## Core: single road

- [ ] Project scaffold: `pyproject.toml`, `.venv`, ruff, pytest
- [ ] `CarFollowingModel` protocol; IDM as first implementation
- [ ] `Vehicle`, `Lane`, `Road` with fixed-timestep integration, seeded RNG
- [ ] Ring road scenario reproducing phantom jams
- [ ] Trace writer (per-tick vehicle positions, speeds; JSON to start)
- [ ] Tests: no collisions, vehicle count conserved, jam emerges at known density
- [ ] Document network and trace JSON formats in README

## Viewer

- [ ] Vanilla JS canvas app under `www/`, no build step
- [ ] Load a trace, play/pause, scrub, speed control
- [ ] Interpolate between ticks for smooth motion
- [ ] Ring road and straight road rendering
- [ ] Visual polish: brake lights, speed/density coloring

## Network

- [ ] Directed graph of roads; nodes are intersections
- [ ] Routes as edge lists; vehicles transition between roads
- [ ] Lane changing (MOBIL or simplified)
- [ ] Intersection control: stop signs, fixed-cycle signals, actuated signals
- [ ] Synthetic grid scenario
- [ ] Viewer draws the network graph and signal states

## Demand and experiments

- [ ] Origin/destination matrix with Poisson arrivals
- [ ] Route choice by shortest path
- [ ] Metrics: throughput, mean delay, queue length per edge and intersection
- [ ] Monte Carlo runner: sweep seeds and parameters, aggregate to CSV/parquet

## Real Dallas

- [ ] OSM import via `osmnx` into the network format
- [ ] First neighborhood scenario (Oak Cliff)
- [ ] Map tiles under the canvas in the viewer
- [ ] `Rules` object for jurisdiction behavior (speed limits, right on red, priority); Dallas first
- [ ] Netherlands and New York rule sets

## Scale

- [ ] Vectorize core with numpy arrays instead of per-vehicle objects
- [ ] Binary trace format
- [ ] Level-of-detail rendering in the viewer
- [ ] City-wide Dallas run

## Deferred

- Gipps and Nagel-Schreckenberg models: pluggable slot exists from the start, implement after IDM is solid
- Live websocket mode between core and viewer: trace playback covers the need until interactive tuning matters
