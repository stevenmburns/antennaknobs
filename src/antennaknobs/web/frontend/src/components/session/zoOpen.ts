// Opening the reference impedance from where it is shown (AK#1985).
//
// Jeff G8HUL looked for Zo on the Smith chart and the SWR readout and never
// found it in the optimizer's menu. The session provides this; the Smith
// chart's "Z₀ = …" corner and the readout's SWR row call it to open the top
// gear menu at the field. Absent (no session): those stay plain text.
import { createContext, useContext } from "react";

export const ZoOpenContext = createContext<(() => void) | null>(null);

export function useZoOpen(): (() => void) | null {
  return useContext(ZoOpenContext);
}
