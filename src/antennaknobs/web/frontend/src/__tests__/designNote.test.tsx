// AK#2291: a design note's inline list (a SimNEC script's directives not
// applied) folds to one line with its count, and opens to every entry. The
// prose around it is untouched, and a list the note does not carry verbatim
// is not folded at all, so nothing can be hidden that cannot be opened.
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DesignNote } from "../components/session/DesignNote";

const LEAD = "NEC-portal directives not applied";
const ITEMS = ["line 4: $probe.Report(1)", "line 7: Plot(Zin)", "line 9: Tidy()"];
const NOTES = `SimNEC circuit elements not imported: SCOPE; ${LEAD}: ${ITEMS.join("; ")}. Every wire's segment count is held.`;

describe("DesignNote", () => {
  it("folds the directives into one collapsed line with the count", () => {
    render(<DesignNote notes={NOTES} lists={[{ lead: LEAD, items: ITEMS }]} />);
    const fold = screen.getByRole("button", { name: `${LEAD} (3)` });
    expect(fold.getAttribute("aria-expanded")).toBe("false");
    for (const item of ITEMS) expect(screen.queryByText(item)).toBeNull();
    // The prose either side stays.
    expect(screen.getByText(/circuit elements not imported: SCOPE/)).toBeTruthy();
    expect(screen.getByText(/segment count is held/)).toBeTruthy();
  });

  it("opens to every entry", async () => {
    render(<DesignNote notes={NOTES} lists={[{ lead: LEAD, items: ITEMS }]} />);
    await userEvent.click(screen.getByRole("button", { name: `${LEAD} (3)` }));
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(ITEMS);
  });

  it("shows the note whole when it does not carry the list verbatim", () => {
    render(<DesignNote notes={NOTES} lists={[{ lead: LEAD, items: ["something else"] }]} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/Plot\(Zin\)/)).toBeTruthy();
  });

  it("shows the note as written with no lists", () => {
    const { container } = render(<DesignNote notes={NOTES} />);
    expect(container.textContent).toBe(NOTES);
  });
});
