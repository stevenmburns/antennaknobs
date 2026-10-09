"""Three feed models on the inverted vee: ``dipoles.invvee`` (bridge wire
carrying a delta gap), ``dipoles.invvee_apex`` (series gap at the closed
apex) and ``dipoles.invvee_endport`` (the arms stop a real gap apart and the
source sits across their two ends). Offered on all three tabs as
``dipoles.endport_feed_on_invvee:feed models``."""

from antennaknobs import analyses as an


def build_studies():
    """The three feeds on one convergence chart. bs2 only: it is the engine
    that serves both the end ports and the apex gap."""
    return [
        an.convergence(
            name="feed models",
            cross=(
                an.Cross(
                    designs=(
                        "dipoles.invvee",
                        "dipoles.invvee_apex",
                        "dipoles.invvee_endport",
                    )
                ),
                an.Cross(engines=("momwire:bspline",)),
            ),
            ground="free",
        ),
    ]
