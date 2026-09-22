// AK#1657 — the per-feed table labels its index and its drive. "feed 0 ∠0°"
// read as a phasor, 0 A at 0° (AC6LA). The index stays 0-based; the drive
// gets its own column, with a magnitude and unit wherever the server says
// whether it is volts or amps, and the phase alone where it does not.
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { SolveReadout } from "../components/results/SolveReadout";
import type { FeedEntry, SolveResponse } from "../lib/api";
import { feedDriveText } from "../lib/format";

const feed = (extra: Partial<FeedEntry>): FeedEntry => ({
  wire_index: 0,
  knot_index: 0,
  z_re: 35.6,
  z_im: -24.6,
  v_re: 1,
  v_im: 0,
  ...extra,
});

function renderFeeds(feeds: FeedEntry[]) {
  const result = {
    geometry: "user.cardioid",
    wires: [],
    feed_wire_index: 0,
    feed_knot_index: 0,
    z_in_re: feeds[0].z_re,
    z_in_im: feeds[0].z_im,
    design_freq_mhz: 7,
    measurement_freq_mhz: 7,
    solve_ms: 1,
    z0_ohms: 50,
    feeds,
  } as unknown as SolveResponse;
  return render(
    <SolveReadout
      result={result}
      rttMs={null}
      currentExample={undefined}
      effectiveMultiFeed={true}
      normCheck={null}
      normCheckEnabled={false}
    />,
  );
}

describe("feedDriveText", () => {
  it("gives a current source its amps", () => {
    expect(
      feedDriveText(feed({ v_re: 0, v_im: -1.414214, drive_unit: "A" })),
    ).toBe("1.414 A ∠−90°");
  });

  it("gives a voltage source its volts", () => {
    expect(feedDriveText(feed({ v_re: 1, v_im: 0, drive_unit: "V" }))).toBe(
      "1 V ∠0°",
    );
  });

  it("shows the phase alone when the server does not say which (older server, padded feed)", () => {
    expect(feedDriveText(feed({ v_re: 0, v_im: 1 }))).toBe("∠90°");
    expect(feedDriveText(feed({ v_re: 1, v_im: 0, drive_unit: null }))).toBe(
      "∠0°",
    );
  });
});

describe("the per-feed table (AK#1657)", () => {
  it("has a header row naming the three columns", () => {
    renderFeeds([
      feed({ drive_unit: "A", v_re: 1.414214 }),
      feed({ drive_unit: "A", v_im: -1.414214, v_re: 0 }),
    ]);
    const table = screen.getByRole("table", {
      name: /per-feed drive and impedance/,
    });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(["feed", "drive", "Z (V/I)"]);
  });

  it("puts the 0-based index, the drive and Z in separate cells", () => {
    renderFeeds([
      feed({ drive_unit: "A", v_re: 1.414214, z_re: 32.1, z_im: -25.4 }),
      feed({
        drive_unit: "A",
        v_re: 0,
        v_im: -1.414214,
        z_re: 63.4,
        z_im: 10.3,
      }),
    ]);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    const cells = rows.map((r) =>
      within(r)
        .getAllByRole("cell")
        .map((c) => c.textContent?.replace(/\s+/g, " ").trim()),
    );
    expect(cells).toEqual([
      ["0", "1.414 A ∠0°", "32.1 − j25.4 Ω"],
      ["1", "1.414 A ∠−90°", "63.4 + j10.3 Ω"],
    ]);
    // The old one-line spelling is gone.
    expect(screen.queryByText(/feed 0 ∠/)).toBeNull();
  });
});
