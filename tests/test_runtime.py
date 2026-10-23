import pytest

from bne.errors import BNEError
from bne.project import load_project
from bne.runtime import Dialogue, Ended, Menu, Pause, Story
from bne.saves import pack, unpack


def story_at_start(write_game, text, **kwargs):
    project = load_project(write_game({"intro": text}, **kwargs))
    story = Story(project)
    story.start()
    return story


def test_dialogue_and_interpolation(write_game):
    story = story_at_start(
        write_game,
        """\
label start:
    "Рассказчик"
    e "Привет, [name]! [[score]] = [score]."
    return
""",
    )
    assert story.waiting == Dialogue(None, "#D6DEED", "Рассказчик")
    story.advance()
    assert story.waiting == Dialogue("Ева", "#AABBCC", "Привет, Гость! [score] = 0.")
    story.advance()
    assert isinstance(story.waiting, Ended)
    story.advance()
    assert len(story.history) == 2


@pytest.mark.parametrize(
    ("choice", "answer", "score"), [(0, "ноль", 0), (1, "один", 1), (2, "два", 2)]
)
def test_menu_branches_and_nested_conditions(write_game, choice, answer, score):
    story = story_at_start(
        write_game,
        """\
label start:
    menu:
        "Первый":
            $ score = 0
        "Второй":
            $ score += 1
        "Третий":
            $ score += 2
    if score == 0:
        "ноль"
    elif score == 1:
        if not flag:
            "один"
        else:
            "не та ветка"
    else:
        "два"
    "общая реплика"
    return
""",
    )
    story.choose(choice)
    assert story.variables["score"] == score
    assert story.waiting.text == answer
    story.advance()
    assert story.waiting.text == "общая реплика"
    story.advance()
    assert isinstance(story.waiting, Ended)


def test_conditional_menu_uses_visible_indices(write_game):
    story = story_at_start(
        write_game,
        """\
label start:
    menu:
        "Скрытый" if flag:
            "не эта ветка"
        "Открытый [name]" if not flag:
            "да"
        "Всегда":
            "нет"
    return
""",
    )
    assert [choice.text for choice in story.waiting.choices] == ["Открытый Гость", "Всегда"]
    story.advance()
    assert isinstance(story.waiting, Menu)
    story.choose(0)
    assert story.waiting.text == "да"


def test_menu_without_available_options_and_invalid_choice(write_game):
    with pytest.raises(BNEError, match="нет доступных вариантов"):
        story_at_start(
            write_game, 'label start:\n    menu:\n        "Нет" if False:\n            pass'
        )
    story = story_at_start(write_game, 'label start:\n    menu:\n        "Да":\n            return')
    for index in (-1, 1, True, "0"):
        with pytest.raises(BNEError, match="варианта"):
            story.choose(index)
    story.choose(0)
    with pytest.raises(BNEError, match="нет активного меню"):
        story.choose(0)


def test_cross_scene_call_and_local_label_precedence(write_game):
    root = write_game(
        {
            "intro": """\
label start:
    call room
    "обратно"
    call room.start
    "после другой сцены"
    return
label room:
    "локальная метка"
    return
""",
            "room": """\
label start:
    "другая сцена"
    return
""",
        }
    )
    story = Story(load_project(root))
    story.start()
    assert story.waiting.text == "локальная метка"
    assert story.frame.scene == "intro"
    story.advance()
    assert story.waiting.text == "обратно"
    story.advance()
    assert story.waiting.text == "другая сцена"
    assert story.frame.scene == "room"
    story.advance()
    assert story.waiting.text == "после другой сцены"
    story.advance()
    assert isinstance(story.waiting, Ended)
    assert not story.stack


def test_eof_returns_from_call(write_game):
    root = write_game(
        {
            "intro": 'label start:\n    call sub\n    "после"\n    return',
            "sub": 'label start:\n    "внутри"',
        }
    )
    story = Story(load_project(root))
    story.start()
    story.advance()
    assert story.waiting.text == "после"


@pytest.mark.parametrize("terminator", ["return", "end", "pass"])
def test_story_can_finish_without_dialogue(write_game, terminator):
    story = story_at_start(write_game, f"label start:\n    {terminator}")
    assert isinstance(story.waiting, Ended)


def test_visual_state_and_events(write_game):
    story = story_at_start(
        write_game,
        """\
label start:
    scene bg room with fade
    show eva calm at left with dissolve
    "a"
    show eva smile
    window hide
    pause
    hide eva with dissolve
    window show
    "b"
    show eva calm
    scene bg room
    "c"
    return
""",
    )
    assert story.background == "bg room"
    assert story.sprites["eva"].position == "left"
    assert [event.data["transition"] for event in story.drain_events()] == ["fade", "dissolve"]
    story.advance()
    assert isinstance(story.waiting, Pause)
    assert story.waiting.seconds is None
    assert story.sprites["eva"].image == "eva smile"
    assert story.sprites["eva"].position == "left"
    assert not story.window_visible
    story.advance()
    assert not story.sprites
    assert story.window_visible
    story.advance()
    assert not story.sprites


def test_audio_state_and_defaults(write_game):
    story = story_at_start(
        write_game,
        """\
label start:
    play music "audio/music.wav" fadein 0.5
    play sound "audio/music.wav" volume 0.7
    "a"
    stop sound
    stop music fadeout 1.2
    "b"
    return
""",
    )
    events = story.drain_events()
    assert story.music.loop is True
    assert story.music.volume == story.project.config.music_volume
    assert events[0].data["fade"] == 0.5
    assert events[1].data["channel"] == "sound"
    assert events[1].data["volume"] == 0.7
    story.advance()
    assert story.music is None
    assert [event.kind for event in story.drain_events()] == ["stop", "stop"]


def test_all_assignment_operators(write_game):
    story = story_at_start(
        write_game,
        """\
label start:
    $ score = 5
    $ score += 5
    $ score -= 2
    $ score *= 3
    $ score /= 2
    $ score //= 2
    $ score %= 4
    "[score]"
    return
""",
    )
    assert story.variables["score"] == 2.0
    assert story.waiting.text == "2.0"


def test_dynamic_character_name(write_game):
    story = story_at_start(
        write_game,
        """\
label start:
    $ name = "Лев"
    p "Моё имя — [name]."
    return
""",
        extra='define p = Character("[name]")',
    )
    assert story.waiting.speaker == "Лев"


def test_loop_and_call_guards(write_game):
    with pytest.raises(BNEError, match="10 000"):
        story_at_start(write_game, "label start:\n    jump start")
    with pytest.raises(BNEError, match="цепочка call"):
        story_at_start(write_game, "label start:\n    call start")


def test_all_demo_paths_and_checkpoint_roundtrips(demo_project):
    initial = Story(demo_project)
    initial.start()
    queue = [initial]
    finished = []
    seen_scenes = set()
    checkpoints = 0
    while queue:
        story = queue.pop()
        for _ in range(200):
            seen_scenes.add(story.frame.scene)
            data = pack(story)
            restored = unpack(demo_project, data)
            assert restored.waiting == story.waiting
            assert restored.variables == story.variables
            assert restored.sprites == story.sprites
            assert restored.stack == story.stack
            checkpoints += 1
            if isinstance(story.waiting, Menu):
                for index in range(len(story.waiting.choices)):
                    branch = unpack(demo_project, data)
                    branch.choose(index)
                    queue.append(branch)
                break
            if isinstance(story.waiting, Ended):
                finished.append(story)
                break
            story.advance()
        else:
            pytest.fail("Demo path never terminates")
    assert len(finished) == 15
    assert seen_scenes == {"arrival", "square", "finale"}
    assert checkpoints > 200
    assert {story.variables["player_name"] for story in finished} == {"Лев", "Саша", "Путник"}
    assert {story.variables["took_map"] for story in finished} == {True, False}
    assert any(story.variables["trust"] >= 2 for story in finished)
    assert any(story.variables["trust"] == 0 for story in finished)
