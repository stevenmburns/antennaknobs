// Opened decks are told apart by their file name (AK#2071, AC6LA): the server
// labels a deck by its stem, so foo.ez and foo.nec read alike. The picker
// shows the name with its extension, and its hover adds the dialect a reader
// chose, since the same file read two ways is two entries.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { GeometryCombobox } from "../components/params/GeometryCombobox";
import { clearDecks, deckTitle, deckTitleFor, openDeck } from "../lib/decks";
import type { ExampleDescriptor } from "../lib/params";
import { HARNESS_EXAMPLE } from "./designSessionHarness";

// The server answers as it does today: every deck labelled by the stem.
function serveStem() {
  let n = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      const key = `deck.${String(++n).padStart(12, "0")}`;
      return new Response(JSON.stringify({ key, example: { ...HARNESS_EXAMPLE, name: key, label: "foo" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

const CATALOG: ExampleDescriptor = { ...HARNESS_EXAMPLE, name: "dipoles.dipole", label: "Dipole" };

afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
});

describe("an opened deck's label and hover", () => {
  it("labels each deck by its file name, extension included", async () => {
    serveStem();
    const ez = await openDeck({ name: "foo.ez", z: "a" });
    const nec = await openDeck({ name: "foo.nec", z: "b" });
    expect(ez.example.label).toBe("foo.ez");
    expect(nec.example.label).toBe("foo.nec");
  });

  it("hovers with the file name, and the dialect when one was chosen", async () => {
    serveStem();
    const auto = await openDeck({ name: "foo.nec", z: "b" });
    const nec4 = await openDeck({ name: "foo.nec", z: "b", dialect: "nec4" });
    expect(deckTitle(auto)).toBe("foo.nec");
    expect(deckTitle(nec4)).toBe("foo.nec, read as NEC-4");
    expect(deckTitleFor(nec4.key)).toBe("foo.nec, read as NEC-4");
    expect(deckTitleFor(CATALOG.name)).toBeUndefined();
  });

  it("the picker shows the names and carries the hovers; a catalog design has none", async () => {
    serveStem();
    const ez = await openDeck({ name: "foo.ez", z: "a" });
    const nec = await openDeck({ name: "foo.nec", z: "b", dialect: "nec2" });
    render(
      <GeometryCombobox
        groups={[
          { fam: "dipoles", label: "Dipoles", items: [CATALOG] },
          { fam: "deck", label: "Opened decks", items: [ez.example, nec.example] },
        ]}
        selected={nec.key}
        currentLabel={nec.example.label}
        filter=""
        setFilter={() => {}}
        onSelect={() => {}}
      />,
    );
    const box = screen.getByRole("combobox") as HTMLInputElement;
    expect(box.value).toBe("foo.nec");
    expect(box.title).toBe("foo.nec, read as NEC-2");

    fireEvent.focus(box);
    const opt = (label: string) => screen.getByRole("option", { name: label });
    expect(opt("foo.ez").title).toBe("foo.ez");
    expect(opt("foo.nec").title).toBe("foo.nec, read as NEC-2");
    expect(opt("Dipole").hasAttribute("title")).toBe(false);
  });

  it("the closed picker has no hover on a catalog design", () => {
    render(
      <GeometryCombobox
        groups={[{ fam: "dipoles", label: "Dipoles", items: [CATALOG] }]}
        selected={CATALOG.name}
        currentLabel="Dipole"
        filter=""
        setFilter={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByRole("combobox").hasAttribute("title")).toBe(false);
  });
});
