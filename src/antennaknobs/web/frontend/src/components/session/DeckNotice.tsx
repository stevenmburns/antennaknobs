import { MAX_SHARE_CHARS, shareable, type OpenedDeck } from "../../lib/decks";

// The opened-deck notices (lib/decks.ts): a deck that did not open, in the
// server's own words, and a deck that opened but is too long for the page's
// link to carry, so the link cannot share it (it still works in this page).
export function DeckNotice({
  deck,
  error,
  onDismissError,
}: {
  /** The opened deck the session is on, or null. */
  deck: OpenedDeck | null;
  /** Why the last deck the user opened did not open, or null. */
  error: string | null;
  onDismissError: () => void;
}) {
  const tooLong = deck !== null && !shareable(deck);
  return (
    <>
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
