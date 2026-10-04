// Crash reporting (AK#1851): a render error shows the fallback panel instead
// of a blank page, and the hosted instance gets exactly one report carrying
// only the message, the component stack and the version. A local workbench
// (its /capabilities says client_error_reports: false) gets none.
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { CrashProbe, ErrorBoundary } from "../components/ErrorBoundary";
import {
  MAX_REPORTS_PER_PAGE,
  reportClientError,
  resetClientErrorReports,
  scrubReportText,
} from "../lib/clientErrors";

type Call = { url: string; init?: RequestInit | undefined };

function stubServer(hosted: boolean): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === "/capabilities") {
        return {
          ok: true,
          json: async () => ({
            client_error_reports: hosted,
            versions: { antennaknobs: "0.96.0", momwire: "0.71.0" },
          }),
        } as Response;
      }
      return { ok: true, status: 204 } as Response;
    }),
  );
  return calls;
}

const reports = (calls: Call[]) => calls.filter((c) => c.url === "/client-error");

function Boom(): never {
  throw new Error("kaboom at https://app.antennaknobs.dev/?deck=SECRETDECKTEXT&x=1");
}

beforeEach(() => {
  resetClientErrorReports();
  // React logs the caught error to the console; the test reads the DOM.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the error boundary", () => {
  it("shows the reload panel and sends one scrubbed report, hosted", async () => {
    const calls = stubServer(true);
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert").textContent).toMatch(/Something broke/);
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    await waitFor(() => expect(reports(calls)).toHaveLength(1));
    const init = reports(calls)[0].init!;
    expect(init.method).toBe("POST");
    expect(init.keepalive).toBe(true);
    const body = JSON.parse(String(init.body));
    // Exactly the three fields: no URL, no user agent, nothing else.
    expect(Object.keys(body).sort()).toEqual(["component_stack", "message", "version"]);
    expect(body.version).toBe("0.96.0");
    expect(body.message).toContain("kaboom");
    expect(body.component_stack).toContain("Boom");
    // The deck the link carried never leaves the page.
    expect(String(init.body)).not.toContain("SECRETDECKTEXT");
    expect(body.message).toContain("https://app.antennaknobs.dev/");
  });

  it("reports nothing on a local workbench", async () => {
    const calls = stubServer(false);
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    // The one question asked: may this page report? The answer is no.
    await waitFor(() => expect(calls.map((c) => c.url)).toContain("/capabilities"));
    await new Promise((r) => setTimeout(r, 0));
    expect(reports(calls)).toHaveLength(0);
  });

  it("renders its children untouched when nothing throws", () => {
    stubServer(true);
    render(
      <ErrorBoundary>
        <CrashProbe />
        <p>fine</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("fine")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the reporter", () => {
  it("deduplicates per page load and stops after a few", async () => {
    const calls = stubServer(true);
    await reportClientError(new Error("same"));
    await reportClientError(new Error("same"));
    expect(reports(calls)).toHaveLength(1);
    for (let i = 0; i < 10; i++) await reportClientError(new Error(`other ${i}`));
    expect(reports(calls)).toHaveLength(MAX_REPORTS_PER_PAGE);
  });

  it("asks /capabilities once per page load", async () => {
    const calls = stubServer(true);
    await reportClientError(new Error("a"));
    await reportClientError(new Error("b"));
    expect(calls.filter((c) => c.url === "/capabilities")).toHaveLength(1);
  });

  it("cuts URL queries, fragments and deck parameters out of the text", () => {
    expect(scrubReportText("at https://h.dev/app?deck=ABC&v=1 (x)")).toBe("at https://h.dev/app (x)");
    expect(scrubReportText("GET /deck?deck=ABC failed")).toBe("GET /deck failed");
    expect(scrubReportText("open //h/x#frag now")).toBe("open //h/x now");
    expect(scrubReportText("deck=ZZZ")).toBe("deck=…");
    expect(scrubReportText("is it 5? yes")).toBe("is it 5? yes");
  });
});
