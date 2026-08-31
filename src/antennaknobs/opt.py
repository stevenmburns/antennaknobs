from . import Antenna
from .far_field import get_elevation

import numpy as np

# from scipy.optimize import minimize_scalar
from scipy.optimize import minimize


def _parse_path(name: str):
    """`bands.0.halfdriver_factor` → ['bands', 0, 'halfdriver_factor'].
    Integer-looking segments become ints so they index tuples/lists; the
    rest stay strings for attr or dict access."""
    parts = []
    for p in name.split("."):
        if p.lstrip("-").isdigit():
            parts.append(int(p))
        else:
            parts.append(p)
    return parts


def _get_path(obj, name):
    """Walk a dotted path. Tries dict-key, sequence-index, then attribute
    at each step — so it works against Builder attrs, the bands tuple,
    and per-band dicts in one expression."""
    for p in _parse_path(name):
        if isinstance(obj, dict):
            obj = obj[p]
        elif isinstance(obj, (list, tuple)):
            obj = obj[int(p)]
        else:
            obj = getattr(obj, p)
    return obj


def _set_path(obj, name, value):
    """Functional update: dicts and tuples are rebuilt on the way back
    up so the original `bands` tuple in the class's default_params (a
    shared MappingProxyType reference) never gets mutated under one
    Builder instance.

    The outermost call writes back to the Builder via setattr — which
    AntennaBuilder routes into _params — leaving class-level defaults
    untouched."""
    path = _parse_path(name)

    def _recur(cur, idx):
        if idx == len(path) - 1:
            leaf = path[idx]
            if isinstance(cur, dict):
                return {**cur, leaf: value}
            if isinstance(cur, tuple):
                i = int(leaf)
                return tuple(value if k == i else v for k, v in enumerate(cur))
            if isinstance(cur, list):
                i = int(leaf)
                new = list(cur)
                new[i] = value
                return new
            setattr(cur, leaf, value)
            return cur
        head = path[idx]
        if isinstance(cur, dict):
            new_child = _recur(cur[head], idx + 1)
            return {**cur, head: new_child}
        if isinstance(cur, tuple):
            i = int(head)
            new_child = _recur(cur[i], idx + 1)
            return tuple(new_child if k == i else v for k, v in enumerate(cur))
        if isinstance(cur, list):
            i = int(head)
            new_child = _recur(cur[i], idx + 1)
            new = list(cur)
            new[i] = new_child
            return new
        child = getattr(cur, head)
        new_child = _recur(child, idx + 1)
        setattr(cur, head, new_child)
        return cur

    _recur(obj, 0)


def optimize(
    antenna_builder,
    independent_variable_names,
    *,
    z0=50,
    resonance=False,
    opt_gain=False,
    bounds=None,
    fractions=None,
    engine=Antenna,
):

    def objective(independent_variables):

        for v, nm in zip(
            independent_variables, independent_variable_names, strict=True
        ):
            _set_path(antenna_builder, nm, v)

        a = engine(antenna_builder)
        zs = a.impedance()
        # Only compute the far-field pattern when opt_gain is on — get_elevation
        # integrates over the full sphere and dominates per-iteration cost
        # (>5× the impedance solve). For pure impedance / resonance objectives
        # the computed max_gain is unused.
        max_gain = get_elevation(a)[1] if opt_gain else 0.0
        del a

        for z in zs:
            reflection_coefficient = (z - z0) / (z + z0)
            rho = abs(reflection_coefficient)
            swr = (1 + rho) / (1 - rho)
            rho_db = np.log10(rho) * 10.0

            if opt_gain:
                print(
                    "Impedance at %s: (%.3f,%+.3fj) Ohms rho=%.4f swr=%.4f, rho_db=%.3f max_gain=%.2f"
                    % (str(antenna_builder), z.real, z.imag, rho, swr, rho_db, max_gain)
                )
            else:
                print(
                    "Impedance at %s: (%.3f,%+.3fj) Ohms rho=%.4f swr=%.4f, rho_db=%.3f"
                    % (str(antenna_builder), z.real, z.imag, rho, swr, rho_db)
                )

        # Multi-feed designs score their WORST feed (minimax, issue #785): a
        # sum lets one badly mismatched element hide behind several good ones.
        # Same aggregation as the web optimizer; single-feed is unchanged.
        res = 0
        if resonance:
            res += max((abs(z.imag) for z in zs), default=0.0)
        else:
            res += max((abs(z - z0) for z in zs), default=0.0)

        if opt_gain:
            res -= 100 * max_gain

        return res

    #'Nelder-Mead', tol=0.001
    #'Powell', options={'maxiter':100, 'disp': True, 'xtol': 0.0001}

    x0 = tuple(_get_path(antenna_builder, nm) for nm in independent_variable_names)
    if bounds is None:
        if fractions is None or len(fractions) != len(x0):
            frac = 5 / 3 if fractions is None else fractions[0]
            bounds = tuple((x / frac, x * frac) for x in x0)
        else:
            bounds = tuple(
                (x / frac, x * frac) for x, frac in zip(x0, fractions, strict=True)
            )

    result = minimize(
        objective,
        x0=x0,
        method="Powell",
        options={"maxiter": 100, "disp": True, "xtol": 0.0001},
        tol=0.001,
        bounds=bounds,
    )

    print(result)

    for x, nm in zip(result.x, independent_variable_names, strict=True):
        _set_path(antenna_builder, nm, x)

    print(objective(result.x))

    return antenna_builder
