from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal

import pytesseract
from PIL import Image, ImageOps

from .peeling import VisibleAggregate


DEFAULT_CONFIDENCE_THRESHOLD: float = 90.0

STAT_ORDER: tuple[tuple[str, str], ...] = (
    ("inf", "atk"), ("inf", "def"), ("inf", "let"), ("inf", "hp"),
    ("cav", "atk"), ("cav", "def"), ("cav", "let"), ("cav", "hp"),
    ("arc", "atk"), ("arc", "def"), ("arc", "let"), ("arc", "hp"),
)


@dataclass
class OCRCell:
    klass: str
    stat: str
    value_pct: float
    confidence: float
    raw_text: str
    needs_review: bool = False


@dataclass
class OCRResult:
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    cells: list[OCRCell] = field(default_factory=list)
    visible: VisibleAggregate | None = None
    n_low_confidence: int = 0

    def is_ok(self) -> bool:
        return self.error is None and self.visible is not None


def preprocess_image(img: Image.Image) -> Image.Image:
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    return ImageOps.grayscale(img).convert("RGB")


def clahe_rgb(img: Image.Image) -> Image.Image:
    import cv2
    import numpy as np
    arr = np.array(img.convert("L"))
    enh = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(arr)
    return Image.fromarray(enh).convert("RGB")


_PERCENT_TOKEN = re.compile(r"\+?(\d+(?:\.\d+)?)%")


def debug_ocr_tokens(img: "Image.Image | str") -> list[dict]:
    if isinstance(img, str):
        img = Image.open(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return _ocr_tokens(preprocess_image(img))


def _ocr_tokens(img: Image.Image, config: str = "") -> list[dict]:
    data = pytesseract.image_to_data(
        img, output_type=pytesseract.Output.DICT, config=config
    )
    n = len(data["text"])
    out = []
    for i in range(n):
        txt = data["text"][i].strip()
        if not txt:
            continue
        conf_raw = data["conf"][i]
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue
        out.append({
            "text": txt,
            "conf": conf,
            "x": int(data["left"][i]),
            "y": int(data["top"][i]),
            "w": int(data["width"][i]),
            "h": int(data["height"][i]),
        })
    return out


def _has_header(tokens: list[dict]) -> bool:
    blob = " ".join(t["text"].lower() for t in tokens)
    return "stat" in blob and "bonuses" in blob


def _has_mail_id(tokens: list[dict]) -> bool:
    blob = " ".join(t["text"].lower() for t in tokens)
    return "mail" in blob and "id" in blob


def _percent_tokens_by_side(
    tokens: list[dict], image_width: int
) -> tuple[list[dict], list[dict]]:
    left, right = [], []
    midline = image_width / 2
    for t in tokens:
        m = _PERCENT_TOKEN.fullmatch(t["text"])
        if not m:
            continue
        value = float(m.group(1))
        entry = {**t, "value": value}
        if t["x"] + t["w"] / 2 < midline:
            left.append(entry)
        else:
            right.append(entry)
    left.sort(key=lambda e: e["y"])
    right.sort(key=lambda e: e["y"])
    return left, right


def ocr_battle_report(
    img: Image.Image | str,
    side: Literal["left", "right"] = "left",
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> OCRResult:
    if isinstance(img, str):
        img = Image.open(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    processed = preprocess_image(img)
    tokens = _ocr_tokens(processed)

    result = OCRResult()

    if not _has_header(tokens):
        result.error = (
            "Could not find the 'Stat Bonuses' header in the screenshot. "
            "Make sure you upload a battle-report screenshot that shows the "
            "stat-bonuses panel."
        )
        return result

    left_pcts, right_pcts = _percent_tokens_by_side(tokens, image_width=img.size[0])

    if len(left_pcts) < 12 or len(right_pcts) < 12:
        result.error = (
            f"Incomplete stat panel — found {len(left_pcts)} values on the left "
            f"and {len(right_pcts)} on the right, expected 12 on each side. "
            f"The screenshot is probably cropped: make sure the panel is fully "
            f"visible down to 'Archer Health' before taking it."
        )
        return result

    chosen = left_pcts if side == "left" else right_pcts
    if len(chosen) > 14:
        result.warnings.append(
            f"OCR found {len(chosen)} percentage values on the {side} side "
            f"(expected 12). Using the first 12 by top-to-bottom order; "
            f"review the cells flagged for confirmation."
        )
    chosen = chosen[:12]

    if not _has_mail_id(tokens):
        result.warnings.append(
            "Could not find the 'Mail ID' footer in the screenshot. The "
            "result should still be usable, but for safety make sure the "
            "whole panel is visible — including the Mail ID at the bottom."
        )

    cells: list[OCRCell] = []
    visible_kwargs: dict[str, float] = {}
    n_low_conf = 0
    for (klass, stat), tok in zip(STAT_ORDER, chosen):
        needs_review = tok["conf"] < confidence_threshold
        if needs_review:
            n_low_conf += 1
        cells.append(OCRCell(
            klass=klass, stat=stat,
            value_pct=tok["value"],
            confidence=tok["conf"],
            raw_text=tok["text"],
            needs_review=needs_review,
        ))
        visible_kwargs[f"{klass}_{stat}_pct"] = tok["value"]

    result.cells = cells
    result.n_low_confidence = n_low_conf
    result.visible = VisibleAggregate(**visible_kwargs)
    return result


__all__ = [
    "OCRCell",
    "OCRResult",
    "ocr_battle_report",
    "preprocess_image",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "STAT_ORDER",
]
