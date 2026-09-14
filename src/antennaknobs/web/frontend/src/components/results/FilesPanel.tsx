import { useEffect, useState } from "react";
import type { DesignSource, EngineIo } from "../../lib/api";

// The Files view (AK#1428): what the design was written as and, when the solve
// on screen ran through an external engine's binary, the deck that engine was
// given and the report it printed. Three tabs over one monospace pane, each
// with Copy and Download.
//
// The Deck and Output tabs show only texts a binary actually ran on. A solver
// that runs none gets a sentence saying so, never the export writer's deck,
// which is not what any engine was given. Whether a solve left texts behind,
// and what to call their engine, is served: this file names no engine
// (#1006 G2-6).
export type FilesViewData = {
  geometry: string;
  /** The served name of the engine behind the texts, or null when the solve
   *  on screen ran no binary. */
  engine: string | null;
  /** A solve of this design is on screen, or texts from an earlier one are. */
  solved: boolean;
  source: DesignSource | null;
  engineIo: EngineIo | null;
  /** The engine texts belong to an earlier solve than the one on screen. */
  stale: boolean;
};

type Tab = "source" | "deck" | "output";

type Pane =
  | { text: string; filename: string; message?: undefined }
  | { text?: undefined; filename?: undefined; message: string };

function saveText(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function FilesPanel({
  data,
  size,
  fill,
}: {
  data: FilesViewData | null;
  size: number;
  fill: boolean;
}) {
  const [tab, setTab] = useState<Tab>("source");
  const [runPick, setRunPick] = useState(0);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);

  if (!fill || !data) {
    // The thumbnail carries no texts (its call site passes none); a label is
    // all a 96 px square can say about a file.
    return (
      <div
        className={fill ? "files-fill" : "files-thumb"}
        style={fill ? undefined : { width: size, height: size }}
      >
        <div className="files-empty">Source · engine deck · engine output</div>
      </div>
    );
  }

  const engine = data.engine;
  const runs = data.engineIo?.runs ?? [];
  const runIdx = Math.min(runPick, Math.max(0, runs.length - 1));
  const run = runs[runIdx];
  const base = data.geometry.replace(/\./g, "_") || "antenna";

  const pane = ((): Pane => {
    if (tab === "source") {
      if (!data.source) return { message: "Loading the design's source…" };
      if (!data.source.available) {
        return { message: "This design has no source file to show." };
      }
      return { text: data.source.text, filename: data.source.filename };
    }
    if (engine === null) {
      if (!data.solved) return { message: "Waiting for a solve…" };
      return {
        message:
          "This solver runs no external program, so there is no deck or " +
          "printout. Pick a solver slot that runs one to see the deck it was " +
          "given and what it printed.",
      };
    }
    if (!data.engineIo) return { message: `Fetching the ${engine} ${tab}…` };
    if (!run) return { message: data.engineIo.error ?? `No ${engine} run to show.` };
    const which = runs.length > 1 ? `_run${runIdx + 1}` : "";
    return {
      text: tab === "deck" ? run.deck : run.printout,
      filename: `${base}_${data.engineIo.solver}${which}.${tab === "deck" ? "nec" : "out"}`,
    };
  })();

  const engineTab = tab !== "source" && engine !== null;
  const tabs: [Tab, string][] = [
    ["source", data.source?.available ? data.source.filename : "Source"],
    ["deck", `${engine ?? "Engine"} deck`],
    ["output", `${engine ?? "Engine"} output`],
  ];
  return (
    <div className="files-fill">
      <div className="files-bar">
        <div className="files-tabs" role="tablist" aria-label="Files">
          {tabs.map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              className={`files-tab${tab === id ? " active" : ""}`}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        {engineTab && runs.length > 1 && (
          <select
            className="files-run"
            aria-label="Engine run"
            value={runIdx}
            onChange={(e) => setRunPick(Number(e.target.value))}
          >
            {runs.map((_r, i) => (
              <option key={i} value={i}>{`run ${i + 1} of ${runs.length}`}</option>
            ))}
          </select>
        )}
        {pane.text !== undefined && (
          <div className="files-actions">
            <button
              className="files-action"
              onClick={() => {
                void navigator.clipboard
                  ?.writeText(pane.text)
                  .then(() => setCopied(true))
                  .catch(() => {});
              }}
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              className="files-action"
              title={`Save as ${pane.filename}`}
              onClick={() => saveText(pane.text, pane.filename)}
            >
              Download
            </button>
          </div>
        )}
      </div>
      {engineTab && run?.note && <div className="files-note">{run.note}</div>}
      {engineTab && run?.cached && (
        <div className="files-note">
          Served from the capture folder: this exact deck has run before.
        </div>
      )}
      {engineTab && run && data.engineIo?.error && (
        <div className="files-error">{data.engineIo.error}</div>
      )}
      {pane.text !== undefined ? (
        <pre
          className={`files-text${engineTab && data.stale ? " stale" : ""}`}
          aria-label={pane.filename}
        >
          {pane.text}
        </pre>
      ) : (
        <div className="files-empty">{pane.message}</div>
      )}
    </div>
  );
}
