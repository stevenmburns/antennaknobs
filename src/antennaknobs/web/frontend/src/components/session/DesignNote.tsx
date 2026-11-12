// The design's informational note, under the antenna selector.
//
// A file import writes what it left behind into one prose note, and a list
// in it can run to dozens of entries (a SimNEC script's directives not
// applied, AK#2291), burying the sentences that matter. The server names
// each such list (`note_lists`: its lead and its items, which the note
// carries verbatim as `<lead>: <a>; <b>; ...`), so the panel folds it to one
// line that opens on demand, without parsing the prose. A list the note does
// not carry verbatim is not folded: the note shows whole, and nothing is
// ever hidden that cannot be opened.
import { Fragment, useState, type ReactElement } from "react";
import type { NoteList } from "../../lib/params";

function FoldedList({ list }: { list: NoteList }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="design-note-list">
      <button
        type="button"
        className="solver-advisory-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {`${list.lead} (${list.items.length})`}
      </button>
      {open && (
        <ul className="design-note-items">
          {list.items.map((item, k) => (
            <li key={k}>{item}</li>
          ))}
        </ul>
      )}
    </span>
  );
}

export function DesignNote({
  notes,
  lists,
}: {
  notes: string;
  lists?: readonly NoteList[] | null | undefined;
}) {
  let parts: (string | ReactElement)[] = [notes];
  for (const list of lists ?? []) {
    const written = `${list.lead}: ${list.items.join("; ")}`;
    parts = parts.flatMap((p) => {
      if (typeof p !== "string") return [p];
      const at = p.indexOf(written);
      if (at < 0) return [p];
      return [
        p.slice(0, at),
        <FoldedList key={list.lead} list={list} />,
        p.slice(at + written.length),
      ];
    });
  }
  return (
    <div className="design-note">
      {parts.map((p, k) => (
        <Fragment key={k}>{p}</Fragment>
      ))}
    </div>
  );
}
