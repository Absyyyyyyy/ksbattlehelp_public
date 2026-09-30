from __future__ import annotations

import json
import pytest
from streamlit.testing.v1 import AppTest

from kingshot_sim.config.fighter import HeroGearPiece, BonusVector
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui import persistence


def test_create_empty_roster():
    from kingshot_sim.webui.tabs.settings import create_empty_roster

    r = create_empty_roster("Custom New")
    assert isinstance(r, AccountRoster)
    assert r.name == "Custom New"
    assert r.generation == 8
    assert isinstance(r.class_gear, dict)
    assert isinstance(r.bonuses, BonusVector)
    assert isinstance(r.buffs, Buffs)


def test_save_load_delete_active_roster(tmp_path, monkeypatch):
    from kingshot_sim.webui.tabs.settings import (
        save_active_roster,
        load_active_roster,
        delete_active_roster,
    )

    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    roster = AccountRoster(
        name="AlphaSquad",
        generation=7,
        owned_heroes={
            "Inf": ["Eric", "Amadeus"],
            "Cav": ["Petra"],
            "Arc": ["Jaeger"],
        },
        builds={
            "Eric": HeroBuild(level="MAX", widget_level=10, skill_levels=(5, 5, 5)),
            "Petra": HeroBuild(level="4_5", widget_level=8, skill_levels=(5, 4, 3)),
        },
        class_gear={
            "Inf": {
                "head": HeroGearPiece(slot="head", quality="mythic", level=40, forge_mastery=5),
            },
        },
        bonuses=BonusVector(inf_atk_pct=150.0, squad_let_pct=50.0),
        buffs=Buffs(city_atk=20, rhino_level=8, appoint_field_commander=True),
    )

    save_active_roster(roster, "AlphaSquad")
    assert "AlphaSquad" in persistence.list_rosters()

    loaded = load_active_roster("AlphaSquad")
    assert loaded.name == "AlphaSquad"
    assert loaded.generation == 7
    assert loaded.owned_heroes["Inf"] == ["Eric", "Amadeus"]
    assert loaded.builds["Eric"].widget_level == 10
    assert loaded.class_gear["Inf"]["head"].level == 40
    assert loaded.class_gear["Inf"]["head"].forge_mastery == 5
    assert loaded.bonuses.inf_atk_pct == 150.0
    assert loaded.bonuses.squad_let_pct == 50.0
    assert loaded.buffs.city_atk == 20
    assert loaded.buffs.rhino_level == 8
    assert loaded.buffs.appoint_field_commander is True

    delete_active_roster("AlphaSquad")
    assert "AlphaSquad" not in persistence.list_rosters()


def test_roster_json_v2_export_import(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    roster = AccountRoster(
        name="JSONExportTest",
        generation=6,
        owned_heroes={"Cav": ["Petra", "Margot"]},
        class_gear={"Cav": {"boots": HeroGearPiece(slot="boots", quality="red", level=100, forge_mastery=10)}},
        bonuses=BonusVector(cav_atk_pct=120.0),
        buffs=Buffs(city_def=20),
    )
    raw_json = persistence.roster_to_json(roster)
    parsed = json.loads(raw_json)
    assert parsed["version"] == 2
    assert parsed["format"] == "ksbattlehelper-roster"
    assert parsed["name"] == "JSONExportTest"

    imported = persistence.roster_from_json(raw_json)
    assert imported.name == "JSONExportTest"
    assert imported.generation == 6
    assert imported.class_gear["Cav"]["boots"].quality == "red"
    assert imported.bonuses.cav_atk_pct == 120.0
    assert imported.buffs.city_def == 20


def _render_account_roster_section_app():
    from kingshot_sim.webui.tabs.settings import render_account_roster_section
    render_account_roster_section()


def test_render_account_roster_section_empty_apptest(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    at = AppTest.from_function(_render_account_roster_section_app)
    at.run()
    assert not at.exception, f"render_account_roster_section crashed: {at.exception}"


def test_render_account_roster_section_with_existing_roster_apptest(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    r = AccountRoster(
        name="ExistingProfile",
        generation=6,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=30)}},
        bonuses=BonusVector(inf_atk_pct=50.0),
        buffs=Buffs(city_atk=10),
    )
    persistence.save_roster(r, "ExistingProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.settings import render_account_roster_section
        st.session_state["_ks_active_roster"] = "ExistingProfile"
        render_account_roster_section()

    at = AppTest.from_function(_app)
    at.run()
    assert not at.exception, f"render_account_roster_section crashed with profile: {at.exception}"


def test_delete_selected_profile_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    r1 = AccountRoster(name="ToDelete", generation=8)
    r2 = AccountRoster(name="Survivor", generation=8)
    persistence.save_roster(r1, "ToDelete")
    persistence.save_roster(r2, "Survivor")

    def _app_delete_selected():
        import streamlit as st
        from kingshot_sim.webui.tabs.settings import render_account_roster_section
        st.session_state["_ks_active_roster"] = "ToDelete"
        st.session_state["settings_roster_select"] = "ToDelete"
        render_account_roster_section()

    at = AppTest.from_function(_app_delete_selected)
    at.run()
    assert not at.exception

    del_btn = at.button(key="settings_roster_del_btn")
    del_btn.click().run()
    assert not at.exception
    assert "ToDelete" not in persistence.list_rosters()
    assert at.session_state.get("settings_roster_select") != "ToDelete"


def test_delete_from_saved_list_when_selected_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    r1 = AccountRoster(name="ListToDelete", generation=8)
    r2 = AccountRoster(name="SurvivorProfile", generation=8)
    persistence.save_roster(r1, "ListToDelete")
    persistence.save_roster(r2, "SurvivorProfile")

    def _app_list():
        import streamlit as st
        from kingshot_sim.webui.tabs.settings import render_account_roster_section
        st.session_state["_ks_active_roster"] = "ListToDelete"
        st.session_state["settings_roster_select"] = "ListToDelete"
        render_account_roster_section()

    at = AppTest.from_function(_app_list)
    at.run()
    assert not at.exception

    del_list_btn = at.button(key="settings_del_roster_list_ListToDelete")
    del_list_btn.click().run()
    assert not at.exception
    assert "ListToDelete" not in persistence.list_rosters()
    assert at.session_state.get("settings_roster_select") != "ListToDelete"


def test_upload_json_activates_uploaded_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    r = AccountRoster(
        name="UploadedRoster",
        generation=7,
        owned_heroes={"Inf": ["Eric"]},
        bonuses=BonusVector(inf_atk_pct=99.0),
        buffs=Buffs(city_atk=20),
    )
    raw_bytes = persistence.roster_to_json(r).encode("utf-8")

    at = AppTest.from_function(_render_account_roster_section_app)
    at.run()
    assert not at.exception

    uploader = at.file_uploader(key="settings_roster_upload_json")
    uploader.upload("UploadedRoster.json", raw_bytes).run()
    assert not at.exception
    at.run()

    assert "UploadedRoster" in persistence.list_rosters()
    assert at.session_state["_ks_active_roster"] == "UploadedRoster"
    assert at.session_state["settings_roster_select"] == "UploadedRoster"
    loaded = persistence.load_roster("UploadedRoster")
    assert loaded.bonuses.inf_atk_pct == 99.0


def _render_full_settings_app():
    from kingshot_sim.webui.tabs.settings import render
    render()


def test_render_full_settings_tab_apptest(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    at = AppTest.from_function(_render_full_settings_app)
    at.run()
    assert not at.exception, f"settings.render() crashed: {at.exception}"


def test_save_profile_button_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    at = AppTest.from_function(_render_account_roster_section_app)
    at.run()
    assert not at.exception
    at.text_input(key="settings_roster_name_input").set_value("NewSavedProfile").run()
    assert not at.exception
    at.button(key="settings_roster_save_btn").click().run()
    assert not at.exception
    assert "NewSavedProfile" in persistence.list_rosters()


def test_save_as_profile_button_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    r = AccountRoster(name="BaseProfile", generation=6)
    persistence.save_roster(r, "BaseProfile")

    def _app():
        import streamlit as st
        from kingshot_sim.webui.tabs.settings import render_account_roster_section
        st.session_state["_ks_active_roster"] = "BaseProfile"
        render_account_roster_section()

    at = AppTest.from_function(_app)
    at.run()
    assert not at.exception
    at.text_input(key="settings_roster_save_as_input").set_value("BaseProfile Copy").run()
    assert not at.exception
    at.button(key="settings_roster_save_as_btn").click().run()
    assert not at.exception
    assert "BaseProfile_Copy" in persistence.list_rosters()


def test_full_settings_render_save_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    at = AppTest.from_function(_render_full_settings_app)
    at.run()
    assert not at.exception
    at.text_input(key="settings_roster_name_input").set_value("FullSettingsSave").run()
    assert not at.exception
    at.button(key="settings_roster_save_btn").click().run()
    assert not at.exception
    assert "FullSettingsSave" in persistence.list_rosters()


def test_settings_renders_three_tabs_only(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")
    monkeypatch.setattr(persistence, "_use_session_backend", lambda: False)

    at = AppTest.from_function(_render_full_settings_app)
    at.default_timeout = 10
    at.run()
    assert not at.exception

    labels = [t.label for t in at.tabs]
    assert any("Account & roster profiles" in lbl for lbl in labels)
    assert "Advanced options" in labels
    assert "Backup & restore" in labels
    assert not any("Saved rosters" in lbl for lbl in labels)
    assert not any(lbl.startswith("Saved profiles") for lbl in labels)


def test_legacy_fighter_profiles_inspect_convert_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")
    monkeypatch.setattr(persistence, "_use_session_backend", lambda: False)

    from kingshot_sim.config.fighter import Fighter, LeaderHero, JoinerHero, TroopRoster

    legacy_fighter = Fighter(
        label="LegacyChamp",
        leader_inf=LeaderHero("Eric", level="MAX", widget_level=10),
        leader_cav=LeaderHero("Petra", level="MAX", widget_level=8),
        leader_arc=LeaderHero("Jaeger", level="MAX", widget_level=5),
        joiners=(JoinerHero("Margot", level="MAX"),),
        bonuses=BonusVector(inf_atk_pct=50.0),
        troops=TroopRoster(),
    )
    persistence.save_profile(legacy_fighter, "LegacyChamp")
    assert "LegacyChamp" in persistence.list_profiles()
    assert "LegacyChamp" not in persistence.list_rosters()

    at = AppTest.from_function(_render_full_settings_app)
    at.default_timeout = 10
    at.run()
    assert not at.exception

    insp_btn = at.button(key="legacy_insp_LegacyChamp")
    insp_btn.click().run()
    assert not at.exception
    assert at.session_state.get("set_inspect_profile") is not None
    assert at.session_state["set_inspect_profile"][0] == "LegacyChamp"

    convert_btn = at.button(key="legacy_convert_LegacyChamp")
    convert_btn.click().run()
    assert not at.exception
    assert "LegacyChamp" in persistence.list_rosters()
    converted_roster = persistence.load_roster("LegacyChamp")
    assert converted_roster.name == "LegacyChamp"
    assert "Eric" in converted_roster.owned_heroes.get("Inf", [])

    del_btn = at.button(key="legacy_del_LegacyChamp")
    del_btn.click().run()
    assert not at.exception
    assert "LegacyChamp" not in persistence.list_profiles()


def test_backup_restore_metrics_show_account_rosters(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(persistence, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(persistence, "_SEARCH_DIR", tmp_path / "searches")
    monkeypatch.setattr(persistence, "_use_session_backend", lambda: False)

    from kingshot_sim.config.fighter import Fighter, LeaderHero, TroopRoster

    r1 = AccountRoster(name="Roster1", generation=8)
    r2 = AccountRoster(name="Roster2", generation=8)
    persistence.save_roster(r1, "Roster1")
    persistence.save_roster(r2, "Roster2")

    f1 = Fighter(
        label="FighterLegacy",
        leader_inf=LeaderHero("Eric", level="MAX", widget_level=10),
        leader_cav=LeaderHero("Petra", level="MAX", widget_level=8),
        leader_arc=LeaderHero("Jaeger", level="MAX", widget_level=5),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(),
    )
    persistence.save_profile(f1, "FighterLegacy")

    at = AppTest.from_function(_render_full_settings_app)
    at.default_timeout = 10
    at.run()
    assert not at.exception

    metric_map = {m.label: m.value for m in at.metric}
    assert "Account Rosters" in metric_map
    assert "Legacy Profiles" in metric_map
    assert "Op overrides" in metric_map
    assert "Data overrides" in metric_map
    assert metric_map["Account Rosters"] == "2"
    assert metric_map["Legacy Profiles"] == "1"



