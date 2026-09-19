import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const C = createRequire(import.meta.url)('../www/core.js');

const ring = {
  version: 2, dt: 1,
  network: { nodes: [], roads: [{ id: 'ring', length: 100, ring: true, lanes: 1, points: [] }] },
  vehicles: [{ id: 0, length: 5 }, { id: 1, length: 5 }],
  ticks: [
    { t: 0, v: [[0, 0, 0, 10, 10, 0], [1, 0, 0, 95, 10, 0]] },
    { t: 1, v: [[0, 0, 0, 20, 10, 0], [1, 0, 0, 5, 10, 0]] },
    { t: 2, v: [[0, 0, 0, 30, 0, -2]] },
  ],
};

const net = {
  version: 2, dt: 1,
  network: {
    nodes: [{ id: 'a', x: 0, y: 0, control: null }, { id: 'b', x: 100, y: 0, control: 'signal' }, { id: 'c', x: 100, y: 100, control: null }],
    roads: [
      { id: 'ab', src: 'a', dst: 'b', length: 100, lanes: 2, ring: false, points: [[0, 0], [100, 0]] },
      { id: 'bc', src: 'b', dst: 'c', length: 100, lanes: 1, ring: false, points: [[100, 0], [100, 100]] },
    ],
  },
  vehicles: [{ id: 7, length: 5 }],
  ticks: [
    { t: 0, v: [[7, 0, 1, 90, 10, 0]], s: [[1, 0, 'g']] },
    { t: 1, v: [[7, 1, 0, 5, 10, 0]], s: [[1, 0, 'y']] },
  ],
};

test('findTick clamps and bisects', () => {
  const times = [0, 1, 2, 5];
  assert.equal(C.findTick(times, -1), 0);
  assert.equal(C.findTick(times, 0), 0);
  assert.equal(C.findTick(times, 1.5), 1);
  assert.equal(C.findTick(times, 2), 2);
  assert.equal(C.findTick(times, 99), 3);
});

test('lerpPos takes the short way round a ring', () => {
  assert.equal(C.lerpPos(95, 5, 100, true, 0.5), 0);
  assert.equal(C.lerpPos(95, 5, 100, true, 0.25), 97.5);
  assert.equal(C.lerpPos(95, 5, 100, false, 0.5), 50);
});

test('sample interpolates position and speed, wraps across the seam', () => {
  const idx = C.index(ring);
  const at = t => Object.fromEntries(C.sample(idx, t).map(v => [v.id, v]));
  assert.equal(at(0.5)[0].pos, 15);
  assert.equal(at(0.5)[1].pos, 0);
  assert.equal(at(1.5)[0].speed, 5);
  assert.equal(at(1.5)[1].pos, 5, 'vehicle without a successor holds its tick value');
  assert.equal(at(2)[1], undefined, 'and is gone once its last tick is passed');
  assert.equal(idx.duration, 2);
  assert.equal(idx.vmax, 10);
});

test('sample carries a vehicle across a road change and slides between lanes', () => {
  const idx = C.index(net);
  const v = C.sample(idx, 0.5)[0];
  assert.equal(v.road, 0);
  assert.equal(v.pos, 97.5, 'halfway from 90 on ab to 5 on bc: 15 m of travel');
  assert.equal(v.lane, 1);
  assert.equal(v.lateral, 0, 'no lateral slide when the road changes');
});

test('v1 traces are normalised to v2 rows', () => {
  const v1 = {
    version: 1, dt: 1, network: { roads: [{ id: 'r', length: 50, ring: true }] },
    vehicles: [{ id: 0, length: 5 }], ticks: [{ t: 0, v: [[0, 0, 10, 3, 0]] }],
  };
  const idx = C.index(v1);
  assert.deepEqual(idx.ticks[0].v[0], [0, 0, 0, 10, 3, 0]);
  assert.equal(idx.roads[0].lanes, 1);
});

test('ringXY starts at the top (y up) and runs clockwise', () => {
  const a = C.ringXY(0, 100), b = C.ringXY(25, 100);
  assert.ok(Math.abs(a.x) < 1e-9 && a.y > 0);
  assert.ok(b.x > 0 && Math.abs(b.y) < 1e-9);
  assert.ok(Math.abs(a.dx - 1) < 1e-9 && Math.abs(a.dy) < 1e-9, 'moving east at the top');
});

test('pointAt offsets lanes to the right of travel', () => {
  const idx = C.index(net);
  const ab = idx.roads[0];
  const kerb = C.pointAt(ab, 50, 0), inner = C.pointAt(ab, 50, 1);
  assert.equal(kerb.x, 50);
  assert.ok(kerb.y < inner.y && inner.y < 0, 'eastbound: right is -y; kerb lane is furthest right');
  assert.equal(inner.y, -C.LANE_W / 2);
  const bc = C.pointAt(idx.roads[1], 100, 0);
  assert.ok(Math.abs(bc.y - 100) < 1e-9 && bc.x > 100, 'northbound: right is +x');
  assert.deepEqual([bc.dx, bc.dy], [0, 1]);
});

test('signals map by node and road', () => {
  const idx = C.index(net);
  assert.equal(C.signals(idx, 0).get('1,0'), 'g');
  assert.equal(C.signals(idx, 1.5).get('1,0'), 'y');
  assert.deepEqual(idx.series.map(s => s.n), [1, 1]);
});

test('colorRamp endpoints and speedColor clamping', () => {
  const lut = C.colorRamp(['#000000', '#ffffff'], 3);
  assert.deepEqual(lut, ['rgb(0,0,0)', 'rgb(128,128,128)', 'rgb(255,255,255)']);
  assert.equal(C.speedColor(lut, -5, 10), lut[0]);
  assert.equal(C.speedColor(lut, 50, 10), lut[2]);
  assert.equal(C.speedColor(lut, 5, 10), lut[1]);
});

test('pointAt runs straight on past the end of a road', () => {
  const idx = C.index(net);
  const p = C.pointAt(idx.roads[0], 110, 1);
  assert.ok(Math.abs(p.x - 110) < 1e-9);
  assert.equal(p.y, -C.LANE_W / 2);
});
