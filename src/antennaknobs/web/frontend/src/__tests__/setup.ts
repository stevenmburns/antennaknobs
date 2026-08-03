// Vitest setup for the component tests (see vitest.config.ts `setupFiles`).
//
// Testing Library normally unmounts between tests by registering its own
// afterEach at import time, but it looks for that hook on globalThis and this
// suite runs without `globals: true`. Verified empirically: without the hook
// below a component mounted in one test is still in document.body during the
// next, so getBy* queries throw on duplicate matches. Registering it here
// rather than per test file keeps the guarantee unconditional — a new
// component test cannot forget it.
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(cleanup);
