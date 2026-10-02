// The variable-count controls both slot tab strips share (AK#1801): the +
// at the end of the strip, and the remove button in a slot's ⚙ settings.

/** The + at the end of a slot tab strip: adds a copy of the active slot.
 *  Not rendered once the family is full (`next` null). */
export function AddSlotButton({
  noun,
  next,
  onAdd,
}: {
  noun: string;
  next: string | null;
  onAdd: () => void;
}) {
  if (next === null) return null;
  const what = `Add ${noun} slot ${next}, a copy of the active slot`;
  return (
    <button className="slot-add-btn" title={what} aria-label={what} onClick={onAdd}>
      +
    </button>
  );
}

/** A slot's remove button, for its settings footer: enabled when the slot can
 *  go, else disabled with the reason beside it. The caller renders it only
 *  for a slot past the stock set. */
export function RemoveSlotButton({
  noun,
  id,
  refusal,
  onRemove,
}: {
  noun: string;
  id: string;
  /** slotRemovalRefusal's sentence, or null. */
  refusal: string | null;
  onRemove: () => void;
}) {
  return (
    <>
      {refusal && <span className="backend-config-note slot-remove-note">{refusal}</span>}
      <button
        className="backend-config-reset slot-remove-btn"
        disabled={refusal !== null}
        aria-label={`Remove ${noun} slot ${id}`}
        onClick={onRemove}
      >
        remove slot {id}
      </button>
    </>
  );
}
