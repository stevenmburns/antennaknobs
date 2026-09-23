import { useRef, useState, type CSSProperties } from "react";
import { FIT_CAP, naturalSize, stepZoom, ZOOM_STEPS } from "../../lib/schematicZoom";

// The feed-network schematic view (issue #652): the circuit half of a
// design — feedline, tuner, balun, and the port the source sits on — which
// is otherwise invisible in every view. The SVG arrives server-rendered
// (schemdraw is Python-only) drawn in currentColor, and is inlined rather
// than <img>-embedded so it inherits the theme's text colour.
//
// SIZING (AK#1682). The panel used to only ever shrink the drawing to fit,
// so a wide chain (AC6LA's CLC feed system, ~800 pt) printed its values at
// a few pixels and browser zoom could not help — the fit just shrank it
// back. The stage view now:
//   - FITS by default, both ways, but scales UP only to FIT_CAP × natural
//     size, so a three-element chain does not become a cartoon;
//   - offers a zoom (−, fit, +) that draws at a fixed multiple of natural
//     size inside a scroll box, so any chain can be read at any width.
// Thumbnails keep shrink-to-fit: they are a glance, not a reading surface.

export function SchematicPanel({
  svg,
  unavailable,
  size,
  fill,
}: {
  svg: string | null;
  unavailable: boolean;
  size: number;
  fill: boolean;
}) {
  // null = fit. Held across SVG refetches (every knob tweak re-renders the
  // drawing), so a user reading a zoomed chain keeps their zoom.
  const [zoom, setZoom] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const cls = fill ? "schematic-fill" : "schematic-thumb";
  const style = fill ? undefined : { width: size, height: size };
  if (!svg) {
    // One message at every scale (stage, phone screen, thumbnail — the
    // thumb shrinks it via CSS): the design is a bare antenna, so there is
    // no feedline, tuner, or balun to draw.
    return (
      <div className={cls} style={style}>
        {unavailable && (
          <div className="schematic-empty">
            No feed circuit — this design is the bare antenna.
          </div>
        )}
      </div>
    );
  }
  // Server-generated markup from our own backend — the same trust boundary
  // as every solve response this UI renders.
  if (!fill) {
    return (
      <div className={cls} style={style} dangerouslySetInnerHTML={{ __html: svg }} />
    );
  }

  const nat = naturalSize(svg);
  // The scale fit is drawing at right now, for the first +/− press. Read
  // from the box when it has one (jsdom and a hidden panel do not); 1 is
  // the honest default — natural size.
  const fitScale = (): number => {
    const box = scrollRef.current;
    if (!nat || !box || !box.clientWidth || !box.clientHeight) return 1;
    return Math.min(FIT_CAP, box.clientWidth / nat.w, box.clientHeight / nat.h);
  };
  const vars: Record<string, string> = {};
  if (nat) {
    if (zoom == null) {
      vars["--schem-max-w"] = `${nat.w * FIT_CAP}px`;
      vars["--schem-max-h"] = `${nat.h * FIT_CAP}px`;
    } else {
      vars["--schem-w"] = `${nat.w * zoom}px`;
      vars["--schem-h"] = `${nat.h * zoom}px`;
    }
  }
  return (
    <div className={cls}>
      <div
        ref={scrollRef}
        className={`schematic-scroll ${zoom == null ? "schematic-fit" : "schematic-zoomed"}`}
        data-zoom={zoom == null ? "fit" : String(zoom)}
        style={vars as CSSProperties}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      {nat && (
        <div className="schematic-zoom" role="group" aria-label="Schematic zoom">
          <button
            type="button"
            aria-label="Zoom out"
            title="Zoom out"
            disabled={zoom != null && zoom <= ZOOM_STEPS[0]}
            onClick={() => setZoom(stepZoom(zoom ?? fitScale(), -1))}
          >
            −
          </button>
          <button
            type="button"
            className={zoom == null ? "active" : undefined}
            aria-pressed={zoom == null}
            aria-label="Fit to panel"
            title="Fit the drawing to the panel"
            onClick={() => setZoom(null)}
          >
            {zoom == null ? "fit" : `${Math.round(zoom * 100)}%`}
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            title="Zoom in"
            disabled={zoom != null && zoom >= ZOOM_STEPS[ZOOM_STEPS.length - 1]}
            onClick={() => setZoom(stepZoom(zoom ?? fitScale(), 1))}
          >
            +
          </button>
        </div>
      )}
    </div>
  );
}
