import { KnobMenuNumber } from "../backend/fields";
import type { KnobOpt, SchemaParamSpec } from "../../lib/params";

// Per-knob optimiser menu (right-click a knob): vary toggle + extents + turn
// step. Position-fixed at the click point.
export function KnobOptMenu({
  menu,
  spec,
  ko,
  onPatch,
  onClose,
}: {
  menu: { name: string; x: number; y: number };
  spec: SchemaParamSpec | undefined;
  ko: KnobOpt;
  onPatch: (patch: Partial<KnobOpt>) => void;
  onClose: () => void;
}) {
  const name = menu.name;
  const s = spec;
  const num = (v: number) => (Number.isFinite(v) ? v : 0);
  const set = (patch: Partial<KnobOpt>) => onPatch(patch);
  return (
    <>
      <div
        className="knob-menu-backdrop"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault();
          onClose();
        }}
      />
      <div
        className="knob-menu"
        style={{ left: menu.x, top: menu.y }}
        onContextMenu={(e) => e.preventDefault()}
      >
        <div className="knob-menu-title">{s?.label ?? name}</div>
        <label className="knob-menu-vary">
          <input
            type="checkbox"
            checked={ko.vary}
            onChange={(e) => set({ vary: e.target.checked })}
          />
          Optimize this knob
          <kbd
            className="knob-menu-kbd"
            title="Focus a knob and press O to toggle"
          >
            O
          </kbd>
        </label>
        <div className="knob-menu-row">
          <span>Optimize range</span>
          <KnobMenuNumber
            value={num(ko.optMin)}
            onChange={(v) => set({ optMin: v })}
          />
          <KnobMenuNumber
            value={num(ko.optMax)}
            onChange={(v) => set({ optMax: v })}
          />
        </div>
        <div className="knob-menu-row">
          <span>Display range</span>
          <KnobMenuNumber
            value={num(ko.dispMin)}
            onChange={(v) => set({ dispMin: v })}
          />
          <KnobMenuNumber
            value={num(ko.dispMax)}
            onChange={(v) => set({ dispMax: v })}
          />
        </div>
        <div className="knob-menu-row">
          <span>Turn step</span>
          <KnobMenuNumber
            value={num(ko.step)}
            onChange={(v) => set({ step: v })}
          />
        </div>
      </div>
    </>
  );
}
