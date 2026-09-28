from __future__ import annotations
from pathlib import Path
from typing import Final


_DEFAULT_BODY_DIR: Final[Path] = (
    Path(__file__).resolve().parent.parent / "webui" / "assets" / "hero body"
)


_BODY_FILENAMES: Final[dict[str, str]] = {
    "alcar-full-image":     "Alcar",
    "ava-full-image":       "Ava",
    "charles-full-image":   "Charles",
    "eric-full-image":      "Eric",
    "hilde-kingshot-full":  "Hilde",
    "jaeger-full-image":    "Jaeger",
    "long-fei-full-image":  "Long Fei",
    "margot-full-image":    "Margot",
    "marlin-kingshot-full": "Marlin",
    "petra-full-image":     "Petra",
    "rosa-full-image":      "Rosa",
    "sophia-full-image":    "Sophia",
    "thrud-full-image":     "Thrud",
    "triton-full-image":    "Triton",
    "vivian-full-image":    "Vivian",
    "wee-woo-full-image":   "Wee & Woo",
    "yang-full-image":      "Yang",
    "zoe-kingshot-full":    "Zoe",
    "amadeus":              "Amadeus",
    "helga":                "Helga",
    "jabel":                "Jabel",
    "saul":                 "Saul",
}

_HERO_TO_STEM: Final[dict[str, str]] = {v: k for k, v in _BODY_FILENAMES.items()}


def body_path_for(hero_name: str, body_dir: Path | None = None) -> Path | None:
    stem = _HERO_TO_STEM.get(hero_name)
    if stem is None:
        return None
    directory = body_dir if body_dir is not None else _DEFAULT_BODY_DIR
    for ext in (".webp", ".png", ".jpg"):
        p = directory / f"{stem}{ext}"
        if p.exists():
            return p
    return directory / f"{stem}.webp"


def all_body_heroes() -> tuple[str, ...]:
    return tuple(sorted(_HERO_TO_STEM.keys()))


__all__ = ["body_path_for", "all_body_heroes"]
