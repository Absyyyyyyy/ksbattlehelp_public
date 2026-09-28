from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image
from functools import lru_cache

from .ocr import _ocr_tokens, preprocess_image


_CARD_SAT = 60
_CARD_VAL = 110
_N_COLS = 4

_HIST_BINS = (30, 32)
_BODY_MATCH_OK = 0.30
_PIN_FLOOR = 0.12
_CHAR_Y0, _CHAR_Y1, _CHAR_X = 0.05, 0.78, 0.04


def _hs_hist(bgr: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], mask, list(_HIST_BINS), [0, 180, 0, 256])
    cv2.normalize(h, h, 0, 1, cv2.NORM_MINMAX)
    return h


@lru_cache(maxsize=1)
def _load_body_hists() -> dict[str, np.ndarray]:
    from ..data.hero_bodies import all_body_heroes, body_path_for
    out: dict[str, np.ndarray] = {}
    for hero in all_body_heroes():
        p = body_path_for(hero)
        if p is None or not p.exists():
            continue
        try:
            arr = np.array(Image.open(p).convert("RGBA"))
        except Exception:
            continue
        bgr = cv2.cvtColor(arr[..., :3], cv2.COLOR_RGB2BGR)
        mask = (arr[..., 3] > 40).astype(np.uint8) * 255
        out[hero] = _hs_hist(bgr, mask)
    return out


@lru_cache(maxsize=1)
def _gen_class_index() -> dict[tuple[str | None, int], tuple[str, ...]]:
    from ..data.reference import HERO_CLASS, HERO_GENERATION
    idx: dict[tuple[str | None, int], list[str]] = {}
    for h in _load_body_hists():
        idx.setdefault((HERO_CLASS.get(h), HERO_GENERATION.get(h, 0)), []).append(h)
    return {k: tuple(v) for k, v in idx.items()}


def _pins_unique_hero(klass: str | None, gen: int | None) -> bool:
    if klass is None or gen is None:
        return False
    return len(_gen_class_index().get((klass, gen), ())) == 1


def _card_character_mask(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    bg = (H >= 16) & (H <= 46) & (S > 90) & (V > 110)
    return (~bg).astype(np.uint8) * 255


def match_hero_body(crop: np.ndarray, klass: str | None = None,
                    gen: int | None = None) -> tuple[str | None, float]:
    if crop is None or crop.size == 0:
        return None, -2.0
    hists = _load_body_hists()
    if not hists:
        return None, -2.0
    if klass is not None or gen is not None:
        from ..data.reference import HERO_CLASS, HERO_GENERATION
        if klass is not None:
            hists = {h: v for h, v in hists.items()
                     if HERO_CLASS.get(h) == klass} or hists
        if gen is not None:
            narrowed = {h: v for h, v in hists.items()
                        if HERO_GENERATION.get(h, 0) == gen}
            if narrowed:
                hists = narrowed
    h = _hs_hist(crop, _card_character_mask(crop))
    best_hero, best = None, -2.0
    for hero, rh in hists.items():
        s = float(cv2.compareHist(h, rh, cv2.HISTCMP_CORREL))
        if s > best:
            best, best_hero = s, hero
    return best_hero, best


_CLASS_ICON_DIR = Path(__file__).resolve().parent.parent / "webui" / "assets" / "class icon"
_CICON_REGION = (0.03, 0.32, 0.01, 0.18)
_CICON_SZ = 56


def _class_symbol_mask(icon_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(icon_bgr, cv2.COLOR_BGR2HSV)
    m = (((hsv[..., 2] > 150) & (hsv[..., 1] < 90)) * 255).astype(np.uint8)
    return cv2.resize(m, (_CICON_SZ, _CICON_SZ), interpolation=cv2.INTER_AREA)


@lru_cache(maxsize=1)
def _load_class_templates() -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for stem, cls in (("inf", "Inf"), ("cav", "Cav"), ("arc", "Arc")):
        p = _CLASS_ICON_DIR / f"{stem}.png"
        if not p.exists():
            continue
        img = cv2.imread(str(p))
        if img is not None:
            out[cls] = _class_symbol_mask(img)
    return out


def detect_card_class(card: np.ndarray) -> str | None:
    templ = _load_class_templates()
    if not templ or card is None or card.size == 0:
        return None
    ch, cw = card.shape[:2]
    x0, x1, y0, y1 = _CICON_REGION
    icon = card[int(ch * y0):int(ch * y1), int(cw * x0):int(cw * x1)]
    if icon.size == 0:
        return None
    sym = _class_symbol_mask(icon)
    best, best_s = None, -2.0
    for cls, t in templ.items():
        s = float(cv2.matchTemplate(sym, t, cv2.TM_CCOEFF_NORMED)[0, 0])
        if s > best_s:
            best_s, best = s, cls
    return best


_GBADGE_REGION = (0.62, 0.97, 0.02, 0.22)
_GBADGE_EDGE = 0.075
_GDIGIT_REGION = (0.80, 0.98, 0.03, 0.20)


def _card_has_gen_badge(card: np.ndarray) -> bool:
    if card is None or card.size == 0:
        return False
    ch, cw = card.shape[:2]
    x0, x1, y0, y1 = _GBADGE_REGION
    sub = card[int(ch * y0):int(ch * y1), int(cw * x0):int(cw * x1)]
    if sub.size == 0:
        return False
    g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    return float((cv2.Canny(g, 60, 160) > 0).mean()) >= _GBADGE_EDGE


def _read_gen_digit(card: np.ndarray) -> int | None:
    if card is None or card.size == 0:
        return None
    ch, cw = card.shape[:2]
    x0, x1, y0, y1 = _GDIGIT_REGION
    sub = card[int(ch * y0):int(ch * y1), int(cw * x0):int(cw * x1)]
    if sub.size == 0:
        return None
    try:
        import pytesseract
        g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
        _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cfg = "--psm 10 -c tessedit_char_whitelist=3456789"
        for img in (bw, 255 - bw):
            t = pytesseract.image_to_string(img, config=cfg).strip()
            for ch_ in t:
                if ch_.isdigit():
                    return int(ch_)
    except Exception:
        return None
    return None


_UNLOCKED_SAT = 132


@dataclass
class RosterHeroCell:
    hero_name: str | None
    star: int
    face_score: float
    row: int
    col: int
    unlocked: bool = True
    klass: str | None = None
    sub_tier: int = 0
    needs_review: bool = True


@dataclass
class RosterOCRResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    cells: list[RosterHeroCell] = field(default_factory=list)

    def is_ok(self) -> bool:
        return self.error is None and len(self.cells) > 0

    def owned_heroes(self) -> list[str]:
        return sorted({c.hero_name for c in self.cells if c.hero_name})


def _bands(profile: np.ndarray, thr_frac: float, min_len: int) -> list[tuple[int, int]]:
    if profile.size == 0 or profile.max() == 0:
        return []
    on = profile > profile.max() * thr_frac
    runs: list[tuple[int, int]] = []
    s: int | None = None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= min_len:
                runs.append((s, i))
            s = None
    if s is not None and len(on) - s >= min_len:
        runs.append((s, len(on)))
    return runs


def _card_mask(img_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 1] > _CARD_SAT) & (hsv[..., 2] > _CARD_VAL)).astype(np.uint8)


def _card_is_unlocked(card: np.ndarray) -> bool:
    if card.size == 0:
        return False
    ch, cw = card.shape[:2]
    S = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)[..., 1]
    b = max(1, int(min(ch, cw) * 0.10))
    ring = np.concatenate([
        S[:b, :].ravel(), S[-b:, :].ravel(), S[:, :b].ravel(), S[:, -b:].ravel(),
    ])
    return float(ring.mean()) >= _UNLOCKED_SAT


_RSTAR_SLOTS = 5
_RSTAR_BAND = 0.80
_RSTAR_CREAM_V, _RSTAR_CREAM_S = 200, 150
_RSTAR_AMBER_V, _RSTAR_AMBER_S = 170, 120
_RSTAR_FULL_RAW = 0.50
_RSTAR_FULL_FILL = 0.80
_RSTAR_SUB_EDGES = (0.07, 0.22, 0.37, 0.52, 0.63)


def count_roster_stars(card: np.ndarray) -> tuple[int, int, float]:
    if card is None or card.size == 0:
        return 0, 0, 0.0
    ch, cw = card.shape[:2]
    crop = card[int(ch * _RSTAR_BAND):ch, :]
    if crop.size == 0:
        return 0, 0, 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    S, V = hsv[..., 1], hsv[..., 2]
    cream = (V > _RSTAR_CREAM_V) & (S < _RSTAR_CREAM_S)
    amber = (V < _RSTAR_AMBER_V) & (S > _RSTAR_AMBER_S)
    ink = cv2.morphologyEx(
        (cream | amber).astype(np.uint8), cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    row_runs = _bands(ink.sum(axis=1), 0.30, max(3, int(crop.shape[0] * 0.10)))
    if not row_runs:
        return 0, 0, 0.0
    ry0, ry1 = max(row_runs, key=lambda ab: ab[1] - ab[0])
    cream, amber, ink = cream[ry0:ry1], amber[ry0:ry1], ink[ry0:ry1]
    col_runs = _bands(ink.sum(axis=0), 0.25, max(2, int(cw * 0.02)))
    if len(col_runs) < 2:
        return 0, 0, 0.0
    x_lo, x_hi = col_runs[0][0], col_runs[-1][1]
    slot_w = (x_hi - x_lo) / _RSTAR_SLOTS
    fills: list[float] = []
    for i in range(_RSTAR_SLOTS):
        a = int(x_lo + i * slot_w)
        b = int(x_lo + (i + 1) * slot_w)
        c = int(cream[:, a:b].sum())
        d = int(amber[:, a:b].sum())
        raw = c / (c + d) if (c + d) else 0.0
        fills.append(min(1.0, raw / _RSTAR_FULL_RAW))
    full = min(_RSTAR_SLOTS, sum(1 for f in fills if f >= _RSTAR_FULL_FILL))
    sub = (sum(1 for e in _RSTAR_SUB_EDGES if fills[full] > e)
           if full < _RSTAR_SLOTS else 0)
    conf = float(np.mean([abs(f - 0.5) * 2 for f in fills])) if fills else 0.0
    return full, sub, min(1.0, conf)


def _to_bgr(img, image_override) -> np.ndarray | None:
    if image_override is not None:
        return image_override
    if isinstance(img, np.ndarray):
        return img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if isinstance(img, str):
        return cv2.imread(img)
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def detect_card_grid(bgr: np.ndarray) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    H, W = bgr.shape[:2]
    mask = _card_mask(bgr)
    col_bands = _bands(mask.sum(axis=0), 0.25, int(W * 0.07))
    if len(col_bands) != _N_COLS:
        step = W / _N_COLS
        col_bands = [(int(c * step + W * 0.01), int((c + 1) * step - W * 0.01))
                     for c in range(_N_COLS)]
    row_bands = _bands(mask.sum(axis=1), 0.22, int(H * 0.03))
    if not row_bands:
        return col_bands, []
    tallest = max(b - a for a, b in row_bands)
    full_rows = [(a, b) for a, b in row_bands if (b - a) >= tallest * 0.6]
    return col_bands, full_rows


def ocr_hero_roster(
    img: "Image.Image | str | np.ndarray",
    *,
    min_score: float = _BODY_MATCH_OK,
    _image_override: np.ndarray | None = None,
) -> RosterOCRResult:
    result = RosterOCRResult()
    bgr = _to_bgr(img, _image_override)
    if bgr is None:
        result.error = "Could not read the roster image."
        return result
    col_bands, full_rows = detect_card_grid(bgr)
    if not full_rows:
        result.error = (
            "No hero cards detected. Upload the 'Heroes' screen (the 4-column "
            "grid), sorted by Quality."
        )
        return result

    for r, (ry0, ry1) in enumerate(full_rows):
        ch = ry1 - ry0
        for c, (cx0, cx1) in enumerate(col_bands):
            cw = cx1 - cx0
            if cw < 8 or ch < 8:
                continue
            card = bgr[ry0:ry1, cx0:cx1]
            if not _card_is_unlocked(card):
                continue
            klass = detect_card_class(card)
            gen = _read_gen_digit(card) if _card_has_gen_badge(card) else None
            char = bgr[ry0 + int(ch * _CHAR_Y0):ry0 + int(ch * _CHAR_Y1),
                       cx0 + int(cw * _CHAR_X):cx1 - int(cw * _CHAR_X)]
            hero, score = match_hero_body(char, klass=klass, gen=gen)
            pinned = _pins_unique_hero(klass, gen)
            if hero is None or (score < (_PIN_FLOOR if pinned else min_score)):
                continue
            star, sub_tier, _ = count_roster_stars(card)
            result.cells.append(RosterHeroCell(
                hero_name=hero, star=int(star), sub_tier=int(sub_tier),
                face_score=float(score), row=r, col=c, unlocked=True,
                klass=klass, needs_review=True,
            ))

    if not result.cells:
        result.error = (
            "Found the grid but matched no heroes. Make sure it's the 'Heroes' "
            "collection screen at full resolution."
        )
    return result


__all__ = [
    "RosterHeroCell", "RosterOCRResult", "ocr_hero_roster", "detect_card_grid",
    "count_roster_stars",
]
