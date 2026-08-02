import type { BandSpec } from "./params";

// Ceiling for anchor-derived frequency windows (the unlocked meas-freq
// VFO and un-band-locked sweeps). Historically a hardcoded 60 MHz — an
// HF-era bound that survived the 2m/70cm band additions (#497) and
// then INVERTED the VFO range on VHF designs (anchor 146: min 116.8 >
// max 60, so touching the knob clamped it to 60 MHz). Derive it from
// the design's own band table instead, keeping 60 as the floor so
// bandless/HF-only designs behave exactly as before.
export function freqWindowCeiling(bands: BandSpec[]): number {
  return Math.max(60, ...bands.map((b) => b.max_mhz * 1.25));
}

// Which band (if any) contains frequency `f` — drives the active-tab
// highlight on the meas-band selector. Falls outside any band → no tab
// highlighted.
export function bandContaining(bands: BandSpec[], f: number): string | null {
  for (const b of bands) {
    if (f >= b.min_mhz && f <= b.max_mhz) return b.key;
  }
  return null;
}
