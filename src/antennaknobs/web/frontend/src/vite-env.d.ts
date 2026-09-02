// Ambient declarations for Vite's non-code imports -- `*.css`, `*.svg`,
// `?raw`/`?url` suffixes, and import.meta.env.
//
// Required since TypeScript 6. TS 5 let a side-effect import of a
// non-code module through with no declaration at all; TS 6 raises TS2882
// ("Cannot find module or type declarations for side-effect import")
// instead, and `src/main.tsx`'s `import "./styles.css"` is the one site
// in this tree that trips it.
//
// A reference file rather than `"types": ["vite/client"]` in
// tsconfig.json on purpose: setting `types` REPLACES automatic @types
// resolution, which would drop the vitest and testing-library globals
// the suite relies on. A triple-slash reference only adds.
/// <reference types="vite/client" />
