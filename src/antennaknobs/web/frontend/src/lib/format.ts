import type { FeedEntry } from "./api";

export function formatScalar(raw: unknown, precision: number, unit: string | null): string {
  return typeof raw === "number" ? `${raw.toFixed(precision)}${unit ?? ""}` : "—";
}

export function reflectionCoefficient(r: number, x: number, z0: number) {
  // Γ = (Z - Z0) / (Z + Z0), with Z = r + jx (Z0 real).
  const denom = (r + z0) * (r + z0) + x * x;
  const gRe = (r * r - z0 * z0 + x * x) / denom;
  const gIm = (2 * x * z0) / denom;
  return { gRe, gIm, gMag: Math.hypot(gRe, gIm) };
}

export function formatOhms(v: number): string {
  // The server clamps an open-circuited feed (e.g. a series matchbox
  // capacitor slider at 0 pF) to a 1e9 Ω sentinel — JSON has no Infinity.
  // Anything that large is physically an open, not a number worth printing.
  if (Math.abs(v) >= 1e8) return "∞ (open)";
  return `${v.toFixed(2)} Ω`;
}

export function formatSwr(r: number, x: number, z0: number): string {
  const { gMag } = reflectionCoefficient(r, x, z0);
  if (gMag >= 0.9999) return "∞";
  const swr = (1 + gMag) / (1 - gMag);
  if (swr > 99) return swr.toFixed(0);
  return swr.toFixed(2);
}

// Nice-number lengths for the zoomed scale bar: pick the readable unit and
// trim float dust (5×10⁻³ m × 1000 → "5 mm", not "5.000000000000001 mm").
export function formatMetres(v: number): string {
  const fmt = (x: number, unit: string) => `${parseFloat(x.toPrecision(2))} ${unit}`;
  if (v >= 1) return fmt(v, "m");
  if (v >= 0.01) return fmt(v * 100, "cm");
  return fmt(v * 1000, "mm");
}

// One feed's drive for the per-feed table (AK#1657): "1.414 A ∠−90°" where
// the server says whether it is volts or amps, else the phase alone. A bare
// magnitude with no unit is exactly the reading this column exists to stop.
export function feedDriveText(f: FeedEntry): string {
  const phase = Math.round((Math.atan2(f.v_im, f.v_re) * 180) / Math.PI);
  const angle = `∠${phase < 0 ? "−" : ""}${Math.abs(phase)}°`;
  if (!f.drive_unit) return angle;
  const mag = Number(Math.hypot(f.v_re, f.v_im).toPrecision(4));
  return `${mag} ${f.drive_unit} ${angle}`;
}
