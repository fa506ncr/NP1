import json
import subprocess
import sys
from pathlib import Path

import pytest

from bne import launcher
from bne.__main__ import main as cli_main
from bne.errors import BNEError
from bne.project import load_project
from tools.build import BUILD_FORMAT, MARKER, copy_game, publish, validate_output

ROOT = Path(__file__).resolve().parents[1]


def test_source_launcher_works_outside_repository(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Проверка пройдена" in result.stdout


def test_frozen_game_is_next_to_executable_not_extraction_directory(tmp_path, monkeypatch):
    executable = tmp_path / "My game" / "BerlNovellaEngine.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "temporary-runtime"), raising=False)
    assert launcher.game_directory() == executable.parent / "game"


def test_cli_explicit_project_overrides_desktop_default(write_game, capsys):
    root = write_game()
    assert cli_main([str(root), "--check"], default_project="does-not-exist") == 0
    assert "Проверка пройдена" in capsys.readouterr().out


def test_windowed_launcher_has_a_log_instead_of_none_streams(write_game, tmp_path, monkeypatch):
    root = write_game()
    monkeypatch.setattr(launcher, "game_directory", lambda: root)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        result = launcher.main(["--check"])
        assert sys.stdout is None and sys.stderr is None
    assert result == 0
    assert "Проверка пройдена" in (tmp_path / "BerlNovellaEngine/last-run.log").read_text("utf-8")


def test_windowed_error_is_reported_but_check_does_not_open_a_dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "game_directory", lambda: tmp_path / "missing")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    shown = []
    monkeypatch.setattr(launcher, "show_error", lambda message, path: shown.append(message))
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        assert launcher.main([]) == 1
        assert launcher.main(["--check"]) == 1
    assert len(shown) == 1
    assert "прочитать" in shown[0]
    assert "BNE:" in (tmp_path / "BerlNovellaEngine/last-run.log").read_text("utf-8")


def test_windowed_unexpected_error_writes_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    shown = []
    monkeypatch.setattr(launcher, "show_error", lambda message, path: shown.append(message))

    def fail(*args, **kwargs):
        raise RuntimeError("startup failed")

    monkeypatch.setattr(launcher, "cli_main", fail)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        assert launcher.main([]) == 1
    assert "startup failed" in shown[0]
    assert "Traceback" in (tmp_path / "BerlNovellaEngine/last-run.log").read_text("utf-8")


def test_copy_game_keeps_assets_but_not_saves_or_hidden_data(write_game, tmp_path):
    root = write_game()
    (root / "saves").mkdir()
    (root / "saves/quick.json").write_text('{"private": "progress"}')
    (root / ".env").write_text("private config")
    (root / ".git").mkdir()
    (root / ".git/config").write_text("not a game asset")
    (root / "images/.cache").mkdir()
    (root / "images/.cache/scratch.png").write_bytes(b"scratch")
    (root / "__pycache__").mkdir()
    (root / "__pycache__/cache.pyc").write_bytes(b"bytecode")
    target = tmp_path / "packaged game"
    copy_game(root, target)
    assert (target / "manager.bne").is_file()
    assert (target / "images/room.png").read_bytes() == b"image"
    assert (target / "saves").is_dir() and not list((target / "saves").iterdir())
    assert not (target / ".env").exists()
    assert not (target / ".git").exists()
    assert not (target / "images/.cache").exists()
    assert not (target / "__pycache__").exists()
    assert load_project(root).fingerprint == load_project(target).fingerprint


def test_copy_game_rejects_symlinks(write_game, tmp_path):
    root = write_game()
    link = root / "images/link.png"
    try:
        link.symlink_to(root / "images/room.png")
    except OSError:
        pytest.skip("Windows symlink privileges are not available")
    with pytest.raises(BNEError, match="ссылку"):
        copy_game(root, tmp_path / "game-copy")


@pytest.mark.parametrize("name", ["../game", "", "a/b", "BNE.exe", "x" * 49])
def test_output_name_cannot_be_a_path(tmp_path, name):
    with pytest.raises(BNEError, match="Имя сборки"):
        validate_output(tmp_path, name, tmp_path / "game", False)


def test_never_replace_sources_or_repository(write_game):
    root = write_game()
    with pytest.raises(BNEError, match="репозиторий"):
        validate_output(ROOT.parent, ROOT.name, root, True)
    with pytest.raises(BNEError, match="исходную игру"):
        validate_output(root.parent, root.name, root, True)
    with pytest.raises(BNEError, match="исходную игру"):
        validate_output(root, "Build", root, True)


def test_overwrite_requires_a_known_build_marker(tmp_path):
    target = tmp_path / "BNE"
    target.mkdir()
    (target / "important.txt").write_text("keep me")
    with pytest.raises(BNEError, match="уже существует"):
        validate_output(tmp_path, "BNE", tmp_path / "source-game", False)
    with pytest.raises(BNEError, match="не является сборкой"):
        validate_output(tmp_path, "BNE", tmp_path / "source-game", True)
    assert (target / "important.txt").read_text() == "keep me"
    (target / MARKER).write_text(json.dumps({"format": BUILD_FORMAT}))
    assert validate_output(tmp_path, "BNE", tmp_path / "source-game", True) == target


def test_publish_rolls_back_old_bundle_if_archive_move_fails(tmp_path, monkeypatch):
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    destination = tmp_path / "BNE"
    destination.mkdir()
    (destination / "old-game.txt").write_text("working game")
    archive_destination = tmp_path / "BNE.zip"
    archive_destination.write_bytes(b"working archive")
    bundle = temporary / "new-bundle"
    bundle.mkdir()
    (bundle / "new-game.txt").write_text("new game")
    archive = temporary / "new.zip"
    archive.write_bytes(b"new archive")
    real_rename = Path.rename

    def fail_archive_rename(path, target):
        if path == archive:
            raise OSError("archive is locked")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_archive_rename)
    with pytest.raises(OSError, match="locked"):
        publish(bundle, archive, destination, archive_destination, temporary)
    assert (destination / "old-game.txt").read_text() == "working game"
    assert not (destination / "new-game.txt").exists()
    assert archive_destination.read_bytes() == b"working archive"
