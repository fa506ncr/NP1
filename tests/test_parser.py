import subprocess
import sys
from pathlib import Path

import pytest

from bne.errors import BNEError
from bne.project import load_project


def test_comments_quotes_bom_and_hash_colors(write_game):
    root = write_game(
        {
            "intro": """\
# Заголовок
label start:  # комментарий
    e "Цвет #aabbcc, кавычки: \\"да\\"." # за строкой
    'Путь # не комментарий'
    return
"""
        }
    )
    manager = root / "manager.bne"
    manager.write_text("\ufeff" + manager.read_text(), encoding="utf-8")
    project = load_project(root)
    assert project.characters["e"].color == "#AABBCC"
    assert project.scripts["intro"].code[0].args["text"] == 'Цвет #aabbcc, кавычки: "да".'
    assert project.scripts["intro"].code[0].source.line == 3


@pytest.mark.parametrize(
    ("script", "message"),
    [
        ('label start:\n\t"tab"', "табуляцию"),
        ('label start:\n  "two"', "четырём"),
        ('label start:\n        "eight"', "Неожиданный отступ"),
        ("label start:\n", "пустым"),
        ("label other:\n    pass", "входной метки"),
        ("label start:\n    pass\nlabel start:\n    pass", "Повторная метка"),
        ("label start:\n    explode everything", "Неизвестная команда"),
        ("label start:\n    menu:", "хотя бы один"),
        ("label start:\n    if score > 0\n        pass", "символ :"),
        ("label start:\n    else:\n        pass", "Неизвестная команда"),
        ('"no label"', "верхнем уровне"),
        ("label start:\n    show eva calm at top", "left / center / right"),
        ("label start:\n    scene bg room with zoom", "with fade"),
        ("label start:\n    hide eva calm", "hide принимает тег"),
        ("label start:\n    pause -1", "от 0"),
        ('label start:\n    play voice "file.wav"', "Аудиоканалы"),
        ('label start:\n    play music "audio/music.wav" volume 3', "от 0"),
        ('label start:\n    play music "audio/music.wav" loop noloop', "Повторный параметр"),
        ("label start:\n    stop music nonsense", "Синтаксис"),
        ("label start:\n    $ score **= 2", "Используйте"),
    ],
)
def test_syntax_errors_have_file_and_line(write_game, script, message):
    with pytest.raises(BNEError, match=message) as error:
        load_project(write_game({"intro": script}))
    assert "intro.bne:" in str(error.value)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('unknown "Hi"', "персонаж"),
        ("scene bg missing", "изображение"),
        ("show unknown", "изображение"),
        ("hide unknown", "тег"),
        ("jump missing", "метка"),
        ("call intro.missing", "метка"),
        ("$ missing = 3", "default missing"),
        ("$ score = missing + 1", "переменные"),
        ("if missing:\n        pass", "переменные"),
        ('"Hello [missing]"', "в тексте"),
        ('play music "audio/missing.wav"', "не найден"),
    ],
)
def test_static_reference_checks(write_game, line, message):
    with pytest.raises(BNEError, match=message):
        load_project(write_game({"intro": "label start:\n    " + line + "\n    return"}))


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("default score = 2", "уже объявлена"),
        ('define e = Character("Другой")', "уже объявлен"),
        ('define broken = Character("X", color="red")', "Используйте Character"),
        ('define bad = Character("X", unknown="value")', "Используйте Character"),
        ('define jump = Character("X")', "совпадает с командой"),
        ("default True = 1", "Недопустимое имя"),
        ("default value = unknown", "Неизвестная переменная"),
        ('define dynamic = Character("[missing]")', "в тексте"),
        ("define config.fake = 1", "Неизвестная настройка"),
        ("define config.width = 0", "целое"),
        ("define config.height = True", "целое"),
        ("define config.text_speed = -1", "число"),
        ("define config.music_volume = 2", "число"),
        ('define config.font = ""', "config.font"),
        ('image eva calm = "images/eva.png"', "уже объявлено"),
    ],
)
def test_manager_validation(write_game, extra, message):
    with pytest.raises(BNEError, match=message):
        load_project(write_game(extra=extra))


def test_no_start_and_duplicate_scene(write_game):
    root = write_game()
    manager = root / "manager.bne"
    original = manager.read_text()
    manager.write_text(original.replace("start intro", ""))
    with pytest.raises(BNEError, match="стартовую сцену"):
        load_project(root)
    manager.write_text(original + '\nscene intro = "scene/intro.bne"')
    with pytest.raises(BNEError, match="уже объявлена"):
        load_project(root)


def test_entry_label_and_explicit_start(write_game):
    root = write_game({"intro": 'label different:\n    "hello"\n    return'})
    manager = root / "manager.bne"
    manager.write_text(
        manager.read_text().replace('"scene/intro.bne"', '"scene/intro.bne" entry different')
    )
    assert load_project(root).start == ("intro", 0)
    manager.write_text(manager.read_text().replace("start intro", "start intro.different"))
    assert load_project(manager).start == ("intro", 0)


def test_rpg_is_explicitly_not_implemented(write_game):
    root = write_game()
    manager = root / "manager.bne"
    manager.write_text(
        manager.read_text().replace('"scene/intro.bne"', '"scene/intro.bne" mode rpg')
    )
    with pytest.raises(BNEError, match="ходьба ещё не реализована"):
        load_project(root)


def test_assets_cannot_escape_game(write_game, tmp_path):
    secret = tmp_path / "outside.png"
    secret.write_bytes(b"not an asset")
    root = write_game(extra='image unsafe = "../outside.png"')
    with pytest.raises(BNEError, match="за пределы"):
        load_project(root)
    root = write_game(extra='image unsafe = "images/link.png"')
    (root / "images/link.png").symlink_to(secret)
    with pytest.raises(BNEError, match="за пределы"):
        load_project(root)


def test_cli_check_does_not_import_pygame(demo_project):
    code = (
        "from bne.__main__ import main; import sys; code=main(['--check']); "
        "assert 'pygame' not in sys.modules; sys.exit(code)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Проверка пройдена" in result.stdout


def test_cli_error_without_traceback(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "bne", str(tmp_path / "missing"), "--check"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "BNE:" in result.stderr
    assert "Traceback" not in result.stderr


def test_scene_declaration_does_not_require_spaces_around_equals(write_game):
    root = write_game()
    path = root / "manager.bne"
    path.write_text(
        path.read_text().replace('intro = "scene/intro.bne"', 'intro="scene/intro.bne"')
    )
    assert load_project(root).start == ("intro", 0)


def test_too_many_menu_choices(write_game):
    script = "label start:\n    menu:\n" + "".join(
        f'        "Choice {index}":\n            pass\n' for index in range(10)
    )
    with pytest.raises(BNEError, match="не больше 9"):
        load_project(write_game({"intro": script}))


@pytest.mark.parametrize("path", [r"images\\room.png", r"images/\0.png", r"images/\n.png"])
def test_invalid_resource_path_is_a_language_error(write_game, path):
    root = write_game(extra=f'image unsafe = "{path}"')
    with pytest.raises(BNEError):
        load_project(root)


def test_empty_image_name_is_rejected(write_game):
    with pytest.raises(BNEError, match="Имя image"):
        load_project(write_game(extra='image    = "images/room.png"'))
