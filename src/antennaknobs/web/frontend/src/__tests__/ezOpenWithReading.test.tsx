// Open… an .ez whose format leaves a reading undefined (AK#2173): the
// refusal carries the reading, the notice offers "Open with this reading",
// the retry carries `accept_guesses`, and a link keeps it (`&readings=1`).
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { clearDecks, deckPayload, DeckOpenError, openDeck, type OpenedDeck } from "../lib/decks";
import { linkSearch, parseDeepLink } from "../lib/deepLink";
import { DeckNotice } from "../components/session/DeckNotice";
import { HARNESS_EXAMPLE } from "./designSessionHarness";

const KEY = "deck.0123456789ab";

afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
});

describe("the refusal and the retry", () => {
  it("a refusal that names a reading carries it and what was sent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              detail: "laplace.ez: load 1: a Laplace load's variable ..., Open with this reading to read it as s",
              deck_status: "undefined",
              reading: "s, the Laplace variable",
            }),
            { status: 422, headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    const payload = { name: "laplace.ez", z: "abc" };
    const err = await openDeck(payload).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DeckOpenError);
    expect((err as DeckOpenError).reading).toBe("s, the Laplace variable");
    expect((err as DeckOpenError).payload).toEqual(payload);
  });

  it("a plain refusal carries no reading", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "no", deck_status: "refused" }), { status: 422 })),
    );
    const err = (await openDeck({ name: "x.ez", z: "abc" }).catch((e: unknown) => e)) as DeckOpenError;
    expect(err.reading).toBeNull();
  });

  it("the flag rides every request for the deck, and only when set", () => {
    expect(deckPayload({ name: "a.ez", z: "z", accept_guesses: true })).toEqual({
      name: "a.ez",
      z: "z",
      accept_guesses: true,
    });
    expect(deckPayload({ name: "a.ez", z: "z" })).toEqual({ name: "a.ez", z: "z" });
  });

  it("a link carries it and reads it back", () => {
    const deck = { z: "zz", name: "a.ez", accept_guesses: true };
    const s = linkSearch("", { design: KEY, variant: null, analysis: null, view: null, deck });
    expect(s).toContain("readings=1");
    expect(parseDeepLink(s)!.deck).toMatchObject({ name: "a.ez", accept_guesses: true });
    const plain = linkSearch("", { design: KEY, variant: null, analysis: null, view: null, deck: { z: "zz", name: "a.ez" } });
    expect(plain).not.toContain("readings");
  });
});

describe("the notice", () => {
  it("offers the reading as a button only when there is one", () => {
    const accept = vi.fn();
    const { rerender } = render(
      <DeckNotice deck={null} error="laplace.ez: … Open with this reading …" onDismissError={() => {}} onAcceptReading={accept} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open with this reading" }));
    expect(accept).toHaveBeenCalledOnce();
    rerender(<DeckNotice deck={null} error="no" onDismissError={() => {}} />);
    expect(screen.queryByRole("button", { name: "Open with this reading" })).toBeNull();
  });

  it("offers Read as for an .ez, where the file's engine setting is the default", () => {
    const ez: OpenedDeck = {
      key: KEY,
      name: "model.ez",
      z: "zz",
      example: { ...HARNESS_EXAMPLE, name: KEY, label: "model.ez" },
      readAs: { read_as: "nec2", reason: "an EZNEC .ez model", detected: null, chosen: null },
    };
    render(<DeckNotice deck={ez} error={null} onDismissError={() => {}} onReadAs={() => {}} />);
    const select = screen.getByLabelText("read the deck as");
    expect(select).toBeTruthy();
    expect(screen.getByRole("option", { name: "auto (as the file says)" })).toBeTruthy();
  });
});
