// Crash reports for the hosted app (AK#1851).
//
// The error boundary (components/ErrorBoundary.tsx) and the window's `error` /
// `unhandledrejection` handlers report here; this POSTs `/client-error`, where
// the hosted server writes one log line. A report carries exactly three
// fields: the error's message, React's component stack (the boundary's catch
// only) and the app version. No URL, no user agent, no deck, no knob values;
// anything shaped like a URL query is cut out here and again on the server,
// because the `?deck=` link carries a visitor's whole deck.
//
// Reporting is OFF until the server says otherwise: the first report asks
// /capabilities once, and only `client_error_reports: true` (the hosted
// instance) turns it on. A local workbench answers false, so a local build
// never reports anywhere (the #846 rule). Deduplicated per page load, and a
// few reports at most per page load.

export const MAX_REPORTS_PER_PAGE = 3;
const MESSAGE_MAX = 500;
const STACK_MAX = 4000;

type ReportConfig = { enabled: boolean; version: string };

let configPromise: Promise<ReportConfig> | null = null;
const seen = new Set<string>();
let sent = 0;

/** Test seam: forget this page load's reports and the server's answer. */
export function resetClientErrorReports(): void {
  configPromise = null;
  seen.clear();
  sent = 0;
}

/** `text` with every URL query and fragment and any `deck=` run cut out. */
export function scrubReportText(text: string): string {
  return text
    .replace(/((?:[a-z][a-z0-9+.-]*:)?\/\/[^\s?#)'"]*)[?#][^\s)'"]*/gi, "$1")
    .replace(/\?[^\s)'"]*=[^\s)'"]*/g, "")
    .replace(/\bdeck=[^\s&)'"]*/g, "deck=…");
}

function bounded(text: string, cap: number): string {
  const t = scrubReportText(text);
  return t.length <= cap ? t : `${t.slice(0, cap)}…`;
}

function reportConfig(): Promise<ReportConfig> {
  configPromise ??= (async () => {
    try {
      const r = await fetch("/capabilities");
      if (!r.ok) return { enabled: false, version: "unknown" };
      const c = (await r.json()) as {
        client_error_reports?: unknown;
        versions?: { antennaknobs?: unknown };
      };
      const v = c.versions?.antennaknobs;
      return {
        enabled: c.client_error_reports === true,
        version: typeof v === "string" ? v : "unknown",
      };
    } catch {
      return { enabled: false, version: "unknown" };
    }
  })();
  return configPromise;
}

function messageOf(error: unknown): string {
  if (error instanceof Error) return `${error.name}: ${error.message}`;
  if (typeof error === "string") return error;
  try {
    return String(error);
  } catch {
    return "unprintable error";
  }
}

/** Report one error. Resolves once it is sent or declined; never throws. */
export async function reportClientError(
  error: unknown,
  componentStack?: string | null,
): Promise<void> {
  const message = bounded(messageOf(error), MESSAGE_MAX);
  const component_stack = bounded(componentStack ?? "", STACK_MAX);
  const key = `${message}\n${component_stack}`;
  if (seen.has(key) || sent >= MAX_REPORTS_PER_PAGE) return;
  seen.add(key);
  sent += 1;
  const { enabled, version } = await reportConfig();
  if (!enabled) return;
  try {
    await fetch("/client-error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, component_stack, version }),
      keepalive: true,
    });
  } catch {
    // A report that cannot be sent is dropped: reporting must never be a
    // second failure.
  }
}

let installed = false;

/** The window's uncaught errors and rejections, reported. Once per page. */
export function installGlobalErrorReports(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  window.addEventListener("error", (e) => {
    void reportClientError(e.error ?? e.message);
  });
  window.addEventListener("unhandledrejection", (e) => {
    void reportClientError(e.reason);
  });
}
