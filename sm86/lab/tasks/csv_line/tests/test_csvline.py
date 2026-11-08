import pytest

from csvline import parse_line


def test_simple():
    assert parse_line("a,b,c") == ["a", "b", "c"]


def test_empty_fields():
    assert parse_line("a,,b") == ["a", "", "b"]


def test_trailing_sep():
    assert parse_line("a,b,") == ["a", "b", ""]


def test_empty_line():
    assert parse_line("") == [""]


def test_quoted_sep():
    assert parse_line('"a,b",c') == ["a,b", "c"]


def test_escaped_quote():
    assert parse_line('"say ""hi""",x') == ['say "hi"', "x"]


def test_whitespace_kept():
    assert parse_line(" a , b ") == [" a ", " b "]


def test_quoted_whitespace():
    assert parse_line('"  x  ",y') == ["  x  ", "y"]


def test_unterminated_quote():
    with pytest.raises(ValueError):
        parse_line('"abc,d')


def test_custom_sep():
    assert parse_line('a;"b;c";d', sep=";") == ["a", "b;c", "d"]


def test_only_quotes():
    assert parse_line('""') == [""]


def test_quoted_empty_between():
    assert parse_line('a,"",b') == ["a", "", "b"]
