'use strict';
(() => {
  const C = TrafficCore;
  const $ = id => document.getElementById(id);
  const scene = $('scene'), sctx = scene.getContext('2d');
  const strip = $('strip'), stctx = strip.getContext('2d');
  const css = getComputedStyle(document.documentElement);
  const tok = n => css.getPropertyValue(n).trim();
  const PAL = {
    bg: tok('--bg'), road: tok('--road'), edge: tok('--edge'), lane: tok('--lane'), grid: tok('--grid'),
    stop: tok('--v-stop'), slow: tok('--v-slow'), free: tok('--v-free'), brake: tok('--brake'),
    amber: tok('--amber'), faint: tok('--faint'), dim: tok('--dim'), text: tok('--text'),
  };
  const LUT = C.colorRamp([PAL.stop, PAL.slow, PAL.free], 64);
  const LANE_W = 3.6, CAR_W = 2.2, RATES = [0.25, 0.5, 1, 2, 4, 8, 16];

  const S = {
    idx: null, t: 0, playing: true, rate: 1,
    cam: { scale: 1, x: 0, y: 0 }, // world metres -> screen px; (x,y) is the world point at view centre
    drag: null, last: 0, W: 0, H: 0, DPR: 1, stripCache: null,
  };

  // ---- loading -------------------------------------------------------------
  function load(trace, name) {
    S.idx = C.index(trace);
    S.t = 0; S.playing = true; S.stripCache = null;
    const r = S.idx.roads[0];
    $('sub').textContent = `${name} · ${r.ring ? 'ring' : 'road'} ${r.length} m · ` +
      `${trace.vehicles.length} vehicles · ${fmtTime(S.idx.duration)}`;
    fitCamera();
    syncPlay();
  }
  function readFile(file) {
    if (!file) return;
    file.text().then(txt => load(JSON.parse(txt), file.name))
      .catch(err => { $('sub').textContent = `could not read ${file.name}: ${err.message}`; });
  }

  // ---- geometry ------------------------------------------------------------
  function worldBounds() {
    const r = S.idx.roads[0];
    if (r.ring) { const R = C.ringXY(0, r.length).R + LANE_W; return { x0: -R, y0: -R, x1: R, y1: R }; }
    return { x0: 0, y0: -LANE_W * 3, x1: r.length, y1: LANE_W * 3 };
  }
  function viewCentre() {
    const bottom = $('.bottom') || document.querySelector('.bottom');
    const bh = bottom.getBoundingClientRect().height + 18;
    return { cx: S.W / 2, cy: (S.H - bh + 70) / 2, availH: S.H - bh - 70 };
  }
  function fitCamera() {
    if (!S.idx) return;
    const b = worldBounds(), v = viewCentre();
    S.cam.scale = 0.9 * Math.min(S.W / (b.x1 - b.x0), v.availH / (b.y1 - b.y0));
    S.cam.x = (b.x0 + b.x1) / 2; S.cam.y = (b.y0 + b.y1) / 2;
  }
  function toScreen(wx, wy) {
    const v = viewCentre();
    return { x: v.cx + (wx - S.cam.x) * S.cam.scale, y: v.cy + (wy - S.cam.y) * S.cam.scale };
  }
  function vehicleWorld(v) {
    const road = S.idx.roads[v.road];
    const centre = v.pos - v.length / 2;
    if (road.ring) return C.ringXY(centre, road.length);
    return { x: centre, y: 0, heading: 0 };
  }

  // ---- scene ---------------------------------------------------------------
  function drawScene() {
    const ctx = sctx;
    ctx.clearRect(0, 0, S.W, S.H);
    if (!S.idx) {
      ctx.fillStyle = PAL.dim; ctx.font = '14px IBM Plex Mono, monospace'; ctx.textAlign = 'center';
      ctx.fillText('no trace loaded', S.W / 2, S.H / 2);
      return;
    }
    const road = S.idx.roads[0], sc = S.cam.scale;
    drawRoad(ctx, road, sc);
    const vehicles = C.sample(S.idx, S.t);
    for (const v of vehicles) {
      const w = vehicleWorld(v), p = toScreen(w.x, w.y);
      const len = Math.max(v.length * sc, 4), wid = Math.max(CAR_W * sc, 2.5);
      ctx.save();
      ctx.translate(p.x, p.y); ctx.rotate(w.heading);
      ctx.fillStyle = C.speedColor(LUT, v.speed, S.idx.vmax);
      ctx.beginPath(); ctx.roundRect(-len / 2, -wid / 2, len, wid, Math.min(2, wid / 3)); ctx.fill();
      if (v.accel < -0.6 && wid >= 3) {
        ctx.fillStyle = PAL.brake;
        const d = Math.max(1, wid * 0.28);
        ctx.fillRect(-len / 2, -wid / 2, d, d);
        ctx.fillRect(-len / 2, wid / 2 - d, d, d);
      }
      ctx.restore();
    }
    updateHud(vehicles);
  }
  function drawRoad(ctx, road, sc) {
    ctx.lineCap = 'butt';
    if (road.ring) {
      const R = C.ringXY(0, road.length).R, c = toScreen(0, 0);
      ctx.strokeStyle = PAL.road; ctx.lineWidth = LANE_W * sc;
      ctx.beginPath(); ctx.arc(c.x, c.y, R * sc, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = PAL.edge; ctx.lineWidth = 1;
      for (const rr of [R - LANE_W / 2, R + LANE_W / 2]) {
        ctx.beginPath(); ctx.arc(c.x, c.y, rr * sc, 0, Math.PI * 2); ctx.stroke();
      }
      // distance ticks every 100 m, labelled at 0
      ctx.strokeStyle = PAL.lane; ctx.fillStyle = PAL.dim;
      ctx.font = '10px IBM Plex Mono, monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (let s = 0; s < road.length; s += 100) {
        const a = C.ringXY(s, road.length), r0 = (R + LANE_W / 2) * sc + 3, r1 = r0 + 6;
        const ux = a.x / R, uy = a.y / R;
        ctx.beginPath(); ctx.moveTo(c.x + ux * r0, c.y + uy * r0); ctx.lineTo(c.x + ux * r1, c.y + uy * r1); ctx.stroke();
        if (s === 0) ctx.fillText('0 m', c.x + ux * (r1 + 14), c.y + uy * (r1 + 14));
      }
    } else {
      const a = toScreen(0, 0), b = toScreen(road.length, 0);
      ctx.strokeStyle = PAL.road; ctx.lineWidth = LANE_W * sc;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      ctx.strokeStyle = PAL.edge; ctx.lineWidth = 1;
      for (const dy of [-LANE_W / 2, LANE_W / 2]) {
        const y = a.y + dy * sc;
        ctx.beginPath(); ctx.moveTo(a.x, y); ctx.lineTo(b.x, y); ctx.stroke();
      }
    }
  }

  // ---- space-time strip ----------------------------------------------------
  function stripSize() {
    const r = strip.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height) };
  }
  function buildStrip() {
    const { w, h } = stripSize();
    const off = document.createElement('canvas');
    off.width = w * S.DPR; off.height = h * S.DPR;
    const ctx = off.getContext('2d');
    ctx.setTransform(S.DPR, 0, 0, S.DPR, 0, 0);
    ctx.fillStyle = PAL.grid; ctx.fillRect(0, 0, w, h);
    const idx = S.idx, road = idx.roads[0], L = road.length, T = idx.duration || 1;
    // minute grid
    ctx.strokeStyle = PAL.line || '#26303f'; ctx.lineWidth = 1;
    ctx.fillStyle = PAL.dim; ctx.font = '9px IBM Plex Mono, monospace'; ctx.textBaseline = 'top';
    for (let t = 60; t < T; t += 60) {
      const x = Math.round((t / T) * w) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      ctx.fillText(fmtTime(t), x + 3, 2);
    }
    // trajectories
    ctx.lineWidth = 1.2; ctx.lineCap = 'round';
    const ticks = idx.ticks;
    for (let i = 0; i + 1 < ticks.length; i++) {
      const x0 = (ticks[i].t / T) * w, x1 = (ticks[i + 1].t / T) * w, next = idx.maps[i + 1];
      for (const r of ticks[i].v) {
        const nb = next.get(r[0]);
        if (!nb || nb[1] !== r[1]) continue;
        let p0 = r[2], p1 = nb[2];
        if (road.ring && Math.abs(p1 - p0) > L / 2) continue; // wrapped: skip the seam
        ctx.strokeStyle = C.speedColor(LUT, (r[3] + nb[3]) / 2, idx.vmax);
        ctx.beginPath();
        ctx.moveTo(x0, h - (p0 / L) * h); ctx.lineTo(x1, h - (p1 / L) * h);
        ctx.stroke();
      }
    }
    S.stripCache = off;
  }
  function drawStrip() {
    const { w, h } = stripSize();
    if (strip.width !== w * S.DPR || strip.height !== h * S.DPR) {
      strip.width = w * S.DPR; strip.height = h * S.DPR; S.stripCache = null;
    }
    stctx.setTransform(S.DPR, 0, 0, S.DPR, 0, 0);
    stctx.clearRect(0, 0, w, h);
    if (!S.idx) return;
    if (!S.stripCache) buildStrip();
    stctx.drawImage(S.stripCache, 0, 0, w, h);
    const x = Math.round((S.t / (S.idx.duration || 1)) * w) + 0.5;
    stctx.strokeStyle = PAL.amber; stctx.lineWidth = 1;
    stctx.beginPath(); stctx.moveTo(x, 0); stctx.lineTo(x, h); stctx.stroke();
    stctx.fillStyle = PAL.amber;
    stctx.beginPath(); stctx.moveTo(x - 4, 0); stctx.lineTo(x + 4, 0); stctx.lineTo(x, 5); stctx.fill();
  }
  function scrubTo(clientX) {
    const r = strip.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
    S.t = f * S.idx.duration;
  }

  // ---- hud / controls ------------------------------------------------------
  function fmtTime(t) {
    const m = Math.floor(t / 60), s = Math.floor(t % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  }
  const kmh = v => `${(v * 3.6).toFixed(0)} km/h`;
  function updateHud(vehicles) {
    const st = C.stats(vehicles);
    $('hTime').textContent = fmtTime(S.t);
    $('hVeh').textContent = st.n;
    $('hMean').textContent = kmh(st.mean);
    $('hMin').textContent = kmh(st.min);
  }
  function syncPlay() { $('play').textContent = S.playing ? '❚❚' : '▶'; }
  function setRate(r) {
    S.rate = r;
    for (const b of $('rates').children) b.classList.toggle('active', +b.dataset.rate === r);
  }
  for (const r of RATES) {
    const b = document.createElement('button');
    b.dataset.rate = r; b.textContent = (r < 1 ? r.toString().replace('0.', '.') : r) + '×';
    b.addEventListener('click', () => setRate(r));
    $('rates').appendChild(b);
  }
  setRate(1);
  $('play').addEventListener('click', () => { S.playing = !S.playing; syncPlay(); });
  $('file').addEventListener('change', e => readFile(e.target.files[0]));

  addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === ' ') { e.preventDefault(); S.playing = !S.playing; syncPlay(); }
    else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      if (!S.idx) return;
      S.playing = false; syncPlay();
      const step = (S.idx.trace.dt || 1) * (e.shiftKey ? 10 : 1);
      S.t = Math.min(S.idx.duration, Math.max(0, S.t + (e.key === 'ArrowRight' ? step : -step)));
    }
    else if (e.key === ']' || e.key === '[') {
      const i = RATES.indexOf(S.rate) + (e.key === ']' ? 1 : -1);
      if (RATES[i] !== undefined) setRate(RATES[i]);
    }
    else if (e.key === 'f') fitCamera();
    else if (e.key === 'Home') S.t = 0;
  });

  // scrub
  let scrubbing = false;
  strip.addEventListener('pointerdown', e => { if (!S.idx) return; scrubbing = true; strip.setPointerCapture(e.pointerId); scrubTo(e.clientX); });
  strip.addEventListener('pointermove', e => { if (scrubbing) scrubTo(e.clientX); });
  strip.addEventListener('pointerup', () => { scrubbing = false; });

  // pan / zoom
  scene.addEventListener('pointerdown', e => { S.drag = { x: e.clientX, y: e.clientY }; scene.setPointerCapture(e.pointerId); scene.classList.add('dragging'); });
  scene.addEventListener('pointermove', e => {
    if (!S.drag) return;
    S.cam.x -= (e.clientX - S.drag.x) / S.cam.scale; S.cam.y -= (e.clientY - S.drag.y) / S.cam.scale;
    S.drag = { x: e.clientX, y: e.clientY };
  });
  scene.addEventListener('pointerup', () => { S.drag = null; scene.classList.remove('dragging'); });
  scene.addEventListener('wheel', e => {
    if (!S.idx) return;
    e.preventDefault();
    const v = viewCentre(), k = Math.exp(-e.deltaY * 0.0015);
    const wx = S.cam.x + (e.clientX - v.cx) / S.cam.scale, wy = S.cam.y + (e.clientY - v.cy) / S.cam.scale;
    S.cam.scale = Math.min(200, Math.max(0.05, S.cam.scale * k));
    S.cam.x = wx - (e.clientX - v.cx) / S.cam.scale; S.cam.y = wy - (e.clientY - v.cy) / S.cam.scale;
  }, { passive: false });

  // drag & drop
  let dragDepth = 0;
  addEventListener('dragenter', e => { e.preventDefault(); if (++dragDepth === 1) $('drop').classList.remove('hidden'); });
  addEventListener('dragleave', () => { if (--dragDepth === 0) $('drop').classList.add('hidden'); });
  addEventListener('dragover', e => e.preventDefault());
  addEventListener('drop', e => { e.preventDefault(); dragDepth = 0; $('drop').classList.add('hidden'); readFile(e.dataTransfer.files[0]); });

  // ---- resize / loop -------------------------------------------------------
  function resize() {
    S.DPR = Math.min(devicePixelRatio || 1, 2);
    S.W = innerWidth; S.H = innerHeight;
    scene.width = S.W * S.DPR; scene.height = S.H * S.DPR;
    sctx.setTransform(S.DPR, 0, 0, S.DPR, 0, 0);
    S.stripCache = null;
    fitCamera();
  }
  addEventListener('resize', resize);
  resize();

  function frame(now) {
    const dt = S.last ? Math.min(0.1, (now - S.last) / 1000) : 0;
    S.last = now;
    if (S.idx && S.playing && !scrubbing) {
      S.t += dt * S.rate;
      if (S.t > S.idx.duration) S.t = 0;
    }
    drawScene();
    drawStrip();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  // ---- boot ----------------------------------------------------------------
  const url = new URLSearchParams(location.search).get('trace');
  if (url) {
    fetch(url).then(r => r.json()).then(t => load(t, url))
      .catch(err => { $('sub').textContent = `could not load ${url}: ${err.message}`; });
  } else if (typeof SAMPLE_TRACE !== 'undefined') {
    load(SAMPLE_TRACE, 'sample');
  }
})();
