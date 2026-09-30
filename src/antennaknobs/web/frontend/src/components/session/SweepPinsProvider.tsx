import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";
import { type SweepPin, type SweepPinSnapshot, withPins } from "../../lib/sweepPins";
import { SweepPinsContext, type SweepPinsCtx } from "./contexts";

// The shell's pinned sweeps (AK#1757 item 1): App mounts this around every
// session, as it holds the pattern pins, so a pin outlives the design tab
// that made it. Memory only: never settings.toml, never a layout. The id
// counter is shell-level so ids stay unique whichever session mints them.
export function SweepPinsProvider({ children }: { children: ReactNode }) {
  const [pins, setPins] = useState<SweepPin[]>([]);
  const seq = useRef(0);
  const addPins = useCallback((snaps: SweepPinSnapshot[]) => {
    if (snaps.length === 0) return;
    // Ids minted before the state update: an updater may run twice (strict
    // mode), and must return the same pins both times.
    const ids = snaps.map(() => `sweep-pin-${seq.current++}`);
    setPins((ps) => {
      let k = 0;
      return withPins(ps, snaps, () => ids[k++]);
    });
  }, []);
  const removePin = useCallback((id: string) => {
    setPins((ps) => ps.filter((p) => p.id !== id));
  }, []);
  const togglePin = useCallback((id: string) => {
    setPins((ps) => ps.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p)));
  }, []);
  const ctx = useMemo<SweepPinsCtx>(
    () => ({ pins, addPins, removePin, togglePin }),
    [pins, addPins, removePin, togglePin],
  );
  return <SweepPinsContext.Provider value={ctx}>{children}</SweepPinsContext.Provider>;
}
