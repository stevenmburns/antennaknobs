import { useEffect, useMemo, useRef, useState } from "react";
import type { SolveRequest } from "../../lib/api";
import {
  chainToJson,
  fetchPalette,
  fmtSwr,
  fmtZ,
  galleryFor,
  readFile,
  renderRails,
  StationRequestError,
  withoutItem,
  type GalleryResponse,
  type PaletteResponse,
  type RailResult,
  type RenderResponse,
  type StationChain,
} from "../../lib/stationRail";

// The Station view (docs/design/block-builder.md, "The station rail"): the
// rail (rig pinned left, the antenna on screen pinned right), the Python it
// writes and the schematic it draws, kept in step; the junction probes; A/B
// rails; and the placement gallery. The antenna is the workbench's own
// design at its knobs: every POST carries the session's solve request, and
// the server solves the antenna once per request for both rails, every probe
// and every card. Switching between A and B is a display switch over the one
// response, never a request.

/** What the session lends the view: the design on screen and its request. */
export type StationContext = {
  geometry: string;
  buildRequest: () => SolveRequest;
};

const RAIL_NAMES = ["A", "B"] as const;
const DEBOUNCE_MS = 250;

type Gallery = { title: string; body: GalleryResponse | null; error: string | null };

export function StationPanel({
  station,
  size,
  fill,
}: {
  station: StationContext | null;
  size: number;
  fill: boolean;
}) {
  // Only the stage's bag lends a context; thumbnails get none and draw the
  // placeholder. The stage draws at a fixed `size` (fill false) or fills
  // its cell (fill true).
  if (!station) {
    return (
      <div className="station-thumb" style={fill ? undefined : { width: size, height: size }}>
        <div className="station-thumb-rail">
          <span>RIG</span>
          <span className="station-thumb-line" />
          <span>ANT</span>
        </div>
        <div className="station-thumb-label">Station rail</div>
      </div>
    );
  }
  const rail = <StationRail key={station.geometry} station={station} />;
  return fill ? rail : (
    <div className="station-box" style={{ width: size, height: size }}>
      {rail}
    </div>
  );
}

function StationRail({ station }: { station: StationContext }) {
  const [rails, setRails] = useState<(StationChain | null)[]>([null]);
  const [active, setActive] = useState(0);
  const [data, setData] = useState<RenderResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [palette, setPalette] = useState<PaletteResponse | null>(null);
  const [gallery, setGallery] = useState<Gallery | null>(null);
  const [readText, setReadText] = useState("");
  const [readMsg, setReadMsg] = useState<string | null>(null);
  // The key of the rails the server last answered for, frozen names and
  // all: putting its frozen chains back into state must not re-post them.
  const settled = useRef<string | null>(null);
  const shownPython = useRef<(string | null)[]>([]);

  const request = station.buildRequest();
  const requestJson = JSON.stringify(request);
  const railsJson = JSON.stringify(rails.map((c) => (c ? chainToJson(c) : null)));

  useEffect(() => {
    fetchPalette()
      .then(setPalette)
      .catch(() => setPalette(null));
  }, []);

  useEffect(() => {
    const key = requestJson + railsJson;
    if (key === settled.current) return;
    const controller = new AbortController();
    const t = setTimeout(() => {
      setBusy(true);
      renderRails(JSON.parse(requestJson) as SolveRequest, rails, shownPython.current, controller.signal)
        .then((resp) => {
          if (controller.signal.aborted) return;
          const frozen = resp.rails.map((r) => r.chain);
          settled.current =
            requestJson + JSON.stringify(frozen.map((c) => chainToJson(c)));
          shownPython.current = resp.rails.map((r) => r.python);
          setData(resp);
          setError(null);
          setRails(frozen);
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          setError(
            e instanceof StationRequestError && e.status === 404
              ? "The station rail runs on a local install of antennaknobs."
              : e instanceof Error
                ? e.message
                : String(e),
          );
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(t);
      controller.abort();
    };
    // `rails` is read through railsJson, its value key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestJson, railsJson]);

  const shown = data?.rails[active] ?? null;
  const chain = rails[active] ?? null;

  const setChain = (c: StationChain) =>
    setRails((rs) => rs.map((r, i) => (i === active ? c : r)));

  const openGallery = (title: string, what: { add: string } | { move: number }) => {
    if (!chain) return;
    setGallery({ title, body: null, error: null });
    galleryFor(request, chain, what)
      .then((body) => setGallery({ title, body, error: null }))
      .catch((e: unknown) =>
        setGallery({ title, body: null, error: e instanceof Error ? e.message : String(e) }),
      );
  };

  const onRead = () => {
    readFile(request, readText)
      .then((resp) => {
        if ("refusal" in resp) {
          setReadMsg(resp.refusal);
          return;
        }
        setReadMsg(`Read onto rail ${RAIL_NAMES[active]}.`);
        setChain(resp.chain);
      })
      .catch((e: unknown) => setReadMsg(e instanceof Error ? e.message : String(e)));
  };

  if (error && !data) {
    return (
      <div className="station-fill">
        <div className="station-error" role="alert">
          {error}
        </div>
      </div>
    );
  }
  if (!data || !shown) {
    return (
      <div className="station-fill">
        <div className="station-empty">Solving the station…</div>
      </div>
    );
  }
  const ant = data.antenna;
  return (
    <div className={`station-fill${busy ? " station-busy" : ""}`}>
      <div className="station-head">
        <div className="station-tabs" role="tablist" aria-label="Rails">
          {rails.map((_c, i) => (
            <button
              key={RAIL_NAMES[i]}
              role="tab"
              aria-selected={i === active}
              className={i === active ? "active" : undefined}
              onClick={() => setActive(i)}
            >
              Rail {RAIL_NAMES[i]}
            </button>
          ))}
          {rails.length === 1 ? (
            <button
              onClick={() => {
                setRails((rs) => [rs[0], rs[0]]);
                setActive(1);
              }}
            >
              + B (a copy of A)
            </button>
          ) : (
            <button
              onClick={() => {
                setRails((rs) => [rs[active]]);
                setActive(0);
              }}
            >
              Keep only {RAIL_NAMES[active]}
            </button>
          )}
        </div>
        <div className="station-meta">
          {ant.freq_mhz.toFixed(3)} MHz · SWR against {ant.z_ref} Ω · {data.antenna_solves}{" "}
          antenna solve{data.antenna_solves === 1 ? "" : "s"}
        </div>
      </div>
      {ant.notice && <div className="station-notice">{ant.notice}</div>}
      {error && (
        <div className="station-error" role="alert">
          {error}
        </div>
      )}

      <Rail
        rail={shown}
        antennaLabel={`${ant.design} · ${ant.feed}`}
        onMove={(i) => openGallery(`Move ${shown.chips[i].label}`, { move: i })}
        onRemove={(i) => chain && setChain(withoutItem(chain, i))}
      />
      {shown.advisories.length > 0 && (
        <ul className="station-advisories">
          {shown.advisories.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}

      {data.rails.length === 2 && <Compare rails={data.rails} />}

      <div className="station-panes">
        <section className="station-pane">
          <h3>Python</h3>
          <pre className="station-code" aria-label="Generated Python">
            {shown.python.split("\n").map((ln, i) => (
              <div key={i} className={shown.changed.includes(i) ? "changed" : undefined}>
                {ln || " "}
              </div>
            ))}
          </pre>
        </section>
        <section className="station-pane">
          <h3>Schematic</h3>
          {shown.svg ? (
            // Server-rendered markup from our own backend, the same trust
            // boundary as the Schematic view.
            <div className="station-svg" dangerouslySetInnerHTML={{ __html: shown.svg }} />
          ) : (
            <div className="station-empty">{shown.svg_reason ?? "No drawing."}</div>
          )}
          <Probes rail={shown} />
        </section>
      </div>

      <section className="station-palette">
        <h3>Add a component</h3>
        <div className="station-palette-row">
          {palette &&
            Object.entries(palette.palette).map(([key, p]) => (
              <button key={key} onClick={() => openGallery(`Add ${p.label}`, { add: key })}>
                {p.label}
              </button>
            ))}
        </div>
      </section>

      {gallery && (
        <GalleryView
          gallery={gallery}
          onPick={(c) => {
            setChain(c);
            setGallery(null);
          }}
          onClose={() => setGallery(null)}
        />
      )}

      <details className="station-read">
        <summary>Read a station file back onto rail {RAIL_NAMES[active]}</summary>
        <textarea
          aria-label="Station file"
          value={readText}
          onChange={(e) => setReadText(e.target.value)}
          spellCheck={false}
        />
        <button onClick={onRead} disabled={!readText.trim()}>
          Put on the rail
        </button>
        {readMsg && <div className="station-read-msg">{readMsg}</div>}
      </details>
    </div>
  );
}

function Rail({
  rail,
  antennaLabel,
  onMove,
  onRemove,
}: {
  rail: RailResult;
  antennaLabel: string;
  onMove: (i: number) => void;
  onRemove: (i: number) => void;
}) {
  return (
    <div className="station-rail" aria-label="Station rail">
      <span className="station-end">RIG</span>
      {rail.chips.map((c, i) => (
        <span key={i} className={`station-chip${c.series ? "" : " shunt"}`}>
          <button className="station-chip-body" onClick={() => onMove(i)} title="Move">
            {c.label}
            <small>{c.series ? `${c.a} → ${c.b}` : `at ${c.a}`}</small>
          </button>
          <button
            className="station-chip-x"
            aria-label={`Remove ${c.label}`}
            onClick={() => onRemove(i)}
          >
            ×
          </button>
        </span>
      ))}
      <span className="station-end">ANTENNA · {antennaLabel}</span>
    </div>
  );
}

function Probes({ rail }: { rail: RailResult }) {
  return (
    <table className="station-probes">
      <caption>Looking towards the antenna</caption>
      <thead>
        <tr>
          <th>at</th>
          <th>Z</th>
          <th>SWR</th>
        </tr>
      </thead>
      <tbody>
        {rail.probes.map((p, i) => (
          <tr key={`${p.at}-${i}`}>
            <td>{p.at}</td>
            <td>{fmtZ(p)}</td>
            <td>{fmtSwr(p.swr)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Compare({ rails }: { rails: RailResult[] }) {
  return (
    <table className="station-compare" aria-label="Rails compared">
      <thead>
        <tr>
          <th />
          <th>Z at the rig</th>
          <th>SWR</th>
          <th>station loss</th>
          <th>reaches the antenna</th>
        </tr>
      </thead>
      <tbody>
        {rails.map((r, i) => (
          <tr key={RAIL_NAMES[i]}>
            <th>{RAIL_NAMES[i]}</th>
            <td>{fmtZ(r)}</td>
            <td>{fmtSwr(r.swr)}</td>
            <td>{r.loss_db === null ? "—" : `${r.loss_db.toFixed(2)} dB`}</td>
            <td>{r.p_ant_w.toFixed(1)} W of 100</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GalleryView({
  gallery,
  onPick,
  onClose,
}: {
  gallery: Gallery;
  onPick: (c: StationChain) => void;
  onClose: () => void;
}) {
  const body = gallery.body;
  const cards = useMemo(() => body?.cards ?? [], [body]);
  return (
    <section className="station-gallery" aria-label="Placements">
      <div className="station-gallery-head">
        <h3>{gallery.title}</h3>
        <button onClick={onClose} aria-label="Close placements">
          ×
        </button>
      </div>
      {gallery.error && <div className="station-error">{gallery.error}</div>}
      {!body && !gallery.error && <div className="station-empty">Solving each place…</div>}
      {body?.refusal && <div className="station-notice">{body.refusal}</div>}
      <div className="station-cards">
        {cards.map((c) => (
          <button
            key={c.pos}
            className={`station-card${c.current ? " current" : ""}`}
            onClick={() => onPick(c.chain)}
          >
            <div className="station-card-where">
              {c.where}
              {c.current ? " (where it is now)" : ""}
            </div>
            {c.svg && (
              <div className="station-card-svg" dangerouslySetInnerHTML={{ __html: c.svg }} />
            )}
            <pre className="station-card-diff">
              {c.diff.map((ln, i) => (
                <div key={i} className={ln[0] === "+" ? "add" : ln[0] === "-" ? "del" : undefined}>
                  {ln}
                </div>
              ))}
            </pre>
            <div className="station-card-nums">
              SWR {fmtSwr(c.swr)} · {c.loss_db === null ? "—" : `−${c.loss_db.toFixed(2)} dB`} ·{" "}
              {c.p_ant_w.toFixed(0)} W reach the antenna
            </div>
            {c.advisories.map((a) => (
              <div key={a} className="station-card-advisory">
                {a}
              </div>
            ))}
          </button>
        ))}
      </div>
    </section>
  );
}
