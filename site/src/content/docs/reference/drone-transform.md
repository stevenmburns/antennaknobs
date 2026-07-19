---
title: Drone & Transform API
description: The 3D turtle (Drone) and the homogeneous-transform helpers (Transform, TransformStack) for authoring antenna geometry as a flight path.
---

Most designs build their wire list from absolute corner coordinates. For
path-shaped antennas — loops, inverted-vee arms, rhombics, zig-zags — it's often
clearer to **describe the walk**: fly a leg, turn, fly the next, paying out wire
as you go. `Drone` is that 3D turtle; `Transform` / `TransformStack` are the
coordinate-frame helpers underneath it (and useful on their own for placing
elements). All three compile to the same edge list `build_wires` returns:

```python
((x0, y0, z0), (x1, y1, z1), nsegs, excitation)
```

so they're purely an alternate **authoring** style — nothing downstream changes.
See [Many ways to express geometry](/concepts/authoring/) for where this fits
among the other idioms.

## `Drone`

```python
from antennaknobs import Drone
```

A pen-carrying drone that carries a pose (position + orientation) and lays wire
as it flies.

**Body frame:** local **+x** is *forward* (the nose), **+z** is *up* (the yaw
axis), **+y** is *left* — a right-handed frame. Turns are **body-relative** (like
a turtle's left/right, generalized to 3D), so they're relative to the current
heading, not the world axes.

### Constructor

```python
Drone(position=(0.0, 0.0, 0.0), *, nominal_nsegs=21, ref=1.0)
```

- **`position`** — starting world position `(x, y, z)`.
- **`nominal_nsegs`** — the segment count a wire of length `ref` receives. Longer
  wires get proportionally more (see [auto-segmentation](#auto-segmentation)).
- **`ref`** — the reference length for that scaling, usually a quarter
  wavelength. Matches `AntennaBuilder`'s convention.

### Pen control

The pen is *up* (moving without wire) or *down* (laying wire). Each method
returns `self`, so calls chain.

| Method | Effect |
| --- | --- |
| `pay_out()` | Lower the pen — subsequent `forward()` lays **structural** wire. |
| `feed(excitation=1+0j)` | Lower the pen for the **driven** segment — wire laid carries the source `excitation`. |
| `cut()` | Raise the pen — subsequent `forward()` moves without wire. |

### Movement

| Method | Effect |
| --- | --- |
| `forward(dist, nsegs=None)` | Fly `dist` (m) along the nose; lays an edge if the pen is down. `nsegs` overrides the auto count. |
| `forward_to_plane(plane, nsegs=None)` | Fly along the nose **until the path meets `plane`** — a `forward()` whose distance is solved for, not given. Lays an edge if the pen is down. `plane` is a 4-tuple `(nx, ny, nz, d)`: the direction `(nx, ny, nz)` is the plane normal (normalized internally) and `d` is the signed distance from the origin along that unit normal, so the plane is `n̂·x == d` and `d` is a true distance regardless of the normal's length (`(0,0,1,5)` and `(0,0,2,5)` both mean `z = 5`). Raises if the normal is zero, the nose is parallel to the plane, or the plane is behind the nose; a no-op when already on it. |
| `jump(dist)` | Fly `dist` along the nose **without** wire (pen ignored). |
| `move_to(position)` | Relocate to `position`, keeping orientation; lays no wire. |
| `close(nsegs=None)` | Fly straight back to where the current pen-down stroke began, laying the closing edge (a loop's last side, or its feed gap). No-op if the pen is up or already home. |

### Turns (body-relative, **degrees**)

| Method | Axis |
| --- | --- |
| `yaw(deg)` | Turn left/right about local **+z** (up). |
| `pitch(deg)` | Nose up/down about local **+y** (left). |
| `roll(deg)` | Bank about local **+x** (the nose). |
| `face(heading, up=(0,0,1))` | Point the nose along `heading` with the given `up`, keeping position. `up` is orthogonalized against `heading` (they must not be parallel). Handy to start a planar figure: face an in-plane heading with the plane normal as `up`, then `yaw` turns stay in that plane. |

### Labelled nodes

For the one edge whose length you'd otherwise have to solve for (e.g. the top of
a triangle once you've flown to both corners), drop a pin and connect to it — no
trig:

| Method | Effect |
| --- | --- |
| `mark(label)` | Pin the current position under `label`. |
| `line_to(label, nsegs=None)` | Lay a wire from here to a previously `mark()`ed node (with the current pen), then move there — the drone works out the straight segment itself. |

### Reading state

| Member | Value |
| --- | --- |
| `position` *(property)* | Current world position `(x, y, z)`. |
| `heading` *(property)* | World-space unit vector the nose points along. |
| `wires()` | The accumulated edge list, in `build_wires` shape. |

### Auto-segmentation

When `forward()` / `close()` / `line_to()` aren't given an explicit `nsegs`, the
drone picks `max(1, round(nominal_nsegs · |length| / ref))` — the same formula
as `segs_for`, short moves included. It does **not**
force a parity — each solver wants a different one (odd for sinusoidal /
B-spline degree-2 / PyNEC, even for B-spline degree-1) so the feed lands
cleanly, and the engine coerces the fed wire's count to its own parity at solve
time; unfed wires keep their exact count.

### Example — a vertical delta loop

From `designs/loops/delta_loop_flyby.py`: a downward-pointing triangle in the
x = 0 plane, flown in full. `face()` starts the nose along the top edge with the
plane normal (+x) as "up", so every `yaw()` stays in-plane — no explicit trig.
`forward_through_plane` lays the whole top edge in one move, flying through the
symmetry plane `y = 0` to the mirror corner without computing its length.

```python
from antennaknobs import Drone

drone = Drone(position=S, nominal_nsegs=n_body, ref=quarter)
drone.face(heading=(0.0, 1.0, 0.0), up=(1.0, 0.0, 0.0))
drone.yaw(self.angle_deg)                # tilt up onto the right slant

drone.pay_out()
drone.forward(side, nsegs=n_body)                                # S -> A  (right slant)
drone.yaw(180 - self.angle_deg)                                  # exterior angle at A
drone.forward_through_plane((0.0, 1.0, 0.0, 0.0), nsegs=n_body)  # A -> B  (top edge)
drone.yaw(180 - self.angle_deg)                                  # exterior angle at B
drone.forward(side, nsegs=n_body)                                # B -> T  (left slant)
drone.feed(1 + 0j)
drone.close(nsegs=n_feed)                                        # T -> S  (feed gap, fly home)

return drone.wires()
```

Other idiomatic examples in the catalog: `horizontal_loop_drone.py` (a planar
square via four `yaw(90).forward(side)` legs), `delta_loop_reflected.py` (the
drone as a pure **point finder** — fly pen-up and read `.position`, then reflect
the rest), and `delta_loop_topdown.py` (start at the top centre and
`forward_to_plane` down a slant onto the feed plane `y = eps`, so the slant
length and feed height fall out of the intersection rather than being computed).

## `Transform`

```python
from antennaknobs import Transform
```

A 4×4 homogeneous transform (rotation + translation). All rotation factories take
**degrees**.

| Member | Returns / effect |
| --- | --- |
| `Transform(A=identity)` | Wrap a 4×4 matrix `A`. |
| `Transform.translate(x, y, z)` | Translation-only transform *(static)*. |
| `Transform.rotX(deg)` / `rotY(deg)` / `rotZ(deg)` | Rotation about a world axis, in degrees *(static)*. |
| `Transform.inverse(tr)` | The inverse of `tr` *(static)*. |
| `t.hit(coords)` | Apply `t` to a point `coords=(x, y, z)`; returns the transformed `(x, y, z)`. |
| `t.premult(other)` | Return `other @ t` (apply `t` first, then `other`). |
| `t.postmult(other)` | Return `t @ other` (apply `other` second). |

## `TransformStack`

```python
from antennaknobs import TransformStack
```

A stack of composed frames — push nested transforms to build up a coordinate
frame (e.g. place an array element within the array's frame), read points
through the top.

| Method | Effect |
| --- | --- |
| `TransformStack()` | New stack holding the identity frame. |
| `push(tr)` | Compose `tr` onto the current top frame and push it. |
| `pop()` | Remove the top frame. |
| `hit(v)` | Transform point `v` through the current top frame. |

### Example — stacked frames

From `designs/specialty/hentenna.py`: lift to the base height, tilt the whole
structure, then read local points through the composed frame.

```python
from antennaknobs import Transform, TransformStack

st = TransformStack()
st.push(Transform.translate(0, 0, b))     # to base height
st.push(Transform.rotX(-self.slant_deg))  # tilt the structure

def build_path(lst, ns, ex):
    return ((st.hit(a), st.hit(b), ns, ex) for a, b in zip(lst[:-1], lst[1:]))
```
