# The portal moves home (#846): architecture decisions

Design doc for giving the SimNEC portal its own home and identity.
Answers the eight questions from #846, each with a decision and the
rejected alternatives. Evidence re-measured on main at `999978aa4`
(2026-08-15). Third revision, and the title verb has changed twice for
good reason: rev 1 recommended a thin extraction to a new repo depending
on antennaknobs; review pushback ("the portal should just do basic
antenna-only solves") produced rev 2's restricted momwire-only dialect
but kept the new repo; a second round of review ("momwire can have the
portal be its user-facing entry point") killed the new repo too. The
recommendation is now: **the portal becomes `momwire/portal/` — momwire's
own executable front door — serving momwire's restricted antenna-only NEC
dialect. No new repo, no new PyPI package.**

## What changed since the issue was filed

The issue's strategic core — "extraction forces us to enumerate what a
ported-admittance consumer needs and turn that into momwire's formal
public interface" — **already happened without the extraction**. PR #848
deleted all four branches of the private `_y_and_port_coeffs` shim; the
portal's production code calls exactly two public momwire methods,
`compute_port_solution()` (`nec_portal.py:1802`) and `currents_at_knots()`
(`:2320`), plus the five public solver constructors. momwire#232 is
CLOSED: `PortSolution` is in momwire's `__all__` and `sol.y` is
bit-identical to `compute_y_matrix()` by construction. Zero `momwire._*`
reaches remain in portal production code (three live in tests only,
deliberately, asserting solve routing).

What the portal still leans on is **antennaknobs-internal**: `parse_nec`,
the `MomwireEngine` assembly layer (nine private attributes across 12
sites), `AntennaBuilder`, and two nearly-free-standing network functions.
The scope census below shows most of that surface exists to serve cards
SimNEC never sends and output sections SimNEC never reads.

## The scope census (what "antenna-only" costs in practice)

* **The 44-deck fixture corpus is 93% antenna-only.** Card histogram:
  GW 104, EX 55, XQ 52, FR 49, GE 45, GN 16, RP 7, LD 7 … **TL 2, NT 2**,
  confined to three decks (`dipole_tl_network`, `dipole_nt_network`,
  `dipole_tl_shunt_crossed`) — all hand-authored probes, per the corpus
  README ("inputs we authored … or recovered from string constants in
  SimNEC's jar"); none is captured SimNEC traffic.
* **SimNEC never emits network cards on this path.** Its `NECSource`
  writes only `RP 0 …` request cards (`nec_portal.py:1069-1072`); TL/NT
  can only arrive in a user-pasted deck.
* **SimNEC never reads the network output.** The execute-grammar study
  (§4.9): the NETWORK DATA and STRUCTURE EXCITATION sections are
  "*(ignored)* … not consumed, because the state machine only arms on the
  ANTENNA INPUT PARAMETERS banner". The portal prints them for oracle
  diffability only (`nec_portal.py:2851-2856`).
* **The portal's network machinery is ~330 of 3,634 lines (~9%)** and its
  removal deletes the last solve-path antennaknobs import that isn't the
  parser/engine pair: `tl_admittance_2x2` + `SingularNetworkError`
  (`nec_portal.py:144`).
* **The portal already restricts the importer.** `_synthesize_union_deck`
  (`:1806-1820`) hands `parse_nec` a synthetic deck of geometry + LD + IS
  + one `EX 0` per port — TL/NT never reach the importer from the portal
  today. The full network grammar is along for the ride, not in use.

Refusing TL/NT is house precedent three times over: the portal's own
`_DEFERRED_CARDS` voice ("`SP (surface patch) is not supported by this
engine yet`", `:1175-1179`), its per-feature refusals (EX type ≠ 0, RP
modes 1/4/5/6, radial screens), and the NEC-5 census lane's 488
by-design dialect refusals (`engines/nec5.py:217-222`). Every NEC engine
serves a named dialect; momwire's names antenna-only.

## 1. Dependency direction: momwire only, via the restricted dialect

The portal depends on **momwire alone** — and (§4) lives inside it. The
deck grammar it serves is **momwire's own NEC dialect** — nec2c has one,
NEC-5 has one, momwire gets one: geometry (the cards the corpus
exercises: GW, GM, GS, GE), ground (GN, GD), FR, EX 0 voltage sources,
LD loads, IS insulation, EK, and the request cards (XQ, RP 0/2/3, NE/NH,
PT, NX). TL and NT join `_DEFERRED_CARDS` and refuse by name, with a
message that points at antennaknobs for full-network decks. Network
solving is SimNEC's job (it already recomputes everything it cares
about) or antennaknobs' (whose importer keeps the full grammar
unchanged).

What made momwire-only "a rewrite" in rev 1, re-examined under the cut:

* `parse_nec` — replaced by a restricted parser (§2). The antenna half of
  `nec_import.py` is ~1,600 lines, but ~275 of that is the 4nec2 SY
  expression language (out of dialect) and ~314 is polyline/junction
  translation; a parser for the corpus grammar lands near **500-700
  lines**.
* `MomwireEngine` — not needed. momwire's public constructors already
  take everything the assembly layer produces: `wires=` polylines,
  per-wire `wire_radius` (#147), `n_per_edge_per_wire`, `feeds=[(wire,
  arclength, V)]`, `junction_ports`, `node_gaps`, `ground_z/ground_eps/
  ground_model`, `cancel=`. The nine private engine attributes evaporate
  when the portal owns its parse: `_polylines`/`_edge_segments` existed
  because the *engine* owned the geometry; `_make_solver`/`_contract_y`/
  `_feed_names`/`_feed_W`/`_loading_kwargs` are the assembly the dialect
  module now does against public API.
* `element_currents` — momwire already ships it publicly
  (`_element_currents.py:34-120`), and the portal's hand-rolled
  `current_elements` (`nec_portal.py:2291-2338`) is a near-verbatim
  duplicate (same mesh walk, same moments, same steps). The portal
  deletes its copy and keeps only `_segment_currents`' deck-direction
  re-signing, which is NEC's convention, not momwire's.
* LD loads — **no solver change needed**. The portal already stamps
  series/parallel RLC as port impedances outside the solver
  (`_load_impedances` + `np.eye(n) + z_load[:,None] @ y`, ~40 lines);
  that algebra moves with the portal. `_series_rlc_impedance` is 26
  lines with zero module dependencies — copied, with attribution, not
  imported.
* Far field — **no solver change needed**. momwire's solver core has
  zero far-field code, and the portal has never used anyone else's: it
  owns a complete nec2c-parity implementation (~320 lines: cliff modes,
  image coefficients, the −999.99 floor) because the *output table
  format* is the contract. It moves with the portal, inside
  `momwire/portal/` — it is table-formatting physics, not solver
  physics, and the isolation rule (§4) keeps it out of the core.

Rejected alternative: rev 1's thin extraction depending on antennaknobs.
It was the honest call against the full-dialect surface, but the census
dissolved that surface; its remaining advantage was a few weeks' less
interface work, paid for permanently with the scipy-sized antennaknobs
install for every SimNEC user. Rejected alternative: momwire-only with
the network stack relocated — still a rewrite, still forks the network
model antennaknobs needs; the restriction is what makes momwire-only
real.

Cost, stated honestly: a user-pasted deck with TL/NT that the portal
accepted yesterday gets a refusal tomorrow. Evidence says that user is
hypothetical (three self-authored probe decks; SimNEC neither sends the
cards nor reads the resulting sections); the refusal names the migration
path; the Ward note carries one line about it.

## 2. The dialect lives in momwire: `momwire.deck`

New public momwire module owning the dialect spec and parser:
`parse(deck_text) -> DeckModel` (wires, radii, per-edge segments, feeds
as (wire, arclength, V), ground kwargs, loads, insulation, request
cards) and `build_solver(model, basis=...)` mapping onto the five public
solver families. It owns the NEC-isms the constructors don't speak:
(tag, segment) → (wire, arclength) addressing, junction snapping, GM/GS
transforms, GE semantics. Pure Python, no new dependencies.

Why momwire: the dialect is the *engine's* identity (nec2c's and NEC-5's
dialects belong to their engines, not their wrappers); it version-locks
grammar to solver capability; and it has immediate second consumers —
every validation study and bench harness we run hand-translates decks
into constructor calls today, and `momwire.deck` deletes that. It also
finally forces the documentation debt: `feeds=`/`junction_ports`/
`compute_port_solution` appear in momwire's README today not at all.

The dialect gets a **normative grammar document, written spec-first** in
phase I: card by card, field by field — what each supported card means
(GW, GM, GS, GE, GN, GD, FR, EX 0, LD, IS, EK, XQ, RP 0/2/3, NE/NH, PT,
NX), which fields are read vs ignored, and the named refusals (TL, NT,
EX ≠ 0, RP 1/4/5/6, radial screens, SP/SM) with their messages. The
parser implements the spec and its tests cite it, the way NEC-2's and
NEC-5's manuals define their dialects — not the other way around. It
publishes on momwire.dev (§6), which makes it the first thing a SimNEC
user can actually link when asking "what does this engine accept?" — a
question nec2c answers with a 40-year-old manual and we currently answer
with nothing.

**The dialect seam is plural from day one.** A NEC-5-flavored dialect is
a probable follow-on (so momwire can work directly on NEC-5 decks — the
formulation-twin and corpus studies hand-translate them today), and the
module shape should anticipate it without building it: dialect
front-ends parse into one **dialect-neutral `DeckModel`**, and
`build_solver` maps the model onto solver families — so a second dialect
is a second parser, not a second pipeline. `parse(text,
dialect="nec2")` with `"nec2"` the only value shipped in phase I.
Nothing NEC-2-specific may leak into `DeckModel`'s vocabulary (it speaks
wires/arclengths/feeds/gaps/grounds, not tags and cards). momwire is
already half-ready on the solver side: `node_gaps` exists precisely to
express NEC-5's tag/segment/end knot source (issue #305), and
antennaknobs' importer already recognizes NEC-5's edge-source EX
spellings — the dialect knowledge exists, it just lives in the wrong
package for momwire to use directly. The grammar reference (below) gets
a per-dialect page structure for the same reason.

The parser stays in antennaknobs too — `parse_nec` is unchanged,
antennaknobs needs the full network grammar for `.nec` import (#369)
regardless. Two parsers, two dialects, one engine: exactly the nec2c/
NEC-5 situation — and when the NEC-5 dialect lands, momwire serves both
the way NEC-5 itself reads both its own and legacy decks.

## 3. The momwire interface: mostly done; the remaining work is named

* **Done**: `compute_port_solution()`/`PortSolution` (#232, shipped
  0.24.0); `element_currents`/`currents_at_knots` public; constructor
  surface for wires/radii/feeds/gaps/grounds (§1).
* **New (phase I)**: `momwire.deck` — the dialect module above.
* **Docs**: README + momwire.dev section for the port API, the dialect,
  and the portal (the census found zero README mentions of any of it).
* **Explicitly NOT needed** (rev 1 had these wrong or open): per-segment
  lumped loading in the solvers (the portal stamps it), a solver-core
  far-field module (the portal owns the table), and the #232 "deferred
  half" as a *prerequisite* — `element_currents` already covers the
  portal's need.
* The three test-only route spies stay in the portal's battery,
  documented as the accepted exception.

## 4. Packaging: `momwire/portal/`, momwire's executable front door

No new repo, no new PyPI package. The portal becomes a subpackage of
momwire, installed with it: `pip install momwire` yields the
`momwire-nec2c` console script (declared in momwire's
`[project.scripts]`) and `python -m momwire.portal` as the long
spelling. momwire — today the only engine in this ecosystem with no
executable front door — becomes a peer of nec2c and nec5cl: an engine
you can point SimNEC at.

Why this beats the rev-2 separate package (`nec2momwire`):

* **Version skew is deleted, not detected.** Rev 2's cross-repo canary
  existed to *catch* portal-vs-momwire API drift; colocation makes drift
  structurally impossible. The battery runs in momwire's own CI against
  the working tree; a dialect feature lands in the same PR as the solver
  capability it exposes. One maintainer plus agents should not pay a
  two-repo coordination tax that buys nothing.
* **The probe reports the number that changes results** (§5).
* **Zero bootstrap**: no new CI, publishing, tracker, or README. Ward
  watches momwire's tracker — the engine's, which is what he would watch
  anyway. Docs land on momwire.dev, which exists as of this week.

The costs, and their controls:

* **Identity dilution** — SimNEC-protocol cruft (banner spoofing,
  column-exact NEC-2 tables, timing canonicalization, the `out` lore,
  800 KB of fixtures, the 1,700-line protocol study) now lives in the
  physics repo. Control: a strict isolation rule — **`momwire/portal/`
  may import the public solver API; nothing outside `momwire/portal/`
  may import from it** — enforced by a test, not a convention.
* **Test weight** — +960 collected tests on a ~1,900-test suite. They
  are fixture-diff fast and the `oracle_binary` quarantine stays; this
  is CI minutes, accepted.
* **Cadence coupling** — a portal-only formatting fix needs a momwire
  release (they are cheap); an engine release bumps the probe with no
  protocol change (harmless, and per §5, correct).
* **No escape hatch** — if the portal someday grows non-SimNEC
  consumers and protocol versions of its own, extracting it later is
  the work we are declining now. The restricted scope is the bet that
  it will not.

The console script keeps the load-bearing name **`momwire-nec2c`**
(SimNEC dispatches by `indexOf("nec2c")`, must not match `nec5`/`nec42`
first, `getEngine()` wants a digit); the pinning tests move with it, and
phase III adds the missing test for the documented-but-untested
`out`-substring path trap. Transition collision is managed by
antennaknobs' exact pin: old antennaknobs (`momwire==0.29.0`) cannot see
the momwire that declares the script, and the pin-bump release that can
drops antennaknobs' declaration in the same transaction (§7).

## 5. Version identity

`PROBE_VERSION` reads `importlib.metadata.version("momwire")` — the
probe reports **the engine's version**, which is the number that changes
solve results. Under any wrapper-package scheme the probe reports a
number that can sit still while the engine under it moves; colocation
makes the probe semantically correct by construction.

The optics cost, accepted deliberately: the probe today says
`NEC2momwire.0.52` (antennaknobs' version — and on stale editable
installs, not even that); after the move it says `NEC2momwire.0.30`-ish.
To anyone comparing, a downgrade. The decision (review, 2026-08-15) is
to carry an explanatory line in the Ward note — "the probe now tracks
the momwire engine version, the number that actually changes results;
it restarts lower and will move faster" — rather than force a momwire
1.0 declaration through a packaging change. If momwire earns 1.0, it
earns it on solver grounds, separately. `LEGACY_PROBE_VERSION` and
`BANNER_VERSION` (+ per-basis suffixes) move verbatim.

## 6. What travels

| moves into `momwire/portal/` | stays in antennaknobs |
|---|---|
| `nec_portal.py` minus the ~330-line network branch, minus the duplicated `current_elements` | `nec_import.py` (full grammar, unchanged), `builder.py`, `network*.py` |
| `_series_rlc_impedance` (26 lines, copied with attribution) | its original in `network.py` |
| the 3 test files (960 tests) — the 3 network decks become refusal fixtures | whole-suite CI stops collecting portal tests |
| `tests/fixtures/nec_portal/` (90 files; clean-room README) | |
| `scripts/nec_portal_capture.py`, `nec_portal_smoke.sh` | |
| both 2026-08-08 SimNEC status docs (clean-room reference) | |
| `simnec.md` content → the momwire.dev usage page | a present-tense stub page linking out |
| `[project.scripts] momwire-nec2c` → momwire's pyproject | removed in the same pin-bump release (§7) |

New in momwire besides the move: `momwire.deck` + its tests + docs.

**momwire.dev grows a Reference section.** The site today is only the
14-chapter primer — narrative, act-structured, no reference content at
all. The portal brings its first two reference pages, in a new Starlight
sidebar group beside the acts:

* **the dialect grammar** (§2's normative spec, published) — the
  card-by-card contract, maintained as the spec the parser tests cite,
  so the page cannot go stale against the code;
* **portal usage** — install (`pip install momwire`), pointing SimNEC at
  `momwire-nec2c`, the wrapper-script recipe, `--basis` selection, the
  probe/version contract, `python -m momwire.portal`, and what refusals
  look like. Absorbs the durable parts of antennaknobs' `simnec.md`
  (447 lines), rewritten present-tense for the new home.

The two 2026-08-08 SimNEC status docs stay **in-repo engineering
reference, not site content**: they document the reverse-engineered
behavior of SimNEC's own parser — load-bearing for maintaining the
portal, but publishing an anatomy of someone else's jar on the project
site is neither necessary nor courteous. The site documents *our*
contract; the repo documents theirs.

## 7. Migration: dialect first, rewire in place, move third, cut over last

The decoupling happens **in place**, where the fixture battery can prove
it, before any file moves:

* **Phase I — momwire**: the normative dialect grammar (spec-first,
  §2), then `momwire.deck` (parser, `build_solver`) implementing it;
  the grammar publishes on momwire.dev (new Reference sidebar group)
  and the README gains the port-API section. Released as a momwire
  minor.
* **Phase II — portal rewire in place** (antennaknobs): portal switches
  to `momwire.deck` + public constructors + public `element_currents`;
  TL/NT join `_DEFERRED_CARDS`; the five antennaknobs imports drop to
  zero. Gate: 41 antenna decks byte-identical against their oracle
  `.out` files; the 3 network decks assert the refusal message.
* **Phase III — the move**: `momwire/portal/` + console script + battery
  + fixtures land in momwire (verbatim from phase II's proven state);
  the isolation-rule test and the `out`-substring test land with them;
  the **portal usage page** joins the grammar in the site's Reference
  group (absorbing `simnec.md`'s durable content). One momwire release
  ships deck + portal + docs together.
* **Phase IV — antennaknobs cutover**: the pin-bump release adopts that
  momwire, deletes the moved files, drops its `momwire-nec2c`
  declaration, adds the site stub; Docker needs no change beyond the pin
  (the script now arrives via the momwire wheel). Release notes + Ward
  note (the probe line + the TL/NT refusal line). No deprecation shim —
  the exact pin makes the transition atomic per environment.

## 8. Release ritual / CI

momwire's existing ritual absorbs everything: the battery joins its CI
lanes (fixture-based, no SimNEC binary needed — the `pyproject.toml:
169-176` rationale comment travels), wheels/publishing unchanged, no
cross-repo canary needed — colocation deleted its reason to exist.

## Phased issues (filed when this doc merges)

The issue's original phases 1–2 are already complete (#848 /
momwire#232) — recorded, no issues needed. Filed instead: **I**
(momwire: `momwire.deck` + docs), **II** (antennaknobs: portal rewire in
place, byte-identity + refusal gates), **III** (momwire: the move +
isolation rule + script), **IV** (antennaknobs: pin-bump cutover + Ward
note). Plus the stray finding from the evidence pass, filed separately:
`web/adapter.py:2137` still imports a momwire private
(`_wire_to_element`), unrelated to the portal.
