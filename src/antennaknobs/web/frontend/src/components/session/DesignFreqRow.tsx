import { BandDropdown } from "../params/BandDropdown";
import type { BandSpec } from "../../lib/params";

// Highlight the band whose window contains the current designFreq — same
// behaviour as the meas-freq row. The slider min/max also tracks that band,
// so sliding past its edge auto-re-anchors to the neighbouring band. The
// caller gates this on has_design_freq so the row is hidden for hand-tuned
// absolute designs where the slider would do nothing.
export function DesignFreqRow({
  bands,
  designFreq,
  activeKey,
  onSelectBand,
  onSetFreq,
  onCustomBand,
}: {
  bands: BandSpec[];
  designFreq: number;
  activeKey: string | null;
  onSelectBand: (key: string) => void;
  onSetFreq: (v: number) => void;
  /** "Custom…" in the band picker (#1487): a band at any centre and span. */
  onCustomBand?: (centerMhz: number, spanMhz: number) => void;
}) {
  const active = bands.find((b) => b.key === activeKey) ?? bands[0];
  return (
    <div className="field">
      <label>
        <span>design freq</span>
        <span>{designFreq.toFixed(3)} MHz</span>
      </label>
      <div className="band-row">
        <BandDropdown
          bands={bands}
          value={active.key}
          onSelect={onSelectBand}
          ariaLabel="band"
          onCustom={onCustomBand}
          customSeedMhz={designFreq}
        />
        <input
          type="range"
          aria-label="design frequency"
          min={active.min_mhz}
          max={active.max_mhz}
          step={0.005}
          value={designFreq}
          onInput={(e) =>
            onSetFreq(Number((e.target as HTMLInputElement).value))
          }
        />
      </div>
    </div>
  );
}
