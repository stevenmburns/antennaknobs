r"""A complete, working example antenna. Copy it and make it your own.

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
Claude Code can write a design for you. It is a program you install and
run in a terminal window, and it needs a paid Claude account; install
steps are at https://claude.com/claude-code. Then:
  1. Open a terminal: Command Prompt or PowerShell on Windows, Terminal on
     macOS or Linux.
  2. Go to this folder:
         cd %USERPROFILE%\.antennaknobs\designs     (Windows)
         cd ~/.antennaknobs/designs                  (macOS / Linux)
  3. Type  claude  and press Enter.
  4. Type what you want in plain English, the way you would ask a person:
         make me a 14 MHz dipole in free space fed with 10 m of RG-8X
Claude reads the CLAUDE.md file next to this one, writes the .py file,
runs it to check its work, and fixes its own mistakes. A chat assistant
in a browser can't run the code, so it can't check it: what it writes for
this folder often calls functions that don't exist.

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

GOING FURTHER: THE WHOLE STATION
--------------------------------
A design can also model its feed system — coax, a balun/unun, a tuner —
by adding an optional ``build_network(self)`` method: the wire that was
driven below loses its ``ex=`` and gets a NAME instead
(``Wire(feed_lo, feed_hi, name="feed")``), and the network drives it through
real feedline and matchbox
components, re-referencing SWR and the power budget to the rig. See the
"build_network" section of CLAUDE.md in this folder for the contract and
the pre-built boxes in ``antennaknobs.station``; built-in examples:
``dipoles.invvee_coax_station`` (just coax), ``wire.efhw_sloper``
(49:1 unun + coax).
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder, Wire


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
        """Return the antenna as a list of straight wires.

        Each one is ``Wire(start, end)``, where ``start`` and ``end`` are
        ``(x, y, z)`` points in metres. Everything else is an optional keyword:
          * ``ex=1 + 0j`` on the ONE wire the transmitter drives,
          * ``n_seg=`` to pin how many segments the wire is divided into.
            Leave it out and the wire is meshed at the design density
            (``nominal_nsegs`` segments per quarter wave at ``design_freq``),
            which is what you want almost always,
          * ``name=`` and ``spec=`` (see CLAUDE.md) when you need them.
        """
        # Size each arm from the design frequency: a half-wave dipole is about
        # lambda/2 tip-to-tip, so each arm is ~lambda/4. ``length_factor`` trims
        # it to resonance (real wire runs a few % short of the ideal).
        wavelength = self.design_wavelength  # free-space λ at design_freq, in metres
        h = (wavelength / 4.0) * self.length_factor  # each arm, metres
        z = self.height
        eps = 0.01  # tiny half-gap at the centre where the feed point sits

        # A center-fed dipole lying along the y axis at height z:
        #
        #   tip(-h) ---- arm ---- (-eps)[ feed ](+eps) ---- arm ---- tip(+h)
        #
        left_tip = (0.0, -h, z)
        right_tip = (0.0, h, z)
        feed_lo = (0.0, -eps, z)
        feed_hi = (0.0, eps, z)

        # No n_seg: each wire is meshed at the design density, so the counts
        # follow the length knob and the band.
        return [
            Wire(left_tip, feed_lo),  # left arm
            Wire(feed_hi, right_tip),  # right arm
            Wire(feed_lo, feed_hi, ex=1 + 0j),  # the driven feed gap
        ]
