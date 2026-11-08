import os
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "wordfreq.py"


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", env=env)


def write(tmp_path, text):
    p = tmp_path / "in.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_counts_and_order(tmp_path):
    r = run(write(tmp_path, "the cat and the hat. The end!"))
    assert r.returncode == 0
    assert r.stdout.splitlines() == ["the 3", "and 1", "cat 1", "end 1", "hat 1"]


def test_top_n(tmp_path):
    assert run(write(tmp_path, "b b b a a c"), "-n", 2).stdout.splitlines() == ["b 3", "a 2"]


def test_apostrophes(tmp_path):
    out = run(write(tmp_path, "Don't 'quote' don't rock'n'roll ''")).stdout.splitlines()
    assert out == ["don't 2", "quote 1", "rock'n'roll 1"]


def test_unicode_letters(tmp_path):
    out = run(write(tmp_path, "Caf\u00e9 caf\u00e9 na\u00efve 123 4x")).stdout.splitlines()
    assert out == ["caf\u00e9 2", "na\u00efve 1", "x 1"]


def test_min_len(tmp_path):
    assert run(write(tmp_path, "a an ant ants a an"), "--min-len", 3).stdout.splitlines() == ["ant 1", "ants 1"]


def test_missing_file(tmp_path):
    r = run(tmp_path / "nope.txt")
    assert r.returncode == 1 and "error: cannot read" in r.stderr


def test_bad_n(tmp_path):
    assert run(write(tmp_path, "x"), "-n", 0).returncode == 2
