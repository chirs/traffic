'use strict';
// Pure trace logic: no DOM or canvas. Loaded as a classic script; also require()-able for tests.
// World coordinates are metres with y up; the renderer flips y.
const TrafficCore = (() => {
  const LANE_W = 3.6;

  // Trace v1 rows were [id, road, pos, speed, accel]; v2 adds lane: [id, road, lane, pos, speed, accel].
  function normalise(trace) {
    if ((trace.version || 1) >= 2) return trace;
    return {
      ...trace, version: 2,
      network: {
        nodes: [],
        roads: trace.network.roads.map(r => ({ lanes: 1, points: [], src: null, dst: null, ...r })),
      },
      ticks: trace.ticks.map(k => ({ t: k.t, v: k.v.map(r => [r[0], r[1], 0, r[2], r[3], r[4]]) })),
    };
  }

  function index(raw) {
    const trace = normalise(raw);
    const ticks = trace.ticks;
    const times = ticks.map(k => k.t);
    const maps = ticks.map(k => new Map(k.v.map(r => [r[0], r])));
    const lengths = new Map(trace.vehicles.map(v => [v.id, v.length]));
    let vmax = 0;
    for (const k of ticks) for (const r of k.v) if (r[4] > vmax) vmax = r[4];
    const roads = trace.network.roads.map(roadGeometry);
    return {
      trace, ticks, times, maps, lengths, roads,
      staticStates: new Map((trace.static_states || []).map(([n, r, s]) => [`${n},${r}`, s])),
      nodes: trace.network.nodes,
      geo: trace.network.geo || null,
      units: trace.network.units || 'mph',
      vmax: Math.max(1, vmax),
      duration: times[times.length - 1],
      bounds: bounds(roads),
      series: series(ticks),
    };
  }

  // Precompute cumulative lengths so pointAt() can walk a polyline.
  function roadGeometry(road) {
    const pts = road.points || [];
    const cum = [0];
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      cum.push(cum[i - 1] + Math.hypot(x1 - x0, y1 - y0));
    }
    return { ...road, pts, cum, geomLength: cum[cum.length - 1] || road.length };
  }

  // World coordinates (metres) of a point s along a ring of circumference L, centred at the
  // origin, s=0 at the top, running clockwise on screen. Returns unit direction too.
  function ringXY(s, L) {
    const R = L / (2 * Math.PI);
    const phi = (s / L) * 2 * Math.PI;
    return { x: R * Math.sin(phi), y: R * Math.cos(phi), dx: Math.cos(phi), dy: -Math.sin(phi), R };
  }

  // Position and unit direction at distance s along a road's centreline, offset to the right
  // for a lane (lane 0 is the kerb lane, lanes-1 the innermost).
  function pointAt(road, s, lane = 0, lateral = 0) {
    let p;
    if (road.ring) {
      p = ringXY(s, road.length);
    } else {
      const { pts, cum } = road;
      const sg = (s / road.length) * road.geomLength; // map road length onto drawn length
      let i = 1;
      while (i < cum.length - 1 && cum[i] < sg) i++;
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      const seg = cum[i] - cum[i - 1] || 1;
      // not clamped: a vehicle crossing to its next road between ticks runs straight on past the end
      const f = Math.max(0, (sg - cum[i - 1]) / seg);
      p = { x: x0 + (x1 - x0) * f, y: y0 + (y1 - y0) * f, dx: (x1 - x0) / seg, dy: (y1 - y0) / seg };
    }
    const off = (road.lanes - lane - 0.5) * LANE_W + lateral; // to the right of travel
    return { x: p.x + p.dy * off, y: p.y - p.dx * off, dx: p.dx, dy: p.dy };
  }

  function bounds(roads) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const r of roads) {
      if (r.ring) {
        const R = ringXY(0, r.length).R + r.lanes * LANE_W;
        x0 = Math.min(x0, -R); y0 = Math.min(y0, -R); x1 = Math.max(x1, R); y1 = Math.max(y1, R);
      }
      for (const [x, y] of r.pts) {
        x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
      }
    }
    const m = 3 * LANE_W;
    return { x0: x0 - m, y0: y0 - m, x1: x1 + m, y1: y1 + m };
  }

  // Per-tick aggregate: vehicle count and mean speed (for the network strip chart).
  function series(ticks) {
    return ticks.map(k => {
      let sum = 0;
      for (const r of k.v) sum += r[4];
      return { n: k.v.length, mean: k.v.length ? sum / k.v.length : 0 };
    });
  }

  // Largest i with times[i] <= t (clamped to the ends).
  function findTick(times, t) {
    let lo = 0, hi = times.length - 1;
    if (t <= times[0]) return 0;
    if (t >= times[hi]) return hi;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (times[mid] <= t) lo = mid; else hi = mid;
    }
    return lo;
  }

  // Interpolate a position, taking the short way round on a ring.
  function lerpPos(a, b, length, ring, f) {
    let d = b - a;
    if (ring) {
      if (d < -length / 2) d += length;
      else if (d > length / 2) d -= length;
    }
    let p = a + d * f;
    if (ring) { p %= length; if (p < 0) p += length; }
    return p;
  }

  // Vehicle states at time t, interpolated between the surrounding ticks. A vehicle that moves
  // to another road between ticks is carried past the end of its current one, so it keeps moving.
  function sample(idx, t) {
    const i = findTick(idx.times, t);
    const a = idx.ticks[i], b = idx.ticks[i + 1];
    const f = b ? Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t))) : 0;
    const next = b ? idx.maps[i + 1] : null;
    const out = [];
    for (const r of a.v) {
      const road = idx.roads[r[1]];
      const nb = next && next.get(r[0]);
      let pos = r[3], speed = r[4], accel = r[5], lane = r[2], lateral = 0;
      if (nb) {
        speed = r[4] + (nb[4] - r[4]) * f;
        accel = r[5] + (nb[5] - r[5]) * f;
        if (nb[1] === r[1]) {
          pos = lerpPos(r[3], nb[3], road.length, road.ring, f);
          if (nb[2] !== r[2]) lateral = (r[2] - nb[2]) * LANE_W * (1 - f); // slide between lanes
        } else {
          pos = r[3] + (road.length - r[3] + nb[3]) * f; // crossing onto the next road
        }
      }
      out.push({ id: r[0], road: r[1], lane, pos, speed, accel, lateral, length: idx.lengths.get(r[0]) ?? 5 });
    }
    return out;
  }

  // Control states at time t as a Map "node,road" -> state: static ones plus this tick's signals.
  function signals(idx, t) {
    const k = idx.ticks[findTick(idx.times, t)];
    const out = new Map(idx.staticStates);
    for (const [n, r, s] of k.s || []) out.set(`${n},${r}`, s);
    return out;
  }

  // Local equirectangular projection used by the Python side: metres east/north of (lat0, lon0).
  const EARTH_R = 6371008.8;
  function projection(geo) {
    const kx = EARTH_R * Math.cos(geo.lat * Math.PI / 180) * Math.PI / 180, ky = EARTH_R * Math.PI / 180;
    return {
      toWorld: (lat, lon) => ({ x: (lon - geo.lon) * kx, y: (lat - geo.lat) * ky }),
      toLonLat: (x, y) => ({ lon: geo.lon + x / kx, lat: geo.lat + y / ky }),
    };
  }
  // Web Mercator tile maths (256 px tiles).
  function tileToLonLat(z, x, y) {
    const n = 2 ** z;
    return { lon: x / n * 360 - 180, lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI };
  }
  function lonLatToTile(z, lon, lat) {
    const n = 2 ** z, r = lat * Math.PI / 180;
    return { x: (lon + 180) / 360 * n, y: (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n };
  }
  // Zoom whose tile pixels best match `scale` screen px per metre at this latitude.
  function tileZoom(scale, lat) {
    const z = Math.log2(156543.03392 * Math.cos(lat * Math.PI / 180) * scale);
    return Math.max(0, Math.min(19, Math.round(z)));
  }

  function stats(vehicles) {
    const n = vehicles.length;
    if (!n) return { n: 0, mean: 0, min: 0 };
    let sum = 0, min = Infinity;
    for (const v of vehicles) { sum += v.speed; if (v.speed < min) min = v.speed; }
    return { n, mean: sum / n, min };
  }

  function parseHex(h) {
    const s = h.replace('#', '');
    const v = parseInt(s.length === 3 ? s.split('').map(c => c + c).join('') : s, 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }

  // n colours interpolated evenly through the given hex stops.
  function colorRamp(stops, n) {
    const rgb = stops.map(parseHex);
    const out = [];
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * (rgb.length - 1);
      const j = Math.min(rgb.length - 2, Math.floor(x)), f = x - j;
      const c = rgb[j].map((a, k) => Math.round(a + (rgb[j + 1][k] - a) * f));
      out.push(`rgb(${c[0]},${c[1]},${c[2]})`);
    }
    return out;
  }

  function speedColor(lut, speed, vmax) {
    const i = Math.floor((speed / vmax) * (lut.length - 1));
    return lut[Math.max(0, Math.min(lut.length - 1, i))];
  }

  return { LANE_W, normalise, index, findTick, lerpPos, sample, signals, ringXY, pointAt, stats, colorRamp, speedColor,
    projection, tileToLonLat, lonLatToTile, tileZoom };
})();

if (typeof module !== 'undefined') module.exports = TrafficCore;
