"""The apex feed on the inverted vee (AK#1757 step 7): E7, the study that
compares the inverted vee's two feed spellings, ``dipoles.invvee`` (the
bridge-wire feed) and ``dipoles.invvee_apex`` (the exact apex feed). It is
offered on both their tabs, as ``dipoles.apex_feed_on_invvee:feed spelling
(E7)``."""

from antennaknobs import analyses as an


def build_studies():
    """E7: the bridge-wire feed and the exact apex feed on one convergence
    chart. 2 designs x 3 engines = 6 curves, the cap (#1787); NEC-2 cannot
    feed the apex knot, so that cell is refused by name (razor-2p stands in
    for NEC-5)."""
    return [
        an.convergence(
            name="feed spelling (E7)",
            cross=(
                an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
                an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec2")),
            ),
        ),
    ]
