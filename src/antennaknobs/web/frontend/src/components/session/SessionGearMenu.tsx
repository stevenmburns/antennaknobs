import type { MeasuredData } from "../../lib/api";
import type { useFullscreen } from "../hooks";
import type { Theme } from "../hooks";
import { TabStrip } from "./TabStrip";

// Sidebar header: brand + the tools (gear) dropdown, incl. the reactive
// copies of the chart-overlay toggles (same state the overlays use, so the
// two locations can never disagree), and the theme toggle.
export function SessionGearMenu({
  gearMenuOpen,
  setGearMenuOpen,
  copiedParams,
  onCopyParams,
  onDownloadNec,
  isMobile,
  fullscreen,
  showHeatmap,
  setShowHeatmap,
  showEnvelope,
  setShowEnvelope,
  showWireLabels,
  setShowWireLabels,
  showFeedNames,
  setShowFeedNames,
  sweepEnabled,
  setSweepEnabled,
  convergeEnabled,
  setConvergeEnabled,
  convergeNValues,
  measured,
  onLoadMeasured,
  onClearMeasured,
  normCheckEnabled,
  setNormCheckEnabled,
  theme,
  applyTheme,
}: {
  gearMenuOpen: boolean;
  setGearMenuOpen: (v: boolean | ((o: boolean) => boolean)) => void;
  copiedParams: boolean;
  onCopyParams: () => void;
  onDownloadNec: () => void;
  isMobile: boolean;
  fullscreen: ReturnType<typeof useFullscreen>;
  showHeatmap: boolean;
  setShowHeatmap: (v: boolean) => void;
  showEnvelope: boolean;
  setShowEnvelope: (v: boolean) => void;
  showWireLabels: boolean;
  setShowWireLabels: (v: boolean) => void;
  showFeedNames: boolean;
  setShowFeedNames: (v: boolean) => void;
  sweepEnabled: boolean;
  setSweepEnabled: (v: boolean) => void;
  convergeEnabled: boolean;
  setConvergeEnabled: (v: boolean) => void;
  convergeNValues: number[];
  measured: MeasuredData | null;
  onLoadMeasured: (f: File) => void;
  onClearMeasured: () => void;
  normCheckEnabled: boolean;
  setNormCheckEnabled: (v: boolean) => void;
  theme: Theme;
  applyTheme: (t: Theme) => void;
}) {
  return (
    <>
      <TabStrip />
      <div className="sidebar-header">
        <div className="brand">
          <h1>AntennaKNoBs</h1>
          <span className="byline">by KK7KNB</span>
        </div>
        <div className="header-actions">
          <div className="gear-menu-wrap">
            <button
              type="button"
              className="header-icon-btn"
              onClick={() => setGearMenuOpen((o) => !o)}
              title="Tools"
              aria-label="Tools menu"
              aria-haspopup="menu"
              aria-expanded={gearMenuOpen}
            >
              ⚙
            </button>
            {gearMenuOpen && (
              <>
                <div
                  className="gear-menu-backdrop"
                  onClick={() => setGearMenuOpen(false)}
                />
                <div className="gear-menu" role="menu">
                  <button
                    type="button"
                    className="gear-menu-item"
                    role="menuitem"
                    onClick={onCopyParams}
                    title="Copy the current knob values as a paste-ready Python default_params block"
                  >
                    {copiedParams ? "Copied ✓" : "Copy params (Python)"}
                  </button>
                  <button
                    type="button"
                    className="gear-menu-item"
                    role="menuitem"
                    onClick={onDownloadNec}
                    title="Download this design as a NEC2 .nec card deck (for xnec2c, 4nec2, EZNEC, …)"
                  >
                    Download .nec deck
                  </button>
                  {/* Reactive copies of the chart-overlay toggles (same state
                      the overlays use, so the two locations can never
                      disagree). On mobile the checkbox overlays are not
                      rendered on the chart screens — small screens can't
                      spare the chart area — so this menu is the only place
                      to reach them there; on desktop it's a convenience
                      duplicate. */}
                  <div className="gear-menu-divider" />
                  {/* Mobile-layout only: it exists to reclaim the phone's
                      status/nav bars; on desktop F11 already does this and
                      the menu entry would be clutter. Also needs element
                      fullscreen (missing on iPhone Safari). */}
                  {isMobile && fullscreen.supported && (
                    <>
                      <div className="gear-menu-section">display</div>
                      <label
                        className="gear-menu-check"
                        title="Take over the whole screen — hides the system status and navigation bars. Uncheck (or use the back gesture) to exit."
                      >
                        <input
                          type="checkbox"
                          checked={fullscreen.active}
                          onChange={fullscreen.toggle}
                        />
                        full screen
                      </label>
                    </>
                  )}
                  <div className="gear-menu-section">antenna chart</div>
                  <label
                    className="gear-menu-check"
                    title="Color wire segments by current magnitude; modulate wire width"
                  >
                    <input
                      type="checkbox"
                      checked={showHeatmap}
                      onChange={(e) => setShowHeatmap(e.target.checked)}
                    />
                    heatmapped currents
                  </label>
                  <label
                    className="gear-menu-check"
                    title="Draw the |I| envelope curve along each wire"
                  >
                    <input
                      type="checkbox"
                      checked={showEnvelope}
                      onChange={(e) => setShowEnvelope(e.target.checked)}
                    />
                    current waveforms
                  </label>
                  <label
                    className="gear-menu-check"
                    title="Draw the per-wire labels (off to declutter dense geometries)"
                  >
                    <input
                      type="checkbox"
                      checked={showWireLabels}
                      onChange={(e) => setShowWireLabels(e.target.checked)}
                    />
                    wire labels
                  </label>
                  <label
                    className="gear-menu-check"
                    title="Draw the 'feed' name beside each feedpoint marker"
                  >
                    <input
                      type="checkbox"
                      checked={showFeedNames}
                      onChange={(e) => setShowFeedNames(e.target.checked)}
                    />
                    feed labels
                  </label>
                  <div className="gear-menu-section">smith chart</div>
                  <label
                    className="gear-menu-check"
                    title="Sweep Z across measurement freq and plot the locus on the Smith chart"
                  >
                    <input
                      type="checkbox"
                      checked={sweepEnabled}
                      onChange={(e) => setSweepEnabled(e.target.checked)}
                    />
                    freq sweep
                  </label>
                  <label
                    className="gear-menu-check"
                    title={`Re-solve at N = ${convergeNValues.join(", ")} segments/wire and Richardson-extrapolate Z to N→∞`}
                  >
                    <input
                      type="checkbox"
                      checked={convergeEnabled}
                      onChange={(e) => setConvergeEnabled(e.target.checked)}
                    />
                    converge sweep
                  </label>
                  <label
                    className="gear-menu-check gear-menu-file"
                    title="Overlay a measured VNA sweep (one-port Touchstone .s1p, e.g. from a NanoVNA) against the modeled locus"
                  >
                    <input
                      type="file"
                      accept=".s1p,.S1P"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (f) onLoadMeasured(f);
                      }}
                    />
                    {measured ? `measured: ${measured.label}` : "measured .s1p\u2026"}
                  </label>
                  {measured && (
                    <button
                      type="button"
                      className="gear-menu-check gear-menu-button"
                      onClick={onClearMeasured}
                    >
                      clear measured
                    </button>
                  )}
                  <div className="gear-menu-section">azimuth / elevation</div>
                  <label
                    className="gear-menu-check"
                    title="On dwell, renormalise the pattern by its own integrated radiated power (dotted) instead of the input power the solid line uses. Overlap ⇒ the solve conserves power; a visible gap is the solver's discretisation error (NEC's 'average gain' check)."
                  >
                    <input
                      type="checkbox"
                      checked={normCheckEnabled}
                      onChange={(e) => setNormCheckEnabled(e.target.checked)}
                    />
                    norm check
                  </label>
                </div>
              </>
            )}
          </div>
          <button
            type="button"
            className="theme-toggle"
            onClick={() => applyTheme(theme === "dark" ? "light" : "dark")}
            title="Toggle light / dark theme"
            aria-label="Toggle light / dark theme"
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </div>
    </>
  );
}
