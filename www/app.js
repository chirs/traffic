'use strict';
(() => {
  const C = TrafficCore;
  const $ = id => document.getElementById(id);
  const scene = $('scene'), sctx = scene.getContext('2d');
  const strip = $('strip'), stctx = strip.getContext('2d');
  const css = getComputedStyle(document.documentElement);
  const tok = n => css.getPropertyValue(n).trim();
  const PAL = {
    bg: tok('--bg'), road: tok('--road'), roadOnMap: tok('--road-on-map'), edge: tok('--edge'), lane: tok('--lane'), grid: tok('--grid'),
    line: tok('--line'), node: tok('--node'),
    stop: tok('--v-stop'), slow: tok('--v-slow'), free: tok('--v-free'), brake: tok('--brake'),
    sigG: tok('--sig-g'), sigY: tok('--sig-y'), sigR: tok('--sig-r'), sigS: tok('--sig-s'), sigP: tok('--sig-p'),
    amber: tok('--amber'), faint: tok('--faint'), dim: tok('--dim'), text: tok('--text'),
  };
  const LUT = C.colorRamp([PAL.stop, PAL.slow, PAL.free], 64);
  const SIG = { g: PAL.sigG, y: PAL.sigY, r: PAL.sigR, s: PAL.sigS, p: PAL.sigP };
  // OSM standard tiles (no key needed; light personal use per the OSM tile usage policy), drawn
  // through an inverting filter so the basemap stays dark under the roads.
  const TILE_URL = (z, x, y) => `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
  const TILE_FILTER = 'invert(0.92) hue-rotate(180deg) saturate(0.25) brightness(0.8)';
  const TILE_ALPHA = 0.55, MAX_TILES = 160;
  const LANE_W = C.LANE_W, CAR_W = 2.0, RATES = [0.25, 0.5, 1, 2, 4, 8, 16];

  const S = {
    idx: null, t: 0, playing: true, rate: 1,
    cam: { scale: 1, x: 0, y: 0 }, // world metres -> screen px; (x,y) is the world point at view centre
    drag: null, last: 0, W: 0, H: 0, DPR: 1, stripCache: null,
    tiles: true, proj: null, tileCache: new Map(),
  };

  // ---- loading -------------------------------------------------------------
  function load(trace, name) {
    S.idx = C.index(trace);
    S.t = 0; S.playing = true; S.stripCache = null;
    const rs = S.idx.roads, ring = rs.length === 1 && rs[0].ring;
    const what = ring ? `ring ${rs[0].length} m` : `${S.idx.nodes.length} nodes · ${rs.length} roads`;
    $('sub').textContent = `${name} · ${what} · ${trace.vehicles.length} vehicles · ${fmtTime(S.idx.duration)}`;
    $('axis').textContent = ring
      ? 'time → · position along road ↑ · click or drag to scrub'
      : 'time → · mean speed (line) and vehicles on road (area) · click or drag to scrub';
    S.proj = S.idx.geo ? C.projection(S.idx.geo) : null;
    $('map').disabled = !S.proj;
    syncMap();
    fitCamera();
    syncPlay();
  }
  function syncMap() {
    const on = !!(S.proj && S.tiles);
    $('map').classList.toggle('active', on);
    $('attrib').classList.toggle('hidden', !on);
  }
  function readFile(file) {
    if (!file) return;
    file.text().then(txt => load(JSON.parse(txt), file.name))
      .catch(err => { $('sub').textContent = `could not read ${file.name}: ${err.message}`; });
  }

  // ---- camera --------------------------------------------------------------
  function viewCentre() {
    const bh = document.querySelector('.bottom').getBoundingClientRect().height + 18;
    return { cx: S.W / 2, cy: (S.H - bh + 70) / 2, availH: S.H - bh - 70 };
  }
  function fitCamera() {
    if (!S.idx) return;
    const b = S.idx.bounds, v = viewCentre();
    S.cam.scale = 0.9 * Math.min(S.W / (b.x1 - b.x0), v.availH / (b.y1 - b.y0));
    S.cam.x = (b.x0 + b.x1) / 2; S.cam.y = (b.y0 + b.y1) / 2;
  }
  function toScreen(wx, wy) {
    const v = viewCentre();
    return { x: v.cx + (wx - S.cam.x) * S.cam.scale, y: v.cy - (wy - S.cam.y) * S.cam.scale };
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
    const sc = S.cam.scale;
    if (S.proj && S.tiles) drawTiles(ctx);
    for (const road of S.idx.roads) drawRoad(ctx, road, sc);
    drawNodes(ctx, sc);
    const vehicles = C.sample(S.idx, S.t);
    for (const v of vehicles) {
      const road = S.idx.roads[v.road];
      const w = C.pointAt(road, v.pos - v.length / 2, v.lane, v.lateral);
      const p = toScreen(w.x, w.y);
      const len = Math.max(v.length * sc, 4), wid = Math.max(CAR_W * sc, 2.5);
      ctx.save();
      ctx.translate(p.x, p.y); ctx.rotate(Math.atan2(-w.dy, w.dx));
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

  // Stroke the road's centreline shifted `lateral` metres to the right of travel.
  function strokePath(ctx, road, lateral) {
    ctx.beginPath();
    if (road.ring) {
      const c = toScreen(0, 0); // clockwise ring: right of travel is inward
      ctx.arc(c.x, c.y, (C.ringXY(0, road.length).R - lateral) * S.cam.scale, 0, Math.PI * 2);
    } else {
      const pts = road.pts, n = pts.length;
      for (let i = 0; i < n; i++) {
        let dx, dy;
        if (i === 0) [dx, dy] = dir(pts[0], pts[1]);
        else if (i === n - 1) [dx, dy] = dir(pts[n - 2], pts[n - 1]);
        else {
          const a = dir(pts[i - 1], pts[i]), b = dir(pts[i], pts[i + 1]);
          dx = a[0] + b[0]; dy = a[1] + b[1];
          const m = Math.hypot(dx, dy) || 1; dx /= m; dy /= m;
        }
        const p = toScreen(pts[i][0] + dy * lateral, pts[i][1] - dx * lateral);
        if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
      }
    }
    ctx.stroke();
  }
  function dir(a, b) {
    const d = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    return [(b[0] - a[0]) / d, (b[1] - a[1]) / d];
  }

  // ---- map tiles -----------------------------------------------------------
  function tile(z, x, y) {
    const key = `${z}/${x}/${y}`;
    let img = S.tileCache.get(key);
    if (!img) {
      img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = TILE_URL(z, x, y);
      if (S.tileCache.size > 400) S.tileCache.delete(S.tileCache.keys().next().value);
      S.tileCache.set(key, img);
    }
    return img;
  }
  function drawTiles(ctx) {
    const v = viewCentre(), sc = S.cam.scale, proj = S.proj;
    const z = C.tileZoom(sc, S.idx.geo.lat);
    // world rect covering the screen
    const wx0 = S.cam.x - v.cx / sc, wx1 = S.cam.x + (S.W - v.cx) / sc;
    const wy1 = S.cam.y + v.cy / sc, wy0 = S.cam.y - (S.H - v.cy) / sc;
    const nw = proj.toLonLat(wx0, wy1), se = proj.toLonLat(wx1, wy0);
    const t0 = C.lonLatToTile(z, nw.lon, nw.lat), t1 = C.lonLatToTile(z, se.lon, se.lat);
    const x0 = Math.floor(t0.x), x1 = Math.floor(t1.x), y0 = Math.floor(t0.y), y1 = Math.floor(t1.y);
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > MAX_TILES) return;
    ctx.save();
    ctx.globalAlpha = TILE_ALPHA;
    if ('filter' in ctx) ctx.filter = TILE_FILTER;
    ctx.imageSmoothingEnabled = true;
    for (let x = x0; x <= x1; x++) {
      for (let y = y0; y <= y1; y++) {
        const img = tile(z, x, y);
        if (!img.complete || !img.naturalWidth) continue;
        const a = C.tileToLonLat(z, x, y), b = C.tileToLonLat(z, x + 1, y + 1);
        const pa = proj.toWorld(a.lat, a.lon), pb = proj.toWorld(b.lat, b.lon);
        const s0 = toScreen(pa.x, pa.y), s1 = toScreen(pb.x, pb.y);
        ctx.drawImage(img, s0.x, s0.y, s1.x - s0.x + 0.5, s1.y - s0.y + 0.5);
      }
    }
    ctx.restore();
  }

  function drawRoad(ctx, road, sc) {
    const half = (road.lanes * LANE_W) / 2;
    ctx.lineCap = 'butt';
    ctx.strokeStyle = S.proj && S.tiles ? PAL.roadOnMap : PAL.road;
    ctx.lineWidth = Math.max(1.5, road.lanes * LANE_W * sc);
    strokePath(ctx, road, half);
    if (sc > 0.6) {
      ctx.strokeStyle = PAL.edge; ctx.lineWidth = 1;
      strokePath(ctx, road, 0);               // left edge / centreline
      strokePath(ctx, road, 2 * half);        // kerb
      if (road.lanes > 1) {
        ctx.strokeStyle = PAL.lane; ctx.setLineDash([3 * sc, 6 * sc]);
        for (let l = 1; l < road.lanes; l++) strokePath(ctx, road, l * LANE_W);
        ctx.setLineDash([]);
      }
    }
    if (road.ring) {
      // distance ticks every 100 m, labelled at 0
      const c = toScreen(0, 0), R = C.ringXY(0, road.length).R;
      ctx.strokeStyle = PAL.lane; ctx.fillStyle = PAL.dim;
      ctx.font = '10px IBM Plex Mono, monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (let s = 0; s < road.length; s += 100) {
        const a = C.ringXY(s, road.length), r0 = R * sc + 3, r1 = r0 + 6;
        const ux = a.x / R, uy = -a.y / R;
        ctx.beginPath(); ctx.moveTo(c.x + ux * r0, c.y + uy * r0); ctx.lineTo(c.x + ux * r1, c.y + uy * r1); ctx.stroke();
        if (s === 0) ctx.fillText('0 m', c.x + ux * (r1 + 14), c.y + uy * (r1 + 14));
      }
    }
  }

  function drawNodes(ctx, sc) {
    const idx = S.idx, sig = C.signals(idx, S.t);
    const maxLanes = Math.max(1, ...idx.roads.map(r => r.lanes));
    idx.nodes.forEach((n, ni) => {
      const p = toScreen(n.x, n.y);
      const box = 2 * (n.radius || maxLanes * LANE_W) * sc;
      if (n.control || n.radius) {
        ctx.fillStyle = PAL.node;
        ctx.fillRect(p.x - box / 2, p.y - box / 2, box, box);
      }
      if (n.control && sc > 0.5) {
        // one lamp per approach, on the kerb just before the stop line
        idx.roads.forEach((r, ri) => {
          if (r.dst !== n.id) return;
          const st = sig.get(`${ni},${ri}`) || (n.control === 'stop' ? 's' : 'r');
          if (st === 'm') return; // major road at a priority junction: no lamp
          const w = C.pointAt(r, Math.max(0, r.length - 1.5), 0, 2.2);
          const q = toScreen(w.x, w.y);
          ctx.fillStyle = SIG[st] || PAL.dim;
          ctx.beginPath(); ctx.arc(q.x, q.y, Math.min(5, Math.max(2, 1.2 * sc)), 0, Math.PI * 2); ctx.fill();
        });
      }
    });
  }

  // ---- strip ---------------------------------------------------------------
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
    const idx = S.idx, T = idx.duration || 1;
    ctx.strokeStyle = PAL.line; ctx.lineWidth = 1;
    ctx.fillStyle = PAL.dim; ctx.font = '9px IBM Plex Mono, monospace'; ctx.textBaseline = 'top';
    for (let t = 60; t < T; t += 60) {
      const x = Math.round((t / T) * w) + 0.5;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      ctx.fillText(fmtTime(t), x + 3, 2);
    }
    const rs = idx.roads;
    if (rs.length === 1 && rs[0].ring) drawTrajectories(ctx, w, h); else drawSeries(ctx, w, h);
    S.stripCache = off;
  }
  function drawTrajectories(ctx, w, h) {
    const idx = S.idx, road = idx.roads[0], L = road.length, T = idx.duration || 1, ticks = idx.ticks;
    ctx.lineWidth = 1.2; ctx.lineCap = 'round';
    for (let i = 0; i + 1 < ticks.length; i++) {
      const x0 = (ticks[i].t / T) * w, x1 = (ticks[i + 1].t / T) * w, next = idx.maps[i + 1];
      for (const r of ticks[i].v) {
        const nb = next.get(r[0]);
        if (!nb || Math.abs(nb[3] - r[3]) > L / 2) continue; // gone, or wrapped: skip the seam
        ctx.strokeStyle = C.speedColor(LUT, (r[4] + nb[4]) / 2, idx.vmax);
        ctx.beginPath();
        ctx.moveTo(x0, h - (r[3] / L) * h); ctx.lineTo(x1, h - (nb[3] / L) * h);
        ctx.stroke();
      }
    }
  }
  function drawSeries(ctx, w, h) {
    const idx = S.idx, T = idx.duration || 1, ser = idx.series;
    const nmax = Math.max(1, ...ser.map(s => s.n));
    const pad = 12;
    ctx.beginPath(); ctx.moveTo(0, h);
    ser.forEach((s, i) => ctx.lineTo((idx.times[i] / T) * w, h - (s.n / nmax) * (h - pad)));
    ctx.lineTo(w, h); ctx.closePath();
    ctx.fillStyle = PAL.line; ctx.fill();
    ctx.lineWidth = 1.5; ctx.lineJoin = 'round';
    for (let i = 0; i + 1 < ser.length; i++) {
      ctx.strokeStyle = C.speedColor(LUT, ser[i].mean, idx.vmax);
      ctx.beginPath();
      ctx.moveTo((idx.times[i] / T) * w, h - (ser[i].mean / idx.vmax) * (h - pad));
      ctx.lineTo((idx.times[i + 1] / T) * w, h - (ser[i + 1].mean / idx.vmax) * (h - pad));
      ctx.stroke();
    }
    ctx.fillStyle = PAL.dim; ctx.textBaseline = 'bottom'; ctx.textAlign = 'right';
    ctx.fillText(`${nmax} vehicles`, w - 4, h - 2);
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
  function fmtSpeed(v) {
    return S.idx.units === 'km/h' ? `${(v * 3.6).toFixed(0)} km/h` : `${(v * 2.23694).toFixed(0)} mph`;
  }
  function updateHud(vehicles) {
    const st = C.stats(vehicles);
    $('hTime').textContent = fmtTime(S.t);
    $('hVeh').textContent = st.n;
    $('hMean').textContent = fmtSpeed(st.mean);
    $('hMin').textContent = fmtSpeed(st.min);
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
  $('map').addEventListener('click', () => { S.tiles = !S.tiles; syncMap(); });
  $('file').addEventListener('change', e => readFile(e.target.files[0]));

  // bundled samples
  const samples = typeof SAMPLES !== 'undefined' ? SAMPLES : [];
  for (const s of samples) {
    const b = document.createElement('button');
    b.textContent = s.name;
    b.addEventListener('click', () => { load(s.trace, s.name); markSample(b); });
    $('samples').appendChild(b);
  }
  function markSample(active) {
    for (const b of $('samples').children) b.classList.toggle('active', b === active);
  }

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
    else if (e.key === 'm' && S.proj) { S.tiles = !S.tiles; syncMap(); }
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
    S.cam.x -= (e.clientX - S.drag.x) / S.cam.scale; S.cam.y += (e.clientY - S.drag.y) / S.cam.scale;
    S.drag = { x: e.clientX, y: e.clientY };
  });
  scene.addEventListener('pointerup', () => { S.drag = null; scene.classList.remove('dragging'); });
  scene.addEventListener('wheel', e => {
    if (!S.idx) return;
    e.preventDefault();
    const v = viewCentre(), k = Math.min(1.25, Math.max(0.8, Math.exp(-e.deltaY * 0.0015)));
    const wx = S.cam.x + (e.clientX - v.cx) / S.cam.scale, wy = S.cam.y - (e.clientY - v.cy) / S.cam.scale;
    S.cam.scale = Math.min(200, Math.max(0.05, S.cam.scale * k));
    S.cam.x = wx - (e.clientX - v.cx) / S.cam.scale; S.cam.y = wy + (e.clientY - v.cy) / S.cam.scale;
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
  } else if (samples.length) {
    load(samples[0].trace, samples[0].name);
    markSample($('samples').firstChild);
  }
})();
