# Structural JSON diff

Implement `diff(a, b)` in `jsondiff.py`. `a` and `b` are JSON-like values (dict, list, str, int, float, bool, None).
It returns a sorted list of strings describing how to get from `a` to `b`:

- `+ PATH: VALUE` for something only in `b`, `- PATH: VALUE` for something only in `a`, and `~ PATH: OLD -> NEW` for a
  changed value.
- Dicts are compared key by key and lists index by index; extra list items at the end are `+` or `-` entries. The
  diff goes inside a dict or list only when both sides at that path are the same kind of container. Any other
  difference is a `~`, and two values are equal only when they have the same type and compare equal (so `1`, `1.0`,
  `True` and `"1"` all differ from each other).
- PATH starts with `$`; a dict key adds `.key` and a list index adds `[i]`. Values are written with
  `json.dumps(value, sort_keys=True)`.
- Equal inputs give `[]`.

Run `python -m pytest -q` in this folder to check your work, and keep going until every test passes. Do not change anything under `tests/`. Use only the Python standard library.
