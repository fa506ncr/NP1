import copy
import json

import pytest

from bne.errors import BNEError
from bne.project import load_project
from bne.runtime import Dialogue, Ended, Menu, Story
from bne.saves import SaveStore, pack, unpack


def sample_story(write_game):
    project = load_project(
        write_game(
            {
                "intro": """\
label start:
    scene bg room
    show eva calm at right
    play music "audio/music.wav"
    call talk
    "после вызова"
    return
label talk:
    $ score += 1
    e "Счёт: [score]"
    menu:
        "Дальше":
            return
"""
            }
        )
    )
    story = Story(project)
    story.start()
    return story


def test_save_restores_exact_wait_and_call_stack(write_game, tmp_path):
    story = sample_story(write_game)
    store = SaveStore(story.project, tmp_path / "saves")
    store.save(story)
    assert store.exists()
    on_disk = json.loads((tmp_path / "saves/quick.json").read_text())
    assert on_disk["format"] == "BNE"
    assert on_disk["state"]["waiting"]["kind"] == "dialogue"
    loaded = store.load()
    assert loaded.waiting == story.waiting
    assert loaded.background == story.background
    assert loaded.sprites == story.sprites
    assert loaded.music == story.music
    assert loaded.history == story.history
    assert len(loaded.stack) == 1
    assert not loaded.events
    loaded.advance()
    assert isinstance(loaded.waiting, Menu)
    store.save(loaded)
    loaded = store.load()
    assert isinstance(loaded.waiting, Menu)
    loaded.choose(0)
    assert isinstance(loaded.waiting, Dialogue)
    assert loaded.waiting.text == "после вызова"
    assert loaded.variables["score"] == 1
    assert loaded.stack == []
    loaded.advance()
    assert isinstance(unpack(story.project, pack(loaded)).waiting, Ended)


def test_changed_scripts_reject_old_save(write_game):
    story = sample_story(write_game)
    data = pack(story)
    path = story.project.root / "scene/intro.bne"
    path.write_text(path.read_text() + "\n# Changed script")
    with pytest.raises(BNEError, match="изменились"):
        unpack(load_project(story.project.root), data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("frame", {"scene": "missing", "pc": 1}),
        ("frame", {"scene": "intro", "pc": -1}),
        ("frame", {"scene": "intro", "pc": True}),
        ("frame", {"scene": "intro", "pc": 99999}),
        ("frame", None),
        ("stack", [None]),
        ("stack", [None] * 129),
        ("variables", {"score": 1}),
        ("variables", {"score": [], "flag": False, "name": "Гость"}),
        ("variables", {"score": float("nan"), "flag": False, "name": "Гость"}),
        ("background", "unknown"),
        ("background", []),
        ("sprites", {"eva": {"image": "eva calm", "position": "top"}}),
        ("sprites", {"wrong_tag": {"image": "eva calm", "position": "left"}}),
        ("music", {"path": "../outside.wav", "loop": True, "volume": 0.5}),
        ("music", {"path": "audio/music.wav", "loop": 1, "volume": 0.5}),
        ("music", {"path": "audio/music.wav", "loop": True, "volume": float("inf")}),
        ("window_visible", "yes"),
        ("waiting", {"kind": "unknown", "anchor": None}),
        ("waiting", {"kind": [], "anchor": None}),
        ("waiting", {"kind": "menu", "anchor": {"scene": "intro", "pc": 0}}),
        ("history", [{"speaker": "x", "text": "a", "color": "not a color"}]),
        ("history", "text"),
    ],
)
def test_invalid_save_state_is_rejected(write_game, key, value):
    story = sample_story(write_game)
    data = pack(story)
    data["state"][key] = value
    with pytest.raises(BNEError):
        unpack(story.project, data)
    # A failed load must not change the running story.
    assert story.variables["score"] == 1
    assert story.waiting.text == "Счёт: 1"


@pytest.mark.parametrize(
    "data", [None, [], {}, {"format": "BNE", "version": True}, {"format": "BNE", "version": 999}]
)
def test_invalid_save_envelope(write_game, data):
    story = sample_story(write_game)
    with pytest.raises(BNEError):
        unpack(story.project, data)


def test_missing_and_non_json_save(write_game, tmp_path):
    story = sample_story(write_game)
    store = SaveStore(story.project, tmp_path)
    with pytest.raises(BNEError, match="ещё не создано"):
        store.load()
    (tmp_path / "quick.json").write_bytes(b"not json or pickle")
    with pytest.raises(BNEError, match="прочитать"):
        store.load()
    data = pack(story)
    del data["state"]["waiting"]
    with pytest.raises(BNEError):
        unpack(story.project, data)


def test_save_is_atomic_and_old_save_survives_failure(write_game, tmp_path, monkeypatch):
    story = sample_story(write_game)
    store = SaveStore(story.project, tmp_path)
    store.save(story)
    before = (tmp_path / "quick.json").read_bytes()

    def fail_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("bne.saves.os.replace", fail_replace)
    with pytest.raises(BNEError, match="записать"):
        store.save(story)
    assert (tmp_path / "quick.json").read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("slot", ["../outside", "", "/root", "quick.json", "x" * 33])
def test_save_slots_cannot_escape_directory(write_game, tmp_path, slot):
    store = SaveStore(sample_story(write_game).project, tmp_path)
    with pytest.raises(BNEError, match="имя слота"):
        store.load(slot)


def test_snapshot_is_independent_of_future_changes(write_game):
    story = sample_story(write_game)
    data = pack(story)
    old = copy.deepcopy(data)
    story.variables["score"] = 100
    story.history.clear()
    assert data == old


def test_save_only_at_interaction(write_game):
    story = Story(sample_story(write_game).project)
    with pytest.raises(BNEError, match="только во время"):
        pack(story)
