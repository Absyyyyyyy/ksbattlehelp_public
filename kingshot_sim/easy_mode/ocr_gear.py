from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from .ocr import _ocr_tokens, preprocess_image, clahe_rgb
from .ocr_heroes import (
    _find_hero_comparison_y, _find_master_comparison_y, _find_troop_power_y,
)


GEAR_SLOTS: tuple[str, ...] = ("head", "gloves", "chest", "boots")

_LEFT_CLUSTER = (0.17, 0.50)
_RIGHT_CLUSTER = (0.50, 0.83)

_ICON_SAT = 75
_ICON_VAL = 70

_Q_SAT = 70
_YELLOW_LO, _YELLOW_HI = 13, 36
_RED_LO, _RED_HI = 12, 160


@dataclass
class GearPieceCell:
    slot: Literal["head", "gloves", "chest", "boots"]
    quality: Literal["mythic", "red"]
    level: int | None = None
    mastery: int | None = None
    quality_conf: float = 0.0
    needs_review: bool = True
    raw_level: str = ""
    raw_mastery: str = ""


@dataclass
class GearCell:
    row_index: int
    has_widget: bool
    widget_level: int | None = None
    pieces: dict[str, GearPieceCell] = field(default_factory=dict)
    is_epic_no_widget: bool = False
    needs_review: bool = True


@dataclass
class GearOCRResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    cells: list[GearCell] = field(default_factory=list)

    def is_ok(self) -> bool:
        return self.error is None and len(self.cells) > 0


def resolve_gear_level(quality: str, displayed: int) -> int:
    if quality == "red":
        return max(100, min(200, 100 + displayed))
    return max(0, min(100, displayed))


_RED_BRACKET_OFFSETS: tuple[tuple[int, int], ...] = (
    (1, 19), (20, 39), (40, 59), (60, 79), (80, 99), (100, 100),
)
_RED_BRACKET_NAMES = ("grey", "green", "blue", "purple", "gold", "red")


def _red_level_bracket(icon: np.ndarray) -> int | None:
    if icon is None or icon.size == 0:
        return None
    h, w = icon.shape[:2]
    band = icon[0:max(1, int(h * 0.22)), int(w * 0.12):int(w * 0.88)]
    if band.size == 0:
        return None
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    bright = V > 110
    if int(bright.sum()) < 15:
        return None
    redbg = (S > 80) & ((H < 12) | (H > 170))
    pill = bright & ~redbg
    if int(pill.sum()) < max(12, int(0.10 * bright.sum())):
        return None
    if float((S[pill] > 80).mean()) < 0.25:
        return 0
    col = pill & (S > 80)
    hue = float(np.median(H[col]))
    if 30 <= hue < 85:
        return 1
    if 85 <= hue < 110:
        return 2
    if 110 <= hue < 150:
        return 3
    if 14 <= hue < 30:
        return 4
    return None


def _red_level_with_bracket(disp: int | None, bracket: int | None) -> int | None:
    if bracket is not None:
        lo, hi = _RED_BRACKET_OFFSETS[bracket]
        if disp is not None and lo <= disp <= hi:
            return resolve_gear_level("red", disp)
        return resolve_gear_level("red", (lo + hi) // 2)
    if disp is not None:
        return resolve_gear_level("red", disp)
    return None


def classify_quality(icon_bgr: np.ndarray) -> tuple[str, float]:
    if icon_bgr is None or icon_bgr.size == 0:
        return "mythic", 0.0
    h, w = icon_bgr.shape[:2]
    hsv = cv2.cvtColor(icon_bgr, cv2.COLOR_BGR2HSV)
    H, S = hsv[..., 0], hsv[..., 1]
    region = np.zeros((h, w), bool)
    y0, y1 = int(h * 0.28), int(h * 0.72)
    region[y0:y1, :max(1, int(w * 0.16))] = True
    region[y0:y1, int(w * 0.84):] = True
    sat = (S > _Q_SAT) & region
    n = int(sat.sum())
    yellow = int((sat & (H >= _YELLOW_LO) & (H <= _YELLOW_HI)).sum())
    red = int((sat & ((H <= _RED_LO) | (H >= _RED_HI))).sum())
    if yellow == 0 and red == 0:
        return "mythic", 0.0
    if red > yellow:
        return "red", red / max(n, 1)
    return "mythic", yellow / max(n, 1)


def _segments(profile: np.ndarray, min_frac: float = 0.30,
              min_len: int = 40) -> list[tuple[int, int]]:
    if profile.size == 0 or profile.max() == 0:
        return []
    thr = profile.max() * min_frac
    on = profile > thr
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


def _merge_close(centers: list[int], gap: int) -> list[int]:
    if not centers:
        return []
    centers = sorted(centers)
    out = [centers[0]]
    for c in centers[1:]:
        if c - out[-1] < gap:
            out[-1] = (out[-1] + c) // 2
        else:
            out.append(c)
    return out


def _icon_mask(img_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 1] > _ICON_SAT) & (hsv[..., 2] > _ICON_VAL)).astype(np.uint8)


_REF_WIDTH = 1170
_MIN_GEAR_W = 800
_MIN_BLOCK_H = 110
_BLOCK_MERGE_GAP = 45


def _sc(value: float, scale: float, floor: int) -> int:
    return max(floor, int(round(value * scale)))


def _find_leader_blocks(
    mask: np.ndarray, x0: int, x1: int, y0: int, y1: int, scale: float = 1.0,
) -> list[tuple[int, int]]:
    sub = mask[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    runs = [(y0 + a, y0 + b)
            for a, b in _segments(sub.sum(axis=1), 0.20, _sc(30, scale, 8))]
    if not runs:
        return []
    merge_gap = _sc(_BLOCK_MERGE_GAP, scale, 10)
    min_block_h = _sc(_MIN_BLOCK_H, scale, 22)
    merged: list[list[int]] = [list(runs[0])]
    for a, b in runs[1:]:
        if a - merged[-1][1] < merge_gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    blocks = [(t, btm) for t, btm in merged if btm - t >= min_block_h]
    return blocks[:3]


def _locate_in_block(
    mask: np.ndarray, x0: int, x1: int, btop: int, bbot: int, side: str,
    scale: float = 1.0,
) -> dict[str, tuple[int, int]] | None:
    sub = mask[btop:bbot, x0:x1]
    if sub.size == 0:
        return None
    rowruns = _segments(sub.sum(axis=1), 0.20, _sc(25, scale, 6))
    if len(rowruns) >= 2:
        (ta, tb), (ba, bb) = rowruns[0], rowruns[-1]
        top = btop + (ta + tb) // 2
        bot = btop + (ba + bb) // 2
    else:
        h = bbot - btop
        ta, tb, ba, bb = int(h * 0.04), int(h * 0.50), int(h * 0.50), int(h * 0.96)
        top, bot = btop + int(h * 0.26), bbot - int(h * 0.26)

    def _cols_in(ra: int, rb: int) -> list[int]:
        half = mask[btop + ra:btop + rb, x0:x1]
        if half.size == 0:
            return []
        return _merge_close(
            [x0 + (a + b) // 2
             for a, b in _segments(half.sum(axis=0), 0.30, _sc(40, scale, 8))],
            gap=_sc(60, scale, 15),
        )

    top_cols = _cols_in(ta, tb)
    bot_cols = _cols_in(ba, bb)
    if len(top_cols) < 2 or len(bot_cols) < 1:
        return None

    top_cols = sorted(top_cols, reverse=(side != "left"))
    bot_cols = sorted(bot_cols, reverse=(side != "left"))

    out: dict[str, tuple[int, int]] = {}
    if len(top_cols) >= 3:
        out["widget"] = (top_cols[0], top)
        out["head"]   = (top_cols[1], top)
        out["gloves"] = (top_cols[2], top)
    else:
        out["head"]   = (top_cols[0], top)
        out["gloves"] = (top_cols[1], top)
    out["chest"] = (bot_cols[0], bot)
    out["boots"] = (bot_cols[1] if len(bot_cols) >= 2 else bot_cols[0], bot)
    return out


_PLUS_RE = re.compile(r"\+?\s*(\d{1,3})")
_LV_RE = re.compile(r"(\d{1,2})")


def _read_int(strip_bgr: np.ndarray, whitelist: str, regex: re.Pattern,
              lo: int, hi: int) -> tuple[int | None, str]:
    try:
        import pytesseract
    except Exception:
        return None, ""
    if strip_bgr is None or strip_bgr.size == 0:
        return None, ""
    from PIL import ImageOps
    g = ImageOps.grayscale(Image.fromarray(cv2.cvtColor(strip_bgr, cv2.COLOR_BGR2RGB)))
    g = g.resize((g.width * 8, g.height * 8), Image.LANCZOS)
    votes: dict[int, int] = {}
    raw_seen = ""
    for thr in (205, 185, 165):
        b = g.point(lambda p, t=thr: 255 if p > t else 0)
        for psm in (7, 8, 11):
            try:
                txt = pytesseract.image_to_string(
                    b, config=f"--psm {psm} -c tessedit_char_whitelist={whitelist}"
                ).strip()
            except Exception:
                return None, ""
            if txt:
                raw_seen = raw_seen or txt
            m = regex.search(txt)
            if not m:
                continue
            val = int(m.group(1))
            if lo <= val <= hi:
                votes[val] = votes.get(val, 0) + 1
    if not votes:
        return None, raw_seen
    best = max(votes.items(), key=lambda kv: kv[1])
    return (best[0] if best[1] >= 2 else None), raw_seen


def _to_bgr(img, image_override) -> np.ndarray | None:
    if image_override is not None:
        return image_override
    if isinstance(img, np.ndarray):
        return img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if isinstance(img, str):
        return cv2.imread(img)
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def ocr_gear(
    img: "Image.Image | str | np.ndarray",
    side: Literal["left", "right"] = "left",
    *,
    read_numbers: bool = True,
    _token_override: list[dict] | None = None,
    _image_override: np.ndarray | None = None,
) -> GearOCRResult:
    result = GearOCRResult()
    img_bgr = _to_bgr(img, _image_override)
    if img_bgr is None:
        result.error = "Could not read the screenshot image."
        return result
    Himg, Wimg = img_bgr.shape[:2]

    if Wimg < _MIN_GEAR_W:
        result.error = (
            f"This screenshot is too small to read gear reliably (only "
            f"{Wimg}px wide; a full-resolution KingShot screenshot is around "
            f"1100px or more). Upload the original screenshot from your "
            f"phone's gallery — not a copy sent through a chat app, which "
            f"downscales it."
        )
        return result

    if _token_override is not None:
        tokens = _token_override
        pil = None
    else:
        pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        tokens = _ocr_tokens(preprocess_image(pil))

    y_top = _find_hero_comparison_y(tokens)
    if y_top is None and pil is not None:
        hc_tokens = _ocr_tokens(clahe_rgb(pil))
        hc_y = _find_hero_comparison_y(hc_tokens)
        if hc_y is not None:
            y_top, tokens = hc_y, hc_tokens
    if y_top is None:
        result.error = (
            "Could not find the 'Hero Comparison' header — upload a "
            "battle-report screenshot that shows the Hero Comparison section."
        )
        return result
    frac = _LEFT_CLUSTER if side == "left" else _RIGHT_CLUSTER
    cx0, cx1 = int(Wimg * frac[0]), int(Wimg * frac[1])
    mask = _icon_mask(img_bgr)
    scale = Wimg / float(_REF_WIDTH)
    icon_s = max(24, int(Wimg * 0.07))

    search_y1 = min(Himg, y_top + int(Himg * 0.45))
    y_troop = _find_troop_power_y(tokens)
    if y_troop is not None and y_top < y_troop < search_y1:
        search_y1 = y_troop
    blocks = _find_leader_blocks(mask, cx0, cx1, y_top, search_y1, scale)
    if not blocks:
        result.error = (
            "No gear clusters detected next to the Hero Comparison portraits."
        )
        return result

    for r, (btop, bbot) in enumerate(blocks):
        located = _locate_in_block(mask, cx0, cx1, btop, bbot, side, scale)
        if located is None:
            result.warnings.append(
                f"Could not locate the gear cluster for leader row {r + 1} on "
                f"the {side} side; fill that hero's gear manually."
            )
            continue
        has_widget = "widget" in located
        if not has_widget:
            result.warnings.append(
                f"Leader row {r + 1} on the {side} side shows gear but no "
                f"widget — that's an epic hero used as a leader, which isn't "
                f"supported yet. Skipped its gear."
            )
            result.cells.append(GearCell(
                row_index=r, has_widget=False, is_epic_no_widget=True,
                pieces={}, needs_review=True,
            ))
            continue

        pieces: dict[str, GearPieceCell] = {}
        for slot in GEAR_SLOTS:
            cx, cy = located[slot]
            icon = img_bgr[cy - icon_s // 2:cy + icon_s // 2,
                           cx - icon_s // 2:cx + icon_s // 2]
            quality, qconf = classify_quality(icon)
            level = mastery = None
            raw_l = raw_m = ""
            if read_numbers and icon.size:
                h = icon.shape[0]
                top_strip = icon[0:int(h * 0.40), :]
                bot_strip = icon[int(h * 0.66):, :]
                disp, raw_l = _read_int(top_strip, "0123456789+", _PLUS_RE, 0, 100)
                if quality == "red":
                    level = _red_level_with_bracket(disp, _red_level_bracket(icon))
                else:
                    level = resolve_gear_level(quality, disp) if disp is not None else None
                mastery, raw_m = _read_int(bot_strip, "Lv.0123456789", _LV_RE, 0, 20)
            pieces[slot] = GearPieceCell(
                slot=slot, quality=quality, level=level, mastery=mastery,
                quality_conf=qconf, needs_review=True,
                raw_level=raw_l, raw_mastery=raw_m,
            )

        widget_level = None
        if read_numbers:
            wcx, wcy = located["widget"]
            wic = img_bgr[wcy - icon_s // 2:wcy + icon_s // 2,
                          wcx - icon_s // 2:wcx + icon_s // 2]
            if wic.size:
                wtop = wic[0:int(wic.shape[0] * 0.45), :]
                widget_level, _ = _read_int(wtop, "0123456789+", _PLUS_RE, 0, 10)

        result.cells.append(GearCell(
            row_index=r, has_widget=True, widget_level=widget_level,
            pieces=pieces, needs_review=True,
        ))

    if not result.cells and not result.warnings:
        result.error = (
            "No gear clusters detected next to the Hero Comparison portraits."
        )
    return result


__all__ = [
    "GearPieceCell", "GearCell", "GearOCRResult",
    "ocr_gear", "classify_quality", "resolve_gear_level", "GEAR_SLOTS",
]
