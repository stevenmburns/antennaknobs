"""Hash census: every .nec fixture in the repo, imported both ways."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
from antennaknobs.nec_import import parse_nec  # noqa: E402

out = {}
for f in sorted((ROOT / "tests" / "fixtures").rglob("*.nec")):
    rel = str(f.relative_to(ROOT))
    text = f.read_text(errors="replace")
    row = {}
    for mode in (False, True):
        try:
            d = parse_nec(text, name=f.name, network=mode)
            blob = repr(d.wire_tuples(specs=mode))
            if mode:
                blob += repr(d.network())
            row["net" if mode else "plain"] = hashlib.sha256(blob.encode()).hexdigest()[
                :16
            ]
        except Exception as e:  # noqa: BLE001 — a census records every refusal
            row["net" if mode else "plain"] = f"{type(e).__name__}: {e}"[:150]
    out[rel] = row
print(json.dumps(out, indent=1, sort_keys=True))
