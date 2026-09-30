import pytest
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg import backup
import streamlit as st


@pytest.fixture
def session_backend(monkeypatch):
    monkeypatch.setenv("KS_SESSION_PROFILES", "1")
    st.session_state.clear()
    yield
    st.session_state.clear()


def test_backup_roundtrip_with_rosters(session_backend):
    r = AccountRoster(name="SavedRoster", generation=7, builds={"Helga": HeroBuild(level="MAX", widget_level=0)})
    ps.save_roster(r, "SavedRoster")

    blob = backup.make_backup_blob()
    payload, err = backup.parse_backup_blob(blob)
    assert err is None
    assert "rosters" in payload
    assert "SavedRoster" in payload["rosters"]

    ps.delete_roster("SavedRoster")
    assert "SavedRoster" not in ps.list_rosters()

    rep = backup.apply_backup_payload(payload, replace_existing=False)
    assert rep.rosters_applied == 1
    assert rep.total_applied >= 1
    assert "SavedRoster" in ps.list_rosters()
    assert "1 roster(s)" in rep.summary()


def test_backup_backwards_compatibility_without_rosters(session_backend):
    legacy_payload = {
        "version": 1,
        "format": "ksbattlehelper-backup",
        "profiles": {},
        "search_spaces": {},
    }
    rep = backup.apply_backup_payload(legacy_payload, replace_existing=False)
    assert rep.rosters_applied == 0
    assert not rep.errors


def test_backup_replace_existing_rosters(session_backend):
    r1 = AccountRoster(name="OldRoster", generation=1, builds={})
    ps.save_roster(r1, "OldRoster")
    assert "OldRoster" in ps.list_rosters()

    r2 = AccountRoster(name="NewRoster", generation=2, builds={})
    payload = {
        "version": 1,
        "format": "ksbattlehelper-backup",
        "rosters": {
            "NewRoster": ps.roster_to_json(r2),
        },
    }

    rep = backup.apply_backup_payload(payload, replace_existing=True)
    assert rep.rosters_applied == 1
    assert "OldRoster" not in ps.list_rosters()
    assert "NewRoster" in ps.list_rosters()


def test_backup_rosters_invalid_payload_and_corrupt_entry(session_backend):
    # Invalid rosters type (not a dict)
    bad_payload = {
        "version": 1,
        "format": "ksbattlehelper-backup",
        "rosters": ["not", "a", "dict"],
    }
    rep = backup.apply_backup_payload(bad_payload, replace_existing=False)
    assert any("'rosters' section is not an object" in err for err in rep.errors)

    # Corrupted roster json
    corrupted_payload = {
        "version": 1,
        "format": "ksbattlehelper-backup",
        "rosters": {
            "BrokenRoster": "{not valid json",
        },
    }
    rep2 = backup.apply_backup_payload(corrupted_payload, replace_existing=False)
    assert rep2.rosters_applied == 0
    assert any("roster 'BrokenRoster'" in err for err in rep2.errors)
