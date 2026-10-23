"""Versioned JSON saves. Never unpickle data or execute code from a save file."""

import json
import math
import os
import re
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bne.errors import BNEError
from bne.expressions import scalar
from bne.model import POSITIONS, Project
from bne.runtime import Dialogue, Ended, Frame, Menu, Music, Pause, Sprite, Story

SAVE_VERSION = 1
MAX_SAVE_BYTES = 8_000_000


def pack(story: Story) -> dict:
    if story.waiting is None:
        raise BNEError("Сохранение доступно только во время диалога, выбора или паузы.")
    kind = {Dialogue: "dialogue", Menu: "menu", Pause: "pause", Ended: "end"}[type(story.waiting)]
    return {
        "format": "BNE",
        "version": SAVE_VERSION,
        "project": story.project.fingerprint,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "state": {
            "frame": asdict(story.frame),
            "stack": [asdict(frame) for frame in story.stack],
            "variables": dict(story.variables),
            "background": story.background,
            "sprites": {tag: asdict(sprite) for tag, sprite in story.sprites.items()},
            "music": asdict(story.music) if story.music else None,
            "window_visible": story.window_visible,
            "waiting": {"kind": kind, "anchor": asdict(story.wait_at) if story.wait_at else None},
            "history": [asdict(entry) for entry in story.history],
        },
    }


def _require(condition: bool) -> None:
    if not condition:
        raise BNEError("Сохранение повреждено или содержит некорректные данные.")


def _frame(project: Project, data: Any) -> Frame:
    _require(isinstance(data, dict))
    scene, pc = data.get("scene"), data.get("pc")
    _require(isinstance(scene, str) and scene in project.scripts)
    _require(type(pc) is int and 0 <= pc <= len(project.scripts[scene].code))
    return Frame(scene, pc)


def unpack(project: Project, data: Any) -> Story:
    _require(isinstance(data, dict) and data.get("format") == "BNE")
    if type(data.get("version")) is not int or data["version"] != SAVE_VERSION:
        raise BNEError("Версия сохранения не поддерживается этим движком.")
    if data.get("project") != project.fingerprint:
        raise BNEError(
            "Сценарии игры изменились. Старое сохранение несовместимо; начните новую игру."
        )
    try:
        state = data["state"]
        _require(isinstance(state, dict))
        story = Story(project)
        story.frame = _frame(project, state["frame"])
        _require(isinstance(state["stack"], list) and len(state["stack"]) <= 128)
        story.stack = [_frame(project, frame) for frame in state["stack"]]
        variables = state["variables"]
        _require(isinstance(variables, dict) and set(variables) == set(project.defaults))
        story.variables = {key: scalar(value) for key, value in variables.items()}
        background = state["background"]
        _require(
            background is None or (isinstance(background, str) and background in project.images)
        )
        story.background = background
        sprites = state["sprites"]
        _require(isinstance(sprites, dict) and len(sprites) <= len(project.images))
        for tag, sprite in sprites.items():
            _require(isinstance(sprite, dict))
            image, position = sprite.get("image"), sprite.get("position")
            _require(isinstance(image, str) and image in project.images and image.split()[0] == tag)
            _require(isinstance(position, str) and position in POSITIONS)
            story.sprites[tag] = Sprite(image, position)
        music = state["music"]
        if music is not None:
            _require(isinstance(music, dict))
            path, loop, volume = music.get("path"), music.get("loop"), music.get("volume")
            _require(isinstance(path, str) and path in project.audio)
            _require(type(loop) is bool)
            _require(type(volume) in (int, float) and math.isfinite(volume) and 0 <= volume <= 1)
            story.music = Music(path, loop, volume)
        _require(type(state["window_visible"]) is bool)
        story.window_visible = state["window_visible"]
        waiting = state["waiting"]
        _require(isinstance(waiting, dict))
        kind = waiting["kind"]
        _require(isinstance(kind, str) and kind in ("dialogue", "menu", "pause", "end"))
        if kind == "end":
            _require(waiting["anchor"] is None)
            story.waiting = Ended()
        else:
            anchor = _frame(project, waiting["anchor"])
            _require(anchor.scene == story.frame.scene and anchor.pc == story.frame.pc - 1)
            instruction = project.scripts[anchor.scene].code[anchor.pc]
            _require(instruction.op == {"dialogue": "say", "menu": "menu", "pause": "pause"}[kind])
            story.wait_at = anchor
            story.waiting = story.wait_for(instruction)
        history = state.get("history", [])
        _require(isinstance(history, list) and len(history) <= 200)
        for entry in history:
            _require(isinstance(entry, dict))
            name, color, text = entry.get("speaker"), entry.get("color"), entry.get("text")
            _require(name is None or isinstance(name, str))
            _require(isinstance(color, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is not None)
            _require(isinstance(text, str))
            if name is not None:
                scalar(name)
            scalar(text)
            story.history.append(Dialogue(name, color, text))
        return story
    except (KeyError, TypeError, ValueError, IndexError, RecursionError) as error:
        raise BNEError("Сохранение повреждено или содержит некорректные данные.") from error


class SaveStore:
    def __init__(self, project: Project, directory: str | Path | None = None):
        self.project = project
        self.directory = Path(directory) if directory is not None else project.root / "saves"

    def _path(self, slot: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", slot):
            raise BNEError("Недопустимое имя слота сохранения.")
        return self.directory / f"{slot}.json"

    def exists(self, slot: str = "quick") -> bool:
        return self._path(slot).is_file()

    def save(self, story: Story, slot: str = "quick") -> None:
        if story.project.fingerprint != self.project.fingerprint:
            raise BNEError("Нельзя сохранить историю от другого проекта.")
        path = self._path(slot)
        data = json.dumps(pack(story), ensure_ascii=False, indent=2, allow_nan=False)
        if len(data.encode("utf-8")) > MAX_SAVE_BYTES:
            raise BNEError("Сохранение слишком большое.")
        temporary: str | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False
            ) as handle:
                temporary = handle.name
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as error:
            raise BNEError(f"Не удалось записать сохранение: {error}") from error
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink(missing_ok=True)

    def load(self, slot: str = "quick") -> Story:
        path = self._path(slot)
        try:
            if path.stat().st_size > MAX_SAVE_BYTES:
                raise BNEError("Файл сохранения слишком большой.")
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise BNEError("Сохранение ещё не создано. Нажмите F5 во время игры.") from error
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
            raise BNEError(f"Не удалось прочитать сохранение: {error}") from error
        return unpack(self.project, data)
