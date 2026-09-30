from __future__ import annotations

from streamlit.testing.v1 import AppTest

from kingshot_sim.config.fighter import HeroGearPiece, BonusVector
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.benchmark.advisor import simulate
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui import persistence


def test_simulate_with_class_gear():
    builds = {
        "Eric": HeroBuild(level="MAX", widget_level=4),
        "Amadeus": HeroBuild(level="MAX", widget_level=4),
        "Petra": HeroBuild(level="MAX", widget_level=4),
        "Margot": HeroBuild(level="MAX", widget_level=4),
        "Jaeger": HeroBuild(level="MAX", widget_level=4),
    }

    # Simulate without gear
    passes_no_gear = simulate(1, builds, class_gear=None)
    score_no_gear = passes_no_gear.cur.per_hero["solo_atk"]["Petra"]

    # Simulate with mythic/red cav gear
    cav_gear = {
        "Cav": {
            "boots": HeroGearPiece(slot="boots", quality="red", level=100, forge_mastery=10),
            "gloves": HeroGearPiece(slot="gloves", quality="red", level=100, forge_mastery=10),
        }
    }
    passes_with_gear = simulate(1, builds, class_gear=cav_gear)
    score_with_gear = passes_with_gear.cur.per_hero["solo_atk"]["Petra"]

    # Cav gear should increase Petra's benchmark performance
    assert score_with_gear > score_no_gear
    assert getattr(passes_with_gear, "class_gear", None) == cav_gear


def _render_benchmark_app():
    from kingshot_sim.webui.tabs.benchmark import render
    render()


def _bench() -> AppTest:
    at = AppTest.from_function(_render_benchmark_app, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _use_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KS_PERSIST_TO_DISK", "1")
    monkeypatch.setattr(persistence, "_ROSTERS_DIR", tmp_path / "rosters")


def _alpha() -> AccountRoster:
    return AccountRoster(
        name="ProfileAlpha",
        generation=7,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={
            "Eric": HeroBuild(level="4_2", widget_level=5, skill_levels=(5, 3, 2)),
            "Petra": HeroBuild(level="MAX", widget_level=8),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=30)}},
        bonuses=BonusVector(inf_atk_pct=50.0),
        buffs=Buffs(city_atk=10),
    )


def test_benchmark_toolbar_empty_rosters_no_crash(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    at = _bench()
    assert not [b for b in at.button if b.key == "benchmark_save_roster_btn"]


def test_benchmark_loads_selected_profile_into_widgets(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    persistence.save_roster(_alpha(), "ProfileAlpha")
    persistence.save_roster(AccountRoster(
        name="ProfileBeta",
        generation=6,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Jaeger"]},
        builds={"Amadeus": HeroBuild(level="MAX", widget_level=10)},
    ), "ProfileBeta")

    at = _bench()
    assert at.selectbox(key="benchmark_roster_select").value == "ProfileAlpha"
    assert at.select_slider(key="_bm_gen").value == 7
    assert at.number_input(key="_bm_star_Eric").value == 4
    assert at.number_input(key="_bm_tier_Eric").value == 2
    assert at.slider(key="_bm_wl_Eric").value == 5

    at.selectbox(key="benchmark_roster_select").select("ProfileBeta").run()
    assert not at.exception
    assert at.select_slider(key="_bm_gen").value == 6
    assert at.multiselect(key="_bm_own_Inf").value == ["Amadeus"]
    assert at.slider(key="_bm_wl_Amadeus").value == 10
    assert at.session_state["_ks_active_roster"] == "ProfileBeta"


def test_benchmark_save_back_writes_widget_edits(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    persistence.save_roster(_alpha(), "ProfileAlpha")
    at = _bench()

    at.number_input(key="_bm_star_Eric").set_value(3).run()
    at.number_input(key="_bm_tier_Eric").set_value(1).run()
    at.slider(key="_bm_wl_Eric").set_value(1).run()
    extra = [h for h in at.multiselect(key="_bm_own_Inf").options if h != "Eric"][0]
    at.multiselect(key="_bm_own_Inf").select(extra).run()
    assert not at.exception

    # Edits stay local until saved back.
    assert persistence.load_roster("ProfileAlpha").builds["Eric"].level == "4_2"

    at.button(key="benchmark_save_roster_btn").click().run()
    assert not at.exception
    saved = persistence.load_roster("ProfileAlpha")
    assert saved.builds["Eric"].level == "3_1"
    assert saved.builds["Eric"].widget_level == 1
    assert saved.owned_heroes["Inf"] == ["Eric", extra]


def test_benchmark_save_back_keeps_account_data(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    persistence.save_roster(_alpha(), "ProfileAlpha")
    at = _bench()

    at.slider(key="_bm_wl_Eric").set_value(9).run()
    at.button(key="benchmark_save_roster_btn").click().run()
    assert not at.exception

    saved = persistence.load_roster("ProfileAlpha")
    assert saved.builds["Eric"].widget_level == 9
    assert saved.builds["Eric"].skill_levels == (5, 3, 2)
    assert saved.class_gear["Inf"]["head"].level == 30
    assert saved.bonuses.inf_atk_pct == 50.0
    assert saved.buffs.city_atk == 10


def test_benchmark_save_back_keeps_heroes_above_generation(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    persistence.save_roster(AccountRoster(
        name="Late", generation=7,
        owned_heroes={"Inf": ["Eric", "Charles"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={"Charles": HeroBuild(level="3_2", widget_level=6)},
    ), "Late")
    at = _bench()

    at.select_slider(key="_bm_gen").set_value(1).run()
    assert "Charles" not in at.multiselect(key="_bm_own_Inf").options
    at.button(key="benchmark_save_roster_btn").click().run()
    assert not at.exception

    saved = persistence.load_roster("Late")
    assert saved.generation == 1
    assert "Charles" in saved.owned_heroes["Inf"]
    assert saved.builds["Charles"] == HeroBuild(level="3_2", widget_level=6)


def test_benchmark_edits_survive_reruns_with_spaced_profile_name(tmp_path, monkeypatch):
    # "New Profile" is stored as New_Profile.json; the tab must not reload it on every rerun.
    _use_disk(tmp_path, monkeypatch)
    persistence.save_roster(AccountRoster(
        name="New Profile", generation=7,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={"Eric": HeroBuild(level="MAX", widget_level=4)},
    ), "New Profile")
    at = _bench()

    at.number_input(key="_bm_star_Eric").set_value(3).run()
    at.run()
    assert at.number_input(key="_bm_star_Eric").value == 3

    at.button(key="benchmark_save_roster_btn").click().run()
    assert persistence.list_rosters() == ["New_Profile"]
    assert persistence.load_roster("New_Profile").builds["Eric"].level.startswith("3_")


def test_benchmark_reload_reverts_local_overrides(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    persistence.save_roster(_alpha(), "ProfileAlpha")
    at = _bench()

    at.number_input(key="_bm_star_Eric").set_value(2).run()
    at.slider(key="_bm_wl_Eric").set_value(9).run()
    at.button(key="benchmark_reload_roster_btn").click().run()
    assert not at.exception

    assert at.number_input(key="_bm_star_Eric").value == 4
    assert at.number_input(key="_bm_tier_Eric").value == 2
    assert at.slider(key="_bm_wl_Eric").value == 5


def test_benchmark_analyse_uses_profile_class_gear(tmp_path, monkeypatch):
    _use_disk(tmp_path, monkeypatch)
    base = dict(
        generation=3,
        owned_heroes={"Inf": ["Eric"], "Cav": ["Petra"], "Arc": ["Jaeger"]},
        builds={h: HeroBuild(level="MAX", widget_level=4) for h in ("Eric", "Petra", "Jaeger")},
    )
    red = HeroGearPiece(slot="boots", quality="red", level=100, forge_mastery=10)
    persistence.save_roster(AccountRoster(name="Geared", class_gear={"Cav": {"boots": red}}, **base), "Geared")
    persistence.save_roster(AccountRoster(name="Plain", **base), "Plain")

    def petra_solo_atk(profile: str) -> float:
        at = _bench()
        at.selectbox(key="benchmark_roster_select").select(profile).run()
        at.button(key="_bm_run").click().run()
        assert not at.exception
        rgen, _, cur = at.session_state["_bm_result"]
        assert rgen == 3
        return cur.per_hero["solo_atk"]["Petra"]

    assert petra_solo_atk("Geared") > petra_solo_atk("Plain")
