from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from kingshot_sim.config.fighter import HeroGearPiece, BonusVector
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.benchmark.advisor import simulate
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui import persistence


def test_simulate_with_class_gear():
    builds = {
        "Eric": HeroBuild(level="MAX", widget_level=4),
        "Amadeus": HeroBuild(level="MAX", widget_level=4),
        "Petra": HeroBuild(level="MAX", widget_level=4),
        "Margot": HeroBuild(level="MAX", widget_level=4),
        "Jaeger": HeroBuild(level="MAX", widget_level=4),
    }

    # Simulate without gear
    passes_no_gear = simulate(1, builds, class_gear=None)
    score_no_gear = passes_no_gear.cur.per_hero["solo_atk"]["Petra"]

    # Simulate with mythic/red cav gear
    cav_gear = {
        "Cav": {
            "boots": HeroGearPiece(slot="boots", quality="red", level=100, forge_mastery=10),
            "gloves": HeroGearPiece(slot="gloves", quality="red", level=100, forge_mastery=10),
        }
    }
    passes_with_gear = simulate(1, builds, class_gear=cav_gear)
    score_with_gear = passes_with_gear.cur.per_hero["solo_atk"]["Petra"]

    # Cav gear should increase Petra's benchmark performance
    assert score_with_gear > score_no_gear
    assert getattr(passes_with_gear, "class_gear", None) == cav_gear


def _render_benchmark_app():
    from kingshot_sim.webui.tabs.benchmark import render
    render()


def test_benchmark_toolbar_empty_rosters_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    at = AppTest.from_function(_render_benchmark_app)
    at.run()
    assert not at.exception


def test_benchmark_toolbar_profile_selection_and_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")

    r_alpha = AccountRoster(
        name="ProfileAlpha",
        generation=7,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={
            "Eric": HeroBuild(level="4_2", widget_level=5),
            "Petra": HeroBuild(level="MAX", widget_level=8),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=30)}},
        bonuses=BonusVector(inf_atk_pct=50.0),
        buffs=Buffs(city_atk=10),
    )
    r_beta = AccountRoster(
        name="ProfileBeta",
        generation=6,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Ahab"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=10),
        },
    )
    persistence.save_roster(r_alpha, "ProfileAlpha")
    persistence.save_roster(r_beta, "ProfileBeta")

    at = AppTest.from_function(_render_benchmark_app)
    at.run()
    assert not at.exception

    # Select ProfileAlpha and click reload
    at.selectbox(key="benchmark_roster_select").select("ProfileAlpha").run()
    assert not at.exception
    at.button(key="benchmark_reload_roster_btn").click().run()
    assert not at.exception

    assert at.session_state["_ks_active_roster"] == "ProfileAlpha"
    assert at.session_state["_bm_gen"] == 7
    assert at.session_state["_bm_star_Eric_7"] == 4
    assert at.session_state["_bm_tier_Eric_7"] == 2
    assert at.session_state["_bm_wl_Eric_7"] == 5
    assert at.session_state["_bm_class_gear"]["Inf"]["head"].level == 30


def test_benchmark_local_overrides_non_destructive_until_save_back(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")

    original = AccountRoster(
        name="OriginalProfile",
        generation=7,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={
            "Eric": HeroBuild(level="MAX", widget_level=4),
        },
    )
    persistence.save_roster(original, "OriginalProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.benchmark import render
        st.session_state["_ks_active_roster"] = "OriginalProfile"
        render()

    at = AppTest.from_function(_app)
    at.run()
    assert not at.exception

    # Initially loaded as active profile
    assert at.session_state["_bm_gen"] == 7

    # Apply local override in session state (e.g. user changes Eric stars and widgets in tab)
    at.session_state["_bm_star_Eric_7"] = 3
    at.session_state["_bm_tier_Eric_7"] = 0
    at.session_state["_bm_wl_Eric_7"] = 1
    at.run()
    assert not at.exception

    # Verify disk profile is completely unchanged (non-destructive)
    disk_roster = persistence.load_roster("OriginalProfile")
    assert disk_roster.builds["Eric"].level == "MAX"
    assert disk_roster.builds["Eric"].widget_level == 4

    # Now click "Save Changes Back to Profile"
    at.button(key="benchmark_save_roster_btn").click().run()
    assert not at.exception

    # Saved profile on disk must now reflect the local overrides
    updated_disk_roster = persistence.load_roster("OriginalProfile")
    assert updated_disk_roster.builds["Eric"].level == "3_0"
    assert updated_disk_roster.builds["Eric"].widget_level == 1


def test_benchmark_reload_reverts_local_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")

    roster = AccountRoster(
        name="RevertProfile",
        generation=7,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={
            "Eric": HeroBuild(level="MAX", widget_level=4),
        },
    )
    persistence.save_roster(roster, "RevertProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.benchmark import render
        st.session_state["_ks_active_roster"] = "RevertProfile"
        render()

    at = AppTest.from_function(_app)
    at.run()
    assert not at.exception

    # Mutate in session state
    at.session_state["_bm_star_Eric_7"] = 2
    at.session_state["_bm_tier_Eric_7"] = 1
    at.session_state["_bm_wl_Eric_7"] = 9
    at.run()
    assert at.session_state["_bm_star_Eric_7"] == 2

    # Click Reload
    at.button(key="benchmark_reload_roster_btn").click().run()
    assert not at.exception

    # Should be reverted back to 5 stars (MAX) and widget 4
    assert at.session_state["_bm_star_Eric_7"] == 5
    assert at.session_state["_bm_tier_Eric_7"] == 0
    assert at.session_state["_bm_wl_Eric_7"] == 4


def test_benchmark_analyse_with_class_gear(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")

    roster = AccountRoster(
        name="GearAnalysisProfile",
        generation=3,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={
            "Eric": HeroBuild(level="MAX", widget_level=4),
            "Petra": HeroBuild(level="MAX", widget_level=4),
            "Jaeger": HeroBuild(level="MAX", widget_level=4),
        },
        class_gear={
            "Cav": {
                "boots": HeroGearPiece(slot="boots", quality="red", level=100, forge_mastery=10),
            }
        },
    )
    persistence.save_roster(roster, "GearAnalysisProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.benchmark import render
        st.session_state["_ks_active_roster"] = "GearAnalysisProfile"
        render()

    at = AppTest.from_function(_app)
    at.run()
    assert not at.exception
    assert at.session_state.get("_bm_class_gear") is not None

    # Click Analyse my roster button
    at.button(key="_bm_run").click().run()
    assert not at.exception
    assert "_bm_result" in at.session_state
    rgen, rbuilds, cur = at.session_state["_bm_result"]
    assert rgen == 3
    assert "Petra" in cur.per_hero["solo_atk"]

