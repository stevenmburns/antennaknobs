import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { CrashProbe, ErrorBoundary } from "./components/ErrorBoundary";
import { installGlobalErrorReports } from "./lib/clientErrors";
import "./styles.css";

installGlobalErrorReports();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <CrashProbe />
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
