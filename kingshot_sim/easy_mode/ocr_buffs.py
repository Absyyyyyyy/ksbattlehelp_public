from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from PIL import Image, ImageOps

from .ocr import _ocr_tokens, preprocess_image, clahe_rgb


def _blob_has_header(blob: str) -> bool:
    return "special" in blob and "bonuses" in blob


_BUFF_MARKERS: tuple[str, ...] = (
    "squad", "territory", "rally", "turret", "appointment", "penalty", "enemy",
)


def _blob_has_buff_markers(blob: str) -> bool:
    b = blob.lower()
    return any(m in b for m in _BUFF_MARKERS)


def _has_buff_header(tokens: list[dict]) -> bool:
    return _blob_has_header(" ".join(t["text"].lower() for t in tokens))


def _detect_header(pil: "Image.Image", tokens: list[dict]) -> bool:
    blob = " ".join(t["text"].lower() for t in tokens)
    if _blob_has_header(blob) or _blob_has_buff_markers(blob):
        return True
    import pytesseract
    gray = preprocess_image(pil)
    try:
        s = pytesseract.image_to_string(gray, config="--psm 6").lower()
        if _blob_has_header(s) or _blob_has_buff_markers(s):
            return True
    except Exception:
        pass
    try:
        up = gray.resize((int(gray.width * 1.6), int(gray.height * 1.6)), Image.LANCZOS)
        s = pytesseract.image_to_string(up, config="--psm 11").lower()
        if _blob_has_header(s) or _blob_has_buff_markers(s):
            return True
    except Exception:
        pass
    try:
        cl = clahe_rgb(pil)
        if _has_buff_header(_ocr_tokens(cl)):
            return True
        cu = cl.resize((int(cl.width * 1.6), int(cl.height * 1.6)), Image.LANCZOS)
        if _blob_has_header(pytesseract.image_to_string(cu, config="--psm 11").lower()):
            return True
    except Exception:
        pass
    return False


_STAT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("lethality", "let"),
    ("attack", "atk"),
    ("defense", "def"),
    ("defence", "def"),
    ("health", "hp"),
)

_ENEMY_MARKERS: tuple[str, ...] = ("enemy", "penalty")

_CLASSES: tuple[str, ...] = ("inf", "cav", "arc")
_STATS: tuple[str, ...] = ("atk", "def", "let", "hp")


def _clean_label(raw: str) -> str:
    s = raw.lower().replace("’", "'").replace("`", "'")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(s.split())


def classify_label(raw: str) -> tuple[str, str] | None:
    cl = _clean_label(raw)
    if not cl:
        return None
    stat = None
    for kw, st in _STAT_KEYWORDS:
        if kw in cl:
            stat = st
            break
    if stat is None:
        return None
    polarity = "enemy" if any(m in cl for m in _ENEMY_MARKERS) else "own"
    return stat, polarity


@dataclass
class BuffLineCell:
    label: str
    raw_label: str
    stat: str
    polarity: str
    value_pct: float
    confidence: float
    needs_review: bool = False


@dataclass
class BuffOCRResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    lines: list[BuffLineCell] = field(default_factory=list)
    n_low_confidence: int = 0

    def is_ok(self) -> bool:
        return self.error is None and len(self.lines) > 0


@dataclass
class BuffAggregate:
    own: dict[str, float] = field(default_factory=dict)
    enemy: dict[str, float] = field(default_factory=dict)
    lines: list[BuffLineCell] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    n_low_confidence: int = 0

    def own_get(self, klass: str, stat: str) -> float:
        return float(self.own.get(f"{klass}_{stat}", 0.0))

    def enemy_get(self, klass: str, stat: str) -> float:
        return float(self.enemy.get(f"{klass}_{stat}", 0.0))


_VALUE_RE = re.compile(r"([+-])?\s*(\d{1,3})(?:\.(\d))?\s*%")
_INK_LUM_MAX = 150
_INK_SAT_MIN = 55


def _ink_binary(crop: Image.Image) -> Image.Image:
    arr = np.asarray(crop.convert("RGB")).astype(np.int32)
    R, G, B = arr[..., 0], arr[..., 1], arr[..., 2]
    lum = 0.299 * R + 0.587 * G + 0.114 * B
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)
    sat = mx - mn
    ink = (lum < _INK_LUM_MAX) | (sat > _INK_SAT_MIN)
    return Image.fromarray(np.where(ink, 0, 255).astype(np.uint8))


def _parse_value(txt: str) -> tuple[str, float] | None:
    m = _VALUE_RE.search(txt)
    if not m:
        return None
    sign = m.group(1) or "+"
    val = float(f"{m.group(2)}.{m.group(3) or '0'}")
    if val == 0.0:
        sign = "+"
    return sign, val


def read_value_cell(
    img: Image.Image, x0: int, x1: int, cy: int, half: int
) -> tuple[float | None, float]:
    import pytesseract

    y0 = max(0, cy - half)
    y1 = cy + half
    crop = img.crop((x0, y0, x1, y1))
    if crop.width <= 0 or crop.height <= 0:
        return None, 0.0
    b = _ink_binary(crop)
    b = b.resize((b.width * 4, b.height * 4), Image.LANCZOS)

    mags: dict[float, int] = {}
    signs: dict[str, int] = {}
    passes = 0
    for psm in (11, 7, 6, 4):
        try:
            txt = pytesseract.image_to_string(
                b, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789+-.%"
            ).strip()
        except Exception:
            continue
        passes += 1
        r = _parse_value(txt)
        if r is None:
            continue
        sign, val = r
        mags[val] = mags.get(val, 0) + 1
        signs[sign] = signs.get(sign, 0) + 1
    if not mags:
        return None, 0.0

    for big in [m for m in list(mags) if m >= 100.0]:
        small = big - (int(big // 100) * 100)
        if small in mags and small < 100.0:
            mags[small] += mags.pop(big)

    best_count = max(mags.values())
    val = min(m for m, c in mags.items() if c == best_count)
    sign = max(signs.items(), key=lambda kv: kv[1])[0]
    signed = val if (val == 0.0 or sign == "+") else -val
    conf = mags[val] / max(passes, 1)
    return signed, conf


_LABEL_KEYWORDS: tuple[str, ...] = (
    "attack", "defense", "defence", "lethality", "health", "bonus",
    "enemy", "defender", "rally", "penalty", "turret", "appointment",
    "territory", "squad", "based", "pet", "skill",
)


def _label_tokens(tokens: list[dict], w: int) -> list[dict]:
    out = []
    for t in tokens:
        low = t["text"].lower()
        if t["conf"] < 40:
            continue
        if not re.search(r"[a-z]", low):
            continue
        if len(low) < 3:
            continue
        if not any(k in low for k in _LABEL_KEYWORDS):
            continue
        out.append(t)
    return out


def _group_rows(label_toks: list[dict], h: int) -> list[dict]:
    if not label_toks:
        return []
    toks = sorted(label_toks, key=lambda t: t["y"])
    gap = max(28, h // 70)
    clusters: list[list[dict]] = [[toks[0]]]
    for t in toks[1:]:
        if t["y"] - clusters[-1][-1]["y"] < gap:
            clusters[-1].append(t)
        else:
            clusters.append([t])
    rows = []
    for cl in clusters:
        cy = int(np.mean([t["y"] + t["h"] / 2 for t in cl]))
        label = " ".join(t["text"] for t in sorted(cl, key=lambda t: t["x"]))
        rows.append({"cy": cy, "label": label})
    return rows


_LEFT_BAND = (0.04, 0.30)
_RIGHT_BAND = (0.70, 0.96)

_REVIEW_CONF = 0.66

_MIN_BUFF_W = 800


def ocr_buffs(
    img: "Image.Image | str | np.ndarray",
    side: Literal["left", "right"] = "left",
    *,
    _token_override: list[dict] | None = None,
    _image_override: Image.Image | None = None,
) -> BuffOCRResult:
    result = BuffOCRResult()

    pil = _image_override
    if pil is None:
        if isinstance(img, np.ndarray):
            pil = Image.fromarray(img)
        elif isinstance(img, str):
            try:
                pil = Image.open(img)
            except Exception as e:
                result.error = f"Could not read image at {img!r}: {e}"
                return result
        else:
            pil = img
    if pil.mode != "RGB":
        pil = pil.convert("RGB")
    w, h = pil.size

    if _token_override is None and w < _MIN_BUFF_W:
        result.error = (
            f"This screenshot is too small to read buffs reliably (only {w}px "
            f"wide; a full-resolution KingShot screenshot is around 1100px or "
            f"more). Upload the original from your phone's gallery — not a copy "
            f"sent through a chat app, which downscales it."
        )
        return result

    if _token_override is not None:
        tokens = _token_override
    else:
        tokens = _ocr_tokens(preprocess_image(pil))

    header_ok = (_has_buff_header(tokens) if _token_override is not None
                 else _detect_header(pil, tokens))
    if not header_ok:
        result.error = (
            "Could not find the 'Notes on Special Bonuses' header. Open the "
            "battle report, tap the (i) next to 'Stat Bonuses' to show the "
            "'Special Bonuses' breakdown, and screenshot that popup."
        )
        return result

    rows = _group_rows(_label_tokens(tokens, w), h)
    if not rows and _token_override is None:
        import pytesseract
        retry = _ocr_tokens(preprocess_image(pil), config="--psm 6")
        rows = _group_rows(_label_tokens(retry, w), h)
        if rows:
            tokens = retry
    if not rows:
        result.warnings.append(
            "Found the Special Bonuses header but no buff lines — the popup "
            "may be empty or cut off. Try re-taking the screenshot."
        )
        return result

    half = max(30, h // 80)
    band = _LEFT_BAND if side == "left" else _RIGHT_BAND
    vx0, vx1 = int(w * band[0]), int(w * band[1])

    n_low = 0
    for row in rows:
        cls = classify_label(row["label"])
        if cls is None:
            continue
        stat, polarity = cls
        value, conf = read_value_cell(pil, vx0, vx1, row["cy"], half)
        if value is None:
            result.warnings.append(
                f"Could not read the {side} value for "
                f"'{_clean_label(row['label'])}' — enter it manually."
            )
            continue
        needs_review = conf < _REVIEW_CONF
        if needs_review:
            n_low += 1
        result.lines.append(BuffLineCell(
            label=_clean_label(row["label"]),
            raw_label=row["label"],
            stat=stat,
            polarity=polarity,
            value_pct=value,
            confidence=conf,
            needs_review=needs_review,
        ))

    result.n_low_confidence = n_low
    if not result.lines and not result.warnings:
        result.warnings.append(
            "No buff lines could be parsed from this screenshot."
        )
    return result


def merge_buff_results(results: list[BuffOCRResult]) -> BuffAggregate:
    agg = BuffAggregate(
        own={f"{k}_{s}": 0.0 for k in _CLASSES for s in _STATS},
        enemy={f"{k}_{s}": 0.0 for k in _CLASSES for s in _STATS},
    )

    best: dict[str, BuffLineCell] = {}
    for res in results:
        for w in res.warnings:
            agg.warnings.append(w)
        for line in res.lines:
            prev = best.get(line.label)
            if prev is None or line.confidence > prev.confidence:
                best[line.label] = line

    for line in best.values():
        target = agg.own if line.polarity == "own" else agg.enemy
        for klass in _CLASSES:
            target[f"{klass}_{line.stat}"] += line.value_pct
        agg.lines.append(line)
        if line.needs_review:
            agg.n_low_confidence += 1

    agg.lines.sort(key=lambda l: (l.polarity, l.stat, l.label))
    return agg


__all__ = [
    "BuffLineCell",
    "BuffOCRResult",
    "BuffAggregate",
    "ocr_buffs",
    "merge_buff_results",
    "classify_label",
    "read_value_cell",
]
