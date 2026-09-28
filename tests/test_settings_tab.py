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
