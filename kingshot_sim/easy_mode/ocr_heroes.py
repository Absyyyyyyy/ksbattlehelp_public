from __future__ import annotations
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from ..data.hero_portraits import all_portrait_heroes, portrait_path_for
from .ocr import (
    preprocess_image, clahe_rgb, _ocr_tokens, DEFAULT_CONFIDENCE_THRESHOLD,
)


_REFERENCE_SIZE: int = 96

_FACE_SCORE_OK:  float = 0.45
_LEVEL_CONF_OK:  float = 70.0
_STAR_COUNT_OK:  int   = 1

CLASS_ORDER: tuple[str, ...] = ("inf", "cav", "arc")


@lru_cache(maxsize=1)
def _load_reference_portraits() -> dict[str, np.ndarray]:
    refs: dict[str, np.ndarray] = {}
    for hero in all_portrait_heroes():
        path = portrait_path_for(hero)
        if path is None or not path.exists():
            continue
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        resized = cv2.resize(
            img, (_REFERENCE_SIZE, _REFERENCE_SIZE),
            interpolation=cv2.INTER_AREA,
        )
        refs[hero] = resized
    return refs


def match_portrait(candidate: np.ndarray) -> tuple[str | None, float]:
    if candidate is None or candidate.size == 0:
        return None, -2.0
    if candidate.ndim == 3:
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
    else:
        gray = candidate
    cand = cv2.resize(
        gray, (_REFERENCE_SIZE, _REFERENCE_SIZE),
        interpolation=cv2.INTER_AREA,
    )
    refs = _load_reference_portraits()
    if not refs:
        return None, -2.0
    best_hero: str | None = None
    best_score: float = -2.0
    for hero, ref in refs.items():
        result = cv2.matchTemplate(cand, ref, cv2.TM_CCOEFF_NORMED)
        score = float(result[0, 0])
        if score > best_score:
            best_score = score
            best_hero = hero
    return best_hero, best_score


_WIDGET_REFERENCE_SIZE: int = 72
_WIDGET_SCORE_OK: float = 0.42


@lru_cache(maxsize=1)
def _load_reference_widgets() -> dict[str, np.ndarray]:
    from ..data.hero_widgets import all_widget_heroes, widget_path_for
    refs: dict[str, np.ndarray] = {}
    for hero in all_widget_heroes():
        path = widget_path_for(hero)
        if path is None or not path.exists():
            continue
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        refs[hero] = cv2.resize(
            img, (_WIDGET_REFERENCE_SIZE, _WIDGET_REFERENCE_SIZE),
            interpolation=cv2.INTER_AREA,
        )
    return refs


def match_widget(candidate: np.ndarray) -> tuple[str | None, float]:
    if candidate is None or candidate.size == 0:
        return None, -2.0
    gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY) if candidate.ndim == 3 else candidate
    cand = cv2.resize(
        gray, (_WIDGET_REFERENCE_SIZE, _WIDGET_REFERENCE_SIZE),
        interpolation=cv2.INTER_AREA,
    )
    refs = _load_reference_widgets()
    if not refs:
        return None, -2.0
    best_hero: str | None = None
    best_score: float = -2.0
    for hero, ref in refs.items():
        score = float(cv2.matchTemplate(cand, ref, cv2.TM_CCOEFF_NORMED)[0, 0])
        if score > best_score:
            best_score = score
            best_hero = hero
    return best_hero, best_score


_LEVEL_RE = re.compile(r"\bLv?\.?\s*(\d{1,2})\b", re.IGNORECASE)


def extract_level(portrait_crop: np.ndarray) -> tuple[int | None, float, str]:
    import pytesseract
    if portrait_crop is None or portrait_crop.size == 0:
        return None, 0.0, ""
    if portrait_crop.ndim == 3:
        rgb = cv2.cvtColor(portrait_crop, cv2.COLOR_BGR2RGB)
    else:
        rgb = cv2.cvtColor(portrait_crop, cv2.COLOR_GRAY2RGB)
    pil = Image.fromarray(rgb)
    pil = preprocess_image(pil)
    try:
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT)
    except Exception:
        return None, 0.0, ""
    n = len(data["text"])
    toks: list[tuple[str, float]] = []
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue
        toks.append((txt, conf))

    if not toks:
        return None, 0.0, ""

    best_level: int | None = None
    best_conf: float = -1.0
    best_text = ""
    for txt, conf in toks:
        m = _LEVEL_RE.search(txt)
        if not m:
            continue
        lvl = int(m.group(1))
        if 1 <= lvl <= 99 and conf > best_conf:
            best_conf = conf
            best_level = lvl
            best_text = txt

    if best_level is None:
        joined = " ".join(t for t, _ in toks)
        m = _LEVEL_RE.search(joined)
        if m:
            lvl = int(m.group(1))
            if 1 <= lvl <= 99:
                digits = m.group(1)
                digit_confs = [c for t, c in toks if digits in t]
                conf = (
                    max(digit_confs) if digit_confs
                    else max((c for _, c in toks), default=0.0)
                )
                best_level = lvl
                best_conf = conf
                best_text = joined

    return best_level, max(best_conf, 0.0), best_text


_STAR_HSV_LOW  = np.array([20, 110, 130], dtype=np.uint8)
_STAR_HSV_HIGH = np.array([42, 255, 255], dtype=np.uint8)


def count_stars(star_strip: np.ndarray) -> tuple[int, float]:
    if star_strip is None or star_strip.size == 0:
        return 0, 0.0
    if star_strip.ndim == 2:
        star_strip = cv2.cvtColor(star_strip, cv2.COLOR_GRAY2BGR)
    hsv = cv2.cvtColor(star_strip, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _STAR_HSV_LOW, _STAR_HSV_HIGH)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = max(20, (star_strip.shape[0] * star_strip.shape[1]) // 500)
    star_count = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            star_count += 1
    star_count = min(star_count, 5)
    yellow_fraction = float(mask.sum()) / 255.0 / max(mask.size, 1)
    conf = min(1.0, yellow_fraction * 12.0)
    return star_count, conf


@dataclass
class HeroCell:
    klass: Literal["inf", "cav", "arc"]
    hero_name: str | None
    level: int | None
    star: int
    face_score: float
    level_conf: float
    star_conf: float
    needs_review: bool = False
    raw_level_text: str = ""


@dataclass
class HeroOCRResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    cells: list[HeroCell] = field(default_factory=list)
    n_low_confidence: int = 0
    slot_class: dict[int, str] = field(default_factory=dict)

    def is_ok(self) -> bool:
        return self.error is None and len(self.cells) == 3


def _find_phrase_y(
    tokens: list[dict],
    first_word: str,
    second_word: str,
    *,
    max_dy: int = 30,
    max_dx: int = 600,
) -> int | None:
    fw = first_word.lower()
    sw = second_word.lower()
    for t in tokens:
        txt = t["text"].lower()
        if fw in txt and sw in txt:
            return t["y"]
    firsts  = [t for t in tokens if fw in t["text"].lower()]
    seconds = [t for t in tokens if sw in t["text"].lower()]
    if not firsts or not seconds:
        return None
    candidates: list[int] = []
    for f in firsts:
        for s in seconds:
            if f is s:
                continue
            dy = abs(s["y"] - f["y"])
            dx = s["x"] - f["x"]
            if dy <= max_dy and 0 <= dx <= max_dx:
                candidates.append(f["y"])
                break
    if not candidates:
        return None
    return min(candidates)


def _find_hero_comparison_y(tokens: list[dict]) -> int | None:
    return _find_phrase_y(tokens, "hero", "comparison")


def _find_troop_power_y(tokens: list[dict]) -> int | None:
    y = _find_phrase_y(tokens, "troop", "power")
    if y is not None:
        return y
    return _find_phrase_y(tokens, "troop", "comparison")


def _find_master_comparison_y(tokens: list[dict]) -> int | None:
    return _find_phrase_y(tokens, "master", "comparison")


def _slice_portrait_grid(
    img_bgr: np.ndarray,
    y_top: int,
    y_bottom: int,
) -> dict[str, dict[str, tuple[int, int, int, int]]]:
    h, w = img_bgr.shape[:2]
    band_top = y_top + int((y_bottom - y_top) * 0.07)
    band_bot = y_bottom - int((y_bottom - y_top) * 0.02)
    row_h = (band_bot - band_top) / 3.0

    left_x0  = int(w * 0.04)
    left_x1  = int(w * 0.22)
    right_x0 = int(w * 0.78)
    right_x1 = int(w * 0.96)

    out: dict[str, dict[str, tuple[int, int, int, int]]] = {"left": {}, "right": {}}
    for r, klass in enumerate(CLASS_ORDER):
        y0 = int(band_top + r * row_h)
        y1 = int(band_top + (r + 1) * row_h)
        out["left"][klass]  = (left_x0,  y0, left_x1,  y1)
        out["right"][klass] = (right_x0, y0, right_x1, y1)
    return out


def ocr_heroes(
    img: Image.Image | str | np.ndarray,
    side: Literal["left", "right"] = "left",
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    *,
    _token_override: list[dict] | None = None,
    _image_override: np.ndarray | None = None,
) -> HeroOCRResult:
    if _image_override is not None:
        img_bgr = _image_override
    elif isinstance(img, np.ndarray):
        img_bgr = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif isinstance(img, str):
        img_bgr = cv2.imread(img)
        if img_bgr is None:
            return HeroOCRResult(error=f"Could not read image at {img!r}")
    else:
        arr = np.array(img.convert("RGB"))
        img_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    result = HeroOCRResult()

    if _token_override is not None:
        tokens = _token_override
        pil_for_tokens = None
    else:
        pil_for_tokens = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        tokens = _ocr_tokens(preprocess_image(pil_for_tokens))

    y_top = _find_hero_comparison_y(tokens)
    if y_top is None and pil_for_tokens is not None:
        hc_tokens = _ocr_tokens(clahe_rgb(pil_for_tokens))
        hc_y = _find_hero_comparison_y(hc_tokens)
        if hc_y is not None:
            y_top, tokens = hc_y, hc_tokens
    if y_top is None:
        result.error = (
            "Could not find the 'Hero Comparison' header in the screenshot. "
            "Make sure you upload a battle-report screenshot that shows the "
            "Hero Comparison section."
        )
        return result

    y_master = _find_master_comparison_y(tokens)
    y_troop  = _find_troop_power_y(tokens)
    y_bot: int | None = None
    if y_master is not None and y_master > y_top:
        y_bot = y_master
    elif y_troop is not None and y_troop > y_top:
        y_bot = y_troop
    if y_bot is None or y_bot <= y_top:
        y_bot = min(img_bgr.shape[0], y_top + int(img_bgr.shape[0] * 0.35))

    boxes = _slice_portrait_grid(img_bgr, y_top, y_bot)
    side_boxes = boxes[side]

    slot_results: list[dict] = []
    h, w = img_bgr.shape[:2]
    for row_idx, slot_klass in enumerate(CLASS_ORDER):
        x0, y0, x1, y1 = side_boxes[slot_klass]
        x0 = max(0, min(x0, w - 1))
        x1 = max(x0 + 1, min(x1, w))
        y0 = max(0, min(y0, h - 1))
        y1 = max(y0 + 1, min(y1, h))
        crop = img_bgr[y0:y1, x0:x1]

        if crop.size == 0:
            slot_results.append({
                "row_idx": row_idx, "hero_name": None, "face_score": -2.0,
                "level": None, "level_conf": 0.0, "level_text": "",
                "star": 0, "star_conf": 0.0,
            })
            continue

        ch, cw = crop.shape[:2]
        fy0 = int(ch * 0.10)
        fy1 = int(ch * 0.80)
        fx0 = int(cw * 0.10)
        fx1 = int(cw * 0.90)
        face_crop = crop[fy0:fy1, fx0:fx1] if (fy1 > fy0 and fx1 > fx0) else crop
        hero_name, face_score = match_portrait(face_crop)

        level_y = int(ch * 0.75)
        level_crop = crop[level_y:, :] if ch - level_y >= 12 else crop
        level, level_conf, level_text = extract_level(level_crop)

        star_y0 = y1
        star_y1 = min(h, y1 + max(20, (y1 - y0) // 6))
        star_strip = img_bgr[star_y0:star_y1, x0:x1]
        star_count, star_conf = count_stars(star_strip)

        slot_results.append({
            "row_idx": row_idx,
            "hero_name": hero_name,
            "face_score": face_score,
            "level": level,
            "level_conf": level_conf,
            "level_text": level_text,
            "star": star_count,
            "star_conf": star_conf,
        })

    from ..data.reference import HERO_CLASS
    class_to_slot: dict[str, dict] = {}
    for s in sorted(slot_results, key=lambda r: -r["face_score"]):
        hero = s["hero_name"]
        if hero is None or s["face_score"] < _FACE_SCORE_OK:
            continue
        klass = HERO_CLASS.get(hero, "").lower()
        if klass in ("inf", "cav", "arc") and klass not in class_to_slot:
            class_to_slot[klass] = s

    n_low = 0
    cells: list[HeroCell] = []
    for klass in CLASS_ORDER:
        s = class_to_slot.get(klass)
        if s is None:
            cells.append(HeroCell(
                klass=klass, hero_name=None, level=None, star=0,
                face_score=-2.0, level_conf=0.0, star_conf=0.0,
                needs_review=True,
            ))
            n_low += 1
            continue
        review = (
            s["level_conf"] < _LEVEL_CONF_OK
            or s["star"] < _STAR_COUNT_OK
        )
        if review:
            n_low += 1
        cells.append(HeroCell(
            klass=klass,
            hero_name=s["hero_name"],
            level=s["level"],
            star=s["star"],
            face_score=s["face_score"],
            level_conf=s["level_conf"],
            star_conf=s["star_conf"],
            needs_review=review,
            raw_level_text=s["level_text"],
        ))

    result.cells = cells
    result.n_low_confidence = n_low
    result.slot_class = {
        s["row_idx"]: klass for klass, s in class_to_slot.items()
    }
    return result


__all__ = [
    "HeroCell",
    "HeroOCRResult",
    "ocr_heroes",
    "match_portrait",
    "extract_level",
    "count_stars",
    "CLASS_ORDER",
]
