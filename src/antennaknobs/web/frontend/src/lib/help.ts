// Where the header's Help button points (AK#1739). The one place the URL is
// chosen: a context-aware Help (the SimNEC import page when a .ssn is loaded,
// the optimizer page from the optimize gear) is later work, and it grows
// HERE — give helpUrl() an argument describing the context and branch on it
// — so the button itself never learns a URL.
//
// The docs site is the public one even for a local install: the workbench
// ships no copy of the docs, and a Help that 404s offline is no worse than a
// Help that is missing.

/** The docs site's origin. `site/astro.config.mjs` serves from this. */
export const DOCS_ORIGIN = "https://antennaknobs.dev";

/** The "using the workbench" page: site/src/content/docs/reference/web.md.
 *  Trailing slash included — the bare path answers with a 301. */
export const WORKBENCH_DOCS_PATH = "/reference/web/";

/** The URL the Help button opens, in a new tab. */
export function helpUrl(): string {
  return DOCS_ORIGIN + WORKBENCH_DOCS_PATH;
}
