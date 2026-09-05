// Soil constants as knobs (issue #1173): the ground panel's soil sub-panel,
// the preset/value derivation, and the request + signature plumbing.
//
// Every visibility assertion is paired with an absence assertion, following
// GroundPanel.test.tsx — a presence-only test still passes if the
// conditional that gates it is deleted.
//
// The soil schema is server-supplied (GET /capabilities →
// adapter.soil_presets_schema / soil_ranges_schema), so like the terrain
// fixtures these are modeled on the type rather than imported from a
// non-existent frontend default. The Python twin
// (tests/test_soil_knobs_1173.py) pins the real payload's shape.
import type { ComponentProps } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GroundPanel } from "../components/session/GroundPanel";
import {
  activeSoilPreset,
  defaultSoil,
  soilSummaryLabel,
  type SoilPresetSchema,
  type SoilRanges,
} from "../lib/ground";
import { solveSignature } from "../lib/solveSignature";
import type { SolveRequest } from "../lib/api";
import { entry } from "./backendFixtures";

// --- fixtures --------------------------------------------------------------

const PRESETS: SoilPresetSchema[] = [
  { name: "poor", label: "poor", eps_r: 5, sigma: 0.001, tooltip: "Rocky." },
  { name: "average", label: "average", eps_r: 13, sigma: 0.005, tooltip: "Pastoral." },
  { name: "salt-water", label: "salt water", eps_r: 81, sigma: 5, tooltip: "Sea." },
];

const RANGES: SoilRanges = {
  eps_r: { min: 1, max: 81, default: 10 },
  sigma: { min: 1e-4, max: 5, default: 0.002, log: true },
};

function panelProps(
  over: Partial<ComponentProps<typeof GroundPanel>> = {},
): ComponentProps<typeof GroundPanel> {
  return {
    backend: entry("bspline"),
    groundEnabled: true,
    setGroundEnabled: vi.fn(),
    groundType: "finite",
    setGroundType: vi.fn(),
    finiteGroundMethod: "fast",
    setFiniteGroundMethod: vi.fn(),
    terrainPresets: [],
    terrainPreset: "levee",
    setTerrainPreset: vi.fn(),
    terrainParams: {},
    setTerrainParams: vi.fn(),
    soil: { eps_r: 13, sigma: 0.005 },
    setSoil: vi.fn(),
    soilPresets: PRESETS,
    soilRanges: RANGES,
    ...over,
  };
}

// NumberField's <label> wraps only the caption/value spans, not the input, so
// there is no label→control association for getByLabelText to follow (same
// note as GroundPanel.test.tsx): locate the field by its caption text and
// step out to the sibling input. LogNumberField holds two inputs — the
// spinbutton is the authoritative linear one, the slider is role="slider".
function numberField(label: string): HTMLInputElement {
  const field = screen.getByText(label).closest(".field");
  if (!field) throw new Error(`no .field wrapper for "${label}"`);
  return within(field as HTMLElement).getByRole("spinbutton") as HTMLInputElement;
}

const EPS_LABEL = "εr (relative permittivity)";
const SIGMA_LABEL = "σ (conductivity, S/m)";

// --- the derivation --------------------------------------------------------

describe("activeSoilPreset", () => {
  it("names the preset a pair of values IS", () => {
    expect(activeSoilPreset({ eps_r: 13, sigma: 0.005 }, PRESETS)?.name).toBe(
      "average",
    );
  });

  it("returns null for a custom soil", () => {
    expect(activeSoilPreset({ eps_r: 14, sigma: 0.005 }, PRESETS)).toBeNull();
    expect(activeSoilPreset({ eps_r: 13, sigma: 0.006 }, PRESETS)).toBeNull();
  });

  it("survives a JSON float round-trip", () => {
    // The values reach the panel back through JSON; exact equality would
    // flicker the selection off for a preset the user just clicked.
    const round = JSON.parse(JSON.stringify({ eps_r: 20.0, sigma: 0.0303 }));
    const presets = [
      { name: "vg", label: "very good", eps_r: 20, sigma: 0.0303, tooltip: "" },
    ];
    expect(activeSoilPreset(round, presets)?.name).toBe("vg");
  });
});

describe("defaultSoil", () => {
  it("takes the served defaults", () => {
    expect(defaultSoil(RANGES)).toEqual({ eps_r: 10, sigma: 0.002 });
  });

  it("is null without served ranges — never a hardcoded 10/0.002", () => {
    expect(defaultSoil(null)).toBeNull();
  });
});

describe("soilSummaryLabel", () => {
  it("names a preset, else the numbers", () => {
    expect(soilSummaryLabel({ eps_r: 13, sigma: 0.005 }, PRESETS)).toBe("average");
    expect(soilSummaryLabel({ eps_r: 14, sigma: 0.005 }, PRESETS)).toContain("14");
  });
});

// --- the panel -------------------------------------------------------------

describe("GroundPanel soil sub-panel", () => {
  it("renders the presets and both knobs over finite ground", () => {
    render(<GroundPanel {...panelProps()} />);
    const group = screen.getByRole("radiogroup", { name: "Soil preset" });
    expect(within(group).getAllByRole("radio")).toHaveLength(PRESETS.length);
    expect(numberField(EPS_LABEL)).toBeTruthy();
    expect(numberField(SIGMA_LABEL)).toBeTruthy();
    // The conductivity knob is the log one — four and a half decades.
    const sigmaField = screen.getByText(SIGMA_LABEL).closest(".field");
    expect(
      within(sigmaField as HTMLElement).getByRole("slider"),
    ).toBeTruthy();
  });

  it("checks the radio matching the current values, and only that one", () => {
    render(<GroundPanel {...panelProps()} />);
    const group = screen.getByRole("radiogroup", { name: "Soil preset" });
    const checked = within(group)
      .getAllByRole("radio")
      .filter((r) => (r as HTMLInputElement).checked);
    expect(checked).toHaveLength(1);
    expect(screen.getByTitle(/Pastoral/)).toBeTruthy();
  });

  it("checks NO preset for a custom soil", () => {
    render(<GroundPanel {...panelProps({ soil: { eps_r: 14, sigma: 0.005 } })} />);
    const group = screen.getByRole("radiogroup", { name: "Soil preset" });
    expect(
      within(group)
        .getAllByRole("radio")
        .filter((r) => (r as HTMLInputElement).checked),
    ).toHaveLength(0);
    expect(screen.getByText("custom soil")).toBeTruthy();
  });

  it("sends a preset's BOTH constants when picked", async () => {
    const setSoil = vi.fn();
    render(<GroundPanel {...panelProps({ setSoil })} />);
    const group = screen.getByRole("radiogroup", { name: "Soil preset" });
    await userEvent.click(within(group).getByTitle("Sea."));
    expect(setSoil).toHaveBeenCalledWith({ eps_r: 81, sigma: 5 });
  });

  it("edits one constant without disturbing the other", async () => {
    const setSoil = vi.fn();
    render(<GroundPanel {...panelProps({ setSoil })} />);
    await userEvent.clear(numberField(EPS_LABEL));
    await userEvent.type(numberField(EPS_LABEL), "20");
    expect(setSoil).toHaveBeenLastCalledWith({ eps_r: 20, sigma: 0.005 });
  });

  it("takes its slider bounds from the server, not from a literal", () => {
    render(<GroundPanel {...panelProps()} />);
    const eps = numberField(EPS_LABEL);
    expect(eps.getAttribute("min")).toBe("1");
    expect(eps.getAttribute("max")).toBe("81");
    const sigma = numberField(SIGMA_LABEL);
    expect(sigma.getAttribute("max")).toBe("5");
  });

  // --- the absence half ----------------------------------------------------

  it("renders NO soil controls when the server describes no ranges", () => {
    render(<GroundPanel {...panelProps({ soilRanges: null })} />);
    expect(screen.queryByRole("radiogroup", { name: "Soil preset" })).toBeNull();
    expect(screen.queryByText(EPS_LABEL)).toBeNull();
  });

  it("renders NO soil controls over PEC ground", () => {
    render(<GroundPanel {...panelProps({ groundType: "pec" })} />);
    expect(screen.queryByRole("radiogroup", { name: "Soil preset" })).toBeNull();
  });

  it("renders NO soil controls when the ground plane is off", () => {
    render(<GroundPanel {...panelProps({ groundEnabled: false })} />);
    expect(screen.queryByRole("radiogroup", { name: "Soil preset" })).toBeNull();
  });

  it("still renders the knobs when the server serves ranges but no presets", () => {
    // Bounds and menu are separate facts; a preset-less server still gets
    // usable knobs.
    render(<GroundPanel {...panelProps({ soilPresets: [] })} />);
    expect(screen.queryByRole("radiogroup", { name: "Soil preset" })).toBeNull();
    expect(numberField(EPS_LABEL)).toBeTruthy();
  });

  it("no longer promises a fixed soil on the finite radio", () => {
    render(<GroundPanel {...panelProps()} />);
    expect(screen.queryByText(/εr=10/)).toBeNull();
  });
});

// --- the wire --------------------------------------------------------------

function req(over: Partial<SolveRequest> = {}): SolveRequest {
  return {
    geometry: "dipole",
    solver: "momwire",
    n_per_wire: 20,
    design_freq_mhz: 14,
    measurement_freq_mhz: 14,
    wire_radius: 0.001,
    ground: true,
    ground_fast: true,
    ground_model: "sommerfeld",
    ...over,
  } as SolveRequest;
}

describe("soil in the analysis signature", () => {
  it("a soil change re-fires the impedance analyses", () => {
    // The issue's ask 3 at the client end: a soil change must be a new
    // curve. solveSignature is exemption-based, so this passes by default —
    // pinned because an exemption entry could quietly remove it.
    const a = solveSignature(req({ soil: { eps_r: 13, sigma: 0.005 } }));
    const b = solveSignature(req({ soil: { eps_r: 81, sigma: 5 } }));
    expect(a).not.toBe(b);
  });

  it("the same soil is the same signature", () => {
    expect(solveSignature(req({ soil: { eps_r: 13, sigma: 0.005 } }))).toBe(
      solveSignature(req({ soil: { eps_r: 13, sigma: 0.005 } })),
    );
  });

  it("an absent soil and a default soil are NOT confused for each other", () => {
    // They must differ, which is exactly why the client omits the field at
    // the default rather than sending it: a default-soil request is then
    // byte-identical to a pre-#1173 one and reuses its cached curve.
    expect(solveSignature(req())).not.toBe(
      solveSignature(req({ soil: { eps_r: 10, sigma: 0.002 } })),
    );
  });
});
