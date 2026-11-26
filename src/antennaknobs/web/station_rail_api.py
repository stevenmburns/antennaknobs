"""The station rail's endpoints, under /station (docs/design/block-builder.md,
"The station rail"): the rail, its code and schematic, the junction probes,
A/B rails, the placement gallery, and reading a file back onto the rail.

Every endpoint takes the workbench's own solve request (``request``: the
design, its knobs, the frequency, the engine slot and the ground), so the rail
feeds whatever design is on screen, at the knobs on screen. The antenna is
solved once per request (`station_rail_solve.SolvedAntenna`) on the request's
momwire engine; both rails, every probe and every gallery card are circuit
reductions over that one solve, and each response says how many antenna
solves it took (``antenna_solves``).

Local installs only, for now: these routes solve without the hosted solve
path's guards (the basis cap, the solve watchdog, the concurrency limit), and
the hosted app's authoring tools are a later decision (the design note's
"Hosted, eventually").
"""

from __future__ import annotations

import difflib
import re
import time
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from .. import station_rail as sr
from ..station_rail_solve import SolvedAntenna, solve_chain

router = APIRouter(prefix="/station")

P_REF_W = 100.0  # the rail's watts are per 100 W accepted at the rig


# --- the antenna -------------------------------------------------------------------


def _catalog() -> set[str]:
    from .adapter import list_designs

    return set(list_designs())


def _module_for(design: str) -> str:
    """What a generated file imports the antenna from: the catalog path, or,
    for a design that is a file of the user's, that file's name as a module
    beside the generated one."""
    if design in _catalog():
        return f"antennaknobs.designs.{design}"
    stem = re.sub(r"\W", "_", design.rsplit("/", 1)[-1].removesuffix(".py"))
    return stem if stem.isidentifier() else f"design_{stem}"


class _Antenna:
    """One request's design, attached to the rail and solved once."""

    def __init__(self, req: dict):
        from .adapter import _make_momwire_engine
        from .examples import example_for

        if not isinstance(req, dict):
            raise sr.RailRefusal("request must be the workbench's solve request")
        geometry = req.get("geometry")
        ex = example_for(geometry)
        if ex.solve_builder is None:
            raise sr.RailRefusal(f"{geometry!r} cannot be built for the rail")
        self.design = geometry
        self.req = req
        self.z_ref = float(req.get("target_z0") or 50.0)
        builder = ex.solve_builder(req)
        self.builder = builder
        self.att = sr.attach(geometry, builder, _module_for(geometry))
        self.freq_mhz = float(builder.freq)
        # The antenna box: the design on its own feed, no station. Shadowed on
        # the instance (object.__setattr__: Builder.__setattr__ would file a
        # plain write into _params and the class method would still win; see
        # adapter._apply_plane), which works for a sandboxed design too, so the
        # station never enters the sandbox. `attach` has read the design's own
        # network and wires already, and the knobs stay readable.
        if self.att.form == "wire":
            wires = builder.build_wires
            object.__setattr__(
                builder, "build_wires", lambda: sr.wires_for(self.att, wires())
            )
        bare = sr.antenna_network(self.att)
        object.__setattr__(builder, "build_network", lambda: bare)
        self.sa = SolvedAntenna(_make_momwire_engine(req, builder))

    def describe(self, origin: str | None = None) -> dict:
        att = self.att
        out = {
            "design": att.design,
            "module": att.module,
            "feed": att.feed,
            "form": att.form,
            "balanced": att.balanced,
            "replaced": att.replaced,
            "freq_mhz": self.freq_mhz,
            "z_ref": self.z_ref,
        }
        notices = []
        if origin is not None:
            out["origin"] = origin
            if origin == "default" and att.replaced:
                notices.append(
                    f"This design's own station ({att.replaced} "
                    f"branch{'es' if att.replaced != 1 else ''} in its "
                    "build_network) is not one the rail can read, so the rail "
                    "starts from the default chain and stands in for it."
                )
        if att.at_feed:
            # Two numbers labelled "feed" in one app: say why they differ.
            notices.append(
                f"The design's station has {att.at_feed} part"
                f"{'s' if att.at_feed != 1 else ''} across {att.feed} itself "
                "(such as an L network's shunt arm). On the rail that is "
                "station, so the antenna row is the bare antenna; the "
                f"workbench's measurement plane at {att.feed} keeps "
                f"{'them' if att.at_feed != 1 else 'it'}, and reads differently."
            )
        if notices:
            out["notice"] = " ".join(notices)
        return out


# --- one rail ------------------------------------------------------------------------


def _svg(net, budget, p_in, freq_mhz) -> tuple[str | None, str | None]:
    from ..schematic import lower, render_svg

    try:
        return (
            render_svg(
                lower(
                    net,
                    title="",
                    budget=[(r["key"], r["watts"]) for r in budget],
                    p_in=p_in,
                    freq_mhz=freq_mhz,
                ),
                color="currentColor",
            ),
            None,
        )
    except ImportError as e:  # an install without the schematic extra
        return None, str(e)


def _display_budget(solved: dict, ant: _Antenna) -> list[dict]:
    from .adapter import _budget_rows

    shim = SimpleNamespace(
        _network=solved["network"],
        _excited_power_budget=[(r["key"], r["watts"]) for r in solved["budget"]],
    )
    p_in = solved["p_in_w"]
    return [
        {
            "label": (r["path"] + ": " if r["path"] else "") + r["label"],
            "watts": P_REF_W * r["watts"] / p_in if p_in > 0 else 0.0,
        }
        for r in _budget_rows(shim, ant.builder)
    ]


def _chips(chain: dict, att: sr.Attachment) -> list[dict]:
    _nodes, placed = sr.layout(chain, att)
    return [
        {
            "label": sr.describe(it),
            "kind": it["kind"],
            "series": sr.is_series(it),
            "a": a,
            "b": b,
            "name": name,
        }
        for it, name, a, b in placed
    ]


def _rail(ant: _Antenna, chain: dict, prev_python: str | None, svg=True) -> dict:
    att = ant.att
    chain, _ = sr.freeze(sr.check_chain(chain), att)
    py = sr.to_python(chain, att)
    s = solve_chain(ant.sa, chain, att, z_ref=ant.z_ref)
    nodes, _ = sr.layout(chain, att)
    out = {
        "chain": chain,
        "python": py,
        "changed": _changed_lines(prev_python, py),
        "chips": _chips(chain, att),
        "nodes": nodes,
        "advisories": sr.advisories(chain, att),
        **{k: s[k] for k in ("z_re", "z_im", "swr", "loss_db", "probes")},
        **{k: s[k] for k in ("tuner", "tuner_advisories")},
        "p_ant_w": P_REF_W * s["antenna_share"],
        "budget": _display_budget(s, ant),
    }
    if svg:
        out["svg"], out["svg_reason"] = _svg(
            s["network"], s["budget"], s["p_in_w"], ant.freq_mhz
        )
    return out


# --- code diffs ----------------------------------------------------------------------


def _opcodes(a: list[str], b: list[str]):
    """difflib's opcodes with each pure insert or delete slid up as far as
    it goes. Inserting an ``Instance(...)`` block before another one is
    ambiguous by a line ("Instance(" at either end matches); the slide puts
    the change on the new block's own lines, as a reader would. The equal
    runs are rebuilt around the slid changes."""
    changes, ea, eb = [], 0, 0  # ea/eb: where the previous change ended
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            while i1 > ea and j1 > eb and b[j1 - 1] == b[j2 - 1]:
                i1, i2, j1, j2 = i1 - 1, i2 - 1, j1 - 1, j2 - 1
        elif tag == "delete":
            while i1 > ea and j1 > eb and a[i1 - 1] == a[i2 - 1]:
                i1, i2, j1, j2 = i1 - 1, i2 - 1, j1 - 1, j2 - 1
        changes.append((tag, i1, i2, j1, j2))
        ea, eb = i2, j2
    ops, ea, eb = [], 0, 0
    for op in changes:
        if op[1] > ea:
            ops.append(("equal", ea, op[1], eb, op[3]))
        ops.append(op)
        ea, eb = op[2], op[4]
    if ea < len(a):
        ops.append(("equal", ea, len(a), eb, len(b)))
    return ops


def _changed_lines(old: str | None, new: str) -> list[int]:
    """0-based indices of the lines of ``new`` that ``old`` did not have."""
    if not old:
        return []
    changed = []
    for tag, _i1, _i2, j1, j2 in _opcodes(old.splitlines(), new.splitlines()):
        if tag in ("replace", "insert"):
            changed.extend(range(j1, j2))
    return changed


def _diff(old: str, new: str, context: int = 1) -> list[str]:
    """A card's code change as diff lines ("+", "-", " ", and "@@" where
    unchanged lines are skipped), ``context`` lines either side."""
    a, b = old.splitlines(), new.splitlines()
    full = []
    for tag, i1, i2, j1, j2 in _opcodes(a, b):
        if tag == "equal":
            full += [" " + ln for ln in a[i1:i2]]
        else:
            full += ["-" + ln for ln in a[i1:i2]] + ["+" + ln for ln in b[j1:j2]]
    hot = [i for i, ln in enumerate(full) if ln[0] != " "]
    keep = {
        j
        for i in hot
        for j in range(max(i - context, 0), min(i + context + 1, len(full)))
    }
    out, last = [], None
    for i in sorted(keep):
        if last is not None and i != last + 1:
            out.append("@@")
        out.append(full[i])
        last = i
    return out


# --- the endpoints' bodies -------------------------------------------------------------


def render(body: dict) -> dict:
    """Each rail in ``body["rails"]`` (one or two chains; a null entry, or
    none at all, is the design's starting chain), on one solve of the
    antenna."""
    t0 = time.perf_counter()
    ant = _Antenna(body.get("request"))
    start, origin = sr.starting_chain(ant.att, ant.builder)
    rails = body.get("rails") or [None]
    if not isinstance(rails, list) or not 1 <= len(rails) <= 2:
        raise sr.RailRefusal("rails is a list of one or two chains")
    prev = body.get("prev_python") or []
    out_rails = []
    for i, chain in enumerate(rails):
        p = prev[i] if isinstance(prev, list) and i < len(prev) else None
        out_rails.append(
            _rail(
                ant,
                start if chain is None else chain,
                p if isinstance(p, str) else None,
            )
        )
    return {
        "antenna": ant.describe(origin),
        "starting_chain": start,
        "rails": out_rails,
        "antenna_solves": ant.sa.solves,
        "ms": (time.perf_counter() - t0) * 1e3,
    }


def gallery(body: dict) -> dict:
    """Cards for one component: a palette key (``add``), a whole component
    record (``item``), or an existing item to move (``move``: its index; the
    current place is one of the cards)."""
    t0 = time.perf_counter()
    ant = _Antenna(body.get("request"))
    att = ant.att
    chain = sr.check_chain(body.get("chain"))
    current = None
    if body.get("move") is not None:
        i = int(body["move"])
        if not 0 <= i < len(chain["items"]):
            raise sr.RailRefusal(f"no item {i} to move")
        chain, _ = sr.freeze(chain, att)
        item = chain["items"][i]
        base = dict(chain, items=chain["items"][:i] + chain["items"][i + 1 :])
        # A shunt's place is its node: canonical position, first on the node.
        while (
            i > 0 and not sr.is_series(item) and not sr.is_series(base["items"][i - 1])
        ):
            i -= 1
        current = i
    elif body.get("item") is not None:
        item = sr.check_chain({"items": [body["item"]]})["items"][0]
        base = chain
    else:
        item = sr.palette_item(str(body.get("add")), ant.freq_mhz)
        base = chain
    old_py = sr.to_python(sr.freeze(chain, att)[0], att)
    cards = []
    for card in sr.placements(base, att, item):
        s = solve_chain(ant.sa, card["chain"], att, z_ref=ant.z_ref, with_probes=False)
        svg, _why = _svg(s["network"], s["budget"], s["p_in_w"], ant.freq_mhz)
        cards.append(
            {
                **{k: card[k] for k in ("pos", "where", "chain", "advisories")},
                **{k: s[k] for k in ("z_re", "z_im", "swr", "loss_db")},
                "p_ant_w": P_REF_W * s["antenna_share"],
                "svg": svg,
                "current": current is not None and card["pos"] == current,
                "diff": _diff(old_py, sr.to_python(card["chain"], att)),
            }
        )
    return {
        "component": sr.describe(item),
        "refusal": sr.refusal(base, item),
        "cards": cards,
        "antenna_solves": ant.sa.solves,
        "ms": (time.perf_counter() - t0) * 1e3,
    }


def read(body: dict) -> dict:
    """A file back onto the rail: ``{"chain", "antenna"}``, or ``{"refusal"}``
    naming why it is not read (outside the house style, or written for
    another design or feed than the one on screen). Never runs the file."""
    text = body.get("text")
    if not isinstance(text, str):
        raise sr.RailRefusal("text is the file to read")
    try:
        chain, antenna = sr.read_python(text)
    except sr.RailRefusal as e:
        return {"refusal": str(e)}
    req = body.get("request")
    if req is not None:
        geometry = req.get("geometry") if isinstance(req, dict) else None
        module = _module_for(str(geometry))
        if antenna["module"] != module:
            return {
                "refusal": f"this file feeds {antenna['module']}; the workbench "
                f"shows {module}. Open that design to put this station on it."
            }
        # Same design, but the attachment is the one on screen too: the knobs
        # can move a design's feed, and a file for another feed or form would
        # put the chain somewhere the rail does not draw it. Attaching builds
        # the network only; nothing is solved.
        att = _attachment(req)
        mine = {"form": att.form, "feed": att.feed}
        theirs = {k: antenna[k] for k in mine}
        if theirs != mine:
            return {
                "refusal": f"this file feeds {module} at {antenna['feed']!r} "
                f"(form {antenna['form']!r}); on screen the rail feeds it at "
                f"{att.feed!r} (form {att.form!r}), so the file is shown, not "
                "put on the rail"
            }
    return {"chain": chain, "antenna": antenna}


def _attachment(req: dict) -> sr.Attachment:
    from .examples import example_for

    geometry = req.get("geometry")
    ex = example_for(geometry)
    if ex.solve_builder is None:
        raise sr.RailRefusal(f"{geometry!r} cannot be built for the rail")
    return sr.attach(geometry, ex.solve_builder(req), _module_for(geometry))


def palette() -> dict:
    return {
        "palette": {
            k: {"label": sr.describe(sr.palette_item(k, 7.0)), "kind": v["kind"]}
            for k, v in sr.PALETTE.items()
        },
        "cables": sorted(sr.CABLES),
        "chain_version": sr.CHAIN_VERSION,
    }


def _call(fn, body):
    try:
        return fn(body)
    except (KeyError, ValueError, TypeError, NotImplementedError) as e:
        # RailRefusal is a ValueError: its message is the reason, as written.
        detail = str(e) if isinstance(e, sr.RailRefusal) else f"{type(e).__name__}: {e}"
        raise HTTPException(status_code=422, detail=detail) from e


@router.get("/palette")
async def palette_endpoint():
    return palette()


@router.post("/render")
async def render_endpoint(body: dict):
    return await run_in_threadpool(_call, render, body)


@router.post("/gallery")
async def gallery_endpoint(body: dict):
    return await run_in_threadpool(_call, gallery, body)


@router.post("/read")
async def read_endpoint(body: dict):
    return await run_in_threadpool(_call, read, body)
