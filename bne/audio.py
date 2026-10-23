"""Optional pygame audio adapter. A missing sound device must not prevent reading."""

import pygame

from bne.model import Project
from bne.runtime import Event, Story


class Audio:
    def __init__(self, project: Project, muted: bool = False):
        self.project = project
        self.muted = muted
        self.available = False
        self.warning: str | None = None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        if not muted:
            self._initialize()

    def _initialize(self) -> None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.available = True
        except pygame.error:
            self.available = False
            self.warning = "Звуковое устройство недоступно. Игра продолжится без звука."

    def stop_all(self) -> None:
        if self.available:
            pygame.mixer.music.stop()
            pygame.mixer.stop()

    def sync(self, story: Story | None) -> None:
        self.stop_all()
        if story and story.music:
            music = story.music
            self.handle(
                Event(
                    "play",
                    {
                        "channel": "music",
                        "path": music.path,
                        "loop": music.loop,
                        "volume": music.volume,
                        "fade": 0.3,
                    },
                )
            )

    def toggle(self, story: Story | None) -> None:
        self.muted = not self.muted
        if self.muted:
            self.stop_all()
        else:
            if not self.available:
                self._initialize()
            self.sync(story)

    def handle(self, event: Event) -> None:
        if not self.available or self.muted or event.kind not in ("play", "stop"):
            return
        data = event.data
        try:
            if event.kind == "stop":
                milliseconds = round(data["fade"] * 1000)
                if data["channel"] == "music":
                    if milliseconds:
                        pygame.mixer.music.fadeout(milliseconds)
                    else:
                        pygame.mixer.music.stop()
                elif milliseconds:
                    pygame.mixer.fadeout(milliseconds)
                else:
                    pygame.mixer.stop()
            elif data["channel"] == "music":
                pygame.mixer.music.load(str(self.project.root / data["path"]))
                pygame.mixer.music.set_volume(data["volume"])
                pygame.mixer.music.play(
                    -1 if data["loop"] else 0, fade_ms=round(data["fade"] * 1000)
                )
            else:
                path = data["path"]
                if path not in self.sounds:
                    self.sounds[path] = pygame.mixer.Sound(str(self.project.root / path))
                sound = self.sounds[path]
                sound.set_volume(data["volume"])
                sound.play(fade_ms=round(data["fade"] * 1000))
        except (pygame.error, OSError) as error:
            self.warning = f"Не удалось воспроизвести аудио: {error}"
