"""Load manager.bne, compile its scenes and validate references before opening a window."""

import ast
import hashlib
import re
from dataclasses import replace
from pathlib import Path

from bne.errors import BNEError, Source
from bne.expressions import IDENTIFIER, Expression, expression, interpolation_names
from bne.model import Character, Config, Project, Scalar, SceneSpec
from bne.parser import TARGET, parse_scene
from bne.paths import game_file
from bne.syntax import identifier, read_lines, string_literal, words


class ProjectLoader:
    def __init__(self, path: Path):
        path = path.expanduser().resolve()
        self.manager = path / "manager.bne" if path.is_dir() else path
        self.root = self.manager.parent
        self.config = Config()
        self.characters: dict[str, Character] = {}
        self.images: dict[str, Path] = {}
        self.defaults: dict[str, Scalar] = {}
        self.specs: dict[str, SceneSpec] = {}
        self.start: str | None = None
        self.start_source = Source(self.manager)
        self.config_keys: set[str] = set()

    def load(self) -> Project:
        for line in read_lines(self.manager):
            if line.indent:
                raise BNEError("Объявления manager.bne пишутся без отступов.", line.source)
            self._declaration(line.text, line.source)
        if not self.specs:
            raise BNEError(
                'Объявите хотя бы одну сцену: scene intro = "scene/scene1.bne"',
                Source(self.manager),
            )
        if self.start is None:
            raise BNEError("Укажите стартовую сцену: start intro", Source(self.manager))
        if self.config.font:
            game_file(self.root, self.config.font, Source(self.manager))
        scripts = {}
        for name, spec in self.specs.items():
            if spec.mode != "novel":
                raise BNEError(
                    "Режим rpg зарезервирован, но ходьба ещё не реализована. "
                    "В версии 0.1 используйте mode novel.",
                    spec.source,
                )
            scripts[name] = parse_scene(spec)
        digest = hashlib.sha256()
        for path in [self.manager, *(spec.path for spec in self.specs.values())]:
            digest.update(path.relative_to(self.root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        project = Project(
            self.root,
            self.manager,
            self.config,
            self.characters,
            self.images,
            self.defaults,
            scripts,
            ("", 0),
            digest.hexdigest(),
        )
        project.start = project.target(self.start, source=self.start_source)
        self._validate(project)
        return project

    def _declaration(self, text: str, source: Source) -> None:
        match = re.fullmatch(r"define config\.(" + IDENTIFIER + r")\s*=\s*(.+)", text)
        if match:
            self._config(match.group(1), match.group(2), source)
            return
        match = re.fullmatch(r"define (" + IDENTIFIER + r")\s*=\s*(.+)", text)
        if match:
            name = identifier(match.group(1), source)
            if name in self.characters:
                raise BNEError(f"Персонаж «{name}» уже объявлен.", source)
            if name in {
                "jump",
                "call",
                "scene",
                "show",
                "hide",
                "with",
                "play",
                "stop",
                "pause",
                "window",
                "menu",
                "label",
                "end",
            }:
                raise BNEError(f"Имя персонажа «{name}» совпадает с командой движка.", source)
            self.characters[name] = self._character(match.group(2), source)
            return
        match = re.fullmatch(r"default (" + IDENTIFIER + r")\s*=\s*(.+)", text)
        if match:
            name = identifier(match.group(1), source)
            if name in self.defaults:
                raise BNEError(f"Переменная «{name}» уже объявлена.", source)
            self.defaults[name] = expression(match.group(2), source).evaluate(self.defaults)
            return
        match = re.fullmatch(r"image (.+?)\s*=\s*(.+)", text)
        if match:
            name = " ".join(match.group(1).split())
            if not name or not all(
                re.fullmatch(IDENTIFIER, token) and token not in ("at", "with")
                for token in name.split()
            ):
                raise BNEError("Имя image — одно или несколько имён через пробел.", source)
            if name in self.images:
                raise BNEError(f"Изображение «{name}» уже объявлено.", source)
            self.images[name] = game_file(self.root, string_literal(match.group(2), source), source)
            return
        if text.startswith("scene "):
            self._scene(text, source)
            return
        if text.startswith("start "):
            if self.start is not None:
                raise BNEError("start можно указать только один раз.", source)
            self.start = text[6:].strip()
            self.start_source = source
            if not re.fullmatch(TARGET, self.start):
                raise BNEError("После start укажите сцену или сцена.метка.", source)
            return
        raise BNEError(f"Неизвестное объявление manager.bne: {text}", source)

    def _scene(self, text: str, source: Source) -> None:
        match = re.fullmatch(r"scene (" + IDENTIFIER + r")\s*=\s*(.+)", text)
        if not match:
            raise BNEError(
                'Синтаксис: scene имя = "scene/file.bne" [mode novel] [entry start]', source
            )
        tokens = words(match.group(2), source)
        if not tokens:
            raise BNEError("Укажите файл сцены.", source)
        name, path = identifier(match.group(1), source), tokens[0]
        if name in self.specs:
            raise BNEError(f"Сцена «{name}» уже объявлена.", source)
        if not path.endswith(".bne"):
            raise BNEError("Сценарии должны иметь расширение .bne.", source)
        options = {"mode": "novel", "entry": "start"}
        seen = set()
        remaining = tokens[1:]
        if len(remaining) % 2:
            raise BNEError("Ожидается пара mode novel или entry имя_метки.", source)
        for key, value in zip(remaining[::2], remaining[1::2], strict=True):
            if key not in options or key in seen or not re.fullmatch(IDENTIFIER, value):
                raise BNEError(f"Неизвестный или повторный параметр сцены: {key}", source)
            options[key] = identifier(value, source)
            seen.add(key)
        if options["mode"] not in ("novel", "rpg"):
            raise BNEError("Режим сцены: novel (rpg зарезервирован).", source)
        self.specs[name] = SceneSpec(
            name, game_file(self.root, path, source), source, options["mode"], options["entry"]
        )

    def _config(self, key: str, value_text: str, source: Source) -> None:
        if key not in Config.__dataclass_fields__:
            raise BNEError(f"Неизвестная настройка config.{key}.", source)
        if key in self.config_keys:
            raise BNEError(f"Настройка config.{key} уже задана.", source)
        value = expression(value_text, source).evaluate({})
        if key == "title" and (not isinstance(value, str) or not 1 <= len(value) <= 120):
            raise BNEError("config.title — непустая строка до 120 символов.", source)
        if key in ("width", "height"):
            bounds = (640, 3840) if key == "width" else (360, 2160)
            if type(value) is not int or not bounds[0] <= value <= bounds[1]:
                raise BNEError(f"config.{key} — целое от {bounds[0]} до {bounds[1]}.", source)
        if key in ("text_speed", "music_volume"):
            maximum = 200 if key == "text_speed" else 1
            if type(value) not in (int, float) or not 0 <= value <= maximum:
                raise BNEError(f"config.{key} — число от 0 до {maximum}.", source)
        if key == "font" and (not isinstance(value, str) or not value):
            raise BNEError("config.font — относительный путь к TTF/OTF шрифту.", source)
        self.config = replace(self.config, **{key: value})
        self.config_keys.add(key)

    @staticmethod
    def _character(text: str, source: Source) -> Character:
        try:
            node = ast.parse(text, mode="eval").body
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Name)
                or node.func.id != "Character"
                or len(node.args) != 1
            ):
                raise ValueError
            name_node = node.args[0]
            if not isinstance(name_node, ast.Constant) or type(name_node.value) not in (
                str,
                type(None),
            ):
                raise ValueError
            name = name_node.value
            color = "#B8D9E8"
            if len(node.keywords) > 1:
                raise ValueError
            for keyword in node.keywords:
                if (
                    keyword.arg != "color"
                    or not isinstance(keyword.value, ast.Constant)
                    or not isinstance(keyword.value.value, str)
                ):
                    raise ValueError
                color = keyword.value.value
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) or (name and len(name) > 100):
                raise ValueError
            return Character(name, color)
        except (SyntaxError, ValueError, RecursionError) as error:
            raise BNEError(
                'Используйте Character("Имя", color="#AABBCC") или Character(None).', source
            ) from error

    def _validate(self, project: Project) -> None:
        names = set(project.defaults)
        tags = {image.split()[0] for image in project.images}

        def check_expression(value: Expression) -> None:
            unknown = value.names - names
            if unknown:
                raise BNEError(
                    f"Неизвестные переменные: {', '.join(sorted(unknown))}. "
                    "Объявите их через default в manager.bne.",
                    value.source,
                )

        def check_text(text: str, source: Source) -> None:
            unknown = interpolation_names(text) - names
            if unknown:
                raise BNEError(
                    f"Неизвестные переменные в тексте: {', '.join(sorted(unknown))}", source
                )

        for character in project.characters.values():
            if character.name is not None:
                check_text(character.name, Source(project.manager))

        for scene, script in project.scripts.items():
            for instruction in script.code:
                op, args, source = instruction.op, instruction.args, instruction.source
                if op in ("jump", "call"):
                    project.target(args["target"], scene, source)
                elif op == "assign":
                    if args["name"] not in names:
                        raise BNEError(f"Сначала объявите default {args['name']} = ...", source)
                    check_expression(args["value"])
                elif op == "branch":
                    check_expression(args["condition"])
                elif op == "menu":
                    for choice in args["choices"]:
                        check_text(choice["text"], choice["source"])
                        if choice["condition"]:
                            check_expression(choice["condition"])
                elif op == "say":
                    if args["speaker"] is not None and args["speaker"] not in project.characters:
                        raise BNEError(f"Неизвестный персонаж «{args['speaker']}».", source)
                    check_text(args["text"], source)
                elif op in ("scene", "show"):
                    if args["image"] not in project.images:
                        raise BNEError(f"Неизвестное изображение «{args['image']}».", source)
                elif op == "hide" and args["image"] not in tags:
                    raise BNEError(f"Неизвестный тег персонажа «{args['image']}».", source)
                elif op == "play":
                    game_file(project.root, args["path"], source)
                    project.audio.add(args["path"])


def load_project(path: str | Path = "game") -> Project:
    return ProjectLoader(Path(path)).load()
