import {
  DIALECTS,
  DIALECT_LABEL,
  isDialect,
  MAX_SHARE_CHARS,
  shareable,
  type Dialect,
  type OpenedDeck,
} from "../../lib/decks";

// The opened-deck notices (lib/decks.ts): a deck that did not open, in the
// server's own words, and a deck that opened but is too long for the page's
// link to carry, so the link cannot share it (it still works in this page).
// And the dialect an opened .nec deck is read in (NEC-2 / NEC-4 / NEC-5):
// detected ("auto") unless
// the reader chooses one, which re-opens the deck read that way (the design
// note above the knobs says what it was read as, and why).
export function DeckNotice({
  deck,
  error,
  onDismissError,
  onReadAs,
}: {
  /** The opened deck the session is on, or null. */
  deck: OpenedDeck | null;
  /** Why the last deck the user opened did not open, or null. */
  error: string | null;
  onDismissError: () => void;
  /** Re-open the deck read in `dialect` (null: detect it). */
  onReadAs?: (dialect: Dialect | null) => void;
}) {
  const tooLong = deck !== null && !shareable(deck);
  const readAs = deck?.readAs ?? null;
  const isNec = deck !== null && /\.nec$/i.test(deck.name);
  return (
    <>
      {deck && readAs && isNec && onReadAs && (
        <div className="deck-dialect">
          <label>
            Read as{" "}
            <select
              aria-label="read the deck as"
              value={deck.dialect ?? "auto"}
              title="Which NEC dialect the deck is read in: NEC-2 and NEC-4 put sources and loads at segment centres, NEC-5 at segment ends"
              onChange={(e) => onReadAs(isDialect(e.target.value) ? e.target.value : null)}
            >
              <option value="auto">
                auto ({readAs.detected ? DIALECT_LABEL[readAs.detected] : "refused"})
              </option>
              {DIALECTS.map((d) => (
                <option key={d} value={d}>
                  {DIALECT_LABEL[d]}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {error && (
        <div className="settings-notice" role="alert" aria-label="Deck problem">
          <span>
            <strong>deck:</strong> {error}
          </span>
          <button type="button" aria-label="Dismiss the deck notice" onClick={onDismissError}>
            ×
          </button>
        </div>
      )}
      {tooLong && (
        <div className="settings-notice" role="status" aria-label="Deck link">
          <span>
            <strong>{deck.name}</strong> is open in this page, but it is too long to share in a
            link ({Math.ceil(deck.z.length / 1024)} KB compressed; a link carries up to{" "}
            {Math.floor(MAX_SHARE_CHARS / 1000)} KB). To share it, send the file.
          </span>
        </div>
      )}
    </>
  );
}
