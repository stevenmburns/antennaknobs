# AK#1714 fixtures — the two circuits that drive dcl knobs

Byte-exact copies of examples AC6LA (Dan Maguire) wrote for SimNEC and
that SimNEC ships in its examples tree, from the SimNEC 5.3 install on the
development machine (`~/.SimNEC/5/3/Examples/AC6LA_SimNEC/`, examples
version 164). Both files were saved by SimNEC 2.4b10
(`<XMLVersionControl>`). They are `-text` in `.gitattributes`: each mixes
CRLF and LF line ends, and a copy that git normalised would no longer be the
file.

| file | original name | sha256 |
|---|---|---|
| `3el-20m-yagi-sy.ssn` | `3-el 20m Yagi (4nec2 SY cards).ssn` | `dc119bd872fa8f090dcc8a504a5da864f339f595663a9b079eece997a259023a` |
| `half-squares-sy.ssn` | `Parasitic Half-Squares (4nec2 SY cards).ssn` | `4f560660a1a4742d3bd6adedb6ea76ebaae3f3ecaeb68ae531ac8d80472b5a50` |

Both are AC6LA's conversions of 4nec2 decks (`3YAGI20.NEC` and L. B. Cebik's
`80HSBEAM.NEC`), with the SY cards rewritten as `dcl` lines above `NEC2`,
as the files' own comments instruct.

What each one exercises:

- `3el-20m-yagi-sy.ssn` — the primary circuit: seven commented constants
  (`dcl hgh = 50*0.3048 ; // Height (50 feet)`, ...) named directly in the
  GW cards, `NEC2  // ====` and `NECEND  // ====` with trailing comments, an
  `EN` inside the block, `NECOptions.mhosPerMeter` beside `LD 5` cards, and
  `FR 0 0 0 0 freq 0` naming a `freq` whose `dcl` is commented out.
- `half-squares-sy.ssn` — expressions in the card fields (`-len/2`,
  `hgh-sln`), constants in `LD 4` (`Xc`) and `LD 5` (`Cu`) cards, mixed-case
  names (`Xc`, `Cu`; the file notes SimNEC names are case-sensitive), and a
  `dcl R_4 = 0+j50` used only by an N-block `R` component, which stays
  unapplied.
