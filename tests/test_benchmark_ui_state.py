from pathlib import Path
import streamlit as st
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import BenchmarkRoster, roster_to_json, roster_from_json
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg.scope import set_session_storage, clear_session_storage
from kingshot_sim.webui.tabs.benchmark import (
    _extract_roster_from_session,
    _load_roster_into_session,
)

_RUN_APP_PATH = str(Path(__file__).resolve().parent.parent / "run_app.py")


def test_load_roster_into_session():
    st.session_state.clear()
    r = BenchmarkRoster(
        name="TestRoster",
        generation=5,
        owned_heroes={
            "Inf": ["Helga", "Jabel"],
            "Cav": ["Amadeus"],
            "Arc": ["Frak"],
        },
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=0),
            "Jabel": HeroBuild(level="4_2", widget_level=5),
        },
    )

    _load_roster_into_session(r)

    assert st.session_state.get("_bm_active_roster") == "TestRoster"
    assert st.session_state.get("_bm_gen") == 5
    assert st.session_state.get("_bm_own_Inf") == ["Helga", "Jabel"]
    assert st.session_state.get("_bm_own_Cav") == ["Amadeus"]
    assert st.session_state.get("_bm_own_Arc") == ["Frak"]

    assert st.session_state.get("_bm_star_Helga") == 5
    assert st.session_state.get("_bm_tier_Helga") == 0
    assert st.session_state.get("_bm_wl_Helga") == 0

    assert st.session_state.get("_bm_star_Jabel") == 4
    assert st.session_state.get("_bm_tier_Jabel") == 2
    assert st.session_state.get("_bm_wl_Jabel") == 5


def test_extract_roster_from_session():
    st.session_state.clear()
    owned = {
        "Inf": ["Helga"],
        "Cav": ["Amadeus"],
        "Arc": ["Frak"],
    }
    builds = {
        "Helga": HeroBuild(level="MAX", widget_level=0),
        "Amadeus": HeroBuild(level="5_0", widget_level=4),
        "Frak": HeroBuild(level="3_1", widget_level=2),
    }

    roster = _extract_roster_from_session(
        name="ExtractedRoster",
        gen=6,
        builds=builds,
        owned=owned,
    )

    assert roster.name == "ExtractedRoster"
    assert roster.generation == 6
    assert roster.owned_heroes == owned
    assert roster.builds == builds


def test_extract_roster_fills_missing_builds_from_session():
    st.session_state.clear()
    st.session_state["_bm_star_Aman"] = 4
    st.session_state["_bm_tier_Aman"] = 1
    st.session_state["_bm_wl_Aman"] = 6

    owned = {"Inf": ["Aman"]}
    builds = {}

    roster = _extract_roster_from_session(
        name="AutoBuilds",
        gen=4,
        builds=builds,
        owned=owned,
    )

    assert "Aman" in roster.builds
    assert roster.builds["Aman"].level == "4_1"
    assert roster.builds["Aman"].widget_level == 6


def test_generation_slider_preserves_hero_builds():
    st.session_state.clear()
    # User configures Jabel at Gen 7
    st.session_state["_bm_star_Jabel"] = 4
    st.session_state["_bm_tier_Jabel"] = 3
    st.session_state["_bm_wl_Jabel"] = 7
    st.session_state["_bm_own_Inf"] = ["Jabel"]

    # Moving generation slider to gen 6 or gen 5 should retain unsuffixed keys
    builds_gen6 = {}
    roster_gen6 = _extract_roster_from_session(
        name="Gen6View",
        gen=6,
        builds=builds_gen6,
        owned={"Inf": ["Jabel"]},
    )
    assert roster_gen6.builds["Jabel"].level == "4_3"
    assert roster_gen6.builds["Jabel"].widget_level == 7

    # When moving slider to Gen 8, same unsuffixed keys are still intact
    builds_gen8 = {}
    roster_gen8 = _extract_roster_from_session(
        name="Gen8View",
        gen=8,
        builds=builds_gen8,
        owned={"Inf": ["Jabel"]},
    )
    assert roster_gen8.builds["Jabel"].level == "4_3"
    assert roster_gen8.builds["Jabel"].widget_level == 7


def test_json_export_and_import_flow():
    st.session_state.clear()
    orig_roster = BenchmarkRoster(
        name="ExportedRoster",
        generation=7,
        owned_heroes={"Inf": ["Jabel"], "Cav": ["Amadeus"]},
        builds={
            "Jabel": HeroBuild(level="4_3", widget_level=8),
            "Amadeus": HeroBuild(level="MAX", widget_level=4),
        },
    )

    # Export to JSON
    json_blob = roster_to_json(orig_roster)
    assert isinstance(json_blob, str)

    # Import from JSON
    imported_roster = roster_from_json(json_blob)
    assert imported_roster.name == "ExportedRoster"
    assert imported_roster.generation == 7

    # Load into session state
    _load_roster_into_session(imported_roster)
    assert st.session_state["_bm_active_roster"] == "ExportedRoster"
    assert st.session_state["_bm_gen"] == 7
    assert st.session_state["_bm_star_Jabel"] == 4
    assert st.session_state["_bm_tier_Jabel"] == 3
    assert st.session_state["_bm_wl_Jabel"] == 8

    # Extract back out of session state
    re_extracted = _extract_roster_from_session(
        name=st.session_state["_bm_active_roster"],
        gen=st.session_state["_bm_gen"],
        builds={},
        owned={"Inf": st.session_state["_bm_own_Inf"], "Cav": st.session_state["_bm_own_Cav"]},
    )
    assert re_extracted.name == "ExportedRoster"
    assert re_extracted.generation == 7
    assert re_extracted.builds["Jabel"].level == "4_3"
    assert re_extracted.builds["Jabel"].widget_level == 8


def test_persistence_integration_with_session_state():
    set_session_storage(True)
    clear_session_storage()
    st.session_state.clear()
    try:
        r = BenchmarkRoster(
            name="SessionSavedRoster",
            generation=6,
            owned_heroes={"Inf": ["Helga"]},
            builds={"Helga": HeroBuild(level="MAX", widget_level=0)},
        )
        ps.save_roster(r, "SessionSavedRoster")
        assert "SessionSavedRoster" in ps.list_rosters()

        # Load from persistence into session state
        loaded = ps.load_roster("SessionSavedRoster")
        _load_roster_into_session(loaded)

        assert st.session_state["_bm_active_roster"] == "SessionSavedRoster"
        assert st.session_state["_bm_gen"] == 6
        assert st.session_state["_bm_star_Helga"] == 5

        # Modify star in session and save back
        st.session_state["_bm_star_Helga"] = 4
        st.session_state["_bm_tier_Helga"] = 2
        updated_r = _extract_roster_from_session(
            name="SessionSavedRoster",
            gen=6,
            builds={},
            owned={"Inf": ["Helga"]},
        )
        ps.save_roster(updated_r, "SessionSavedRoster")

        reloaded = ps.load_roster("SessionSavedRoster")
        assert reloaded.builds["Helga"].level == "4_2"
    finally:
        set_session_storage(False)


def test_render_roster_manager_select_flow():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string("""
import streamlit as st
from kingshot_sim.webui.tabs.benchmark import render
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import BenchmarkRoster
from kingshot_sim.webui import persistence as ps

if 'init_test' not in st.session_state:
    st.session_state['init_test'] = True
    r = BenchmarkRoster(
        name='UITestRoster',
        generation=5,
        owned_heroes={'Inf': ['Helga']},
        builds={'Helga': HeroBuild('4_2', 6)},
    )
    ps.save_roster(r, 'UITestRoster')

render()
""")
    at.run()
    assert not at.exception
    sb = at.selectbox[0]
    assert "UITestRoster" in sb.options
    sb.select("UITestRoster").run()
    assert not at.exception
    assert at.session_state["_bm_active_roster"] == "UITestRoster"
    assert at.session_state["_bm_gen"] == 5
    assert at.session_state["_bm_star_Helga"] == 4
    assert at.session_state["_bm_tier_Helga"] == 2
    assert at.session_state["_bm_wl_Helga"] == 6


def test_render_roster_manager_delete_flow():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string("""
import streamlit as st
from kingshot_sim.webui.tabs.benchmark import render
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import BenchmarkRoster
from kingshot_sim.webui import persistence as ps

if 'init_del' not in st.session_state:
    st.session_state['init_del'] = True
    r = BenchmarkRoster(
        name='RosterToDelete',
        generation=6,
        owned_heroes={'Inf': ['Helga']},
        builds={'Helga': HeroBuild('5_0', 4)},
    )
    ps.save_roster(r, 'RosterToDelete')

render()
""")
    at.run()
    sb = at.selectbox[0]
    sb.select("RosterToDelete").run()
    assert at.session_state["_bm_active_roster"] == "RosterToDelete"
    at.button(key="_bm_delete_btn").click().run()
    assert not at.exception
    assert at.session_state["_bm_active_roster"] == "[Custom / Unsaved]"
    assert "RosterToDelete" not in ps.list_rosters()


def test_generation_slider_preserves_higher_gen_hero_apptest():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(_RUN_APP_PATH)
    at.run()
    assert not at.exception

    # 1. Verify initial slider is at MAX_GENERATION (Gen 7) and Charles is owned
    assert at.select_slider(key="_bm_gen").value == 7
    assert "Charles" in at.multiselect(key="_bm_own_Inf").value

    # 2. Customize Charles: 4 stars, 2 sub-tiers, widget 7
    at.number_input(key="_bm_star_Charles").set_value(4).run()
    assert not at.exception
    at.number_input(key="_bm_tier_Charles").set_value(2)
    at.slider(key="_bm_wl_Charles").set_value(7).run()
    assert not at.exception

    assert at.session_state["_bm_star_Charles"] == 4
    assert at.session_state["_bm_tier_Charles"] == 2
    assert at.session_state["_bm_wl_Charles"] == 7

    # 3. Move generation slider to Gen 1
    at.select_slider(key="_bm_gen").set_value(1).run()
    assert not at.exception
    assert at.select_slider(key="_bm_gen").value == 1

    # In Gen 1, Charles should not appear in options or visible multiselect selection
    assert "Charles" not in at.multiselect(key="_bm_own_Inf").options
    assert "Charles" not in at.multiselect(key="_bm_own_Inf").value

    # Charles and his custom build must be retained in master backing stores
    assert "Charles" in at.session_state["_bm_master_owned"]["Inf"]
    mb = at.session_state["_bm_master_builds"]["Charles"]
    assert mb.level == "4_2"
    assert mb.widget_level == 7

    # 4. Save roster while viewing Gen 1: verify extraction retains Gen 7 & Charles
    at.button(key="_bm_save_btn").click().run()
    assert not at.exception
    at.text_input(key="_bm_prompt_name").set_value("PreservedGen7Roster")
    at.button(key="_bm_prompt_confirm").click().run()
    assert not at.exception

    # Check the persisted roster
    raw_saved = at.session_state["_ks_rosters_store"]["PreservedGen7Roster"]
    saved_roster = roster_from_json(raw_saved)
    assert saved_roster.name == "PreservedGen7Roster"
    assert saved_roster.generation == 7
    assert "Charles" in saved_roster.owned_heroes["Inf"]
    assert saved_roster.builds["Charles"].level == "4_2"
    assert saved_roster.builds["Charles"].widget_level == 7

    # 5. Move generation slider back to Gen 7
    at.select_slider(key="_bm_gen").set_value(7).run()
    assert not at.exception
    assert at.select_slider(key="_bm_gen").value == 7

    # Charles should now be visible again in multiselect and inputs restored
    assert "Charles" in at.multiselect(key="_bm_own_Inf").options
    assert "Charles" in at.multiselect(key="_bm_own_Inf").value
    assert at.number_input(key="_bm_star_Charles").value == 4
    assert at.number_input(key="_bm_tier_Charles").value == 2
    assert at.slider(key="_bm_wl_Charles").value == 7


def test_save_roster_reserved_name_rejected():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(_RUN_APP_PATH)
    at.run()
    at.button(key="_bm_save_btn").click().run()
    at.text_input(key="_bm_prompt_name").set_value("[Custom / Unsaved]")
    at.button(key="_bm_prompt_confirm").click().run()
    assert len(at.error) > 0
    assert "Cannot use reserved name" in at.error[0].value


