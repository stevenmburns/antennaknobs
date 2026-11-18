// Opening the reference impedance from where it is shown (AK#1985).
//
// Jeff G8HUL looked for Zo on the Smith chart and the SWR readout and never
// found it in the optimizer's menu. The session provides this; the Smith
// chart's "Z₀ = …" corner and the readout's SWR row call it to open the top
// gear menu at the field. Absent (no session): those stay plain text.
import { createContext, useContext } from "react";
import { formatZo } from "../../lib/zoOverride";

export const ZoOpenContext = createContext<(() => void) | null>(null);

export function useZoOpen(): (() => void) | null {
  return useContext(ZoOpenContext);
}

// The design's own Zo while the session measures against another (AK#2116),
// else null. A gear-menu override persists per design with no expiry, so a
// reference that is not the design's must say so wherever it is shown. The
// session derives it with ZoField's test, `zo.value !== zo.design`. A number,
// not an object, so the provider needs no memo to stay stable. Absent (no
// session): nothing is marked.
export const ZoOverriddenContext = createContext<number | null>(null);

export function useZoOverriddenFrom(): number | null {
  return useContext(ZoOverriddenContext);
}

/** The "Overridden" marker's tooltip: what the design itself names. */
export function zoOverriddenTitle(design: number): string {
  return `Design's own: ${formatZo(design)} Ω. Click to change or reset.`;
}
