import { backendSupportsGround, type Backend } from "./backends";
import type { GroundModel } from "./ground";
import type { BandSpec, ExampleDescriptor } from "./params";

// Sweep frequency plan: the log-spaced freq list `runSweep` requests.
// Sommerfeld ground stays at half resolution: momwire 0.7.0's C++ fill +
// grid cache made warm sweeps fast (~30 ms per point once the
// per-frequency grids are cached; measured 0.6 s for 21 points at 2
// threads), but the FIRST sweep after enabling it still fills one grid per
// point (measured 4.3 s for 21 points at 2 threads; 41 would be ~9 s) —
// half resolution halves that cold hit. Fast (reflection-coefficient)
// ground and momwire PEC ground are cheap enough for full resolution.
//
// Anchor + span come from the active example's sweep_policy (a variant can
// override it — see SweepPolicy in web/examples/_base.py). Anchor on the
// measurement frequency whenever the sweep should follow what the user is
// *viewing*: multiband designs declare anchor="meas_freq", and any design
// that's been unlocked from its design freq (to check the pattern on
// another band) should sweep that band too — not stay pinned to the
// design band. Locked single-resonance designs keep sweeping design_freq
// (where measFreq == designFreq anyway).
//
// Band-locked sweep: when the active band contains the anchor, snap the
// sweep range to that band's [min_mhz, max_mhz] so the trace stays inside
// the band the user is tuning instead of bleeding into adjacent ones.
// Falls through to the multiplicative window if the anchor sits outside
// every band.
export function planSweepFreqs(params: {
  backend: Backend;
  groundEnabled: boolean;
  groundModel: GroundModel;
  currentExample: ExampleDescriptor | undefined;
  currentVariant: string;
  measLocked: boolean;
  measFreq: number;
  designFreq: number;
  currentBands: BandSpec[];
  freqWindowCeiling: number;
}): number[] {
  const {
    backend,
    groundEnabled,
    groundModel,
    currentExample,
    currentVariant,
    measLocked,
    measFreq,
    designFreq,
    currentBands,
    freqWindowCeiling,
  } = params;
  const slowGround =
    backendSupportsGround(backend) &&
    groundEnabled &&
    groundModel === "sommerfeld";
  const N = slowGround ? 21 : 41;
  const policy =
    currentExample?.variant_ui?.[currentVariant]?.sweep_policy ??
    currentExample?.sweep_policy;
  const sweepAnchor =
    !measLocked || policy?.anchor === "meas_freq" ? measFreq : designFreq;
  let fLo: number;
  let fHi: number;
  const bandLocked = policy?.band_locked
    ? currentBands.find(
        (b) => sweepAnchor >= b.min_mhz && sweepAnchor <= b.max_mhz,
      )
    : undefined;
  if (bandLocked) {
    fLo = bandLocked.min_mhz;
    fHi = bandLocked.max_mhz;
  } else {
    fLo = Math.max(0.5, sweepAnchor * (policy?.lo_factor ?? 0.8));
    fHi = Math.min(freqWindowCeiling, sweepAnchor * (policy?.hi_factor ?? 1.25));
  }
  return Array.from({ length: N }, (_, i) =>
    Math.exp(Math.log(fLo) + (i / (N - 1)) * (Math.log(fHi) - Math.log(fLo))),
  );
}
