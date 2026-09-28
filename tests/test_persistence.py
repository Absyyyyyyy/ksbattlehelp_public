import pytest
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg.rosters import AccountRoster, roster_to_json
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.config.fighter import BonusVector


def test_persistence_roster_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    r = AccountRoster(
        name="PersistTest",
        generation=8,
        owned_heroes={"Inf": ["Eric", "Howard"]},
        builds={"Eric": HeroBuild(level="MAX", widget_level=10)},
        bonuses=BonusVector(squad_atk_pct=15.0),
    )
    saved_path = ps.save_roster(r, "PersistTest")
    assert saved_path.exists()
    assert "PersistTest" in ps.list_rosters()

    loaded = ps.load_roster("PersistTest")
    assert loaded.name == "PersistTest"
    assert loaded.generation == 8
    assert loaded.owned_heroes == {"Inf": ["Eric", "Howard"]}
    assert loaded.builds["Eric"].widget_level == 10
    assert loaded.bonuses.squad_atk_pct == 15.0

    ps.delete_roster("PersistTest")
    assert "PersistTest" not in ps.list_rosters()
    assert not saved_path.exists()


def test_persistence_roster_session_mode(monkeypatch):
    session_store: dict[str, str] = {}
    monkeypatch.setattr(ps, "_use_session_backend", lambda: True)
    monkeypatch.setattr(ps, "_ss_rosters", lambda: session_store)

    r = AccountRoster(name="SessionRoster", generation=7)
    path = ps.save_roster(r, "SessionRoster")
    assert str(path).startswith("/session/rosters")
    assert "SessionRoster" in ps.list_rosters()

    loaded = ps.load_roster("SessionRoster")
    assert loaded.name == "SessionRoster"
    assert loaded.generation == 7

    ps.delete_roster("SessionRoster")
    assert "SessionRoster" not in ps.list_rosters()

    with pytest.raises(FileNotFoundError):
        ps.load_roster("SessionRoster")


def test_persistence_roster_export_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    r1 = AccountRoster(name="Roster1", generation=6)
    r2 = AccountRoster(name="Roster2", generation=8)
    ps.save_roster(r1, "Roster1")
    ps.save_roster(r2, "Roster2")

    exported = ps.export_rosters_dict()
    assert "Roster1" in exported
    assert "Roster2" in exported
    assert isinstance(exported["Roster1"], str)

    # In session mode
    session_store = dict(exported)
    monkeypatch.setattr(ps, "_use_session_backend", lambda: True)
    monkeypatch.setattr(ps, "_ss_rosters", lambda: session_store)
    session_exported = ps.export_rosters_dict()
    assert session_exported == exported


def test_persistence_load_nonexistent_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    with pytest.raises(FileNotFoundError):
        ps.load_roster("NonExistentRoster")


def test_persistence_import_roster_blob(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    monkeypatch.setattr(ps, "_use_session_backend", lambda: False)

    # 1. Test with dict payload
    dict_payload = {
        "version": 2,
        "format": "ksbattlehelper-roster",
        "name": "DictRoster",
        "generation": 8,
        "owned_heroes": {"Inf": ["Eric"]},
    }
    ps.import_roster_blob("DictRoster", dict_payload)
    assert "DictRoster" in ps.list_rosters()
    loaded_dict = ps.load_roster("DictRoster")
    assert loaded_dict.name == "DictRoster"
    assert loaded_dict.generation == 8
    assert loaded_dict.owned_heroes == {"Inf": ["Eric"]}

    # 2. Test with json string payload
    r = AccountRoster(name="JsonRoster", generation=7, owned_heroes={"Cav": ["Margot"]})
    json_payload = roster_to_json(r)
    ps.import_roster_blob("JsonRoster", json_payload)
    assert "JsonRoster" in ps.list_rosters()
    loaded_json = ps.load_roster("JsonRoster")
    assert loaded_json.name == "JsonRoster"
    assert loaded_json.generation == 7
    assert loaded_json.owned_heroes == {"Cav": ["Margot"]}
