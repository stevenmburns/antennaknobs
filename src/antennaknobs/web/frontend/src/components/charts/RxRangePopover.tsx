import { useEffect, useState } from "react";
import { useInViewport } from "./useInViewport";
import { KnobMenuNumber } from "../backend/fields";
import type { AxisDomain } from "../../lib/sweepAxis";
import { RX_AUTO, type RxAxisChoice, validRxChoice } from "../../lib/paramSweep";

// The Z-vs-parameter chart's y-axis range popover: Auto (fit the trace) or a
// custom min/max, in ohms. The #1738 popover's pattern and classes, without
// its presets and threshold, which are VSWR/S11 notions.
export function RxRangePopover({
  title,
  at,
  choice,
  drawn,
  side = "right",
  onChoice,
  onClose,
}: {
  title: string;
  at: { x: number; y: number };
  /** Which way the box opens from the click: "left" from a right-hand axis,
   *  toward the chart. Clamped to the viewport either way. */
  side?: "left" | "right";
  choice: RxAxisChoice;
  /** The range on screen now: what the custom fields start from. */
  drawn: AxisDomain;
  onChoice: (c: RxAxisChoice) => void;
  onClose: () => void;
}) {
  const [invalid, setInvalid] = useState<"lo" | "hi" | null>(null);
  const box = useInViewport<HTMLDivElement>(at, side);
  const custom = (patch: Partial<AxisDomain>, f: "lo" | "hi") => {
    const next: RxAxisChoice = { kind: "fixed", ...drawn, ...patch };
    const ok = validRxChoice(next);
    setInvalid(ok ? null : f);
    if (ok) onChoice(next);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const round = (v: number) => Number(v.toPrecision(5));
  return (
    <>
      <div className="knob-menu-backdrop" onClick={onClose} />
      <div
        className="knob-menu sweep-axis-menu"
        role="dialog"
        aria-label={title}
        ref={box}
        style={{ left: at.x, top: at.y }}
      >
        <div className="knob-menu-title">{title}</div>
        <div className="sweep-axis-presets" role="group" aria-label="range presets">
          <button
            type="button"
            aria-pressed={choice.kind === "auto"}
            title="Fit this trace (and Z*, on a density sweep), whatever the other axis does"
            onClick={() => onChoice(RX_AUTO)}
          >
            Auto
          </button>
        </div>
        <div className="knob-menu-row">
          <span>min / max (Ω)</span>
          <KnobMenuNumber
            value={round(drawn.lo)}
            onChange={(v) => custom({ lo: v }, "lo")}
            invalid={invalid === "lo"}
            onRevert={() => setInvalid(null)}
          />
          <KnobMenuNumber
            value={round(drawn.hi)}
            onChange={(v) => custom({ hi: v }, "hi")}
            invalid={invalid === "hi"}
            onRevert={() => setInvalid(null)}
          />
        </div>
      </div>
    </>
  );
}
