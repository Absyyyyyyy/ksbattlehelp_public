from pathlib import Path
import pytest
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import BenchmarkRoster, roster_to_json
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg.scope import set_session_storage, clear_session_storage


def test_file_roster_persistence(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    set_session_storage(False)

    r = BenchmarkRoster(
        name="Alpha",
        generation=6,
        owned_heroes={"Inf": ["Helga"]},
        builds={"Helga": HeroBuild(level="MAX", widget_level=0)},
    )
    saved_path = ps.save_roster(r, "Alpha")
    assert saved_path.exists()

    assert "Alpha" in ps.list_rosters()
    loaded = ps.load_roster("Alpha")
    assert loaded.name == "Alpha"
    assert loaded.generation == 6
    assert loaded.owned_heroes == {"Inf": ["Helga"]}

    # Test export in file mode
    exported = ps.export_rosters_dict()
    assert "Alpha" in exported

    # Test import in file mode
    r_imported = BenchmarkRoster(name="Gamma", generation=5)
    ps.import_roster_blob("Gamma", roster_to_json(r_imported))
    assert "Gamma" in ps.list_rosters()
    assert ps.load_roster("Gamma").generation == 5

    # Test delete
    ps.delete_roster("Alpha")
    assert "Alpha" not in ps.list_rosters()

    # Test delete non-existent roster does not error
    ps.delete_roster("NonExistent")

    # Test load non-existent roster raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        ps.load_roster("NonExistent")


def test_session_roster_persistence():
    set_session_storage(True)
    clear_session_storage()
    try:
        r = BenchmarkRoster(name="Beta", generation=8, owned_heroes={}, builds={})
        saved_path = ps.save_roster(r, "Beta")
        assert str(saved_path).startswith("/session/rosters")

        assert "Beta" in ps.list_rosters()
        loaded = ps.load_roster("Beta")
        assert loaded.name == "Beta"

        exported = ps.export_rosters_dict()
        assert "Beta" in exported

        # Test import in session mode
        r_delta = BenchmarkRoster(name="Delta", generation=7)
        ps.import_roster_blob("Delta", roster_to_json(r_delta))
        assert "Delta" in ps.list_rosters()
        assert ps.load_roster("Delta").generation == 7

        ps.delete_roster("Beta")
        assert "Beta" not in ps.list_rosters()

        # Test delete non-existent roster in session mode
        ps.delete_roster("NonExistentSession")

        # Test load non-existent roster raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            ps.load_roster("NonExistentSession")
    finally:
        set_session_storage(False)
