import { describe, expect, it } from "vitest";
import css from "../styles.css?raw";

// The floating solve readout's height cap must hold for the WHOLE card. Under
// content-box it limited only the content: the padding (the minimize button's
// reserved top included) and border landed on top, and a 42-element LPDA's TL
// power budget at 125 % zoom pushed the card 40 px past its cap, its top and
// minimize button off the window. jsdom has no layout, so this pins the rule
// itself; the measured case is in the PR.
const rule = css.match(/\n\.stage-readout\s*\{([^}]*)\}/)?.[1] ?? "";

describe(".stage-readout box", () => {
  it("is border-box, so max-height includes padding and border", () => {
    expect(rule).toMatch(/box-sizing:\s*border-box/);
    expect(rule).toMatch(/max-height:\s*calc\(100%/);
  });

  it("adds the padding and border back to its widths, so the card keeps its width", () => {
    expect(rule).toMatch(/min-width:\s*calc\(172px \+ 2 \* var\(--space-5\) \+ 2px\)/);
    expect(rule).toMatch(/max-width:\s*calc\(240px \+ 2 \* var\(--space-5\) \+ 2px\)/);
  });
});
