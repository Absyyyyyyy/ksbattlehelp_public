import pytest
import json
from pathlib import Path
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg import backup
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui.local_storage import LOCAL_STORAGE_KEYS


def test_backup_payload_includes_rosters(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(ps, "_SEARCH_DIR", tmp_path / "searches")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    r = AccountRoster(name="BackupRosterTest", generation=8)
    ps.save_roster(r, "BackupRosterTest")

    payload = backup.build_backup_payload()
    assert "rosters" in payload
    assert "BackupRosterTest" in payload["rosters"]
    assert isinstance(payload["rosters"]["BackupRosterTest"], str)


def test_backup_restore_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(ps, "_SEARCH_DIR", tmp_path / "searches")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    r = AccountRoster(name="RestoreMe", generation=8, owned_heroes={"Inf": ["Eric"]})
    saved = ps.save_roster(r, "RestoreMe")

    blob = backup.make_backup_blob()
    assert '"RestoreMe"' in blob

    # Delete the roster
    ps.delete_roster("RestoreMe")
    assert "RestoreMe" not in ps.list_rosters()

    # Parse and apply
    parsed, err = backup.parse_backup_blob(blob)
    assert err is None
    assert "rosters" in parsed

    report = backup.apply_backup_payload(parsed, replace_existing=False)
    assert report.rosters_applied == 1
    assert "RestoreMe" in ps.list_rosters()

    loaded = ps.load_roster("RestoreMe")
    assert loaded.name == "RestoreMe"
    assert loaded.generation == 8
    assert loaded.owned_heroes == {"Inf": ["Eric"]}


def test_backup_restore_replace_existing_rosters(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(ps, "_SEARCH_DIR", tmp_path / "searches")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    old_r = AccountRoster(name="OldRoster", generation=5)
    ps.save_roster(old_r, "OldRoster")

    new_r = AccountRoster(name="NewRoster", generation=8)
    ps.save_roster(new_r, "NewRoster")
    blob = backup.make_backup_blob()

    # Create another roster that should be wiped on replace_existing=True
    wiped_r = AccountRoster(name="WipedRoster", generation=6)
    ps.save_roster(wiped_r, "WipedRoster")
    assert "WipedRoster" in ps.list_rosters()

    parsed, err = backup.parse_backup_blob(blob)
    assert err is None

    report = backup.apply_backup_payload(parsed, replace_existing=True)
    assert report.rosters_applied == 2
    assert "WipedRoster" not in ps.list_rosters()
    assert "OldRoster" in ps.list_rosters()
    assert "NewRoster" in ps.list_rosters()


def test_import_report_rosters():
    rep = backup.ImportReport(rosters_applied=3)
    assert rep.total_applied == 3
    assert "3 roster(s)" in rep.summary()


def test_local_storage_keys_includes_active_roster():
    assert "_ks_active_roster" in LOCAL_STORAGE_KEYS
