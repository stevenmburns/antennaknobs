// Flat config (ESLint 9). Kept deliberately non-type-checked — typed linting
// (typescript-eslint's `recommendedTypeChecked`) needs a full `tsc` program
// build per lint run, which is the difference between sub-second and
// multi-second here. `npx tsc --noEmit` already gates type errors in CI and
// via `npm run build`; this config's job is style/correctness lint only.
import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import testingLibrary from "eslint-plugin-testing-library";

export default tseslint.config(
  {
    // dist/ (vite build output for local `npm run build`) and the actual
    // publish target (../static, outside this directory's own tree but
    // reachable via node_modules-style relative ignores) never carry source
    // to lint; node_modules is ESLint's own default ignore but stays explicit
    // since this project ignore list replaces rather than extends it.
    // coverage/ is `npm run test:coverage`'s v8 report output (its own
    // generated JS, e.g. block-navigation.js, is not this project's source).
    ignores: ["dist/**", "../static/**", "node_modules/**", "coverage/**"],
  },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // react-hooks was pinned to 5.2.0 while eslint 9 allowed it, because
      // 6.x/7.x fold the React Compiler's diagnostic suite into
      // `recommended`. eslint 10 forced the 7.x major (5.2.0 peer-depends on
      // eslint <=9), so containment moved from the version pin to rule
      // severity — the four compiler diagnostics ran at `warn` while the
      // ~30 pre-existing sites were triaged (#756, #768).
      //
      // That triage is done, so they are `error` now. A rule at `warn` with
      // 30 standing warnings does not contain anything: nobody sees number
      // 31. Every remaining site carries an inline disable stating WHY it is
      // intentional, which is the artifact worth having — the audit in #768
      // found the two real defects hiding among them (an eager
      // `useRef(f())` minting a discarded UUID and rebuilding a discarded
      // SolveRequest every render) precisely because each site had to be
      // justified one at a time.
      //
      // Deliberately per-site disables rather than a file- or rule-level
      // exemption: a new violation in these same files still fails.
      ...reactHooks.configs.recommended.rules,
      "react-hooks/set-state-in-effect": "error",
      "react-hooks/refs": "error",
      "react-hooks/immutability": "error",
      "react-hooks/purity": "error",
      // The issue calls for exhaustive-deps at error (the plugin default is
      // "warn"); rules-of-hooks is already "error" in `recommended`.
      "react-hooks/exhaustive-deps": "error",
      // "vite" preset (not "recommended"): allows a file to export a
      // top-level constant alongside its component, which this codebase's
      // hook/component co-location (e.g. contexts.ts-style default exports)
      // relies on; plain "recommended" flags every one of those.
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  {
    // Testing Library's recommended rules, scoped to the test tree only —
    // this plugin assumes every file it lints is a test file (it flags
    // `render`/`screen` usage patterns that don't exist elsewhere).
    files: ["src/__tests__/**"],
    plugins: {
      "testing-library": testingLibrary,
    },
    rules: {
      // The compiler's ref diagnostic does not apply to a test harness
      // component (#768): a harness exists precisely to surface a hook's
      // internals — it renders `car.mobileCarouselRef` into the tree so an
      // assertion can reach it. That is reading a ref during render on
      // purpose, and it ships to nobody. Scoped off here rather than
      // disabled at each of the four call sites, because in this tree it is
      // the rule that is wrong, not the code.
      "react-hooks/refs": "off",
      ...testingLibrary.configs.react.rules,
      // 42 legacy `container.querySelector`/`.contains` sites predate this
      // config (role-based queries already lead 138-to-42). Downgraded to
      // `warn` so they're visible in `npm run lint`'s warning count without
      // failing the `--max-warnings=9999` CI gate; migrate opportunistically.
      "testing-library/no-container": "warn",
      "testing-library/no-node-access": "warn",
      // Ground-truth delta from the #736 audit (which estimated only the two
      // rules above): the `react` preset's `recommended` rules also fire 51
      // errors across the same pre-existing legacy suite —
      // render-result-naming-convention (destructured `render()` result names
      // like `on`/`off`/`gamma`), prefer-presence-queries (`queryBy*` used for
      // presence checks), prefer-find-by, no-unnecessary-act and
      // no-manual-cleanup (setup.ts's explicit `cleanup()`, redundant with
      // this project's afterEach registration but not a bug). None of these
      // are new bugs, all of them predate this config exactly like
      // no-container/no-node-access, and fixing 51 call sites across ~15
      // test files is a migration, not an adoption — out of scope for this
      // issue's semantic-diff guardrail. Downgraded to `warn` for the same
      // reason and on the same "migrate opportunistically" footing.
      "testing-library/render-result-naming-convention": "warn",
      "testing-library/prefer-presence-queries": "warn",
      "testing-library/prefer-find-by": "warn",
      "testing-library/no-unnecessary-act": "warn",
      "testing-library/no-manual-cleanup": "warn",
    },
  },
);
