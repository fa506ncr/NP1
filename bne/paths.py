"""All author-controlled asset paths stay inside the game directory."""

from pathlib import Path

from bne.errors import BNEError, Source


def game_file(root: Path, name: str, source: Source | None = None) -> Path:
    if (
        not name
        or Path(name).is_absolute()
        or any(char in name for char in ("\\", "\0", "\r", "\n"))
    ):
        raise BNEError("Укажите относительный путь внутри game/ с разделителем /.", source)
    try:
        path = (root / name).resolve()
        inside = path.is_relative_to(root.resolve())
        exists = path.is_file()
    except (OSError, ValueError, RuntimeError) as error:
        raise BNEError(f"Некорректный путь к ресурсу: {name}", source) from error
    if not inside:
        raise BNEError(f"Путь выходит за пределы папки игры: {name}", source)
    if not exists:
        raise BNEError(f"Файл не найден: {name}", source)
    return path
