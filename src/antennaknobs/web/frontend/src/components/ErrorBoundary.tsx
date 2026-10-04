import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportClientError } from "../lib/clientErrors";

// The app's top-level error boundary (AK#1851). Before it, a render error
// unmounted the whole tree and left a blank page with no trace anywhere; now
// the visitor gets a panel that says so and a reload, and the hosted
// instance gets one report (lib/clientErrors.ts says what it carries).
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    void reportClientError(error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="crash-panel" role="alert">
        <p>Something broke on this page.</p>
        <p className="crash-panel-note">
          Reloading usually brings it back. A link you opened (a design, or
          your own deck) reloads with it.
        </p>
        <button type="button" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    );
  }
}

/** `?crash-test` in the page's address throws during render, so the hosted
 *  boundary and its `client-error:` log line can be checked end to end on
 *  the deployed app (AK#1851's real-app gate). Inert without the flag. */
export function CrashProbe(): null {
  if (new URLSearchParams(window.location.search).has("crash-test")) {
    throw new Error("crash-test: the error boundary's own probe");
  }
  return null;
}
