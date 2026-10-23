"""Pygame presentation: artwork, transitions, text layout and mouse hit regions."""

import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from bne import __version__
from bne.errors import BNEError
from bne.model import Project
from bne.runtime import Dialogue, Menu, Story

INK = (237, 241, 239)
MUTED = (157, 178, 184)
ACCENT = (158, 228, 210)
GOLD = (235, 201, 154)
DARK = (13, 25, 35)
BORDER = (71, 99, 109)


@dataclass(frozen=True)
class Button:
    rect: pygame.Rect
    action: str
    enabled: bool = True


def wrap_text(text: str, font: pygame.font.Font, width: int) -> list[str]:
    """Wrap explicit newlines and long words without losing any non-whitespace text."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if font.size(candidate)[0] <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            if font.size(word)[0] <= width:
                current = word
                continue
            for char in word:
                if current and font.size(current + char)[0] > width:
                    lines.append(current)
                    current = ""
                current += char
        lines.append(current)
    return lines or [""]


class Renderer:
    def __init__(self, project: Project):
        self.project = project
        self.w, self.h = project.config.width, project.config.height
        self.scale = min(self.w / 1280, self.h / 720)
        self.canvas = pygame.Surface((self.w, self.h)).convert()
        self.buttons: list[Button] = []
        self.fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self.originals: dict[Path, pygame.Surface] = {}
        self.backgrounds: dict[str, pygame.Surface] = {}
        self.sprites: dict[str, pygame.Surface] = {}
        self.last_stage: pygame.Surface | None = None
        self.old_stage: pygame.Surface | None = None
        self.transition = "none"
        self.transition_time = 0.0
        self.transition_duration = 0.0
        self.menu_max_scroll = 0.0
        self.history_max_scroll = 0.0
        self.font_path = str(project.root / project.config.font) if project.config.font else None
        self.fallback = self._gradient((27, 49, 64), (12, 23, 33))

    def px(self, value: float) -> int:
        return round(value * self.scale)

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in self.fonts:
            try:
                font = pygame.font.Font(self.font_path, max(10, self.px(size)))
                font.set_bold(bold)
                self.fonts[key] = font
            except (pygame.error, OSError) as error:
                raise BNEError(f"Не удалось загрузить шрифт: {error}") from error
        return self.fonts[key]

    def text(
        self,
        text: str,
        x: int,
        y: int,
        size: int = 20,
        color=INK,
        bold: bool = False,
        target: pygame.Surface | None = None,
    ) -> None:
        (target if target is not None else self.canvas).blit(
            self.font(size, bold).render(text, True, color), (x, y)
        )

    def _gradient(self, top: tuple, bottom: tuple) -> pygame.Surface:
        surface = pygame.Surface((self.w, self.h)).convert()
        for y in range(self.h):
            ratio = y / max(1, self.h - 1)
            color = tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom, strict=True))
            pygame.draw.line(surface, color, (0, y), (self.w, y))
        return surface

    def _load(self, alias: str) -> pygame.Surface:
        path = self.project.images[alias]
        if path not in self.originals:
            try:
                self.originals[path] = pygame.image.load(str(path)).convert_alpha()
            except (pygame.error, OSError) as error:
                raise BNEError(f"Не удалось открыть изображение {path.name}: {error}") from error
        return self.originals[path]

    def background(self, alias: str | None) -> pygame.Surface:
        if alias is None:
            return self.fallback
        if alias not in self.backgrounds:
            original = self._load(alias)
            factor = max(self.w / original.get_width(), self.h / original.get_height())
            size = (
                max(self.w, round(original.get_width() * factor)),
                max(self.h, round(original.get_height() * factor)),
            )
            scaled = pygame.transform.smoothscale(original, size)
            surface = pygame.Surface((self.w, self.h)).convert()
            surface.blit(scaled, ((self.w - size[0]) // 2, (self.h - size[1]) // 2))
            self.backgrounds[alias] = surface
        return self.backgrounds[alias]

    def sprite(self, alias: str) -> pygame.Surface:
        if alias not in self.sprites:
            original = self._load(alias)
            factor = min(
                self.h * 0.91 / original.get_height(), self.w * 0.43 / original.get_width()
            )
            self.sprites[alias] = pygame.transform.smoothscale(
                original,
                (
                    max(1, round(original.get_width() * factor)),
                    max(1, round(original.get_height() * factor)),
                ),
            )
        return self.sprites[alias]

    def begin_frame(self) -> None:
        self.buttons.clear()

    def panel(self, rect: pygame.Rect, fill=(*DARK, 236), border=BORDER, radius: int = 14) -> None:
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, fill, layer.get_rect(), border_radius=self.px(radius))
        if border:
            pygame.draw.rect(layer, border, layer.get_rect(), 1, border_radius=self.px(radius))
        self.canvas.blit(layer, rect)

    def shade(self, opacity: int = 160) -> None:
        layer = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        layer.fill((5, 13, 22, opacity))
        self.canvas.blit(layer, (0, 0))

    def button(
        self,
        rect: pygame.Rect,
        label: str,
        action: str,
        mouse: tuple,
        focus: str | None = None,
        primary: bool = False,
        enabled: bool = True,
        quiet: bool = False,
        size: int = 18,
    ) -> None:
        active = enabled and (rect.collidepoint(mouse) or action == focus)
        if primary:
            self.panel(rect, (*ACCENT, 255) if enabled else (55, 74, 78, 220), None, 8)
            color = DARK if enabled else MUTED
        else:
            self.panel(
                rect,
                (28, 52, 59, 240) if active else (*DARK, 70 if quiet else 210),
                ACCENT if active else (None if quiet else BORDER),
                8,
            )
            color = ACCENT if active else INK if enabled else (94, 116, 125)
        surface = self.font(size).render(label, True, color)
        self.canvas.blit(surface, surface.get_rect(center=rect.center))
        self.buttons.append(Button(rect, action, enabled))

    def begin_transition(self, kind: str) -> None:
        if kind == "none":
            return
        self.old_stage = (
            self.last_stage.copy() if self.last_stage is not None else self.fallback.copy()
        )
        self.transition = kind
        self.transition_duration = 0.65 if kind == "fade" else 0.4
        self.transition_time = 0.0

    @property
    def transitioning(self) -> bool:
        return self.old_stage is not None

    def draw_stage(self, story: Story | None, dt: float = 0.0) -> None:
        if story is None:
            self.canvas.blit(self.fallback, (0, 0))
            return
        stage = self.background(story.background).copy()
        for sprite in story.sprites.values():
            image = self.sprite(sprite.image)
            center = {"left": 0.23, "center": 0.5, "right": 0.77}[sprite.position] * self.w
            stage.blit(
                image,
                (round(center - image.get_width() / 2), self.h - image.get_height() + self.px(28)),
            )
        self.last_stage = stage
        if self.old_stage is None:
            self.canvas.blit(stage, (0, 0))
            return
        self.transition_time += dt
        ratio = min(1.0, self.transition_time / self.transition_duration)
        if self.transition == "fade":
            self.canvas.fill((5, 11, 18))
            image = self.old_stage if ratio < 0.5 else stage
            opacity = 1 - ratio * 2 if ratio < 0.5 else ratio * 2 - 1
            layer = image.copy()
            layer.set_alpha(round(255 * opacity))
            self.canvas.blit(layer, (0, 0))
        else:
            self.canvas.blit(self.old_stage, (0, 0))
            layer = stage.copy()
            layer.set_alpha(round(255 * ratio))
            self.canvas.blit(layer, (0, 0))
        if ratio >= 1:
            self.old_stage = None

    def draw_title(self, has_save: bool, muted: bool, mouse: tuple, focus: str | None) -> None:
        alias = next((name for name in self.project.images if name.startswith("bg ")), None)
        self.canvas.blit(self.background(alias), (0, 0))
        self.last_stage = self.canvas.copy()
        gradient = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for x in range(self.w):
            alpha = round(230 * (1 - x / self.w) ** 0.6)
            pygame.draw.line(gradient, (6, 19, 29, alpha), (x, 0), (x, self.h))
        self.canvas.blit(gradient, (0, 0))
        x = self.px(82)
        self.text("B E R L   /   N O V E L L A   E N G I N E", x, self.px(40), 13, ACCENT)
        self.text("И Н Т Е Р А К Т И В Н А Я   И С Т О Р И Я", x, self.px(156), 13, GOLD)
        title_font = 64
        title_lines = wrap_text(self.project.config.title, self.font(title_font), self.px(650))
        while len(title_lines) > 2 and title_font > 32:
            title_font -= 2
            title_lines = wrap_text(self.project.config.title, self.font(title_font), self.px(650))
        y = self.px(188)
        for line in title_lines:
            self.text(line, x - self.px(3), y, title_font, INK)
            y += self.px(title_font + 12)
        self.text("История начинается с одного выбора.", x, y + self.px(17), 19, MUTED)
        button_y = max(y + self.px(78), self.px(414))
        button_w, button_h, gap = self.px(300), self.px(51), self.px(13)
        for index, (label, action, enabled) in enumerate(
            [
                ("Начать историю  →", "new", True),
                ("Продолжить", "load", has_save),
                ("Выйти", "quit", True),
            ]
        ):
            rect = pygame.Rect(x, button_y + index * (button_h + gap), button_w, button_h)
            self.button(rect, label, action, mouse, focus, primary=index == 0, enabled=enabled)
        self.text(
            f"BNE {__version__}  /  СЦЕН: {len(self.project.scripts)}",
            x,
            self.h - self.px(54),
            12,
            MUTED,
        )
        self.text(
            "Enter — начать     F11 — полный экран     M — звук", x, self.h - self.px(31), 12, MUTED
        )
        badge = pygame.Rect(self.w - self.px(150), self.px(32), self.px(112), self.px(34))
        self.button(
            badge, "Звук: выкл" if muted else "Звук: вкл", "mute", mouse, focus, quiet=True, size=13
        )

    def dialogue_pages(self, text: str) -> list[str]:
        lines = wrap_text(text, self.font(23), self.w - self.px(164))
        return ["\n".join(lines[index : index + 3]) for index in range(0, len(lines), 3)]

    def draw_dialogue(
        self,
        dialogue: Dialogue,
        page: str,
        visible: int,
        page_number: int,
        page_count: int,
        elapsed: float,
    ) -> None:
        rect = pygame.Rect(self.px(48), self.h - self.px(224), self.w - self.px(96), self.px(174))
        self.panel(rect, (*DARK, 236), BORDER, 12)
        pygame.draw.line(
            self.canvas,
            ACCENT,
            (rect.x + self.px(28), rect.y),
            (rect.x + self.px(92), rect.y),
            self.px(2),
        )
        if dialogue.speaker:
            self.text(
                dialogue.speaker,
                rect.x + self.px(30),
                rect.y + self.px(17),
                17,
                pygame.Color(dialogue.color),
                True,
            )
        text_y = rect.y + self.px(51 if dialogue.speaker else 30)
        revealed = page[:visible]
        for index, line in enumerate(revealed.split("\n")):
            self.text(line, rect.x + self.px(30), text_y + index * self.px(33), 23)
        if page_count > 1:
            self.text(
                f"{page_number + 1}/{page_count}",
                rect.right - self.px(83),
                rect.bottom - self.px(30),
                12,
                MUTED,
            )
        if visible >= len(page):
            x, y = rect.right - self.px(30), rect.bottom - self.px(22)
            offset = self.px(2 * math.sin(elapsed * 4))
            pygame.draw.polygon(
                self.canvas,
                ACCENT,
                [
                    (x - self.px(5), y + offset),
                    (x + self.px(5), y + offset),
                    (x, y + self.px(5) + offset),
                ],
            )

    def choice_layout(self, menu: Menu) -> tuple[pygame.Rect, list[tuple[pygame.Rect, list[str]]]]:
        viewport = pygame.Rect(
            self.px(100), self.px(110), self.w - self.px(200), self.h - self.px(210)
        )
        width = min(self.px(850), viewport.w)
        items = []
        y = 0
        for choice in menu.choices:
            lines = wrap_text(choice.text, self.font(21), width - self.px(100))
            height = max(self.px(60), len(lines) * self.px(29) + self.px(24))
            items.append((pygame.Rect((self.w - width) // 2, y, width, height), lines))
            y += height + self.px(12)
        total = y - self.px(12)
        self.menu_max_scroll = max(0, total - viewport.h)
        start = viewport.y + max(0, (viewport.h - total) // 2)
        return viewport, [(rect.move(0, start), lines) for rect, lines in items]

    def selected_scroll(self, menu: Menu, selected: int, scroll: float) -> float:
        viewport, items = self.choice_layout(menu)
        rect = items[selected][0].move(0, -round(scroll))
        if rect.top < viewport.top:
            scroll -= viewport.top - rect.top
        elif rect.bottom > viewport.bottom:
            scroll += min(rect.bottom - viewport.bottom, rect.top - viewport.top)
        return max(0, min(self.menu_max_scroll, scroll))

    def draw_choices(self, menu: Menu, selected: int, scroll: float, mouse: tuple) -> None:
        self.shade(145)
        self.text("В А Ш   В Ы Б О Р", self.px(100), self.px(64), 15, GOLD)
        viewport, items = self.choice_layout(menu)
        scroll = max(0, min(self.menu_max_scroll, scroll))
        old_clip = self.canvas.get_clip()
        self.canvas.set_clip(viewport)
        for index, (rect, lines) in enumerate(items):
            rect = rect.move(0, -round(scroll))
            hit = rect.clip(viewport)
            if hit.height == 0:
                continue
            active = index == selected or hit.collidepoint(mouse)
            self.panel(
                rect,
                (27, 54, 60, 248) if active else (*DARK, 241),
                ACCENT if active else BORDER,
                10,
            )
            self.text(
                f"0{index + 1}",
                rect.x + self.px(21),
                rect.y + self.px(19),
                15,
                ACCENT if active else MUTED,
            )
            for line_index, line in enumerate(lines):
                self.text(line, rect.x + self.px(66), rect.y + self.px(14 + line_index * 29), 21)
            self.buttons.append(Button(hit, f"choose:{index}"))
        self.canvas.set_clip(old_clip)
        hint = "↑ ↓ / 1–9 — выбор     Enter — подтвердить"
        if self.menu_max_scroll:
            hint += "     Колесо — прокрутка"
        self.text(hint, self.px(100), self.h - self.px(76), 13, MUTED)

    def draw_toolbar(self, story: Story, mouse: tuple) -> None:
        self.text(f"B N E   /   {story.frame.scene.upper()}", self.px(49), self.px(26), 12, INK)
        labels = [
            ("История · H", "history"),
            ("Сохранить · F5", "save"),
            ("Загрузить · F9", "load"),
            ("Меню · Esc", "pause"),
        ]
        width = self.px(148)
        x = self.w - self.px(48) - width * len(labels)
        for index, (label, action) in enumerate(labels):
            rect = pygame.Rect(x + index * width, self.h - self.px(41), width, self.px(32))
            self.button(rect, label, action, mouse, quiet=True, size=12)

    def draw_pause(self, mouse: tuple, focus: str | None, muted: bool) -> None:
        self.shade(190)
        width = self.px(440)
        rect = pygame.Rect((self.w - width) // 2, self.px(104), width, self.px(518))
        self.panel(rect, (*DARK, 246), BORDER, 16)
        self.text("Пауза", rect.x + self.px(43), rect.y + self.px(30), 32)
        self.text("История подождёт.", rect.x + self.px(45), rect.y + self.px(77), 15, MUTED)
        options = [
            ("Продолжить", "resume"),
            ("Сохранить · F5", "save"),
            ("Загрузить · F9", "load"),
            ("Звук: выключен" if muted else "Звук: включён", "mute"),
            ("Главное меню", "title"),
            ("Выйти из игры", "quit"),
        ]
        for index, (label, action) in enumerate(options):
            button = pygame.Rect(
                rect.x + self.px(40),
                rect.y + self.px(121 + index * 59),
                rect.w - self.px(80),
                self.px(46),
            )
            self.button(button, label, action, mouse, focus, primary=index == 0, size=17)

    def draw_history(self, history: list[Dialogue], scroll: float, mouse: tuple) -> None:
        self.shade(235)
        self.text("История диалогов", self.px(100), self.px(47), 30)
        self.text("Колесо / ↑ ↓ — прокрутка", self.px(100), self.px(92), 13, MUTED)
        self.button(
            pygame.Rect(self.w - self.px(230), self.px(49), self.px(130), self.px(38)),
            "Закрыть · H",
            "history_close",
            mouse,
            quiet=True,
            size=14,
        )
        viewport = pygame.Rect(
            self.px(100), self.px(142), self.w - self.px(200), self.h - self.px(200)
        )
        entries = []
        y = 0
        for entry in history:
            lines = wrap_text(entry.text, self.font(20), viewport.w - self.px(32))
            entries.append((y, entry, lines))
            y += self.px(35 + len(lines) * 29 + 23)
        self.history_max_scroll = max(0, y - viewport.h)
        offset = max(0, y - viewport.h) - min(scroll, self.history_max_scroll)
        old_clip = self.canvas.get_clip()
        self.canvas.set_clip(viewport)
        for y, entry, lines in entries:
            top = viewport.y + y - round(offset)
            bottom = top + self.px(35 + len(lines) * 29)
            if bottom < viewport.top or top > viewport.bottom:
                continue
            self.text(entry.speaker or "Рассказчик", viewport.x, top, 14, pygame.Color(entry.color))
            for index, line in enumerate(lines):
                self.text(line, viewport.x, top + self.px(28 + index * 29), 20)
        self.canvas.set_clip(old_clip)
        if not history:
            self.text("Здесь появятся прочитанные реплики.", viewport.x, viewport.y, 20, MUTED)

    def draw_end(self, mouse: tuple, focus: str | None) -> None:
        self.shade(170)
        self.text("К О Н Е Ц   И С Т О Р И И", self.px(100), self.px(230), 17, GOLD)
        self.text("Спасибо, что остались.", self.px(96), self.px(273), 43)
        self.text(
            "Каждый новый выбор может привести другой дорогой.",
            self.px(100),
            self.px(347),
            18,
            MUTED,
        )
        self.button(
            pygame.Rect(self.px(100), self.px(414), self.px(310), self.px(52)),
            "В главное меню  →",
            "title",
            mouse,
            focus,
            primary=True,
        )

    def draw_error(self, message: str, mouse: tuple) -> None:
        self.shade(235)
        self.text("Ошибка сценария", self.px(80), self.px(90), 32, GOLD)
        lines = wrap_text(message, self.font(19), self.w - self.px(160))
        for index, line in enumerate(lines[:13]):
            self.text(line, self.px(80), self.px(160 + index * 30), 19)
        self.button(
            pygame.Rect(self.px(80), self.h - self.px(100), self.px(300), self.px(50)),
            "В главное меню",
            "title",
            mouse,
            primary=True,
        )

    def draw_toast(self, message: str) -> None:
        lines = wrap_text(message, self.font(14), self.w - self.px(200))
        width = min(
            self.w - self.px(100), max(self.font(14).size(line)[0] for line in lines) + self.px(40)
        )
        height = self.px(25 + len(lines) * 22)
        rect = pygame.Rect((self.w - width) // 2, self.px(20), width, height)
        self.panel(rect, (*DARK, 249), ACCENT, 9)
        for index, line in enumerate(lines):
            self.text(line, rect.x + self.px(20), rect.y + self.px(12 + index * 22), 14, INK)
