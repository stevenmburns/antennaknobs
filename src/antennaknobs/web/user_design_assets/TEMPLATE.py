"""A complete, working example antenna. Copy it and make it your own.

HOW TO USE THIS FILE
--------------------
1. Copy it to a new file in this same folder, e.g. ``my_dipole.py``. The
   file name (lowercase, words joined by underscores) becomes the antenna's
   name in the app: ``my_dipole.py`` shows up as "user.my_dipole".
2. Change the numbers in ``default_params`` and the geometry in
   ``build_wires``.
3. Refresh the web page. Your antenna appears under "Your designs". If you
   made a mistake, the page shows the error so you can fix it.

NOT A PYTHON PROGRAMMER?
------------------------
Open Claude Code in this folder and just ask, for example:
    "make me a 40-meter off-center-fed dipole"
The CLAUDE.md file next to this one tells Claude everything it needs to
write a valid design and check its work.

THE RULES (keep it this simple)
-------------------------------
- One file = one antenna. The file name is the antenna name
  (lowercase_with_underscores.py, no spaces, no dots except ``.py``).
- Define a class named exactly ``Builder`` that subclasses ``AntennaBuilder``.
- Stay self-contained: only import from ``antennaknobs`` and the Python
  standard library. Don't import other files in this folder.
- Every built-in design follows these same rules, so any file from the
  installed package's ``antennaknobs/designs/`` folders also works here
  verbatim — copying one in is a great way to start a variation.
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder


class Builder(AntennaBuilder):
    # Optional friendly name shown in the UI. Without it, the file name is used.
    label = "Example dipole"

    # The knobs. Every entry here becomes a slider in the UI.
    #
    # This dipole is sized from ``design_freq`` rather than fixed metres, which
    # is the recommended pattern: ``design_freq`` scales the geometry AND drives
    # the app's band selector + measurement-freq slider, so the antenna lands on
    # its band and can be tuned there. Change ``design_freq`` to retune to any
    # band (e.g. 7.1 for 40m). A fixed-metre design instead strands the
    # measurement frequency near 14 MHz -- see CLAUDE.md ("the 40m trap").
    default_params = MappingProxyType(
        {
            "design_freq": 14.1,  # MHz -- the band this antenna is cut for (20m)
            "freq": 14.1,  # MHz -- where you measure SWR / impedance
            "length_factor": 0.96,  # fine length trim near 1.0 (drag to resonate)
            "height": 10.0,  # metres -- height above ground
            # Optional UI hints. "default_view" sets the first 2-D view:
            # "xy" (top-down), "xz" or "yz" (from the side).
            "ui_params": MappingProxyType({"default_view": "xz"}),
        }
    )

    def build_wires(self):
        """Return the antenna as a list of straight wire segments.

        Each entry is ``(start, end, n_segments, feed)``:
          * ``start`` / ``end`` are ``(x, y, z)`` points in metres,
          * ``n_segments`` is how finely to divide that wire (more = finer,
            slower) -- ``self.nominal_nsegs`` is a sensible default,
          * ``feed`` is ``1 + 0j`` on the ONE segment driven by the
            transmitter, and ``None`` on every other wire.
        """
        # Size each arm from the design frequency: a half-wave dipole is about
        # lambda/2 tip-to-tip, so each arm is ~lambda/4. ``length_factor`` trims
        # it to resonance (real wire runs a few % short of the ideal).
        wavelength = 299.792458 / self.design_freq  # metres
        h = (wavelength / 4.0) * self.length_factor  # each arm, metres
        z = self.height
        eps = 0.01  # tiny half-gap at the centre where the feed point sits

        arm_segs = self.nominal_nsegs
        feed_segs = max(1, self.nominal_nsegs // 7)

        # A center-fed dipole lying along the y axis at height z:
        #
        #   tip(-h) ---- arm ---- (-eps)[ feed ](+eps) ---- arm ---- tip(+h)
        #
        left_tip = (0.0, -h, z)
        right_tip = (0.0, h, z)
        feed_lo = (0.0, -eps, z)
        feed_hi = (0.0, eps, z)

        return [
            (left_tip, feed_lo, arm_segs, None),  # left arm
            (feed_hi, right_tip, arm_segs, None),  # right arm
            (feed_lo, feed_hi, feed_segs, 1 + 0j),  # the driven feed gap
        ]
