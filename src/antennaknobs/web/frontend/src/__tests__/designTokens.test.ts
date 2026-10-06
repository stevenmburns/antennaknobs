// Drift guards for the design pass (AK#1757 unit 6, AK#1807), read off the
// source text: a pass that is not guarded is undone by the next feature.
//
//   - Corners come from the radius tokens. A literal border-radius length
//     outside the token definitions needs a `token-exempt:` comment on its
//     line saying why; 50% (a circle) is a shape and needs none.
//   - The chart elements the workbench arc added sit on the tokens their
//     role names (overlays --r-md, controls --r-sm).
//   - The canvas charts take their type from the chart ramp and draw on the
//     chart scale: no font-size literal in components/charts, and every
//     chart canvas is sized by fitChartCanvas.
//   - The phone's chart scale is 1 under the SAME query the JS layout uses.
import { describe, expect, it } from "vitest";
import stylesSrc from "../styles.css?raw";
import { CHART_TYPE } from "../components/charts/chartScale";
import { MOBILE_MEDIA_QUERY } from "../components/hooks";

const chartSources = import.meta.glob("../components/charts/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** The declarations of the first rule whose selector is exactly `sel`. */
function ruleBody(css: string, sel: string): string {
  const at = css.indexOf(`\n${sel} {`);
  if (at < 0) throw new Error(`no rule ${sel}`);
  return css.slice(at, css.indexOf("}", at));
}

const RADIUS_OK = /^(0|50%|var\(--r-(xs|sm|md|lg)\))$/;

/** Every border-radius line whose value is not made of tokens, 0 or 50%,
 *  and which carries no `token-exempt:` note. */
function untokenedRadii(css: string): string[] {
  const bad: string[] = [];
  css.split("\n").forEach((line, i) => {
    const m = /(?:^|[\s;{])border-radius:\s*([^;]+);/.exec(line);
    if (!m) return;
    if (line.includes("token-exempt:")) return;
    const parts = m[1].trim().split(/\s+/);
    if (!parts.every((p) => RADIUS_OK.test(p))) bad.push(`${i + 1}: ${line.trim()}`);
  });
  return bad;
}

describe("radius tokens", () => {
  it("every border-radius is a token, 0, 50% or an annotated exception", () => {
    expect(untokenedRadii(stylesSrc)).toEqual([]);
  });

  it("the guard catches a literal", () => {
    expect(untokenedRadii(".x {\n  border-radius: 5px;\n}")).toHaveLength(1);
    expect(untokenedRadii(".x {\n  border-radius: 0 0 4px var(--r-sm);\n}")).toHaveLength(1);
    expect(untokenedRadii(".x {\n  border-radius: 3px; /* token-exempt: pill */\n}")).toEqual([]);
  });

  it("the token set is defined once, in :root", () => {
    for (const t of ["--r-xs", "--r-sm", "--r-md", "--r-lg"]) {
      expect(stylesSrc.match(new RegExp(`^\\s*${t}:`, "gm"))).toHaveLength(1);
    }
  });
});

// The arc's chart elements and the token their role takes (styles.css's
// token comments: --r-sm inputs/buttons, --r-md cards/toggles/overlays).
const ROLE_RADIUS: Record<string, string> = {
  ".chart-legend": "var(--r-md)", // overlay
  ".chart-legend-chip": "var(--r-md)", // the legend's collapsed toggle
  ".chart-note-pop": "var(--r-md)", // overlay
  ".knob-menu": "var(--r-md)", // the cross and range popovers
  ".chart-note-btn": "var(--r-sm)", // button
  ".zinf-info-btn": "var(--r-sm)",
  ".zparam-xlog-btn": "var(--r-sm)", // lin/log and "values"
  ".zparam-run": "var(--r-sm)", // Run, and the cross button
  ".zparam-reset": "var(--r-sm)", // duplicate, close
  ".chart-table-copy": "var(--r-sm)",
  ".grid-cell": "var(--r-md)", // a duplicate chart's cell
};

describe("the arc's chart elements on their role's tokens", () => {
  for (const [sel, radius] of Object.entries(ROLE_RADIUS)) {
    it(`${sel} takes ${radius}`, () => {
      expect(ruleBody(stylesSrc, sel)).toMatch(
        new RegExp(`border-radius: ${radius.replace(/[()]/g, "\\$&")};`),
      );
    });
  }

  it("popovers share one elevation", () => {
    for (const sel of [".knob-menu", ".chart-note-pop"]) {
      expect(ruleBody(stylesSrc, sel)).toContain("box-shadow: var(--elev-pop);");
    }
  });

  it("the legend, chip and chart buttons size from the chart scale", () => {
    for (const sel of [".chart-legend", ".chart-legend-chip"]) {
      expect(ruleBody(stylesSrc, sel)).toContain(
        `font-size: calc(${CHART_TYPE.label}px * var(--chart-scale));`,
      );
    }
    expect(ruleBody(stylesSrc, ".zparam-xlog-btn")).toContain(
      `font-size: calc(${CHART_TYPE.tick}px * var(--chart-scale));`,
    );
  });

  it("every chart-scaled type size is on the chart ramp", () => {
    const ramp = new Set<number>(Object.values(CHART_TYPE));
    const sizes = [...stylesSrc.matchAll(/(?:font-size:|font:)\s*calc\((\d+(?:\.\d+)?)px \* var\(--chart-scale\)\)/g)];
    expect(sizes.length).toBeGreaterThan(0);
    expect(sizes.map((m) => Number(m[1])).filter((n) => !ramp.has(n))).toEqual([]);
  });
});

describe("the chart scale in CSS", () => {
  it("1.25 on the root, 1 under the phone query (hooks.ts's own string), 1 in a thumbnail", () => {
    expect(ruleBody(stylesSrc, ":root")).toMatch(/--chart-scale: 1\.25;/);
    const phone = `@media ${MOBILE_MEDIA_QUERY} {\n  :root {\n    --chart-scale: 1;`;
    expect(stylesSrc).toContain(phone);
    expect(ruleBody(stylesSrc, ".thumb-scale")).toContain("--chart-scale: 1;");
  });
});

/** Font sizes written as literals in chart canvas code: a `ctx.font` not
 *  taken from CHART_FONT / chartFontPx, or an `NNpx <face>` string. */
function chartFontLiterals(src: string): string[] {
  const bad: string[] = [];
  src.split("\n").forEach((line, i) => {
    const code = line.replace(/\/\/.*$/, "");
    const assign = /\.font\s*=\s*([^;]+)/.exec(code);
    if (assign && !/^(CHART_FONT\.\w+|chartFontPx\()/.test(assign[1].trim())) {
      bad.push(`${i + 1}: ${line.trim()}`);
    } else if (/\d+(\.\d+)?px\s+(ui-monospace|monospace|sans-serif|serif|system-ui|"?IBM)/.test(code)) {
      bad.push(`${i + 1}: ${line.trim()}`);
    }
  });
  return bad;
}

describe("canvas type from the chart ramp", () => {
  const files = Object.entries(chartSources).filter(([p]) => !p.endsWith("chartScale.ts"));

  it("the glob found the chart sources", () => {
    expect(files.map(([p]) => p)).toEqual(
      expect.arrayContaining([
        "../components/charts/ZParamChart.tsx",
        "../components/charts/SmithChart.tsx",
        "../components/charts/SweepChart.tsx",
        "../components/charts/FarFieldChart.tsx",
      ]),
    );
  });

  it("no font-size literal in components/charts", () => {
    const bad = files.flatMap(([p, src]) => chartFontLiterals(src).map((l) => `${p}:${l}`));
    expect(bad).toEqual([]);
  });

  it("the guard catches a literal", () => {
    expect(chartFontLiterals('ctx.font = "10px ui-monospace, monospace";')).toHaveLength(1);
    expect(chartFontLiterals("ctx.font = `${n}px ui-monospace`;")).toHaveLength(1);
    expect(chartFontLiterals("ctx.font = CHART_FONT.tick;")).toEqual([]);
  });

  it("every chart canvas is sized on the chart scale (the antenna view has its own)", () => {
    const drawn = files.filter(([p, src]) => src.includes('getContext("2d")') && !p.endsWith("CurrentCanvas.tsx"));
    expect(drawn.length).toBeGreaterThanOrEqual(5);
    for (const [p, src] of drawn) {
      // A chart may give a height of its own (the map's plot, its legend
      // lines under it): still the one sizing function, on the chart scale.
      expect(src, p).toMatch(/fitChartCanvas\(canvas, ctx, size, k(\)|, \w+\))/);
      expect(src, p).toContain("useChartScale()");
      expect(src, p).not.toMatch(/setTransform\(dpr, 0, 0, dpr/);
    }
  });
});
