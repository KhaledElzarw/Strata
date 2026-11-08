from jsondiff import diff


def test_equal():
    assert diff({"a": [1, {"b": None}]}, {"a": [1, {"b": None}]}) == []


def test_scalar_change():
    assert diff(1, 2) == ["~ $: 1 -> 2"]


def test_dict_add_remove_change():
    assert diff({"a": 1, "b": 2}, {"b": 3, "c": 4}) == ["+ $.c: 4", "- $.a: 1", "~ $.b: 2 -> 3"]


def test_nested():
    assert diff({"x": {"y": {"z": 1}}}, {"x": {"y": {"z": 2}}}) == ["~ $.x.y.z: 1 -> 2"]


def test_lists():
    assert diff([1, 2, 3], [1, 5]) == ["- $[2]: 3", "~ $[1]: 2 -> 5"]
    assert diff([1], [1, [2]]) == ["+ $[1]: [2]"]


def test_type_change():
    assert diff({"a": 1}, {"a": "1"}) == ['~ $.a: 1 -> "1"']
    assert diff({"a": 1}, {"a": True}) == ["~ $.a: 1 -> true"]
    assert diff({"a": 1}, {"a": 1.0}) == ["~ $.a: 1 -> 1.0"]
    assert diff({"a": [1]}, {"a": {"0": 1}}) == ['~ $.a: [1] -> {"0": 1}']


def test_values_rendered_with_sorted_keys():
    assert diff({}, {"k": {"b": 1, "a": 2}}) == ['+ $.k: {"a": 2, "b": 1}']


def test_list_of_dicts():
    assert diff([{"id": 1, "v": "a"}], [{"id": 1, "v": "b"}]) == ['~ $[0].v: "a" -> "b"']
