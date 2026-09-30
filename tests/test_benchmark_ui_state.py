from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.data.reference import MAX_GENERATION
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui.tabs.benchmark import _load_roster_into_session

_RUN_APP_PATH = str(Path(__file__).resolve().parent.parent / "run_app.py")


def test_load_roster_into_session_sets_backing_stores():
    st.session_state.clear()
    r = AccountRoster(
        name="TestRoster",
        generation=5,
        owned_heroes={"Inf": ["Helga", "Jabel"], "Cav": ["Amadeus"], "Arc": ["Frak"]},
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=0),
            "Jabel": HeroBuild(level="4_2", widget_level=5),
        },
    )

    _load_roster_into_session(r)

    ss = st.session_state
    assert ss["_bm_gen"] == 5
    assert ss["_bm_last_gen"] == 5
    assert ss["_bm_master_owned"] == {
        "Inf": ["Helga", "Jabel"], "Cav": ["Amadeus"], "Arc": ["Frak"],
    }
    assert ss["_bm_master_builds"]["Jabel"] == HeroBuild(level="4_2", widget_level=5)


def test_load_roster_into_session_clears_previous_profile_widgets():
    st.session_state.clear()
    st.session_state["_bm_star_Eric"] = 2
    st.session_state["_bm_tier_Eric"] = 3
    st.session_state["_bm_wl_Eric"] = 9
    st.session_state["_bm_own_Inf"] = ["Eric"]
    st.session_state["_bm_result"] = object()

    _load_roster_into_session(AccountRoster(name="Other", generation=3))

    for k in ("_bm_star_Eric", "_bm_tier_Eric", "_bm_wl_Eric", "_bm_own_Inf", "_bm_result"):
        assert k not in st.session_state


def test_load_roster_into_session_clamps_generation():
    st.session_state.clear()
    r = AccountRoster(name="Future", generation=MAX_GENERATION)
    r.generation = MAX_GENERATION + 3
    _load_roster_into_session(r)
    assert st.session_state["_bm_gen"] == MAX_GENERATION


def test_generation_slider_preserves_higher_gen_hero_apptest():
    at = AppTest.from_file(_RUN_APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    assert at.select_slider(key="_bm_gen").value == 7
    assert "Charles" in at.multiselect(key="_bm_own_Inf").value

    at.number_input(key="_bm_star_Charles").set_value(4).run()
    at.number_input(key="_bm_tier_Charles").set_value(2)
    at.slider(key="_bm_wl_Charles").set_value(7).run()
    assert not at.exception

    # Charles isn't available at gen 1, but his build is kept in the backing stores.
    at.select_slider(key="_bm_gen").set_value(1).run()
    assert not at.exception
    assert "Charles" not in at.multiselect(key="_bm_own_Inf").options
    assert "Charles" in at.session_state["_bm_master_owned"]["Inf"]
    mb = at.session_state["_bm_master_builds"]["Charles"]
    assert (mb.level, mb.widget_level) == ("4_2", 7)

    # Back at gen 7 he's owned again with the same build.
    at.select_slider(key="_bm_gen").set_value(7).run()
    assert not at.exception
    assert "Charles" in at.multiselect(key="_bm_own_Inf").value
    assert at.number_input(key="_bm_star_Charles").value == 4
    assert at.number_input(key="_bm_tier_Charles").value == 2
    assert at.slider(key="_bm_wl_Charles").value == 7


def _bench_or_other_tab():
    import streamlit as st

    if st.session_state.get("show_bench", True):
        from kingshot_sim.webui.tabs.benchmark import render
        render()
    else:
        st.write("another tab")


def test_generation_survives_switching_tabs(tmp_path, monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    from kingshot_sim.webui import persistence
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")
    at = AppTest.from_function(_bench_or_other_tab, default_timeout=30)
    at.run()
    at.select_slider(key="_bm_gen").set_value(3).run()

    at.session_state["show_bench"] = False
    at.run()
    at.session_state["show_bench"] = True
    at.run()
    assert not at.exception
    assert at.select_slider(key="_bm_gen").value == 3
