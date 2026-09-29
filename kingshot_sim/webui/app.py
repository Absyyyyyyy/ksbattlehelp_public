from __future__ import annotations
import streamlit as st

from kingshot_sim.webui.tabs import (
    attack_defense, quick_fight, sensitivity, settings, benchmark, skillmod,
)
from kingshot_sim.webui import theme as ks_theme
from kingshot_sim.webui import components
from kingshot_sim.webui import local_storage as ks_lstorage


def _inject_seo_meta() -> None:
    canonical = "https://absy-simulator.streamlit.app/"
    og_image = (
        "https://raw.githubusercontent.com/Absyyyyyyy/ksbattlehelp_public/"
        "main/kingshot_sim/webui/assets/logo_og.jpg"
    )
    favicon = components.favicon_data_uri()
    title = "Absy Labs: Kingshot Battle Helper Simulator & Calculator"
    description = (
        "Absy Labs builds the Kingshot Battle Helper, a free open-source "
        "PvP simulator and calculator for the Kingshot mobile game. Find "
        "the best rally to break a garrison, the best defense to hold an "
        "attack, run Monte-Carlo battle simulations, and optimize mythic "
        "heroes, joiners, gear, and troop ratios. Combat formulas fully "
        "documented and community-validated."
    )
    keywords = (
        "Absy Labs, Kingshot Battle Helper, Kingshot simulator, "
        "Kingshot calculator, Kingshot battle calculator, Kingshot rally, "
        "Kingshot garrison, Kingshot best counter, Kingshot best defense, "
        "Kingshot heroes, Kingshot mythic heroes, Kingshot guide, "
        "Kingshot mobile game, Kingshot PvP, Kingshot tier list, "
        "Petra, Yang, Sophia, Margot, Triton, Vivian, Helga, Eric, Jaeger, "
        "alliance joiners, Kingshot helper, Kingshot tool, "
        "expedition combat, State of Survival combat engine, "
        "Monte Carlo battle simulator"
    )

    import json
    jsonld = {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "Kingshot Battle Helper",
        "alternateName": ["Absy Labs Kingshot Simulator",
                            "Kingshot Battle Calculator"],
        "url": canonical,
        "description": description,
        "applicationCategory": "GameApplication",
        "applicationSubCategory": "Game Calculator",
        "operatingSystem": "Web Browser",
        "browserRequirements": "Requires JavaScript. Modern browser.",
        "softwareVersion": "Beta",
        "isAccessibleForFree": True,
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD",
        },
        "creator": {
            "@type": "Organization",
            "name": "Absy Labs",
            "url": canonical,
        },
        "author": {
            "@type": "Person",
            "name": "Absy",
            "sameAs": "https://ko-fi.com/absyy",
        },
        "inLanguage": "en",
        "keywords": keywords,
        "audience": {
            "@type": "Audience",
            "audienceType": "Kingshot mobile game players",
        },
        "featureList": [
            "Best Counter: find the optimal attacker composition",
            "Best Defense: find the optimal defender composition",
            "Attack & Defense: counter a garrison or harden your own",
            "Quick Fight: single battle simulation",
            "Sensitivity analysis: parameter sweeps",
            "Monte Carlo simulation with 95% confidence intervals",
            "Mythic hero & joiner optimization",
            "Troop ratio and gear optimization",
        ],
    }

    head_html = f"""
        <link rel="canonical" href="{canonical}">
        <link rel="icon" type="image/png" href="{favicon}">
        <link rel="apple-touch-icon" href="{favicon}">
        <meta name="theme-color" content="#3b5b7a">
        <meta name="application-name" content="Absy Labs: Kingshot Battle Helper">
        <meta name="apple-mobile-web-app-title" content="Absy Labs">
        <meta name="description" content="{description}">
        <meta name="keywords" content="{keywords}">
        <meta name="author" content="Absy Labs (Discord: absy)">
        <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
        <meta name="googlebot" content="index, follow, max-snippet:-1, max-image-preview:large">
        <meta name="bingbot" content="index, follow">
        <meta name="rating" content="general">

        <meta property="og:site_name" content="Absy Labs">
        <meta property="og:title" content="{title}">
        <meta property="og:description" content="{description}">
        <meta property="og:url" content="{canonical}">
        <meta property="og:type" content="website">
        <meta property="og:image" content="{og_image}">
        <meta property="og:image:width" content="512">
        <meta property="og:image:height" content="512">
        <meta property="og:image:type" content="image/jpeg">
        <meta property="og:image:alt" content="Absy Labs logo, Dürer's Melencolia I (1514)">
        <meta property="og:locale" content="en_US">

        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="{title}">
        <meta name="twitter:description" content="{description}">
        <meta name="twitter:image" content="{og_image}">
        <meta name="twitter:image:alt" content="Absy Labs logo">

        <script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
        """
    st.markdown(head_html, unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Absy Labs: Kingshot Battle Helper Simulator & Calculator",
        page_icon=components.favicon_path() or ":material/shield:",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get help": "https://discord.gg/pwGvB99WN3",
            "Report a bug": "https://discord.gg/pwGvB99WN3",
            "About": (
                "**Absy Labs: Kingshot Battle Helper** is an open-source "
                "PvP simulator & calculator for Kingshot. Formulas are "
                "documented on GitHub. Beta, so your feedback is invaluable."
            ),
        },
    )
    _inject_seo_meta()

    ks_lstorage.hydrate_from_browser()

    dark = bool(st.session_state.get(ks_theme.THEME_STATE_KEY, False))
    ks_theme.inject(dark=dark)

    with st.sidebar:
        components.render_sidebar_brand()
        _render_sidebar_nav()
        components.render_sidebar_theme_toggle()
        components.render_sidebar_stats()
        components.render_sidebar_kofi()
        components.render_sidebar_discord()
        components.render_sidebar_footer()

    _render_active_tab()

    ks_lstorage.auto_save_to_browser()


_NAV_GROUPS = (
    ("Advisor", (
        ("benchmark", "Benchmark", benchmark.render),
        ("skillmod", "SkillMod", skillmod.render),
    )),
    ("Battle simulator", (
        ("attack_defense", "Attack & Defense", attack_defense.render),
        ("quick_fight", "Quick Fight", quick_fight.render),
        ("sensitivity", "Sensitivity", sensitivity.render),
    )),
    (None, (
        ("settings", "Settings", settings.render),
    )),
)
_TABS = tuple(item for _grp, items in _NAV_GROUPS for item in items)
_TAB_SLUGS = tuple(slug for slug, _label, _fn in _TABS)
_LABEL_BY_SLUG = {slug: label for slug, label, _fn in _TABS}
_RENDER_BY_SLUG = {slug: fn for slug, _label, fn in _TABS}
_DEFAULT_TAB = "benchmark"
_ACTIVE_TAB_KEY = "_ks_active_tab"


def _set_active_tab(slug: str) -> None:
    st.session_state[_ACTIVE_TAB_KEY] = slug


def _current_tab() -> str:
    current = st.session_state.get(_ACTIVE_TAB_KEY, _DEFAULT_TAB)
    return current if current in _TAB_SLUGS else _DEFAULT_TAB


def _render_sidebar_nav() -> None:
    current = _current_tab()
    for group_label, items in _NAV_GROUPS:
        if group_label:
            st.markdown(
                f'<div class="ks-nav-group">{group_label}</div>',
                unsafe_allow_html=True,
            )
        for slug, label, _fn in items:
            st.button(
                label,
                key=f"nav_{slug}",
                width="stretch",
                type=("primary" if slug == current else "secondary"),
                on_click=_set_active_tab, args=(slug,),
            )


def _render_active_tab() -> None:
    render_fn = _RENDER_BY_SLUG[_current_tab()]
    try:
        render_fn()
    except Exception as e:
        st.error(f"This tab crashed: {e!r}")
        st.exception(e)
