// The phone carousel as DesignSession wires it (#700 unit 4): the real prefs
// store, the real hook, the real dots row and the real picker sheet, over a
// stubbed scroll geometry. What it pins is the one contract the unit is about
// — carousel pages ARE the pinned set plus Info, in pin order — plus the four
// ways that mapping can be walked off: a view with no page, unpinning the page
// you are on, pinning a page while you stand somewhere, and Info's index
// moving under both.
//
// jsdom has no layout: clientWidth is 0, scrollLeft never moves, and
// Element.scrollTo does not exist, so scroll-snap cannot be exercised for
// real. The stubs below supply exactly the three geometry facts the hook reads
// (page width, scroll position, and a scrollTo that lands instantly), which
// turns a swipe into "put scrollLeft on a snap point and fire scroll" — the
// same event the browser delivers at the end of a fling.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { VIEW_META, VIEWS, mobileScreens, type View } from "../lib/view";
import { MobileDots } from "../components/session/MobileDots";
import { useMobileCarousel } from "../components/session/useMobileCarousel";
import { PIN_CAP, VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";

const W = 300; // one page wide; every snap point is a multiple of it
const ROSTER = VIEWS.map((v) => v.id);
const label = (id: View) => VIEW_META[id].label;

let scrollPos = 0;
let scrolls: number[] = [];
let origClientWidth: PropertyDescriptor | undefined;
let origScrollLeft: PropertyDescriptor | undefined;

beforeEach(() => {
  localStorage.clear();
  scrollPos = 0;
  scrolls = [];
  origClientWidth = Object.getOwnPropertyDescriptor(Element.prototype, "clientWidth");
  origScrollLeft = Object.getOwnPropertyDescriptor(Element.prototype, "scrollLeft");
  Object.defineProperty(Element.prototype, "clientWidth", {
    configurable: true,
    get: () => W,
  });
  Object.defineProperty(Element.prototype, "scrollLeft", {
    configurable: true,
    get: () => scrollPos,
    set: (v: number) => {
      scrollPos = v;
    },
  });
  // jsdom ships no Element.scrollTo at all. Landing instantly (rather than
  // recording and ignoring) is what makes a programmatic page change visible
  // to the next effect, exactly as a finished smooth scroll would be.
  Object.defineProperty(Element.prototype, "scrollTo", {
    configurable: true,
    writable: true,
    value: (o: ScrollToOptions) => {
      scrolls.push(o.left ?? 0);
      scrollPos = o.left ?? 0;
    },
  });
});

afterEach(() => {
  if (origClientWidth) Object.defineProperty(Element.prototype, "clientWidth", origClientWidth);
  if (origScrollLeft) Object.defineProperty(Element.prototype, "scrollLeft", origScrollLeft);
  delete (Element.prototype as unknown as Record<string, unknown>).scrollTo;
  vi.restoreAllMocks();
});

function seed(pinned: View[], seen: View[] = ROSTER) {
  localStorage.setItem(VIEW_PREFS_KEY, JSON.stringify({ pinned, seen }));
}

// DesignSession's mobile branch, minus the charts: same hook call, same
// derived screen list feeding both the pages and the dots, same sheet props.
function Mobile({
  isMobile = true,
  initialView = "antenna" as View,
}: {
  isMobile?: boolean;
  initialView?: View;
}) {
  const [view, setView] = useState<View>(initialView);
  const prefs = useViewPrefs();
  const car = useMobileCarousel({
    isMobile,
    orientation: "portrait",
    pinned: prefs.pinned,
    view,
    setView,
  });
  const screens = mobileScreens(prefs.pinned);
  return (
    <>
      <div data-testid="view">{view}</div>
      <div data-testid="index">{car.mobileIndex}</div>
      <div data-testid="pages">{screens.map((s) => s.id).join(",")}</div>
      <div
        data-testid="carousel"
        ref={car.mobileCarouselRef}
        onScroll={car.onMobileCarouselScroll}
      />
      <MobileDots
        screens={screens}
        index={car.mobileIndex}
        goToScreen={car.goToMobileScreen}
        view={view}
        pinned={prefs.pinned}
        newIds={prefs.newIds}
        togglePin={prefs.togglePin}
        movePin={prefs.movePin}
        markRosterSeen={prefs.markRosterSeen}
      />
    </>
  );
}

const probe = (id: string) => screen.getByTestId(id).textContent;
const frame = () => new Promise((r) => requestAnimationFrame(() => r(null)));

// A finished swipe: the snap point becomes the scroll position and the browser
// delivers one scroll event. The handler is rAF-throttled, hence the frames.
//
// The leading drain is not ceremony: the re-centre effect queues a frame every
// time the index changes, and here scrollTo lands instantly, so an undrained
// frame from the previous gesture would re-centre the OLD page on top of this
// one. On a phone those frames run milliseconds after the commit, long before
// the next swipe — draining is what makes the simulation match that.
async function swipeTo(i: number) {
  await act(async () => {
    await frame();
  });
  scrollPos = i * W;
  await act(async () => {
    fireEvent.scroll(screen.getByTestId("carousel"));
    await frame();
  });
}

const dots = () =>
  screen.getAllByRole("button", { name: /^Show / }).map((b) => b.getAttribute("title"));
const openSheet = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: "All views" }));
const sheetRow = (id: View) => screen.getByRole("menuitem", { name: label(id) });
const dot = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

const TWO: View[] = ["smith", "antenna"];
const FOUR: View[] = ["smith", "antenna", "vswr", "azimuth"];
const SIX: View[] = ["smith", "antenna", "vswr", "azimuth", "schematic", "gamma"];

// --- 1. Pages and dots ------------------------------------------------------

describe("the carousel's pages", () => {
  it.each([
    ["2 pins", TWO],
    ["4 pins", FOUR],
    ["6 pins", SIX],
  ])("are the pinned views plus Info, one dot each, at %s", (_n, pinned) => {
    seed(pinned);
    render(<Mobile initialView={pinned[0]} />);
    expect(probe("pages")).toBe([...pinned, "info"].join(","));
    // One dot per page and nothing else — an unpinned view has neither.
    expect(dots()).toEqual([...pinned.map(label), "Info"]);
    // The overflow affordance rides the row but is not a dot.
    expect(screen.getByRole("button", { name: "All views" })).toBeTruthy();
  });

  it("gives an unpinned view no page at all", () => {
    seed(TWO);
    render(<Mobile initialView="smith" />);
    for (const id of ROSTER.filter((v) => !TWO.includes(v))) {
      expect(screen.queryByRole("button", { name: `Show ${label(id)}` })).toBeNull();
    }
  });
});

// --- 2. Index ↔ view mapping ------------------------------------------------

describe("a swipe", () => {
  it.each([
    ["2 pins", TWO],
    ["4 pins", FOUR],
    ["6 pins", SIX],
  ])("maps every page index onto the pin at that index, at %s", async (_n, pinned) => {
    seed(pinned);
    render(<Mobile initialView={pinned[0]} />);
    for (let i = 0; i < pinned.length; i++) {
      await swipeTo(i);
      expect(probe("index")).toBe(String(i));
      expect(probe("view")).toBe(pinned[i]);
    }
  });

  it.each([
    ["2 pins", TWO],
    ["4 pins", FOUR],
    ["6 pins", SIX],
  ])("onto Info leaves `view` parked on the last chart page, at %s", async (_n, pinned) => {
    seed(pinned);
    render(<Mobile initialView={pinned[0]} />);
    await swipeTo(pinned.length - 1);
    await swipeTo(pinned.length); // Info
    expect(probe("index")).toBe(String(pinned.length));
    expect(probe("view")).toBe(pinned[pinned.length - 1]);
  });
});

describe("a dot tap", () => {
  it("pages to that pin and scrolls there", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await user.click(screen.getByRole("button", { name: `Show ${label("vswr")}` }));
    expect(probe("view")).toBe("vswr");
    expect(probe("index")).toBe("2");
    expect(scrolls.at(-1)).toBe(2 * W);
  });

  it("reaches Info without moving `view` off the last chart", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await user.click(screen.getByRole("button", { name: `Show ${label("azimuth")}` }));
    await user.click(screen.getByRole("button", { name: "Show Info" }));
    expect(probe("index")).toBe("4");
    expect(probe("view")).toBe("azimuth");
    expect(scrolls.at(-1)).toBe(4 * W);
  });
});

// --- 3. The sheet -----------------------------------------------------------

describe("the ⋯ affordance", () => {
  it("opens the whole roster as a sheet, in registry order", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    expect(screen.queryByRole("menu")).toBeNull();
    await openSheet(user);
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(
      screen.getAllByRole("menuitem").map((el) => el.textContent?.replace(/NEW$/, "")),
    ).toEqual(ROSTER.map(label));
  });

  it("closes on a backdrop click", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    // document, not container: the sheet portals to <body> (a transformed
    // ancestor — .mobile-dots — would otherwise hijack its fixed
    // positioning), so it is deliberately NOT in the render container.
    await user.click(document.querySelector(".view-sheet-backdrop") as Element);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes on the sheet's own ✕ — dismissal must not depend on backdrop real estate", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("portals the sheet out of the transformed dots row", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    // The regression this pins: .mobile-dots centers itself with a CSS
    // transform, and a transformed ancestor is the containing block for
    // position:fixed descendants — a sheet rendered inside it was "fixed"
    // to the dots strip (clipped, backdrop useless). The sheet must never
    // again be a DOM descendant of the dots row.
    const sheet = document.querySelector(".view-sheet") as Element;
    expect(sheet).toBeTruthy();
    expect(sheet.closest(".mobile-dots")).toBeNull();
  });
});

describe("a sheet row tap", () => {
  // Hard case 3. A peek would have made `view` schematic with no page behind
  // it; on mobile the row is the pin, and the new page lands at the end.
  it("pins the view — it does NOT peek it — and appends its page", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    await swipeTo(1);
    scrolls = [];
    await openSheet(user);
    await user.click(sheetRow("schematic"));
    expect(probe("pages")).toBe("smith,antenna,schematic,info");
    // The page under the thumb neither moves nor is scrolled away from.
    expect(probe("view")).toBe("antenna");
    expect(probe("index")).toBe("1");
    expect(scrolls).toEqual([]);
    // Curating is a run of gestures: the sheet stays up.
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(dots()).toEqual([label("smith"), label("antenna"), label("schematic"), "Info"]);
  });

  // Hard case 2.
  it("unpins the page you are on, landing on its successor with the sheet still open", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await swipeTo(1); // antenna
    await openSheet(user);
    await user.click(sheetRow("antenna"));
    expect(probe("pages")).toBe("smith,vswr,azimuth,info");
    // Same slot, new occupant — the page that slid into it.
    expect(probe("index")).toBe("1");
    expect(probe("view")).toBe("vswr");
    expect(screen.getByRole("menu")).toBeTruthy();
  });

  it("clamps onto the new last page when the unpinned one was last", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await swipeTo(3); // azimuth, the last chart page
    await openSheet(user);
    await user.click(sheetRow("azimuth"));
    expect(probe("index")).toBe("2");
    expect(probe("view")).toBe("vswr");
    expect(scrolls.at(-1)).toBe(2 * W);
  });

  // Hard case 4: Info's index is pinned.length, so both gestures move it.
  it("moves Info under a user parked on it, without unparking them", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    await swipeTo(1); // antenna
    await swipeTo(2); // Info, parked on antenna
    await openSheet(user);
    await user.click(sheetRow("schematic"));
    expect(probe("index")).toBe("3");
    expect(probe("view")).toBe("antenna"); // still parked where Info found it
    await user.click(sheetRow("schematic")); // and back
    expect(probe("index")).toBe("2");
    expect(probe("view")).toBe("antenna");
  });

  it("re-parks `view` when the page Info parked it on is unpinned", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await swipeTo(3); // azimuth
    await swipeTo(4); // Info, parked on azimuth
    await openSheet(user);
    await user.click(sheetRow("azimuth"));
    expect(probe("index")).toBe("3"); // Info, one page earlier
    expect(probe("view")).toBe("vswr"); // the new last chart page
  });
});

// --- 3b. Reorder buttons (issue #714) — same rows, so the sheet inherits ----
//     them for free; this proves the carousel's page order (mobileScreens,
//     which `pages` above is built from) follows a reorder same as it
//     follows a pin/unpin.

describe("a sheet reorder", () => {
  it("moves a page earlier and the carousel's page order follows", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    await user.click(dot(`Move ${label("vswr")} earlier`));
    expect(probe("pages")).toBe(["smith", "vswr", "antenna", "azimuth", "info"].join(","));
    const reordered: View[] = ["smith", "vswr", "antenna", "azimuth"];
    expect(dots()).toEqual([...reordered.map(label), "Info"]);
  });

  it("is absent for an unpinned row", async () => {
    const user = userEvent.setup();
    seed(TWO);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    expect(
      screen.queryByRole("button", { name: `Move ${label("schematic")} earlier` }),
    ).toBeNull();
  });

  it("is disabled at the boundaries", async () => {
    const user = userEvent.setup();
    seed(FOUR);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    expect(dot(`Move ${label(FOUR[0])} earlier`).disabled).toBe(true);
    expect(dot(`Move ${label(FOUR[FOUR.length - 1])} later`).disabled).toBe(true);
  });
});

// --- 4. Cap and floor (the sheet reuses togglePin, so it inherits both) ------

describe("the sheet's disabled states", () => {
  it(`refuses a ${PIN_CAP + 1}th page, on the row as well as the dot`, async () => {
    const user = userEvent.setup();
    seed(SIX);
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    const spare = ROSTER.filter((id) => !SIX.includes(id));
    expect(spare.length).toBeGreaterThan(0); // the roster can overrun the cap
    for (const id of spare) {
      expect((sheetRow(id) as HTMLButtonElement).disabled).toBe(true);
      expect(sheetRow(id).getAttribute("title")).toBe("Unpin a view first");
      expect(dot(`Pin ${label(id)}`).disabled).toBe(true);
      await user.click(sheetRow(id));
    }
    expect(probe("pages")).toBe([...SIX, "info"].join(","));
  });

  it("refuses to drop the last page", async () => {
    const user = userEvent.setup();
    seed(["gamma"]);
    render(<Mobile initialView="gamma" />);
    await openSheet(user);
    expect((sheetRow("gamma") as HTMLButtonElement).disabled).toBe(true);
    expect(sheetRow("gamma").getAttribute("title")).toBe("Keep at least one view pinned");
    expect(dot(`Unpin ${label("gamma")}`).disabled).toBe(true);
    await user.click(sheetRow("gamma"));
    expect(probe("pages")).toBe("gamma,info");
  });
});

// --- 5. NEW badges ----------------------------------------------------------

describe("the sheet's NEW badges", () => {
  it("announces unseen views and marks the roster seen on open", async () => {
    const user = userEvent.setup();
    const unseen: View[] = ["gamma", "vswr"];
    seed(
      TWO,
      ROSTER.filter((id) => !unseen.includes(id)),
    );
    render(<Mobile initialView="smith" />);
    await openSheet(user);
    expect(screen.getAllByText("NEW").map((el) => el.parentElement?.textContent)).toEqual(
      unseen.map((id) => `${label(id)}NEW`),
    );
    // Opening IS "you have now been shown the roster" — but the badges must
    // survive the open that revealed them.
    expect(JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}").seen).toEqual(
      expect.arrayContaining(ROSTER),
    );
    await openSheet(user); // close
    await openSheet(user); // and back
    expect(screen.queryByText("NEW")).toBeNull();
  });
});

// --- 6. A view with no page (hard case 1) -----------------------------------

describe("a `view` that is not pinned", () => {
  it("snaps onto the first page rather than stranding on a pageless view", () => {
    seed(FOUR);
    // Stored prefs that do not include the view the session starts on — the
    // carousel would otherwise sit on a page that has no dot.
    render(<Mobile initialView="elevation" />);
    expect(probe("view")).toBe("smith");
    expect(probe("index")).toBe("0");
  });

  it("rescues a peek carried across the desktop → mobile breakpoint", async () => {
    seed(FOUR);
    // Desktop peek: `schematic` is active but unpinned, which is legal there
    // (the rail shows every pin and the peek costs no slot).
    const { rerender } = render(<Mobile isMobile={false} initialView="schematic" />);
    expect(probe("view")).toBe("schematic");
    await act(async () => {
      rerender(<Mobile isMobile initialView="schematic" />);
    });
    expect(probe("view")).toBe("smith");
    expect(probe("index")).toBe("0");
  });
});
