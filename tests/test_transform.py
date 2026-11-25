import numpy as np
import pytest
from antennaknobs import Transform, TransformStack
from antennaknobs.network import Wire


def test_hit():
    tr = Transform()
    coords = (1, 2, 3)
    assert coords == tr.hit(coords)


def test_translate():
    tr0 = Transform.translate(1, 1, 1)
    tr1 = Transform.translate(-1, -1, -1)
    print(tr0.A)
    print(tr1.A)

    assert np.allclose(tr0.premult(tr1).A, Transform().A)
    assert np.allclose(tr0.postmult(tr1).A, Transform().A)


def test_rotate():
    for rot in (Transform.rotX, Transform.rotY, Transform.rotZ):
        tr0 = rot(30)
        tr1 = rot(-30)
        tr2 = Transform.inverse(tr0)
        print(tr0.A)
        print(tr1.A)
        print(tr2.A)

        assert np.allclose(tr0.premult(tr1).A, Transform().A)
        assert np.allclose(tr0.postmult(tr1).A, Transform().A)

        assert np.allclose(tr1.A, tr2.A)


def test_stack():
    st = TransformStack()

    st.push(Transform.translate(1, 1, 1))
    st.push(Transform.translate(-1, -1, -1))

    coords = (1, 2, 3)
    assert coords == st.hit(coords)

    assert np.allclose(st.stack[-1].A, Transform().A)


def test_scale():
    assert Transform.scale(sx=-1).hit((1, 2, 3)) == (-1, 2, 3)
    assert Transform.scale(sy=-1).hit((1, 2, 3)) == (1, -2, 3)
    assert Transform.scale(sz=-1).hit((1, 2, 3)) == (1, 2, -3)
    assert Transform.scale(2, 3, 4).hit((1, 1, 1)) == (2, 3, 4)


def test_emit():
    st = TransformStack()
    st.push(Transform.translate(0, 0, 10))
    st.emit(((0, 0, 0), (1, 0, 0), 5, None))
    st.emit(Wire((0, 0, 0), (0, 1, 0), name="feed"))
    (a, b) = st.wires
    assert (a.p0, a.p1, a.n_seg) == ((0, 0, 10), (1, 0, 10), 5)
    assert (b.p0, b.p1, b.name) == ((0, 0, 10), (0, 1, 10), "feed")


def test_push_pop_tr():
    st = TransformStack()
    with st.push_pop_tr(Transform.scale(sx=-1)):
        assert st.hit((1, 2, 3)) == (-1, 2, 3)
    assert len(st.stack) == 1
    try:
        with st.push_pop_tr(Transform.translate(1, 0, 0)):
            raise RuntimeError
    except RuntimeError:
        pass
    assert len(st.stack) == 1


def test_path_shares_endpoints_and_closes():
    st = TransformStack()
    st.push(Transform.translate(0, 0, 5))
    pts = [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
    wires = st.path(pts, closed=True)
    assert wires == st.wires
    assert [(w.p0, w.p1) for w in wires] == [
        ((0, 0, 5), (1, 0, 5)),
        ((1, 0, 5), (1, 1, 5)),
        ((1, 1, 5), (0, 0, 5)),
    ]
    # Every joint is the same point twice, bit for bit.
    for a, b in zip(wires, wires[1:] + wires[:1], strict=True):
        assert a.p1 == b.p0


def test_path_feed_goes_on_every_segment_or_the_one_named():
    pts = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    every = TransformStack().path(pts, ex=1 + 0j)
    assert [w.ex for w in every] == [1 + 0j, 1 + 0j]
    one = TransformStack().path(pts, ex=1 + 0j, ex_segment=-1)
    assert [w.ex for w in one] == [None, 1 + 0j]
    with pytest.raises(ValueError):
        TransformStack().path(pts, ex=1 + 0j, ex_segment=2)
    with pytest.raises(ValueError):
        TransformStack().path(pts[:1])


def test_path_hands_other_wire_fields_to_every_segment():
    ws = TransformStack().path([(0, 0, 0), (1, 0, 0), (2, 0, 0)], n_seg=7, name="arm")
    assert [(w.n_seg, w.name) for w in ws] == [(7, "arm"), (7, "arm")]


def test_axis_wires_run_along_the_frames_own_axes():
    st = TransformStack()
    st.push(Transform.translate(1, 2, 3))
    with st.push_pop_tr(Transform.rotZ(90)):
        # In the rotated frame +X is the parent's +Y.
        w = st.wire_x(0, 5, ex=1 + 0j)
    assert np.allclose(w.p0, (1, 2, 3)) and np.allclose(w.p1, (1, 7, 3))
    assert w.ex == 1 + 0j
    assert st.wire_y(-1, 1, x=2)[:2] == ((3, 1, 3), (3, 3, 3))
    assert st.wire_z(0, 4, x=1, y=1)[:2] == ((2, 3, 3), (2, 3, 7))
    assert len(st.wires) == 3
