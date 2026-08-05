import type { CSSProperties } from "react";
import {
  applyVisibility,
  isGroup,
  type KnobLayout,
  type KnobOpt,
  type ParamValueBag,
  type SchemaItem,
  type SchemaParamSpec,
} from "../../lib/params";
import { Knob } from "./Knob";

// Translate a knob's optional layout hint into inline grid-placement
// styles. Returns undefined when nothing is set so auto-flow fields stay
// untouched. `col_span` / `row_span` use the CSS `span N` form; an explicit
// `col` / `row` pins the start line (1-indexed). `col` + `col_span`
// together place a spanning field at a fixed column.
function layoutStyle(layout?: KnobLayout | null): CSSProperties | undefined {
  if (!layout) return undefined;
  const style: CSSProperties = {};
  const colStart = layout.col ?? null;
  const rowStart = layout.row ?? null;
  const colSpan = layout.col_span ?? null;
  const rowSpan = layout.row_span ?? null;
  if (colStart != null) {
    style.gridColumn = colSpan != null ? `${colStart} / span ${colSpan}` : `${colStart}`;
  } else if (colSpan != null) {
    style.gridColumn = `span ${colSpan}`;
  }
  if (rowStart != null) {
    style.gridRow = rowSpan != null ? `${rowStart} / span ${rowSpan}` : `${rowStart}`;
  } else if (rowSpan != null) {
    style.gridRow = `span ${rowSpan}`;
  }
  return Object.keys(style).length ? style : undefined;
}

export function ParamForm({
  schema,
  values,
  onChange,
  pathPrefix = [],
  disabledFields,
  opt,
}: {
  schema: SchemaItem[];
  values: ParamValueBag;
  onChange: (path: (string | number)[], value: number | string | boolean) => void;
  pathPrefix?: (string | number)[];
  // Param names that should render as disabled even though they're
  // visible in the schema — e.g. to grey out a control whose effect
  // depends on the active backend. Currently unused (kept as a general
  // mechanism); daisy_chain used to rely on it before build_network()
  // made the single-feed hexbeam engine-agnostic.
  disabledFields?: Set<string> | undefined;
  // Optimiser integration (top-level rail only). `settings` overrides a knob's
  // effective min/max/step; `onContext` opens that knob's right-click menu;
  // `onToggleVary` flips a knob's "Optimize this knob" flag (the `o` shortcut,
  // parallel to the menu checkbox).
  opt?: {
    settings: Record<string, KnobOpt>;
    onContext: (name: string, e: React.MouseEvent) => void;
    onToggleVary: (name: string) => void;
  };
}) {
  return (
    <>
      {schema.map((item) => {
        if (isGroup(item)) {
          const countRaw = values[item.repeat_count];
          const count = typeof countRaw === "number" ? Math.round(countRaw) : 0;
          const instances = values[item.name];
          if (!Array.isArray(instances)) return null;
          return (
            <div key={item.name} className="param-group">
              {Array.from({ length: Math.min(count, instances.length) }, (_, i) => (
                <div key={`${item.name}-${i}`} className="param-group-instance">
                  <div className="param-group-header">
                    {item.label_template.replace("{i}", String(i))}
                  </div>
                  {/* Wrap the band's controls in their own .param-grid so they
                      pack 3-across just like the top-level rail. Without this
                      the nested ParamForm block-stacks one control per row. */}
                  <div className="param-grid is-knobs">
                    <ParamForm
                      schema={item.params}
                      values={instances[i]}
                      onChange={onChange}
                      pathPrefix={[...pathPrefix, item.name, i]}
                      disabledFields={disabledFields}
                    />
                  </div>
                </div>
              ))}
            </div>
          );
        }
        // Scalar leaf.
        if (!applyVisibility(item, values)) return null;
        const currentRaw = values[item.name];
        const currentNum =
          typeof currentRaw === "number" ? currentRaw : Number(item.default);
        const currentStr =
          typeof currentRaw === "string" ? currentRaw : String(item.default);

        // Resolve dynamic min/max from a sibling enum's currently-
        // selected option, when configured. Falls back to the static
        // min/max if the lookup misses.
        let effMin = item.min ?? 0;
        let effMax = item.max ?? 1;
        const rfe = item.range_from_enum_option;
        if (rfe) {
          const siblingVal = values[rfe.param];
          const siblingSchema = schema.find(
            (s) => !isGroup(s) && s.name === rfe.param,
          ) as SchemaParamSpec | undefined;
          const opts = siblingSchema?.enum_options;
          if (opts && typeof siblingVal === "string") {
            const opt = opts.find((o) => o.value === siblingVal);
            if (opt) {
              const lo = opt[rfe.min_key];
              const hi = opt[rfe.max_key];
              if (typeof lo === "number") effMin = lo;
              if (typeof hi === "number") effMax = hi;
            }
          }
        }

        if (item.kind === "bool") {
          const checked = Boolean(currentRaw ?? item.default);
          const isDisabled = disabledFields?.has(item.name) ?? false;
          return (
            <div key={item.name} className="field field-bool" style={layoutStyle(item.layout)}>
              <label
                className={`field-bool-label${isDisabled ? " field-disabled" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={isDisabled}
                  onChange={(e) =>
                    onChange(
                      [...pathPrefix, item.name],
                      (e.target as HTMLInputElement).checked,
                    )
                  }
                />
                <span>{item.label}</span>
              </label>
            </div>
          );
        }

        if (item.kind === "enum") {
          const opts = item.enum_options ?? [];
          return (
            <div key={item.name} className="field field-enum" style={layoutStyle(item.layout)}>
              <label>
                <span>{item.label}</span>
              </label>
              <select
                value={currentStr}
                onChange={(e) => {
                  const next = (e.target as HTMLSelectElement).value;
                  onChange([...pathPrefix, item.name], next);
                  // On-change side effect: set a sibling's value to a
                  // key from the new enum option. Fan_dipole uses this
                  // to snap freq to the band's default.
                  const oc = item.on_change_set;
                  if (oc) {
                    const opt = opts.find((o) => o.value === next);
                    if (opt) {
                      const k = opt[oc.from_enum_key];
                      if (typeof k === "number" || typeof k === "string") {
                        onChange([...pathPrefix, oc.set], k);
                      }
                    }
                  }
                }}
              >
                {opts.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          );
        }

        const shown =
          item.kind === "int"
            ? String(Math.round(currentNum))
            : currentNum.toFixed(item.precision);
        // Every float/int param is a rotary knob: label on top, dial in the
        // middle, value on the bottom. (The slider alternative and its toggle
        // were retired — knobs are the brand.)
        // Per-knob optimiser override: display extents + manual step come from
        // the knob's menu when set, and `vary` marks it a free variable.
        const ko = opt?.settings[item.name];
        const knobMin = ko ? ko.dispMin : effMin;
        const knobMax = ko ? ko.dispMax : effMax;
        const knobStep = ko?.step ?? item.step ?? 0.001;
        return (
          <div
            key={item.name}
            className={`field field-knob${ko?.vary ? " is-opt-var" : ""}`}
            style={layoutStyle(item.layout)}
            onContextMenu={opt ? (e) => opt.onContext(item.name, e) : undefined}
            // `o` toggles this knob's "Optimize this knob" flag while it's
            // focused — the keyboard parallel to the right-click menu. The event
            // bubbles up from the focused role="slider" Knob; the edit <input>
            // stops propagation, so typing a value never triggers it. Ignore it
            // when a modifier is held (reserved for other shortcuts) or on
            // auto-repeat (holding the key mustn't flip-flop the flag).
            onKeyDown={
              opt
                ? (e) => {
                    if (
                      e.key.toLowerCase() === "o" &&
                      !e.ctrlKey &&
                      !e.metaKey &&
                      !e.altKey &&
                      !e.repeat
                    ) {
                      e.preventDefault();
                      opt.onToggleVary(item.name);
                    }
                  }
                : undefined
            }
          >
            <span
              className="knob-label"
              title={item.name === item.label ? item.label : `${item.label} · param: ${item.name}`}
            >
              {item.label}
            </span>
            <Knob
              knobId={[...pathPrefix, item.name].join(".")}
              value={currentNum}
              min={knobMin}
              max={knobMax}
              step={knobStep}
              precision={item.kind === "int" ? 0 : item.precision}
              unit={item.unit}
              label={item.label}
              onChange={(v) => onChange([...pathPrefix, item.name], v)}
            />
            <span className="knob-value">{shown}{item.unit ?? ""}</span>
          </div>
        );
      })}
    </>
  );
}
