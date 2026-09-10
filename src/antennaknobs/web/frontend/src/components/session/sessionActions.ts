import type { MeasuredData, SolveRequest } from "../../lib/api";

// Imperative one-shot session actions lifted out of DesignSession (#642 seam
// 5b-3). Deliberately plain async functions, not hooks: each one runs entirely
// on a user gesture and touches no React state of its own, so it takes the
// handful of setters / builders it needs as arguments and the component keeps
// owning them.

// Export the current design as a .nec card deck and trigger a browser
// download. The backend reuses the same builder construction as the live
// solve, so the deck matches what's on screen.
//
// `dialect` picks NEC-2 or NEC-5 (issue #1389). BOTH items are always offered,
// whatever engines are installed: neither writer needs one, and the person who
// most needs the file is the one without the engine on this machine. What varies
// is whether the DESIGN can be said in that dialect — a buried, ground-contact
// or graded design comes back 422 from nec2 with a sentence pointing at the
// nec5 download, and a TL / virtual-driver network comes back 422 from both.
// Surface the server's message rather than downloading an error page.
export async function downloadNec({
  setGearMenuOpen,
  buildRequest,
  geometry,
  dialect = "nec2",
}: {
  setGearMenuOpen: (open: boolean) => void;
  buildRequest: () => SolveRequest;
  geometry: string;
  dialect?: "nec2" | "nec5";
}) {
  setGearMenuOpen(false);
  try {
    const resp = await fetch("/export_nec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...buildRequest(), dialect }),
    });
    if (!resp.ok) {
      let detail = `NEC export failed (${resp.status}).`;
      try {
        detail = (await resp.json()).detail ?? detail;
      } catch {
        /* non-JSON error body — keep the status-based message */
      }
      window.alert(detail);
      return;
    }
    const blob = await resp.blob();
    const cd = resp.headers.get("Content-Disposition") ?? "";
    const m = cd.match(/filename="([^"]+)"/);
    const fallbackExt = dialect === "nec5" ? ".nec5.nec" : ".nec";
    const filename = m
      ? m[1]
      : `${geometry.replace(/\./g, "_") || "antenna"}${fallbackExt}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    window.alert(`NEC export failed: ${e}`);
  }
}

// Load a measured VNA sweep (.s1p) for the measured-vs-modeled overlay.
// The file is read in the browser and posted as text: the server owns the
// Touchstone parsing (one reader, shared with the CLI), and because the
// *file* stays local, this works the same whether the backend is on this
// machine or across a tunnel.
export async function loadMeasured(
  file: File,
  {
    setGearMenuOpen,
    setMeasured,
  }: {
    setGearMenuOpen: (open: boolean) => void;
    setMeasured: (data: MeasuredData) => void;
  },
) {
  setGearMenuOpen(false);
  try {
    const text = await file.text();
    const resp = await fetch("/measured", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: file.name, text }),
    });
    if (!resp.ok) {
      let detail = `Could not read ${file.name} (${resp.status}).`;
      try {
        detail = (await resp.json()).detail ?? detail;
      } catch {
        /* non-JSON error body — keep the status-based message */
      }
      window.alert(detail);
      return;
    }
    setMeasured(await resp.json());
  } catch (e) {
    window.alert(`Could not read ${file.name}: ${e}`);
  }
}

// Copy the current knob values as a paste-ready Python `default_params`
// (or `<variant>_params`) block. Replaces the old workflow of hand-copying
// the values printed on screen back into a design file. The backend reuses
// the same variant + live-knob overlay as the solve, so what you copy is
// exactly the antenna on screen.
export async function copyParams({
  buildRequest,
  setCopiedParams,
}: {
  buildRequest: () => SolveRequest;
  setCopiedParams: (copied: boolean) => void;
}) {
  try {
    const resp = await fetch("/params_source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequest()),
    });
    const data = await resp.json();
    if (!resp.ok || data.available === false || data.error) {
      window.alert(data.error ?? "Copy params is unavailable for this design.");
      return;
    }
    const src: string = data.source;
    try {
      await navigator.clipboard.writeText(src);
      setCopiedParams(true);
      window.setTimeout(() => setCopiedParams(false), 1500);
    } catch {
      // Clipboard API blocked (e.g. insecure context) — fall back to a
      // prompt the user can copy from by hand.
      window.prompt("Copy these params:", src);
    }
  } catch (e) {
    window.alert(`Copy params failed: ${e}`);
  }
}
