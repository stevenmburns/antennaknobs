import { backendSupportsGround, backendSupportsTerrain } from "../../lib/backends";
import type { BackendEntry } from "../../lib/backends";
import type {
  FiniteGroundMethod,
  GroundType,
  TerrainParams,
  TerrainPresetSchema,
} from "../../lib/ground";
import { NumberField } from "../backend/fields";

export function GroundPanel({
  backend,
  groundEnabled,
  setGroundEnabled,
  groundType,
  setGroundType,
  finiteGroundMethod,
  setFiniteGroundMethod,
  terrainPresets,
  terrainPreset,
  setTerrainPreset,
  terrainParams,
  setTerrainParams,
  groundRequirement = null,
}: {
  backend: BackendEntry;
  groundEnabled: boolean;
  setGroundEnabled: (v: boolean) => void;
  groundType: GroundType;
  setGroundType: (v: GroundType) => void;
  finiteGroundMethod: FiniteGroundMethod;
  setFiniteGroundMethod: (v: FiniteGroundMethod) => void;
  terrainPresets: TerrainPresetSchema[];
  terrainPreset: string;
  setTerrainPreset: (v: string) => void;
  terrainParams: TerrainParams;
  setTerrainParams: (fn: (p: TerrainParams) => TerrainParams) => void;
  /** The active design's required ground model ("sommerfeld" for the
   *  buried-wire designs), or null. Renders the auto-selection notice —
   *  the selection itself is DesignSession's ground-requirement effect. */
  groundRequirement?: string | null;
}) {
  return (
    <>
      {!backendSupportsGround(backend) && groundEnabled && (
        <div className="field" title="This backend doesn't model ground; ignored until you switch to one that does.">
          <em style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>
            ground plane ignored for {backend.label}
          </em>
        </div>
      )}

      {groundRequirement === "sommerfeld" && (
        <div
          className="field"
          title="This design puts conductors below the surface, which only exist under a Sommerfeld half-space — the reflection-coefficient approximation refuses them by name. Selected automatically when the design loaded; you can still change it, but the solver will refuse anything else."
        >
          <em style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>
            buried design — Sommerfeld ground selected automatically
          </em>
        </div>
      )}

      <div className="field">
        <label
          className="link-toggle"
          title="Ground plane at z=0; pick the ground model below"
        >
          <input
            type="checkbox"
            checked={groundEnabled}
            disabled={!backendSupportsGround(backend)}
            onChange={(e) => setGroundEnabled(e.target.checked)}
          />
          ground plane
        </label>
        {backendSupportsGround(backend) && groundEnabled && (
          <>
            <div role="radiogroup" aria-label="Ground type">
              {(
                [
                  [
                    "finite",
                    "finite (εr=10, σ=0.002 S/m)",
                    "Finite ground — pick the solve method below (Sommerfeld-Norton or the reflection-coefficient approximation).",
                  ],
                  [
                    "pec",
                    "PEC",
                    backend.name === "pynec"
                      ? "Perfectly conducting ground (image method, NEC ITYPE=1) — matches every backend's model='PEC' for apples-to-apples engine comparison."
                      : "Perfectly conducting ground (image method) — matches PyNEC's PEC model for apples-to-apples engine comparison.",
                  ],
                  ...(backendSupportsTerrain(backend) &&
                  terrainPresets.length > 0
                    ? [
                        [
                          "terrain",
                          "terrain",
                          "Faceted terrain (levee or cliff preset): impedance solves Sommerfeld on the crest medium; the far field reflects off the facet each ray's specular point lands on — tilted incidence, per-facet media, full effective height below the drops.",
                        ] as [GroundType, string, string],
                      ]
                    : []),
                ] as [GroundType, string, string][]
              ).map(([value, label, title]) => (
                <label key={value} className="link-toggle" title={title}>
                  <input
                    type="radio"
                    name="ground-type"
                    checked={groundType === value}
                    onChange={() => setGroundType(value)}
                  />
                  {label}
                </label>
              ))}
            </div>
            {groundType === "finite" && (
                <div
                  role="radiogroup"
                  aria-label="Finite-ground solve method"
                  style={{ marginLeft: "1.2em" }}
                >
                  {(
                    [
                      [
                        "fast",
                        "refl-coef (fast)",
                        backend.name === "pynec"
                          ? "Reflection-coefficient approximation (NEC ITYPE=0), the default. ~2x faster per solve; impedance degrades below ~0.1λ height."
                          : backend.name === "nec5"
                            ? "NEC-5 has no reflection-coefficient model (its IPERF 0 is full Sommerfeld) — this choice is served by the full Sommerfeld solve, and the applied-model readout says so."
                            : "Reflection-coefficient model, the default. Fast; matches Sommerfeld above ~0.1λ heights.",
                      ],
                      [
                        "sommerfeld",
                        "Sommerfeld",
                        backend.name === "pynec"
                          ? "Sommerfeld-Norton (NEC ITYPE=2) — most accurate, slowest; the impedance sweep drops to half resolution to compensate."
                          : "True Sommerfeld ground — accurate at any height, on every momwire solver including the fast array paths (momwire ≥ 0.8.0). First solve at each frequency builds a grid (seconds); repeats are fast. The impedance sweep runs at half resolution.",
                      ],
                    ] as [FiniteGroundMethod, string, string][]
                  ).map(([value, label, title]) => (
                    <label key={value} className="link-toggle" title={title}>
                      <input
                        type="radio"
                        name="ground-method"
                        checked={finiteGroundMethod === value}
                        onChange={() => setFiniteGroundMethod(value)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              )}
            {groundType === "terrain" &&
              backendSupportsTerrain(backend) &&
              terrainPresets.length > 0 &&
              (() => {
                // Whole panel driven by the /capabilities schema (issue
                // #560): radio list, per-preset knobs and media note all
                // come from terrainPresets. Fall back to the first preset if
                // the parked name is absent (a server-side rename).
                const activePreset =
                  terrainPresets.find((p) => p.name === terrainPreset) ??
                  terrainPresets[0];
                return (
                  <div style={{ marginLeft: "1.2em" }}>
                    <div role="radiogroup" aria-label="Terrain preset">
                      {terrainPresets.map((p) => (
                        <label
                          key={p.name}
                          className="link-toggle"
                          title={p.tooltip}
                        >
                          <input
                            type="radio"
                            name="terrain-preset"
                            checked={activePreset.name === p.name}
                            onChange={() => setTerrainPreset(p.name)}
                          />
                          {p.label}
                        </label>
                      ))}
                    </div>
                    {activePreset.fields.map((f) => (
                      <NumberField
                        key={f.key}
                        label={f.unit ? `${f.label} (${f.unit})` : f.label}
                        value={terrainParams[f.key] ?? f.default}
                        min={f.min}
                        max={f.max}
                        step={f.step}
                        onChange={(v) =>
                          setTerrainParams((p) => ({ ...p, [f.key]: v }))
                        }
                      />
                    ))}
                    <div
                      style={{ fontSize: "0.85em", opacity: 0.65 }}
                      title="Media are fixed in this version; the geometry knobs above are the live parameters."
                    >
                      {activePreset.media_note}
                    </div>
                  </div>
                );
              })()}
          </>
        )}
      </div>
    </>
  );
}
