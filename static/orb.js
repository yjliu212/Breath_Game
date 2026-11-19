/* Optional breathing-orb styles for the practice page (templates/Breath_Game.html).
 *
 * Clicking / tapping the circle, or Enter / Space while it has focus, switches to the
 * next style in an endless loop: plain → taiji → mist → aura → particles → lotus → plain.
 * The choice is remembered in localStorage under "breath.orb".
 *
 * The page's own practice engine keeps full control of the breath: it scales #circle
 * with setScale() exactly as before, and every style is drawn inside #circle, so it
 * follows that scale. The engine reports each frame through BreathOrb.breath(phase,
 * fraction, scale); the styles only read this to drive their inner motion. Nothing here
 * starts, stops or changes practice.
 *
 * "plain" is the original CSS circle and needs no animation loop. The other styles draw
 * into a 240px layer centred on the 160px circle (absolutely positioned, so the layout
 * never moves). Everything a style paints, glows included, stays within EDGE (86) units of
 * the centre: the circle's own radius (80) plus ~6 units, which is ~8px at the largest
 * scale (1.3). The CSS also clips the layer to that circle as a backstop, so nothing ever
 * reaches the buttons above or the phase text below. The layer never takes clicks
 * (pointer-events: none), so they always land on #circle itself. Only the active style's loop runs, and it pauses while the tab is hidden.
 * Ported from the standalone orb previews A–E.
 */
(function () {
  "use strict";

  var KEY = "breath.orb";
  var STYLES = ["plain", "taiji", "mist", "aura", "particles", "lotus"];
  var SMALL = 0.6, BIG = 1.3, IDLE_SCALE = 1;   // must match the engine in Breath_Game.html
  var BOX = 240;                                 // layer size in px (and SVG / canvas units)
  var R = 80, EDGE = 86;                         // circle radius; outer limit of anything drawn

  var noop = function () {};
  var circle = document.getElementById("circle");
  if (!circle) { window.BreathOrb = { breath: noop }; return; }

  // ---------- breath state (written only by the practice engine) ----------
  var B = { phase: "idle", p: 0, scale: IDLE_SCALE };
  // 0 after the exhale (0.6x) .. 1 after the inhale (1.3x); about 0.57 at rest (1x).
  function level() {
    var v = (B.scale - SMALL) / (BIG - SMALL);
    return v < 0 ? 0 : v > 1 ? 1 : v;
  }
  function running() { return B.phase !== "idle"; }

  var mq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  var RM = !!(mq && mq.matches);

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function smooth(x) { x = clamp01(x); return x * x * (3 - 2 * x); }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // SVG is built from markup (the HTML parser puts it in the SVG namespace).
  function svgLayer(layer, inner, extra) {
    layer.innerHTML = '<svg viewBox="-120 -120 240 240" aria-hidden="true" focusable="false"' +
      (extra || "") + ">" + inner + "</svg>";
    return function (id) { return layer.querySelector('[data-k="' + id + '"]'); };
  }
  // Filters use a fixed user-space region (the allowed disc's bounding square) instead of a
  // bbox-relative one; a blur only paints where its input is, so no box ever shows.
  var FREGION = ' filterUnits="userSpaceOnUse" x="-' + EDGE + '" y="-' + EDGE +
    '" width="' + 2 * EDGE + '" height="' + 2 * EDGE + '"';
  function f(x, d) { return x.toFixed(d === undefined ? 3 : d); }

  // ---------- A · Taiji: slowly turning yin-yang, bagua ring glows on inhale ----------
  var taiji = {
    idle: true,
    build: function (layer) {
      var TRIGRAMS = [[1, 1, 1], [0, 1, 1], [0, 1, 0], [0, 0, 1], [0, 0, 0], [1, 0, 0], [1, 0, 1], [1, 1, 0]];
      var ring = "";
      TRIGRAMS.forEach(function (lines, k) {
        ring += '<g transform="rotate(' + k * 45 + ')">';
        lines.forEach(function (solid, i) {
          var y = -(58 + i * 5);      // outermost line ends ~70 from the centre, inside the circle
          (solid ? [[-8, 8]] : [[-8, -2], [2, 8]]).forEach(function (s) {
            ring += '<line x1="' + s[0] + '" x2="' + s[1] + '" y1="' + y + '" y2="' + y + '"/>';
          });
        });
        ring += "</g>";
      });
      var $ = svgLayer(layer,
        '<defs>' +
        '<radialGradient id="orb-a-halo"><stop offset="0" stop-color="#5fae8c" stop-opacity=".32"/>' +
        '<stop offset=".55" stop-color="#2f6f58" stop-opacity=".12"/><stop offset="1" stop-color="#0f172a" stop-opacity="0"/></radialGradient>' +
        '<radialGradient id="orb-a-yang" cx=".4" cy=".35" r=".8"><stop offset="0" stop-color="#93c9ad"/><stop offset="1" stop-color="#4f8f75"/></radialGradient>' +
        '<radialGradient id="orb-a-yin" cx=".6" cy=".65" r=".8"><stop offset="0" stop-color="#2b3c5f"/><stop offset="1" stop-color="#18233d"/></radialGradient>' +
        '<filter id="orb-a-glow"' + FREGION + '><feGaussianBlur stdDeviation="2"/></filter>' +
        '</defs>' +
        '<circle data-k="halo" r="' + EDGE + '" fill="url(#orb-a-halo)"/>' +
        '<g data-k="disc">' +
        '<circle r="50" fill="url(#orb-a-yin)"/>' +
        '<path d="M0,-50 A50,50 0 0 1 0,50 A25,25 0 0 1 0,0 A25,25 0 0 0 0,-50Z" fill="url(#orb-a-yang)"/>' +
        '<circle cy="25" r="6.5" fill="#1d2a47"/><circle cy="-25" r="6.5" fill="#86bfa2"/>' +
        '<circle r="50" fill="none" stroke="#e8d9a8" stroke-opacity=".35" stroke-width=".8"/>' +
        '</g>' +
        '<circle r="54"fill="none" stroke="#e8d9a8" stroke-opacity=".18" stroke-width=".6"/>' +
        '<g data-k="ringGlow" filter="url(#orb-a-glow)" opacity="0" stroke="#e8d9a8" stroke-width="2.4" stroke-linecap="round">' + ring + '</g>' +
        '<g data-k="ring" opacity=".5" stroke="#e8d9a8" stroke-width="2.4" stroke-linecap="round">' + ring + '</g>');
      this.halo = $("halo"); this.disc = $("disc"); this.ring = $("ring"); this.ringGlow = $("ringGlow");
      this.angle = 0;
    },
    render: function (lv, dt) {
      // One turn per 60 s while practising, half that speed at rest.
      if (!RM) this.angle = (this.angle + dt * (running() ? 6 : 3)) % 360;
      this.disc.setAttribute("transform", "rotate(" + f(this.angle) + ")");
      this.ring.setAttribute("opacity", f(0.45 + 0.35 * lv));
      this.ringGlow.setAttribute("opacity", f(0.85 * lv));
      this.halo.setAttribute("transform", "scale(" + f(0.8 + 0.2 * lv, 4) + ")");
      this.halo.setAttribute("opacity", f(0.45 + 0.55 * lv));
    }
  };

  // ---------- B · Mist: value-noise smoke swirl on a small canvas ----------
  // Lighter than the preview: a 96px canvas (vs 128) and pixels recomputed every other frame.
  var mist = {
    idle: true,
    build: function (layer) {
      var N = this.N = 96;
      layer.innerHTML = '<div class="orb-mist-glow"></div><div class="orb-mist-ball"><canvas width="' + N + '" height="' + N + '"></canvas></div>';
      this.glow = layer.firstChild;
      var cv = layer.querySelector("canvas");
      this.ctx = cv.getContext("2d");
      if (!this.ctx) return;
      this.img = this.ctx.createImageData(N, N);
      var rnd = mulberry32(20261119), i, j;
      var VAL = this.VAL = new Float32Array(256), P = this.P = new Uint8Array(512);
      for (i = 0; i < 256; i++) { VAL[i] = rnd(); P[i] = i; }
      for (i = 255; i > 0; i--) { j = Math.floor(rnd() * (i + 1)); var tmp = P[i]; P[i] = P[j]; P[j] = tmp; }
      for (i = 0; i < 256; i++) P[i + 256] = P[i];
      var R = this.R = new Float32Array(N * N), A = this.A = new Float32Array(N * N), M = this.M = new Uint8Array(N * N);
      for (j = 0; j < N; j++) for (i = 0; i < N; i++) {
        var x = (i + 0.5) / N * 2 - 1, y = (j + 0.5) / N * 2 - 1, k = j * N + i, r = Math.sqrt(x * x + y * y);
        R[k] = r; A[k] = Math.atan2(y, x);
        M[k] = Math.round(255 * clamp01((1 - r) / 0.06));   // soft edge
      }
      // colour ramp: deep navy -> forest -> green -> pale mint, precomputed
      var STOPS = [[0, 11, 26, 46], [0.42, 20, 83, 45], [0.72, 34, 197, 94], [1, 209, 250, 229]];
      var RAMP = this.RAMP = new Float32Array(256 * 3);
      for (var q = 0; q < 256; q++) {
        var v = q / 255;
        for (var s = 1; s < STOPS.length; s++) {
          if (v <= STOPS[s][0] || s === STOPS.length - 1) {
            var a = STOPS[s - 1], b = STOPS[s], t = clamp01((v - a[0]) / (b[0] - a[0]));
            RAMP[q * 3] = a[1] + (b[1] - a[1]) * t; RAMP[q * 3 + 1] = a[2] + (b[2] - a[2]) * t; RAMP[q * 3 + 2] = a[3] + (b[3] - a[3]) * t;
            break;
          }
        }
      }
      this.LUT = new Uint8ClampedArray(256 * 3);
      this.phi = 0; this.odd = false;
    },
    vnoise: function (x, y) {
      var VAL = this.VAL, P = this.P;
      var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
      var X = xi & 255, Y = yi & 255;
      var u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
      var a = VAL[P[P[X] + Y]], b = VAL[P[P[X + 1] + Y]];
      var c = VAL[P[P[X] + Y + 1]], d = VAL[P[P[X + 1] + Y + 1]];
      var top = a + (b - a) * u, bot = c + (d - c) * u;
      return top + (bot - top) * v;
    },
    render: function (lv, dt, force) {
      this.glow.style.opacity = f(0.35 + 0.65 * lv);
      this.glow.style.transform = "scale(" + f(0.9 + 0.1 * lv, 4) + ")";
      if (!this.ctx) return;
      // swirl speed follows the breath; half speed at rest
      if (!RM) this.phi += dt * (0.3 + 0.9 * lv) * (running() ? 1 : 0.5);
      this.odd = !this.odd;
      if (!force && this.odd) return;
      var N = this.N, R = this.R, A = this.A, M = this.M, LUT = this.LUT, RAMP = this.RAMP, data = this.img.data;
      var bright = RM ? 0.75 + 0.2 * lv : 0.6 + 0.5 * lv;
      var lift = RM ? 0 : Math.round(0.12 * lv * 255);       // pushes values toward the bright end on inhale
      for (var q = 0; q < 256; q++) {
        var src = Math.min(255, q + lift) * 3;
        LUT[q * 3] = RAMP[src] * bright; LUT[q * 3 + 1] = RAMP[src + 1] * bright; LUT[q * 3 + 2] = RAMP[src + 2] * bright;
      }
      var phi = this.phi, rot = phi * 0.22, d1x = phi * 0.28, d1y = -phi * 0.17, d2x = -phi * 0.45, d2y = phi * 0.36;
      for (var k = 0, o = 0; k < N * N; k++, o += 4) {
        if (M[k] === 0) { data[o + 3] = 0; continue; }
        var r = R[k], ang = A[k] + rot + 1.8 * (1 - r);
        var x = r * Math.cos(ang), y = r * Math.sin(ang);
        var n1 = this.vnoise(x * 2.1 + d1x + 10, y * 2.1 + d1y + 10);
        var n2 = this.vnoise(x * 4.3 + d2x + n1 * 1.6 + 40, y * 4.3 + d2y + n1 * 1.6 + 40);
        var v = (0.62 * n1 + 0.38 * n2 - 0.22) * 1.75 * (1 - 0.35 * r * r);
        var idx = (v <= 0 ? 0 : v >= 1 ? 255 : (v * 255) | 0) * 3;
        data[o] = LUT[idx]; data[o + 1] = LUT[idx + 1]; data[o + 2] = LUT[idx + 2]; data[o + 3] = M[k];
      }
      this.ctx.putImageData(this.img, 0, 0);
    }
  };

  // ---------- C · Aura: breathing halo, one ripple as each exhale begins ----------
  var aura = {
    idle: false,            // static at rest
    build: function (layer) {
      var $ = svgLayer(layer,
        '<defs>' +
        '<radialGradient id="orb-c-halo"><stop offset="0" stop-color="#4ade80" stop-opacity=".55"/>' +
        '<stop offset=".9" stop-color="#22c55e" stop-opacity=".35"/>' +
        '<stop offset="1" stop-color="#22c55e" stop-opacity="0"/></radialGradient>' +
        '<radialGradient id="orb-c-orb" cx=".42" cy=".38" r=".7"><stop offset="0" stop-color="#6ee7a0"/>' +
        '<stop offset=".5" stop-color="#22c55e"/><stop offset="1" stop-color="#14532d"/></radialGradient>' +
        '<radialGradient id="orb-c-shine" cx=".36" cy=".3" r=".45"><stop offset="0" stop-color="#f0fdf4" stop-opacity=".35"/>' +
        '<stop offset="1" stop-color="#f0fdf4" stop-opacity="0"/></radialGradient>' +
        '<filter id="orb-c-soft"' + FREGION + '><feGaussianBlur stdDeviation=".8"/></filter>' +
        '</defs>' +
        '<circle data-k="halo" r="' + EDGE + '" fill="url(#orb-c-halo)"/>' +
        '<circle data-k="ripple" r="82" fill="none" stroke="#d1fae5" stroke-width="2" opacity="0" filter="url(#orb-c-soft)"/>' +
        '<circle r="80" fill="url(#orb-c-orb)"/>' +
        '<circle r="80" fill="url(#orb-c-shine)"/>' +
        '<circle r="80" fill="none" stroke="#f5e6b8" stroke-opacity=".18" stroke-width=".8"/>');
      this.halo = $("halo"); this.ripple = $("ripple");
      this.age = Infinity;
    },
    exhale: function () { this.age = 0; },
    render: function (lv, dt) {
      // A thin glow band just outside the orb (80..EDGE), brighter on inhale.
      this.halo.setAttribute("opacity", f(0.35 + 0.6 * lv));
      var LIFE = 4;
      if (running()) this.age += dt; else this.age = Infinity;
      if (!RM && this.age < LIFE) {
        var k = this.age / LIFE, out = 1 - (1 - k) * (1 - k);   // ease-out growth
        // Spreads from the orb's edge towards EDGE (scaling with the circle), thinning and
        // fading as it goes; stroke and blur stay inside EDGE.
        this.ripple.setAttribute("r", f(R + 3 * out, 2));
        this.ripple.setAttribute("stroke-width", f(1.6 - 0.8 * k, 2));
        this.ripple.setAttribute("opacity", f(0.6 * Math.min(1, this.age / 0.3) * Math.pow(1 - k, 1.6)));
      } else {
        this.ripple.setAttribute("opacity", "0");
      }
    }
  };

  // ---------- D · Particles: motes gather on inhale, orbit on hold, drift out on exhale ----------
  var particles = {
    idle: true,
    build: function (layer) {
      layer.innerHTML = "<canvas></canvas>";
      this.cv = layer.firstChild;
      this.ctx = this.cv.getContext("2d");
      var rnd = mulberry32(42), P = this.parts = [];
      for (var n = 0; n < 120; n++) {
        P.push({
          th: rnd() * Math.PI * 2,             // starting angle
          w: 0.5 + 0.7 * rnd(),                // angular speed factor
          rin: 0.12 + 0.8 * Math.sqrt(rnd()),  // radius inside the orb, as a fraction of 80
          rout: 80 * (1 + 0.1 * rnd()),        // drift-out radius; faded to nothing before EDGE
          lag: 0.35 * rnd(),                   // some arrive / leave later
          size: 1.3 + 2.4 * rnd() * rnd(),
          a: 0.35 + 0.6 * rnd(),
          gold: rnd() < 0.14,
          wf: 0.4 + 0.8 * rnd(), wp: rnd() * Math.PI * 2
        });
      }
      function sprite(r, g, b) {
        var c = document.createElement("canvas"); c.width = c.height = 32;
        var x = c.getContext("2d");
        if (!x) return c;
        var gr = x.createRadialGradient(16, 16, 0, 16, 16, 16);
        gr.addColorStop(0, "rgba(" + r + "," + g + "," + b + ",1)");
        gr.addColorStop(0.35, "rgba(" + r + "," + g + "," + b + ",.55)");
        gr.addColorStop(1, "rgba(" + r + "," + g + "," + b + ",0)");
        x.fillStyle = gr; x.fillRect(0, 0, 32, 32);
        return c;
      }
      this.MINT = sprite(209, 250, 229); this.GOLD = sprite(245, 230, 184);
      this.spin = 0; this.clock = 0;
    },
    render: function (lv, dt) {
      var ctx = this.ctx;
      if (!ctx) return;
      var px = Math.round(BOX * Math.min(2, window.devicePixelRatio || 1));   // DPR capped at 2
      if (this.cv.width !== px) { this.cv.width = px; this.cv.height = px; }
      ctx.setTransform(px / BOX, 0, 0, px / BOX, px / 2, px / 2);           // 240-unit space, centred
      if (!RM) {
        var slow = running() ? 1 : 0.5;
        this.spin += dt * (0.07 + 0.32 * lv) * slow;
        this.clock += dt * slow;
      }
      var h = BOX / 2, t = this.clock;
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = 1;
      ctx.clearRect(-h, -h, BOX, BOX);
      var halo = ctx.createRadialGradient(0, 0, R * 0.6, 0, 0, EDGE);
      halo.addColorStop(0, "rgba(34,197,94," + f(0.12 + 0.18 * lv) + ")");
      halo.addColorStop(1, "rgba(34,197,94,0)");
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(0, 0, EDGE, 0, Math.PI * 2); ctx.fill();
      var core = ctx.createRadialGradient(-R * 0.2, -R * 0.25, R * 0.05, 0, 0, R);
      core.addColorStop(0, "rgba(74,222,128,.85)");
      core.addColorStop(0.55, "rgba(34,197,94,.55)");
      core.addColorStop(1, "rgba(20,83,45,.35)");
      ctx.fillStyle = core; ctx.beginPath(); ctx.arc(0, 0, R, 0, Math.PI * 2); ctx.fill();

      ctx.globalCompositeOperation = "lighter";
      for (var k = 0; k < this.parts.length; k++) {
        var q = this.parts[k], g, rr, th;
        if (RM) {
          g = 1; rr = q.rin * R * 0.95; th = q.th;
        } else {
          g = smooth((lv - q.lag) / (1 - q.lag));             // 0 = outside, 1 = gathered in the orb
          rr = q.rout + (q.rin * R * 0.95 - q.rout) * g;
          rr += (1.5 + 3.5 * (1 - g)) * Math.sin(t * q.wf + q.wp);
          th = q.th + q.w * this.spin;
        }
        var d = q.size * 4;
        // Fade out as the mote's visible core (about a third of its sprite) nears EDGE.
        var edge = smooth((EDGE - rr - d * 0.18) / 10);
        if (edge <= 0) continue;
        ctx.globalAlpha = q.a * (RM ? 0.3 + 0.7 * lv : 0.22 + 0.78 * g) * edge;
        ctx.drawImage(q.gold ? this.GOLD : this.MINT, rr * Math.cos(th) - d / 2, rr * Math.sin(th) - d / 2, d, d);
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
    }
  };

  // ---------- E · Lotus: 12 translucent petals open on inhale, close on exhale ----------
  var lotus = {
    idle: true,
    build: function (layer) {
      var PETAL = "M0,0 C0.6,-0.28 0.52,-0.76 0,-1 C-0.52,-0.76 -0.6,-0.28 0,0Z";
      function petals(n, fill) {
        var s = "";
        for (var k = 0; k < n; k++) {
          s += '<path d="' + PETAL + '" fill="' + fill + '" stroke="#d1fae5" stroke-opacity=".22" stroke-width=".8" vector-effect="non-scaling-stroke"/>';
        }
        return s;
      }
      var stam = "";
      for (var k = 0; k < 12; k++) stam += '<circle r="1.3" fill="#f5e6b8"/>';
      var $ = svgLayer(layer,
        '<defs>' +
        '<radialGradient id="orb-e-halo"><stop offset="0" stop-color="#22c55e" stop-opacity=".28"/>' +
        '<stop offset=".6" stop-color="#14532d" stop-opacity=".1"/><stop offset="1" stop-color="#0f172a" stop-opacity="0"/></radialGradient>' +
        '<linearGradient id="orb-e-outer" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#14532d" stop-opacity=".6"/>' +
        '<stop offset=".55" stop-color="#22c55e" stop-opacity=".38"/><stop offset="1" stop-color="#bbf7d0" stop-opacity=".55"/></linearGradient>' +
        '<linearGradient id="orb-e-inner" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#22c55e" stop-opacity=".5"/>' +
        '<stop offset=".6" stop-color="#86efac" stop-opacity=".35"/><stop offset="1" stop-color="#ecfdf5" stop-opacity=".6"/></linearGradient>' +
        '<radialGradient id="orb-e-core"><stop offset="0" stop-color="#fffbeb"/>' +
        '<stop offset=".45" stop-color="#fde68a" stop-opacity=".85"/><stop offset="1" stop-color="#facc15" stop-opacity="0"/></radialGradient>' +
        '<radialGradient id="orb-e-coreglow"><stop offset="0" stop-color="#fef3c7" stop-opacity=".55"/>' +
        '<stop offset=".5" stop-color="#bbf7d0" stop-opacity=".18"/><stop offset="1" stop-color="#bbf7d0" stop-opacity="0"/></radialGradient>' +
        '</defs>' +
        '<circle data-k="halo" r="' + EDGE + '" fill="url(#orb-e-halo)"/>' +
        '<g data-k="outer">' + petals(6, "url(#orb-e-outer)") + '</g>' +
        '<g data-k="inner">' + petals(6, "url(#orb-e-inner)") + '</g>' +
        '<circle data-k="coreGlow" r="40" fill="url(#orb-e-coreglow)"/>' +
        '<g data-k="stamens">' + stam + '</g>' +
        '<circle data-k="core" r="12" fill="url(#orb-e-core)"/>');
      this.halo = $("halo"); this.core = $("core"); this.coreGlow = $("coreGlow"); this.stamens = $("stamens");
      this.OUTER = $("outer").children; this.INNER = $("inner").children; this.STAM = this.stamens.children;
      this.rot = 0;
    },
    place: function (list, offset, twist, L, k) {
      for (var j = 0; j < list.length; j++) {
        list[j].setAttribute("transform", "rotate(" + f(j * 60 + offset + this.rot + twist) + ") scale(" + f(L * k) + " " + f(L) + ")");
      }
    },
    render: function (lv, dt) {
      // Openness follows the breath; the circle's own scale adds the size change. Fully
      // open, the outer petal tips reach 81 (82 with the stroke): within EDGE.
      var o = RM ? 0.65 : lv;
      if (!RM) this.rot = (this.rot + dt * (running() ? 3 : 1.5)) % 360;
      var tw = (1 - o) * 28;                       // closed petals curl into a spiral bud
      this.place(this.OUTER, 0, tw, 56 + 25 * o, 0.42 + 0.3 * o);
      this.place(this.INNER, 30, -tw * 1.2, 38 + 24 * o, 0.5 + 0.24 * o);
      for (var j = 0; j < this.STAM.length; j++) {
        var a = (j * 30 + this.rot * 1.5) * Math.PI / 180, r = 9 + 9 * o;
        this.STAM[j].setAttribute("cx", f(r * Math.cos(a), 2));
        this.STAM[j].setAttribute("cy", f(r * Math.sin(a), 2));
      }
      this.stamens.setAttribute("opacity", f(0.35 + 0.55 * o));
      this.core.setAttribute("r", f(9 + 7 * lv, 2));
      this.core.setAttribute("opacity", f(0.7 + 0.3 * lv));
      this.coreGlow.setAttribute("r", f(26 + 24 * lv, 2));
      this.coreGlow.setAttribute("opacity", f(0.4 + 0.6 * lv));
      this.halo.setAttribute("transform", "scale(" + f(0.65 + 0.35 * lv, 4) + ")");
      this.halo.setAttribute("opacity", f(0.45 + 0.55 * lv));
    }
  };

  var IMPL = { taiji: taiji, mist: mist, aura: aura, particles: particles, lotus: lotus };

  // ---------- active style, layers and the single animation loop ----------
  var cur = 0, layers = {}, raf = 0, last = 0;

  function active() { return IMPL[STYLES[cur]] || null; }   // null for "plain"

  function draw(dt, force) {
    var st = active();
    if (st && layers[STYLES[cur]]) st.render(level(), dt, force);
  }
  // Loop only for a non-plain style, on a visible tab, while practising (or, for styles with
  // an idle motion, at rest unless reduced motion is on).
  function needLoop() {
    var st = active();
    if (!st || document.hidden) return false;
    return running() || (st.idle && !RM);
  }
  function frame(now) {
    raf = 0;
    if (!needLoop()) return;
    var dt = last ? Math.min(0.1, (now - last) / 1000) : 0;
    last = now;
    draw(dt, false);
    raf = requestAnimationFrame(frame);
  }
  function wake() {
    if (!raf && needLoop()) { last = 0; raf = requestAnimationFrame(frame); }
  }
  function halt() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }

  function save(name) {
    try { window.localStorage.setItem(KEY, name); } catch (e) { /* storage unavailable */ }
  }
  function load() {
    var v = null;
    try { v = window.localStorage.getItem(KEY); } catch (e) { /* storage unavailable */ }
    var i = STYLES.indexOf(v);
    return i < 0 ? 0 : i;     // unknown, corrupt or missing -> plain
  }

  function normalize(i) {
    if (typeof i === "string" && STYLES.indexOf(i) >= 0) return STYLES.indexOf(i);
    i = Number(i);
    return Number.isInteger(i) && i >= 0 && i < STYLES.length ? i : 0;
  }

  function apply(i, persist) {
    halt();
    var prev = layers[STYLES[cur]];
    if (prev) prev.hidden = true;
    cur = normalize(i);
    var name = STYLES[cur], st = active();
    if (st && !layers[name]) {
      var layer = document.createElement("div");
      layer.className = "orb-layer orb-" + name;
      layer.setAttribute("aria-hidden", "true");
      circle.appendChild(layer);
      try {
        st.build(layer);
        layers[name] = layer;
      } catch (e) {            // a style that can't be built falls back to plain
        circle.removeChild(layer);
        cur = 0; name = "plain"; st = null;
      }
    }
    if (layers[name]) layers[name].hidden = false;
    circle.classList.toggle("orb-alt", cur !== 0);
    circle.setAttribute("data-orb", name);
    if (persist) save(name);
    draw(0, true);
    wake();
    return name;
  }

  function next() { return apply((cur + 1) % STYLES.length, true); }

  // ---------- input: click / tap, Enter / Space on the focused circle ----------
  circle.addEventListener("click", function () { next(); });
  circle.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();      // Space must not scroll the page
      if (!e.repeat) next();
    }
  });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) halt(); else wake();
  });
  if (mq) {
    var onRM = function (e) { RM = e.matches; halt(); draw(0, true); wake(); };
    if (mq.addEventListener) mq.addEventListener("change", onRM);
    else if (mq.addListener) mq.addListener(onRM);
  }

  // ---------- hook for the practice engine ----------
  window.BreathOrb = {
    // phase: "inhale" | "hold1" | "exhale" | "hold2" | "idle"; p: 0..1 through the phase;
    // scale: the scale the engine just gave the circle.
    breath: function (phase, p, scale) {
      var prev = B.phase;
      B.phase = phase; B.p = p; B.scale = scale;
      if (phase === "exhale" && prev !== "exhale") aura.exhale();
      if (phase === "idle") { draw(0, true); halt(); }
      wake();
    }
  };

  // Test hook for puppeteer: set(index or name), next(), current() -> style name.
  window.__orb = {
    styles: STYLES.slice(),
    set: function (i) { return apply(i, true); },
    next: next,
    current: function () { return STYLES[cur]; }
  };

  apply(load(), false);
})();
