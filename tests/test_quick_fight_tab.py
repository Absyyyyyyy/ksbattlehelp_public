from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from kingshot_sim.config.fighter import HeroGearPiece, BonusVector, TroopRoster, TroopGroup
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui import persistence


def _render_quick_fight_app():
    from kingshot_sim.webui.tabs.quick_fight import render
    render()


def test_quick_fight_renders_empty_rosters_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    at = AppTest.from_function(_render_quick_fight_app)
    at.run()
    assert not at.exception
    # Toolbar selectboxes should not be present when no rosters exist
    assert len([s for s in at.selectbox if s.key == "qf_load_att_roster"]) == 0
    assert len([s for s in at.selectbox if s.key == "qf_load_def_roster"]) == 0


def _app_with_custom_attacker():
    from dataclasses import replace
    import streamlit as st
    from kingshot_sim.config.fighter import TroopRoster, TroopGroup
    from kingshot_sim.webui.forms import empty_fighter
    from kingshot_sim.webui.tabs.quick_fight import render
    if "qf_attacker" not in st.session_state:
        st.session_state.qf_attacker = replace(
            empty_fighter("Attacker"),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T10", count=111_000),),
                cavalry=(TroopGroup(tier="T10.TG5", count=222_000),),
                archer=(TroopGroup(tier="T11", count=333_000),),
            ),
        )
    render()


def _app_with_custom_defender():
    from dataclasses import replace
    import streamlit as st
    from kingshot_sim.config.fighter import TroopRoster, TroopGroup
    from kingshot_sim.webui.forms import empty_fighter
    from kingshot_sim.webui.tabs.quick_fight import render
    if "qf_defender" not in st.session_state:
        st.session_state.qf_defender = replace(
            empty_fighter("Defender"),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T9", count=50_000),),
                cavalry=(TroopGroup(tier="T10", count=60_000),),
                archer=(TroopGroup(tier="T10.TG5", count=70_000),),
            ),
        )
    render()


def test_quick_fight_loads_attacker_from_account_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    roster = AccountRoster(
        name="AlphaAttacker",
        generation=7,
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Helga": HeroBuild(level="4_2", widget_level=6),
            "Margot": HeroBuild(level="MAX", widget_level=8),
            "Yang": HeroBuild(level="MAX", widget_level=10),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100)}},
        bonuses=BonusVector(inf_atk_pct=45.0, cav_hp_pct=30.0),
        buffs=Buffs(city_atk=20),
    )
    persistence.save_roster(roster, "AlphaAttacker")

    at = AppTest.from_function(_app_with_custom_attacker)
    at.run()
    assert not at.exception

    # Select AlphaAttacker from toolbar and click load
    at.selectbox(key="qf_load_att_roster").select("AlphaAttacker").run()
    assert not at.exception
    at.button(key="qf_btn_load_att").click().run()
    assert not at.exception

    att = at.session_state.get("qf_attacker")
    assert att is not None
    assert att.label == "AlphaAttacker"
    assert att.leader_inf.hero_name == "Helga"
    assert att.leader_inf.level == "4_2"
    assert att.leader_inf.widget_level == 6
    assert att.leader_inf.gear["head"].level == 100
    assert att.leader_cav.hero_name == "Margot"
    assert att.leader_cav.widget_level == 8
    assert att.leader_arc.hero_name == "Yang"
    assert att.leader_arc.widget_level == 10
    assert att.bonuses.inf_atk_pct == 45.0
    assert att.bonuses.cav_hp_pct == 30.0
    assert att.buffs.city_atk == 20

    # Troops preserved
    assert att.troops == TroopRoster(
        infantry=(TroopGroup(tier="T10", count=111_000),),
        cavalry=(TroopGroup(tier="T10.TG5", count=222_000),),
        archer=(TroopGroup(tier="T11", count=333_000),),
    )

    # Form generation and mode flags
    assert at.session_state.get("qf_att_form_gen") == 1
    assert at.session_state.get("qf_att_input_mode") == "Advanced"
    assert at.session_state.get("qf_att_input_mode_radio") == "Advanced (manual entry)"

    # Form widgets should reflect loaded values
    assert at.selectbox(key="qf_att_g1_li_name").value == "Helga"
    assert at.selectbox(key="qf_att_g1_li_level").value == "4_2"
    assert at.slider(key="qf_att_g1_li_widget").value == 6

    # Verify troop inputs remain interactive after loading profile
    at.number_input(key="qf_att_g1_infantry_0_cnt").set_value(500_000).run()
    assert not at.exception
    updated_att = at.session_state.get("qf_attacker")
    assert updated_att.troops.infantry[0].count == 500_000


def test_quick_fight_loads_defender_from_account_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    roster = AccountRoster(
        name="BetaDefender",
        generation=7,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Vivian"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=9),
            "Margot": HeroBuild(level="4_3", widget_level=7),
            "Vivian": HeroBuild(level="MAX", widget_level=5),
        },
        class_gear={"Cav": {"boots": HeroGearPiece(slot="boots", quality="mythic", level=75)}},
        bonuses=BonusVector(arc_atk_pct=50.0),
        buffs=Buffs(appoint_marshal=True),
    )
    persistence.save_roster(roster, "BetaDefender")

    at = AppTest.from_function(_app_with_custom_defender)
    at.run()
    assert not at.exception

    # Select BetaDefender from toolbar and click load
    at.selectbox(key="qf_load_def_roster").select("BetaDefender").run()
    assert not at.exception
    at.button(key="qf_btn_load_def").click().run()
    assert not at.exception

    defn = at.session_state.get("qf_defender")
    assert defn is not None
    assert defn.label == "BetaDefender"
    assert defn.leader_inf.hero_name == "Amadeus"
    assert defn.leader_inf.widget_level == 9
    assert defn.leader_cav.hero_name == "Margot"
    assert defn.leader_cav.level == "4_3"
    assert defn.leader_cav.widget_level == 7
    assert defn.leader_cav.gear["boots"].level == 75
    assert defn.leader_arc.hero_name == "Vivian"
    assert defn.leader_arc.widget_level == 5
    assert defn.bonuses.arc_atk_pct == 50.0
    assert defn.buffs.appoint_marshal is True

    # Troops preserved
    assert defn.troops == TroopRoster(
        infantry=(TroopGroup(tier="T9", count=50_000),),
        cavalry=(TroopGroup(tier="T10", count=60_000),),
        archer=(TroopGroup(tier="T10.TG5", count=70_000),),
    )

    # Form generation and mode flags
    assert at.session_state.get("qf_def_form_gen") == 1
    assert at.session_state.get("qf_def_input_mode") == "Advanced"
    assert at.session_state.get("qf_def_input_mode_radio") == "Advanced (manual entry)"

    # Form widgets should reflect loaded values
    assert at.selectbox(key="qf_def_g1_li_name").value == "Amadeus"
    assert at.selectbox(key="qf_def_g1_lc_level").value == "4_3"
    assert at.slider(key="qf_def_g1_lc_widget").value == 7


def test_quick_fight_run_battle_after_loading_rosters(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    att_roster = AccountRoster(
        name="BattleAttacker",
        generation=7,
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=5),
            "Margot": HeroBuild(level="MAX", widget_level=5),
            "Yang": HeroBuild(level="MAX", widget_level=5),
        },
        bonuses=BonusVector(inf_atk_pct=30.0),
    )
    def_roster = AccountRoster(
        name="BattleDefender",
        generation=7,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Vivian"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=5),
            "Margot": HeroBuild(level="MAX", widget_level=5),
            "Vivian": HeroBuild(level="MAX", widget_level=5),
        },
        bonuses=BonusVector(inf_def_pct=30.0),
    )
    persistence.save_roster(att_roster, "BattleAttacker")
    persistence.save_roster(def_roster, "BattleDefender")

    at = AppTest.from_function(_render_quick_fight_app)
    at.run()
    assert not at.exception

    # Load attacker
    at.selectbox(key="qf_load_att_roster").select("BattleAttacker").run()
    at.button(key="qf_btn_load_att").click().run()
    assert not at.exception

    # Load defender
    at.selectbox(key="qf_load_def_roster").select("BattleDefender").run()
    at.button(key="qf_btn_load_def").click().run()
    assert not at.exception

    # Run deterministic battle
    at.button(key="qf_run").click().run()
    assert not at.exception
