import streamlit as st
from unittest.mock import patch

from kingshot_sim.webui.local_storage import (
    _FORM_KEY_PREFIXES,
    _collect_form_state,
    _is_widget_key_persistable,
)


def test_benchmark_widget_key_persistence():
    assert _is_widget_key_persistable("_bm_star_Jabel")
    assert _is_widget_key_persistable("_bm_wl_Jabel")
    assert _is_widget_key_persistable("_bm_tier_Jabel")
    assert _is_widget_key_persistable("_bm_own_Inf")
    assert _is_widget_key_persistable("_bm_active_roster")
    assert _is_widget_key_persistable("_bm_gen")


def test_benchmark_transient_keys_excluded():
    assert not _is_widget_key_persistable("_bm_run")
    assert not _is_widget_key_persistable("_bm_ocr_up")
    assert not _is_widget_key_persistable("_bm_ocr_go")
    assert not _is_widget_key_persistable("_bm_ocr_msg")
    assert not _is_widget_key_persistable("_bm_ocr_up_gen1")
    assert not _is_widget_key_persistable("_bm_ocr_go_gen1")
    assert not _is_widget_key_persistable("_bm_ocr_msg_gen1")
    assert not _is_widget_key_persistable("_bm_preset_infantry")
    assert not _is_widget_key_persistable("_bm_preset_clear")


def test_form_key_prefixes_includes_bm():
    assert "_bm_" in _FORM_KEY_PREFIXES


def test_collect_form_state_with_benchmark_keys():
    mock_ss = {
        "_bm_star_Jabel": 5,
        "_bm_wl_Jabel": 2,
        "_bm_tier_Jabel": "T10",
        "_bm_own_Inf": ["Jabel", "Aman"],
        "_bm_active_roster": "Default",
        "_bm_gen": 7,
        # transient keys that must NOT be collected:
        "_bm_run": True,
        "_bm_ocr_up": "mock_file_uploader_state",
        "_bm_ocr_go": True,
        "_bm_ocr_msg": "Analysis complete",
        "_bm_preset_cav": True,
        # non-benchmark keys:
        "other_key": 123,
    }
    with patch.object(st, "session_state", mock_ss):
        collected = _collect_form_state()

    assert collected.get("_bm_star_Jabel") == 5
    assert collected.get("_bm_wl_Jabel") == 2
    assert collected.get("_bm_tier_Jabel") == "T10"
    assert collected.get("_bm_own_Inf") == ["Jabel", "Aman"]
    assert collected.get("_bm_active_roster") == "Default"
    assert collected.get("_bm_gen") == 7

    assert "_bm_run" not in collected
    assert "_bm_ocr_up" not in collected
    assert "_bm_ocr_go" not in collected
    assert "_bm_ocr_msg" not in collected
    assert "_bm_preset_cav" not in collected
    assert "other_key" not in collected


def test_hydrate_from_browser_benchmark_keys():
    import json
    from unittest.mock import MagicMock
    from kingshot_sim.webui.local_storage import hydrate_from_browser, SCHEMA_VERSION, _HYDRATED_FLAG

    mock_ls = MagicMock()
    payload = {
        "schema": SCHEMA_VERSION,
        "backup": {},
        "form": {
            "_bm_star_Jabel": 5,
            "_bm_wl_Jabel": 2,
            "_bm_tier_Jabel": "T10",
            "_bm_run": True,
            "_bm_ocr_up": "file",
        },
        "ui": {},
    }
    mock_ls.getItem.return_value = json.dumps(payload)

    mock_ss = {}
    with patch("kingshot_sim.webui.local_storage._get_local_storage", return_value=mock_ls):
        with patch.object(st, "session_state", mock_ss):
            hydrate_from_browser()

    assert mock_ss.get("_bm_star_Jabel") == 5
    assert mock_ss.get("_bm_wl_Jabel") == 2
    assert mock_ss.get("_bm_tier_Jabel") == "T10"
    assert "_bm_run" not in mock_ss
    assert "_bm_ocr_up" not in mock_ss
    assert mock_ss.get(_HYDRATED_FLAG) is True
