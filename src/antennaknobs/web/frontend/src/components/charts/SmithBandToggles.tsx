import { fmtFreq } from "../../lib/optBands";
import { feedColor } from "./palette";

/** The band list's bands, for showing their Z on the Smith chart while a knob
 *  turns: the list itself (read-only here; it is edited in the optimize
 *  menu), which are shown, and the setter. */
export type SmithBandPicker = {
  freqs: number[];
  shown: number[];
  setShown: (freqs: number[]) => void;
  /** A band's name where the design declares one ("40 m"), by its
   *  frequency (`operating_bands`, AK#2108); the frequency is shown
   *  otherwise. */
  labels?: ReadonlyMap<number, string>;
};

// One toggle per band, on the chart, in its marker's colour (Steve,
// 2026-10-28): only some bands matter for the knob in hand, so showing one is
// a click where the markers are, not a trip into the optimize menu. Each band
// shown is one more solve per knob change, so none starts on.
export function SmithBandToggles({ picker }: { picker: SmithBandPicker }) {
  if (picker.freqs.length === 0) return null;
  return (
    <div className="smith-band-toggles" role="group" aria-label="Bands on the Smith chart">
      {picker.freqs.map((f, i) => {
        const on = picker.shown.includes(f);
        const color = feedColor(i, 0.95);
        const name = picker.labels?.get(f);
        return (
          <button
            key={f}
            type="button"
            className={`smith-band-toggle${on ? " is-on" : ""}`}
            aria-pressed={on}
            title={
              on
                ? `Stop showing ${name ? `${name}, ` : ""}${fmtFreq(f)} MHz`
                : `Show ${name ? `${name}, ` : ""}${fmtFreq(f)} MHz here as you turn knobs (one more solve per change)`
            }
            onClick={() =>
              picker.setShown(on ? picker.shown.filter((g) => g !== f) : [...picker.shown, f])
            }
          >
            <span
              className="smith-band-swatch"
              aria-hidden="true"
              style={{ borderColor: color, background: on ? color : "transparent" }}
            />
            {name ?? fmtFreq(f)}
          </button>
        );
      })}
    </div>
  );
}
