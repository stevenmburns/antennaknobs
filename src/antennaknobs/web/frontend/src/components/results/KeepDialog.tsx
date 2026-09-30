import { useEffect, useState } from "react";
import {
  fetchKeep,
  type KeepBody,
  type KeepText,
  type SavedStudy,
  saveStudy,
  StudyExistsError,
  suggestedPath,
} from "../../lib/keep";

// "Copy as analysis" and "keep as study" (AK#1757, sweep-framework step 7,
// unit 4): what a chart, the pinned sweeps or the pinned patterns keep, as
// the Python the server writes for them (POST /keep), shown before it goes
// anywhere. Copy puts that text on the clipboard; on a local workbench, a
// study can also be saved as a new file in the studies folder (POST
// /studies/save), trusted with edits allowed, which puts it in the picker's
// Studies group on every tab it names. Hosted, there is no save (the server
// refuses it too): copy it instead. In the solver gear's modal shell
// (BackendConfigModal's overlay, card and header), which fits a phone.

export type KeepDialogProps = {
  title: string;
  /** What is kept, without its name: the dialog adds the one typed here. */
  body: KeepBody;
  /** The name it starts with (the analysis's, or "pinned sweeps"). */
  initialName: string;
  /** Whether this workbench may write the file (/capabilities). */
  canSave: boolean;
  onClose: () => void;
  /** A study was saved: the tab re-reads its analyses to list it. */
  onSaved?: (saved: SavedStudy) => void;
};

type Fetched = { key: string; text: KeepText | null; error: string | null };

export function KeepDialog({ title, body, initialName, canSave, onClose, onSaved }: KeepDialogProps) {
  const [name, setName] = useState(initialName);
  const [path, setPath] = useState(() => suggestedPath(initialName));
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState<{
    state: "idle" | "busy" | "saved" | "exists" | "failed";
    message: string | null;
  }>({ state: "idle", message: null });
  const withName: KeepBody = { ...body, name: name.trim() };
  const key = JSON.stringify(withName);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // The text for what is kept under the name typed, re-asked a beat after
  // the typing stops; a later answer replaces an earlier one.
  useEffect(() => {
    const ctl = new AbortController();
    const t = window.setTimeout(() => {
      fetchKeep(JSON.parse(key) as KeepBody, ctl.signal).then(
        (text) => setFetched({ key, text, error: null }),
        (e: unknown) => {
          if (!ctl.signal.aborted) {
            setFetched({ key, text: null, error: e instanceof Error ? e.message : String(e) });
          }
        },
      );
    }, 250);
    return () => {
      window.clearTimeout(t);
      ctl.abort();
    };
  }, [key]);

  const current = fetched?.key === key ? fetched : null;
  const text = current?.text ?? null;
  const isStudy = body.form === "study";
  const saveBlocked =
    !canSave
      ? "Saving writes a file on this machine: a local workbench only. Copy it instead."
      : text?.studyRefusal ?? (path.trim() ? null : "Give the study a file name");

  const copy = () => {
    if (!text) return;
    void navigator.clipboard?.writeText(text.code).then(
      () => setCopied(true),
      () => setCopied(false),
    );
  };
  const save = (overwrite: boolean) => {
    setSaving({ state: "busy", message: null });
    saveStudy(withName, path.trim(), overwrite).then(
      (saved) => {
        setSaving({
          state: "saved",
          message: `Saved ${saved.path}: "${saved.name}" is in the Studies group of every tab it names.`,
        });
        onSaved?.(saved);
      },
      (e: unknown) =>
        setSaving({
          state: e instanceof StudyExistsError ? "exists" : "failed",
          message: e instanceof Error ? e.message : String(e),
        }),
    );
  };

  return (
    <div className="backend-config-overlay" onClick={onClose}>
      <div
        className="backend-config-modal keep-dialog"
        role="dialog"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="backend-config-header">
          <strong>{title}</strong>
          <button className="backend-config-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="backend-config-body">
          <label className="keep-dialog-field">
            <span>name</span>
            <input
              type="text"
              value={name}
              aria-label="The analysis's name"
              onChange={(e) => {
                setName(e.target.value);
                setCopied(false);
              }}
            />
          </label>
          {current?.error && (
            <div className="keep-dialog-why" role="alert">
              {current.error}
            </div>
          )}
          {text && text.problems.length > 0 && (
            <ul className="keep-dialog-why" aria-label="Problems on this design">
              {text.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
          <pre className="keep-dialog-code" aria-label={`${title} as Python`} aria-busy={!current}>
            {text?.code ?? (current?.error ? "" : "…")}
          </pre>
          <div className="keep-dialog-actions">
            <button type="button" className="zparam-reset" disabled={!text} onClick={copy}>
              {copied ? "copied" : "copy"}
            </button>
          </div>
          {isStudy && (
            <div className="keep-dialog-save" role="group" aria-label="Save to the studies folder">
              <label className="keep-dialog-field">
                <span>~/.antennaknobs/studies/</span>
                <input
                  type="text"
                  value={path}
                  disabled={!canSave}
                  aria-label="The study file's path under the studies folder"
                  onChange={(e) => {
                    setPath(e.target.value);
                    setSaving({ state: "idle", message: null });
                  }}
                />
                <span>.py</span>
              </label>
              <button
                type="button"
                className="zparam-reset"
                disabled={!text || saveBlocked !== null || saving.state === "busy"}
                title={saveBlocked ?? "Write it as a new study file, trusted with your edits allowed"}
                onClick={() => save(false)}
              >
                save as study
              </button>
              {saving.state === "exists" && (
                <button type="button" className="zparam-reset" onClick={() => save(true)}>
                  replace it
                </button>
              )}
              {saveBlocked && <div className="keep-dialog-note">{saveBlocked}</div>}
              {saving.message && (
                <div
                  className={saving.state === "saved" ? "keep-dialog-note" : "keep-dialog-why"}
                  role={saving.state === "saved" ? "status" : "alert"}
                >
                  {saving.message}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
