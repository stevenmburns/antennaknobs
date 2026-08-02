import { useContext, useEffect, useRef, useState } from "react";
import type { SolveResponse } from "../../lib/api";
import { formatMetres } from "../../lib/format";
import { cross3, dot3, PROJECTIONS, type Projection, type Vec3 } from "../../lib/view";
import { ThemeContext } from "../hooks";
import { currentColor, plotColors } from "./palette";

// Viewport zoom ceiling. The motivating case (elt_whip, #384) hides 6.35 mm
// of cage detail inside a 2.44 m extent — a 1:384 scale gap — so the ceiling
// leaves an order of magnitude of headroom past "inspect the finest catalog
// detail at canvas size".
const VIEWPORT_ZOOM_MAX = 10000;

export function CurrentCanvas({
  result,
  projection,
  showHeatmap,
  showEnvelope,
  showWireLabels,
  showFeedNames,
  interactive = false,
}: {
  result: SolveResponse | null;
  projection: Projection;
  showHeatmap: boolean;
  showEnvelope: boolean;
  showWireLabels: boolean;
  showFeedNames: boolean;
  // Zoom/pan navigation — main stage only; thumbnails stay inert buttons.
  interactive?: boolean;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Viewport navigation (map-style: cursor-anchored wheel/pinch zoom, drag
  // pan, double-click/tap or the Fit button to re-fit — survey in PR #384).
  // zoom=1, pan=0 IS the auto-fit view, so the fit framing keeps tracking
  // knob drags and re-solves; zoom composes on top as a pure multiplier.
  // Lives in a ref (mutated at pointer-event rate, drawn via rAF) with a
  // React mirror of the zoom level for the HUD chip / touch-action gate.
  const vpRef = useRef({ zoom: 1, panX: 0, panY: 0 });
  const [vpZoom, setVpZoom] = useState(1);
  const redrawRef = useRef<() => void>(() => {});
  const resetViewport = () => {
    vpRef.current = { zoom: 1, panX: 0, panY: 0 };
    setVpZoom(1);
  };

  // The fit frame of the last completed draw (projection + fit centre/scale).
  // A projection switch carries the viewport over through it — see draw() —
  // instead of resetting, so a feature under 400× inspection stays under
  // inspection when the view turns. Cleared on design switch: the previous
  // design's frame means nothing for the new geometry.
  const frameRef = useRef<{
    projection: Projection;
    hC: number;
    vC: number;
    scale: number;
  } | null>(null);

  // Switching DESIGNS re-fits: the viewport was aimed at the old geometry.
  // (Projection switches within a design carry the viewport — see draw().)
  const geometryName = result?.geometry ?? "";
  useEffect(() => {
    resetViewport();
    frameRef.current = null;
    // The main draw effect below re-runs on any new result, so the re-fit
    // paints without an explicit redraw.
  }, [geometryName]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const PC = plotColors();
    const onResize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    };

    function draw() {
      if (!canvas) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx!.clearRect(0, 0, w, h);

      // Vertical axis guide.
      ctx!.strokeStyle = PC.axisFaint;
      ctx!.lineWidth = 1;
      ctx!.beginPath();
      ctx!.moveTo(w / 2, 20);
      ctx!.lineTo(w / 2, h - 20);
      ctx!.stroke();

      if (!result) return;

      // Scale anchored to design wavelength. Worst-case extents (in λ):
      //   horizontal: hf_max × λ/2 ≈ 0.6 λ  (both V and Yagi)
      //   vertical:   max(V droop, Yagi spacing) ≈ 0.5 λ
      //
      // `s` proportionally shrinks every fixed pixel constant (padding,
      // strokes, envelope amplitude, label sizes) so the rendering looks
      // the same at thumbnail and main sizes. Floor keeps thumbnails
      // legible; cap prevents very-large canvases from over-inflating.
      const refSize = 600;
      const s = Math.max(0.3, Math.min(1.4, Math.min(w, h) / refSize));
      const lambdaDesign = result.lambda_design_m;
      const pad = 50 * s;
      const barReserveBottom = 40 * s;
      const FILL = 0.85;

      // Camera projection: an orthonormal screen basis (see PROJECTIONS) —
      // world point p lands at canvas (h·p, v·p); the camera ray is h×v.
      // App.tsx sets a per-geometry default (V/fan_dipole → "yz" side,
      // Yagi/moxon/hexbeam → "xy" top) but the user can override via the
      // projection toggle in the stage.
      const projSpec = PROJECTIONS.find((p) => p.id === projection)!;
      const hVec = projSpec.h;
      const vVec = projSpec.v;
      // True for the two elevation views (screen-up IS world z), which gates
      // the ground reference line below; the isometric's tilted up-vector
      // draws no line (z=0 doesn't project to a horizontal line there).
      const upIsZ = vVec[0] === 0 && vVec[1] === 0 && vVec[2] === 1;
      let hMin = Infinity, hMax = -Infinity;
      let vMin = Infinity, vMax = -Infinity;
      // Axis-aligned world bbox too — the projection-switch carry-over needs
      // a depth estimate along the old camera ray (see below).
      const bbMin = [Infinity, Infinity, Infinity];
      const bbMax = [-Infinity, -Infinity, -Infinity];
      for (const wire of result.wires) {
        for (const p of wire.knot_positions) {
          const ph = dot3(hVec, p);
          const pv = dot3(vVec, p);
          if (ph < hMin) hMin = ph;
          if (ph > hMax) hMax = ph;
          if (pv < vMin) vMin = pv;
          if (pv > vMax) vMax = pv;
          for (let a = 0; a < 3; a++) {
            if (p[a] < bbMin[a]) bbMin[a] = p[a];
            if (p[a] > bbMax[a]) bbMax[a] = p[a];
          }
        }
      }

      // When ground is enabled and screen-up is world z, expand the visible
      // vertical range to include z=0 so the ground reference line lands
      // inside the canvas. Without this, antennas sitting well above the
      // plane push the ground line off-screen.
      let vEffMin = vMin, vEffMax = vMax;
      if (result.ground && upIsZ) {
        vEffMin = Math.min(vMin, 0);
        vEffMax = Math.max(vMax, 0);
      }
      // Vertical span used to size the canvas. Floor at the wavelength
      // worst-case so small antennas don't render comically large; grow with
      // the ground-adjusted antenna span so high antennas zoom out enough
      // to fit the ground line.
      const vSpanEff = Math.max(vEffMax - vEffMin, 0.5 * lambdaDesign);
      // Horizontal span: same floor-with-actual-extent pattern as vertical.
      // The 0.6λ floor covers the typical V / Yagi worst case; wider
      // antennas (EDZ at ~1.5λ, fan-dipole 5-band, ...) grow the span
      // from their actual hMax-hMin so they fit on canvas.
      const hSpanEff = Math.max(hMax - hMin, 0.6 * lambdaDesign);
      const scale = FILL * Math.min(
        (w - 2 * pad) / hSpanEff,
        (h - pad - barReserveBottom) / vSpanEff,
      );

      const hC = (hMin + hMax) / 2;
      const vC = (vEffMin + vEffMax) / 2;
      const cx = w / 2;
      const cy = h / 2;
      const vp = vpRef.current;

      // Projection switch with an active zoom: carry the viewport over
      // instead of resetting. Reconstruct the world point at the old canvas
      // centre — its two screen coordinates from the old frame, its depth
      // along the old camera ray from the geometry point nearest that
      // centre ray (the wire actually under inspection; the bbox centre
      // would misplace anything off-centre in depth, e.g. an apex feed) —
      // then aim the new frame at that point, preserving the absolute px/m
      // scale so the feature keeps its on-screen size (each view has its
      // own fit scale, so the relative zoom factor is rescaled). If the
      // carried zoom clamps to 1, it degrades to a plain fit. Design
      // switches still hard-reset (frameRef is cleared by the effect above).
      const frame = frameRef.current;
      if (frame && frame.projection !== projection && vp.zoom > 1) {
        const old = PROJECTIONS.find((p) => p.id === frame.projection)!;
        const oldZscale = frame.scale * vp.zoom;
        const hCtr = frame.hC - vp.panX / oldZscale;
        const vCtr = frame.vC + vp.panY / oldZscale;
        const n = cross3(old.h, old.v);
        let depth = dot3(n, [
          (bbMin[0] + bbMax[0]) / 2,
          (bbMin[1] + bbMax[1]) / 2,
          (bbMin[2] + bbMax[2]) / 2,
        ]);
        let best = Infinity;
        for (const wire of result.wires) {
          for (const p of wire.knot_positions) {
            const dh = dot3(old.h, p) - hCtr;
            const dv = dot3(old.v, p) - vCtr;
            const d2 = dh * dh + dv * dv;
            if (d2 < best) {
              best = d2;
              depth = dot3(n, p);
            }
          }
        }
        const P: Vec3 = [
          old.h[0] * hCtr + old.v[0] * vCtr + n[0] * depth,
          old.h[1] * hCtr + old.v[1] * vCtr + n[1] * depth,
          old.h[2] * hCtr + old.v[2] * vCtr + n[2] * depth,
        ];
        const zoomNew = Math.min(
          VIEWPORT_ZOOM_MAX,
          Math.max(1, (vp.zoom * frame.scale) / scale),
        );
        vp.zoom = zoomNew;
        if (zoomNew > 1) {
          const zs = scale * zoomNew;
          vp.panX = (hC - dot3(hVec, P)) * zs;
          vp.panY = (dot3(vVec, P) - vC) * zs;
        } else {
          vp.panX = 0;
          vp.panY = 0;
        }
        setVpZoom(zoomNew);
      }
      frameRef.current = { projection, hC, vC, scale };

      // Compose the user viewport on top of the fit framing. Only geometry
      // goes through `zscale`; pixel-sized glyphs (strokes, labels, envelope
      // amplitude, feed dot) stay on `s`, so zooming magnifies the antenna
      // without ballooning its annotations.
      const zscale = scale * vp.zoom;
      const project = (p: [number, number, number]) => ({
        x: cx + (dot3(hVec, p) - hC) * zscale + vp.panX,
        y: cy + (vC - dot3(vVec, p)) * zscale + vp.panY, // higher vert value = higher on screen
      });

      // Ground reference line at world z=0, drawn only on the elevation
      // views (screen-up is world z) when the backend has ground enabled.
      // Cosmetic — the math is correct regardless; this just removes the
      // "where is the ground" guessing game from the side view. vC was
      // adjusted above to keep this on-canvas, so no bounds check needed
      // here.
      if (result.ground && upIsZ) {
        const groundY = cy + vC * zscale + vp.panY;
        ctx!.strokeStyle = `rgba(${PC.groundRgb}, 0.55)`;
        ctx!.lineWidth = 1;
        ctx!.setLineDash([6, 4]);
        ctx!.beginPath();
        ctx!.moveTo(0, groundY);
        ctx!.lineTo(w, groundY);
        ctx!.stroke();
        ctx!.setLineDash([]);
        ctx!.fillStyle = `rgba(${PC.groundRgb}, 0.85)`;
        ctx!.font = `${Math.max(8, Math.round(10 * s))}px ui-monospace, monospace`;
        ctx!.fillText("ground (z = 0)", 8 * s, groundY - 4 * s);
      }

      // Global current magnitude — use sample arrays when available so the
      // shared color scale catches mid-segment peaks (B-spline d=2 quadratic
      // curvature, sinusoidal three-term, B-spline enrichment dip). Falls
      // back to knot arrays for backends that don't ship samples (PyNEC).
      let magMaxGlobal = 1e-30;
      const perWirePts: [number, number, number][][] = [];
      const perWireMags: number[][] = [];
      for (const wire of result.wires) {
        const pts = wire.sample_positions ?? wire.knot_positions;
        const cre = wire.sample_currents_re ?? wire.knot_currents_re;
        const cim = wire.sample_currents_im ?? wire.knot_currents_im;
        const m = cre.map((r, i) => Math.hypot(r, cim[i]));
        perWirePts.push(pts);
        perWireMags.push(m);
        for (const v of m) if (v > magMaxGlobal) magMaxGlobal = v;
      }

      ctx!.lineCap = "round";
      ctx!.lineJoin = "round";

      // One wire at a time: wire stroke + envelope.
      const envScale = 60 * s;
      const labelFontPx = Math.max(8, Math.round(11 * s));
      const feedFontPx = Math.max(8, Math.round(12 * s));
      const feedWireIdx = result.feed_wire_index;
      for (let wi = 0; wi < result.wires.length; wi++) {
        const wire = result.wires[wi];
        const pts = perWirePts[wi];
        const mags = perWireMags[wi];

        for (let i = 0; i < pts.length - 1; i++) {
          const a = project(pts[i]);
          const b = project(pts[i + 1]);
          if (showHeatmap) {
            const m = (0.5 * (mags[i] + mags[i + 1])) / magMaxGlobal;
            ctx!.strokeStyle = currentColor(m);
            ctx!.lineWidth = (2 + 6 * m) * s;
          } else {
            // Plain wires: uniform color/width, no current-magnitude modulation.
            ctx!.strokeStyle = PC.labelBright;
            ctx!.lineWidth = 2 * s;
          }
          ctx!.beginPath();
          ctx!.moveTo(a.x, a.y);
          ctx!.lineTo(b.x, b.y);
          ctx!.stroke();
        }

        // Current-waveform envelope: if this is the feed wire (and the feed
        // isn't at an end), split at the feed knot so a V's per-arm tangent
        // flip is respected. Otherwise draw one continuous envelope.
        // feed_knot_index lives in knot-array space; in sample space (knots
        // interleaved with midpoints) it maps to 2*feed_knot_index.
        if (showEnvelope) {
          ctx!.strokeStyle = `rgba(${PC.envelopeRgb}, 0.7)`;
          ctx!.lineWidth = 1.5 * s;
          const lastIdx = pts.length - 1;
          const hasSamples = wire.sample_positions != null;
          const feedIdx = result.feed_knot_index * (hasSamples ? 2 : 1);
          if (wi === feedWireIdx && feedIdx > 0 && feedIdx < lastIdx) {
            drawArmEnvelope(ctx!, pts, mags, magMaxGlobal, project, 0, feedIdx, envScale);
            drawArmEnvelope(ctx!, pts, mags, magMaxGlobal, project, feedIdx, lastIdx, envScale);
          } else {
            drawArmEnvelope(ctx!, pts, mags, magMaxGlobal, project, 0, lastIdx, envScale);
          }
        }

        // Wire label near the leftmost knot for multi-wire geometries.
        if (showWireLabels && result.wires.length > 1) {
          const lp = project(wire.knot_positions[0]);
          ctx!.fillStyle = PC.label;
          ctx!.font = `${labelFontPx}px ui-monospace, monospace`;
          ctx!.fillText(wire.label, lp.x - 8 * s - ctx!.measureText(wire.label).width, lp.y + 3 * s);
        }
      }

      // Feed marker(s). Three sources, in priority order:
      //  1. `feed_positions[]` (issue #571): one physical feed point per
      //     declared feed port — a lazy-H fed in phase through a harness has
      //     two, one per element centre, even though its drive comes from a
      //     single build_network() source. Rendered with the port name.
      //  2. `feeds[]` (bowtie 1×2 array): per-feed Z+V, labelled by phase.
      //  3. the legacy single feed_position / feed_wire_index path.
      if (result.feed_positions && result.feed_positions.length > 0) {
        const fps = result.feed_positions;
        for (let fi = 0; fi < fps.length; fi++) {
          const feed = project(fps[fi].position);
          ctx!.fillStyle = PC.feed;
          ctx!.beginPath();
          ctx!.arc(feed.x, feed.y, 5 * s, 0, Math.PI * 2);
          ctx!.fill();
          if (showFeedNames) {
            ctx!.font = `${feedFontPx}px ui-monospace, monospace`;
            const label = fps.length > 1 ? fps[fi].name : "feed";
            ctx!.fillText(label, feed.x + 8 * s, feed.y - 8 * s);
          }
        }
      } else {
        const feedList = result.feeds && result.feeds.length > 0
          ? result.feeds
          : [{
              wire_index: feedWireIdx,
              knot_index: result.feed_knot_index,
              feed_position: result.feed_position,
              v_re: 1, v_im: 0,
              z_re: result.z_in_re, z_im: result.z_in_im,
            }];
        for (let fi = 0; fi < feedList.length; fi++) {
          const f = feedList[fi];
          const w_ = result.wires[f.wire_index];
          // Prefer the exact feed point; fall back to the nearest knot.
          const pos3d = f.feed_position ?? (w_ ? w_.knot_positions[f.knot_index] : undefined);
          if (!pos3d) continue;
          const feed = project(pos3d);
          ctx!.fillStyle = PC.feed;
          ctx!.beginPath();
          ctx!.arc(feed.x, feed.y, 5 * s, 0, Math.PI * 2);
          ctx!.fill();
          if (showFeedNames) {
            ctx!.font = `${feedFontPx}px ui-monospace, monospace`;
            const label = feedList.length > 1
              ? `feed ${fi} ∠${Math.round(Math.atan2(f.v_im, f.v_re) * 180 / Math.PI)}°`
              : "feed";
            ctx!.fillText(label, feed.x + 8 * s, feed.y - 8 * s);
          }
        }
      }

      // Scale bar, centered horizontally under the antenna. At fit zoom it
      // is the familiar λ/4 bar; once zoomed, λ/4 no longer fits on screen,
      // so it becomes a map-style bar: a nice round length (1/2/5 × 10^k m)
      // near a quarter of the canvas width, always true to `zscale`.
      let barWorld = lambdaDesign / 4;
      let barLabel = `λ/4 = ${(lambdaDesign / 4).toFixed(2)} m`;
      if (vp.zoom !== 1) {
        const target = (0.25 * w) / zscale;
        const pow = Math.pow(10, Math.floor(Math.log10(target)));
        const mant = target / pow;
        barWorld = (mant >= 5 ? 5 : mant >= 2 ? 2 : 1) * pow;
        barLabel = formatMetres(barWorld);
      }
      const barLenPx = barWorld * zscale;
      const barX0 = (w - barLenPx) / 2;
      const barY = h - 24 * s;
      ctx!.strokeStyle = PC.label;
      ctx!.lineWidth = 1;
      ctx!.beginPath();
      ctx!.moveTo(barX0, barY);
      ctx!.lineTo(barX0 + barLenPx, barY);
      ctx!.moveTo(barX0, barY - 4 * s);
      ctx!.lineTo(barX0, barY + 4 * s);
      ctx!.moveTo(barX0 + barLenPx, barY - 4 * s);
      ctx!.lineTo(barX0 + barLenPx, barY + 4 * s);
      ctx!.stroke();
      ctx!.fillStyle = PC.labelBright;
      ctx!.font = `${labelFontPx}px ui-monospace, monospace`;
      const labelW = ctx!.measureText(barLabel).width;
      ctx!.fillText(barLabel, (w - labelW) / 2, barY - 8 * s);
    }

    onResize();
    const obs = new ResizeObserver(onResize);
    obs.observe(canvas);
    redrawRef.current = draw;
    if (!interactive) return () => obs.disconnect();

    // ---- viewport navigation ------------------------------------------
    // Draws coalesce to one per frame: pointer/wheel events mutate vpRef
    // and schedule a rAF repaint.
    let raf = 0;
    const scheduleDraw = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        draw();
      });
    };

    // Zoom by `factor` keeping the canvas point (ax, ay) fixed — the world
    // point under the cursor/pinch centre stays under it. Zooming all the
    // way back out lands exactly on the fit view (pan snaps to 0).
    const applyZoom = (factor: number, ax: number, ay: number) => {
      const v = vpRef.current;
      const z = Math.min(VIEWPORT_ZOOM_MAX, Math.max(1, v.zoom * factor));
      const f = z / v.zoom;
      const cx = canvas.clientWidth / 2;
      const cy = canvas.clientHeight / 2;
      v.panX = ax - cx - (ax - cx - v.panX) * f;
      v.panY = ay - cy - (ay - cy - v.panY) * f;
      v.zoom = z;
      if (z === 1) {
        v.panX = 0;
        v.panY = 0;
      }
      setVpZoom(z);
      scheduleDraw();
    };

    // Wheel zoom, ~1.2× per detent, exponential so trackpads feel smooth.
    // Native non-passive listener for the same reason as the VFO dial:
    // React's onWheel can't preventDefault the page scroll.
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY; // line-mode → px
      applyZoom(Math.exp(-dy * 0.002), e.clientX - rect.left, e.clientY - rect.top);
    };

    // Pointer state: one pointer drags (pan — only when zoomed, so at fit a
    // touch drag stays with the mobile carousel swipe), two pinch-zoom.
    const pointers = new Map<number, { x: number; y: number; downX: number; downY: number }>();
    let moved = false;
    let lastTap = { t: 0, x: 0, y: 0 };
    const posOf = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };

    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType === "mouse" && e.button !== 0 && e.button !== 1) return;
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        // Capture is best-effort: a drag that leaves the canvas just ends.
      }
      const p = posOf(e);
      pointers.set(e.pointerId, { ...p, downX: p.x, downY: p.y });
      moved = false;
      if (e.pointerType === "mouse") e.preventDefault(); // middle-click autoscroll
    };

    const onPointerMove = (e: PointerEvent) => {
      const prev = pointers.get(e.pointerId);
      if (!prev) return;
      const p = posOf(e);
      if (Math.hypot(p.x - prev.downX, p.y - prev.downY) > 4) moved = true;
      if (pointers.size === 2) {
        // Pinch: translate by the midpoint delta, zoom by the distance
        // ratio about the new midpoint.
        const other = [...pointers.entries()].find(([id]) => id !== e.pointerId)![1];
        const oldMid = { x: (prev.x + other.x) / 2, y: (prev.y + other.y) / 2 };
        const oldDist = Math.hypot(prev.x - other.x, prev.y - other.y) || 1;
        const newMid = { x: (p.x + other.x) / 2, y: (p.y + other.y) / 2 };
        const newDist = Math.hypot(p.x - other.x, p.y - other.y) || 1;
        const v = vpRef.current;
        v.panX += newMid.x - oldMid.x;
        v.panY += newMid.y - oldMid.y;
        applyZoom(newDist / oldDist, newMid.x, newMid.y);
      } else if (pointers.size === 1 && vpRef.current.zoom > 1) {
        const v = vpRef.current;
        v.panX += p.x - prev.x;
        v.panY += p.y - prev.y;
        scheduleDraw();
      }
      pointers.set(e.pointerId, { ...prev, x: p.x, y: p.y });
    };

    const onPointerUp = (e: PointerEvent) => {
      const had = pointers.delete(e.pointerId);
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch {
        // Never captured (see above) — nothing to release.
      }
      if (!had || moved || e.type === "pointercancel") return;
      // Clean tap/click: double within 350 ms & 30 px re-fits.
      const now = performance.now();
      const p = posOf(e);
      if (now - lastTap.t < 350 && Math.hypot(p.x - lastTap.x, p.y - lastTap.y) < 30) {
        resetViewport();
        scheduleDraw();
        lastTap = { t: 0, x: 0, y: 0 };
      } else {
        lastTap = { t: now, x: p.x, y: p.y };
      }
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    return () => {
      obs.disconnect();
      if (raf) cancelAnimationFrame(raf);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
    };
  }, [result, projection, showHeatmap, showEnvelope, showWireLabels, showFeedNames, theme, interactive]);

  const zoomed = vpZoom > 1.001;
  return (
    <div className="canvas-viewport">
      <canvas
        ref={canvasRef}
        style={
          interactive
            ? {
                // At fit, touch drags belong to the page (mobile carousel
                // swipe); pinch is never a browser gesture here, so a
                // two-finger zoom always reaches us. Once zoomed, the canvas
                // owns all touches for panning until re-fit.
                touchAction: zoomed ? "none" : "pan-x pan-y",
                cursor: zoomed ? "grab" : "zoom-in",
              }
            : undefined
        }
      />
      {interactive && (
        <div className="viewport-hud">
          {zoomed && (
            <span className="viewport-zoom">
              {vpZoom >= 10 ? Math.round(vpZoom) : vpZoom.toFixed(1)}×
            </span>
          )}
          <button
            className="viewport-fit"
            disabled={!zoomed}
            onClick={() => {
              resetViewport();
              redrawRef.current();
            }}
            title="Zoom to fit (or double-click the canvas)"
          >
            Fit
          </button>
        </div>
      )}
    </div>
  );
}

function drawArmEnvelope(
  ctx: CanvasRenderingContext2D,
  knots: [number, number, number][],
  mags: number[],
  magMax: number,
  project: (p: [number, number, number]) => { x: number; y: number },
  start: number,
  end: number,
  envScale: number,
) {
  if (end <= start) return;

  // Per-segment normal in canvas space, oriented toward screen-up so V-style
  // arms put their envelopes "above" the wire. For axis-aligned vertical
  // segments ny is exactly zero and the flip is a no-op; that's fine — what
  // matters is that the moxon's adjacent perpendicular segments get
  // *different* normals so the bend-break below catches the corner.
  const segN: { nx: number; ny: number }[] = [];
  for (let i = start; i < end; i++) {
    const p = project(knots[i]);
    const q = project(knots[i + 1]);
    const dx = q.x - p.x;
    const dy = q.y - p.y;
    const len = Math.hypot(dx, dy) || 1;
    let nx = -dy / len;
    let ny = dx / len;
    if (ny > 0) {
      nx = -nx;
      ny = -ny;
    }
    segN.push({ nx, ny });
  }

  // Walk runs of segments whose normals agree (within ~3°), and start a new
  // sub-path at each bend. Without this, a connected envelope at a 90°
  // corner zigzags across the corner since the two adjacent segments offset
  // their knots in perpendicular directions.
  const BEND_TOL = 0.9986;  // cos(3°)
  ctx.beginPath();
  let s = 0;
  while (s < segN.length) {
    let e = s;
    while (
      e + 1 < segN.length &&
      segN[e].nx * segN[e + 1].nx + segN[e].ny * segN[e + 1].ny >= BEND_TOL
    ) {
      e++;
    }
    const { nx, ny } = segN[s];
    for (let k = s; k <= e + 1; k++) {
      const ki = start + k;
      const p = project(knots[ki]);
      const offset = (mags[ki] / magMax) * envScale;
      const ex = p.x + nx * offset;
      const ey = p.y + ny * offset;
      if (k === s) ctx.moveTo(ex, ey);
      else ctx.lineTo(ex, ey);
    }
    s = e + 1;
  }
  ctx.stroke();
}
