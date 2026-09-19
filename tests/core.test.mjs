import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const C = createRequire(import.meta.url)('../www/core.js');

const trace = {
  version: 1, dt: 1,
  network: { roads: [{ id: 'ring', length: 100, ring: true }] },
  vehicles: [{ id: 0, length: 5 }, { id: 1, length: 5 }],
  ticks: [
    { t: 0, v: [[0, 0, 10, 10, 0], [1, 0, 95, 10, 0]] },
    { t: 1, v: [[0, 0, 20, 10, 0], [1, 0, 5, 10, 0]] },
    { t: 2, v: [[0, 0, 30, 0, -2]] },
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
  const idx = C.index(trace);
  const at = t => Object.fromEntries(C.sample(idx, t).map(v => [v.id, v]));
  assert.equal(at(0.5)[0].pos, 15);
  assert.equal(at(0.5)[1].pos, 0);
  assert.equal(at(1.5)[0].speed, 5);
  assert.equal(at(1.5)[1].pos, 5, 'vehicle without a successor holds its tick value');
  assert.equal(at(2)[1], undefined, 'and is gone once its last tick is passed');
  assert.equal(idx.duration, 2);
  assert.equal(idx.vmax, 10);
});

test('ringXY starts at the top and runs clockwise', () => {
  const a = C.ringXY(0, 100), b = C.ringXY(25, 100);
  assert.ok(Math.abs(a.x) < 1e-9 && a.y < 0);
  assert.ok(b.x > 0 && Math.abs(b.y) < 1e-9);
  assert.ok(Math.abs(a.heading) < 1e-9, 'heading at top points +x');
});

test('colorRamp endpoints and speedColor clamping', () => {
  const lut = C.colorRamp(['#000000', '#ffffff'], 3);
  assert.deepEqual(lut, ['rgb(0,0,0)', 'rgb(128,128,128)', 'rgb(255,255,255)']);
  assert.equal(C.speedColor(lut, -5, 10), lut[0]);
  assert.equal(C.speedColor(lut, 50, 10), lut[2]);
  assert.equal(C.speedColor(lut, 5, 10), lut[1]);
});
