from __future__ import annotations
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from .ocr_hero_roster import detect_card_grid
from .ocr_gear import resolve_gear_level


GEAR_SLOTS: tuple[str, ...] = ("head", "chest", "gloves", "boots")
GEAR_CLASSES: tuple[str, ...] = ("Inf", "Cav", "Arc")

_GEAR_ICON_DIR = Path(__file__).resolve().parent.parent / "webui" / "assets" / "gear"
_TPL_SZ = 96
_CTR_Y0, _CTR_Y1, _CTR_X0, _CTR_X1 = 0.24, 0.76, 0.18, 0.82
_MATCH_OK = 0.55
_MIN_GEAR_W = 700


@lru_cache(maxsize=1)
def _load_gear_templates() -> dict[tuple[str, str], np.ndarray]:
    refs: dict[tuple[str, str], np.ndarray] = {}
    for cls in GEAR_CLASSES:
        for slot in GEAR_SLOTS:
            p = _GEAR_ICON_DIR / f"{cls.lower()}_{slot}.png"
            if not p.exists():
                continue
            img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            refs[(cls, slot)] = cv2.resize(
                img, (_TPL_SZ, _TPL_SZ), interpolation=cv2.INTER_AREA)
    return refs


def _center_crop(tile_bgr: np.ndarray) -> np.ndarray:
    h, w = tile_bgr.shape[:2]
    sub = tile_bgr[int(h * _CTR_Y0):int(h * _CTR_Y1),
                   int(w * _CTR_X0):int(w * _CTR_X1)]
    if sub.size == 0:
        return np.zeros((_TPL_SZ, _TPL_SZ), np.uint8)
    g = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY) if sub.ndim == 3 else sub
    return cv2.resize(g, (_TPL_SZ, _TPL_SZ), interpolation=cv2.INTER_AREA)


def match_gear(tile_bgr: np.ndarray) -> tuple[tuple[str, str] | None, float, float]:
    refs = _load_gear_templates()
    if not refs:
        return None, -2.0, 0.0
    cand = _center_crop(tile_bgr)
    scored = sorted(
        ((float(cv2.matchTemplate(cand, t, cv2.TM_CCOEFF_NORMED)[0, 0]), ks)
         for ks, t in refs.items()),
        key=lambda kv: kv[0], reverse=True,
    )
    best, ks = scored[0]
    second = scored[1][0] if len(scored) > 1 else best
    return ks, best, best - second


def classify_quality(tile_bgr: np.ndarray) -> tuple[str, float]:
    if tile_bgr is None or tile_bgr.size == 0:
        return "mythic", 0.0
    h, w = tile_bgr.shape[:2]
    hsv = cv2.cvtColor(tile_bgr, cv2.COLOR_BGR2HSV)
    H, S = hsv[..., 0], hsv[..., 1]
    region = np.zeros((h, w), bool)
    y0, y1 = int(h * 0.30), int(h * 0.70)
    region[y0:y1, :int(w * 0.12)] = True
    region[y0:y1, int(w * 0.88):] = True
    sat = (S > 70) & region
    n = int(sat.sum())
    if n == 0:
        return "mythic", 0.0
    red = int((sat & ((H <= 12) | (H >= 160))).sum())
    gold = int((sat & (H >= 13) & (H <= 36)).sum())
    if red > gold:
        return "red", red / max(n, 1)
    return "mythic", gold / max(n, 1)


def read_level(tile_bgr: np.ndarray) -> tuple[int | None, str]:
    try:
        import pytesseract
    except Exception:
        return None, ""
    if tile_bgr is None or tile_bgr.size == 0:
        return None, ""
    h, w = tile_bgr.shape[:2]
    crop = tile_bgr[int(h * 0.04):int(h * 0.27), int(w * 0.44):int(w * 0.99)]
    ch, cw = crop.shape[:2]
    if ch == 0 or cw == 0:
        return None, ""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    white = (((hsv[..., 2] > 170) & (hsv[..., 1] < 70)) * 255).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    comps = [tuple(stats[i, :4]) for i in range(1, n)
             if stats[i, cv2.CC_STAT_AREA] >= 10
             and stats[i, cv2.CC_STAT_HEIGHT] >= ch * 0.42
             and stats[i, cv2.CC_STAT_WIDTH] <= cw * 0.42]
    if not comps:
        return None, ""
    comps.sort(key=lambda b: b[0])
    runs = [comps]
    if len(comps) >= 2:
        runs.append(comps[1:])
    votes: dict[int, int] = {}
    raw_seen = ""
    for run in runs:
        x0 = max(0, min(b[0] for b in run) - 2)
        x1 = max(b[0] + b[2] for b in run) + 2
        y0 = max(0, min(b[1] for b in run) - 2)
        y1 = max(b[1] + b[3] for b in run) + 2
        glyph = white[y0:y1, x0:x1]
        if glyph.size == 0:
            continue
        glyph = cv2.resize(glyph, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
        glyph = 255 - cv2.dilate(glyph, np.ones((3, 3), np.uint8))
        for psm in (7, 8, 13):
            try:
                txt = pytesseract.image_to_string(
                    glyph, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789"
                ).strip()
            except Exception:
                return None, raw_seen
            raw_seen = raw_seen or txt
            m = re.search(r"\d{1,3}", txt)
            if m and 0 <= int(m.group()) <= 100:
                v = int(m.group())
                votes[v] = votes.get(v, 0) + 1
    if not votes:
        return None, raw_seen
    return max(votes.items(), key=lambda kv: kv[1])[0], raw_seen


def read_mastery(tile_bgr: np.ndarray) -> tuple[int | None, str]:
    try:
        import pytesseract
    except Exception:
        return None, ""
    if tile_bgr is None or tile_bgr.size == 0:
        return None, ""
    h, w = tile_bgr.shape[:2]
    crop = tile_bgr[int(h * 0.80):h, int(w * 0.50):w]
    if crop.size == 0:
        return None, ""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow = (((hsv[..., 0] >= 18) & (hsv[..., 0] <= 40) &
               (hsv[..., 1] > 80) & (hsv[..., 2] > 140)) * 255).astype(np.uint8)
    yellow = cv2.resize(yellow, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
    votes: dict[int, int] = {}
    raw_seen = ""
    for psm in (7, 8, 11, 13):
        try:
            txt = pytesseract.image_to_string(
                yellow, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789"
            ).strip()
        except Exception:
            return None, raw_seen
        raw_seen = raw_seen or txt
        m = re.search(r"\d{1,2}", txt)
        if m and 0 <= int(m.group()) <= 20:
            v = int(m.group())
            votes[v] = votes.get(v, 0) + 1
    if not votes:
        return None, raw_seen
    return max(votes.items(), key=lambda kv: kv[1])[0], raw_seen


@dataclass
class GearRosterPiece:
    klass: Literal["Inf", "Cav", "Arc"]
    slot: Literal["head", "chest", "gloves", "boots"]
    quality: Literal["mythic", "red"]
    level: int | None
    mastery: int | None
    engine_level: int | None
    match_score: float
    match_margin: float
    row: int
    col: int
    needs_review: bool = True
    level_raw: str = ""
    mastery_raw: str = ""


@dataclass
class GearRosterResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    pieces: list[GearRosterPiece] = field(default_factory=list)
    loadouts: dict[str, dict[str, GearRosterPiece]] = field(default_factory=dict)

    def is_ok(self) -> bool:
        return self.error is None and len(self.pieces) > 0

    def hero_gear_kwargs(self, klass: str) -> list[dict]:
        out: list[dict] = []
        for slot in GEAR_SLOTS:
            p = self.loadouts.get(klass, {}).get(slot)
            if p is None or p.engine_level is None:
                continue
            out.append({
                "slot": slot, "quality": p.quality,
                "level": p.engine_level, "forge_mastery": p.mastery or 0,
            })
        return out


def _to_bgr(img, image_override) -> np.ndarray | None:
    if image_override is not None:
        return image_override
    if isinstance(img, np.ndarray):
        return img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if isinstance(img, str):
        return cv2.imread(img)
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _better(a: GearRosterPiece, b: GearRosterPiece) -> GearRosterPiece:
    ka = (a.engine_level if a.engine_level is not None else -1,
          a.mastery or 0, a.match_score)
    kb = (b.engine_level if b.engine_level is not None else -1,
          b.mastery or 0, b.match_score)
    return a if ka >= kb else b


def ocr_gear_roster(
    img: "Image.Image | str | np.ndarray",
    *,
    read_numbers: bool = True,
    _image_override: np.ndarray | None = None,
) -> GearRosterResult:
    result = GearRosterResult()
    bgr = _to_bgr(img, _image_override)
    if bgr is None:
        result.error = "Could not read the gear screenshot image."
        return result
    H, W = bgr.shape[:2]
    if W < _MIN_GEAR_W:
        result.error = (
            f"This screenshot is too small to read gear reliably (only {W}px "
            f"wide). Upload the original Backpack -> Gear screenshot from your "
            f"phone's gallery, not a downscaled chat-app copy."
        )
        return result
    if not _load_gear_templates():
        result.error = "Gear template library is missing (webui/assets/gear/)."
        return result

    col_bands, full_rows = detect_card_grid(bgr)
    if not full_rows:
        result.error = (
            "No gear tiles detected. Upload the Backpack 'Gear' tab (the "
            "4-column grid of gear icons)."
        )
        return result

    for r, (ry0, ry1) in enumerate(full_rows):
        for c, (cx0, cx1) in enumerate(col_bands):
            if cx1 - cx0 < 8 or ry1 - ry0 < 8:
                continue
            tile = bgr[ry0:ry1, cx0:cx1]
            ks, score, margin = match_gear(tile)
            if ks is None or score < _MATCH_OK:
                continue
            klass, slot = ks
            quality, _ = classify_quality(tile)
            level = mastery = engine_level = None
            lraw = mraw = ""
            if read_numbers:
                level, lraw = read_level(tile)
                mastery, mraw = read_mastery(tile)
                if level is not None:
                    engine_level = resolve_gear_level(quality, level)
            result.pieces.append(GearRosterPiece(
                klass=klass, slot=slot, quality=quality, level=level,
                mastery=mastery, engine_level=engine_level, match_score=score,
                match_margin=margin, row=r, col=c, needs_review=True,
                level_raw=lraw, mastery_raw=mraw,
            ))

    if not result.pieces:
        result.error = (
            "Found the grid but matched no gear. Make sure it's the Backpack "
            "'Gear' tab at full resolution."
        )
        return result

    for p in result.pieces:
        slot_map = result.loadouts.setdefault(p.klass, {})
        cur = slot_map.get(p.slot)
        slot_map[p.slot] = p if cur is None else _better(cur, p)

    for klass in GEAR_CLASSES:
        missing = [s for s in GEAR_SLOTS if s not in result.loadouts.get(klass, {})]
        if missing:
            result.warnings.append(
                f"{klass}: no {', '.join(missing)} piece detected — fill it in "
                f"manually or re-upload a screenshot that shows it."
            )
    return result


__all__ = [
    "GearRosterPiece", "GearRosterResult", "ocr_gear_roster",
    "match_gear", "classify_quality", "read_level", "read_mastery",
    "GEAR_SLOTS", "GEAR_CLASSES",
]
