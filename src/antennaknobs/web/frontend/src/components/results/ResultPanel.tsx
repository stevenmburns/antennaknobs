import { Fragment } from "react";
import { formatScalar } from "../../lib/format";
import type { ResultFieldSpec, ResultSchemaItem } from "../../lib/params";

// label_template substitutions for ResultGroupItem:
//   {i}            → 0-based index
//   {i1}           → 1-based index
//   {name:.Nf}     → result[name][i] formatted as a fixed-N-decimal float
function renderGroupLabel(template: string, i: number, result: Record<string, unknown> | null): string {
  let out = template.replace(/\{i1\}/g, String(i + 1)).replace(/\{i\}/g, String(i));
  out = out.replace(/\{(\w+):\.(\d+)f\}/g, (_, name: string, decimals: string) => {
    const arr = result?.[name];
    if (!Array.isArray(arr)) return "—";
    const v = arr[i];
    return typeof v === "number" ? v.toFixed(Number(decimals)) : "—";
  });
  return out;
}

export function ResultPanel({
  schema,
  result,
}: {
  schema: ResultSchemaItem[];
  result: Record<string, unknown> | null;
}) {
  // Render one row per schema entry. Scalar items read the field off the
  // response by name; group items repeat over the first inner field's
  // top-level array. Missing/non-numeric values render as an em-dash so
  // the row layout doesn't collapse mid-update.
  return (
    <>
      {schema.map((item) => {
        if ("kind" in item && item.kind === "group") {
          const repeatField = item.fields[0]?.field;
          const arr = repeatField ? result?.[repeatField] : undefined;
          if (!Array.isArray(arr)) return null;
          return (
            <Fragment key={`result-group-${item.name}`}>
              {arr.map((_, i) => (
                <div className="row" key={`result-group-${item.name}-${i}`}>
                  <span>{renderGroupLabel(item.label_template, i, result)}</span>
                  <span className="val">
                    {item.fields.map((f, fi) => {
                      const sub = result?.[f.field];
                      const v = Array.isArray(sub) ? sub[i] : undefined;
                      return (
                        <span key={`${item.name}-${i}-${fi}`}>
                          {formatScalar(v, f.precision, f.unit)}
                        </span>
                      );
                    })}
                  </span>
                </div>
              ))}
            </Fragment>
          );
        }
        const s = item as ResultFieldSpec;
        return (
          <div className="row" key={`result-${s.field}`}>
            <span>{s.label}</span>
            <span className="val">{formatScalar(result?.[s.field], s.precision, s.unit)}</span>
          </div>
        );
      })}
    </>
  );
}
