"""Is the reuse census paid once per geometry? Three sinusoidal solves of the
10-element Yagi over Sommerfeld ground with reuse on, in one process: the
stock geometry, the same again, then the director length moved 1 %."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import measure  # noqa: E402

name = "yagi10_reuse_sin"
for label, df in (
    ("stock", None),
    ("same again", None),
    ("director_factor x1.01", 0.95 * 1.01),
):
    if df is not None:
        measure.CASES[name][4]["director_factor"] = df
    r = measure.run(name, True)
    print(
        f"{label:24} census {r['census_s']:.2f} s  fill {r['fill_s']:.2f} s  "
        f"total {r['wall_s']:.2f} s  reuse {r['reuse_state']}"
    )
