// The feed-network schematic view (issue #652): the circuit half of a
// design — feedline, tuner, balun, and the port the source sits on — which
// is otherwise invisible in every view. The SVG arrives server-rendered
// (schemdraw is Python-only) drawn in currentColor, and is inlined rather
// than <img>-embedded so it inherits the theme's text colour.
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
  return (
    <div className={cls} style={style} dangerouslySetInnerHTML={{ __html: svg }} />
  );
}
