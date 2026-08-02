import { useState } from "react";

// One advisory finding from the design screener (what a design does that a
// typical one doesn't), attached to a trust-required entry.
export type DesignAdvisory = { severity: string; message: string; line: number };

// A user design reported by GET /examples that didn't register. Either a real
// load error (bad Python), or — when `trust_required` — a design that loaded
// fine but hasn't been trusted to run yet, carrying its screener `advisory`.
export type DesignLoadError = {
  name: string;
  file: string;
  message: string;
  trust_required?: boolean;
  advisory?: DesignAdvisory[];
};

// Designs that loaded clean but haven't been trusted to run yet. A user design
// is a Python program that runs with your privileges, so it executes only once
// you trust it (see design_trust.py). This panel is collapsed to one line by
// default — click a design to see what it does (the screener advisory) and to
// trust it. Enforcement happens at scan time (untrusted files are never
// executed); this is just where you make the decision, per design.
export function AwaitingTrustPanel({
  designs,
  busy,
  onTrust,
}: {
  designs: DesignLoadError[];
  busy: string | null;
  onTrust: (stem: string, allowEdits: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [openName, setOpenName] = useState<string | null>(null);
  const n = designs.length;
  return (
    <div className="design-trust-panel">
      <button
        className="design-trust-summary"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="design-trust-lock" aria-hidden="true">
          🔒
        </span>
        {n} design{n === 1 ? " needs" : "s need"} your OK to run
        <span className="design-trust-caret" aria-hidden="true">
          {expanded ? "▾" : "▸"}
        </span>
      </button>
      {expanded && (
        <ul className="design-trust-list">
          {designs.map((d) => {
            const open = openName === d.name;
            const isBusy = busy === d.name;
            return (
              <li key={d.name} className="design-trust-item">
                <button
                  className="design-trust-item-head"
                  aria-expanded={open}
                  onClick={() => setOpenName(open ? null : d.name)}
                >
                  <code>{d.name}</code>
                  <span className="design-trust-caret" aria-hidden="true">
                    {open ? "▾" : "▸"}
                  </span>
                </button>
                {open && (
                  <div className="design-trust-detail">
                    {d.advisory && d.advisory.length > 0 ? (
                      <>
                        <div className="design-trust-advisory-head">
                          Heads up — this design does things a normal antenna
                          design doesn&apos;t. Look before you let it run:
                        </div>
                        <ul className="design-trust-advisory">
                          {d.advisory.map((a, i) => (
                            <li key={i} className={`sev-${a.severity}`}>
                              line {a.line}: {a.message}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <div className="design-trust-advisory-head">
                        Nothing unusual — it only builds antenna geometry.
                      </div>
                    )}
                    <div className="design-trust-actions">
                      <button
                        className="design-trust-btn"
                        disabled={isBusy}
                        onClick={() => onTrust(d.name, false)}
                      >
                        Allow it to run
                      </button>
                      <button
                        className="design-trust-btn is-edits"
                        disabled={isBusy}
                        onClick={() => onTrust(d.name, true)}
                        title="For a design you're writing yourself — won't ask again when you save changes"
                      >
                        Allow + my edits
                      </button>
                    </div>
                    <div className="design-trust-note">
                      A design is a small program that runs on your computer.
                      Only allow ones from people you trust.
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
