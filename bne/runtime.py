"""The visual novel virtual machine. No window, clock, filesystem writes or pygame here."""

import ast
from dataclasses import dataclass

from bne.errors import BNEError
from bne.expressions import binary, interpolate
from bne.model import Instruction, Project, Scalar

ASSIGN_OPERATORS = {
    "+=": ast.Add,
    "-=": ast.Sub,
    "*=": ast.Mult,
    "/=": ast.Div,
    "//=": ast.FloorDiv,
    "%=": ast.Mod,
}


@dataclass(frozen=True)
class Frame:
    scene: str
    pc: int


@dataclass(frozen=True)
class Sprite:
    image: str
    position: str


@dataclass(frozen=True)
class Music:
    path: str
    loop: bool
    volume: float


@dataclass(frozen=True)
class Dialogue:
    speaker: str | None
    color: str
    text: str


@dataclass(frozen=True)
class Choice:
    text: str
    target: int


@dataclass(frozen=True)
class Menu:
    choices: tuple[Choice, ...]


@dataclass(frozen=True)
class Pause:
    seconds: float | None


@dataclass(frozen=True)
class Ended:
    pass


Wait = Dialogue | Menu | Pause | Ended


@dataclass(frozen=True)
class Event:
    kind: str
    data: dict


class Story:
    """Advance until an interaction; the host decides how to display that interaction."""

    def __init__(self, project: Project):
        self.project = project
        self.frame = Frame(*project.start)
        self.stack: list[Frame] = []
        self.variables: dict[str, Scalar] = dict(project.defaults)
        self.background: str | None = None
        self.sprites: dict[str, Sprite] = {}
        self.music: Music | None = None
        self.window_visible = True
        self.waiting: Wait | None = None
        self.wait_at: Frame | None = None
        self.events: list[Event] = []
        self.history: list[Dialogue] = []

    def start(self) -> None:
        if self.waiting is None:
            self._run()

    def advance(self) -> None:
        if isinstance(self.waiting, (Dialogue, Pause)):
            self.waiting = None
            self.wait_at = None
            self._run()

    def choose(self, index: int) -> None:
        if not isinstance(self.waiting, Menu):
            raise BNEError("Сейчас нет активного меню выбора.")
        if type(index) is not int or not 0 <= index < len(self.waiting.choices):
            raise BNEError("Такого варианта выбора нет.")
        self.frame = Frame(self.frame.scene, self.waiting.choices[index].target)
        self.waiting = None
        self.wait_at = None
        self._run()

    def drain_events(self) -> list[Event]:
        events, self.events = self.events, []
        return events

    def wait_for(self, instruction: Instruction) -> Dialogue | Menu | Pause:
        """Reconstruct a wait from validated code (also used to restore a JSON save)."""
        args, source = instruction.args, instruction.source
        if instruction.op == "say":
            character = self.project.characters.get(args["speaker"])
            name = character.name if character else None
            if name is not None:
                name = interpolate(name, self.variables, source)
                if len(name) > 100:
                    raise BNEError("Имя персонажа после подстановки длиннее 100 символов.", source)
            return Dialogue(
                name,
                character.color if character else "#D6DEED",
                interpolate(args["text"], self.variables, source),
            )
        if instruction.op == "menu":
            options = tuple(
                Choice(
                    interpolate(choice["text"], self.variables, choice["source"]), choice["target"]
                )
                for choice in args["choices"]
                if choice["condition"] is None or choice["condition"].evaluate(self.variables)
            )
            if not options:
                raise BNEError("У menu нет доступных вариантов: все условия ложны.", source)
            return Menu(options)
        if instruction.op == "pause":
            return Pause(args["seconds"])
        raise BNEError("Невозможно восстановить ожидание для этой команды.", source)

    def _finish(self) -> None:
        self.waiting = Ended()
        self.wait_at = None

    def _run(self) -> None:
        for _ in range(10_000):
            script = self.project.scripts[self.frame.scene]
            if self.frame.pc >= len(script.code):
                if self.stack:
                    self.frame = self.stack.pop()
                    continue
                self._finish()
                return
            anchor = self.frame
            instruction = script.code[anchor.pc]
            self.frame = Frame(anchor.scene, anchor.pc + 1)
            op, args, source = instruction.op, instruction.args, instruction.source
            if op in ("say", "menu", "pause"):
                self.waiting = self.wait_for(instruction)
                self.wait_at = anchor
                if isinstance(self.waiting, Dialogue):
                    self.history.append(self.waiting)
                    self.history = self.history[-200:]
                return
            if op in ("jump", "call"):
                if op == "call":
                    if len(self.stack) >= 128:
                        raise BNEError("Слишком глубокая цепочка call (максимум 128).", source)
                    self.stack.append(self.frame)
                self.frame = Frame(*self.project.target(args["target"], anchor.scene, source))
            elif op == "return":
                if not self.stack:
                    self._finish()
                    return
                self.frame = self.stack.pop()
            elif op == "end":
                self._finish()
                return
            elif op == "assign":
                value = args["value"].evaluate(self.variables)
                if args["operator"] != "=":
                    value = binary(
                        ASSIGN_OPERATORS[args["operator"]],
                        self.variables[args["name"]],
                        value,
                        source,
                    )
                self.variables[args["name"]] = value
            elif op == "branch":
                if not args["condition"].evaluate(self.variables):
                    self.frame = Frame(anchor.scene, args["target"])
            elif op == "goto":
                self.frame = Frame(anchor.scene, args["target"])
            elif op == "scene":
                self.background = args["image"]
                self.sprites.clear()
                self.events.append(Event("visual", {"transition": args["transition"]}))
            elif op == "show":
                tag = args["image"].split()[0]
                previous = self.sprites.get(tag)
                position = args["position"] or (previous.position if previous else "center")
                self.sprites[tag] = Sprite(args["image"], position)
                self.events.append(Event("visual", {"transition": args["transition"]}))
            elif op == "hide":
                self.sprites.pop(args["image"], None)
                self.events.append(Event("visual", {"transition": args["transition"]}))
            elif op == "transition":
                self.events.append(Event("visual", args))
            elif op == "window":
                self.window_visible = args["visible"]
            elif op == "play":
                volume = args["volume"]
                if volume is None:
                    volume = self.project.config.music_volume if args["channel"] == "music" else 1.0
                data = {**args, "volume": volume}
                if args["channel"] == "music":
                    self.music = Music(args["path"], args["loop"], volume)
                self.events.append(Event("play", data))
            elif op == "stop":
                if args["channel"] == "music":
                    self.music = None
                self.events.append(Event("stop", args))
        raise BNEError(
            "Выполнено 10 000 команд без диалога, выбора или pause. "
            "Возможно, в jump бесконечный цикл.",
            instruction.source,
        )
