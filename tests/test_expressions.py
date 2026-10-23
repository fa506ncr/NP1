from pathlib import Path

import pytest

from bne.errors import BNEError, Source
from bne.expressions import expression, interpolate, interpolation_names

SOURCE = Source(Path("test.bne"), 7)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 + 3 * 4", 14),
        ("(5 - 1) // 2", 2),
        ("7 % 3", 1),
        ("5 / 2", 2.5),
        ("-3 + +2", -1),
        ('"Привет, " + name', "Привет, Ева"),
        ('"a" * 3', "aaa"),
        ("not flag and score >= 2", True),
        ("1 < score <= 3", True),
        ("True or 1 / 0", True),
        ("False and 1 / 0", False),
        ("None == None", True),
        ("score != 0", True),
        ("score == 0 or flag", False),
    ],
)
def test_expressions(text, expected):
    assert expression(text, SOURCE).evaluate({"name": "Ева", "score": 2, "flag": False}) == expected


@pytest.mark.parametrize(
    "text",
    [
        '__import__("os").system("echo unsafe")',
        "name.upper()",
        "name[0]",
        "[1, 2]",
        "{1: 2}",
        "(1, 2)",
        "lambda: 1",
        "2 ** 1000",
        'f"{score}"',
        "True if flag else False",
        "[x for x in name]",
        "__builtins__",
        "1e999",
        "b'bytes'",
        "1j",
        "score is None",
    ],
)
def test_python_is_not_executable(text):
    with pytest.raises(BNEError):
        expression(text, SOURCE)


@pytest.mark.parametrize(
    "text",
    [
        '"x" * 1000000000000',
        '"%999999999s" % "x"',
        "1 / 0",
        '"x" - 1',
        "99999999999999999999999999999999999999999999999",
    ],
)
def test_arithmetic_is_bounded(text):
    with pytest.raises(BNEError) as error:
        expression(text, SOURCE).evaluate({})
    assert "test.bne:7" in str(error.value)


def test_missing_variable_and_invalid_expression():
    with pytest.raises(BNEError, match="Неизвестная переменная"):
        expression("unknown", SOURCE).evaluate({})
    with pytest.raises(BNEError, match="Некорректное выражение"):
        expression("1 +", SOURCE)


def test_interpolation_and_escaping():
    assert (
        interpolate("[name]: [score]. [[name]]", {"name": "Ева", "score": 3}, SOURCE)
        == "Ева: 3. [name]"
    )
    assert interpolation_names("[[literal]] [name] [score]") == {"name", "score"}
    with pytest.raises(BNEError, match="Неизвестная переменная"):
        interpolate("[missing]", {}, SOURCE)


def test_complexity_limit():
    with pytest.raises(BNEError, match="сложное"):
        expression(" + ".join("1" for _ in range(100)), SOURCE)


def test_interpolation_expansion_is_bounded():
    assert len(interpolate("[name]", {"name": "x" * 16000}, SOURCE)) == 16000
    with pytest.raises(BNEError, match="подстановки"):
        interpolate("[name][name]", {"name": "x" * 16000}, SOURCE)
