import pytest

from intervals import covered, gaps, insert, merge


def test_merge_overlapping():
    assert merge([(1, 4), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]


def test_merge_touching():
    assert merge([(1, 3), (3, 5)]) == [(1, 5)]


def test_merge_unsorted():
    assert merge([(5, 7), (1, 2), (2, 3)]) == [(1, 3), (5, 7)]


def test_merge_contained():
    assert merge([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]


def test_merge_drops_empty():
    assert merge([(1, 1), (2, 3), (4, 4)]) == [(2, 3)]


def test_merge_empty_input():
    assert merge([]) == []


def test_merge_returns_tuples():
    assert merge([[1, 2]]) == [(1, 2)]


def test_merge_invalid():
    with pytest.raises(ValueError):
        merge([(3, 1)])


def test_merge_does_not_mutate():
    src = [(2, 3), (1, 2)]
    merge(src)
    assert src == [(2, 3), (1, 2)]


def test_insert():
    assert insert([(1, 2), (5, 6)], (2, 5)) == [(1, 6)]


def test_insert_separate():
    assert insert([(1, 2)], (4, 5)) == [(1, 2), (4, 5)]


def test_covered():
    assert covered([(1, 4), (2, 6), (10, 11)]) == 6


def test_covered_floats():
    assert covered([(0.5, 1.5), (1.0, 2.0)]) == pytest.approx(1.5)


def test_gaps():
    assert gaps([(2, 3), (5, 7)], 0, 10) == [(0, 2), (3, 5), (7, 10)]


def test_gaps_clipped():
    assert gaps([(-5, 2), (8, 20)], 0, 10) == [(2, 8)]


def test_gaps_none():
    assert gaps([(0, 10)], 0, 10) == []
