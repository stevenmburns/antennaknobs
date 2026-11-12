"""The CLI's multi-band optimize on an invented three-knob design, with and
without ``--port-sites``.

The design is the benchmark's inverted L over Sommerfeld ground
(`bench_coil_slide.CoilL`): ``h`` (the vertical's height, a geometry knob),
``coil_pct`` (the coil's position as a percentage of the top wire) and
``coil_uh`` (its inductance, a network value). It is served to the CLI under
an invented spec name, then ``antennaknobs optimize --bands`` runs twice and
the wall time of each is printed beside its report.

    python scratch/port-sites-1915/cli_multiknob.py
"""

import contextlib
import io
import time

from bench_coil_slide import BANDS, CoilL

from antennaknobs import cli

SPEC = "invented.coil_l"


def main():
    real = cli.resolve_class
    cli.resolve_class = lambda s: CoilL if s == SPEC else real(s)
    base = [
        "optimize",
        "--builder",
        SPEC,
        "--engine",
        "momwire",
        "--ground",
        "finite:13,0.005",
        "--bands",
        BANDS,
        "--params",
        "h",
        "coil_pct",
        "coil_uh",
        "--bound",
        "h=6.5:7.5",
        "--bound",
        "coil_pct=5:85",
        "--bound",
        "coil_uh=3:7",
        "--max-evals",
        "60",
    ]
    for label, extra in (("rebuild", []), ("port-sites", ["--port-sites"])):
        out = io.StringIO()
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(out):
            cli.cli(base + extra)
        wall = time.perf_counter() - t0
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        print(f"== {label}: {wall:.2f} s")
        for ln in lines:
            if ln.startswith(("#", "worst", "port sites")) or "=" in ln:
                print("  " + ln)


if __name__ == "__main__":
    main()
