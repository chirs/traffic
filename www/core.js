'use strict';
// Pure trace logic: no DOM or canvas. Loaded as a classic script; also require()-able for tests.
const TrafficCore = (() => {
  function index(trace) {
    const ticks = trace.ticks;
    const times = ticks.map(k => k.t);
    const maps = ticks.map(k => new Map(k.v.map(r => [r[0], r])));
    const lengths = new Map(trace.vehicles.map(v => [v.id, v.length]));
    let vmax = 0;
    for (const k of ticks) for (const r of k.v) if (r[3] > vmax) vmax = r[3];
    return {
      trace, ticks, times, maps, lengths,
      vmax: Math.max(1, vmax),
      duration: times[times.length - 1],
      roads: trace.network.roads,
    };
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

  // Vehicle states at time t, interpolated between the surrounding ticks.
  function sample(idx, t) {
    const i = findTick(idx.times, t);
    const a = idx.ticks[i], b = idx.ticks[i + 1];
    const f = b ? Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t))) : 0;
    const next = b ? idx.maps[i + 1] : null;
    const out = [];
    for (const r of a.v) {
      const road = idx.roads[r[1]];
      const nb = next && next.get(r[0]);
      let pos = r[2], speed = r[3], accel = r[4];
      if (nb && nb[1] === r[1]) {
        pos = lerpPos(r[2], nb[2], road.length, road.ring, f);
        speed = r[3] + (nb[3] - r[3]) * f;
        accel = r[4] + (nb[4] - r[4]) * f;
      }
      out.push({ id: r[0], road: r[1], pos, speed, accel, length: idx.lengths.get(r[0]) ?? 5 });
    }
    return out;
  }

  // World coordinates (metres) of a point s along a ring of circumference L,
  // centred at the origin, s=0 at the top, increasing clockwise (canvas y is down).
  function ringXY(s, L) {
    const R = L / (2 * Math.PI);
    const th = (s / L) * 2 * Math.PI - Math.PI / 2;
    return { x: R * Math.cos(th), y: R * Math.sin(th), heading: th + Math.PI / 2, R };
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

  return { index, findTick, lerpPos, sample, ringXY, stats, colorRamp, speedColor };
})();

if (typeof module !== 'undefined') module.exports = TrafficCore;
