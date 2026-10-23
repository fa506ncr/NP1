import itertools
import os
from pathlib import Path

import pytest

# Only presentation tests need SDL; core/compiler tests never import pygame.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

REPO = Path(__file__).resolve().parents[1]
DEFAULTS = """\
define e = Character("Ева", color="#AABBCC")
define n = Character(None)
default score = 0
default name = "Гость"
default flag = False
image bg room = "images/room.png"
image eva calm = "images/eva.png"
image eva smile = "images/eva.png"
"""


@pytest.fixture
def write_game(tmp_path):
    counter = itertools.count()

    def write(scripts=None, *, manager=None, extra=""):
        root = tmp_path / f"game{next(counter)}"
        (root / "scene").mkdir(parents=True)
        (root / "images").mkdir()
        (root / "audio").mkdir()
        # Compiler tests only need file existence; renderer tests use real demo assets.
        (root / "images/room.png").write_bytes(b"image")
        (root / "images/eva.png").write_bytes(b"image")
        (root / "audio/music.wav").write_bytes(b"audio")
        scripts = (
            scripts
            if scripts is not None
            else {"intro": 'label start:\n    "Привет"\n    return\n'}
        )
        for scene, text in scripts.items():
            (root / f"scene/{scene}.bne").write_text(text, encoding="utf-8")
        if manager is None:
            registry = "\n".join(f'scene {name} = "scene/{name}.bne"' for name in scripts)
            manager = DEFAULTS + extra + "\n" + registry + "\nstart " + next(iter(scripts))
        (root / "manager.bne").write_text(manager, encoding="utf-8")
        return root

    return write


@pytest.fixture
def demo_project():
    from bne.project import load_project

    return load_project(REPO / "game")
