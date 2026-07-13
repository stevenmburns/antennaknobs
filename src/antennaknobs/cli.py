from functools import partial

from . import AntennaBuilder, resolve_variant_params
from . import (
    sweep,
    sweep_swr,
    sweep_gain,
    sweep_patterns,
    pattern,
    pattern3d,
    compare_patterns,
    optimize,
)
from .engines import PyNECEngine, MomwireEngine
from .serialize import builder_params_source
from .user_designs import USER_NS, iter_design_files, resolve_user_design

from momwire import (
    SinusoidalSolver,
    BSplineSolver,
    HMatrixSolver,
    ArrayBlockSolver,
)

import argparse
import logging
from importlib import import_module
from types import ModuleType

logger = logging.getLogger(__name__)

ENGINE_CLASSES = {
    "momwire": MomwireEngine,
}
if PyNECEngine is not None:
    ENGINE_CLASSES["pynec"] = PyNECEngine

MOMWIRE_BASES = {
    "sinusoidal": SinusoidalSolver,
    "bspline": BSplineSolver,
    "hmatrix": HMatrixSolver,
    "arrayblock": ArrayBlockSolver,
}


def resolve_class(s):
    lst = s.split(".")

    """
    Try in order:
    local with explicit Builder
    local with implicit Builder
    library with explicit Builder
    library with implicit Builder
    """

    logger.debug("resolve_class: spec=%r lst=%r", s, lst)

    def try_to_resolve(builder_name, module_name):
        logger.debug(
            "try_to_resolve: builder_name=%r module_name=%r", builder_name, module_name
        )
        try:
            module = import_module(module_name)
            try:
                res = getattr(module, builder_name)
                logger.debug("try_to_resolve: resolved %r", res)
                return None if isinstance(res, ModuleType) else res
            except AttributeError:
                return None
        except ModuleNotFoundError:
            return None

    def try_to_resolve_list(lst):
        if len(lst) > 1:
            if (res := try_to_resolve(lst[-1], ".".join(lst[:-1]))) is not None:
                return res

        return try_to_resolve("Builder", ".".join(lst))

    if (res := try_to_resolve_list(lst)) is not None:
        return res

    if (res := try_to_resolve_list(["antennaknobs", "designs"] + lst)) is not None:
        return res

    # Designs live under a family subpackage (designs/<family>/<name>.py).
    # A bare name like "moxon" can still be resolved by searching each family
    # — the family prefix ("beams.moxon") is accepted by the branch above but
    # not required. Basenames are unique today, but if two families ever
    # define the same name, refuse to guess: report both and make the caller
    # qualify it (the qualified form resolves in the branch above).
    matches = []
    for fam in _design_families():
        cand = ["antennaknobs", "designs", fam] + lst
        if (res := try_to_resolve_list(cand)) is not None:
            matches.append((fam, res))
    if len(matches) > 1:
        qualified = ", ".join(f"{fam}.{'.'.join(lst)}" for fam, _ in matches)
        raise ValueError(
            f"ambiguous design {s!r}: matches {qualified} — qualify it with the family"
        )
    if matches:
        return matches[0][1]

    # User-authored designs (local plugin folder), addressed explicitly as
    # "user.<name>". Kept to its own namespace on purpose: a bare name never
    # resolves to a user file, so a user design can't shadow a built-in. Load
    # errors propagate so someone debugging their own file sees the real cause.
    if len(lst) == 2 and lst[0] == USER_NS:
        if (res := resolve_user_design(lst[1])) is not None:
            return res

    return None


def _design_families():
    """Family subpackage names under antennaknobs.designs (cached)."""
    global _DESIGN_FAMILIES
    if _DESIGN_FAMILIES is None:
        import os

        import antennaknobs.designs as _d

        fams = set()
        for root in list(getattr(_d, "__path__", [])):
            for name in os.listdir(root):
                if name.startswith(("_", ".")):
                    continue
                if os.path.isdir(os.path.join(root, name)):
                    fams.add(name)
        _DESIGN_FAMILIES = sorted(fams)
    return _DESIGN_FAMILIES


_DESIGN_FAMILIES = None


def list_builtin_designs() -> list[str]:
    """Every built-in design as a sorted ``family.name`` dotted path.

    A pure filesystem walk over ``antennaknobs.designs`` — every family
    ``*.py`` defines a ``Builder``, so the listing matches what ``resolve_class``
    can resolve, without importing the modules.
    """
    import os

    import antennaknobs.designs as _d

    names: list[str] = []
    for root in list(getattr(_d, "__path__", [])):
        for fam in os.listdir(root):
            if fam.startswith(("_", ".")):
                continue
            fam_dir = os.path.join(root, fam)
            if not os.path.isdir(fam_dir):
                continue
            for fn in os.listdir(fam_dir):
                if not fn.endswith(".py") or fn.startswith("_"):
                    continue
                names.append(f"{fam}.{fn[:-3]}")
    return sorted(set(names))


def list_variants(cls):
    """Return all variant names for a Builder class. A variant is any class
    attribute whose name ends in '_params' and is a Mapping; the variant name
    is the attribute name with '_params' stripped."""
    from collections.abc import Mapping

    out = []
    for nm in dir(cls):
        if not nm.endswith("_params"):
            continue
        if not isinstance(getattr(cls, nm), Mapping):
            continue
        out.append(nm[: -len("_params")])
    return sorted(out)


def get_builder(nm):
    """Resolve a builder spec into a zero-arg factory.

    Spec is "name" or "name:variant". A variant binds the named '<variant>_params'
    class attribute as the builder's params; absent or ':default' uses default_params.
    """
    name, _, variant = nm.partition(":")
    cls = resolve_class(name)
    if cls is None:
        # Fail with a clear message instead of returning None, which every
        # caller would then call as `builder()` -> `TypeError: 'NoneType' object
        # is not callable` (a confusing crash for a simple typo). SystemExit
        # prints just the message to stderr and exits non-zero, no traceback.
        raise SystemExit(
            f"unknown builder {nm!r} — run `antennaknobs list` to see available designs"
        )
    if not variant or variant == "default":
        return cls
    attr = f"{variant}_params"
    params = getattr(cls, attr, None)
    if params is None:
        available = ", ".join(list_variants(cls)) or "(none)"
        raise ValueError(
            f"builder {name!r} has no variant {variant!r}; available: {available}"
        )
    # Overlay the variant on default_params so a partial variant (only the
    # keys it changes) resolves to a complete param set; a complete variant
    # reproduces itself. Keep the getattr check above so an unknown variant
    # name stays a hard error rather than silently falling back to default.
    return partial(cls, params=resolve_variant_params(cls, variant))


def get_builders(nms):
    return (get_builder(nm) for nm in nms)


def emit_params_name(builder_spec):
    """Variable name for a serialised param block emitted from ``builder_spec``.

    A ``name:variant`` spec emits ``<variant>_params`` (so the block drops
    straight back beside the variant it came from); a bare name or ``:default``
    emits ``default_params``.
    """
    _, _, variant = builder_spec.partition(":")
    if variant and variant != "default":
        return f"{variant}_params"
    return "default_params"


def parse_ground(s):
    """--ground argument:
    free                          -> None
    pec                           -> 'pec'
    finite                        -> default ('finite', 10.0, 0.002)
                                     (Sommerfeld-Norton on PyNEC)
    finite:<eps_r>,<sigma>        -> ('finite', eps_r, sigma)
    finite-fast                   -> default ('finite-fast', 10.0, 0.002)
                                     (reflection-coefficient approximation)
    finite-fast:<eps_r>,<sigma>   -> ('finite-fast', eps_r, sigma)
    """
    if s is None or s == "free":
        return None
    if s == "pec":
        return "pec"
    for kind in ("finite-fast", "finite"):
        if s == kind:
            return (kind, 10.0, 0.002)
        if s.startswith(kind + ":"):
            try:
                eps_r, sigma = (float(x) for x in s[len(kind) + 1 :].split(","))
            except ValueError as e:
                raise argparse.ArgumentTypeError(f"bad --ground spec {s!r}: {e}") from e
            return (kind, eps_r, sigma)
    raise argparse.ArgumentTypeError(f"unrecognised --ground: {s!r}")


def broadcast_pairs(builders, engines):
    """Numpy-style 1D broadcast of two sequences into a list of pairs.

    Equal lengths zip pairwise; a length-1 sequence broadcasts against the
    other. Any other length mismatch raises.
    """
    nb, ne = len(builders), len(engines)
    if nb == ne:
        return list(zip(builders, engines))
    if nb == 1:
        return [(builders[0], e) for e in engines]
    if ne == 1:
        return [(b, engines[0]) for b in builders]
    raise argparse.ArgumentTypeError(
        f"cannot broadcast {nb} builders against {ne} engines; "
        "lengths must match or one side must be 1"
    )


def parse_engine_spec(spec):
    """Parse an engine spec into (engine_name, kwargs_to_bind).

    Forms: "pynec", "momwire", "momwire:sinusoidal|bspline|hmatrix|arrayblock".
    """
    name, _, basis = spec.partition(":")
    if name not in ENGINE_CLASSES:
        raise argparse.ArgumentTypeError(
            f"unknown engine {name!r}; available: {', '.join(sorted(ENGINE_CLASSES))}"
        )
    if not basis:
        return name, {}
    if name != "momwire":
        raise argparse.ArgumentTypeError(
            f"engine {name!r} does not accept a basis suffix (got {basis!r})"
        )
    if basis not in MOMWIRE_BASES:
        raise argparse.ArgumentTypeError(
            f"unknown momwire basis {basis!r}; available: {', '.join(sorted(MOMWIRE_BASES))}"
        )
    return name, {"solver": MOMWIRE_BASES[basis]}


def make_engine_factory(engine_spec, ground_spec):
    name, kwargs = parse_engine_spec(engine_spec)
    cls = ENGINE_CLASSES[name]
    # PyNECEngine's default ground IS finite; momwire's default is free.
    # When the user passes --ground explicitly we always honour it;
    # when they don't, we use whatever the engine's own default is.
    if ground_spec is not _GROUND_UNSET:
        kwargs["ground"] = ground_spec
    if not kwargs:
        return cls
    return partial(cls, **kwargs)


_GROUND_UNSET = object()


def cli(arguments=None):

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity: -v for INFO, -vv for DEBUG "
        "(e.g. design-resolution and sweep tracing).",
    )

    subparsers = parser.add_subparsers(dest="command")

    def add_common(p, use_builders=False):
        p.add_argument(
            "--fn",
            type=str,
            default=None,
            help="Plot goes to the file, or displayed on screen if None.",
        )
        if use_builders:
            p.add_argument(
                "--builders",
                type=str,
                nargs="+",
                default=["dipoles.invvee:dipole", "dipoles.invvee"],
                help="Use this list of antenna builders.",
            )
        else:
            p.add_argument(
                "--builder",
                type=str,
                default="dipoles.invvee:dipole",
                help="Use this antenna builder.",
            )

    def add_engine_args(p, plural=False):
        if plural:
            p.add_argument(
                "--engines",
                type=str,
                nargs="+",
                default=["momwire"],
                help="One or more simulation backends. Each spec is "
                '"momwire[:sinusoidal|bspline|hmatrix|arrayblock]" or "pynec". '
                "Cross-products with --builders.",
            )
        else:
            p.add_argument(
                "--engine",
                type=str,
                default="momwire",
                help="Simulation backend: momwire | "
                "momwire:sinusoidal | momwire:bspline | momwire:hmatrix | "
                "momwire:arrayblock | pynec (default: momwire). pynec needs "
                "the optional pynec-accel package; momwire is always "
                "available.",
            )
        p.add_argument(
            "--ground",
            default=_GROUND_UNSET,
            help="Ground model: free | pec | finite[:<eps_r>,<sigma>] "
            "(Sommerfeld-Norton, both engines) | finite-fast[:<eps_r>,<sigma>] "
            "(reflection-coefficient approximation) "
            "(default: engine-specific — finite for pynec, free for momwire).",
        )

    def add_pattern_common(p):
        p.add_argument(
            "--elevation_angle",
            default=15,
            type=float,
            help="Elevation angle for azimuth plot.",
        )
        p.add_argument(
            "--azimuth_f",
            default=0,
            type=int,
            help="Azimuth angle (front) for the elevation plot.",
        )
        p.add_argument(
            "--azimuth_r",
            default=180,
            type=int,
            help="Azimuth angle (rear) for the elevation plot.",
        )

    def engine_factory_from_args(args):
        ground = (
            args.ground if args.ground is _GROUND_UNSET else parse_ground(args.ground)
        )
        return make_engine_factory(args.engine, ground)

    p = subparsers.add_parser("draw", help="Draw antenna")
    add_common(p)

    def f(args):
        builder = get_builder(args.builder)
        AntennaBuilder.draw(builder().build_wires(), fn=args.fn)

    p.set_defaults(func=f)

    p = subparsers.add_parser("sweep", help="Sweep antenna")
    add_common(p)
    add_engine_args(p)
    add_pattern_common(p)
    p.add_argument("--param", type=str, default="freq", help="Variable to sweep.")
    p.add_argument(
        "--range", nargs=2, default=None, type=float, help="Range for sweep."
    )
    p.add_argument(
        "--center", default=None, type=float, help="Center if range not given."
    )
    p.add_argument(
        "--fraction", default=None, type=float, help="Fraction around center for range."
    )
    p.add_argument("--npoints", default=21, type=int, help="Points in the range.")
    p.add_argument(
        "--gain",
        default=False,
        action="store_true",
        help="Plot gain instead of impedance.",
    )
    p.add_argument(
        "--use_smithchart",
        default=False,
        action="store_true",
        help="Plot impedance using a smithchart.",
    )
    p.add_argument(
        "--swr",
        default=False,
        action="store_true",
        help="Plot SWR + reflection magnitude against the swept --param "
        "(default freq, which uses the engine's fast vectorized sweep).",
    )
    p.add_argument("--z0", default=50, type=float, help="Reference impedance.")
    p.add_argument(
        "--markers",
        default=[],
        nargs="+",
        type=float,
        help="Add markers at these values.",
    )

    p.add_argument(
        "--patterns",
        default=False,
        action="store_true",
        help="Compare patterns generated for each swept value.",
    )

    def f(args):
        builder = get_builder(args.builder)
        engine = engine_factory_from_args(args)
        if args.patterns:
            sweep_patterns(
                builder(),
                args.param,
                rng=args.range,
                npoints=args.npoints,
                center=args.center,
                fraction=args.fraction,
                fn=args.fn,
                elevation_angle=args.elevation_angle,
                azimuth_f=args.azimuth_f,
                azimuth_r=args.azimuth_r,
                engine=engine,
            )
        elif args.swr:
            sweep_swr(
                builder(),
                args.param,
                z0=args.z0,
                rng=args.range,
                npoints=args.npoints,
                center=args.center,
                fraction=args.fraction,
                fn=args.fn,
                engine=engine,
            )
        elif args.gain:
            sweep_gain(
                builder(),
                args.param,
                rng=args.range,
                npoints=args.npoints,
                center=args.center,
                fraction=args.fraction,
                fn=args.fn,
                engine=engine,
            )
        else:
            sweep(
                builder(),
                args.param,
                rng=args.range,
                npoints=args.npoints,
                center=args.center,
                fraction=args.fraction,
                use_smithchart=args.use_smithchart,
                fn=args.fn,
                z0=args.z0,
                markers=args.markers,
                engine=engine,
            )

    p.set_defaults(func=f)

    p = subparsers.add_parser("optimize", help="Optimize antenna")
    add_common(p)
    add_engine_args(p)
    p.add_argument(
        "--params",
        nargs="+",
        default=None,
        type=str,
        help="Use these optimization params.",
    )
    p.add_argument("--z0", default=50, type=float, help="Use this reference impedance.")
    p.add_argument(
        "--resonance",
        default=False,
        action="store_true",
        help="Optimize to resonance instead of matching an impedance.",
    )
    p.add_argument(
        "--opt_gain",
        default=False,
        action="store_true",
        help="Also try to optimize gain.",
    )

    def f(args):
        builder = get_builder(args.builder)
        engine = engine_factory_from_args(args)
        opt_builder = optimize(
            builder(),
            args.params,
            z0=args.z0,
            opt_gain=args.opt_gain,
            resonance=args.resonance,
            engine=engine,
        )
        print()
        print("# Optimized knobs — paste over the design's params block:")
        print(
            builder_params_source(
                opt_builder,
                name=emit_params_name(args.builder),
                default_precision=6,
            )
        )
        compare_patterns([engine(builder()), engine(opt_builder)], fn=args.fn)

    p.set_defaults(func=f)

    p = subparsers.add_parser(
        "params", help="Print a design's knob values as paste-ready Python"
    )
    p.add_argument(
        "--builder",
        type=str,
        default="dipoles.invvee:dipole",
        help="Antenna builder (name or name:variant) to dump.",
    )
    p.add_argument(
        "--name",
        type=str,
        default=None,
        help="Variable name for the emitted block "
        "(default: <variant>_params, or default_params).",
    )
    p.add_argument(
        "--no-ui",
        dest="no_ui",
        default=False,
        action="store_true",
        help="Omit the ui_params block (knob values only).",
    )
    p.add_argument(
        "--wrap",
        choices=["dict", "mappingproxy"],
        default="dict",
        help="Wrap the block in MappingProxyType to match the catalog style.",
    )

    def f(args):
        builder = get_builder(args.builder)
        name = args.name or emit_params_name(args.builder)
        # For a real variant, emit only its deltas from default_params — the
        # minimal <variant>_params overlay (see resolve_variant_params). A bare
        # design / :default emits the full block, since it *is* the baseline.
        design, _, variant = args.builder.partition(":")
        base = None
        if variant and variant != "default":
            cls = resolve_class(design)
            if cls is not None and hasattr(
                getattr(cls, f"{variant}_params", None), "keys"
            ):
                base = dict(cls.default_params)
        print(
            builder_params_source(
                builder(),
                name=name,
                include_ui=not args.no_ui,
                wrap=args.wrap,
                base=base,
            )
        )

    p.set_defaults(func=f)

    p = subparsers.add_parser("pattern", help="Display far field of antenna")
    add_common(p)
    add_engine_args(p)
    p.add_argument(
        "--wireframe", default=False, action="store_true", help="Draw wireframe."
    )
    p.add_argument(
        "--elevation_angle",
        default=15,
        type=float,
        help="Elevation angle for azimuth plot.",
    )

    def f(args):
        builder = get_builder(args.builder)
        engine = engine_factory_from_args(args)
        eng = engine(builder())
        if args.wireframe:
            pattern3d(eng, fn=args.fn)
        else:
            pattern(eng, elevation_angle=args.elevation_angle, fn=args.fn)
        # Power budget (issue #299): where the source watts went, from the
        # excited solve the pattern just ran. Only printed when the design
        # has a network with something to report.
        budget = getattr(eng, "_excited_power_budget", None)
        p_in = getattr(eng, "_excited_p_in", None)
        if budget and p_in:
            print(f"input power: {p_in * 1e3:.4g} mW")
            p_network = 0.0
            for label, w in budget:
                w = max(0.0, w)
                p_network += w
                print(f"  {label}: {w * 1e3:.4g} mW ({w / p_in:.1%})")
            p_ant = p_in - p_network
            # "accepted", not "radiated": this is the structural remainder
            # that reaches the wires — over a real ground the far field gets
            # less (see far_field.radiated_fraction, the third ledger).
            print(f"  antenna (accepted): {p_ant * 1e3:.4g} mW ({p_ant / p_in:.1%})")

    p.set_defaults(func=f)

    p = subparsers.add_parser(
        "compare_patterns", help="Display far field of multiple antennas"
    )
    add_common(p, use_builders=True)
    add_engine_args(p, plural=True)
    add_pattern_common(p)

    def f(args):
        ground = (
            args.ground if args.ground is _GROUND_UNSET else parse_ground(args.ground)
        )
        pairs = broadcast_pairs(args.builders, args.engines)
        multi_engine = len(set(args.engines)) > 1
        multi_builder = len(set(args.builders)) > 1
        instances = []
        labels = []
        for bname, espec in pairs:
            eng = make_engine_factory(espec, ground)
            instances.append(eng(get_builder(bname)()))
            if multi_engine and multi_builder:
                labels.append(f"{bname}/{espec}")
            elif multi_engine:
                labels.append(espec)
            else:
                labels.append(bname)
        compare_patterns(
            instances,
            elevation_angle=args.elevation_angle,
            fn=args.fn,
            builder_names=labels,
            azimuth_f=args.azimuth_f,
            azimuth_r=args.azimuth_r,
        )

    p.set_defaults(func=f)

    p = subparsers.add_parser("export", help="Export antenna to a NEC2 .nec card deck")
    p.add_argument(
        "--builder",
        type=str,
        default="dipoles.invvee:dipole",
        help="Antenna builder to export.",
    )
    p.add_argument(
        "--ground",
        default=_GROUND_UNSET,
        help="Ground model: free | pec | finite | finite:<eps_r>,<sigma> "
        "(default: finite, matching PyNECEngine).",
    )
    p.add_argument("--out", default=None, help="Write the deck here (default: stdout).")
    p.add_argument(
        "--freq",
        default=None,
        type=float,
        help="Frequency in MHz for the FR card (default: the builder's freq).",
    )
    p.add_argument(
        "--no-pattern",
        dest="include_rp",
        action="store_false",
        default=True,
        help="Omit the RP far-field card (impedance only, via XQ).",
    )

    def f(args):
        from .nec_export import export_nec

        builder = get_builder(args.builder)
        kwargs = {"include_rp": args.include_rp}
        if args.ground is not _GROUND_UNSET:
            kwargs["ground"] = parse_ground(args.ground)
        if args.freq is not None:
            kwargs["freq"] = args.freq
        deck = export_nec(builder(), **kwargs)
        if args.out:
            with open(args.out, "w") as fh:
                fh.write(deck)
            print(f"wrote {args.out}")
        else:
            print(deck, end="")

    p.set_defaults(func=f)

    p = subparsers.add_parser(
        "list", help="List available antenna designs (built-in and user)"
    )
    p.add_argument(
        "filter",
        nargs="?",
        default=None,
        help="Case-insensitive substring; only matching design names are shown.",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--builtin-only", action="store_true", help="Only the built-in designs."
    )
    group.add_argument(
        "--user-only", action="store_true", help="Only the user-authored designs."
    )

    def f(args):
        from itertools import groupby

        q = args.filter.lower() if args.filter else None

        def keep(name):
            return q is None or q in name.lower()

        sections: list[tuple[str, list[str]]] = []
        if not args.user_only:
            names = [n for n in list_builtin_designs() if keep(n)]
            for fam, grp in groupby(names, key=lambda n: n.split(".")[0]):
                sections.append((fam, list(grp)))
        if not args.builtin_only:
            users = [f"{USER_NS}.{stem}" for stem, _ in iter_design_files()]
            users = sorted(u for u in users if keep(u))
            if users:
                sections.append((USER_NS, users))

        if not sections:
            where = f" matching {args.filter!r}" if q else ""
            print(f"no designs{where}")
            return

        for i, (fam, members) in enumerate(sections):
            if i:
                print()
            print(f"{fam}")
            for name in members:
                print(f"  {name}")

    p.set_defaults(func=f)

    def _resolve_design_path(name_or_path):
        """A `<name|path>` from an allow/screen command → the design file Path,
        or None if it can't be found. Accepts a filesystem path, a `user.<name>`
        design name, or a bare `<name>`."""
        from pathlib import Path

        from .user_designs import USER_NS, find_design_file

        p = Path(name_or_path)
        if p.suffix == ".py" and p.is_file():
            return p
        stem = name_or_path
        if stem.startswith(f"{USER_NS}."):
            stem = stem[len(USER_NS) + 1 :]
        return find_design_file(stem)

    p = subparsers.add_parser(
        "screen",
        help="Show what a design file does that's unusual, without running it "
        "(an advisory to inform whether to allow it).",
    )
    p.add_argument(
        "path",
        help="Path to a design .py file — e.g. one someone sent you.",
    )

    def f(args):
        from pathlib import Path

        from .design_screen import screen_file

        path = Path(args.path)
        if not path.is_file():
            print(f"no such file: {path}")
            raise SystemExit(2)
        report = screen_file(path)
        if not report.blocked:
            print(
                f"{path.name}: nothing unusual — only antennaknobs + the math "
                f"standard library, no code execution or file/network access."
            )
            return
        print(report.summary())
        print(
            "\nThat doesn't mean it's malicious, but review it before you allow "
            "it. To let it run: `antennaknobs allow <name>` (add --edits if it's "
            "your own file)."
        )
        raise SystemExit(1)

    p.set_defaults(func=f)

    p = subparsers.add_parser(
        "allow",
        help="Allow a user design to run (it runs code on your machine).",
    )
    p.add_argument("name", help="A design name (user.<name> or <name>) or a .py path.")
    p.add_argument(
        "--edits",
        action="store_true",
        help="Allow this file AND your future edits to it (for a design you "
        "author). Without this, only the current version is allowed, and any "
        "later change asks again.",
    )

    def f(args):
        from . import design_screen, design_trust

        path = _resolve_design_path(args.name)
        if path is None:
            print(f"no such design: {args.name}")
            raise SystemExit(2)
        # Show the advisory so the decision is informed.
        report = design_screen.screen_file(path)
        print(report.summary())
        design_trust.trust(path, mode="always" if args.edits else "pinned")
        scope = "and your future edits" if args.edits else "(this version)"
        print(f"\nallowed {path.name} {scope}.")

    p.set_defaults(func=f)

    p = subparsers.add_parser("disallow", help="Stop allowing a user design to run.")
    p.add_argument("name", help="A design name (user.<name> or <name>) or a .py path.")

    def f(args):
        from . import design_trust

        path = _resolve_design_path(args.name)
        if path is None:
            print(f"no such design: {args.name}")
            raise SystemExit(2)
        print(
            f"no longer allowing {path.name}."
            if design_trust.untrust(path)
            else f"{path.name} was not allowed."
        )

    p.set_defaults(func=f)

    args = parser.parse_args(args=arguments)
    level = logging.WARNING - 10 * min(args.verbose, 2)
    logging.basicConfig(level=level, format="%(name)s: %(message)s")

    from .design_trust import DesignNotTrustedError

    try:
        args.func(args)
    except DesignNotTrustedError as exc:
        # A design the user hasn't allowed yet: show the clean guidance, not a
        # traceback.
        print(str(exc))
        raise SystemExit(1) from None
