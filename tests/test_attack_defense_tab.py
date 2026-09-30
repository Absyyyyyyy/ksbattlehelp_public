from __future__ import annotations

from dataclasses import replace
from streamlit.testing.v1 import AppTest

from kingshot_sim.config.fighter import HeroGearPiece, BonusVector
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui import persistence


def _render_attack_defense_app():
    from kingshot_sim.webui.tabs.attack_defense import render
    render()


def test_attack_defense_empty_rosters_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    at = AppTest.from_function(_render_attack_defense_app, default_timeout=30)
    at.run()
    assert not at.exception
    # Toolbar reload/save buttons should be present and disabled
    assert at.button(key="bc_reload_roster_btn").disabled
    assert at.button(key="bc_save_roster_btn").disabled


def test_attack_defense_candidate_loads_from_account_roster(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    roster = AccountRoster(
        name="CandidateProfile",
        generation=7,
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=6),
            "Margot": HeroBuild(level="4_0", widget_level=8),
            "Yang": HeroBuild(level="MAX", widget_level=10),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100)}},
        bonuses=BonusVector(inf_atk_pct=45.0, squad_let_pct=20.0),
        buffs=Buffs(city_atk=20),
    )
    persistence.save_roster(roster, "CandidateProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.attack_defense import render
        st.session_state["_ks_active_roster"] = "CandidateProfile"
        render()

    at = AppTest.from_function(_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Candidate search space should be populated from the AccountRoster
    space = at.session_state.get("bc_space")
    assert space is not None
    assert "Helga" in space.available_mythic_inf
    assert "Margot" in space.available_mythic_cav
    assert "Yang" in space.available_mythic_arc
    assert space.leader_specs["Helga"].widget_level == 6
    assert space.leader_specs["Margot"].widget_level == 8
    assert space.class_gear["Inf"]["head"].level == 100
    assert space.bonuses.inf_atk_pct == 45.0
    assert space.bonuses.squad_let_pct == 20.0
    assert space.buffs.city_atk == 20


def test_attack_defense_candidate_local_overrides_non_destructive_until_save_back(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    original = AccountRoster(
        name="NonDestructiveProfile",
        generation=7,
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=4),
        },
        bonuses=BonusVector(inf_atk_pct=30.0),
    )
    persistence.save_roster(original, "NonDestructiveProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.attack_defense import render
        st.session_state["_ks_active_roster"] = "NonDestructiveProfile"
        render()

    at = AppTest.from_function(_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Modify candidate space in session state (in-tab local override)
    cur_space = at.session_state["bc_space"]
    at.session_state["bc_space"] = replace(
        cur_space,
        bonuses=BonusVector(inf_atk_pct=85.0),
    )
    at.run()
    assert not at.exception

    # Disk roster must remain completely untouched
    disk_roster = persistence.load_roster("NonDestructiveProfile")
    assert disk_roster.bonuses.inf_atk_pct == 30.0

    # Click "Save Changes Back to Profile"
    at.button(key="bc_save_roster_btn").click().run()
    assert not at.exception

    # Profile on disk must now reflect the saved changes
    updated_disk_roster = persistence.load_roster("NonDestructiveProfile")
    assert updated_disk_roster.bonuses.inf_atk_pct == 85.0


def test_attack_defense_candidate_reload_reverts_local_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    roster = AccountRoster(
        name="RevertProfile",
        generation=7,
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=4),
        },
        bonuses=BonusVector(inf_atk_pct=30.0),
    )
    persistence.save_roster(roster, "RevertProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.attack_defense import render
        st.session_state["_ks_active_roster"] = "RevertProfile"
        render()

    at = AppTest.from_function(_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Modify locally
    cur_space = at.session_state["bc_space"]
    at.session_state["bc_space"] = replace(
        cur_space,
        bonuses=BonusVector(inf_atk_pct=99.0),
    )
    at.run()
    assert at.session_state["bc_space"].bonuses.inf_atk_pct == 99.0

    # Click "Reload from Profile"
    at.button(key="bc_reload_roster_btn").click().run()
    assert not at.exception

    # Verify session state candidate space was reverted to 30.0
    assert at.session_state["bc_space"].bonuses.inf_atk_pct == 30.0


def test_attack_defense_opponent_loads_from_account_roster(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    roster = AccountRoster(
        name="EnemyRoster",
        generation=7,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=9),
            "Margot": HeroBuild(level="MAX", widget_level=7),
            "Yang": HeroBuild(level="MAX", widget_level=8),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=60)}},
        bonuses=BonusVector(cav_hp_pct=50.0),
        buffs=Buffs(appoint_marshal=True),
    )
    persistence.save_roster(roster, "EnemyRoster")

    at = AppTest.from_function(_render_attack_defense_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Select EnemyRoster from the opponent roster selectbox and click Load
    at.selectbox(key="bc_load_roster_def").select("EnemyRoster").run()
    assert not at.exception
    at.button(key="bc_btn_load_roster_def").click().run()
    assert not at.exception

    opp = at.session_state.get("bc_defender")
    assert opp is not None
    assert opp.label == "EnemyRoster"
    assert opp.leader_inf.hero_name == "Amadeus"
    assert opp.leader_inf.widget_level == 9
    assert opp.leader_inf.gear["head"].level == 60
    assert opp.leader_cav.hero_name == "Margot"
    assert opp.leader_cav.widget_level == 7
    assert opp.leader_arc.hero_name == "Yang"
    assert opp.bonuses.cav_hp_pct == 50.0
    assert opp.buffs.appoint_marshal is True


def test_attack_defense_defense_mode_loads_opponent_and_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")

    cand_roster = AccountRoster(
        name="DefCandRoster",
        generation=5,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        bonuses=BonusVector(inf_def_pct=35.0),
    )
    opp_roster = AccountRoster(
        name="DefOppRoster",
        generation=5,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Vivian"]},
        bonuses=BonusVector(inf_atk_pct=55.0),
    )
    persistence.save_roster(cand_roster, "DefCandRoster")
    persistence.save_roster(opp_roster, "DefOppRoster")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.attack_defense import render
        st.session_state["ad_mode"] = "Best defense (I'm defending)"
        st.session_state["_ks_active_roster"] = "DefCandRoster"
        render()

    at = AppTest.from_function(_app, default_timeout=30)
    at.run()
    assert not at.exception

    # Candidate space should have loaded DefCandRoster
    space = at.session_state.get("bd_space")
    assert space is not None
    assert "Eric" in space.available_mythic_inf
    assert space.bonuses.inf_def_pct == 35.0

    # Load opponent
    at.selectbox(key="bd_load_roster_att").select("DefOppRoster").run()
    assert not at.exception
    at.button(key="bd_btn_load_roster_att").click().run()
    assert not at.exception

    opp = at.session_state.get("bd_attacker")
    assert opp is not None
    assert opp.label == "DefOppRoster"
    assert opp.leader_inf.hero_name == "Amadeus"
    assert opp.leader_cav.hero_name == "Margot"
    assert opp.bonuses.inf_atk_pct == 55.0


def test_attack_defense_candidate_edits_survive_reruns_with_spaced_profile_name(tmp_path, monkeypatch):
    # "My Main" is stored as My_Main.json; the toolbar must not reload it on every rerun.
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")
    persistence.save_roster(AccountRoster(
        name="My Main",
        generation=7,
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
    ), "My Main")

    at = AppTest.from_function(_render_attack_defense_app, default_timeout=30)
    at.run()
    assert at.multiselect(key="bc_sp_inf").value == ["Helga"]

    extra = [h for h in at.multiselect(key="bc_sp_inf").options if h != "Helga"][0]
    at.multiselect(key="bc_sp_inf").select(extra).run()
    at.run()
    assert at.multiselect(key="bc_sp_inf").value == ["Helga", extra]

    at.button(key="bc_save_roster_btn").click().run()
    assert not at.exception
    assert persistence.list_rosters() == ["My_Main"]
    assert persistence.load_roster("My_Main").owned_heroes["Inf"] == ["Helga", extra]
