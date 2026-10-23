"""Command line entry point: python -m bne [game/] [--check]."""

import argparse
import sys
from pathlib import Path

from bne import __version__
from bne.errors import BNEError
from bne.project import load_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Berl Novella Engine — движок визуальных новелл.")
    parser.add_argument(
        "project", nargs="?", default="game", help="папка игры или manager.bne (по умолчанию: game)"
    )
    parser.add_argument("--check", action="store_true", help="проверить игру без открытия окна")
    parser.add_argument("--mute", action="store_true", help="запустить без звука")
    parser.add_argument("--fullscreen", action="store_true", help="полноэкранный режим")
    parser.add_argument("--save-dir", type=Path, help="другая папка для сохранений")
    parser.add_argument("--version", action="version", version=f"Berl Novella Engine {__version__}")
    args = parser.parse_args(argv)
    try:
        project = load_project(args.project)
        if args.check:
            print(f"BNE {__version__} · {project.config.title}")
            print(
                f"Проверка пройдена: сцен — {len(project.scripts)}, "
                f"персонажей — {len(project.characters)}, изображений — {len(project.images)}."
            )
            print(f"Старт: {project.start[0]} · {project.manager}")
            return 0
        try:
            from bne.app import App
        except ModuleNotFoundError as error:
            if error.name != "pygame":
                raise
            raise BNEError(
                'Установите движок и зависимости: python -m pip install -e "."'
            ) from error
        return App(
            project, save_dir=args.save_dir, mute=args.mute, fullscreen=args.fullscreen
        ).run()
    except BNEError as error:
        print(f"BNE: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
