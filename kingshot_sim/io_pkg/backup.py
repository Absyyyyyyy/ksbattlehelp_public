from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any

from kingshot_sim.data import op_overrides as op_ov
from kingshot_sim.data import user_data as ud
from kingshot_sim.webui import persistence as ps


BACKUP_VERSION = 1


def build_backup_payload() -> dict[str, Any]:
    op_payload: list[dict[str, int | str]] = []
    for (hero, slot), rules in sorted(op_ov.list_op_overrides().items()):
        for orig, new in rules:
            op_payload.append({
                "hero": hero, "slot": slot,
                "original_op": int(orig), "new_op": int(new),
            })

    data_payload = dict(sorted(ud.list_data_overrides().items()))

    return {
        "version": BACKUP_VERSION,
        "format": "ksbattlehelper-backup",
        "profiles": ps.export_profiles_dict(),
        "search_spaces": ps.export_searches_dict(),
        "rosters": ps.export_rosters_dict(),
        "op_overrides": op_payload,
        "data_overrides": data_payload,
    }


def make_backup_blob(*, indent: int | None = 2) -> str:
    return json.dumps(build_backup_payload(), indent=indent, sort_keys=False)


@dataclass
class ImportReport:
    profiles_applied: int = 0
    searches_applied: int = 0
    rosters_applied: int = 0
    op_overrides_applied: int = 0
    data_overrides_applied: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_applied(self) -> int:
        return (self.profiles_applied + self.searches_applied
                + self.rosters_applied
                + self.op_overrides_applied + self.data_overrides_applied)

    def summary(self) -> str:
        parts = []
        if self.profiles_applied:
            parts.append(f"{self.profiles_applied} profile(s)")
        if self.searches_applied:
            parts.append(f"{self.searches_applied} roster/search space(s)")
        if self.rosters_applied:
            parts.append(f"{self.rosters_applied} roster(s)")
        if self.op_overrides_applied:
            parts.append(f"{self.op_overrides_applied} op-code override(s)")
        if self.data_overrides_applied:
            parts.append(f"{self.data_overrides_applied} data override(s)")
        if not parts:
            return "Nothing imported."
        return "Imported " + ", ".join(parts) + "."


def parse_backup_blob(raw_text: str) -> tuple[dict[str, Any], str | None]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return {}, f"Malformed JSON: {e}"
    if not isinstance(parsed, dict):
        return {}, "Top-level JSON must be an object."
    fmt = parsed.get("format")
    if fmt is not None and fmt != "ksbattlehelper-backup":
        return {}, (
            f"Unexpected format tag {fmt!r}. This file does not look "
            "like a KingShot Battle Helper backup."
        )
    return parsed, None


def apply_backup_payload(
    payload: dict[str, Any],
    *,
    replace_existing: bool,
) -> ImportReport:
    report = ImportReport()

    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        report.errors.append("'profiles' section is not an object — skipped.")
        profiles = {}

    if replace_existing:
        for name in list(ps.list_profiles()):
            ps.delete_profile(name)
    for name, blob in profiles.items():
        try:
            ps.import_profile_blob(str(name), str(blob))
            report.profiles_applied += 1
        except Exception as e:
            report.errors.append(f"profile {name!r}: {e}")

    searches = payload.get("search_spaces", {})
    if not isinstance(searches, dict):
        report.errors.append("'search_spaces' section is not an object — skipped.")
        searches = {}

    if replace_existing:
        for name in list(ps.list_search_spaces()):
            ps.delete_search(name)
    for name, blob in searches.items():
        try:
            ps.import_search_blob(str(name), str(blob))
            report.searches_applied += 1
        except Exception as e:
            report.errors.append(f"search space {name!r}: {e}")

    rosters = payload.get("rosters", {})
    if not isinstance(rosters, dict):
        report.errors.append("'rosters' section is not an object — skipped.")
        rosters = {}

    if replace_existing:
        for name in list(ps.list_rosters()):
            ps.delete_roster(name)
    for name, blob in rosters.items():
        try:
            ps.import_roster_blob(str(name), str(blob))
            report.rosters_applied += 1
        except Exception as e:
            report.errors.append(f"roster {name!r}: {e}")

    op_list = payload.get("op_overrides", [])
    if not isinstance(op_list, list):
        report.errors.append("'op_overrides' section is not a list — skipped.")
        op_list = []

    if replace_existing:
        op_ov.clear_all_overrides()
    for entry in op_list:
        try:
            op_ov.set_op_override(
                entry["hero"], entry["slot"],
                int(entry["original_op"]), int(entry["new_op"]),
            )
            report.op_overrides_applied += 1
        except (KeyError, TypeError, ValueError) as e:
            report.errors.append(f"op-override {entry!r}: {e}")

    data_map = payload.get("data_overrides", {})
    if not isinstance(data_map, dict):
        report.errors.append("'data_overrides' section is not an object — skipped.")
        data_map = {}

    if replace_existing:
        ud.clear_all_data_overrides()
    for key, value in data_map.items():
        try:
            ud.set_data_override(str(key), value)
            report.data_overrides_applied += 1
        except ValueError as e:
            report.errors.append(f"data-override {key!r}: {e}")

    return report


__all__ = [
    "BACKUP_VERSION",
    "ImportReport",
    "build_backup_payload",
    "make_backup_blob",
    "parse_backup_blob",
    "apply_backup_payload",
]
