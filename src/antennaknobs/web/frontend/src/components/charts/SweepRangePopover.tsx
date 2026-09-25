import { useEffect, useState } from "react";
import { KnobMenuNumber } from "../backend/fields";
import {
  AUTO,
  type AxisDomain,
  DEFAULT_SWR_THRESHOLD,
  formatTick,
  S11_PRESET_FLOORS,
  s11DbForSwr,
  sameChoice,
  type SweepAxisChoice,
  type SweepMode,
  SWR_THRESHOLD_MAX,
  SWR_THRESHOLD_MIN,
  validChoice,
  VSWR_PRESET_TOPS,
} from "../../lib/sweepAxis";

// The sweep charts' range popover (AK#1738), opened by clicking the chart's
// y axis. Same pattern and classes as SweepRangeMenu (the measurement dial's
// menu): a full-screen backdrop takes the outside click, the box is fixed at
// the click, Escape closes.

type Field = "lo" | "hi" | "threshold";

const presetsFor = (mode: SweepMode): { label: string; choice: SweepAxisChoice }[] =>
  mode === "vswr"
    ? VSWR_PRESET_TOPS.map((hi) => ({
        label: `1–${formatTick(hi)}`,
        choice: { kind: "fixed", lo: 1, hi },
      }))
    : S11_PRESET_FLOORS.map((lo) => ({
        label: `${lo} dB`,
        // A preset is a floor under 0 dB (sweepAxisDomain keeps the top's
        // over-unity growth for it).
        choice: { kind: "fixed", lo, hi: 0 },
      }));

export function SweepRangePopover({
  mode,
  at,
  choice,
  drawn,
  threshold,
  onChoice,
  onThreshold,
  onClose,
}: {
  mode: SweepMode;
  /** Where the click landed, in viewport pixels. */
  at: { x: number; y: number };
  choice: SweepAxisChoice;
  /** The domain on screen now: what the custom fields start from. */
  drawn: AxisDomain;
  threshold: number;
  onChoice: (c: SweepAxisChoice) => void;
  onThreshold: (t: number) => void;
  onClose: () => void;
}) {
  const [invalid, setInvalid] = useState<ReadonlySet<Field>>(new Set());
  const mark = (f: Field, bad: boolean) =>
    setInvalid((s) => {
      if (s.has(f) === bad) return s;
      const next = new Set(s);
      if (bad) next.add(f);
      else next.delete(f);
      return next;
    });
  // The custom range edits whichever range is on screen, so typing one end
  // keeps the other where the viewer is looking.
  const custom = (patch: Partial<AxisDomain>, f: Field) => {
    const next: SweepAxisChoice = { kind: "fixed", ...drawn, ...patch };
    const ok = validChoice(mode, next);
    mark(f, !ok);
    if (ok) onChoice(next);
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const round = (v: number) => Number(v.toPrecision(4));
  const title = mode === "vswr" ? "VSWR range" : "S11 range";
  return (
    <>
      <div className="knob-menu-backdrop" onClick={onClose} />
      <div
        className="knob-menu sweep-axis-menu"
        role="dialog"
        aria-label={title}
        style={{ left: at.x, top: at.y }}
      >
        <div className="knob-menu-title">{title}</div>
        <div className="sweep-axis-presets" role="group" aria-label="range presets">
          <button
            type="button"
            aria-pressed={choice.kind === "auto"}
            title={
              mode === "vswr"
                ? "Fit the sweep's dip: the smallest of 1.5, 2, 3, 5, 10 … that holds it with headroom. Grows while a knob moves, re-fits when it settles."
                : "Fit the sweep's dip: the shallowest of −10, −20, −30 … dB it clears by 5 dB. Deepens while a knob moves, re-fits when it settles."
            }
            onClick={() => onChoice(AUTO)}
          >
            Auto
          </button>
          {presetsFor(mode).map((p) => (
            <button
              key={p.label}
              type="button"
              aria-pressed={sameChoice(choice, p.choice)}
              onClick={() => onChoice(p.choice)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="knob-menu-row">
          <span>{mode === "vswr" ? "min / max" : "min / max (dB)"}</span>
          <KnobMenuNumber
            value={round(drawn.lo)}
            onChange={(v) => custom({ lo: v }, "lo")}
            invalid={invalid.has("lo")}
            onRevert={() => mark("lo", false)}
          />
          <KnobMenuNumber
            value={round(drawn.hi)}
            onChange={(v) => custom({ hi: v }, "hi")}
            invalid={invalid.has("hi")}
            onRevert={() => mark("hi", false)}
          />
        </div>
        <div className="knob-menu-row">
          <span>SWR threshold</span>
          <KnobMenuNumber
            value={threshold}
            onChange={(v) => {
              const ok = v >= SWR_THRESHOLD_MIN && v <= SWR_THRESHOLD_MAX;
              mark("threshold", !ok);
              if (ok) onThreshold(v);
            }}
            invalid={invalid.has("threshold")}
            onRevert={() => mark("threshold", false)}
          />
        </div>
        <div className="knob-menu-note">
          {`the ${formatTick(Number(threshold.toFixed(2)))}:1 line; on S11 it is ${s11DbForSwr(threshold).toFixed(1)} dB`}
        </div>
        <button
          type="button"
          className="knob-menu-revert"
          disabled={threshold === DEFAULT_SWR_THRESHOLD}
          onClick={() => {
            mark("threshold", false);
            onThreshold(DEFAULT_SWR_THRESHOLD);
          }}
        >
          ↺ 2:1
        </button>
      </div>
    </>
  );
}
