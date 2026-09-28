from __future__ import annotations

import json
import pytest
from streamlit.testing.v1 import AppTest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
)
from kingshot_sim.io_pkg import scope, backup as backup_mod
from kingshot_sim.io_pkg.profiles import fighter_to_json


def _sample_fighter(label: str = "TestProfile") -> Fighter:
    return Fighter(
        label=label,
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=100, squad_def_pct=80),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=50_000),),
            cavalry=(TroopGroup(tier="T10.5", count=50_000),),
            archer=(TroopGroup(tier="T10.5", count=50_000),),
        ),
    )


def test_scope_outside_streamlit_returns_false():
    assert scope.in_streamlit_context() is False
    assert scope.use_session_storage() is False


def test_scope_disk_opt_out_env_var(monkeypatch):
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    assert scope.in_streamlit_context() is False


def test_scope_force_session_env_var(monkeypatch):
    monkeypatch.setenv("KS_SESSION_PROFILES", "1")
    assert scope.use_session_storage() is True


def _set_op_override_in_app() -> None:
    import streamlit as st
    from kingshot_sim.data.op_overrides import set_op_override, list_op_overrides
    set_op_override("Vivian", "sk1", 211, 101)
    st.session_state["_observed_overrides"] = list_op_overrides()


def _read_op_overrides_in_app() -> None:
    import streamlit as st
    from kingshot_sim.data.op_overrides import list_op_overrides
    st.session_state["_observed_overrides"] = list_op_overrides()


def test_op_overrides_isolated_across_sessions():
    at_a = AppTest.from_function(_set_op_override_in_app)
    at_a.run()
    assert at_a.session_state["_observed_overrides"] == {
        ("Vivian", "sk1"): [(211, 101)]
    }, "Override must be visible in the session that set it"

    at_b = AppTest.from_function(_read_op_overrides_in_app)
    at_b.run()
    assert at_b.session_state["_observed_overrides"] == {}, (
        "Override set in session A must NOT be visible in session B "
        "(this was the data-leak bug)."
    )


def _set_data_override_in_app() -> None:
    import streamlit as st
    from kingshot_sim.data.user_data import set_data_override, list_data_overrides
    set_data_override("hero_max.Yang", 999.0)
    st.session_state["_observed_data"] = list_data_overrides()


def _read_data_overrides_in_app() -> None:
    import streamlit as st
    from kingshot_sim.data.user_data import list_data_overrides
    st.session_state["_observed_data"] = list_data_overrides()


def test_data_overrides_isolated_across_sessions():
    at_a = AppTest.from_function(_set_data_override_in_app)
    at_a.run()
    assert at_a.session_state["_observed_data"] == {"hero_max.Yang": 999.0}

    at_b = AppTest.from_function(_read_data_overrides_in_app)
    at_b.run()
    assert at_b.session_state["_observed_data"] == {}, (
        "Data override set in session A must NOT be visible in session B."
    )


def _save_profile_in_app() -> None:
    import streamlit as st
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    from kingshot_sim.webui import persistence
    f = Fighter(
        label="ProfileSetInSessionA",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(infantry=(), cavalry=(), archer=()),
    )
    persistence.save_profile(f, "session_a_profile")
    st.session_state["_observed_profiles"] = persistence.list_profiles()


def _list_profiles_in_app() -> None:
    import streamlit as st
    from kingshot_sim.webui import persistence
    st.session_state["_observed_profiles"] = persistence.list_profiles()
    st.session_state["_uses_session"] = persistence.is_session_backend()


def test_profile_save_isolated_across_sessions():
    at_a = AppTest.from_function(_save_profile_in_app)
    at_a.run()
    assert "session_a_profile" in at_a.session_state["_observed_profiles"]

    at_b = AppTest.from_function(_list_profiles_in_app)
    at_b.run()
    assert at_b.session_state["_uses_session"] is True, (
        "Inside a Streamlit context, persistence MUST default to "
        "session backend (the bug fix)."
    )
    assert "session_a_profile" not in at_b.session_state["_observed_profiles"], (
        "Profile saved in session A must NOT appear in session B's list."
    )


def _render_settings_tab() -> None:
    import streamlit as st
    st.session_state["_ks_active_tab"] = "⚙️ Settings"
    from kingshot_sim.webui.app import main
    main()


def test_settings_tab_renders_without_exception():
    at = AppTest.from_function(_render_settings_tab)
    at.run()
    assert not at.exception, f"Settings tab raised: {at.exception}"


def test_backup_blob_has_expected_top_level_shape():
    payload, err = backup_mod.parse_backup_blob('"just a string"')
    assert err is not None

    payload, err = backup_mod.parse_backup_blob(
        json.dumps({"format": "something-else"})
    )
    assert err is not None and "format" in err.lower()

    payload, err = backup_mod.parse_backup_blob(json.dumps({}))
    assert err is None
    assert payload == {}


def test_backup_blob_round_trip_in_session(monkeypatch):
    monkeypatch.setenv("KS_SESSION_PROFILES", "1")

    def _round_trip_in_app() -> None:
        import streamlit as st
        from kingshot_sim.data.op_overrides import (
            set_op_override, clear_all_overrides, list_op_overrides,
        )
        from kingshot_sim.data.user_data import (
            set_data_override, clear_all_data_overrides, list_data_overrides,
        )
        from kingshot_sim.webui import persistence
        from kingshot_sim.io_pkg import backup as bm
        from kingshot_sim.config.fighter import (
            Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
        )

        f = Fighter(
            label="RoundTrip",
            leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
            leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
            leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
            joiners=(),
            bonuses=BonusVector(),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T10.5", count=10_000),),
                cavalry=(),
                archer=(),
            ),
        )
        persistence.save_profile(f, "rt_profile")
        set_op_override("Vivian", "sk1", 211, 101)
        set_data_override("hero_max.Yang", 600.0)

        blob = bm.make_backup_blob()
        st.session_state["_blob"] = blob

        persistence.delete_profile("rt_profile")
        clear_all_overrides()
        clear_all_data_overrides()
        assert persistence.list_profiles() == []
        assert list_op_overrides() == {}
        assert list_data_overrides() == {}

        parsed, err = bm.parse_backup_blob(blob)
        assert err is None
        report = bm.apply_backup_payload(parsed, replace_existing=True)
        st.session_state["_report"] = {
            "profiles": report.profiles_applied,
            "ops": report.op_overrides_applied,
            "data": report.data_overrides_applied,
            "errors": list(report.errors),
        }

        st.session_state["_final_profiles"] = persistence.list_profiles()
        st.session_state["_final_ops"] = list_op_overrides()
        st.session_state["_final_data"] = list_data_overrides()

    at = AppTest.from_function(_round_trip_in_app)
    at.run()
    assert not at.exception, f"Round-trip script crashed: {at.exception}"

    rep = at.session_state["_report"]
    assert rep["profiles"] == 1, "One profile should have been restored"
    assert rep["ops"] == 1, "One op override should have been restored"
    assert rep["data"] == 1, "One data override should have been restored"
    assert rep["errors"] == [], (
        f"Round-trip should produce no errors, got: {rep['errors']}"
    )

    assert "rt_profile" in at.session_state["_final_profiles"]
    assert at.session_state["_final_ops"] == {("Vivian", "sk1"): [(211, 101)]}
    assert at.session_state["_final_data"] == {"hero_max.Yang": 600.0}


def _import_partial_in_app() -> None:
    import streamlit as st
    from kingshot_sim.data.op_overrides import clear_all_overrides
    from kingshot_sim.data.user_data import clear_all_data_overrides
    from kingshot_sim.io_pkg import backup as bm
    from kingshot_sim.webui import persistence
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, LeaderHero,
    )
    from kingshot_sim.io_pkg.profiles import fighter_to_json

    for n in list(persistence.list_profiles()):
        persistence.delete_profile(n)
    clear_all_overrides()
    clear_all_data_overrides()

    fighter_json = fighter_to_json(Fighter(
        label="OK",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(infantry=(), cavalry=(), archer=()),
    ))

    payload = {
        "format": "ksbattlehelper-backup",
        "version": 1,
        "profiles": {"good_profile": fighter_json},
        "search_spaces": {},
        "op_overrides": [
            {"hero": "Vivian", "slot": "sk1", "original_op": 211, "new_op": 999_999},
            {"hero": "Vivian", "slot": "sk1", "original_op": 211, "new_op": 101},
        ],
        "data_overrides": {"hero_max.Yang": 700.0},
    }
    report = bm.apply_backup_payload(payload, replace_existing=False)
    st.session_state["_partial_report"] = {
        "profiles_applied": report.profiles_applied,
        "ops_applied": report.op_overrides_applied,
        "data_applied": report.data_overrides_applied,
        "errors_count": len(report.errors),
    }


def test_apply_backup_payload_collects_errors_without_aborting():
    at = AppTest.from_function(_import_partial_in_app)
    at.run()
    assert not at.exception, f"Partial-import script crashed: {at.exception}"

    rep = at.session_state["_partial_report"]
    assert rep["profiles_applied"] == 1
    assert rep["ops_applied"] == 1
    assert rep["data_applied"] == 1
    assert rep["errors_count"] == 1, (
        "The one malformed op override should appear in errors, "
        f"got {rep['errors_count']}"
    )
