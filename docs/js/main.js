/* Foldy website. No dependencies.
 * The demo fan below is a browser port of src/foldy/fan.py (same arc, springs, push-apart magnification,
 * taskbar clearance and kinetic scrolling), so what you see here is how the real app behaves. */
(() => {
"use strict";

/* ====================================================================== config */
const REPO = "vinchezko/Foldy";                       // <- change this if your repository has another name
const REPO_URL = `https://github.com/${REPO}`;
const DOWNLOAD_URL = `${REPO_URL}/releases/latest/download/Foldy.exe`;


const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const smooth = t => t * t * (3 - 2 * t);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

$$("[data-download]").forEach(a => (a.href = DOWNLOAD_URL));
$$("[data-repo]").forEach(a => (a.href = REPO_URL));
$$("[data-releases]").forEach(a => (a.href = `${REPO_URL}/releases`));
$$("[data-owner]").forEach(a => (a.href = `https://github.com/${REPO.split("/")[0]}`));
$$(".pin").forEach(p => p.style.setProperty("--h", p.dataset.hue));

/* ====================================================================== reveal, nav, parallax */
const io = "IntersectionObserver" in window
  ? new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .12 })
  : null;
$$(".reveal").forEach(el => (io ? io.observe(el) : el.classList.add("in")));

const nav = $("#nav");
const px = $$("[data-speed]");
let ticking = false;
function onScroll() {
  nav.classList.toggle("solid", scrollY > 30);
  if (reduced) return;
  const vh = innerHeight;
  for (const el of px) {
    const r = el.parentElement.getBoundingClientRect();
    if (r.bottom < -300 || r.top > vh + 300) continue;
    const base = Math.min(vh, r.top + scrollY);                      // 0 offset at load (hero) / when the section scrolls into view
    el.style.transform = `translate3d(0,${((base - r.top) * parseFloat(el.dataset.speed)).toFixed(1)}px,0)`;
  }
}
addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; onScroll(); }); } }, { passive: true });
onScroll();

/* ====================================================================== folder contents for the demo */
const STACKS = {
  Downloads: [["Invoice-0924.pdf","pdf"],["Holiday-photos.zip","zip"],["IMG_2041.jpg","img"],["Meeting notes.docx","doc"],["setup.exe","code"],["Podcast ep. 12.mp3","audio"],
    ["Screen recording.mp4","video"],["Resume-2026.pdf","pdf"],["Wallpaper.png","img"],["backup.zip","zip"],["report-final.docx","doc"],["Thesis draft.pdf","pdf"],["Track 07.mp3","audio"],
    ["Receipt.pdf","pdf"],["Logo.png","img"],["data.csv","doc"],["tutorial.mp4","video"],["Fonts.zip","zip"],["main.py","code"],["Tickets.pdf","pdf"],["Cover.jpg","img"],["notes.txt","doc"],
    ["Lecture 3.mp4","video"],["archive-2025.zip","zip"],["Contract.pdf","pdf"],["Sketch.png","img"],["app.js","code"],["Playlist.mp3","audio"],["Budget.xlsx","doc"],["Poster.jpg","img"]],
  Projects: [["foldy","folder"],["website","folder"],["notes.md","doc"],["main.py","code"],["design.png","img"],["todo.txt","doc"],["build.bat","code"],["demo.mp4","video"],["assets","folder"],["README.md","doc"],["icon.ico","img"],["release.zip","zip"]],
  Photos: [["Summer 2025","folder"],["IMG_1001.jpg","img"],["IMG_1002.jpg","img"],["IMG_1003.jpg","img"],["Portrait.png","img"],["Sunset.jpg","img"],["Beach.jpg","img"],["Mountains.jpg","img"],["City night.jpg","img"],
    ["Family.jpg","img"],["Cat.jpg","img"],["Birthday.jpg","img"],["Panorama.jpg","img"],["Food.jpg","img"],["Road trip.mp4","video"],["Concert.jpg","img"],["Garden.png","img"],["Old scan.png","img"],["Sketchbook.zip","zip"],["Wallpapers","folder"],["Edit-07.jpg","img"],["Snow.jpg","img"]],
};
const DEF = { density: 1, speed: 1, glass: .9, magnify: .45, curve: .75, maxvis: 14, labels: true, natural: false, sort: 0 };

/* ====================================================================== the fan (port of fan.py) */
class Fan {
  constructor(stage, taskbar, cfg) {
    this.stage = stage; this.tb = taskbar; this.cfg = cfg;
    this.layer = document.createElement("div"); this.layer.className = "fan-layer"; stage.appendChild(this.layer);
    this.toastEl = $(".toast", stage);
    this.state = "closed"; this.btn = null; this.name = null;
    this.mouse = null; this.hov = null; this.ghost = false; this.raf = 0; this.last = 0;
    this.els = []; this.header = null; this.lift = 0; this.focus = 0;
    this.scroll = this.sv = this.target = this.maxscroll = 0; this.tWheel = 0;
    this.onUser = null;
    stage.addEventListener("pointermove", e => {
      const r = stage.getBoundingClientRect();
      this.mouse = { x: e.clientX - r.left, y: e.clientY - r.top };
      this.ghost = false;
      if (this.onUser) this.onUser();
      if (this.state !== "closed") this.kick();
    });
    stage.addEventListener("pointerleave", () => { if (!this.ghost) { this.mouse = null; this.hov = null; if (this.state !== "closed") this.kick(); } });
    stage.addEventListener("wheel", e => this.onWheel(e), { passive: false });
  }

  toast(text) {
    const t = this.toastEl; if (!t) return;
    t.textContent = text; t.classList.add("show");
    clearTimeout(this._tt); this._tt = setTimeout(() => t.classList.remove("show"), 1700);
  }

  kick() { if (!this.raf) { this.last = performance.now() / 1000; this.raf = requestAnimationFrame(ms => this.tick(ms)); } }

  open(btn) {
    const name = btn.dataset.stack;
    if (this.state !== "closed") {
      if (this.name === name && this.state === "open") {
        if (this.byGhost) { this.byGhost = false; return; }       // you grabbed the demo the tour had opened: keep it open
        return this.close();
      }
      this.hardClose();
    }
    const c = this.cfg;
    const s = this.stage.getBoundingClientRect(), b = btn.getBoundingClientRect(), t = this.tb.getBoundingClientRect();
    this.btn = btn; this.name = name; this.byGhost = false;
    this.isz = Math.round(40 * c.density); this.sp = Math.round(52 * c.density);
    this.W = s.width; this.H = s.height;
    this.tbY = t.top - s.top;                                        // taskbar top edge
    this.ox = b.left + b.width / 2 - s.left; this.oy = b.top + b.height / 2 - s.top;   // the clicked button's centre
    this.start = (this.oy - this.tbY) + this.isz / 2 + 10;           // first icon sits just clear of the taskbar
    this.cap = clamp(Math.floor((this.oy - this.start - 56) / this.sp), 1, Math.round(c.maxvis));
    const reach = this.cap * this.sp + 120;
    this.R = Math.max(2000 - 1500 * c.curve, reach / 1.1);
    const ext = this.R * (1 - Math.cos(reach / this.R));
    this.bend = this.ox + ext + 90 <= this.W ? 1 : (this.ox - ext - 280 >= 0 ? -1 : 1);
    this.labelSide = this.ox < 280 ? 1 : -1;

    let list = STACKS[name].slice();
    if (c.sort === 1) list.sort((a, z) => a[0].localeCompare(z[0]));
    if (c.sort === 2) list.sort((a, z) => (a[1] !== "folder") - (z[1] !== "folder") || a[0].localeCompare(z[0]));
    this.maxscroll = Math.max(0, list.length - this.cap);
    this.scroll = this.sv = this.target = 0; this.lift = 0; this.focus = 0; this.hov = null;

    this.layer.innerHTML = ""; this.layer.style.setProperty("--ga", c.glass);
    this.els = list.map(([nm, ty], i) => {
      const w = document.createElement("div"); w.className = "fi";
      const ic = document.createElement("div"); ic.className = "fic"; ic.innerHTML = `<svg><use href="#i-${ty}"/></svg>`;
      ic.style.width = ic.style.height = this.isz + "px";
      const lb = document.createElement("div"); lb.className = "fl"; lb.textContent = nm;
      w.append(lb, ic); this.layer.appendChild(w);
      const el = { i, w, ic, lb, nm, x: 0, v: 0, target: 0, pending: 1, ts: null, hs: 1, edge: 1, sx: 0, sy: 0, lv: c.labels ? 1 : 0, hf: false };
      for (const n of [ic, lb]) {
        n.addEventListener("click", () => { this.toast(`Opens “${nm}”`); this.close(); });
        n.addEventListener("pointerenter", () => { el.hf = true; this.kick(); });
        n.addEventListener("pointerleave", () => { el.hf = false; this.kick(); });
      }
      return el;
    });
    const hw = document.createElement("div"); hw.className = "fh"; hw.textContent = "Open in Explorer  ↗";
    this.layer.appendChild(hw);
    this.header = { i: -1, w: hw, x: 0, v: 0, target: 0, pending: 1, ts: null, hs: 1, sx: 0, sy: 0 };
    hw.addEventListener("click", () => { this.toast("Opens the folder in Explorer"); this.close(); });
    hw.addEventListener("pointerenter", () => { this.hov = this.header; this.kick(); });
    hw.addEventListener("pointerleave", () => { this.hov = null; this.kick(); });

    const T = performance.now() / 1000, spd = Math.max(c.speed, .1);
    // items unfold one after another, but only the visible arc counts: items beyond it open with the last visible one,
    // and the "Open in Explorer" pill appears almost at once (it used to wait for every item in the folder)
    this.els.forEach((el, rank) => { el.pending = 1; el.ts = T + Math.min(rank, this.cap) * .018 / spd; });
    this.header.pending = 1; this.header.ts = T + .03 / spd;
    this.state = "open"; btn.classList.add("on");
    this.layout(); this.paint(); this.kick();
  }

  close() {
    if (this.state !== "open") return;
    this.state = "closing"; this.btn && this.btn.classList.remove("on");
    const T = performance.now() / 1000, spd = Math.max(this.cfg.speed, .1);
    [this.header, ...[...this.els].reverse()].forEach((el, rank) => { el.pending = 0; el.ts = T + rank * .01 / spd; });
    this.kick();
  }

  hardClose() {
    cancelAnimationFrame(this.raf); this.raf = 0;
    this.layer.innerHTML = ""; this.els = []; this.header = null; this.state = "closed";
    this.btn && this.btn.classList.remove("on");
  }

  contains(node) { return this.layer.contains(node) || $$(".pin", this.tb).some(p => p.contains(node)); }

  onWheel(e) {
    if (this.state !== "open" || this.maxscroll <= 0 || !this.mouse) return;
    if (this.mouse.y > this.tbY || Math.abs(this.mouse.x - this.ox) > 420) return;     // only over the fan
    e.preventDefault();
    let d = -e.deltaY / 100 * 1.6;                                   // wheel notch ≈ 1.6 items; touchpads are smaller
    if (this.cfg.natural) d = -d;
    if (this.target < 0 || this.target > this.maxscroll) d *= .4;    // rubber-band resistance
    this.target = clamp(this.target + d, -1.2, this.maxscroll + 1.2);
    this.tWheel = performance.now() / 1000; this.kick();
  }

  arc(s) { const th = s / this.R; return { x: this.ox + this.bend * this.R * (1 - Math.cos(th)), y: this.oy - this.start - this.R * Math.sin(th) }; }

  fade(u) {                                                          // same profile as the app
    const sp = this.sp, ut = (this.cap - 1) * sp - u;
    const kb = clamp(this.scroll, 0, 1), kt = clamp(this.maxscroll - this.scroll, 0, 1);
    const ab = smooth(clamp((u + .6 * sp) / (.6 * sp), 0, 1)) * (1 - kb * .55 * (1 - smooth(clamp(u / (1.4 * sp), 0, 1))));
    const at = smooth(clamp((ut + .6 * sp) / (.6 * sp), 0, 1)) * (1 - kt * .55 * (1 - smooth(clamp(ut / (1.4 * sp), 0, 1))));
    return ab * at;
  }

  layout() {
    const sp = this.sp, isz = this.isz, els = this.els, n = els.length;
    if (!n) return;
    const ex = new Array(n); let extra = 0;                          // magnified items take room and push neighbours apart
    for (let k = 0; k < n; k++) { if (k) extra += isz / 2 * ((els[k - 1].hs - 1) + (els[k].hs - 1)); ex[k] = extra; }
    const headExtra = extra + isz / 2 * (els[n - 1].hs - 1);
    let delta = 0;
    if (this.state === "open" && this.mouse) {                       // the item under the cursor stays put
      const f = this.focus, i0 = Math.floor(f), t = f - i0, g = i => ex[clamp(i, 0, n - 1)];
      delta = g(i0) * (1 - t) + g(i0 + 1) * t;
    }
    for (const el of els) {
      const u = (el.i - this.scroll) * sp;
      el.edge = this.fade(u);
      const p = this.arc(u + ex[el.i] - delta); el.sx = p.x; el.sy = p.y;
    }
    const hp = this.arc(Math.min(n, this.cap) * sp + 10 + headExtra - delta); this.header.sx = hp.x; this.header.sy = hp.y;
    const limit = this.tbY - 6; let need = 0;                        // never touch the taskbar, whatever the settings
    for (const el of els) if (el.edge > .25) need = Math.max(need, el.sy + isz * el.hs * (.78 + .22 * el.edge) / 2 - limit);
    this.lift = Math.max(need, this.lift + (need - this.lift) * .35);
    if (this.lift > .01) { for (const el of els) el.sy -= this.lift; this.header.sy -= this.lift; }
  }

  paint() {
    const isz = this.isz;
    for (const el of this.els) {
      const cx = this.ox + el.x * (el.sx - this.ox), cy = this.oy + el.x * (el.sy - this.oy);
      const sc = (.35 + .65 * clamp(el.x, 0, 1.1)) * el.hs * (.78 + .22 * el.edge);
      const opI = clamp(el.x * 2.2, 0, 1) * el.edge, opL = clamp((el.x - .05) * 1.6, 0, 1) * el.edge * el.lv;
      el.w.style.display = opI < .01 && opL < .01 ? "none" : "";
      el.w.style.transform = `translate3d(${cx.toFixed(1)}px,${cy.toFixed(1)}px,0)`;
      el.ic.style.transform = `translate(-50%,-50%) scale(${sc.toFixed(3)})`;
      el.ic.style.opacity = opI.toFixed(3);
      const off = (isz * sc / 2 + 8).toFixed(1);
      el.lb.style.transform = this.labelSide < 0 ? `translate(calc(-100% - ${off}px),-50%)` : `translate(${off}px,-50%)`;
      el.lb.style.opacity = opL.toFixed(3);
    }
    const h = this.header;
    if (h) {
      const cx = this.ox + h.x * (h.sx - this.ox), cy = this.oy + h.x * (h.sy - this.oy), sc = (.35 + .65 * clamp(h.x, 0, 1.1)) * h.hs;
      h.w.style.transform = `translate3d(${cx.toFixed(1)}px,${cy.toFixed(1)}px,0) translate(-50%,-50%) scale(${sc.toFixed(3)})`;
      h.w.style.opacity = clamp((h.x - .05) * 1.6, 0, 1).toFixed(3);
    }
  }

  tick(ms) {                                                         // damped springs, dt-based: smooth at any frame rate
    this.raf = 0;
    if (!this.header) return;
    const T = ms / 1000; let dt = Math.min(T - this.last, .05); this.last = T; if (dt <= 0) dt = .016;
    const c = this.cfg, dts = dt * c.speed; let busy = false;

    if (this.maxscroll > 0 || this.scroll !== 0) {                   // kinetic scrolling with rubber-band, settles on a slot
      const idle = T - this.tWheel;
      if (idle > .35) this.target = Math.round(clamp(this.target, 0, this.maxscroll));
      else if (idle > .12) this.target = clamp(this.target, 0, this.maxscroll);
      const n = Math.floor(dt / .004) + 1, h = dt / n;
      for (let k = 0; k < n; k++) { this.sv += (140 * (this.target - this.scroll) - 20 * this.sv) * h; this.scroll += this.sv * h; }
      if (Math.abs(this.target - this.scroll) > .002 || Math.abs(this.sv) > .01) busy = true; else { this.scroll = this.target; this.sv = 0; }
    }

    let amp = 0, f = this.focus;                                     // fisheye: gaussian magnification around the pointer
    if (this.state === "open" && this.mouse) {
      const sm = this.R * Math.asin(clamp((this.oy - this.start - this.mouse.y) / this.R, -1, 1));
      f = this.focus = this.scroll + sm / this.sp;
      const xm = this.ox + this.bend * this.R * (1 - Math.cos(sm / this.R));
      amp = c.magnify * Math.exp(-(((this.mouse.x - xm) / 320) ** 2));
    }
    for (const el of [...this.els, this.header]) {
      if (el.ts !== null) { if (T >= el.ts) { el.target = el.pending; el.ts = null; } else busy = true; }
      const damp = el.target > .5 ? 22 : 32, n = Math.floor(dts / .004) + 1, h = dts / n;
      for (let k = 0; k < n; k++) { el.v += (300 * (el.target - el.x) - damp * el.v) * h; el.x += el.v * h; }
      if (Math.abs(el.target - el.x) > .002 || Math.abs(el.v) > .02) busy = true; else { el.x = el.target; el.v = 0; }
      let t = 1;
      if (el === this.header) t = this.hov === el ? 1.06 : 1;
      else {
        t = 1 + amp * Math.exp(-(((el.i - f) * this.sp / (1.5 * this.sp)) ** 2)) * el.edge;
        const lt = c.labels || el.hf ? 1 : 0; el.lv += (lt - el.lv) * (1 - Math.exp(-dt * 14));
        if (Math.abs(lt - el.lv) > .01) busy = true;
      }
      el.hs += (t - el.hs) * (1 - Math.exp(-dt * 16)); if (Math.abs(t - el.hs) > .003) busy = true;
    }
    this.layout(); this.paint();
    if (busy || (this.state === "open" && this.mouse)) this.raf = requestAnimationFrame(m => this.tick(m));
    else if (this.state === "closing") this.hardClose();
  }
}

/* ====================================================================== wiring: hero demo */
const fans = [];
function makeFan(stageSel, tbSel, cfg) {
  const stage = $(stageSel), tb = $(tbSel);
  if (!stage || !tb) return null;
  const fan = new Fan(stage, tb, cfg); fans.push(fan);
  $$(".pin", tb).forEach(b => b.addEventListener("click", () => fan.open(b)));
  return fan;
}
document.addEventListener("pointerdown", e => fans.forEach(f => { if (f.state === "open" && !f.contains(e.target)) f.close(); }));
document.addEventListener("keydown", e => { if (e.key === "Escape") fans.forEach(f => f.close()); });
let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => fans.forEach(f => f.state !== "closed" && f.hardClose()), 150); });

const heroFan = makeFan("#stage-hero", "#tb-hero", { ...DEF, density: 1.12 });

/* self-playing tour of the hero demo; stops the instant you touch it, resumes after 9 s of quiet */
function startTour(fan) {
  if (!fan || reduced) return;
  const stage = fan.stage, buttons = $$(".pin", fan.tb);
  const ghost = document.createElement("div"); ghost.className = "ghost";
  ghost.innerHTML = '<svg viewBox="0 0 22 22" width="22" height="22"><path d="M3 2l14 8.2-6.4 1.6 3.8 6.4-2.8 1.6-3.8-6.4L3 17z" fill="#fff" stroke="#111" stroke-width="1.2" stroke-linejoin="round"/></svg>';
  stage.appendChild(ghost);
  let userAt = -1e9, visible = true, pos = { x: 0, y: 0 };
  fan.onUser = () => { userAt = performance.now(); ghost.classList.remove("on"); };
  stage.addEventListener("pointerdown", fan.onUser);
  new IntersectionObserver(es => (visible = es[0].isIntersecting)).observe(stage);
  const quiet = () => performance.now() - userAt > 9000;
  const place = p => { pos = p; ghost.style.transform = `translate(${p.x}px,${p.y}px)`; };
  const move = (to, ms) => new Promise(res => {
    const from = { ...pos }, t0 = performance.now(); fan.ghost = true; ghost.classList.add("on");
    const step = now => {
      if (!fan.ghost) return res(false);
      const k = clamp((now - t0) / ms, 0, 1), e = k < .5 ? 2 * k * k : 1 - ((-2 * k + 2) ** 2) / 2;
      place({ x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e });
      fan.mouse = { x: pos.x + 3, y: pos.y + 3 }; fan.kick();
      k < 1 ? requestAnimationFrame(step) : res(true);
    };
    requestAnimationFrame(step);
  });
  (async function loop() {
    await sleep(2200);
    const order = ["Downloads", "Projects", "Photos"]; let n = 0;
    for (;;) {
      if (!visible || !quiet() || fan.state !== "closed") { await sleep(900); continue; }
      const btn = buttons.find(b => b.dataset.stack === order[n++ % 3]);
      const s = stage.getBoundingClientRect(), b = btn.getBoundingClientRect();
      const bx = b.left - s.left + b.width / 2, by = b.top - s.top + b.height / 2;
      fan.ghost = true; ghost.classList.add("on"); place({ x: bx + 120, y: by + 30 });
      if (!(await move({ x: bx + 6, y: by + 4 }, 800))) continue;
      fan.open(btn); fan.byGhost = true; await sleep(950);
      for (const idx of [1, 4, 7, 3]) {
        if (!fan.ghost) break;
        const el = fan.els[Math.min(idx, fan.cap - 1)]; if (!el) continue;
        if (!(await move({ x: el.sx - 4, y: el.sy - 4 }, 700))) break;
        await sleep(380);
      }
      if (fan.ghost && fan.maxscroll > 0) {                          // show the kinetic scrolling too
        fan.target = Math.min(fan.maxscroll, fan.target + 6); fan.tWheel = performance.now() / 1000; fan.kick(); await sleep(1500);
        fan.target = 0; fan.tWheel = performance.now() / 1000; fan.kick(); await sleep(1200);
      }
      if (fan.ghost && fan.state === "open") fan.close();
      fan.ghost = false; ghost.classList.remove("on"); await sleep(1700);
    }
  })();
}
startTour(heroFan);

/* ====================================================================== wiring: "Try it" with the settings replica */
const tryCfg = { ...DEF };
const tryFan = makeFan("#stage-try", "#tb-try", tryCfg);
const SL = [
  ["density", "Density", 70, 140, 100, v => v + "%"], ["speed", "Animation speed", 50, 200, 100, v => (v / 100).toFixed(1) + "×"],
  ["glass", "Glass opacity", 25, 100, 100, v => v + "%"], ["magnify", "Magnification", 0, 80, 100, v => v + "%"],
  ["curve", "Arc curve", 0, 100, 100, v => v + "%"], ["maxvis", "Max items", 6, 20, 1, v => v],
];
const rows = {};
let rebuildT;
const rebuild = () => { clearTimeout(rebuildT); rebuildT = setTimeout(() => { if (tryFan && tryFan.state === "open") { const b = tryFan.btn; tryFan.hardClose(); tryFan.open(b); } }, 140); };
function syncRow(key) {
  const r = rows[key], v = Math.round(tryCfg[key] * r.scale);
  r.input.value = v; r.val.textContent = r.fmt(v); r.rst.disabled = v === Math.round(DEF[key] * r.scale);
}
const slWrap = $("#sliders");
if (slWrap) {
  for (const [key, label, lo, hi, scale, fmt] of SL) {
    const row = document.createElement("div"); row.className = "srow";
    row.innerHTML = `<span>${label}</span><input type="range" min="${lo}" max="${hi}"><span class="v"></span><button title="Reset to default">↺</button>`;
    slWrap.appendChild(row);
    rows[key] = { input: $("input", row), val: $(".v", row), rst: $("button", row), scale, fmt };
    rows[key].input.addEventListener("input", () => {
      tryCfg[key] = +rows[key].input.value / scale; syncRow(key);
      if (key === "glass" && tryFan.layer) tryFan.layer.style.setProperty("--ga", tryCfg.glass); else if (["density", "curve", "maxvis"].includes(key)) rebuild();
    });
    rows[key].rst.addEventListener("click", () => { tryCfg[key] = DEF[key]; syncRow(key); if (key === "glass") tryFan.layer.style.setProperty("--ga", tryCfg.glass); else if (["density", "curve", "maxvis"].includes(key)) rebuild(); });
    syncRow(key);
  }
  $("#o-sort").addEventListener("change", e => { tryCfg.sort = e.target.selectedIndex; rebuild(); });
  $("#o-labels").addEventListener("change", e => { tryCfg.labels = e.target.checked; tryFan.kick(); });
  $("#o-nat").addEventListener("change", e => { tryCfg.natural = e.target.checked; });
  $("#b-preview").addEventListener("click", () => { const b = $$(".pin", tryFan.tb)[0]; tryFan.state === "open" ? tryFan.close() : tryFan.open(b); });
  $("#b-add").addEventListener("click", () => tryFan.toast("In the app this opens the Windows folder picker"));
  $("#b-reset").addEventListener("click", () => {
    Object.assign(tryCfg, DEF); SL.forEach(([k]) => syncRow(k));
    $("#o-sort").selectedIndex = 0; $("#o-labels").checked = true; $("#o-nat").checked = false;
    tryFan.layer.style.setProperty("--ga", tryCfg.glass); rebuild();
  });
  $("#b-uninstall").addEventListener("click", () => { $("#install").scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); setTimeout(() => $("#hold").focus({ preventScroll: true }), 700); });
}

/* ====================================================================== how it works */
const how = $("#how-visual"), steps = $$(".step");
if (how && "IntersectionObserver" in window) {
  const so = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { how.dataset.active = e.target.dataset.n; steps.forEach(s => s.classList.toggle("on", s === e.target)); }
  }), { rootMargin: "-42% 0px -42% 0px" });
  steps.forEach(s => so.observe(s));
}
if (steps[0]) steps[0].classList.add("on");

/* ====================================================================== install + uninstall mocks */
function runChecklist(list, bar, weights, { onProgress, onStep } = {}) {
  return (async () => {
    const items = $$("li", list); items.forEach(li => (li.className = "")); bar.style.width = "0%";
    const total = weights.reduce((a, b) => a + b, 0); let done = 0;
    for (let i = 0; i < items.length; i++) {
      items[i].className = "run"; onStep && onStep(i);
      const steps = 8;
      for (let k = 1; k <= steps; k++) {
        await sleep(60 + weights[i] * 22); const p = (done + weights[i] * k / steps) / total;
        bar.style.width = (p * 100).toFixed(1) + "%"; onProgress && onProgress(p, i, k / steps);
      }
      items[i].className = "ok"; done += weights[i];
    }
  })();
}
const instPanel = $("#inst-panel");
if (instPanel) {
  let seen = false, running = false;
  const run = async () => {
    if (running) return; running = true;
    $("#inst-title").textContent = "Installing Foldy"; $("#inst-sub").textContent = "Getting ready…";
    await runChecklist($("#inst-steps"), $("#inst-bar"), [1, 6, 2, 1, 1, 1, 1], {
      onStep: i => ($("#inst-sub").textContent = $$("#inst-steps li")[i].textContent + "…"),
      onProgress: (p, i, k) => { $("#inst-pct").textContent = Math.round(p * 100) + "%"; $("#inst-detail").textContent = i === 1 ? `Copying… ${(k * 31).toFixed(1)} / 31.0 MB` : ""; },
    });
    $("#inst-title").textContent = "Foldy is installed"; $("#inst-sub").textContent = "Starting Foldy…"; $("#inst-pct").textContent = "100%"; $("#inst-detail").textContent = "";
    await sleep(3200); running = false; if (seen) run();
  };
  new IntersectionObserver(es => { seen = es[0].isIntersecting; if (seen) run(); }, { threshold: .35 }).observe(instPanel);
}

const hold = $("#hold");
if (hold) {
  const ring = $("#ring"), face = $("#hold-face"), icon = $("#trash-svg"), label = $("#hold-label"), CIRC = 326.7;
  let p = 0, holding = false, done = false, last = 0, raf = 0;
  const mixc = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",");
  const draw = () => {
    ring.style.strokeDashoffset = (CIRC * (1 - p)).toFixed(1);
    ring.style.stroke = `rgb(${mixc([255, 176, 92], [255, 72, 92], p)})`;
    face.style.fill = `rgb(${mixc([44, 46, 54], [96, 34, 46], p)})`;
    icon.style.color = `rgb(${mixc([235, 238, 245], [255, 150, 160], p)})`;
    icon.style.transform = `rotate(${(-8 * p).toFixed(1)}deg)`; icon.style.transformOrigin = "20px 20px";
    label.textContent = done ? "Uninstalling…" : p > .02 ? "Keep holding…" : "Hold to uninstall";
  };
  const tick = now => {
    const dt = Math.min((now - last) / 1000, .05); last = now;
    if (!done) p = clamp(p + (holding ? dt / 1.5 : -dt / .45), 0, 1);
    draw();
    if (p >= 1 && !done) { done = true; holding = false; setTimeout(runUninstall, 450); }
    raf = (holding || (p > 0 && !done)) ? requestAnimationFrame(tick) : 0;
  };
  const begin = () => { if (done) return; holding = true; last = performance.now(); if (!raf) raf = requestAnimationFrame(tick); };
  const end = () => { holding = false; last = performance.now(); if (!raf && p > 0) raf = requestAnimationFrame(tick); };
  hold.addEventListener("pointerdown", e => { hold.setPointerCapture && hold.setPointerCapture(e.pointerId); begin(); });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach(ev => hold.addEventListener(ev, end));
  hold.addEventListener("keydown", e => { if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); begin(); } });
  hold.addEventListener("keyup", e => { if (e.key === " " || e.key === "Enter") end(); });

  async function runUninstall() {
    $("#un-stage").hidden = true; $("#un-run").hidden = false;
    $("#un-title").textContent = "Uninstalling Foldy"; $("#un-sub").textContent = "Removing…";
    await runChecklist($("#un-steps"), $("#un-bar"), [1, 3, 2, 1, 1, 3, 1], { onStep: i => ($("#un-sub").textContent = $$("#un-steps li")[i].textContent + "…") });
    $("#un-title").textContent = "Foldy has been uninstalled"; $("#un-sub").textContent = "Everything was removed. (Demo only: nothing on your PC changed.)";
    await sleep(5200);
    $("#un-run").hidden = true; $("#un-stage").hidden = false; p = 0; done = false; holding = false; draw();
  }
  draw();
}

})();
