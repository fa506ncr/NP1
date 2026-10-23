"""Project metadata and the small, renderer-independent instruction set."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bne.errors import BNEError, Source

Scalar = str | int | float | bool | None
POSITIONS = {"left", "center", "right"}
TRANSITIONS = {"none", "fade", "dissolve"}


@dataclass(frozen=True)
class Character:
    name: str | None
    color: str = "#B8D9E8"


@dataclass(frozen=True)
class Config:
    title: str = "Berl Novella Engine"
    width: int = 1280
    height: int = 720
    text_speed: float = 42.0
    music_volume: float = 0.35
    font: str | None = None


@dataclass(frozen=True)
class SceneSpec:
    name: str
    path: Path
    source: Source
    mode: str = "novel"
    entry: str = "start"


@dataclass
class Instruction:
    op: str
    args: dict[str, Any]
    source: Source


@dataclass
class Script:
    spec: SceneSpec
    code: list[Instruction] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)


@dataclass
class Project:
    root: Path
    manager: Path
    config: Config
    characters: dict[str, Character]
    images: dict[str, Path]
    defaults: dict[str, Scalar]
    scripts: dict[str, Script]
    start: tuple[str, int]
    fingerprint: str
    audio: set[str] = field(default_factory=set)

    def target(
        self, name: str, current_scene: str | None = None, source: Source | None = None
    ) -> tuple[str, int]:
        """Local labels win over scene names; scene.label is always explicit."""
        if "." in name:
            scene, label = name.split(".", 1)
        elif current_scene and name in self.scripts[current_scene].labels:
            return current_scene, self.scripts[current_scene].labels[name]
        elif name in self.scripts:
            scene = name
            label = self.scripts[scene].spec.entry
        else:
            raise BNEError(f"Неизвестная сцена или метка «{name}».", source)
        if scene not in self.scripts or label not in self.scripts[scene].labels:
            raise BNEError(f"Неизвестная сцена или метка «{name}».", source)
        return scene, self.scripts[scene].labels[label]
