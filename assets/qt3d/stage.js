// QT trap reel stage: a three.js scene (lit toy-like objects, soft shadows, a slowly moving camera)
// under HTML cards and captions. Python (mcq_agent/qt3d.py) loads a plan with load(plan) and then
// calls seek(t) for every frame; everything on screen is a pure function of t.
import * as THREE from 'three';
import { RoundedBoxGeometry } from '../vendor/three/RoundedBoxGeometry.js';
import { RoomEnvironment } from '../vendor/three/RoomEnvironment.js';

const W = 1080, H = 1920;
const $ = (id) => document.getElementById(id);

// ── easing ──────────────────────────────────────────────────
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const ease = (x) => { x = clamp(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
const easeIn = (x) => Math.pow(clamp(x), 3);
const backOut = (x) => { x = clamp(x); const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
function spring(t, f = 2.2, z = 0.5) {           // step response in seconds: rises, overshoots a little, settles
  if (t <= 0) return 0;
  const w = 2 * Math.PI * f, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + (z * w / wd) * Math.sin(wd * t));
}
// count-up for a shown number ("₹4,200", "250 m", "3,818.18"): returns the text at progress k, or null
function countText(orig, k) {
  const m = String(orig).match(/^(₹?\s?)(\d[\d,]*(?:\.\d+)?)(\s?[%A-Za-z/ ]{0,12})$/);
  if (!m) return null;
  const num = parseFloat(m[2].replace(/,/g, ''));
  if (!(num >= 10)) return null;
  const dec = (m[2].split('.')[1] || '').length;
  const v = num * clamp(k);
  let [ip, fp] = v.toFixed(dec).split('.');
  if (m[2].includes(',')) {
    if (/\d,\d\d,\d{3}/.test(m[2])) { const last = ip.slice(-3), rest = ip.slice(0, -3); ip = (rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' : '') + last; }
    else ip = ip.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  return m[1] + ip + (fp ? '.' + fp : '') + m[3];
}
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
const isNum = (w) => /[0-9₹%]/.test(w);

// ── look ────────────────────────────────────────────────────
// each theme is a desk-top set: wood tint, the wall behind (top / middle / near the desk), lamp glow
const THEMES = {
  green:  { floor: '#c89668', bg: '#0f1c46', top: '#0b1638', mid: '#1b2f6b', hor: '#3a4f86', lamp: '#ffd98a' },
  purple: { floor: '#b98a63', bg: '#1d1844', top: '#120f2e', mid: '#2c2566', hor: '#56508e', lamp: '#ffd2a0' },
  navy:   { floor: '#c4986e', bg: '#0f1c46', top: '#0a1534', mid: '#17295f', hor: '#33497f', lamp: '#ffe0a0' },
  teal:   { floor: '#cfa278', bg: '#0e2a3c', top: '#0a1d2c', mid: '#154158', hor: '#33677c', lamp: '#fff0b8' },
  maroon: { floor: '#b88560', bg: '#2a1530', top: '#1a0d22', mid: '#3a1f46', hor: '#6a4466', lamp: '#ffcf8a' },
};
const PAL = ['#e9524a', '#3c7ce8', '#35b66b', '#f4b63a', '#9a66e2', '#2fbfd0'];
const SEG = ['#3c7ce8', '#f4b63a', '#35b66b', '#e9524a', '#9a66e2'];
const SKIN = '#f2c9a4';

// ── three.js setup ──────────────────────────────────────────
// quality knobs (?scale=0.75&aa=0&sh=1024&soft=0): the 3D layer can render smaller than the page and be scaled up
const Q = new URLSearchParams(location.search);
const SCALE = parseFloat(Q.get('scale') || '1');
const renderer = new THREE.WebGLRenderer({ canvas: $('gl'), antialias: Q.get('aa') !== '0', preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(Math.round(W * SCALE), Math.round(H * SCALE), false);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = Q.get('soft') === '0' ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
const scene = new THREE.Scene();
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
const camera = new THREE.PerspectiveCamera(30, W / H, 0.1, 500);
const hemi = new THREE.HemisphereLight(0xffffff, 0x2a3a30, 0.55);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff1df, 2.4);
sun.castShadow = true;
sun.shadow.mapSize.set(+(Q.get('sh') || 2048), +(Q.get('sh') || 2048));
sun.shadow.bias = -0.0005;
sun.shadow.normalBias = 0.03;
scene.add(sun, sun.target);
// seeded random, so every render of a plan places the world the same way
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
// wood desk top: planks with grain, painted grey so the theme tints it
const woodTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 1024;
  const g = c.getContext('2d'); const r = rng(11);
  const PL = 9;                                     // planks across the texture
  for (let p = 0; p < PL; p++) {
    const y0 = p * 1024 / PL, hgt = 1024 / PL, base = 205 + Math.floor(r() * 22);
    g.fillStyle = `rgb(${base},${base},${base})`; g.fillRect(0, y0, 1024, hgt);
    for (let i = 0; i < 90; i++) {                 // grain: long wavy streaks along the plank
      const v = base - 25 - Math.floor(r() * 45), yy = y0 + r() * hgt, amp = 2 + r() * 5, ph = r() * 6, f = 0.004 + r() * 0.01;
      g.strokeStyle = `rgba(${v},${v},${v},${0.25 + r() * 0.4})`; g.lineWidth = 0.8 + r() * 2.2;
      g.beginPath(); for (let x = 0; x <= 1024; x += 16) g.lineTo(x, yy + Math.sin(x * f + ph) * amp); g.stroke();
    }
    if (p % 3 === 0) { g.fillStyle = 'rgba(70,70,70,0.5)'; g.fillRect(0, y0, 1024, 2); }   // a faint joint now and then
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(10, 10); t.rotation = Math.PI / 2;
  t.anisotropy = 8; t.colorSpace = THREE.SRGBColorSpace; return t;
})();
const floorMat = new THREE.MeshStandardMaterial({ color: '#c89668', map: woodTex, roughness: 0.62, metalness: 0, envMapIntensity: 0.35 });
const floor = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), floorMat);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);
const root = new THREE.Group();
scene.add(root);

// ── the world around the puzzle: a CA's desk (wall, lamp light, calculator, ledgers, coins, pen) ──
const skyMat = new THREE.ShaderMaterial({
  side: THREE.BackSide, depthWrite: false, fog: false,
  uniforms: { top: { value: new THREE.Color() }, mid: { value: new THREE.Color() }, hor: { value: new THREE.Color() } },
  vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `uniform vec3 top; uniform vec3 mid; uniform vec3 hor; varying vec3 vP;
    void main(){ float h = vP.y; vec3 c = mix(hor, mid, smoothstep(0.0, 0.22, h)); c = mix(c, top, smoothstep(0.22, 0.75, h));
      gl_FragColor = vec4(c, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
});
const sky = new THREE.Mesh(new THREE.SphereGeometry(420, 32, 16), skyMat);
scene.add(sky);
const world = new THREE.Group();
scene.add(world);
function canvasTex(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
// lamp pool: a warm soft light on the desk under the puzzle
const poolTex = canvasTex(256, 256, (g) => {
  const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, 'rgba(255,255,255,0.55)'); gr.addColorStop(0.5, 'rgba(255,255,255,0.22)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
});
const calcTex = canvasTex(512, 900, (g, w, h) => {
  g.fillStyle = '#1d2433'; g.fillRect(0, 0, w, h);
  g.fillStyle = '#9fb59a'; g.fillRect(40, 60, w - 80, 170);                       // display
  g.fillStyle = '#26331f'; g.font = '700 110px Courier New, monospace'; g.textAlign = 'right'; g.textBaseline = 'middle';
  g.fillText('1,00,000', w - 60, 150);
  g.fillStyle = '#c9d2e6'; g.font = '700 30px Arial'; g.textAlign = 'left'; g.fillText('CA', 44, 270);
  const keys = ['MC', 'MR', 'M-', 'M+', '7', '8', '9', '÷', '4', '5', '6', '×', '1', '2', '3', '−', '0', '.', '=', '+'];
  keys.forEach((k, i) => {
    const cx = 40 + (i % 4) * 112, cy = 310 + Math.floor(i / 4) * 112;
    g.fillStyle = k === '=' ? '#f0b429' : (i < 4 ? '#3c4a66' : '#e9edf5'); g.beginPath(); g.roundRect(cx, cy, 96, 90, 16); g.fill();
    g.fillStyle = k === '=' ? '#1d2433' : (i < 4 ? '#e9edf5' : '#1d2433'); g.font = '700 44px Arial'; g.textAlign = 'center'; g.fillText(k, cx + 48, cy + 47);
  });
});
const ledgerTex = canvasTex(512, 700, (g, w, h) => {
  g.fillStyle = '#fbf7ea'; g.fillRect(0, 0, w, h);
  g.strokeStyle = 'rgba(70,110,180,0.45)'; g.lineWidth = 2;
  for (let y = 70; y < h; y += 34) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
  g.strokeStyle = 'rgba(200,60,60,0.6)'; for (const x of [60, 360, 440]) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke(); }
  g.fillStyle = 'rgba(30,40,80,0.75)'; g.font = 'italic 600 26px Georgia';
  const rows = ['Cash  Dr.', 'To Sales', 'By Bank', 'To Capital', 'By Rent', 'Interest', 'Annuity', 'Balance c/d'];
  rows.forEach((t, i) => { g.textAlign = 'left'; g.fillText(t, 72, 96 + i * 68); g.textAlign = 'right'; g.fillText(String(1200 + i * 375), 430, 96 + i * 68); });
});
function buildWorld(th, seed) {
  world.clear();
  scene.fog = new THREE.Fog(th.hor, 46, 210);
  skyMat.uniforms.top.value.set(th.top); skyMat.uniforms.mid.value.set(th.mid); skyMat.uniforms.hor.value.set(th.hor);
  const r = rng(seed);
  const S = 1.6;                                       // props are a little larger than life next to the toy puzzle
  const pool = new THREE.Mesh(new THREE.PlaneGeometry(46, 30), new THREE.MeshBasicMaterial({ map: poolTex, color: th.lamp, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.55 }));
  pool.rotation.x = -Math.PI / 2; pool.position.set(0, 0.002, -1); world.add(pool);
  const place = (obj, x, z, ry) => { obj.position.set(x, 0, z); obj.rotation.y = ry; obj.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } }); world.add(obj); return obj; };
  // calculator
  const calc = new THREE.Group();
  const body = new THREE.Mesh(new RoundedBoxGeometry(3.4 * S, 0.5 * S, 6 * S, 4, 0.25 * S), std('#2a3246', { r: 0.45 }));
  body.position.y = 0.25 * S;
  const face = new THREE.Mesh(new THREE.PlaneGeometry(3.1 * S, 5.6 * S), new THREE.MeshStandardMaterial({ map: calcTex, roughness: 0.5 }));
  face.rotation.x = -Math.PI / 2; face.position.y = 0.505 * S;
  calc.add(body, face); calc.rotation.x = 0;
  place(calc, -11 - r() * 2, -12 - r() * 2, 0.35 + r() * 0.2);
  // ledger books, a stack of three
  const covers = ['#16285e', '#7a1f2b', '#1e5b47', '#f0b429'];
  const stack = new THREE.Group();
  let y = 0;
  for (let i = 0; i < 3; i++) {
    const bw = (5.6 - i * 0.3) * S, bd = (7.6 - i * 0.4) * S, bh = (0.75 + r() * 0.35) * S;
    const b = new THREE.Group();
    const cover = new THREE.Mesh(new RoundedBoxGeometry(bw, bh, bd, 2, 0.08 * S), std(covers[(i + Math.floor(r() * 4)) % 4], { r: 0.6 }));
    const pages = new THREE.Mesh(new THREE.BoxGeometry(bw * 0.96, bh * 0.78, bd * 0.97), std('#f6f0de', { r: 0.9 }));
    pages.position.set(0.12 * S, 0, 0);
    b.add(cover, pages); b.position.y = y + bh / 2; b.rotation.y = (r() - 0.5) * 0.35; y += bh;
    stack.add(b);
  }
  place(stack, 12 + r() * 2, -14 - r() * 2, -0.3 + r() * 0.2);
  // open ledger lying flat at the back
  const open = new THREE.Group();
  for (const sx of [-1, 1]) {
    const pg = new THREE.Mesh(new THREE.BoxGeometry(5 * S, 0.12 * S, 7 * S), new THREE.MeshStandardMaterial({ map: ledgerTex, roughness: 0.9 }));
    pg.position.set(sx * 2.55 * S, 0.06 * S, 0); pg.rotation.z = sx * -0.04; open.add(pg);
  }
  const back = new THREE.Mesh(new THREE.BoxGeometry(10.5 * S, 0.06 * S, 7.3 * S), std('#16285e', { r: 0.6 })); back.position.y = 0.01; open.add(back);
  place(open, -1 + r() * 2, -24 - r() * 3, (r() - 0.5) * 0.4);
  // coins: a few stacks and some loose ones
  const gold = std('#d9a33a', { m: 0.85, r: 0.28, env: 1.0 });
  const coinG = new THREE.CylinderGeometry(0.44 * S, 0.44 * S, 0.12 * S, 40);
  const coins = new THREE.Group();
  const spots = [[-5, -11], [-3.6, -12.2], [5.5, -10.5], [6.9, -11.6], [-16, -4], [16, -5]];
  spots.forEach(([x, z], i) => {
    const n = i < 4 ? 2 + Math.floor(r() * 6) : 1;
    for (let k = 0; k < n; k++) {
      const c = new THREE.Mesh(coinG, gold);
      c.position.set(x + (r() - 0.5) * 0.12, 0.06 * S + k * 0.125 * S, z + (r() - 0.5) * 0.12); c.rotation.y = r() * 6;
      coins.add(c);
    }
  });
  place(coins, 0, 0, 0);
  // pen lying across the desk
  const pen = new THREE.Group();
  const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.22 * S, 0.22 * S, 8 * S, 24), std('#16285e', { r: 0.25, m: 0.2 }));
  const tip = new THREE.Mesh(new THREE.ConeGeometry(0.22 * S, 0.9 * S, 24), std('#d9a33a', { m: 0.9, r: 0.25 }));
  tip.position.y = -4.45 * S; tip.rotation.x = Math.PI;
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.23 * S, 0.23 * S, 0.5 * S, 24), std('#d9a33a', { m: 0.9, r: 0.25 }));
  cap.position.y = 4 * S;
  pen.add(barrel, tip, cap); pen.rotation.z = Math.PI / 2; pen.position.y = 0.22 * S;
  const penHolder = new THREE.Group(); penHolder.add(pen);
  place(penHolder, -2 + r() * 3, -15.5 - r(), 0.5 + r() * 0.4);
  // sticky notes
  const notes = ['#ffd54a', '#8fd3ff', '#ff9fb2'];
  for (let i = 0; i < 2; i++) {
    const n = new THREE.Mesh(new THREE.BoxGeometry(2.6 * S, 0.03, 2.6 * S), std(notes[(i + Math.floor(r() * 3)) % 3], { r: 0.85 }));
    n.position.y = 0.015; place(n, (i ? 1 : -1) * (19 + r() * 3), -2 - r() * 3, r() * 0.6 - 0.3);
  }
  // the wall: a dark navy panel far behind the desk, with a soft lamp glow on it
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(500, 160), new THREE.MeshStandardMaterial({ color: th.mid, roughness: 1 }));
  wall.position.set(0, 60, -95); world.add(wall);
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(140, 90), new THREE.MeshBasicMaterial({ map: poolTex, color: th.lamp, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.35, fog: false }));
  glow.position.set(-10, 22, -94.5); world.add(glow);
}

// blob (contact) shadow texture
const blobTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'); const gr = g.createRadialGradient(64, 64, 4, 64, 64, 62);
  gr.addColorStop(0, 'rgba(0,0,0,0.55)'); gr.addColorStop(0.55, 'rgba(0,0,0,0.25)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
})();
function blob(r) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(r * 2, r * 2),
    new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; m.position.y = 0.005; m.renderOrder = 1;
  return m;
}

const std = (color, o = {}) => new THREE.MeshStandardMaterial({
  color: new THREE.Color(color), roughness: o.r ?? 0.42, metalness: o.m ?? 0, envMapIntensity: o.env ?? 0.55,
  emissive: new THREE.Color(o.e ?? '#000000'), emissiveIntensity: o.ei ?? 0, transparent: !!o.transparent, side: o.side ?? THREE.FrontSide,
});
function shadowed(o) { o.traverse((m) => { if (m.isMesh && !m.material.transparent) { m.castShadow = true; m.receiveShadow = true; } }); return o; }
const geoCache = new Map();
function rbox(w, h, d, r = 0.08) {
  const key = [w, h, d, r].map((v) => v.toFixed(3)).join('|');
  if (!geoCache.has(key)) geoCache.set(key, new RoundedBoxGeometry(w, h, d, 4, Math.min(r, w / 2 - 0.001, h / 2 - 0.001, d / 2 - 0.001)));
  return geoCache.get(key);
}

// ── objects ─────────────────────────────────────────────────
const HEIGHT = { bell: 2.0, pole: 1.75, tree: 1.8, coin: 1.0, person: 1.42, box: 0.9, dot: 0.8 };

function makeBell() {
  const g = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.42, 0.08, 40), std('#1d1e24', { r: 0.6 }));
  base.position.y = 0.04;
  const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.05, 1.2, 16), std('#26272e', { r: 0.5 }));
  stand.position.y = 0.64;
  const prof = [[0.001, 0.64], [0.07, 0.62], [0.14, 0.56], [0.19, 0.46], [0.22, 0.32], [0.26, 0.18], [0.33, 0.08], [0.43, 0.02], [0.44, 0.0], [0.4, 0.0]];
  const gold = std('#e7b24a', { m: 0.85, r: 0.26, env: 1.1, side: THREE.DoubleSide });
  const bell = new THREE.Mesh(new THREE.LatheGeometry(prof.map(([x, y]) => new THREE.Vector2(x, y)), 48), gold);
  bell.position.y = 1.22;
  const knob = new THREE.Mesh(new THREE.SphereGeometry(0.07, 20, 16), gold);
  knob.position.y = 1.88;
  const sw = new THREE.Group(); sw.position.y = 1.9; bell.position.y -= 1.9; knob.position.y -= 1.9; sw.add(bell, knob);
  g.add(base, stand, sw, blob(0.62));
  g.userData = { glow: [gold], swing: sw };
  return g;
}
function makePole(color) {
  const g = new THREE.Group();
  const p = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.08, 1.5, 20), std('#f2f2f4', { r: 0.35 }));
  p.position.y = 0.75;
  const capM = std(color, { r: 0.3 });
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.16, 24, 18), capM);
  cap.position.y = 1.58;
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.26, 0.08, 28), std('#3a3b42', { r: 0.6 }));
  base.position.y = 0.04;
  g.add(p, cap, base, blob(0.45));
  g.userData = { glow: [capM] };
  return g;
}
function makeTree() {
  const g = new THREE.Group();
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.11, 0.5, 14), std('#7a4b2a', { r: 0.8 }));
  trunk.position.y = 0.25;
  const leafM = std('#2fa35a', { r: 0.6 });
  [[0.5, 0.62, 0.62], [0.42, 0.56, 1.0], [0.32, 0.48, 1.36]].forEach(([r, h, y]) => {
    const c = new THREE.Mesh(new THREE.ConeGeometry(r, h, 28), leafM); c.position.y = y; g.add(c);
  });
  g.add(trunk, blob(0.6));
  g.userData = { glow: [leafM] };
  return g;
}
const rupeeCanvas = document.createElement('canvas');
rupeeCanvas.width = rupeeCanvas.height = 256;
function drawRupee() {
  const g = rupeeCanvas.getContext('2d'); g.fillStyle = '#e9b544'; g.fillRect(0, 0, 256, 256);
  g.strokeStyle = '#c48f22'; g.lineWidth = 14; g.beginPath(); g.arc(128, 128, 108, 0, Math.PI * 2); g.stroke();
  g.fillStyle = '#b8811a'; g.font = '800 150px Pop, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('₹', 128, 136);
}
drawRupee();
const rupeeTex = new THREE.CanvasTexture(rupeeCanvas);
rupeeTex.colorSpace = THREE.SRGBColorSpace;
function makeCoin() {
  const g = new THREE.Group();
  const side = std('#d9a33a', { m: 0.8, r: 0.3, env: 1.0 });
  const face = new THREE.MeshStandardMaterial({ map: rupeeTex, metalness: 0.7, roughness: 0.32, envMapIntensity: 1.0 });
  const c = new THREE.Mesh(new THREE.CylinderGeometry(0.44, 0.44, 0.12, 56), [side, face, face]);
  c.rotation.x = Math.PI / 2; c.position.y = 0.5;
  const sp = new THREE.Group(); sp.add(c);
  g.add(sp, blob(0.5));
  g.userData = { glow: [side], spin: sp };
  return g;
}
function makePawn(color) {
  const g = new THREE.Group();
  const bodyM = std(color, { r: 0.38 });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.27, 0.46, 8, 28), bodyM);
  body.position.y = 0.55;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.22, 32, 24), std(SKIN, { r: 0.5 }));
  head.position.y = 1.18;
  const bob = new THREE.Group(); bob.add(body, head);
  g.add(bob, blob(0.5));
  g.userData = { glow: [bodyM], bob };
  return g;
}
function makeBox(color) {
  const g = new THREE.Group();
  const m = std(color, { r: 0.35 });
  const b = new THREE.Mesh(rbox(0.8, 0.8, 0.8, 0.12), m); b.position.y = 0.4;
  g.add(b); g.userData = { glow: [m] };
  return g;
}
function makeDot(color) {
  const g = new THREE.Group();
  const m = std(color, { r: 0.28, env: 0.8 });
  const s = new THREE.Mesh(new THREE.SphereGeometry(0.36, 40, 30), m); s.position.y = 0.36;
  g.add(s, blob(0.42)); g.userData = { glow: [m] };
  return g;
}
function makeGap() {
  const g = new THREE.Group();
  const m = new THREE.Mesh(rbox(1, 0.24, 0.72, 0.07), std('#2fb7a6', { r: 0.4 }));
  m.position.y = 0.12; g.add(m); g.userData = { box: m };
  return g;
}
function makeSeg(color) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(rbox(1, 1, 1), std(color, { r: 0.34, env: 0.7 }));
  g.add(m); g.userData = { box: m };
  return g;
}
function trackTexture(lanes) {
  const c = document.createElement('canvas'); c.width = 2048; c.height = 64 * lanes + 32;
  const g = c.getContext('2d');
  g.fillStyle = '#b8452f'; g.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 4000; i++) { g.fillStyle = `rgba(0,0,0,${Math.random() * 0.06})`; g.fillRect(Math.random() * c.width, Math.random() * c.height, 3, 3); }
  g.fillStyle = '#f6efe6';
  for (let i = 0; i <= lanes; i++) g.fillRect(0, 16 + i * 64 - 2, c.width, 4);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function makeTrack(it) {
  const g = new THREE.Group();
  const lanes = it.lanes || 3;
  const m = new THREE.Mesh(new THREE.BoxGeometry(it.w, 0.06, it.d), [std('#a9442f'), std('#a9442f'), new THREE.MeshStandardMaterial({ map: trackTexture(lanes), roughness: 0.9 }), std('#a9442f'), std('#a9442f'), std('#a9442f')]);
  m.position.y = 0.03; m.receiveShadow = true;
  g.add(m);
  return g;
}
function makeFinish(it) {
  const g = new THREE.Group();
  const line = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.065, it.d), std('#fff3c4', { r: 0.5 }));
  line.position.y = 0.035;
  const postM = std('#f4f4f6', { r: 0.3 });
  const p1 = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.7, 16), postM); p1.position.set(0, 0.85, -it.d / 2 - 0.15);
  const p2 = p1.clone(); p2.position.z = it.d / 2 + 0.15;
  const tape = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, it.d + 0.3), std('#ffcf3d', { r: 0.4 })); tape.position.y = 1.45;
  g.add(line, p1, p2, tape);
  return g;
}
function makeBeam(it) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(rbox(it.w, 0.14, 0.34, 0.06), std('#f3efe4', { r: 0.4 }));
  m.position.y = 0.07; g.add(m);
  return g;
}
function makeTick() {
  const g = new THREE.Group();
  const m = new THREE.Mesh(rbox(0.07, 0.2, 0.5, 0.03), std('#f3efe4', { r: 0.4 }));
  m.position.y = 0.1; g.add(m);
  return g;
}
function makeArc(it) {
  const g = new THREE.Group();
  const x0 = it.x0, x1 = it.x1, h = it.hgt || 1.1;
  const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(x0, 0.2, 0), new THREE.Vector3((x0 + x1) / 2, h * 2, 0), new THREE.Vector3(x1, 0.2, 0));
  const geo = new THREE.TubeGeometry(curve, 64, 0.085, 12, false);
  const m = new THREE.Mesh(geo, std('#ffcf3d', { r: 0.35, e: '#ffb800', ei: 0.25 }));
  g.add(m); g.userData = { arc: m, segs: 64 * 12 * 6 };
  return g;
}
function makeBoard(it) {
  const g = new THREE.Group();
  const frame = new THREE.Mesh(rbox(it.w + 0.36, it.h + 0.36, 0.22, 0.1), std('#8a5a33', { r: 0.6 }));
  const slate = new THREE.Mesh(new THREE.PlaneGeometry(it.w, it.h), std('#1d3b30', { r: 0.95, env: 0.1 }));
  slate.position.z = 0.115;
  const legM = std('#6e4527', { r: 0.7 });
  const l1 = new THREE.Mesh(rbox(0.16, 0.9, 0.5, 0.04), legM); l1.position.set(-it.w / 2 + 0.6, -it.h / 2 - 0.45, 0);
  const l2 = l1.clone(); l2.position.x = it.w / 2 - 0.6;
  const b = new THREE.Group(); b.add(frame, slate, l1, l2); b.position.y = it.h / 2 + 0.75;
  g.add(b);
  return g;
}

function makeObj(it) {
  switch (it.type) {
    case 'bell': return makeBell();
    case 'pole': return makePole(it.color);
    case 'tree': return makeTree();
    case 'coin': return makeCoin();
    case 'person': case 'pawn': return makePawn(it.color);
    case 'box': return makeBox(it.color);
    case 'gap': return makeGap();
    case 'seg': return makeSeg(it.color);
    case 'track': return makeTrack(it);
    case 'finish': return makeFinish(it);
    case 'beam': return makeBeam(it);
    case 'tick': return makeTick();
    case 'arc': return makeArc(it);
    case 'board': return makeBoard(it);
    default: return makeDot(it.color);
  }
}

// ── scene layouts: a state -> items (+ labels) and a framing ────────────
function layoutRow(s) {
  const n = clamp(Math.round(s.n ?? 4), 1, 20);
  const sp = n <= 6 ? 1.75 : Math.min(1.75, 14 / (n - 1));
  const sc = clamp(sp / 1.75, 0.42, 1) * 1.15;
  const kind = ['bell', 'pole', 'tree', 'coin', 'person', 'box', 'dot'].includes(s.item) ? s.item : 'dot';
  const lit = s.lit;
  const on = (i) => lit === 'all' || lit === i || (Array.isArray(lit) && lit.includes(i));
  const x = (i) => (i - (n - 1) / 2) * sp;
  const items = [];
  for (let i = 0; i < n; i++) {
    const labels = [];
    if (s.numbers !== false) labels.push({ text: String(i + 1), cls: 'num' + (on(i) ? ' on' : ''), anchor: 'above', dy: HEIGHT[kind] * sc + 0.32 });
    items.push({ id: `row:${i}`, type: kind, x: x(i), z: 0, s: sc, color: PAL[i % PAL.length], lit: on(i), delay: Math.min(i, 12) * 0.06, labels });
  }
  const gaps = Array.isArray(s.gaps) ? s.gaps : [];
  for (let i = 0; i < Math.min(gaps.length, n - 1); i++) {
    items.push({ id: `gap:${i}`, type: 'gap', x: (x(i) + x(i + 1)) / 2, z: 1.0 * sc, s: 1, gw: sp * 0.74, gd: 0.72 * sc,
      delay: 0.08 * i, labels: [{ text: String(gaps[i]), cls: 'gap', anchor: 'gaptop' }] });
  }
  const width = Math.max(5.6, (n - 1) * sp + 1.6);
  return { items, note: s.note, noteAt: [0, 0, 2.1 * Math.max(sc, 0.7)],
    frame: { cx: 0, cy: HEIGHT[kind] * sc * 0.5, cz: 0.4, w: width, h: HEIGHT[kind] * sc + 1.6, el: 22, az: 0 } };
}

function layoutTrack(s) {
  const L = Number(s.length) || 100;
  const runners = Array.isArray(s.runners) ? s.runners : [];
  const pos = runners.map((r) => Number(r.pos) || 0);
  const lanes = Math.max(3, runners.length);
  const span = 12, X = (m) => (m - L / 2) * span / L;
  const d = lanes * 0.9 + 0.3;
  const items = [{ id: 'track', type: 'track', x: 0, z: 0, w: span + 4, d, lanes, s: 1, noPop: true },
                 { id: 'finish', type: 'finish', x: X(L), z: 0, d, s: 1, labels: [{ text: `FINISH · ${s.unit_label || L + ' m'}`, cls: 'gold', anchor: 'above', dy: 2.0 }] }];
  runners.forEach((r, j) => {
    const labels = [{ text: String(r.name), cls: 'pill', anchor: 'above', dy: 1.78 }];
    if (r.label) labels.push({ text: String(r.label), cls: 'dark', anchor: 'front', dz: 0.75 });
    items.push({ id: `run:${r.name}`, type: 'pawn', x: X(Number(r.pos) || 0), z: (j + 0.5 - runners.length / 2) * 0.9, s: 1, color: PAL[j % PAL.length], labels, delay: 0.1 * j });
  });
  const lo = pos.length ? Math.min(...pos) : 0;
  const v0 = Number.isFinite(Number(s.view_from)) && s.view_from !== undefined ? Number(s.view_from) : (lo > 0.4 * L ? Math.max(0, lo - 0.3 * L) : 0);
  const cx = (X(v0) + X(L)) / 2 + 0.3, w = Math.max(6, (X(L) - X(v0)) * 1.08 + 2.2);
  return { items, note: s.note, noteAt: [cx, 0, d / 2 + 1.3], frame: { cx, cy: 0.6, cz: 0, w, h: 3.2, el: 26, az: 16 } };
}

function layoutBars(s) {
  const bars = Array.isArray(s.bars) ? s.bars : [];
  const n = Math.max(bars.length, 1);
  const sp = n <= 3 ? 1.95 : 1.6, bw = n <= 3 ? 1.4 : 1.25;
  const tot = bars.map((b) => (b.segments || []).reduce((a, g) => a + (Number(g.v) || 0), 0));
  const mx = Number(s.max) || Math.max(1, ...tot);
  const HM = 3.8;
  const items = [];
  bars.forEach((b, i) => {
    const x = (i - (n - 1) / 2) * sp;
    const segs = b.segments || [];
    segs.forEach((g, j) => {
      const h = Math.max(0.04, HM * (Number(g.v) || 0) / mx);
      const labels = [];
      if (g.label) labels.push({ text: String(g.label), cls: 'seg', anchor: 'mid' });
      if (j === 0) labels.push({ text: String(b.label), cls: 'floor', anchor: 'front', dz: bw / 2 + 0.55 });
      if (j === segs.length - 1 && b.top) labels.push({ text: String(b.top), cls: 'gold', anchor: 'top', dy: 0.5 });
      items.push({ id: `seg:${b.label}:${j}`, type: 'seg', bar: `bar:${b.label}`, j, x, z: 0, w: bw, d: bw, h,
        color: g.color || SEG[j % SEG.length], grow: true, delay: 0.14 * i + 0.22 * j, labels });
    });
  });
  const width = Math.max(5.6, (n - 1) * sp + bw + 1.0);
  return { items, note: s.note, noteAt: [0, 0, bw / 2 + 2.4], frame: { cx: 0, cy: HM * 0.42, cz: 0.3, w: width, h: HM + 1.3, el: 18, az: 0 } };
}

function layoutLine(s) {
  const a = Number(s.from) || 0, b = Number(s.to) || 10;
  const span = 11, X = (v) => (v - (a + b) / 2) * span / ((b - a) || 1);
  const tick = Number(s.tick) || Math.max(1, (b - a) / 10);
  const items = [{ id: 'beam', type: 'beam', x: 0, z: 0, w: span + 1.2, s: 1, noPop: true }];
  let k = 0;
  for (let v = a; v <= b + 1e-9 && k < 40; v += tick, k++) {
    const lab = Number.isInteger(v) ? String(v) : String(+v.toFixed(2));
    items.push({ id: `tick:${lab}`, type: 'tick', x: X(v), z: 0, s: 1, delay: 0.03 * k, labels: [{ text: lab, cls: 'tick', anchor: 'front', dz: 0.75 }] });
  }
  (s.jumps || []).forEach((jp, j) => {
    const x0 = X(Number(jp.from)), x1 = X(Number(jp.to));
    items.push({ id: `jump:${jp.from}:${jp.to}`, type: 'arc', x: 0, z: 0, x0, x1, hgt: Math.min(1.4, 0.45 + Math.abs(x1 - x0) * 0.22), s: 1, draw: true, delay: 0.25 * j,
      labels: jp.label ? [{ text: String(jp.label), cls: 'gold', anchor: 'arc' }] : [] });
  });
  (s.points || []).forEach((p) => {
    const col = p.good ? '#2fbf71' : (p.bad ? '#ff5d52' : '#f4a73a');
    items.push({ id: `pt:${p.at}`, type: 'dot', x: X(Number(p.at)), z: 0, s: 1.0, color: col, labels: p.label ? [{ text: String(p.label), cls: 'pill', anchor: 'above', dy: 1.25 }] : [] });
  });
  return { items, note: s.note, noteAt: [0, 0, 1.9], frame: { cx: 0, cy: 0.6, cz: 0.3, w: span + 1.2, h: 3.0, el: 22, az: 0 } };
}

function layoutBoard(s) {
  const lines = (s.lines || []).slice(0, 4);
  const bw = 8.2, bh = 4.4;
  const labels = lines.map((ln, i) => ({ text: String(ln), cls: 'chalk' + (i === lines.length - 1 ? ' last' : ''), anchor: 'board',
    by: bh / 2 + 0.75 + bh / 2 - (i + 0.8) * (bh / Math.max(lines.length + 0.6, 2.6)), key: `${i}:${ln}` }));
  return { items: [{ id: 'board', type: 'board', x: 0, z: 0, w: bw, h: bh, s: 1, labels }], note: null,
    frame: { cx: 0, cy: bh / 2 + 0.75, cz: 0, w: bw + 0.8, h: bh + 1.2, el: 8, az: 0 } };
}

const LAYOUTS = { row: layoutRow, track: layoutTrack, bars: layoutBars, line: layoutLine, board: layoutBoard };
function layout(state) {
  if (!state) return { items: [], note: null, frame: null };
  const f = LAYOUTS[state.type] || layoutBoard;
  const out = f(state);
  out.type = state.type;
  out.counters = Array.isArray(state.counters) ? state.counters.slice(0, 3) : [];
  return out;
}

// ── blending two layouts ────────────────────────────────────
function blend(P, C, k, tl, evStart) {
  const pm = new Map(P.items.map((i) => [i.id, i]));
  const out = [];
  for (const c of C.items) {
    const p = pm.get(c.id);
    if (p) {
      pm.delete(c.id);
      const o = { ...c, app: 1 };
      for (const key of ['x', 'z', 'h', 'w', 'd', 's', 'x0', 'x1', 'gw', 'gd']) {
        if (typeof c[key] === 'number' && typeof p[key] === 'number') o[key] = lerp(p[key], c[key], k);
      }
      o.moving = Math.abs((p.x ?? 0) - (c.x ?? 0)) > 0.05 && k < 1;
      o.litNew = c.lit && !p.lit;
      o.litAt = evStart;
      out.push(o);
    } else {
      const lt = tl - (c.delay || 0);
      const a = c.noPop ? easeOut(lt / 0.5) : (c.grow ? backOut(lt / 0.75) : spring(lt, 2.0, 0.48));
      out.push({ ...c, app: a, litNew: !!c.lit, litAt: evStart + (c.delay || 0) + 0.45 });
    }
  }
  for (const p of pm.values()) {
    const a = 1 - ease(tl / 0.45);
    if (a > 0.01) out.push({ ...p, app: a, leaving: true });
  }
  // bars: stack the (animated) segment heights
  const tops = new Map();
  out.filter((i) => i.type === 'seg').sort((a, b) => a.j - b.j).forEach((i) => {
    const y = tops.get(i.bar) ?? 0;
    i.y = y; i.hh = Math.max(0.001, i.h * clamp(i.app, 0, 1.25));
    tops.set(i.bar, y + i.hh);
  });
  return out;
}

// ── item -> mesh ────────────────────────────────────────────
const live = new Map();
function applyItems(items, t) {
  const seen = new Set();
  for (const it of items) {
    seen.add(it.id);
    let rec = live.get(it.id);
    const key = `${it.type}|${it.color || ''}|${it.lanes || ''}|${it.type === 'arc' ? it.x0.toFixed(2) + it.x1.toFixed(2) : ''}|${it.type === 'board' ? it.w : ''}`;
    if (!rec || rec.key !== key) {
      if (rec) root.remove(rec.obj);
      rec = { obj: shadowed(makeObj(it)), key };
      if (it.type === 'track') rec.obj.traverse((m) => { if (m.isMesh) m.castShadow = false; });
      live.set(it.id, rec);
      root.add(rec.obj);
    }
    const o = rec.obj, u = o.userData;
    const a = it.app ?? 1;
    o.visible = a > 0.003;
    o.position.set(it.x ?? 0, it.y ?? 0, it.z ?? 0);
    const s = (it.s ?? 1);
    if (it.type === 'seg') {
      u.box.geometry = rbox(it.w, Math.max(0.02, it.hh), it.d, Math.min(0.1, it.hh / 2.2));
      u.box.position.y = it.hh / 2;
      o.scale.set(1, 1, 1);
    } else if (it.type === 'gap') {
      u.box.geometry = rbox(Math.max(0.1, it.gw), 0.24, it.gd ?? 0.72, 0.07);
      o.scale.setScalar(Math.max(0.0001, a));
    } else if (it.type === 'arc') {
      const k = it.leaving ? 1 : clamp(a, 0, 1);
      u.arc.geometry.setDrawRange(0, Math.floor(u.segs * k / 6) * 6);
      o.scale.setScalar(1);
      o.position.set(0, 0, 0);
    } else if (it.type === 'track' || it.type === 'beam' || it.type === 'board') {
      o.scale.set(1, 1, 1);
      if (it.type === 'board') { o.position.y = (1 - clamp(a)) * -0.6; }
      o.visible = a > 0.02;
      o.traverse((m) => { if (m.isMesh && m.material && !Array.isArray(m.material)) { m.material.transparent = a < 0.99; m.material.opacity = clamp(a); } });
    } else {
      o.scale.setScalar(Math.max(0.0001, s * a));
    }
    // lit: glow + a hop when it lights up
    const lt = t - (it.litAt ?? -9);
    if (u.glow) {
      for (const m of u.glow) {
        m.emissive.set(it.lit ? '#ffb020' : '#000000');
        m.emissiveIntensity = it.lit ? (it.litNew ? 0.25 + 0.6 * Math.exp(-lt * 2.5) : 0.25) : 0;
      }
    }
    if (it.litNew && lt > 0 && lt < 0.5) o.position.y += Math.sin(Math.PI * lt / 0.5) * 0.3 * s;
    if (u.swing) u.swing.rotation.z = it.litNew && lt > 0 ? Math.sin(lt * 14) * 0.35 * Math.exp(-lt * 2.2) : 0;
    if (u.spin) u.spin.rotation.y = Math.sin(t * 1.3 + (it.x ?? 0)) * 0.5;
    if (u.bob) u.bob.position.y = it.moving ? Math.abs(Math.sin(t * 13)) * 0.12 : 0;
  }
  for (const [id, rec] of live) if (!seen.has(id)) rec.obj.visible = false;
}

// ── labels (HTML pinned to 3D points) ───────────────────────
const lblEls = new Map();
const v3 = new THREE.Vector3();
function project(x, y, z) {
  v3.set(x, y, z).project(camera);
  return [(v3.x + 1) / 2 * W, (1 - v3.y) / 2 * H, v3.z];
}
function anchorPoint(it, l) {
  const s = (it.s ?? 1) * (it.type === 'seg' ? 1 : clamp(it.app ?? 1, 0, 1.2));
  switch (l.anchor) {
    case 'mid': return [it.x, (it.y ?? 0) + (it.hh ?? 0) / 2, (it.z ?? 0) + it.d / 2 + 0.02];
    case 'top': return [it.x, (it.y ?? 0) + (it.hh ?? 0) + (l.dy ?? 0.4), it.z ?? 0];
    case 'front': return [it.x, 0.02, (it.z ?? 0) + (l.dz ?? 0.7)];
    case 'gaptop': return [it.x, 0.25, (it.z ?? 0) + 0.05];
    case 'arc': return [(it.x0 + it.x1) / 2, (it.hgt ?? 1) + 0.45, 0];
    case 'board': return [-3.4, l.by, 0.2];
    default: return [it.x, (it.y ?? 0) + (l.dy ?? 1) * s, it.z ?? 0];
  }
}
function drawLabels(items, extra, t) {
  const seen = new Set();
  const host = $('labels');
  const put = (id, text, cls, p, op, scale = 1, align = 'center', screen = null) => {
    seen.add(id);
    let el = lblEls.get(id);
    if (!el) { el = document.createElement('div'); el.className = 'lbl'; host.appendChild(el); lblEls.set(id, el); el._t = null; el._c = null; }
    if (el._t !== text) { el.textContent = text; el._t = text; }
    if (el._c !== cls) { el.className = 'lbl ' + cls; el._c = cls; }
    const [sx, sy] = screen || project(...p);
    const tx = align === 'left' ? '0%' : '-50%';
    el.style.transform = `translate(${sx.toFixed(1)}px, ${sy.toFixed(1)}px) translate(${tx}, -50%) scale(${scale.toFixed(3)})`;
    el.style.opacity = clamp(op).toFixed(3);
    el.style.display = op > 0.01 ? 'block' : 'none';
  };
  for (const it of items) {
    (it.labels || []).forEach((l, i) => {
      const a = it.type === 'seg' ? clamp((it.hh ?? 0) / Math.max(it.h, 0.01) * 1.4 - 0.3) : clamp(it.app ?? 1);
      let op = it.leaving ? clamp(it.app * 2 - 1) : (l.anchor === 'board' ? clamp(((it.labelT?.[i]) ?? 1)) : a);
      if (l.anchor === 'board') {
        const k = it.boardK?.[l.key] ?? 1;
        op = Math.min(op, k);
        put(`${it.id}#${l.key}`, l.text, l.cls, anchorPoint(it, l), op, 0.96 + 0.04 * k, 'left');
        return;
      }
      if (l.anchor === 'mid' && (it.hh ?? 0) < 0.42) op = 0;
      put(`${it.id}#${i}`, l.text, l.cls, anchorPoint(it, l), op, l.cls.startsWith('num') ? 0.7 + 0.3 * a : 0.85 + 0.15 * a);
    });
    if (it.litNew && (it.app ?? 1) > 0.85 && (it.s ?? 1) >= 0.7) {
      const lt = t - it.litAt;
      if (lt > 0 && lt < 0.9) {
        const top = (it.y ?? 0) + HEIGHT[it.type] * (it.s ?? 1) * 0.72;
        put(`${it.id}#ripple`, '', 'ripple', [it.x, top, it.z ?? 0], 1 - lt / 0.9, (0.5 + lt * 1.6) * (it.s ?? 1));
      }
    }
  }
  for (const e of extra) put(e.id, e.text, e.cls, e.p || [0, 0, 0], e.op, e.scale ?? 1, 'center', e.screen || null);
  for (const [id, el] of lblEls) if (!seen.has(id)) el.style.display = 'none';
}

// ── counters ────────────────────────────────────────────────
const ctrEls = new Map();
function drawCounters(prevC, curC, tl, top) {
  const host = $('counters');
  const pm = new Map(prevC.map((c) => [c.label, c]));
  const n = curC.length, tw = 300, gap = 28;
  const x0 = (W - (n * tw + (n - 1) * gap)) / 2;
  const seen = new Set();
  curC.forEach((c, i) => {
    seen.add(c.label);
    let el = ctrEls.get(c.label);
    if (!el) {
      el = document.createElement('div'); el.className = 'ctr';
      el.innerHTML = '<div class="k"></div><div class="v"></div>';
      host.appendChild(el); ctrEls.set(c.label, el);
      el.style.setProperty('--c', ['#5aa8ff', '#4fd88a', '#ffc83d'][i % 3]);
    }
    el.querySelector('.k').textContent = c.label;
    const p = pm.get(c.label);
    const v1 = Number(c.value), v0 = p ? Number(p.value) : 0;
    let shown = c.value;
    if (Number.isFinite(v1) && Number.isFinite(v0)) {
      const v = lerp(v0, v1, easeOut(tl / 0.9));
      shown = Number.isInteger(v1) && Number.isInteger(v0) ? String(Math.round(v)) : String(+v.toFixed(2));
    }
    el.querySelector('.v').textContent = shown;
    const a = p ? 1 : spring(tl - 0.1 * i, 2.0, 0.5);
    el.style.left = `${x0 + i * (tw + gap)}px`;
    el.style.top = `${top}px`;
    el.style.transform = `translateY(${(1 - a) * 40}px) scale(${0.85 + 0.15 * a})`;
    el.style.opacity = clamp(a * 1.5).toFixed(3);
    el.style.display = 'block';
  });
  for (const [k, el] of ctrEls) if (!seen.has(k)) el.style.display = 'none';
}

// ── camera ──────────────────────────────────────────────────
const TANV = Math.tan(THREE.MathUtils.degToRad(15)), TANH = TANV * W / H;
function cameraFor(fr, spanPx) {
  const dW = fr.w / (2 * TANH * 0.95);
  const dH = fr.h * H / (2 * TANV * spanPx);
  return { ...fr, dist: Math.max(dW, dH, 8) };
}
function blendCam(a, b, k) {
  if (!a) return b;
  const o = {};
  for (const key of ['cx', 'cy', 'cz', 'dist', 'el', 'az', 'ty']) o[key] = lerp(a[key], b[key], k);
  return o;
}
// ── camera director: a different move on every beat ────────
// Each run of lines with the same card gets one shot; within it the camera keeps moving, and it eases
// into the next shot (the trap cuts in hard, with a zoom punch).
let RUNS = [];
const SHOTS = {
  hero:  (u) => ({ el: 7, az: 12 - 12 * u, dist: 0.94 }),
  side:  (u) => ({ el: 12, az: -26 + 8 * u, dist: 0.95 }),
  punch: (u, tl) => ({ el: 15, az: 3, dist: 0.98 - 0.16 * easeOut(tl / 0.35) }),
  orbit: (u) => ({ el: 19, az: -16 + 30 * u, dist: 0.96 }),
  high:  (u) => ({ el: 44, az: 12 - 18 * u, dist: 0.98 }),
  push:  (u) => ({ el: 16, az: 6 - 6 * u, dist: 1.14 - 0.24 * u }),
  pull:  (u) => ({ el: 21, az: -8 + 8 * u, dist: 0.9 + 0.22 * u }),
  wide:  (u) => ({ el: 24, az: 10 * u, dist: 1.05 }),
};
function shotRuns(E) {
  const steps = ['push', 'high', 'side', 'orbit'];
  const out = [];
  let k = 0, cur = null;
  E.forEach((e, i) => {
    const kind = (e.card || {}).kind;
    if (cur && e.group && e.group === E[i - 1].group) { out.push(cur); return; }
    let name = 'wide';
    if (kind === 'attempt') name = 'hero';
    else if (kind === 'hook') name = (i === 0 || (E[i - 1].card || {}).kind === 'attempt') ? 'hero' : 'side';
    else if (kind === 'trap') name = 'punch';
    else if (kind === 'answer') name = 'orbit';
    else if (kind === 'step') name = steps[k++ % steps.length];
    else if (kind === 'shortcut') name = 'high';
    else if (kind === 'your_turn') name = 'pull';
    cur = { name, first: i, start: e.start, end: e.start + e.dur };
    out.push(cur);
  });
  out.forEach((r) => { const last = E.map((e, i) => [e, i]).filter(([, i]) => out[i] === r).pop(); r.end = last[0].start + last[0].dur + 0.3; r.dur = Math.max(0.5, r.end - r.start); });
  return out;
}
function shotCam(run, t, base) {
  const u = clamp((t - run.start) / run.dur), tl = t - run.start;
  const s = SHOTS[run.name](u, tl);
  let el = s.el, az = base.az + s.az, dist = s.dist;
  if (base.type === 'board') { el = Math.min(el, 14); az = clamp(az, -20, 20); }
  if (base.type === 'track') { el = Math.max(el, 12); az = base.az + 0.35 * s.az; dist = Math.max(dist, 1.0); }
  if (base.type === 'row' || base.type === 'line') dist = Math.max(dist, 0.97);   // keep every item in the frame
  const out = { ...base, el, az, dist: base.dist * dist };
  if (run.name === 'punch') { const k = Math.exp(-tl * 7) * (tl > 0.02 ? 1 : 0); out.cx += Math.sin(tl * 47) * 0.18 * k; out.cy += Math.cos(tl * 39) * 0.12 * k; }
  return out;
}

function placeCamera(c, t) {
  const az = THREE.MathUtils.degToRad(c.az + 1.6 * Math.sin(t * 0.21));
  const el = THREE.MathUtils.degToRad(Math.max(3, c.el + 0.8 * Math.sin(t * 0.17 + 1.3)));
  const d = c.dist * (1 - 0.01 * Math.sin(t * 0.13));
  camera.position.set(c.cx + d * Math.sin(az) * Math.cos(el), c.cy + d * Math.sin(el), c.cz + d * Math.cos(az) * Math.cos(el));
  camera.lookAt(c.cx, c.cy, c.cz);
  camera.setViewOffset(W, H, 0, H / 2 - c.ty, W, H);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  const r = Math.max(8, c.dist * 0.55);
  sun.position.set(c.cx - r * 0.55, r * 1.25, c.cz + r * 0.75);
  sun.target.position.set(c.cx, 0, c.cz);
  Object.assign(sun.shadow.camera, { left: -r, right: r, top: r, bottom: -r, near: 0.5, far: r * 4 });
  sun.shadow.camera.updateProjectionMatrix();
}

// ── cards ───────────────────────────────────────────────────
const cardEls = new Map();
const STAMP_TRAP = 0.42, STAMP_OK = 0.6;   // seconds after the card comes in (qt3d.py times the thud to these)
function cardEl(ev) {
  const g = ev.group;
  if (cardEls.has(g)) return cardEls.get(g);
  const c = ev.card || {};
  const el = document.createElement('div');
  if (c.kind === 'attempt') {
    el.className = 'card dark attempt';
    el.innerHTML = `<div class="tag">ASKED IN</div><div class="exam">${esc(c.exam || 'CA Foundation')}</div><div class="when">${esc(c.when || '')}</div><div class="sub">${esc(c.sub || '')}</div>`;
  } else if (c.kind === 'answer') {
    el.className = 'card dark answer';
    el.innerHTML = `<div class="small">${esc(c.small || 'The right answer')}</div><div class="big"><span class="t">${esc(c.big)}</span><span class="ok">✓</span></div><div class="stamp green">VERIFIED ✓</div>`;
  } else if (c.kind === 'hook') {
    el.className = 'card dark hook';
    el.innerHTML = `<div class="small">${esc(c.small)}</div><div class="big">${String(c.big || '').split(/\s+/).map((w) => `<span class="hw">${md(w)}</span>`).join(' ')}</div>`;
  } else if (c.kind === 'trap') {
    el.className = 'card dark trap';
    const big = String(c.big || '').replace(/\s*[×✕x]\s*$/, '');
    el.innerHTML = `<div class="small">${esc(c.small)}</div><div class="big"><span class="t">${esc(big)}</span><span class="x">✕</span></div><div class="sub">${esc(c.sub || 'that is the trap')}</div><div class="stamp red">TRAP</div>`;
  } else if (g === 'q') {
    el.className = 'card cream q';
    const opts = (PLAN.options || []).map((o, i) => `<div class="opt" data-i="${i}"><span class="l">(${'abcd'[i]})</span><span class="t">${esc(o)}</span><span class="mark"></span><span class="strike" style="display:none"></span></div>`).join('');
    el.innerHTML = `<div class="hdr">${esc(PLAN.header || '')}</div><div class="qt">${md(PLAN.question)}</div><div class="opts">${opts}</div>`;
  } else {
    const kind = c.kind;
    el.className = 'card ' + (kind === 'shortcut' ? 'cream short' : kind === 'your_turn' ? 'dark yt' : 'dark step');
    const title = c.title || (kind === 'shortcut' ? 'The shortcut' : kind === 'your_turn' ? 'Your turn' : '');
    el.innerHTML = `<div class="title">${esc(title)}</div><div class="rows"></div>` +
      (kind === 'your_turn' ? `<div class="cta"><svg viewBox="0 0 24 24" fill="none" stroke="#2a1d00" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z"/></svg>Comment your answer</div>` : '');
  }
  el.style.display = 'none';
  $('cards').appendChild(el);
  cardEls.set(g, el);
  return el;
}

function drawCard(ev, t, role) {
  if (!ev.group) return;
  const el = cardEl(ev);
  const c = ev.card || {};
  const since = t - ev.gStart;
  let tr = '', op = 1;
  if (role === 'in') {
    const a = spring(since - (ev.delayIn || 0), 1.9, 0.58);
    tr = `translate(-50%, ${((1 - a) * 36).toFixed(1)}px) scale(${(0.92 + 0.08 * a).toFixed(4)})`;
    op = clamp((since - (ev.delayIn || 0)) / 0.14);
  } else {
    const k = easeOut((t - ev.outAt) / 0.18);
    tr = `translate(-50%, ${(-24 * k).toFixed(1)}px) scale(${(1 - 0.04 * k).toFixed(4)})`;
    op = 1 - k;
  }
  if (c.kind === 'hook' && role === 'in') {
    el.querySelectorAll('.hw').forEach((w, i) => {
      const a = spring(since - 0.1 - 0.07 * i, 2.4, 0.5);
      w.style.display = 'inline-block';
      w.style.transform = `translateY(${((1 - a) * 28).toFixed(1)}px) scale(${(0.8 + 0.2 * a).toFixed(3)})`;
      w.style.opacity = clamp((since - 0.1 - 0.07 * i) / 0.12).toFixed(2);
    });
  }
  if (c.kind === 'answer' && role === 'in') {
    const big = el.querySelector('.big');
    const s = since < 0.12 ? 0 : 1.6 - 0.6 * backOut((since - 0.12) / 0.35);
    big.style.transform = `scale(${s.toFixed(3)})`;
    big.style.opacity = clamp((since - 0.1) / 0.1).toFixed(2);
  }
  if (c.kind === 'attempt' && role === 'in') {
    const w = el.querySelector('.when');
    const s = since < 0.35 ? 0 : 1.7 - 0.7 * backOut((since - 0.35) / 0.35);
    w.style.transform = `scale(${s.toFixed(3)})`;
    w.style.opacity = clamp((since - 0.33) / 0.1).toFixed(2);
  }
  if (c.kind === 'trap' && role === 'in') {
    const ss = since - STAMP_TRAP;
    const sh = Math.sin(ss * 55) * 18 * Math.exp(-ss * 7) * (ss > 0 ? 1 : 0);
    tr = `translate(calc(-50% + ${sh.toFixed(1)}px), 0px) scale(${(0.9 + 0.1 * spring(since, 2.2, 0.5)).toFixed(4)})`;
    const big = el.querySelector('.big');
    const s = since < 0.08 ? 0 : 1.9 - 0.9 * backOut((since - 0.08) / 0.32);
    big.style.transform = `scale(${s.toFixed(3)})`;
    big.style.opacity = clamp((since - 0.06) / 0.1).toFixed(2);
  }
  if ((c.kind === 'trap' || c.kind === 'answer') && role === 'in') {
    const st = el.querySelector('.stamp');
    const ss = since - (c.kind === 'trap' ? STAMP_TRAP : STAMP_OK);
    const rot = c.kind === 'trap' ? -14 : 10;
    st.style.display = ss >= 0 ? 'block' : 'none';
    // slams down from big and tilted, overshoots a hair, settles with a little rotation
    const k = easeIn(clamp(ss / 0.13));
    const settle = ss > 0.13 ? 1 + 0.05 * Math.sin((ss - 0.13) * 30) * Math.exp(-(ss - 0.13) * 12) : 1;
    st.style.transform = `rotate(${(rot + (1 - k) * 10).toFixed(2)}deg) scale(${((2.6 - 1.6 * k) * settle).toFixed(3)})`;
    st.style.opacity = clamp(ss / 0.06).toFixed(2);
    if (c.kind === 'answer') {
      const sk = ss > 0 ? Math.exp(-ss * 9) * Math.sin(ss * 50) * 8 : 0;
      tr = tr.replace('translate(-50%,', `translate(calc(-50% + ${sk.toFixed(1)}px),`);
    }
  }
  el.style.display = op > 0.01 ? 'block' : 'none';
  el.style.transform = tr;
  el.style.opacity = clamp(op).toFixed(3);
  if (role !== 'in') return;

  if (ev.group === 'q') {
    el.querySelectorAll('.qt b').forEach((b, i) => {
      const k = ease((t - ev.gStart - 0.5 - 0.35 * i) / 0.55);
      b.style.backgroundSize = `${(k * 100).toFixed(1)}% 100%`;
    });
    const ot = PLAN.optTimes || [];
    el.querySelectorAll('.opt').forEach((o, i) => {
      const at = ot[i] ?? 1e9;
      const a = spring(t - at, 2.2, 0.5);
      o.style.display = t >= at ? 'block' : 'none';
      o.style.transform = `translateY(${((1 - a) * 24).toFixed(1)}px) scale(${(0.88 + 0.12 * a).toFixed(4)})`;
      o.style.opacity = clamp((t - at) / 0.15).toFixed(2);
      const rv = PLAN.revealAt ?? 1e9;
      const r = t - rv;
      const mark = o.querySelector('.mark'), strike = o.querySelector('.strike');
      o.classList.toggle('ok', r >= 0.15 && i === PLAN.answer);
      if (r >= 0.15 && i === PLAN.answer) {
        mark.textContent = '✓';
        o.style.transform = `scale(${(1 + 0.08 * Math.sin(Math.PI * clamp((r - 0.15) / 0.35))).toFixed(4)})`;
      } else mark.textContent = '';
      const isTrap = i === PLAN.trap && i !== PLAN.answer;
      o.classList.toggle('trapx', r >= 0.5 && isTrap);
      strike.style.display = r >= 0.5 && isTrap ? 'block' : 'none';
      if (isTrap) strike.style.transform = `scaleX(${easeOut((r - 0.5) / 0.3).toFixed(3)})`;
      if (r >= 0.15 && i !== PLAN.answer) o.style.opacity = (1 - 0.55 * clamp((r - 0.15) / 0.3)).toFixed(2);
    });
  } else if (c.kind === 'step' || c.kind === 'shortcut' || c.kind === 'your_turn') {
    const rowsEl = el.querySelector('.rows');
    const rows = c.rows || [];
    while (rowsEl.children.length < rows.length) {
      const r = document.createElement('div'); r.className = 'row'; r.innerHTML = '<div class="in"></div>'; rowsEl.appendChild(r);
    }
    [...rowsEl.children].forEach((r, i) => {
      if (i >= rows.length) { r.style.display = 'none'; return; }
      const inner = r.firstChild;
      const html = md(rows[i]);
      if (inner._h !== html) { inner.innerHTML = html; inner._h = html; }
      const at = (ev.rowTimes || [])[i] ?? ev.start;
      const a = spring(t - at, 2.0, 0.6);
      r.style.display = t >= at ? 'block' : 'none';
      r.style.maxHeight = `${(clamp(a, 0, 1) * 80).toFixed(1)}px`;
      inner.style.transform = `translateY(${((1 - a) * 26).toFixed(1)}px)`;
      inner.querySelectorAll('b').forEach((b) => {            // key numbers count up as their row appears
        if (b._o === undefined) b._o = b.textContent;
        const ct = countText(b._o, easeOut((t - at - 0.12) / 0.5));
        if (ct !== null) b.textContent = ct;
      });
      inner.style.opacity = clamp((t - at) / 0.2).toFixed(2);
    });
    const cta = el.querySelector('.cta');
    if (cta) {
      const at = ev.ctaAt ?? 1e9;
      const a = spring(t - at, 2.0, 0.45);
      cta.style.display = t >= at ? 'inline-flex' : 'none';
      cta.style.transform = `translateY(${(Math.sin(t * 5) * 4 + (1 - a) * 30).toFixed(1)}px) scale(${(0.85 + 0.15 * a).toFixed(4)})`;
    }
  }
}

// ── captions ────────────────────────────────────────────────
let capKey = null;
function drawCaption(ev, t, hide) {
  const el = $('cap');
  if (hide || !ev.words || !ev.words.length || t > ev.start + ev.dur + 0.2) { el.style.display = 'none'; capKey = null; return; }
  const ph = ev.phrases || [[0, ev.words.length - 1]];
  let cur = null;
  for (const [a, b] of ph) {
    if (t >= ev.words[a][1] - 0.08) cur = [a, b];
  }
  if (!cur) { el.style.display = 'none'; return; }
  const [a, b] = cur;
  const ws = ev.words.slice(a, b + 1);
  const key = `${ev.start}|${a}`;
  if (capKey !== key) {
    el.innerHTML = ws.map((w) => `<span class="w">${esc(w[0])}</span>`).join(' ');
    capKey = key;
  }
  el.style.display = 'block';
  [...el.children].forEach((sp, i) => {
    const [w, ws0] = ws[i];
    const on = t >= ws0 - 0.03;
    const isCur = on && (i === ws.length - 1 || t < ws[i + 1][1] - 0.03);
    sp.classList.toggle('f', !on);
    const hl = on && (isNum(w) || isCur && ws.length === 1);
    sp.classList.toggle('hl', hl);
    sp.style.backgroundSize = hl ? `${(easeOut((t - ws0 + 0.02) / 0.2) * 100).toFixed(1)}% 84%` : '0% 46%';
    const k = on ? 1 - easeOut((t - ws0) / 0.22) : 0;
    sp.style.transform = `translateY(${(-8 * k).toFixed(1)}px) scale(${(1 + 0.08 * k).toFixed(3)}) rotate(${hl ? -1.5 : 0}deg)`;
  });
  const a0 = t - ws[0][1];
  el.style.opacity = clamp((a0 + 0.1) / 0.12).toFixed(2);
}

// ── opening sting: logo + "QT TRAP #N" ─────────────────────
function drawSting(t) {
  const S = PLAN.sting, el = $('sting');
  if (!S || t > S.dur + 0.05) { el.style.display = 'none'; return 0; }
  el.style.display = 'block';
  const tile = el.querySelector('.tile'), ttl = el.querySelector('.ttl'), no = el.querySelector('.no b');
  const bars = el.querySelectorAll('.bar');
  const a = spring(t - 0.02, 2.4, 0.5);
  tile.style.transform = `translateY(${((1 - a) * 120).toFixed(1)}px) rotate(${((1 - a) * -18).toFixed(2)}deg) scale(${(0.4 + 0.6 * a).toFixed(3)})`;
  const b = spring(t - 0.18, 2.6, 0.55);
  ttl.style.transform = `translateY(${((1 - b) * 60).toFixed(1)}px)`; ttl.style.opacity = clamp((t - 0.18) / 0.1).toFixed(2);
  const c = t < 0.4 ? 0 : 2.2 - 1.2 * backOut((t - 0.4) / 0.25);
  no.style.transform = `rotate(-4deg) scale(${c.toFixed(3)})`;
  bars[0].style.transform = `translateY(${(-60 * (1 - easeOut(t / 0.25))).toFixed(1)}px)`;
  bars[1].style.transform = `translateY(${(60 * (1 - easeOut(t / 0.25))).toFixed(1)}px)`;
  // exit: the panel wipes up and away to reveal the desk
  const out = easeIn(clamp((t - (S.dur - 0.28)) / 0.28));
  el.style.clipPath = `inset(0 0 ${(out * 100).toFixed(2)}% 0)`;
  return 1 - out;
}

// ── frame ───────────────────────────────────────────────────
let PLAN = null;
let LAY = [];
window.load = async (plan) => {
  PLAN = plan;
  const th = THEMES[plan.theme] || THEMES.green;
  floorMat.color.set(th.floor);
  renderer.setClearColor(th.hor);
  document.body.style.background = th.bg;
  hemi.color.set(th.mid); hemi.groundColor.set(th.floor); hemi.intensity = 0.75;
  buildWorld(th, 1 + Math.floor((plan.total || 1) * 7) % 97);
  RUNS = shotRuns(plan.events);
  const b = plan.badge || {};
  $('badge').innerHTML = `<span class="tag">${esc(b.tag || 'CA FOUNDATION')}</span><span>${esc(b.text || '')}</span>`;
  $('handle').textContent = plan.handle ? `● ${plan.handle}` : '';
  if (plan.logo) {
    const imgs = [document.querySelector('#logo img'), document.querySelector('#end .tile img')];
    for (const im of imgs) { im.src = plan.logo; try { await im.decode(); } catch (e) { /* drawn without it */ } }
    $('logo').style.display = 'flex';
  }
  if (plan.sting) {
    const im = document.querySelector('#sting .tile img');
    if (plan.logo) { im.src = plan.logo; try { await im.decode(); } catch (e) { /* drawn without it */ } }
    document.querySelector('#sting .no b').textContent = '#' + plan.sting.n;
    const [w1, ...rest] = String(plan.sting.label || 'QT TRAP').split(' ');
    document.querySelector('#sting .ttl').innerHTML = `${esc(w1)} <span>${esc(rest.join(' '))}</span>`;
  }
  document.querySelector('#end .follow').innerHTML = plan.handle ? `Follow <span>${esc(plan.handle)}</span>` : '';
  LAY = plan.events.map((ev) => ({ prev: layout(ev.prev), cur: layout(ev.cur) }));
  await document.fonts.ready;
  await Promise.all(['800 40px Pop', '700 40px Pop', '600 40px Pop', '600 40px Int', '700 40px Int', '800 40px Int'].map((f) => document.fonts.load(f, '₹0aA')));
  drawRupee(); rupeeTex.needsUpdate = true;
  // warm up: draw every scene once so shaders compile before frame 0
  for (let i = 0; i < plan.events.length; i += 1) window.seek(plan.events[i].start + 1.0);
  return true;
};

window.seek = (t) => {
  const E = PLAN.events;
  let idx = 0;
  for (let i = 0; i < E.length; i++) if (E[i].start <= t + 1e-6) idx = i;
  const ev = E[idx];
  const tl = t - ev.start;
  const L = LAY[idx];
  const typeChange = !L.prev.type || L.prev.type !== L.cur.type;
  const TR = L.cur.type === 'track' ? 1.8 : 0.85;
  const k = ease(tl / TR);
  const P = typeChange ? { items: idx === 0 ? [] : L.prev.items } : L.prev;
  let items;
  if (typeChange) {
    // old scene leaves, then the new one comes in
    const outItems = idx === 0 ? [] : blend(L.prev, { items: [] }, 1, tl, ev.start);
    const inItems = blend({ items: [] }, L.cur, 1, tl - (idx === 0 ? 0.15 : 0.35), ev.start);
    items = outItems.concat(inItems);
  } else {
    items = blend(P, L.cur, k, tl, ev.start);
  }
  if (L.cur.type === 'board') {
    const prevKeys = new Set(((L.prev.type === 'board' ? L.prev.items[0]?.labels : []) || []).map((l) => l.key));
    for (const it of items) if (it.type === 'board') {
      it.boardK = {};
      (it.labels || []).forEach((l, i) => { it.boardK[l.key] = prevKeys.has(l.key) ? 1 : ease((tl - 0.3 - 0.35 * i) / 0.5); });
    }
  }
  applyItems(items, t);

  // camera: the content framing (eases when the scene changes), then the shot for this beat
  const baseOf = (i) => {
    const l = LAY[i], has = (l.cur.counters || []).length > 0;
    const fr = l.cur.frame || { cx: 0, cy: 1, cz: 0, w: 8, h: 4, el: 22, az: 0 };
    return { ...cameraFor(fr, 720 - (has ? 210 : 0)), ty: 975 + (has ? 170 : 0), type: l.cur.type };
  };
  const base = idx > 0 ? { ...blendCam(baseOf(idx - 1), baseOf(idx), ease(tl / 1.1)), type: L.cur.type } : baseOf(0);
  const run = RUNS[idx];
  let cam = shotCam(run, t, base);
  if (run.first === idx && idx > 0 && run.name !== 'punch') {
    const pr = RUNS[idx - 1];
    const k = ease((t - run.start) / 0.95);
    if (k < 1) cam = blendCam(shotCam(pr, Math.min(t, pr.end), { ...baseOf(idx - 1), type: LAY[idx - 1].cur.type }), cam, k);
  }
  placeCamera(cam, t);

  // labels: scene note
  const extra = [];
  const notes = [];
  if (L.prev.note && (typeChange || L.prev.note !== L.cur.note) && idx > 0) notes.push({ n: L.prev.note, at: L.prev.noteAt, op: 1 - ease(tl / 0.3), id: `note:${idx - 1}:${L.prev.note}` });
  if (L.cur.note) {
    const same = !typeChange && L.prev.note === L.cur.note;
    const a = same ? 1 : spring(tl - 0.35, 2.0, 0.5);
    notes.push({ n: L.cur.note, at: L.cur.noteAt, op: a, scale: 0.85 + 0.15 * clamp(a, 0, 1.2), id: same ? `note:${L.cur.note}` : `note:${idx}:${L.cur.note}` });
  }
  for (const nt of notes) {
    const [nx, ny] = project(...(nt.at || [0, 0, 2]));
    extra.push({ id: nt.id, text: nt.n, cls: 'note', screen: [clamp(nx, 220, W - 220), clamp(ny + 40, 560, 1300)], op: nt.op, scale: nt.scale ?? 1 });
  }
  drawLabels(items, extra, t);

  // counters sit between the card and the scene
  drawCounters(typeChange ? [] : (L.prev.counters || []), L.cur.counters || [], tl, ev.group === 'q' ? 760 : 620);

  // cards: the current group comes in, the previous group leaves
  for (const el of cardEls.values()) el.style.display = 'none';
  const leaving = idx > 0 && E[idx - 1].group && E[idx - 1].group !== ev.group;
  if (leaving && tl < 0.2) drawCard({ ...E[idx - 1], outAt: ev.start }, t, 'out');
  drawCard({ ...ev, delayIn: leaving && ev.gStart === ev.start ? 0.15 : 0 }, t, 'in');

  // countdown + dim
  const cd = ev.countdown;
  const inCd = cd && t >= cd[0] - 0.05 && t < cd[1] + 0.1;
  const pauseLine = ev.card && ev.card.kind === 'pause';
  const dimK = pauseLine ? (inCd ? 1 : ease(tl / 0.4)) * (cd && t > cd[1] ? 1 - ease((t - cd[1]) / 0.3) : 1) : 0;
  $('dim').style.opacity = (0.55 * dimK).toFixed(3);
  const cdEl = $('cd');
  if (pauseLine) {
    cdEl.style.opacity = dimK.toFixed(3);
    const arc = $('cdarc'), num = $('cdnum');
    if (cd && t >= cd[0]) {
      const p = clamp((t - cd[0]) / (cd[1] - cd[0]));
      arc.setAttribute('stroke-dashoffset', (603.2 * (1 - p)).toFixed(1));
      const n = Math.max(1, 3 - Math.floor(p * 3));
      const local = (t - cd[0]) - (3 - n) * (cd[1] - cd[0]) / 3;
      num.textContent = String(n);
      num.style.transform = `scale(${(1 + 0.35 * (1 - easeOut(local / 0.3))).toFixed(3)})`;
    } else {
      arc.setAttribute('stroke-dashoffset', '603.2');
      num.textContent = '❚❚';
      num.style.fontSize = '64px';
      num.style.transform = `scale(${(1 + 0.06 * Math.sin(t * 6)).toFixed(3)})`;
    }
    if (cd && t >= cd[0]) num.style.fontSize = '120px';
    cdEl.querySelector('.msg').style.opacity = cd && t >= cd[0] - 0.05 ? '1' : '0';
  } else cdEl.style.opacity = 0;

  // flash on the trap and on the answer
  const fl = $('flash');
  const kind = ev.card && ev.card.kind;
  if (kind === 'trap' || kind === 'reveal' || kind === 'answer') {
    const col = kind === 'trap' ? '255,70,60' : '60,220,120';
    const a = 0.8 * Math.exp(-Math.max(0, tl - (kind === 'trap' ? STAMP_TRAP : 0.15)) * 3.5) * (tl > (kind === 'trap' ? STAMP_TRAP : 0.15) ? 1 : 0);
    fl.style.background = `radial-gradient(120% 80% at 50% 45%, rgba(${col},0) 45%, rgba(${col},0.75) 100%)`;
    fl.style.opacity = a.toFixed(3);
  } else fl.style.opacity = 0;

  // end card: the logo, big, over the last line
  const endEl = $('end');
  const endAt = PLAN.endAt ?? 1e9;
  if (PLAN.logo && t >= endAt) {
    const a = spring(t - endAt, 1.8, 0.5);
    endEl.style.opacity = clamp((t - endAt) / 0.2).toFixed(3);
    endEl.querySelector('.tile').style.transform = `translateY(${((1 - a) * 60).toFixed(1)}px) scale(${(0.7 + 0.3 * a).toFixed(4)}) rotate(${((1 - a) * -6).toFixed(2)}deg)`;
    endEl.querySelector('.follow').style.transform = `translateY(${((1 - spring(t - endAt - 0.15, 1.8, 0.55)) * 40).toFixed(1)}px)`;
    $('dim').style.opacity = Math.max(+$('dim').style.opacity, 0.78 * clamp((t - endAt) / 0.4)).toFixed(3);
    $('logo').style.opacity = (1 - clamp((t - endAt) / 0.3)).toFixed(3);
  } else { endEl.style.opacity = 0; $('logo').style.opacity = 1; }

  drawCaption(ev, t, inCd && t >= cd[0]);
  drawSting(t);
  renderer.render(scene, camera);
  return idx;
};
window.ready = true;
