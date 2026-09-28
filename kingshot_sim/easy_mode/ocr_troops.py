from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image, ImageOps

from ..config.fighter import TroopGroup, TroopRoster
from ..data.reference import make_tier_label
from .ocr import _ocr_tokens, DEFAULT_CONFIDENCE_THRESHOLD


_LEVEL_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d)(?!\d)")

_COUNT_RE = re.compile(r"^[1-9]\d{0,2}(?:,\d{3})+$")

_STAR_RE = re.compile(r"^[1-8]$")

CLASS_ORDER: tuple[str, ...] = ("inf", "cav", "arc")

_BASE_TIER_BY_INT: dict[int, str] = {
    6: "T6",
    9: "T9",
    10: "T10",
}


_UPSCALE_TRIGGER_W: int = 1100
_UPSCALE_TARGET_W: int = 1600
_UPSCALE_MAX: float = 4.0

_MIN_RELIABLE_W: int = 800


def _preprocess_troops_for_ocr(img: Image.Image) -> tuple[Image.Image, float]:
    if img.mode != "RGB":
        img = img.convert("RGB")
    gray = ImageOps.grayscale(img)
    w = gray.width
    scale = 1.0
    if w < _UPSCALE_TRIGGER_W:
        gray = ImageOps.autocontrast(gray, cutoff=1)
        scale = min(_UPSCALE_MAX, max(2.0, _UPSCALE_TARGET_W / w))
        gray = gray.resize(
            (round(gray.width * scale), round(gray.height * scale)),
            Image.LANCZOS,
        )
    return gray.convert("RGB"), scale


_LEVEL_CROP_UPSCALE: int = 6
_LEVEL_CROP_THRESHOLDS: tuple[int, ...] = (200, 175)
_LEVEL_CROP_PSMS: tuple[int, ...] = (7, 11)


def _recover_level_for_count(img: Image.Image, count: dict) -> dict | None:
    cx, cy, cw, ch = count["x"], count["y"], count["w"], count["h"]
    x0 = max(0, cx - 15)
    y0 = max(0, cy - int(ch * 1.6) - 6)
    x1 = min(img.width, cx + cw + 15)
    y1 = max(y0 + 1, cy - 4)
    band = img.crop((x0, y0, x1, y1))
    if band.width < 2 or band.height < 2:
        return None
    gray = ImageOps.grayscale(band).resize(
        (band.width * _LEVEL_CROP_UPSCALE, band.height * _LEVEL_CROP_UPSCALE),
        Image.LANCZOS,
    )
    for thr in _LEVEL_CROP_THRESHOLDS:
        binar = gray.point(lambda p, t=thr: 255 if p > t else 0).convert("RGB")
        for psm in _LEVEL_CROP_PSMS:
            for t in _ocr_tokens(binar, config=f"--psm {psm}"):
                m = _LEVEL_RE.search(t["text"])
                if not m:
                    continue
                raw_value = float(f"{m.group(1)}.{m.group(2)}")
                int_part = int(raw_value + 0.5)
                if int_part not in _BASE_TIER_BY_INT:
                    continue
                return {
                    "text": t["text"],
                    "conf": t["conf"],
                    "x": cx,
                    "y": y0,
                    "w": cw,
                    "h": y1 - y0,
                    "value": f"{m.group(1)}.{m.group(2)}",
                    "int_part": int_part,
                }
    return None


@dataclass
class TroopCell:
    klass: Literal["inf", "cav", "arc"]
    tier: str
    level_label: str
    star: int
    count: int
    confidence: float
    needs_review: bool = False
    raw_level: str = ""
    raw_count: str = ""


@dataclass
class TroopOCRResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    cells: list[TroopCell] = field(default_factory=list)
    roster: TroopRoster | None = None
    n_low_confidence: int = 0

    def is_ok(self) -> bool:
        return self.error is None and self.roster is not None


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


def _find_troop_row_by_labels(tokens: list[dict]) -> int | None:
    matches: list[int] = []
    seen_classes: set[str] = set()
    for t in tokens:
        txt = t["text"].lower()
        for klass, needle in (("inf", "infantr"),
                               ("cav", "cavalr"),
                               ("arc", "archer")):
            if needle in txt and klass not in seen_classes:
                matches.append(t["y"])
                seen_classes.add(klass)
                break
    if len(matches) < 2:
        return None
    return min(matches) - 80


def _find_anchor_y(tokens: list[dict]) -> int | None:
    y = _find_phrase_y(tokens, "troop", "power")
    if y is not None:
        return y
    y = _find_phrase_y(tokens, "troop", "comparison")
    if y is not None:
        return y
    return _find_troop_row_by_labels(tokens)


def _find_stat_bonuses_y(tokens: list[dict]) -> int | None:
    return _find_phrase_y(tokens, "stat", "bonuses")


def _extract_levels(tokens: list[dict], y_min: int, y_max: int) -> list[dict]:
    out: list[dict] = []
    for t in tokens:
        if not (y_min <= t["y"] <= y_max):
            continue
        m = _LEVEL_RE.search(t["text"])
        if not m:
            continue
        raw_value = float(f"{m.group(1)}.{m.group(2)}")
        int_part = int(raw_value + 0.5)
        if int_part not in _BASE_TIER_BY_INT:
            continue
        out.append({
            **t,
            "value": f"{m.group(1)}.{m.group(2)}",
            "int_part": int_part,
        })
    out.sort(key=lambda e: e["x"])
    return out


def _extract_counts(tokens: list[dict], y_min: int, y_max: int) -> list[dict]:
    out = []
    for t in tokens:
        if not (y_min <= t["y"] <= y_max):
            continue
        if not _COUNT_RE.fullmatch(t["text"]):
            continue
        out.append({**t, "count": int(t["text"].replace(",", ""))})
    out.sort(key=lambda e: e["x"])
    return out


def _nearest_count_for_level(level: dict, counts: list[dict], max_dx: int) -> dict | None:
    best = None
    best_dx = max_dx + 1
    for c in counts:
        dx = abs(c["x"] - level["x"])
        if dx < best_dx:
            best_dx = dx
            best = c
    return best


def _star_for_level(level: dict, tokens: list[dict], slot_w: int) -> int:
    lx, ly = level["x"], level["y"]
    candidates: list[tuple[int, int, int]] = []
    half_w = max(20, slot_w // 2)
    for t in tokens:
        if not _STAR_RE.fullmatch(t["text"]):
            continue
        dy = ly - t["y"]
        dx = t["x"] - lx
        if dy <= 0 or dy > slot_w:
            continue
        if abs(dx) > half_w:
            continue
        candidates.append((abs(dx), dy, int(t["text"])))
    if not candidates:
        return 0
    candidates.sort()
    return candidates[0][2]


def _resolve_tier(int_part: int, star: int) -> tuple[str, bool]:
    base = _BASE_TIER_BY_INT.get(int_part)
    if base is None:
        return "", True
    if base != "T10":
        return base, False
    if star == 0:
        return "T10", True
    if 1 <= star <= 8:
        return make_tier_label(10, star), False
    return "T10", True


def ocr_troops(
    img: Image.Image | str,
    side: Literal["left", "right"] = "left",
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    *,
    _token_override: list[dict] | None = None,
    _image_width: int | None = None,
) -> TroopOCRResult:
    source_img: Image.Image | None = None
    if _token_override is not None:
        tokens = _token_override
        image_width = _image_width if _image_width is not None else 1000
    else:
        if isinstance(img, str):
            img = Image.open(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        source_img = img
        processed, scale = _preprocess_troops_for_ocr(img)
        tokens = _ocr_tokens(processed)
        if scale != 1.0:
            inv = 1.0 / scale
            for t in tokens:
                t["x"] = int(round(t["x"] * inv))
                t["y"] = int(round(t["y"] * inv))
                t["w"] = int(round(t["w"] * inv))
                t["h"] = int(round(t["h"] * inv))
        image_width = img.size[0]

    result = TroopOCRResult()

    anchor_y = _find_anchor_y(tokens)
    if anchor_y is None:
        result.error = (
            "Could not find the 'Troop Power Comparison' header in the "
            "screenshot. Make sure you upload a battle-report screenshot that "
            "shows the troop comparison row."
        )
        return result

    lower_y = _find_stat_bonuses_y(tokens)
    if lower_y is None or lower_y <= anchor_y:
        lower_y = anchor_y + 1200

    y_min = anchor_y + 30
    y_max = lower_y - 10

    levels = _extract_levels(tokens, y_min, y_max)
    counts = _extract_counts(tokens, y_min, y_max)

    if source_img is not None and counts:
        if len(counts) >= 2:
            xs = sorted(c["x"] for c in counts)
            gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a > 0]
            tol = (min(gaps) / 2.0) if gaps else 60.0
        else:
            tol = 60.0
        covered = [L["x"] + L["w"] / 2.0 for L in levels]
        recovered: list[dict] = []
        for c in counts:
            ccx = c["x"] + c["w"] / 2.0
            if any(abs(ccx - lx) <= tol for lx in covered):
                continue
            rl = _recover_level_for_count(source_img, c)
            if rl is not None:
                recovered.append(rl)
                covered.append(rl["x"] + rl["w"] / 2.0)
        if recovered:
            levels = sorted(levels + recovered, key=lambda L: L["x"])

    if len(levels) == 0:
        if image_width < _MIN_RELIABLE_W:
            result.error = (
                f"This screenshot is too small to read reliably (only "
                f"{image_width}px wide; a full-resolution KingShot screenshot "
                f"is around 1100px or more). At this size the 'Lv. X.Y' troop "
                f"level and the TG corner badge are below what OCR can read. "
                f"Please upload the original screenshot straight from your "
                f"phone's gallery — not a copy sent through a chat app "
                f"(Discord / WhatsApp / etc.), which downscales it."
            )
            return result
        result.error = (
            "Could not find any troop level labels in the screenshot. "
            "Make sure the 'Troop Power Comparison' panel is fully "
            "visible and the 'Lv. X.Y' text on each troop tile is "
            "readable (not blurry / not covered by overlays)."
        )
        return result

    if source_img is not None and image_width < _MIN_RELIABLE_W:
        result.warnings.append(
            f"This screenshot is low-resolution ({image_width}px wide), so the "
            f"troop counts and tiers may be misread. Verify every value below "
            f"against the screenshot, or re-upload the original full-resolution "
            f"capture for a clean read."
        )

    if len(levels) > 6:
        median_y = sorted(L["y"] for L in levels)[len(levels) // 2]
        levels.sort(key=lambda L: (abs(L["y"] - median_y), L["x"]))
        levels = levels[:6]
        levels.sort(key=lambda L: L["x"])
        result.warnings.append(
            f"Found {len(levels)} extra level-like tokens in the troop band; "
            f"used the 6 closest to the median row."
        )

    midline = image_width / 2
    left_levels  = [L for L in levels if L["x"] + L["w"] / 2 < midline]
    right_levels = [L for L in levels if L["x"] + L["w"] / 2 >= midline]

    if (side == "left" and not left_levels) or (side == "right" and not right_levels):
        result.error = (
            f"No troop tiles detected on the {side} side. The screenshot "
            f"might be cropped horizontally or the 'Lv. X.Y' text is "
            f"unreadable on that half."
        )
        return result

    if len(left_levels) > 3:
        left_levels.sort(key=lambda L: -L["conf"])
        left_levels = left_levels[:3]
        left_levels.sort(key=lambda L: L["x"])
        result.warnings.append("Found > 3 troop tiles on the left side; "
                                "kept the 3 highest-confidence.")
    if len(right_levels) > 3:
        right_levels.sort(key=lambda L: -L["conf"])
        right_levels = right_levels[:3]
        right_levels.sort(key=lambda L: L["x"])
        result.warnings.append("Found > 3 troop tiles on the right side; "
                                "kept the 3 highest-confidence.")

    all_xs = sorted(L["x"] for L in (left_levels + right_levels))
    if len(all_xs) >= 2:
        slot_w = max(80, (all_xs[-1] - all_xs[0]) // max(len(all_xs) - 1, 1))
    else:
        slot_w = 100

    chosen_levels = left_levels if side == "left" else right_levels

    side_counts = [
        c for c in counts
        if (c["x"] + c["w"] / 2 < midline) == (side == "left")
    ]

    n_low = 0
    cells: list[TroopCell] = []
    roster_groups: dict[str, list[TroopGroup]] = {"inf": [], "cav": [], "arc": []}

    for slot_idx, lvl in enumerate(chosen_levels):
        klass = CLASS_ORDER[slot_idx]
        count_tok = _nearest_count_for_level(lvl, side_counts, max_dx=slot_w)
        star = _star_for_level(lvl, tokens, slot_w)
        tier, tier_review = _resolve_tier(lvl["int_part"], star)

        if count_tok is None:
            cells.append(TroopCell(
                klass=klass, tier=tier, level_label=lvl["value"],
                star=star, count=0, confidence=lvl["conf"],
                needs_review=True, raw_level=lvl["text"], raw_count="",
            ))
            n_low += 1
            result.warnings.append(
                f"Could not find a troop count near the {klass} slot on the "
                f"{side} side; cell flagged for manual entry."
            )
            continue

        conf = min(lvl["conf"], count_tok["conf"])
        needs_review = tier_review or conf < confidence_threshold
        if needs_review:
            n_low += 1

        cell = TroopCell(
            klass=klass, tier=tier, level_label=lvl["value"], star=star,
            count=count_tok["count"], confidence=conf,
            needs_review=needs_review,
            raw_level=lvl["text"], raw_count=count_tok["text"],
        )
        cells.append(cell)

        if tier:
            roster_groups[klass].append(TroopGroup(tier=tier, count=count_tok["count"]))

    result.cells = cells
    result.n_low_confidence = n_low
    result.roster = TroopRoster(
        infantry=tuple(roster_groups["inf"]),
        cavalry=tuple(roster_groups["cav"]),
        archer=tuple(roster_groups["arc"]),
    )
    return result


__all__ = [
    "TroopCell",
    "TroopOCRResult",
    "ocr_troops",
    "CLASS_ORDER",
]
