from __future__ import annotations
from pathlib import Path
from typing import Final


_DEFAULT_WIDGET_DIR: Final[Path] = (
    Path(__file__).resolve().parent.parent / "webui" / "assets" / "herowidget"
)


_WIDGET_FILENAMES: Final[dict[str, str]] = {
    "alcar":   "Alcar",
    "amadeus": "Amadeus",
    "ava":     "Ava",
    "charles": "Charles",
    "eric":    "Eric",
    "helga":   "Helga",
    "hilde":   "Hilde",
    "jabel":   "Jabel",
    "jaeger":  "Jaeger",
    "longfei": "Long Fei",
    "margot":  "Margot",
    "marlin":  "Marlin",
    "petra":   "Petra",
    "rosa":    "Rosa",
    "saul":    "Saul",
    "sophia":  "Sophia",
    "thrud":   "Thrud",
    "triton":  "Triton",
    "vivian":  "Vivian",
    "weewoo":  "Wee & Woo",
    "yang":    "Yang",
    "zoe":     "Zoe",
}

_HERO_TO_STEM: Final[dict[str, str]] = {v: k for k, v in _WIDGET_FILENAMES.items()}


def hero_for_widget_filename(name_or_path: str | Path) -> str | None:
    stem = name_or_path if isinstance(name_or_path, str) else str(name_or_path)
    if "/" in stem or "\\" in stem or "." in stem:
        stem = Path(stem).stem
    return _WIDGET_FILENAMES.get(stem)


def widget_path_for(hero_name: str, widget_dir: Path | None = None) -> Path | None:
    stem = _HERO_TO_STEM.get(hero_name)
    if stem is None:
        return None
    directory = widget_dir if widget_dir is not None else _DEFAULT_WIDGET_DIR
    return directory / f"{stem}.jpg"


def all_widget_heroes() -> tuple[str, ...]:
    return tuple(sorted(_HERO_TO_STEM.keys()))


__all__ = [
    "hero_for_widget_filename",
    "widget_path_for",
    "all_widget_heroes",
]
