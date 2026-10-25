import { useEffect, useState } from "react";
import {
  type Build,
  type BuildAxis,
  BUILD_MAX_POINTS,
  BUILD_MIN_POINTS,
  buildProblem,
  defaultBuildName,
  HOLD_TARGETS,
  type HoldObjective,
  holdRangeText,
} from "../../lib/buildAnalysis";
import type { SchemaParamSpec } from "../../lib/params";

// The map and hold builders (AK#2045), opened from the knob menu beside
// "Sweep this knob…": a two-knob map (two knobs, their ranges and points), or
// this knob swept with another held at a target (resonance on one knob, a Z0
// match on two). Build makes the analysis (lib/buildAnalysis.ts), lists it in
// the tab's picker as "built here", and picks it on the first chart, where
// it runs as a design's own map or held sweep does. Copy link then carries
// it. In the keep dialog's modal shell.

export type BuildKind = "map" | "hold";

export type BuildAnalysisDialogProps = {
  kind: BuildKind;
  /** The knob the menu was opened on: the map's x, the hold's swept knob. */
  knob: string;
  /** The design's sweepable knobs. */
  knobs: readonly SchemaParamSpec[];
  /** A knob's default sweep (its own range and the chart's point count). */
  axisFor: (knob: string) => BuildAxis;
  /** The names the tab's picker lists already. */
  taken: ReadonlySet<string>;
  /** The ranges set in the knobs' Optimize menus (KnobOpt optMin/optMax),
   *  by knob: a held knob searches its own, else its own real range. */
  optRanges?: Readonly<Record<string, { min: number; max: number }>>;
  /** Build it: resolves once it is listed and picked, rejects with why not. */
  onBuild: (b: Build) => Promise<void>;
  onClose: () => void;
};

type AxisText = { knob: string; lo: string; hi: string; points: string; log: boolean };

const asText = (a: BuildAxis): AxisText => ({
  knob: a.knob,
  lo: String(a.lo),
  hi: String(a.hi),
  points: String(a.points),
  log: a.log,
});
const asAxis = (a: AxisText): BuildAxis => ({
  knob: a.knob,
  lo: a.lo.trim() === "" ? NaN : Number(a.lo),
  hi: a.hi.trim() === "" ? NaN : Number(a.hi),
  points: a.points.trim() === "" ? NaN : Number(a.points),
  log: a.log,
});

function AxisRow({
  label,
  axis,
  knobs,
  onKnob,
  onChange,
}: {
  label: string;
  axis: AxisText;
  knobs: readonly SchemaParamSpec[];
  onKnob: (knob: string) => void;
  onChange: (patch: Partial<AxisText>) => void;
}) {
  return (
    <div className="build-dialog-axis" role="group" aria-label={label}>
      <span className="build-dialog-label">{label}</span>
      <select aria-label={`${label} knob`} value={axis.knob} onChange={(e) => onKnob(e.target.value)}>
        {knobs.map((k) => (
          <option key={k.name} value={k.name}>
            {k.label}
          </option>
        ))}
      </select>
      <label>
        from
        <input
          type="number"
          aria-label={`${label} from`}
          value={axis.lo}
          onChange={(e) => onChange({ lo: e.target.value })}
        />
      </label>
      <label>
        to
        <input
          type="number"
          aria-label={`${label} to`}
          value={axis.hi}
          onChange={(e) => onChange({ hi: e.target.value })}
        />
      </label>
      <label>
        points
        <input
          type="number"
          aria-label={`${label} points`}
          min={BUILD_MIN_POINTS}
          max={BUILD_MAX_POINTS}
          step={1}
          value={axis.points}
          onChange={(e) => onChange({ points: e.target.value })}
        />
      </label>
      <label className="build-dialog-log">
        <input type="checkbox" checked={axis.log} onChange={(e) => onChange({ log: e.target.checked })} />
        log
      </label>
    </div>
  );
}

export function BuildAnalysisDialog({
  kind,
  knob,
  knobs,
  axisFor,
  taken,
  optRanges,
  onBuild,
  onClose,
}: BuildAnalysisDialogProps) {
  const other = (not: string) => knobs.find((k) => k.name !== not)?.name ?? not;
  const [x, setX] = useState<AxisText>(() => asText(axisFor(knob)));
  const [y, setY] = useState<AxisText>(() => asText(axisFor(other(knob))));
  const [objective, setObjective] = useState<HoldObjective>("resonance");
  const [held, setHeld] = useState<string[]>(() => [other(knob)]);
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = (k: string) => knobs.find((s) => s.name === k)?.label ?? k;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const draft: Build =
    kind === "map"
      ? { kind: "map", name: "", x: asAxis(x), y: asAxis(y) }
      : {
          kind: "hold",
          name: "",
          sweep: asAxis(x),
          objective,
          adjust: held,
          ranges: Object.fromEntries(held.flatMap((h) => (optRanges?.[h] ? [[h, optRanges[h]]] : []))),
        };
  // The name follows the choices until the viewer types one.
  const shownName = name ?? defaultBuildName(draft, label, taken);
  const build: Build = { ...draft, name: shownName };
  const problem =
    buildProblem(build, knobs) ?? (taken.has(shownName.trim()) ? "The picker lists that name already" : null);
  const want = HOLD_TARGETS.find((t) => t.objective === objective)?.knobs ?? 1;
  const candidates = knobs.filter((k) => k.name !== x.knob);
  const setTarget = (o: HoldObjective) => {
    setObjective(o);
    const n = HOLD_TARGETS.find((t) => t.objective === o)?.knobs ?? 1;
    setHeld((h) => {
      const pool = candidates.map((k) => k.name);
      const kept = h.filter((k) => pool.includes(k)).slice(0, n);
      for (const k of pool) if (kept.length < n && !kept.includes(k)) kept.push(k);
      return kept;
    });
  };
  const title = kind === "map" ? "Build a map" : "Build a held sweep";

  const go = () => {
    if (problem) return;
    setBusy(true);
    setError(null);
    onBuild(build).then(
      () => onClose(),
      (e: unknown) => {
        setBusy(false);
        setError(e instanceof Error ? e.message : String(e));
      },
    );
  };

  return (
    <div className="backend-config-overlay" onClick={onClose}>
      <div
        className="backend-config-modal keep-dialog build-dialog"
        role="dialog"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="backend-config-header">
          <strong>{title}</strong>
          <button className="backend-config-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="backend-config-body">
          {kind === "map" ? (
            <>
              <AxisRow
                label="x"
                axis={x}
                knobs={knobs}
                onKnob={(k) => setX(asText(axisFor(k)))}
                onChange={(p) => setX((a) => ({ ...a, ...p }))}
              />
              <AxisRow
                label="y"
                axis={y}
                knobs={knobs}
                onKnob={(k) => setY(asText(axisFor(k)))}
                onChange={(p) => setY((a) => ({ ...a, ...p }))}
              />
              <div className="keep-dialog-note">
                Coloured by |Γ| on the session&apos;s Z0, with X = 0 (resonance) drawn as a contour.
              </div>
            </>
          ) : (
            <>
              <AxisRow
                label="sweep"
                axis={x}
                knobs={knobs}
                onKnob={(k) => {
                  setX(asText(axisFor(k)));
                  setHeld((h) => (h.includes(k) ? h.map((v) => (v === k ? other(k) : v)) : h));
                }}
                onChange={(p) => setX((a) => ({ ...a, ...p }))}
              />
              <div className="build-dialog-axis" role="group" aria-label="hold">
                <span className="build-dialog-label">hold</span>
                <select
                  aria-label="hold target"
                  value={objective}
                  onChange={(e) => setTarget(e.target.value as HoldObjective)}
                >
                  {HOLD_TARGETS.map((t) => (
                    <option key={t.objective} value={t.objective}>
                      {t.label}
                    </option>
                  ))}
                </select>
                <span>by adjusting</span>
                {Array.from({ length: want }, (_, i) => (
                  <select
                    key={i}
                    aria-label={`held knob ${i + 1}`}
                    value={held[i] ?? ""}
                    onChange={(e) => setHeld((h) => h.map((v, j) => (j === i ? e.target.value : v)))}
                  >
                    {candidates.map((k) => (
                      <option key={k.name} value={k.name}>
                        {k.label}
                      </option>
                    ))}
                  </select>
                ))}
              </div>
              {held.map((h) => {
                const k = knobs.find((s) => s.name === h);
                return k ? (
                  <div key={h} className="keep-dialog-note" aria-label={`${k.label} range`}>
                    {holdRangeText(k, optRanges?.[h])}
                  </div>
                ) : null;
              })}
              <div className="keep-dialog-note">
                At every point the held knob is re-solved within that range (set it in the knob&apos;s Optimize
                menu); a point with no solution there is a gap. Drawn as R/X and the held knob against the swept
                one.
              </div>
            </>
          )}
          <label className="keep-dialog-field">
            <span>name</span>
            <input
              type="text"
              value={shownName}
              aria-label="The analysis's name"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          {problem && <div className="keep-dialog-note">{problem}</div>}
          {error && (
            <div className="keep-dialog-why" role="alert">
              {error}
            </div>
          )}
          <div className="keep-dialog-actions">
            <button
              type="button"
              className="zparam-reset"
              disabled={problem !== null || busy}
              title={problem ?? "List it in the picker as built here, and run it on the chart"}
              onClick={go}
            >
              {busy ? "building…" : "build and run"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
