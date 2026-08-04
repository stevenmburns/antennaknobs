import type { View } from "../../lib/view";
import { VIEW_RENDERERS, type ViewRenderProps } from "./viewRegistry";

// Dispatch only: look the view's renderer up in the registry and invoke it.
// The lookup is exact per id — there is no fallthrough view, so a missing
// entry is a typecheck failure rather than a silently wrong chart.
export function ViewPanel({
  view,
  showWireLabels = false,
  showFeedNames = true,
  schematicSvg = null,
  schematicUnavailable = false,
  ...rest
}: Omit<
  ViewRenderProps,
  "showWireLabels" | "showFeedNames" | "schematicSvg" | "schematicUnavailable"
> & {
  view: View;
  // Optional at the call sites (the thumbstrip omits them); resolved here so
  // every registry entry sees a complete prop bag.
  showWireLabels?: boolean;
  showFeedNames?: boolean;
  schematicSvg?: string | null;
  schematicUnavailable?: boolean;
}) {
  return VIEW_RENDERERS[view]({
    ...rest,
    showWireLabels,
    showFeedNames,
    schematicSvg,
    schematicUnavailable,
  });
}
