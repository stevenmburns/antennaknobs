"""The CLI's multi-band optimize on an invented SimNEC deck whose capacitor
position is a slider, with and without ``--port-sites``.

The deck is `tests/test_ssn_port_sites_1915.py`'s (a 162-segment jammed wire
fed by a NECSource at 100 %, a C(Cap_F) NECSource at Cap_Pct). Without the
option the importer cuts the load's segment out, so the position knob reads a
zero slope; with it the load rides its piece at the exact percentage.

    python scratch/port-sites-1915/ssn_position_knob.py
"""

import contextlib
import io
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import antennaknobs.cli  # noqa: F401 — the module; the package re-exports cli()
from test_ssn_port_sites_1915 import FREQS, TEXT

cli = sys.modules["antennaknobs.cli"]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        deck = Path(tmp) / "invented_flat_top.ssn"
        deck.write_text(TEXT)
        base = [
            "optimize",
            "--builder",
            f"@{deck}",
            "--engine",
            "momwire",
            "--ground",
            "finite:13,0.005",
            "--bands",
            ",".join(str(f) for f in FREQS),
            "--params",
            "par_H_len",
            "par_Cap_Pct",
            "par_Cap_F",
            "--bound",
            "par_H_len=15:19",
            "--bound",
            "par_Cap_Pct=20:60",
            "--bound",
            "par_Cap_F=50:120",
            "--max-evals",
            "60",
        ]
        for label, extra in (("without", []), ("port-sites", ["--port-sites"])):
            out = io.StringIO()
            t0 = time.perf_counter()
            with contextlib.redirect_stdout(out):
                cli.cli(base + extra)
            wall = time.perf_counter() - t0
            print(f"== {label}: {wall:.2f} s")
            for ln in out.getvalue().splitlines():
                if ln.startswith(("# minimax", "worst", "port sites")) or (
                    "did not move" in ln or "par_" in ln and "=" in ln
                ):
                    print("  " + ln)


if __name__ == "__main__":
    main()
