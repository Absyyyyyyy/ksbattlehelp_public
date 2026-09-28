from __future__ import annotations
from pathlib import Path
from typing import Final


_DEFAULT_PORTRAIT_DIR: Final[Path] = (
    Path(__file__).resolve().parent.parent / "webui" / "assets" / "hero icon"
)


_PORTRAIT_FILENAMES: Final[dict[str, str]] = {
    "alcar-avatar-image":     "Alcar",
    "amadeus":                "Amadeus",
    "amane-avatar":           "Amane",
    "ava-avatar-image":       "Ava",
    "charles-avatar":         "Charles",
    "chenko-avatar":          "Chenko",
    "diana-avatar-icon":      "Diana",
    "eric-avatar-icon":       "Eric",
    "fahd-avatar":            "Fahd",
    "gordon-avatar":          "Gordon",
    "helga-kingshot":         "Helga",
    "hilde-kingshot":         "Hilde",
    "howard-avatar":          "Howard",
    "jabel":                  "Jabel",
    "jaeger-icon-kingshot":   "Jaeger",
    "long-fei-avatar-icon":   "Long Fei",
    "margot-avatar":          "Margot",
    "marlin-kingshot":        "Marlin",
    "petra-avatar-icon":      "Petra",
    "quinn-avatar":           "Quinn",
    "rosa-avatar-image":      "Rosa",
    "saul-kingshot":          "Saul",
    "sophia-avatar-icon":     "Sophia",
    "thrud-avatar-icon":      "Thrud",
    "triton-avatar-icon":     "Triton",
    "vivian-avatar-icon":     "Vivian",
    "wee-woo":                "Wee & Woo",
    "yang-avatar-icon":       "Yang",
    "yeonwoo-avatar":         "Yeonwoo",
    "zoe-gen2-kingshot":      "Zoe",
}


_HERO_TO_STEM: Final[dict[str, str]] = {v: k for k, v in _PORTRAIT_FILENAMES.items()}


def hero_for_filename(name_or_path: str | Path) -> str | None:
    stem = Path(name_or_path).stem if not isinstance(name_or_path, str) else name_or_path
    if "/" in stem or "\\" in stem or "." in stem:
        stem = Path(stem).stem
    return _PORTRAIT_FILENAMES.get(stem)


def portrait_path_for(hero_name: str, portrait_dir: Path | None = None) -> Path | None:
    stem = _HERO_TO_STEM.get(hero_name)
    if stem is None:
        return None
    directory = portrait_dir if portrait_dir is not None else _DEFAULT_PORTRAIT_DIR
    return directory / f"{stem}.jpg"


def all_portrait_heroes() -> tuple[str, ...]:
    return tuple(sorted(_HERO_TO_STEM.keys()))


__all__ = [
    "hero_for_filename",
    "portrait_path_for",
    "all_portrait_heroes",
]
