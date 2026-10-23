"""Compile indentation-based novel scenes into explicit, saveable instructions."""

import math
import re

from bne.errors import BNEError, Source
from bne.expressions import IDENTIFIER, expression
from bne.model import POSITIONS, TRANSITIONS, Instruction, SceneSpec, Script
from bne.syntax import Line, identifier, read_lines, string_literal, string_prefix, words

TARGET = IDENTIFIER + r"(?:\." + IDENTIFIER + r")?"


class SceneParser:
    def __init__(self, spec: SceneSpec):
        self.script = Script(spec)
        self.lines = read_lines(spec.path)
        self.index = 0

    def parse(self) -> Script:
        while self.index < len(self.lines):
            line = self.lines[self.index]
            match = re.fullmatch(r"label (" + IDENTIFIER + r"):", line.text)
            if line.indent != 0 or not match:
                raise BNEError("На верхнем уровне сцены ожидается label имя:", line.source)
            name = identifier(match.group(1), line.source)
            if name in self.script.labels:
                raise BNEError(f"Повторная метка «{name}».", line.source)
            self.script.labels[name] = len(self.script.code)
            self.index += 1
            self._body(4, line)
        if self.script.spec.entry not in self.script.labels:
            raise BNEError(
                f"В сцене нет входной метки «{self.script.spec.entry}».",
                Source(self.script.spec.path),
            )
        return self.script

    def _emit(self, op: str, args: dict, source: Source) -> int:
        self.script.code.append(Instruction(op, args, source))
        return len(self.script.code) - 1

    def _body(self, indent: int, parent: Line) -> None:
        if self.index >= len(self.lines) or self.lines[self.index].indent < indent:
            raise BNEError("Блок не может быть пустым; используйте pass.", parent.source)
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if line.indent < indent:
                break
            if line.indent != indent:
                raise BNEError("Неожиданный отступ.", line.source)
            if line.text.startswith("if "):
                self._conditional(indent)
            elif line.text == "menu:":
                self._menu(indent)
            else:
                self.index += 1
                self._statement(line)

    def _conditional(self, indent: int) -> None:
        exits = []
        first = True
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if line.indent != indent:
                break
            is_else = line.text == "else:"
            prefix = "if " if first else "elif "
            if not is_else and not line.text.startswith(prefix):
                break
            if not line.text.endswith(":"):
                raise BNEError("После условия нужен символ :", line.source)
            condition = None if is_else else expression(line.text[len(prefix) : -1], line.source)
            branch = None
            if condition is not None:
                branch = self._emit("branch", {"condition": condition, "target": 0}, line.source)
            self.index += 1
            self._body(indent + 4, line)
            exits.append(self._emit("goto", {"target": 0}, line.source))
            if branch is not None:
                self.script.code[branch].args["target"] = len(self.script.code)
            first = False
            if is_else:
                break
        end = len(self.script.code)
        for exit_index in exits:
            self.script.code[exit_index].args["target"] = end

    def _menu(self, indent: int) -> None:
        line = self.lines[self.index]
        self.index += 1
        choices = []
        menu = self._emit("menu", {"choices": choices}, line.source)
        exits = []
        while self.index < len(self.lines):
            option = self.lines[self.index]
            if option.indent <= indent:
                break
            if option.indent != indent + 4 or not option.text.endswith(":"):
                raise BNEError('Ожидается вариант меню: "Текст":', option.source)
            text, suffix = string_prefix(option.text[:-1].strip(), option.source)
            condition = None
            if suffix:
                if not suffix.startswith("if "):
                    raise BNEError('После "варианта" допустимо только if условие:', option.source)
                condition = expression(suffix[3:], option.source)
            choices.append(
                {
                    "text": text,
                    "condition": condition,
                    "target": len(self.script.code),
                    "source": option.source,
                }
            )
            self.index += 1
            self._body(indent + 8, option)
            exits.append(self._emit("goto", {"target": 0}, option.source))
        if not choices:
            raise BNEError("В menu нужен хотя бы один вариант.", self.script.code[menu].source)
        if len(choices) > 9:
            raise BNEError("В одном menu допускается не больше 9 вариантов.", line.source)
        for exit_index in exits:
            self.script.code[exit_index].args["target"] = len(self.script.code)

    def _statement(self, line: Line) -> None:
        text, source = line.text, line.source
        for op in ("jump", "call"):
            if text.startswith(op + " "):
                target = text[len(op) + 1 :].strip()
                if not re.fullmatch(TARGET, target):
                    raise BNEError("Ожидается имя сцены, метки или сцена.метка.", source)
                self._emit(op, {"target": target}, source)
                return
        if text in ("return", "end", "pass"):
            self._emit("nop" if text == "pass" else text, {}, source)
            return
        if text.startswith("$"):
            match = re.fullmatch(
                r"\$\s*(" + IDENTIFIER + r")\s*(//=|\+=|-=|\*=|/=|%=|=)\s*(.+)", text
            )
            if not match:
                raise BNEError("Используйте $ переменная = выражение (или +=, -=, ...).", source)
            self._emit(
                "assign",
                {
                    "name": identifier(match.group(1), source),
                    "operator": match.group(2),
                    "value": expression(match.group(3), source),
                },
                source,
            )
            return
        if text == "pause" or text.startswith("pause "):
            seconds = None if text == "pause" else _number(text[6:], source, 0, 86400)
            self._emit("pause", {"seconds": seconds}, source)
            return
        if text in ("window show", "window hide"):
            self._emit("window", {"visible": text == "window show"}, source)
            return
        if text.startswith("with "):
            transition = text[5:].strip()
            if transition not in TRANSITIONS:
                raise BNEError("Переходы: fade, dissolve, none.", source)
            self._emit("transition", {"transition": transition}, source)
            return
        if text.split()[0] in ("scene", "show", "hide"):
            self._visual(line)
            return
        if text.split()[0] in ("play", "stop"):
            self._audio(line)
            return
        if text.startswith(('"', "'")):
            self._emit("say", {"speaker": None, "text": string_literal(text, source)}, source)
            return
        match = re.fullmatch(r"(" + IDENTIFIER + r")\s+(.+)", text)
        if match and match.group(2).startswith(('"', "'")):
            self._emit(
                "say",
                {"speaker": match.group(1), "text": string_literal(match.group(2), source)},
                source,
            )
            return
        raise BNEError(f"Неизвестная команда: {text}", source)

    def _visual(self, line: Line) -> None:
        parts = words(line.text, line.source)
        op, tokens = parts[0], parts[1:]
        transition = "none"
        position = None
        if "with" in tokens:
            index = tokens.index("with")
            if index != len(tokens) - 2 or tokens[-1] not in TRANSITIONS:
                raise BNEError(
                    "В конце команды ожидается with fade / dissolve / none.", line.source
                )
            transition = tokens[-1]
            tokens = tokens[:index]
        if "at" in tokens:
            index = tokens.index("at")
            if op != "show" or index != len(tokens) - 2 or tokens[-1] not in POSITIONS:
                raise BNEError("Для show доступны at left / center / right.", line.source)
            position = tokens[-1]
            tokens = tokens[:index]
        if not tokens or any(not re.fullmatch(IDENTIFIER, token) for token in tokens):
            raise BNEError("Укажите имя ресурса из image в manager.bne.", line.source)
        if op == "hide" and len(tokens) != 1:
            raise BNEError("hide принимает тег: hide mira (без имени эмоции).", line.source)
        self._emit(
            op,
            {"image": " ".join(tokens), "position": position, "transition": transition},
            line.source,
        )

    def _audio(self, line: Line) -> None:
        parts = words(line.text, line.source)
        if len(parts) < 2 or parts[1] not in ("music", "sound"):
            raise BNEError("Аудиоканалы: music и sound.", line.source)
        op, channel = parts[:2]
        if op == "stop":
            fade = 0.0
            if len(parts) > 2:
                if len(parts) != 4 or parts[2] != "fadeout":
                    raise BNEError("Синтаксис: stop music [fadeout секунды].", line.source)
                fade = _number(parts[3], line.source, 0, 30)
            self._emit("stop", {"channel": channel, "fade": fade}, line.source)
            return
        if len(parts) < 3:
            raise BNEError('Синтаксис: play music "audio/file.wav"', line.source)
        args = {
            "channel": channel,
            "path": parts[2],
            "loop": channel == "music",
            "fade": 0.0,
            "volume": None,
        }
        index = 3
        seen = set()
        while index < len(parts):
            token = parts[index]
            key = "loop" if token in ("loop", "noloop") else token
            if key in seen:
                raise BNEError(f"Повторный параметр аудио: {key}", line.source)
            seen.add(key)
            if token in ("loop", "noloop") and channel == "music":
                args["loop"] = token == "loop"
                index += 1
            elif token in ("fadein", "volume") and index + 1 < len(parts):
                args["fade" if token == "fadein" else "volume"] = _number(
                    parts[index + 1], line.source, 0, 30 if token == "fadein" else 1
                )
                index += 2
            else:
                raise BNEError(f"Неизвестный параметр аудио: {token}", line.source)
        self._emit("play", args, line.source)


def _number(text: str, source: Source, low: float, high: float) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise BNEError("Ожидается число.", source) from error
    if not math.isfinite(value) or not low <= value <= high:
        raise BNEError(f"Число должно быть от {low:g} до {high:g}.", source)
    return value


def parse_scene(spec: SceneSpec) -> Script:
    return SceneParser(spec).parse()
