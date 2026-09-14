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

// A band the user types in for a frequency the design's band table does not
// cover (#1487), e.g. a 300 MHz dipole between 2 m and 70 cm. It has the same
// shape the adapter synthesizes for an out-of-band native freq (#390), built
// client-side from a centre and a span. Keys carry a prefix so they can never
// collide with a served band key.
export const CUSTOM_BAND_PREFIX = "custom:";

export function isCustomBand(key: string | null | undefined): boolean {
  return !!key && key.startsWith(CUSTOM_BAND_PREFIX);
}

// ±1.5 % of the centre: the window the adapter gives a synthetic band.
export function defaultCustomSpan(centerMhz: number): number {
  return Number((0.03 * centerMhz).toPrecision(3));
}

export function customBandSpec(centerMhz: number, spanMhz: number): BandSpec {
  return {
    key: `${CUSTOM_BAND_PREFIX}${centerMhz}:${spanMhz}`,
    label: `custom ${Number(centerMhz.toFixed(3))} MHz`,
    freq_mhz: centerMhz,
    min_mhz: centerMhz - spanMhz / 2,
    max_mhz: centerMhz + spanMhz / 2,
  };
}

// Why a centre/span pair cannot make a band, or null when it can.
export function customBandError(centerMhz: number, spanMhz: number): string | null {
  if (!Number.isFinite(centerMhz) || centerMhz <= 0) {
    return "centre must be a positive frequency";
  }
  if (!Number.isFinite(spanMhz) || spanMhz <= 0) return "span must be positive";
  if (spanMhz >= 2 * centerMhz) return "span must be less than twice the centre";
  return null;
}
