import {
  AwaitingTrustPanel,
  type DesignLoadError,
} from "../AwaitingTrustPanel";
import { GeometryCombobox } from "../params/GeometryCombobox";
import type { ExampleDescriptor, ExampleGroup } from "../../lib/params";

export function CatalogPanel({
  geomGroups,
  geometry,
  currentExample,
  geomFilter,
  setGeomFilter,
  setGeometry,
  currentVariant,
  selectVariant,
  examplesError,
  loadErrors,
  trustBusy,
  trustDesign,
}: {
  geomGroups: ExampleGroup[];
  geometry: string;
  currentExample: ExampleDescriptor | undefined;
  geomFilter: string;
  setGeomFilter: (v: string) => void;
  setGeometry: (v: string) => void;
  currentVariant: string;
  selectVariant: (v: string) => void;
  examplesError: string | null;
  loadErrors: DesignLoadError[];
  trustBusy: string | null;
  trustDesign: (stem: string, allowEdits: boolean) => void;
}) {
  return (
    <>
      <div className="antenna-row">
        <GeometryCombobox
          groups={geomGroups}
          selected={geometry}
          currentLabel={currentExample?.label ?? ""}
          filter={geomFilter}
          setFilter={setGeomFilter}
          onSelect={setGeometry}
        />
        {currentExample && currentExample.variants.length > 1 && (
          <select
            id="variant-select"
            className="geometry-select variant-select"
            value={currentVariant}
            onChange={(e) => selectVariant(e.target.value)}
            aria-label="variant"
            title="variant"
          >
            {currentExample.variants.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        )}
      </div>
      {currentExample?.notes && (
        <div className="design-note">{currentExample.notes}</div>
      )}
      {examplesError && (
        <div className="examples-error">
          Failed to load /examples: {examplesError}
        </div>
      )}
      {loadErrors.some((e) => e.trust_required) && (
        <AwaitingTrustPanel
          designs={loadErrors.filter((e) => e.trust_required)}
          busy={trustBusy}
          onTrust={trustDesign}
        />
      )}
      {loadErrors.some((e) => !e.trust_required) && (
        <div className="design-load-errors" role="alert">
          {(() => {
            const errs = loadErrors.filter((e) => !e.trust_required);
            return (
              <>
                <div className="design-load-errors-title">
                  {errs.length} design{errs.length === 1 ? "" : "s"} failed to
                  load
                </div>
                <ul>
                  {errs.map((err) => (
                    <li key={err.name}>
                      <code>{err.name}</code> — {err.message}
                      <span className="design-load-errors-file">
                        {err.file}
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="design-load-errors-hint">
                  Fix the file and refresh. See CLAUDE.md in your designs
                  folder.
                </div>
              </>
            );
          })()}
        </div>
      )}
    </>
  );
}
