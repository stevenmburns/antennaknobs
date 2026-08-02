import { createContext } from "react";

// Shared between App.tsx (which owns the Provider and the theme-toggle
// control) and the chart components under components/charts/ (which read it
// via useContext to repaint on theme toggle). Lives here rather than in
// App.tsx so neither side has to take a runtime import on the other —
// App.tsx imports the charts, so a chart importing this value straight out
// of App.tsx would be a live import cycle (issue #642 seam 3).
export type Theme = "light" | "dark";
export const ThemeContext = createContext<Theme>("light");
