# Word frequency command-line tool

Write `wordfreq.py`, run as `python wordfreq.py FILE [-n N] [--min-len K]`.

- It reads FILE as UTF-8. A word is a run of letters (any Unicode letter) and apostrophes, compared in lower case.
  Apostrophes at the start or end of a word are removed; a word left empty is ignored. Digits and underscores are not
  part of words.
- It prints the N most frequent words (default 10), one per line as `word count` with a single space, most frequent
  first; ties are broken alphabetically.
- `--min-len K` ignores words shorter than K characters (after the outer apostrophes are removed). The default is 1.
- A file that cannot be read prints `error: cannot read FILE` to stderr and exits with status 1.
- N must be a positive integer; anything else is an argparse usage error (exit status 2).

Run `python -m pytest -q` in this folder to check your work, and keep going until every test passes. Do not change anything under `tests/`. Use only the Python standard library.
