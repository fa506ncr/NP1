"""Line and literal helpers for both .bne entry points and scene files."""

import ast
import keyword
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from bne.errors import BNEError, Source
from bne.expressions import IDENTIFIER, MAX_STRING

STRING_PATTERN = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""
STRING_PREFIX = re.compile("^(" + STRING_PATTERN + ")")


@dataclass(frozen=True)
class Line:
    indent: int
    text: str
    source: Source


def read_lines(path: Path) -> list[Line]:
    try:
        if path.stat().st_size > 2_000_000:
            raise BNEError("Файл .bne слишком большой (максимум 2 МБ).", Source(path))
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise BNEError(f"Не удалось прочитать UTF-8 сценарий: {error}", Source(path)) from error
    result = []
    for number, raw in enumerate(text.splitlines(), 1):
        source = Source(path, number)
        leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
        clean = _strip_comment(raw).rstrip()
        if not clean.strip():
            continue
        if "\t" in leading:
            raise BNEError("Для отступов используйте пробелы, а не табуляцию.", source)
        indent = len(leading)
        if indent % 4:
            raise BNEError("Отступ должен быть кратен четырём пробелам.", source)
        if indent > 128:
            raise BNEError("Слишком глубокая вложенность блоков (максимум 32).", source)
        result.append(Line(indent, clean.strip(), source))
    return result


def _strip_comment(text: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\" and quote:
            escaped = True
        elif quote and char == quote:
            quote = ""
        elif not quote and char in ("'", '"'):
            quote = char
        elif not quote and char == "#":
            return text[:index]
    return text


def string_literal(text: str, source: Source) -> str:
    try:
        node = ast.parse(text.strip(), mode="eval").body
    except (SyntaxError, ValueError, RecursionError) as error:
        raise BNEError("Ожидается строка в кавычках на одной строке.", source) from error
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise BNEError("Ожидается строка в кавычках.", source)
    if len(node.value) > MAX_STRING:
        raise BNEError("Строка слишком длинная.", source)
    return node.value


def string_prefix(text: str, source: Source) -> tuple[str, str]:
    match = STRING_PREFIX.match(text)
    if not match:
        raise BNEError("Ожидается строка в кавычках.", source)
    return string_literal(match.group(), source), text[match.end() :].strip()


def words(text: str, source: Source) -> list[str]:
    try:
        return shlex.split(text, comments=False)
    except ValueError as error:
        raise BNEError(f"Неверные кавычки: {error}", source) from error


def identifier(name: str, source: Source) -> str:
    if not re.fullmatch(IDENTIFIER, name) or keyword.iskeyword(name):
        raise BNEError(f"Недопустимое имя «{name}»: используйте латиницу, цифры и _.", source)
    return name
