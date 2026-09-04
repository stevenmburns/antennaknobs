// A tab's composition line: what this engine is made of, in words.
//
// antennaknobs#1006 point 2, made visible. Everything before G2-7 was
// equivalence-gated and looked identical to a user by design; this is the
// first change they are meant to SEE. It exists because the roster is six
// names with no way to tell that three of them differ in one word.
//
// Carries no engine names and no vocabulary of its own: the axes, their order
// and every phrase are served (`composition_axes`, `axis_value_labels`), on
// the same argument as the option catalogue — UI copy ABOUT engines belongs
// with the engines.
import type { CompositionSegment } from "../../lib/backends";

export function CompositionLine({
  label,
  segments,
}: {
  /** The tab's own label, which opens the line. */
  label: string;
  /** Null when the backend cannot describe itself compositionally. */
  segments: CompositionSegment[] | null;
}) {
  if (segments === null) {
    // (e) — stated once, never fabricated. `axes: null` means "cannot be
    // asked", and inventing segments would be this feature's worst failure:
    // asserting a composition nobody measured.
    //
    // "External engine" opens the sentence because a bare "not described
    // compositionally" beside six tabs that all say something concrete reads
    // as an error rather than a statement. Naming what the thing IS first
    // makes the absence a fact about PyNEC/NEC-5 rather than a gap.
    return (
      <div className="composition-line" data-testid="composition-line">
        <span className="composition-tab">{label}</span>
        <span className="composition-sep"> · </span>
        <em className="composition-undescribed">
          External engine, not described compositionally
        </em>
      </div>
    );
  }
  return (
    // One row, wrapping, never truncated: a description of the engine cut
    // short is a confident half-sentence, which is worse than a long one.
    <div className="composition-line" data-testid="composition-line">
      <span className="composition-tab">{label}</span>
      {segments.map((s) => (
        <span key={s.axis}>
          <span className="composition-sep"> · </span>
          {/* No dimming for fixed segments — the line reads as one sentence
              rather than as a form, and the pin marker is the only
              typography that carries meaning. Both are judgement calls made
              in the running app, and either is a CSS change. */}
          <span className="composition-seg" data-axis={s.axis}>
            {s.text}
            {s.pinned && (
              // A PARENTHETICAL, not a comma. The comma read as another unit
              // separator beside the middle dots, so the annotation looked
              // like punctuation in a list rather than a note about the
              // segment it belongs to.
              <span className="composition-pin"> (pinned)</span>
            )}
          </span>
        </span>
      ))}
    </div>
  );
}
