"""Desktop host for the renderer-independent BNE story runtime."""

import sys
from pathlib import Path

import pygame

from bne.audio import Audio
from bne.errors import BNEError
from bne.model import Project
from bne.render import Renderer
from bne.runtime import Dialogue, Ended, Menu, Pause, Story
from bne.saves import SaveStore


class App:
    def __init__(
        self,
        project: Project,
        save_dir: Path | None = None,
        mute: bool = False,
        fullscreen: bool = False,
    ):
        self.project = project
        try:
            pygame.display.init()
            pygame.font.init()
            self.fullscreen = fullscreen
            self.windowed_size = (project.config.width, project.config.height)
            flags = pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE
            self.display = pygame.display.set_mode(self.windowed_size, flags)
            pygame.display.set_caption(f"{project.config.title} — Berl Novella Engine")
            self.renderer = Renderer(project)
        except pygame.error as error:
            pygame.quit()
            raise BNEError(f"Не удалось открыть окно: {error}") from error
        self.audio = Audio(project, mute)
        self.saves = SaveStore(project, save_dir)
        self.story: Story | None = None
        self.running = True
        self.mode = "title"
        self.return_mode = "playing"
        self.focus: str | None = "new"
        self.wait_token = None
        self.wait_elapsed = 0.0
        self.visible = 0.0
        self.pages = [""]
        self.page = 0
        self.selected = 0
        self.menu_scroll = 0.0
        self.history_scroll = 0.0
        self.skip_elapsed = 0.0
        self.toast = self.audio.warning or ""
        self.toast_time = 5.0 if self.toast else 0.0
        self.audio.warning = None
        self.error = ""

    def run(self) -> int:
        clock = pygame.time.Clock()
        try:
            # Populate hit regions before the first input event.
            self.draw(0)
            pygame.display.flip()
            while self.running:
                dt = min(0.1, clock.tick(60) / 1000)
                for event in pygame.event.get():
                    try:
                        self.handle_event(event)
                    except BNEError as error:
                        self._fail(error)
                try:
                    self.update(dt)
                    self.draw(dt)
                except BNEError as error:
                    self._fail(error)
                    self.draw(0)
                pygame.display.flip()
        finally:
            pygame.quit()
        return 0

    def _notify(self, message: str) -> None:
        self.toast, self.toast_time = message, 4.0

    def _fail(self, error: BNEError) -> None:
        self.error = str(error)
        print(f"BNE: {error}", file=sys.stderr)
        self.mode = "error"
        self.audio.stop_all()

    def new_game(self) -> None:
        candidate = Story(self.project)
        candidate.start()
        self.audio.stop_all()
        self.story = candidate
        self.mode = "playing"
        self.wait_token = None
        self.focus = None
        self._sync()

    def _sync(self) -> None:
        if self.story is None:
            return
        events = self.story.drain_events()
        transitions = [event.data["transition"] for event in events if event.kind == "visual"]
        if "fade" in transitions:
            self.renderer.begin_transition("fade")
        elif "dissolve" in transitions:
            self.renderer.begin_transition("dissolve")
        for event in events:
            self.audio.handle(event)
        if self.story.waiting is not self.wait_token:
            self.wait_token = self.story.waiting
            self.wait_elapsed = 0.0
            self.visible = 0.0
            self.page = 0
            self.selected = 0
            self.menu_scroll = 0.0
            if isinstance(self.story.waiting, Dialogue):
                self.pages = self.renderer.dialogue_pages(self.story.waiting.text)

    def update(self, dt: float) -> None:
        self.toast_time = max(0, self.toast_time - dt)
        if self.audio.warning:
            self._notify(self.audio.warning)
            self.audio.warning = None
        if self.mode != "playing" or self.story is None:
            return
        self._sync()
        self.wait_elapsed += dt
        waiting = self.story.waiting
        if isinstance(waiting, Pause) and waiting.seconds is not None:
            if self.wait_elapsed >= waiting.seconds:
                self.story.advance()
                self._sync()
        elif isinstance(waiting, Dialogue):
            speed = self.project.config.text_speed
            self.visible = len(self.pages[self.page]) if speed == 0 else self.visible + dt * speed
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]:
                self.skip_elapsed += dt
                if self.skip_elapsed >= 0.08:
                    self.skip_elapsed = 0.0
                    self._next(skip=True)
            else:
                self.skip_elapsed = 0.0

    def _next(self, skip: bool = False) -> None:
        if self.story is None:
            return
        waiting = self.story.waiting
        if isinstance(waiting, Dialogue):
            text = self.pages[self.page]
            if not skip and self.visible < len(text):
                self.visible = len(text)
                return
            if self.page + 1 < len(self.pages):
                self.page += 1
                self.visible = 0.0
                self.wait_elapsed = 0.0
                return
            self.story.advance()
        elif isinstance(waiting, Pause):
            self.story.advance()
        elif isinstance(waiting, Ended):
            self.action("title")
        self._sync()

    def action(self, action: str) -> None:
        if action == "new":
            self.new_game()
        elif action == "quit":
            self.running = False
        elif action == "title":
            self.audio.stop_all()
            self.mode, self.focus = "title", "new"
            self.renderer.old_stage = None
        elif action == "pause" and self.story:
            self.mode, self.focus = "pause", "resume"
        elif action == "resume" and self.story:
            self.mode, self.focus = "playing", None
        elif action == "save" and self.story:
            try:
                self.saves.save(self.story)
                self._notify("История сохранена · F9 — вернуться к этому моменту")
            except BNEError as error:
                self._notify(str(error))
        elif action == "load":
            try:
                candidate = self.saves.load()
            except BNEError as error:
                self._notify(str(error))
                return
            self.story = candidate
            self.wait_token = None
            self.mode, self.focus = "playing", None
            self.audio.sync(self.story)
            self.renderer.begin_transition("fade")
            self._sync()
            self._notify("Сохранение загружено")
        elif action == "mute":
            self.audio.toggle(self.story if self.mode != "title" else None)
            self._notify("Звук выключен" if self.audio.muted else "Звук включён")
        elif action == "history" and self.story:
            self.return_mode = self.mode
            self.mode = "history"
            self.history_scroll = 0.0
        elif action == "history_close":
            self.mode = self.return_mode
        elif action.startswith("choose:") and self.story and self.mode == "playing":
            self.story.choose(int(action.split(":")[1]))
            self._sync()

    def _toggle_fullscreen(self) -> None:
        was_fullscreen = self.fullscreen
        try:
            if not was_fullscreen:
                self.windowed_size = self.display.get_size()
                self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
            self.fullscreen = not was_fullscreen
        except pygame.error as error:
            self._notify(f"Не удалось переключить экран: {error}")

    def _viewport(self) -> tuple[int, int, int, int]:
        width, height = self.display.get_size()
        factor = min(width / self.renderer.w, height / self.renderer.h)
        w, h = max(1, round(self.renderer.w * factor)), max(1, round(self.renderer.h * factor))
        return (width - w) // 2, (height - h) // 2, w, h

    def logical_mouse(self, position: tuple[int, int]) -> tuple[int, int]:
        x, y, w, h = self._viewport()
        return (
            round((position[0] - x) * self.renderer.w / w),
            round((position[1] - y) * self.renderer.h / h),
        )

    def _focus_next(self, direction: int) -> None:
        buttons = [button for button in self.renderer.buttons if button.enabled]
        if not buttons:
            return
        actions = [button.action for button in buttons]
        current = actions.index(self.focus) if self.focus in actions else -1
        self.focus = actions[(current + direction) % len(actions)]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self.display = pygame.display.set_mode(
                (max(320, event.w), max(180, event.h)), pygame.RESIZABLE
            )
        elif event.type == pygame.MOUSEMOTION:
            self.focus = None
        elif event.type == pygame.MOUSEWHEEL:
            if self.mode == "history":
                self.history_scroll = max(
                    0,
                    min(
                        self.renderer.history_max_scroll,
                        self.history_scroll + event.y * self.renderer.px(85),
                    ),
                )
            elif self.mode == "playing" and self.story and isinstance(self.story.waiting, Menu):
                self.menu_scroll = max(
                    0,
                    min(
                        self.renderer.menu_max_scroll,
                        self.menu_scroll - event.y * self.renderer.px(65),
                    ),
                )
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            position = self.logical_mouse(event.pos)
            if not self.renderer.canvas.get_rect().collidepoint(position):
                return
            for button in reversed(self.renderer.buttons):
                if button.enabled and button.rect.collidepoint(position):
                    self.action(button.action)
                    return
            if self.mode == "playing":
                self._next()
        elif event.type == pygame.KEYDOWN:
            self._key(event.key)

    def _key(self, key: int) -> None:
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return
        if key == pygame.K_m:
            self.action("mute")
            return
        if key == pygame.K_F5 and self.mode not in ("title", "error"):
            self.action("save")
            return
        if key == pygame.K_F9:
            self.action("load")
            return
        if key in (pygame.K_ESCAPE, pygame.K_h):
            if self.mode == "history":
                self.action("history_close")
            elif key == pygame.K_h and self.mode == "playing":
                self.action("history")
            elif key == pygame.K_ESCAPE:
                if self.mode == "playing":
                    self.action("pause")
                elif self.mode == "pause":
                    self.action("resume")
                elif self.mode == "error":
                    self.action("title")
                elif self.mode == "title":
                    self.running = False
            return
        if self.mode == "history":
            if key in (pygame.K_UP, pygame.K_DOWN):
                delta = 1 if key == pygame.K_UP else -1
                self.history_scroll = max(
                    0,
                    min(
                        self.renderer.history_max_scroll,
                        self.history_scroll + delta * self.renderer.px(85),
                    ),
                )
            return
        if self.mode == "playing" and self.story:
            waiting = self.story.waiting
            if isinstance(waiting, Menu):
                if key in (pygame.K_UP, pygame.K_DOWN):
                    self.selected = (self.selected + (1 if key == pygame.K_DOWN else -1)) % len(
                        waiting.choices
                    )
                    self.menu_scroll = self.renderer.selected_scroll(
                        waiting, self.selected, self.menu_scroll
                    )
                elif pygame.K_1 <= key <= pygame.K_9:
                    index = key - pygame.K_1
                    if index < len(waiting.choices):
                        self.action(f"choose:{index}")
                elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.action(f"choose:{self.selected}")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._next()
            return
        if key in (pygame.K_TAB, pygame.K_DOWN, pygame.K_UP):
            self._focus_next(-1 if key == pygame.K_UP else 1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.action(self.focus or {"title": "new", "error": "title"}.get(self.mode, "resume"))

    def draw(self, dt: float) -> None:
        renderer = self.renderer
        renderer.begin_frame()
        mouse = self.logical_mouse(pygame.mouse.get_pos())
        if self.mode == "title":
            renderer.draw_title(self.saves.exists(), self.audio.muted, mouse, self.focus)
        elif self.mode == "error":
            renderer.draw_stage(None, dt)
            renderer.draw_error(self.error, mouse)
        else:
            renderer.draw_stage(self.story, dt)
            if self.mode == "history" and self.story:
                renderer.draw_history(self.story.history, self.history_scroll, mouse)
            elif self.mode == "pause":
                renderer.draw_pause(mouse, self.focus, self.audio.muted)
            elif self.story:
                waiting = self.story.waiting
                if isinstance(waiting, Dialogue) and self.story.window_visible:
                    renderer.draw_dialogue(
                        waiting,
                        self.pages[self.page],
                        int(self.visible),
                        self.page,
                        len(self.pages),
                        self.wait_elapsed,
                    )
                elif isinstance(waiting, Menu):
                    renderer.draw_choices(waiting, self.selected, self.menu_scroll, mouse)
                elif isinstance(waiting, Pause) and waiting.seconds is None:
                    renderer.text(
                        "Нажмите Space или щёлкните, чтобы продолжить.",
                        renderer.px(49),
                        renderer.h - renderer.px(85),
                        15,
                    )
                elif isinstance(waiting, Ended):
                    renderer.draw_end(mouse, self.focus)
                renderer.draw_toolbar(self.story, mouse)
        if self.toast_time > 0:
            renderer.draw_toast(self.toast)
        x, y, width, height = self._viewport()
        self.display.fill((4, 10, 16))
        canvas = renderer.canvas
        if (width, height) != canvas.get_size():
            canvas = pygame.transform.smoothscale(canvas, (width, height))
        self.display.blit(canvas, (x, y))
