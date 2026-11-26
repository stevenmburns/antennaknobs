# Block JSON, v1

The stored form of a block-builder design (see `block-builder.md`, "How a
block program is stored and run"). A program is one JSON object; the server
checks it (`block_design.compile_program`), runs it with an interpreter
(`block_design.run`, never `exec`), and renders it as Python
(`block_codegen.generate`). Templates: `block_templates.py`.

Run one from the command line with `--blocks FILE.json` on any command that
takes `--builder`, or `--builder @FILE.json` anywhere a builder spec goes.

## The design

```json
{"block": "design", "schema": 1, "name": "Dipole", "freq_mhz": 28.47,
 "params": [{"name": "length_factor", "value": 0.967, "min": 0.8, "max": 1.25}],
 "body": [ ...blocks... ]}
```

| field | |
|---|---|
| `name` | one line of text, at most 80 characters. It is the generated file's first comment, so nothing that ends a line is allowed |
| `freq_mhz` | the design frequency: `design_freq` and `freq` in the knobs; λ is measured at it |
| `params` | the knobs. `name`, `value` (a number), optional `unit` (`"m"`, `"λ"`, `"°"` or `""`, a label only), optional `min` / `max` (the slider's range, `ui_params`) |
| `schema` | optional, `1` |
| `body` | the blocks, run in order |

A param's value is used as written: a `λ` unit does **not** multiply it by
the wavelength; write `λ * width_factor` where metres are meant, as the
catalog does.

## Blocks

Every block is an object with `"block"` naming its kind and an optional
`"id"` (a string of 1 to 64 characters). Errors name the block by its `id`,
or by its JSON pointer (`/body/0/body/2`) when it has none. Unknown fields
are refused.

| block | fields | Python |
|---|---|---|
| `let` | `name`, `value` | `name = value` |
| `point` | `name`, `at: [x, y, z]` | `P = (x, y, z)` |
| `mirror_point` | `name`, `of` (a point), `across` (`yz` / `xz` / `xy`) | `Q = (P[0], -P[1], P[2])` for `xz` |
| `wire` | `from`, `to` (a point name or `[x, y, z]`), optional `feed` | `st.emit(Wire(P, Q))` |
| `wire_x` / `wire_y` / `wire_z` | `from`, `to` (numbers along the axis), optional off-axis coordinates (`y`, `z` for `wire_x`), optional `feed` | `st.wire_x(a, b, y=...)` |
| `path` | `points` (2 or more), optional `feed_segment` | `st.path([A, B, C])` |
| `loop` | `points` (3 or more), optional `feed_segment` | `st.path([A, B, C], closed=True)` |
| `move` | `by: [dx, dy, dz]`, `body` | `with st.push_pop_tr(Transform.translate(dx, dy, dz)):` |
| `rotate` | `axis` (`x` / `y` / `z`), `deg`, `body` | `with st.push_pop_tr(Transform.rotZ(deg)):` |
| `mirror` | `across` (a plane), `body` | `with st.push_pop_tr(Transform.mirrorXZ()):` |
| `both_sides` | `across`, `body` | `for side in (Transform(), Transform.mirrorXZ()):` + `with st.push_pop_tr(side):` |
| `repeat` | `count`, optional `var` (default `i`), optional `each`, `body` | `for i in range(count):` |
| `with_wire` | `spec` (a `WIRES` name, e.g. `"14-awg"`), `body` | `with st.wire_spec(WIRES["14-awg"]):` |

- `feed` is `"centre"`, the only position in v1: `ex=1 + 0j` on that wire.
  `feed_segment` (0-based) puts it on one wire of a path. An off-centre or
  end feed is a port on the wire, which belongs to the network side.
- `each` is the transform a `repeat` applies on every pass, seeing the loop
  variable: `{"move": [dx, dy, dz]}` or `{"rotate": {"axis": "z", "deg":
  "360 * i / 6"}}`. It generates one `with` inside the `for`.
- Segment counts are never written: every wire is meshed at the design
  density by `auto_mesh`, as `n_seg=None` is in hand-written designs.

## Expressions

A coordinate, a `value`, `deg` or `count` is a JSON number, a string in the
grammar below, or `{"ref": "name"}`.

```
expr  := term (("+" | "-" | "−") term)*
term  := unary (("*" | "×" | "/" | "÷") unary)*
unary := ("-" | "−") unary | atom
atom  := number | name | "λ" | ("sqrt" | "sin" | "cos") "(" expr ")" | "(" expr ")"
```

- A name is a param, a `let`, or a loop variable. `λ` (or `wavelength`) is
  the wavelength at `freq_mhz`.
- `sin` and `cos` take degrees, like every angle here.
- Nothing else is accepted: no attribute access, indexing, `**`, other
  functions or names. At most 256 characters and 32 levels of nesting; every
  value must be finite, an integer at most 2**53, and a division by zero, a
  `sqrt` of a negative or an overflow is an error on the block.
- The parser is hand-written (`block_expr.py`); no Python evaluator ever
  sees the text.

## Names and frames

- Every name in a program (params, lets, points, loop variables) is used
  once, and is letters, digits and `_`, a letter first. Python keywords and
  builtins, the generated module's own names (`st`, `self`, `math`, `side`,
  `wavelength`, `Wire`, `Transform`, ...), the framework knobs (`freq`,
  `design_freq`, `nominal_nsegs`) and `AntennaBuilder` attributes are
  reserved.
- A `let` or a loop variable is seen by the blocks after it in its body,
  nested ones included.
- **Joins stay inside one transform block** (Steve, 2026-11-24): a point is
  a position in the frame of the block it was made in, so a wire uses only
  points made in its own `move` / `rotate` / `mirror` / `both_sides` /
  `repeat`-with-`each` body. `with_wire` and a plain `repeat` do not change
  the frame and do not end it. A point is not seen after its body ends.

## Bounds

So that a program from anyone runs in bounded time and memory:

| bound | value | why |
|---|---|---|
| repeat count | 0 to 256 | the catalog's largest repeat is 120 radials |
| repeat nesting | 3 | an array of rotated elements of repeated parts |
| wires | 3000 | the hosted upload's segment cap; a wire is at least one segment |
| steps (statements run + repeat passes) | 100 000 | three nested repeats of 256 emit nothing but run 16.7 M passes |
| blocks | 2000 | bounds the compile pass |
| file | 1 MB | |

A `count` read from a knob is checked when the program runs, since a knob
can move.

## The saved file

`block_codegen.generate` writes the Python and, as its last line,

```
# antennaknobs-blocks: v1 <base64 of the canonical JSON>
```

(canonical: sorted keys, no spaces, UTF-8). `block_codegen.reopen` returns
the program only when the code above the trailer is exactly what that
program generates; any hand edit raises `HandEditedError`, which carries the
saved program for an editor that offers to open it as saved. The file is
compared as text and never compiled or run.
