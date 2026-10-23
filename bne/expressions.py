"""A deliberately small expression language: no eval, exec, calls or attributes."""

import ast
import math
import operator
import re
from dataclasses import dataclass
from typing import Any

from bne.errors import BNEError, Source
from bne.model import Scalar

MAX_STRING = 16_000
MAX_INT_BITS = 128
IDENTIFIER = r"[A-Za-z][A-Za-z0-9_]*"
INTERPOLATION = re.compile(r"\[\[|\]\]|\[(" + IDENTIFIER + r")\]")
BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.And,
    ast.Or,
    ast.Not,
    ast.UAdd,
    ast.USub,
    *BINARY,
    *COMPARE,
)


def scalar(value: Any, source: Source | None = None) -> Scalar:
    if type(value) not in (str, int, float, bool, type(None)):
        raise BNEError("Допустимы только строки, числа, True, False и None.", source)
    if isinstance(value, str) and len(value) > MAX_STRING:
        raise BNEError("Строка слишком длинная.", source)
    if type(value) is int and value.bit_length() > MAX_INT_BITS:
        raise BNEError("Слишком большое целое число.", source)
    if type(value) is float and not math.isfinite(value):
        raise BNEError("Число должно быть конечным.", source)
    return value


@dataclass(frozen=True)
class Expression:
    text: str
    tree: ast.Expression
    source: Source

    @property
    def names(self) -> set[str]:
        return {node.id for node in ast.walk(self.tree) if isinstance(node, ast.Name)}

    def evaluate(self, variables: dict[str, Scalar]) -> Scalar:
        try:
            return scalar(_visit(self.tree.body, variables, self.source), self.source)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
            raise BNEError(f"Ошибка выражения «{self.text}»: {error}", self.source) from error


def expression(text: str, source: Source) -> Expression:
    if len(text) > 2048:
        raise BNEError("Выражение слишком длинное.", source)
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise BNEError(f"Некорректное выражение: {text}", source) from error
    nodes = list(ast.walk(tree))
    if len(nodes) > 128:
        raise BNEError("Выражение слишком сложное.", source)
    for node in nodes:
        if not isinstance(node, ALLOWED_NODES):
            raise BNEError(
                "В .bne нельзя вызывать Python, функции или обращаться к атрибутам.", source
            )
        if isinstance(node, ast.Constant):
            scalar(node.value, source)
        if isinstance(node, ast.Name) and not re.fullmatch(IDENTIFIER, node.id):
            raise BNEError(f"Недопустимое имя переменной: {node.id}", source)
    return Expression(text, tree, source)


def binary(op: type[ast.operator], left: Scalar, right: Scalar, source: Source) -> Scalar:
    if op is ast.Mult:
        if isinstance(left, str) and isinstance(right, int):
            if len(left) * max(0, right) > MAX_STRING:
                raise BNEError("Результат умножения строки слишком длинный.", source)
        if isinstance(right, str) and isinstance(left, int):
            if len(right) * max(0, left) > MAX_STRING:
                raise BNEError("Результат умножения строки слишком длинный.", source)
    if op is ast.Mod and (isinstance(left, str) or isinstance(right, str)):
        raise BNEError("Оператор % поддерживает только числа.", source)
    try:
        return scalar(BINARY[op](left, right), source)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise BNEError(f"Ошибка арифметики: {error}", source) from error


def _visit(node: ast.AST, variables: dict[str, Scalar], source: Source) -> Scalar:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise BNEError(f"Неизвестная переменная «{node.id}». Объявите default.", source)
        return variables[node.id]
    if isinstance(node, ast.BinOp):
        return binary(
            type(node.op),
            _visit(node.left, variables, source),
            _visit(node.right, variables, source),
            source,
        )
    if isinstance(node, ast.UnaryOp):
        operand = _visit(node.operand, variables, source)
        if isinstance(node.op, ast.Not):
            return not operand
        return scalar(+operand if isinstance(node.op, ast.UAdd) else -operand, source)
    if isinstance(node, ast.BoolOp):
        result: Scalar = None
        for child in node.values:
            result = _visit(child, variables, source)
            if isinstance(node.op, ast.And) and not result:
                return result
            if isinstance(node.op, ast.Or) and result:
                return result
        return result
    if isinstance(node, ast.Compare):
        left = _visit(node.left, variables, source)
        for op, right_node in zip(node.ops, node.comparators, strict=True):
            right = _visit(right_node, variables, source)
            if not COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    raise BNEError("Неподдерживаемое выражение.", source)


def interpolation_names(text: str) -> set[str]:
    return {match.group(1) for match in INTERPOLATION.finditer(text) if match.group(1)}


def interpolate(text: str, variables: dict[str, Scalar], source: Source) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group() == "[[":
            return "["
        if match.group() == "]]":
            return "]"
        name = match.group(1)
        if name not in variables:
            raise BNEError(f"Неизвестная переменная в тексте: {name}", source)
        return str(variables[name])

    parts = []
    offset = total = 0
    for match in INTERPOLATION.finditer(text):
        piece = text[offset : match.start()] + replace(match)
        total += len(piece)
        if total > MAX_STRING:
            raise BNEError("Текст после подстановки переменных слишком длинный.", source)
        parts.append(piece)
        offset = match.end()
    tail = text[offset:]
    if total + len(tail) > MAX_STRING:
        raise BNEError("Текст после подстановки переменных слишком длинный.", source)
    return "".join(parts) + tail
