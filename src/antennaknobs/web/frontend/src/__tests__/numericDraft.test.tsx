// The numeric-draft contract in components/backend/fields.tsx.
//
// These fields hold a TEXT draft rather than binding straight to the number,
// because binding to the number coerced "" → 0 on backspace: the field could
// not be cleared, and the forced 0 left a leading zero when you typed again.
// That behaviour was carried only by a comment until issue #768 moved the
// prop-sync out of an effect and into a render-time adjustment — a refactor
// with no test under it. These are that test.
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { NumberField } from "../components/backend/fields";

function Harness({ initial, onChange }: { initial: number; onChange?: (v: number) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <NumberField
        label="N"
        value={value}
        onChange={(v) => {
          setValue(v);
          onChange?.(v);
        }}
      />
      {/* Drives `value` from OUTSIDE, the way a backend swap or reset does. */}
      <button onClick={() => setValue(42)}>external</button>
    </>
  );
}

describe("numeric draft", () => {
  it("can be emptied mid-edit without committing a 0", () => {
    const onChange = vi.fn();
    render(<Harness initial={15} onChange={onChange} />);
    const input = screen.getByRole("spinbutton");

    fireEvent.change(input, { target: { value: "" } });

    // The draft is empty — the field is clearable...
    expect((input as HTMLInputElement).value).toBe("");
    // ...and nothing was committed, so no 0 snaps back into the model.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps a half-typed value that parses to the number already committed", () => {
    render(<Harness initial={1.5} />);
    const input = screen.getByRole("spinbutton");

    // "1.50" parses to 1.5, which is what `value` already holds. The sync must
    // not fire, or the trailing zero would vanish from under the cursor.
    fireEvent.change(input, { target: { value: "1.50" } });

    expect((input as HTMLInputElement).value).toBe("1.50");
  });

  it("re-syncs when the value changes from outside", () => {
    render(<Harness initial={15} />);
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "" } });
    expect((input as HTMLInputElement).value).toBe("");

    fireEvent.click(screen.getByText("external"));

    // An outside change overrides whatever was being typed — that is the whole
    // point of the sync, and what the removed effect used to provide.
    expect((input as HTMLInputElement).value).toBe("42");
  });
});
