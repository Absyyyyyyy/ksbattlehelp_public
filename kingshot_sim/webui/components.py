from __future__ import annotations
import base64
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence
import streamlit as st


_ASSETS_DIR = Path(__file__).parent / "assets"


@lru_cache(maxsize=4)
def _asset_data_uri(filename: str, mime: str) -> str:
    p = _ASSETS_DIR / filename
    if not p.exists():
        return ""
    data = p.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def logo_data_uri() -> str:
    return _asset_data_uri("logo.jpg", "image/jpeg")


def favicon_data_uri() -> str:
    return _asset_data_uri("favicon.png", "image/png")


def favicon_path() -> Optional[str]:
    p = _ASSETS_DIR / "favicon.png"
    return str(p) if p.exists() else None


def og_image_data_uri() -> str:
    return _asset_data_uri("logo_og.jpg", "image/jpeg")


@lru_cache(maxsize=64)
def hero_portrait_data_uri(hero: str) -> str:
    from kingshot_sim.data.hero_portraits import portrait_path_for
    p = portrait_path_for(hero)
    if p is None or not p.exists():
        return ""
    return f"data:image/jpeg;base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def hero_portrait_html(hero: str, size: int = 44, cls: Optional[str] = None,
                       ring: bool = True) -> str:
    uri = hero_portrait_data_uri(hero)
    if not uri:
        return class_chip_html(cls) if cls else ""
    color = _CLASS_COLORS.get(cls or "", "var(--ks-border)")
    border = f"2px solid {color}" if ring else "1px solid var(--ks-border)"
    return (
        f'<img src="{uri}" alt="{hero}" width="{size}" height="{size}" '
        f'style="border-radius:8px;object-fit:cover;border:{border};'
        f'flex:0 0 auto;display:inline-block;vertical-align:middle;" />'
    )


_CLASS_ICONS = {
    "Inf": '<path d="M8 1.5l5 2v4.2c0 3.4-2.2 5.8-5 6.8-2.8-1-5-3.4-5-6.8V3.5l5-2z" '
              'stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" fill="none" />'
              '<path d="M8 5.5v4M6 7.5h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />',
    "Cav": '<path d="M4 14h8M5 12h6c.3-1.8-.4-3.8-1.8-5.1-.6-.5-1.1-1-1.2-1.7C7.9 4 8.2 3 9.5 2.5 '
              '7 1.8 4.8 3 3.6 5.2 3 6.3 3.5 7.2 4.5 7.5c.6.2.7.6.5 1L4 10.5c-.4.6-.2 1.5 1 1.5z" '
              'stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" fill="none" />'
              '<circle cx="6.8" cy="5.5" r=".55" fill="currentColor" />',
    "Arc": '<path d="M3 13C8.5 13 12.5 9 12.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none" />'
              '<path d="M3 13l3-3M3 13l3 .5M3 13l.5 3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none" />'
              '<path d="M6 10l7-7M11.5 3h1.5v1.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none" />',
}
_CLASS_COLORS = {"Inf": "var(--ks-inf)", "Cav": "var(--ks-cav)", "Arc": "var(--ks-arc)"}
_CLASS_LABELS = {"Inf": "Infantry", "Cav": "Cavalry", "Arc": "Archer"}


def class_icon_svg(cls: str, size: int = 14) -> str:
    body = _CLASS_ICONS.get(cls, "")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 16 16" '
        f'style="display:inline-block;vertical-align:-2px;">{body}</svg>'
    )


def class_badge_html(cls: str, size: str = "md", show_label: bool = True) -> str:
    color = _CLASS_COLORS[cls]
    label = _CLASS_LABELS[cls]
    px = {"sm": 6, "md": 8, "lg": 10}[size]
    py = {"sm": 2, "md": 3, "lg": 5}[size]
    ic = {"sm": 11, "md": 13, "lg": 16}[size]
    fs = {"sm": 10.5, "md": 11.5, "lg": 13}[size]
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:color-mix(in srgb, {color} 12%, transparent);color:{color};'
        f'padding:{py}px {px}px;border-radius:6px;font-size:{fs}px;'
        f'font-weight:600;line-height:1;letter-spacing:0.01em;white-space:nowrap;">'
        f'{class_icon_svg(cls, ic)}{label if show_label else ""}</span>'
    )


def class_chip_html(cls: str) -> str:
    color = _CLASS_COLORS[cls]
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:20px;height:20px;border-radius:6px;'
        f'background:color-mix(in srgb, {color} 13%, transparent);color:{color};'
        f'flex:0 0 auto;">{class_icon_svg(cls, 12)}</span>'
    )


def split_bar_html(split: Sequence[float], height: int = 8,
                    show_labels: bool = False, width: str = "100%") -> str:
    inf, cav, arc = split
    labels_html = ""
    if show_labels:
        labels_html = (
            '<div style="display:flex;justify-content:space-between;margin-top:5px;'
            'font-size:11px;color:var(--ks-text-muted);font-family:\'JetBrains Mono\',ui-monospace,monospace;">'
            f'<span style="color:var(--ks-inf);">{round(inf*100)}% Inf</span>'
            f'<span style="color:var(--ks-cav);">{round(cav*100)}% Cav</span>'
            f'<span style="color:var(--ks-arc);">{round(arc*100)}% Arc</span>'
            '</div>'
        )
    return (
        f'<div style="width:{width};">'
        f'<div style="display:flex;height:{height}px;border-radius:999px;'
        f'overflow:hidden;background:var(--ks-surface-muted);">'
        f'<div style="width:{inf*100:.2f}%;background:var(--ks-inf);"></div>'
        f'<div style="width:{cav*100:.2f}%;background:var(--ks-cav);"></div>'
        f'<div style="width:{arc*100:.2f}%;background:var(--ks-arc);"></div>'
        f'</div>{labels_html}</div>'
    )


def score_bar_html(score: float, ci_lo: Optional[float] = None,
                    ci_hi: Optional[float] = None, width=180) -> str:
    if isinstance(width, str):
        def pct(v: float) -> float:
            return ((max(-1.0, min(1.0, v)) + 1) / 2) * 100
        ci_html = ""
        if ci_lo is not None and ci_hi is not None:
            lo, hi = pct(ci_lo), pct(ci_hi)
            ci_html = (
                f'<div style="position:absolute;left:{lo:.2f}%;top:5px;'
                f'width:{hi-lo:.2f}%;height:4px;'
                f'background:color-mix(in srgb,var(--ks-accent) 33%, transparent);'
                f'border-radius:999px;"></div>'
            )
        dot = pct(score)
        return (
            f'<div style="position:relative;width:{width};height:14px;display:block;">'
            f'<div style="position:absolute;left:0;top:6px;right:0;height:2px;'
            f'background:var(--ks-surface-muted);border-radius:999px;"></div>'
            f'<div style="position:absolute;left:50%;top:2px;bottom:2px;'
            f'width:1px;background:var(--ks-text-faint);"></div>'
            f'{ci_html}'
            f'<div style="position:absolute;left:{dot:.2f}%;top:1px;'
            f'transform:translateX(-50%);'
            f'width:12px;height:12px;border-radius:50%;'
            f'background:var(--ks-accent);border:2px solid #fff;'
            f'box-shadow:0 1px 2px rgba(0,0,0,0.15);"></div>'
            f'</div>'
        )

    def px(v: float) -> float:
        return ((max(-1.0, min(1.0, v)) + 1) / 2) * width
    ci_html = ""
    if ci_lo is not None and ci_hi is not None:
        lo, hi = px(ci_lo), px(ci_hi)
        ci_html = (
            f'<div style="position:absolute;left:{lo}px;top:5px;'
            f'width:{hi-lo:.2f}px;height:4px;'
            f'background:color-mix(in srgb,var(--ks-accent) 33%, transparent);'
            f'border-radius:999px;"></div>'
        )
    dot = px(score)
    return (
        f'<div style="position:relative;width:{width}px;height:14px;display:inline-block;">'
        f'<div style="position:absolute;left:0;top:6px;right:0;height:2px;'
        f'background:var(--ks-surface-muted);border-radius:999px;"></div>'
        f'<div style="position:absolute;left:{width/2}px;top:2px;bottom:2px;'
        f'width:1px;background:var(--ks-text-faint);"></div>'
        f'{ci_html}'
        f'<div style="position:absolute;left:{dot-6:.2f}px;top:1px;'
        f'width:12px;height:12px;border-radius:50%;'
        f'background:var(--ks-accent);border:2px solid #fff;'
        f'box-shadow:0 1px 2px rgba(0,0,0,0.15);"></div>'
        f'</div>'
    )


_SCORE_BANDS = (
    (0.50, "Crushing win", "💥", "var(--ks-arc)"),
    (0.15, "You win", "✅", "var(--ks-arc)"),
    (-0.15, "Coin-flip", "⚖️", "var(--ks-warn)"),
    (-0.50, "You lose", "❌", "var(--ks-cav)"),
    (-2.00, "Crushing loss", "💀", "var(--ks-cav)"),
)


def score_verdict(score: float) -> tuple[str, str, str]:
    for thresh, label, emoji, color in _SCORE_BANDS:
        if score >= thresh:
            return label, emoji, color
    return "Crushing loss", "💀", "var(--ks-cav)"


def score_verdict_html(score: float, *, defender_perspective: bool = False,
                       big: bool = False) -> str:
    label, _emoji, color = score_verdict(score)
    if big:
        return (
            f'<span style="display:inline-flex;align-items:center;gap:7px;'
            f'background:color-mix(in srgb,{color} 15%,transparent);color:{color};'
            f'border:1px solid color-mix(in srgb,{color} 35%,transparent);'
            f'padding:7px 16px;border-radius:999px;font-size:16px;font-weight:700;'
            f'white-space:nowrap;">{label}</span>'
        )
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:color-mix(in srgb,{color} 13%,transparent);color:{color};'
        f'padding:2px 9px;border-radius:999px;font-size:12.5px;font-weight:600;'
        f'white-space:nowrap;">{label}</span>'
    )


def stat_html(label: str, value: str, *, sub: str = "",
              color: str = "var(--ks-text)") -> str:
    sub_html = (
        f'<span style="font-size:11px;color:var(--ks-text-muted);">{sub}</span>'
    ) if sub else ""
    return (
        f'<div style="display:flex;flex-direction:column;gap:2px;">'
        f'<span style="font-size:11px;color:var(--ks-text-faint);font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.05em;">{label}</span>'
        f'<span style="font-size:22px;font-weight:700;color:{color};line-height:1;'
        f'font-family:\'JetBrains Mono\',ui-monospace,monospace;'
        f'font-variant-numeric:tabular-nums;">{value}</span>'
        f'{sub_html}</div>'
    )


def answer_banner_html(*, eyebrow: str, score: float,
                       stats: Sequence[dict], recommendation_html: str = "",
                       trio_html: str = "") -> str:
    _, _, color = score_verdict(score)
    trio_block = (
        f'<div style="flex:0 0 auto;">{trio_html}</div>' if trio_html else ""
    )
    stats_block = "".join(stat_html(**s) for s in stats)
    rec_block = (
        f'<div style="margin-top:16px;padding-top:14px;'
        f'border-top:1px solid var(--ks-border);display:flex;gap:10px;">'
        f'<span style="color:{color};flex-shrink:0;'
        f'font-family:\'JetBrains Mono\',ui-monospace,monospace;">→</span>'
        f'<span style="font-size:14px;color:var(--ks-text);line-height:1.55;">'
        f'{recommendation_html}</span></div>'
    ) if recommendation_html else ""
    return (
        f'<div style="background:linear-gradient(115deg,'
        f'color-mix(in srgb,{color} 14%,var(--ks-surface)) 0%,'
        f'var(--ks-surface) 60%);'
        f'border:1px solid color-mix(in srgb,{color} 40%,var(--ks-border));'
        f'border-radius:16px;padding:22px;box-shadow:var(--ks-shadow-card);">'
        f'<div style="font-size:12px;font-weight:700;letter-spacing:0.08em;'
        f'text-transform:uppercase;color:var(--ks-text-faint);'
        f'margin-bottom:12px;">{eyebrow}</div>'
        f'<div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap;">'
        f'{trio_block}'
        f'<div style="flex:1;min-width:200px;display:flex;flex-direction:column;'
        f'gap:12px;">'
        f'<div>{score_verdict_html(score, big=True)}</div>'
        f'<div style="display:flex;gap:26px;flex-wrap:wrap;">{stats_block}</div>'
        f'</div></div>{rec_block}</div>'
    )


def render_answer_banner(**kwargs) -> None:
    st.markdown(answer_banner_html(**kwargs), unsafe_allow_html=True)


def result_summary_html(*, eyebrow: str, score: float,
                        stats: Sequence[dict], trio_html: str = "") -> str:
    stats_block = "".join(stat_html(**s) for s in stats)
    trio_block = (
        f'<div style="flex:0 0 auto;">{trio_html}</div>' if trio_html else ""
    )
    eyebrow_block = (
        f'<div style="font-size:11px;font-weight:600;letter-spacing:0.07em;'
        f'text-transform:uppercase;color:var(--ks-text-faint);'
        f'margin-bottom:10px;">{eyebrow}</div>' if eyebrow else ""
    )
    return (
        f'<div style="border:1px solid var(--ks-border);border-radius:12px;'
        f'background:var(--ks-surface);box-shadow:var(--ks-shadow);'
        f'padding:18px 20px;">'
        f'{eyebrow_block}'
        f'<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">'
        f'{trio_block}'
        f'<div style="display:flex;flex-direction:column;gap:10px;flex:1;'
        f'min-width:180px;">'
        f'<div>{score_verdict_html(score)}</div>'
        f'<div style="display:flex;gap:24px;flex-wrap:wrap;">{stats_block}</div>'
        f'</div></div></div>'
    )


def render_result_summary(**kwargs) -> None:
    st.markdown(result_summary_html(**kwargs), unsafe_allow_html=True)


def score_legend_html() -> str:
    ordered = list(reversed(_SCORE_BANDS))
    n = len(ordered)
    cells = ""
    for i, (_thresh, label, _emoji, color) in enumerate(ordered):
        fill = 22 if label == "Coin-flip" else 14
        right = ("border-right:1px solid var(--ks-bg);" if i < n - 1 else "")
        cells += (
            f'<div style="flex:1;background:color-mix(in srgb,{color} {fill}%,'
            f'transparent);color:{color};padding:7px 4px;text-align:center;'
            f'font-size:11px;font-weight:600;{right}">{label}</div>'
        )
    return (
        f'<div style="display:flex;border-radius:8px;overflow:hidden;'
        f'margin-top:10px;">{cells}</div>'
    )


def render_score_formula_expander(*, expanded: bool = False) -> None:
    with st.expander("How the battle score is calculated", expanded=expanded):
        st.markdown(
            "The **battle score** is the normalised troop-power margin at the "
            "end of the fight, on a <code>−1</code> … <code>+1</code> scale "
            "(− = the defender comes out ahead, + = the attacker does). The "
            "<span style='color:var(--ks-warn);font-weight:600;'>±0.15</span> "
            "band around zero is treated as a **coin-flip**. Within simulation "
            "noise, not a real edge.",
            unsafe_allow_html=True,
        )
        st.markdown(score_legend_html(), unsafe_allow_html=True)


def apply_plotly_theme(fig, *, dark: bool) -> None:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=("#e6edf3" if dark else "#0a2540")),
    )
    grid = "rgba(255,255,255,0.08)" if dark else "rgba(10,37,64,0.08)"
    fig.update_xaxes(gridcolor=grid, zerolinecolor=grid)
    fig.update_yaxes(gridcolor=grid, zerolinecolor=grid)


def is_dark_mode() -> bool:
    from kingshot_sim.webui import theme as _theme
    return bool(st.session_state.get(_theme.THEME_STATE_KEY, False))


def add_score_verdict_bands(fig, *, axis: str = "y") -> None:
    bands = (
        (0.15, 1.0, "rgba(10,135,90,0.10)"),
        (-0.15, 0.15, "rgba(187,85,4,0.09)"),
        (-1.0, -0.15, "rgba(6,127,151,0.10)"),
    )
    for lo, hi, color in bands:
        if axis == "y":
            fig.add_hrect(y0=lo, y1=hi, fillcolor=color, line_width=0,
                          layer="below")
        else:
            fig.add_vrect(x0=lo, x1=hi, fillcolor=color, line_width=0,
                          layer="below")


def portrait_name_html(hero: str, cls: Optional[str] = None, *,
                       size: int = 26, weight: int = 500,
                       font_size: float = 13.0) -> str:
    pic = hero_portrait_html(hero, size=size, cls=cls)
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'vertical-align:middle;">{pic}'
        f'<span style="font-weight:{weight};color:var(--ks-text);'
        f'font-size:{font_size}px;">{hero}</span></span>'
    )


def multi_pill_html(label: str, cls: Optional[str] = None) -> str:
    color = _CLASS_COLORS.get(cls, "var(--ks-accent)")
    icon_html = class_icon_svg(cls, 11) if cls else ""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:color-mix(in srgb, {color} 12%, transparent);color:{color};'
        f'padding:3px 8px;border-radius:6px;font-size:12px;font-weight:500;'
        f'margin-right:4px;margin-bottom:4px;">{icon_html}{label}</span>'
    )


def render_page_header(title: str, sub: str = "") -> None:
    sub_html = (
        f'<div style="font-size:14px;color:var(--ks-text-muted);'
        f'margin-top:6px;line-height:1.55;max-width:820px;">{sub}</div>'
    ) if sub else ""
    html = (
        f'<div style="margin-bottom:24px;">'
        f'<h1 style="margin:0;font-size:28px;font-weight:700;'
        f'letter-spacing:-0.02em;color:var(--ks-text);">{title}</h1>'
        f'{sub_html}</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_section_label(text: str, num: Optional[int] = None) -> None:
    num_html = (
        f'<span style="display:inline-flex;align-items:center;'
        f'justify-content:center;width:18px;height:18px;border-radius:5px;'
        f'background:var(--ks-accent-soft);color:var(--ks-accent);'
        f'font-size:11px;font-weight:700;margin-right:8px;'
        f'font-family:\'JetBrains Mono\',ui-monospace,monospace;">{num}</span>'
    ) if num is not None else ""
    st.markdown(
        f'<div style="display:flex;align-items:center;margin:22px 0 10px;">'
        f'{num_html}'
        f'<span style="font-size:11px;font-weight:600;letter-spacing:0.07em;'
        f'text-transform:uppercase;color:var(--ks-text-muted);">{text}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_subheading(text: str, sub: str = "") -> None:
    sub_html = (
        f'<div style="font-size:12.5px;color:var(--ks-text-muted);'
        f'margin-top:2px;">{sub}</div>'
    ) if sub else ""
    st.markdown(
        f'<div style="margin:6px 0 10px;">'
        f'<div style="font-size:15px;font-weight:600;letter-spacing:-0.01em;'
        f'color:var(--ks-text);">{text}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    logo = logo_data_uri()
    img_html = (
        f'<img src="{logo}" alt="Absy Labs logo" '
        f'style="width:38px;height:38px;border-radius:8px;display:block;'
        f'object-fit:cover;box-shadow:0 2px 6px rgba(10,37,64,0.18);" />'
        if logo
        else '<div style="width:38px;height:38px;border-radius:8px;'
             'background:linear-gradient(135deg,#3b5b7a,#2f4a64);"></div>'
    )
    html = (
        '<div style="display:flex;align-items:center;gap:11px;margin-bottom:16px;">'
        f'{img_html}'
        '<div style="min-width:0;">'
        '<div style="font-size:15px;font-weight:700;letter-spacing:-0.015em;'
        'color:var(--ks-text);line-height:1.15;">Absy Labs</div>'
        '<div style="font-size:10.5px;color:var(--ks-text-muted);'
        'margin-top:2px;line-height:1.3;">'
        'Kingshot Battle Helper<br>Simulator &amp; Calculator · Beta</div>'
        '</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_sidebar_kofi() -> None:
    st.html(
        '<a href="https://ko-fi.com/absyy" target="_blank" style="'
        'display:block;text-decoration:none;color:#fff;'
        'background:linear-gradient(135deg,#ff5e5b 0%,#e84543 100%);'
        'border-radius:8px;padding:14px 16px;margin-bottom:14px;'
        'box-shadow:0 2px 6px rgba(255,94,91,0.30);'
        'font-family:Inter,sans-serif;line-height:1.3;">'
        '<div style="font-size:14px;font-weight:700;color:#fff;'
        'margin-bottom:3px;">Support on Ko-fi</div>'
        '<div style="font-size:12px;color:#fff;opacity:0.92;'
        'margin-bottom:10px;">Free forever. Keep me caffeinated</div>'
        '<div style="font-size:11.5px;font-weight:600;'
        'font-family:JetBrains Mono,monospace;color:#fff;'
        'padding-top:8px;border-top:1px solid rgba(255,255,255,0.22);">'
        'ko-fi.com/absyy →</div></a>'
    )


def render_sidebar_discord() -> None:
    st.html(
        '<a href="https://discord.gg/pwGvB99WN3" target="_blank" style="'
        'display:block;text-decoration:none;color:#fff;'
        'background:#5865f2;border-radius:8px;padding:14px 16px;'
        'margin-bottom:14px;box-shadow:0 2px 6px rgba(88,101,242,0.25);'
        'font-family:Inter,sans-serif;line-height:1.3;">'
        '<div style="font-size:14px;font-weight:700;color:#fff;'
        'margin-bottom:3px;">Join the Discord</div>'
        '<div style="font-size:12px;color:#fff;opacity:0.92;">'
        'Bug reports, tests, ideas</div></a>'
    )


def render_sidebar_theme_toggle() -> None:
    from kingshot_sim.webui import theme as ks_theme

    st.toggle(
        "Dark mode",
        key=ks_theme.THEME_STATE_KEY,
        help="Switch the interface between light and dark.",
    )


def render_sidebar_footer() -> None:
    html = (
        '<div style="border-top:1px solid var(--ks-border);padding-top:12px;'
        'font-size:12px;color:var(--ks-text-muted);line-height:1.5;'
        'margin-top:24px;">'
        'Built by <strong style="color:var(--ks-text);">Absy</strong> · '
        '1163, 1182, 1510'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_sidebar_stats() -> None:
    from kingshot_sim.webui import runtime_stats

    total = runtime_stats.get_total_sims()
    busy = runtime_stats.get_queue_count() + runtime_stats.get_running_count()
    dot = (f'<span style="color:var(--ks-warn);">● {busy} running</span>'
           if busy > 0 else
           '<span style="color:var(--ks-success);">● idle</span>')
    st.markdown(
        '<div style="display:flex;justify-content:space-between;'
        'align-items:baseline;font-size:11.5px;color:var(--ks-text-faint);'
        'margin:2px 0 14px;">'
        f'<span style="font-variant-numeric:tabular-nums;">{total:,} sims run</span>'
        f'<span>{dot}</span></div>',
        unsafe_allow_html=True,
    )


def scroll_to_anchor(anchor_id: str) -> None:
    try:
        from streamlit.components.v1 import html as _components_html
    except Exception:
        return
    _components_html(
        f"""
        <script>
            (function() {{
                function doScroll() {{
                    try {{
                        var doc = window.parent.document;
                        var el = doc.getElementById({anchor_id!r});
                        if (el) {{
                            el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                        }}
                    }} catch (e) {{ /* swallow — fun feature, not critical */ }}
                }}
                // Two ticks: the first lets Streamlit finish committing
                // the rerun DOM, the second gives layout a chance to
                // settle so smooth-scroll lands on the right position.
                setTimeout(doScroll, 60);
                setTimeout(doScroll, 250);
            }})();
        </script>
        """,
        height=0,
    )
