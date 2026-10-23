from dataclasses import replace

import pygame
import pytest

from bne.app import App
from bne.errors import BNEError
from bne.render import wrap_text
from bne.runtime import Dialogue, Ended, Menu, Pause


@pytest.fixture
def app(demo_project, tmp_path):
    instance = App(demo_project, save_dir=tmp_path, mute=True)
    yield instance
    pygame.quit()


def key(app, code):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


def move_to_mira(app):
    app.new_game()
    while not (isinstance(app.story.waiting, Dialogue) and app.story.waiting.speaker == "Мира"):
        app.story.advance()
        app._sync()


def test_title_dialogue_choice_pause_and_history_render(app):
    app.draw(0)
    assert {button.action for button in app.renderer.buttons} == {"new", "load", "quit", "mute"}
    assert not next(button for button in app.renderer.buttons if button.action == "load").enabled
    move_to_mira(app)
    app.visible = 99999
    app.draw(1)
    assert app.renderer.canvas.get_size() == (1280, 720)
    assert app.renderer.last_stage is not None
    key(app, pygame.K_SPACE)
    assert isinstance(app.story.waiting, Menu)
    app.draw(1)
    assert (
        len([button for button in app.renderer.buttons if button.action.startswith("choose:")]) == 3
    )
    key(app, pygame.K_DOWN)
    key(app, pygame.K_RETURN)
    assert app.story.variables["player_name"] == "Саша"
    key(app, pygame.K_ESCAPE)
    assert app.mode == "pause"
    app.draw(0)
    assert any(button.action == "resume" for button in app.renderer.buttons)
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_h)
    assert app.mode == "history"
    app.draw(0)
    key(app, pygame.K_h)
    assert app.mode == "playing"


def test_typewriter_first_click_reveals_then_advances(app):
    move_to_mira(app)
    first = app.story.waiting
    assert app.visible == 0
    key(app, pygame.K_SPACE)
    assert app.story.waiting is first
    assert app.visible >= len(app.pages[0])
    key(app, pygame.K_SPACE)
    assert isinstance(app.story.waiting, Menu)


def test_timed_pause_and_overlay_does_not_advance(app):
    app.new_game()
    assert isinstance(app.story.waiting, Pause)
    key(app, pygame.K_ESCAPE)
    app.update(10)
    assert isinstance(app.story.waiting, Pause)
    key(app, pygame.K_ESCAPE)
    app.update(0.7)
    assert isinstance(app.story.waiting, Dialogue)


def test_quicksave_quickload_and_load_failure_leave_state_intact(app):
    move_to_mira(app)
    before = app.story
    key(app, pygame.K_F9)
    assert app.story is before
    assert "ещё не создано" in app.toast
    key(app, pygame.K_F5)
    assert app.saves.exists()
    key(app, pygame.K_SPACE)
    key(app, pygame.K_SPACE)
    assert isinstance(app.story.waiting, Menu)
    key(app, pygame.K_F9)
    assert app.story.waiting == before.history[-1]
    assert app.story is not before
    app.draw(1)


def test_input_coordinates_after_resize(app):
    app.draw(0)
    button = next(button for button in app.renderer.buttons if button.action == "new")
    app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=900, h=900))
    x, y, w, h = app._viewport()
    point = (
        round(x + button.rect.centerx * w / app.renderer.w),
        round(y + button.rect.centery * h / app.renderer.h),
    )
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
    assert app.mode == "playing"
    assert isinstance(app.story.waiting, Pause)


def test_long_text_pagination_and_long_word_wrapping(app):
    text = "Это длинная реплика. " * 100
    pages = app.renderer.dialogue_pages(text)
    assert len(pages) > 1
    assert all(len(page.split("\n")) <= 3 for page in pages)
    wrapped = wrap_text("x" * 1000, app.renderer.font(23), 200)
    assert "".join(wrapped) == "x" * 1000
    assert all(app.renderer.font(23).size(line)[0] <= 200 for line in wrapped)
    assert wrap_text("\n\n", app.renderer.font(23), 200) == ["", "", ""]


def test_playthrough_with_keyboard_and_end_screen(app):
    key(app, pygame.K_RETURN)
    for _ in range(200):
        app.draw(1)
        if isinstance(app.story.waiting, Ended):
            break
        if isinstance(app.story.waiting, Menu):
            key(app, pygame.K_1)
        else:
            app._next(skip=True)
    else:
        pytest.fail("The game never reaches its ending")
    assert any(button.action == "title" for button in app.renderer.buttons)
    key(app, pygame.K_RETURN)
    assert app.mode == "title"


def test_fullscreen_toggle_and_error_screen(app):
    key(app, pygame.K_F11)
    assert app.fullscreen
    key(app, pygame.K_F11)
    assert not app.fullscreen
    app._fail(BNEError("Ошибка тестового сценария"))
    app.draw(0)
    assert app.mode == "error"
    key(app, pygame.K_ESCAPE)
    assert app.mode == "title"


def test_minimum_logical_resolution(demo_project, tmp_path):
    project = replace(demo_project, config=replace(demo_project.config, width=640, height=360))
    app = App(project, save_dir=tmp_path, mute=True)
    try:
        app.draw(0)
        assert all(
            app.renderer.canvas.get_rect().contains(button.rect) for button in app.renderer.buttons
        )
        move_to_mira(app)
        app.visible = 99999
        app.draw(1)
        key(app, pygame.K_ESCAPE)
        app.draw(0)
        assert all(
            app.renderer.canvas.get_rect().contains(button.rect) for button in app.renderer.buttons
        )
    finally:
        pygame.quit()


def test_dummy_audio_device_can_play_music_and_effects(demo_project, tmp_path):
    app = App(demo_project, save_dir=tmp_path, mute=False)
    try:
        app.new_game()
        assert app.audio.available
        assert pygame.mixer.music.get_busy()
        from bne.runtime import Event

        app.audio.handle(
            Event("play", {"channel": "sound", "path": "audio/chime.wav", "volume": 0.5, "fade": 0})
        )
        assert pygame.mixer.get_busy()
        app.audio.toggle(app.story)
        assert app.audio.muted
        assert not pygame.mixer.music.get_busy()
        app.audio.toggle(app.story)
        assert not app.audio.muted
        assert pygame.mixer.music.get_busy()
    finally:
        pygame.quit()


def test_event_loop_exits_cleanly(app):
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert app.run() == 0
    assert not pygame.display.get_init()


def test_bad_image_can_show_error_without_loading_it_again(app, monkeypatch):
    move_to_mira(app)

    def fail_load(*args):
        raise BNEError("Повреждённый PNG")

    monkeypatch.setattr(app.renderer, "_load", fail_load)
    with pytest.raises(BNEError) as error:
        app.draw(0)
    app._fail(error.value)
    app.draw(0)
    assert app.mode == "error"
    app.focus = None
    key(app, pygame.K_RETURN)
    assert app.mode == "title"


def test_missing_audio_device_is_nonfatal(demo_project, monkeypatch):
    from bne.audio import Audio
    from bne.runtime import Event

    pygame.mixer.quit()

    def unavailable():
        raise pygame.error("No audio device")

    monkeypatch.setattr(pygame.mixer, "init", unavailable)
    audio = Audio(demo_project)
    assert not audio.available
    assert "без звука" in audio.warning
    audio.handle(Event("play", {"channel": "music"}))


def test_fullscreen_failure_keeps_current_window(app, monkeypatch):
    before = app.display

    def unavailable(*args):
        raise pygame.error("Unsupported video mode")

    monkeypatch.setattr(pygame.display, "set_mode", unavailable)
    key(app, pygame.K_F11)
    assert not app.fullscreen
    assert app.display is before
    assert "Не удалось" in app.toast


def test_page_advance_does_not_advance_script(app):
    move_to_mira(app)
    app.story.waiting = Dialogue("Мира", "#AABBCC", "Очень длинная реплика. " * 100)
    app._sync()
    before = app.story.frame
    assert len(app.pages) > 1
    key(app, pygame.K_SPACE)
    key(app, pygame.K_SPACE)
    assert app.page == 1
    assert app.story.frame == before
    assert app.visible == 0


def test_long_choice_menu_scrolls_to_keyboard_selection(app):
    from bne.runtime import Choice

    move_to_mira(app)
    app.story.waiting = Menu(tuple(Choice("Длинный вариант выбора. " * 20, 0) for _ in range(9)))
    app._sync()
    app.draw(0)
    assert app.renderer.menu_max_scroll > 0
    for _ in range(8):
        key(app, pygame.K_DOWN)
    app.draw(0)
    assert app.selected == 8
    assert app.menu_scroll > 0
    assert any(button.action == "choose:8" for button in app.renderer.buttons)
