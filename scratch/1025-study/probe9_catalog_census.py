"""AK#1025 probe 9: which catalog decks are BURIED, and of which class?

Classes that matter for the GE ground flag:
  contact      — some wire END sits exactly at z=0 (bonded); flag 1
  fully buried — wires below z=0 and nothing touching the plane; flag -1
  above        — nothing below z=0
"""

import importlib
import pkgutil

import antennaknobs.designs as D

rows = []
for m in pkgutil.walk_packages(D.__path__, D.__name__ + "."):
    if m.ispkg:
        continue
    try:
        mod = importlib.import_module(m.name)
    except Exception:  # noqa: BLE001 - a refusal IS a result in a probe
        continue
    B = getattr(mod, "Builder", None)
    if B is None:
        continue
    try:
        wires = B().build_wires()
        zs = [float(w.p0[2]) for w in wires] + [float(w.p1[2]) for w in wires]
    except Exception as e:  # noqa: BLE001 - a refusal IS a result in a probe
        rows.append(
            (
                m.name.split("designs.", 1)[-1],
                None,
                None,
                f"build failed: {type(e).__name__}",
            )
        )
        continue
    zmin, zmax = min(zs), max(zs)
    if zmin >= 0.0:
        cls = "above"
    elif any(abs(z) == 0.0 for z in zs):
        cls = "CONTACT (flag 1)"
    else:
        cls = "FULLY BURIED (flag -1)"
    rows.append((m.name.split("designs.", 1)[-1], zmin, zmax, cls))

for name, zmin, zmax, cls in sorted(rows, key=lambda r: (r[3] or "", r[0])):
    if cls == "above":
        continue
    z0 = f"{zmin:8.3f}" if zmin is not None else "    ?   "
    z1 = f"{zmax:8.3f}" if zmax is not None else "    ?   "
    print(f"{name:52s} zmin={z0} zmax={z1}  {cls}")
