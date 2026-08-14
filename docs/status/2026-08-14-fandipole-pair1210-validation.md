# Validation study: the catalog fan dipole (`multiband.fandipole`, `pair_12_10`)

**2026-08-14** · instrument `scripts/bench_fandipole_pair1210.py` · artifact
`scratch/fandipole-pair1210-study.json` · free space (keeps NEC-5's Michalski
ground offset out of the formulation comparison)

The 12m/10m pair variant of the catalog fan: two dipoles bonded at the shared
cone feed, fed by the as-built bridge idiom — a 2 cm one-segment feed wire
(`eps = 0.01`) whose ends are each a K=3 junction (two band risers + bridge).
Two questions: do the oracles agree on this harder-than-ByDipole1 geometry,
and how big is the bridge-feed artifact that a partition-addressed node gap
(momwire#315) would remove?

## 1. Cross-engine ladders (nominal_nsegs 11 → 45, both band centers)

| n | bs2 | bs1 | nec5 | pynec |
|---|---|---|---|---|
| **12m, 24.97 MHz** | | | | |
| 11 | 65.45+27.24j | 65.11+26.10j | 64.78+23.69j | 49.97+21.32j |
| 21 | 65.54+27.79j | 65.41+27.23j | 65.21+25.86j | 52.93+22.77j |
| 45 | 65.60+28.15j | 65.55+27.85j | 65.44+27.10j | 54.43+23.69j |
| **10m, 28.47 MHz** | | | | |
| 11 | 69.10+36.26j | 68.27+33.47j | 68.48+32.62j | 52.22+29.13j |
| 21 | 69.43+37.75j | 69.13+36.58j | 69.22+36.13j | 55.48+31.24j |
| 45 | 69.63+38.65j | 69.51+38.07j | 69.54+37.77j | 57.33+32.60j |

**bs2 / bs1 / nec5 agree.** At n=45 the three lanes sit within ~1 Ω on X and
~0.2 Ω on R on both bands, with the usual characters: bs2 essentially flat
from n=21, bs1 converging from below a little slower, NEC-5 marching its
O(1/N) walk from below (the #890 finding — a Richardson pair would close the
remaining gap). For a two-band structure with coupled parallel elements and
two K=3 junctions, this is three-oracle agreement at the same level the
ByDipole1 study showed for a lone wire.

**The NEC-2 lineage (pynec) is invalid on this feed idiom.** It reads ~11 Ω
low on R at every rung of both bands, and it is not a convergence problem —
the ladder crawls upward but is nowhere near the other lanes at n=45. The
eps sweep below shows why it cannot be rescued by refinement: it diverges as
the bridge shrinks. Mechanism is the known NEC-2 pathology set: the
one-segment bridge is flanked by a junction at each end and is ~5× shorter
than its neighbour segments, i.e. the junction-fan collocation error (#484)
plus the small-Δ/a floor (#448 lineage). The extended thin-wire kernel does
not help — measured identical to 3 decimals with `extended_thin_wire_kernel`
on and off, because NEC-2 gates EK off on junction-adjacent segments and
BOTH ends of the bridge are junctions. Census implication: bridge-fed fans
belong with the deliberately-exempt nec2 feed sites, not in its voting pool.

## 2. The feed-bridge artifact (the momwire#315 number)

Fixed mesh (nominal 35), shrinking only the bridge: the two feed-junction
points S/T move from y = ±0.01 to ±eps (arms and spokes untouched), then a
linear eps→0 extrapolation from the two smallest rungs.

| lane | 12m: eps→0 limit | as-built − limit | 10m: eps→0 limit | as-built − limit |
|---|---|---|---|---|
| bs2 | 65.87+27.49j | **−0.28+0.56j** | 70.77+41.22j | **−1.21−2.83j** |
| bs1 | 65.78+27.13j | −0.27+0.55j | 70.60+40.55j | −1.19−2.88j |
| nec5 | 65.67+26.42j | −0.28+0.41j | 70.70+40.47j | −1.19−2.95j |
| pynec | (36.81+15.39j) | diverges | (38.71+23.11j) | diverges |

The artifact is **engine-independent to ±0.1 Ω** across bs2/bs1/nec5 — three
formulations, one answer for what the bridge costs. On 12m it is ~0.6 Ω; on
**10m it is ~3.1 Ω** (−1.2 R, −2.9 X on a 70+39j feedpoint). The higher band
pays more because at 28.47 MHz the off-resonant 12m element loads the feed
region, so the feed detail matters more.

This is the measured consumer for momwire#315 (partition-addressed node
gaps): the eps→0 limit is exactly what a true {both-left}|{both-right} gap
would compute directly, and on this catalog design the bridge idiom
mis-states the 10m feedpoint by ~3 Ω.

## Caveats

- eps→0 by linear extrapolation from eps = 0.005 and 0.0025; the smallest
  rung's bridge is 5 mm (Δ/a ≈ 5–10 for the reduced kernel). The three-lane
  agreement of the artifact — including NEC-5, a different formulation — is
  the evidence the extrapolation is measuring geometry, not kernel floor.
- Fixed mesh for the eps sweep (nominal 35); ladder shows bs2 moves ≲0.1 Ω
  from n=35 to n=45, well under the artifact being measured.
- Free space. Over ground the absolute impedances shift but the bridge
  artifact is a feed-region effect and should carry; not measured here.
- NEC-5 rungs are raw (no Richardson pair); its lane is ~0.7 Ω below bs2 at
  n=45 in X, consistent with its documented walk, and its as-built−limit
  DIFFERENCE agrees with bs2 to 0.12 Ω — the walk cancels in the artifact.
