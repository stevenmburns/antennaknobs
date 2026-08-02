import { useEffect, useRef, useState } from "react";
import { mixHex } from "../../lib/math";

// A dependency-free rotary knob — a drop-in alternative to the range
// slider for float/int params. Semantically a slider (role="slider"), so
// it stays keyboard- and screen-reader-accessible: vertical drag, scroll
// wheel, and arrow keys all adjust the value; double-click (or Enter) to
// type an exact number. The dial sweeps ~270° from min (lower-left) to
// max (lower-right). Absolute-angle dragging is deliberately avoided —
// drag is a *relative* vertical delta, which is far easier to do
// precisely than chasing the pointer around a circle.
export function Knob({
  knobId,
  value,
  min,
  max,
  step,
  precision,
  unit,
  label,
  onChange,
  startDeg = -135,
  sweepDeg = 270,
  variant = "param",
  disabled = false,
}: {
  // Stable id, emitted as data-knob-id for testing/debugging.
  knobId: string;
  value: number;
  min: number;
  max: number;
  step: number;
  precision: number;
  unit: string | null;
  label: string;
  onChange: (v: number) => void;
  // Dial geometry in clock-angle degrees (0 = 12 o'clock, +CW). The default is
  // the classic 270° gauge sweeping clockwise from 7:30 (lower-left) to 4:30.
  // Pass startDeg=90, sweepDeg=-(max-min) for a CCW dial starting at 3 o'clock
  // (elevation: -90 quarter-arc; azimuth: -360 full circle) — degrees then map
  // 1:1 onto the dial face.
  startDeg?: number;
  sweepDeg?: number;
  // "vfo" = the big weighted measurement-freq tuning dial: knurled skirt +
  // finger dimple on an eased rotor, outer band arc that warms toward the edge.
  // "param" = the compact setup/cut dials (clean accent, no warming).
  variant?: "param" | "vfo";
  // Locked (e.g. measurement freq while "lock to design freq" is on): dims the
  // dial and ignores drag/wheel/keys.
  disabled?: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ y: number; v: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const isVfo = variant === "vfo";
  const span = max - min || 1;
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  // Clamp + round to the param's precision so we emit clean values (2.46, not
  // 2.4600000001) and don't spam the live solve with fp noise. No grid snap —
  // used where the exact value matters (Home/End reaching min/max).
  const roundP = (v: number) => {
    const p = precision >= 0 ? precision : 6;
    return clamp(Number(v.toFixed(p)));
  };
  // Snap to the nearest multiple of `step` — a clean grid anchored at 0, not at
  // `min`. Anchoring at min offset the whole grid by min's fractional part, so
  // nudging an off-grid value kept that offset (1.03 + 0.2 -> 1.23). Anchored at
  // 0 it lands on a round increment (1.03 + 0.2 -> 1.2). min/max are bounds, not
  // the grid origin; they stay reachable exactly via roundP (Home/End).
  const snap = (v: number) => {
    if (step > 0) v = Math.round(v / step) * step;
    return roundP(v);
  };

  const frac = Math.min(1, Math.max(0, (value - min) / span));
  const ang = startDeg + frac * sweepDeg;
  const Rarc = isVfo ? 42 : 38;
  const polar = (deg: number, r: number): [number, number] => {
    const a = (deg * Math.PI) / 180;
    return [50 + r * Math.sin(a), 50 - r * Math.cos(a)];
  };
  const arc = (r: number, a0: number, a1: number): string => {
    const [x0, y0] = polar(a0, r);
    const [x1, y1] = polar(a1, r);
    const delta = a1 - a0;
    const large = Math.abs(delta) > 180 ? 1 : 0;
    // Sweep-flag follows the traversal direction: clockwise (SVG +angle) for an
    // increasing clock-angle, counter-clockwise for a decreasing one. Lets a
    // negative sweepDeg (CCW dials: elevation, azimuth) bend the correct way.
    const sweep = delta >= 0 ? 1 : 0;
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} ${sweep} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };
  // Param-knob indicator notch across the cap face (center-out), at value.
  const [nx0, ny0] = polar(ang, 3);
  const [nx1, ny1] = polar(ang, 14);
  // Only the VFO's band arc warms --accent -> --hot over the top ~40% of travel
  // ("redlining" near the band edge). Small knobs stay a clean accent.
  const warm = Math.max(0, (frac - 0.6) / 0.4);
  const fillColor = isVfo ? mixHex("#2f5fb0", "#cf7a22", warm) : undefined;

  // Scroll wheel: ±step per detent (×10 with Shift). Attached natively so
  // we can preventDefault — React's onWheel is passive and can't stop the
  // page from scrolling under the dial.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (disabled) return;
      e.preventDefault();
      const dir = e.deltaY < 0 ? 1 : -1;
      const mult = e.shiftKey ? 10 : 1;
      let v = value + dir * step * mult;
      // Snap to the step grid anchored at 0 (clean multiples), matching snap().
      if (step > 0) v = Math.round(v / step) * step;
      const p = precision >= 0 ? precision : 6;
      onChange(Math.min(max, Math.max(min, Number(v.toFixed(p)))));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [value, step, min, max, precision, onChange, disabled]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (editing || disabled) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = { y: e.clientY, v: value };
    setDragging(true);
    wrapRef.current?.focus();
    e.preventDefault();
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dy = d.y - e.clientY; // drag up = increase
    const sens = e.shiftKey ? 0.25 : 1; // hold Shift for fine control
    onChange(snap(d.v + (dy / 180) * span * sens)); // ~180px = full sweep
  };
  const endDrag = (e: React.PointerEvent) => {
    dragRef.current = null;
    setDragging(false);
    (e.target as Element).releasePointerCapture?.(e.pointerId);
  };

  // Apply a single nav/edit key to this knob. Shared by the local onKeyDown
  // (when the knob is focused) and the global sticky-selection router (when it
  // isn't). Returns true when the key was consumed, so callers can
  // preventDefault only for keys we actually handled.
  const applyKey = (key: string): boolean => {
    if (disabled) return false;
    if (key === "Enter") {
      setEditing(true);
      return true;
    }
    let next: number | null = null;
    switch (key) {
      case "ArrowUp":
      case "ArrowRight":
        next = value + step;
        break;
      case "ArrowDown":
      case "ArrowLeft":
        next = value - step;
        break;
      case "PageUp":
        next = value + step * 10;
        break;
      case "PageDown":
        next = value - step * 10;
        break;
      case "Home":
        // Jump to exactly min/max — these are bounds, not grid points, so skip
        // the step snap (roundP clamps + rounds to precision only).
        onChange(roundP(min));
        return true;
      case "End":
        onChange(roundP(max));
        return true;
      default:
        return false;
    }
    onChange(snap(next));
    return true;
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (applyKey(e.key)) e.preventDefault();
  };

  const commit = (raw: string) => {
    const n = Number(raw);
    if (Number.isFinite(n)) onChange(snap(n));
    setEditing(false);
  };

  const p = Math.max(0, precision);
  return (
    <div
      className={`knob${isVfo ? " is-vfo" : ""}${disabled ? " is-disabled" : ""}`}
      data-knob-id={knobId}
      ref={wrapRef}
      role="slider"
      tabIndex={editing || disabled ? -1 : 0}
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={`${value.toFixed(p)}${unit ?? ""}`}
      aria-disabled={disabled || undefined}
      onKeyDown={onKeyDown}
    >
      {editing ? (
        <input
          className="knob-edit"
          type="number"
          autoFocus
          defaultValue={value}
          min={min}
          max={max}
          step={step}
          onBlur={(e) => commit((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
            else if (e.key === "Escape") setEditing(false);
            e.stopPropagation();
          }}
        />
      ) : (
        <svg
          // The VFO's 270° gauge opens at the bottom (~6 o'clock) and its
          // content stops by y≈82, so crop the empty bottom off the box rather
          // than reserve a full square. NOT for the others: the azimuth dial is
          // a full circle that uses the bottom.
          viewBox={isVfo ? "0 0 100 88" : "0 0 100 100"}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onDoubleClick={() => setEditing(true)}
        >
          <path
            className="knob-track"
            d={arc(Rarc, startDeg, startDeg + sweepDeg)}
          />
          <path
            className="knob-fill"
            style={fillColor ? { stroke: fillColor } : undefined}
            d={arc(Rarc, startDeg, ang)}
          />
          {/* Focus ring drawn in SVG space so it's a true circle centered on the
              dial (50,50) — the wrapper's box-shadow ring would be an ellipse on
              the VFO's non-square 112×99 box. Just outside the gauge arc (Rarc).
              Shown on keyboard focus via .vfo-focus-ring CSS. */}
          {isVfo && <circle className="vfo-focus-ring" cx="50" cy="50" r="50.5" />}
          {isVfo ? (
            // The whole knob body spins; the band arc behind it stays put — a
            // fixed scale with a turning dial, exactly like a transceiver VFO.
            <g
              className={`knob-rotor${dragging ? " no-ease" : ""}`}
              style={{ transform: `rotate(${ang.toFixed(2)}deg)` }}
            >
              <circle className="knob-cap" cx="50" cy="50" r="30" />
              {Array.from({ length: 30 }, (_, i) => {
                const a = (i * 360) / 30;
                const [sx0, sy0] = polar(a, 27.5);
                const [sx1, sy1] = polar(a, 32);
                return (
                  <line
                    key={i}
                    className="knob-skirt"
                    x1={sx0.toFixed(2)}
                    y1={sy0.toFixed(2)}
                    x2={sx1.toFixed(2)}
                    y2={sy1.toFixed(2)}
                  />
                );
              })}
              <line className="knob-notch" x1="50" y1="39" x2="50" y2="24" />
              <circle className="knob-dimple" cx="50" cy="30" r="3.4" />
            </g>
          ) : (
            <>
              <circle className="knob-cap" cx="50" cy="50" r="15" />
              <line
                className="knob-notch"
                x1={nx0.toFixed(2)}
                y1={ny0.toFixed(2)}
                x2={nx1.toFixed(2)}
                y2={ny1.toFixed(2)}
              />
            </>
          )}
        </svg>
      )}
    </div>
  );
}
