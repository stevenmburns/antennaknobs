import numpy as np
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
