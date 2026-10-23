"""Source-aware errors shared by the compiler, runtime and save system."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    path: Path
    line: int = 1

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


class BNEError(Exception):
    """An error safe to show to the game author instead of a Python traceback."""

    def __init__(self, message: str, source: Source | None = None):
        self.message = message
        self.source = source
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.source}: {self.message}" if self.source else self.message
