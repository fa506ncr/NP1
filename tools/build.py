"""Build a native, editable-game desktop distribution; run on the target OS.

    python -m pip install -e ".[build]"
    python tools/build.py

Generated binaries and archives stay in ignored dist/. No cross-compilation.
"""

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

from bne import __version__
from bne.errors import BNEError
from bne.project import load_project

ROOT = Path(__file__).resolve().parents[1]
BUILD_FORMAT = "bne-desktop-build"
PYGAME_VERSION = "2.5.8"
MARKER = "bne-build.json"


def archive_name(name: str) -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)
    architecture = platform.machine().lower()
    architecture = {"amd64": "x86_64", "aarch64": "arm64"}.get(architecture, architecture)
    return f"{name}-{system}-{architecture}.zip"


def validate_output(output: Path, name: str, source: Path, overwrite: bool) -> Path:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", name):
        raise BNEError("Имя сборки: латиница, цифры, _ и -, до 48 символов; первый символ — буква.")
    candidate = output / name
    if candidate.is_symlink():
        raise BNEError("Нельзя заменять символическую ссылку вместо папки сборки.")
    target = candidate.resolve()
    if (
        ROOT.is_relative_to(target)
        or target.is_relative_to(ROOT / ".git")
        or source.is_relative_to(target)
        or target.is_relative_to(source)
    ):
        raise BNEError("Папка сборки не должна заменять репозиторий, .git или исходную игру.")
    if target.exists():
        if not overwrite:
            raise BNEError(f"Сборка уже существует: {target}\nДля замены добавьте --overwrite.")
        try:
            marker = json.loads((target / MARKER).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BNEError("Отказ: существующая папка не является сборкой BNE.") from error
        if not isinstance(marker, dict) or marker.get("format") != BUILD_FORMAT:
            raise BNEError("Отказ: существующая папка не является сборкой BNE.")
    archive = output / archive_name(name)
    if archive.is_symlink():
        raise BNEError("Нельзя заменять символическую ссылку вместо архива сборки.")
    if archive.exists() and (not overwrite or not archive.is_file()):
        raise BNEError(f"Архив уже существует: {archive}. Для замены файла добавьте --overwrite.")
    return target


def copy_game(source: Path, destination: Path) -> None:
    """Package assets, never the author's saves, hidden files, caches or symlinks."""
    for current, directories, filenames in os.walk(source, followlinks=False):
        current = Path(current)
        relative = current.relative_to(source)
        directories[:] = [
            name
            for name in directories
            if not name.startswith(".")
            and name != "__pycache__"
            and not (current == source and name == "saves")
        ]
        for name in directories:
            if (current / name).is_symlink():
                raise BNEError(f"Для сборки замените ссылку обычной папкой: {relative / name}")
        target = destination / relative
        target.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                continue
            if current == source and name == "saves":
                continue
            path = current / name
            if path.is_symlink():
                raise BNEError(f"Для сборки замените ссылку обычным файлом: {relative / name}")
            shutil.copy2(path, target / name)
    (destination / "saves").mkdir(exist_ok=True)


def copy_licenses(destination: Path) -> None:
    notices = destination / "licenses"
    shutil.copytree(ROOT / "licenses", notices)
    candidates = [
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
    ]
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license is None:
        raise BNEError("Не найден LICENSE.txt вашего Python. Используйте обычную установку Python.")
    shutil.copy2(python_license, notices / "Python.txt")
    distribution = importlib.metadata.distribution("pyinstaller")
    bootloader_license = next(
        (
            distribution.locate_file(path)
            for path in distribution.files or []
            if path.name.lower() == "copying.txt"
        ),
        None,
    )
    if bootloader_license is None:
        raise BNEError("Не найдена лицензия загрузчика PyInstaller. Переустановите .[build].")
    shutil.copy2(bootloader_license, notices / "PyInstaller.txt")
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")


def publish(
    bundle: Path, archive: Path, destination: Path, archive_destination: Path, temporary: Path
) -> None:
    """A compiler/check/zip failure must never remove the last working distribution."""
    old_bundle, old_archive = temporary / "previous-bundle", temporary / "previous.zip"
    new_bundle = new_archive = False
    try:
        if destination.exists():
            destination.rename(old_bundle)
        if archive_destination.exists():
            archive_destination.rename(old_archive)
        bundle.rename(destination)
        new_bundle = True
        archive.rename(archive_destination)
        new_archive = True
    except OSError:
        if new_archive:
            archive_destination.unlink()
        if new_bundle:
            shutil.rmtree(destination)
        if old_archive.exists():
            old_archive.rename(archive_destination)
        if old_bundle.exists():
            old_bundle.rename(destination)
        raise


def build(game: Path, output: Path, name: str, overwrite: bool = False) -> tuple[Path, Path]:
    game = game.expanduser().resolve()
    output = output.expanduser().resolve()
    if not game.is_dir():
        raise BNEError("--game должен указывать на папку с manager.bne.")
    project = load_project(game)
    destination = validate_output(output, name, game, overwrite)
    if importlib.util.find_spec("PyInstaller") is None:
        raise BNEError('Для сборки установите зависимости: python -m pip install -e ".[build]"')
    if importlib.metadata.version("pygame-ce") != PYGAME_VERSION:
        raise BNEError(f"Сборка проверена с pygame-ce {PYGAME_VERSION}. Установите .[build].")
    output.mkdir(parents=True, exist_ok=True)
    archive_destination = output / archive_name(name)
    if overwrite and destination.exists():
        print(
            "Внимание: старая сборка будет заменена, включая её game/saves. "
            "Скопируйте нужные сохранения до сборки.",
            flush=True,
        )
    with tempfile.TemporaryDirectory(prefix=".bne-", dir=output) as temporary_name:
        temporary = Path(temporary_name)
        staged_game = temporary / "game"
        copy_game(game, staged_game)
        load_project(staged_game)
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--windowed" if sys.platform == "win32" else "--console",
            "--name",
            name,
            "--distpath",
            str(temporary / "dist"),
            "--workpath",
            str(temporary / "work"),
            "--specpath",
            str(temporary / "spec"),
            "--log-level",
            "WARN",
            "--exclude-module",
            "pytest",
            "--exclude-module",
            "tkinter",
            str(ROOT / "main.py"),
        ]
        print(f"Сборка {project.config.title} для {sys.platform}…", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
        bundle = temporary / "dist" / name
        staged_game.rename(bundle / "game")
        copy_licenses(bundle)
        metadata = {
            "format": BUILD_FORMAT,
            "version": 1,
            "engine_version": __version__,
            "pygame_version": PYGAME_VERSION,
            "platform": sys.platform,
            "architecture": platform.machine(),
            "title": project.config.title,
        }
        (bundle / MARKER).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (bundle / "README.txt").write_text(
            "Berl Novella Engine\n\n"
            "Распакуйте архив целиком и запустите приложение в этой папке.\n"
            "Python устанавливать не нужно. Не переносите один .exe отдельно от _internal и game.\n"
            "Сценарии: game/manager.bne и game/scene/*.bne — "
            "их можно редактировать без пересборки.\n"
            "Сохранение: F5; загрузка: F9; пауза: Esc; полный экран: F11.\n"
            "Сохранения: game/saves/. Нужна папка с правом записи или параметр --save-dir.\n"
            "Сборка без цифровой подписи. Лицензии зависимостей находятся в licenses/.\n",
            encoding="utf-8",
        )
        executable = bundle / (name + (".exe" if sys.platform == "win32" else ""))
        # Deliberately run outside the project: a double-click must not depend on cwd.
        check_directory = temporary / "empty-cwd"
        check_directory.mkdir()
        check = subprocess.run(
            [str(executable), "--check"],
            cwd=check_directory,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=60,
        )
        if check.returncode:
            raise BNEError("Готовое приложение не прошло --check.\n" + check.stdout + check.stderr)
        archive_base = temporary / "release"
        archive = Path(shutil.make_archive(str(archive_base), "zip", bundle.parent, name))
        publish(bundle, archive, destination, archive_destination, temporary)
    return destination, archive_destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сборка BNE без Python на компьютере игрока.")
    parser.add_argument("--game", type=Path, default=ROOT / "game", help="папка исходной игры")
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="папка для результата")
    parser.add_argument("--name", default="BerlNovellaEngine", help="имя приложения (без .exe)")
    parser.add_argument("--overwrite", action="store_true", help="заменить предыдущую сборку BNE")
    args = parser.parse_args(argv)
    try:
        directory, archive = build(args.game, args.output, args.name, args.overwrite)
        print(f"Готово: {directory}\nАрхив для передачи игрокам: {archive}")
        return 0
    except (
        BNEError,
        OSError,
        subprocess.SubprocessError,
        importlib.metadata.PackageNotFoundError,
    ) as error:
        print(f"BNE build: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
