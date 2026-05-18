"""Shared helpers for canonical Gantt payload construction."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


def _relationship_id(pred_id: str, succ_id: str, rel_type: str) -> str:
    return f"{pred_id}->{succ_id}:{rel_type or 'FS'}"


def build_relationship_id(pred_id: str, succ_id: str, rel_type: str) -> str:
    """Public helper for canonical relationship identifier format."""
    return _relationship_id(pred_id, succ_id, rel_type)


def _to_iso_date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except Exception:
            pass
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def _to_iso_text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    text = str(value)
    return text if text else None


def build_schedule_item_payload(
    *,
    item_id: int,
    s_item_id: str,
    s_item: str,
    working_days: float,
    calendar_days: int,
    total_float: float,
    start: Any,
    finish: Any,
    is_critical: bool,
    wbs_path: str,
    status: str,
    percent_complete: float | None,
    level: int,
    is_summary: bool,
    parent_id: str | None,
    children_count: int,
    group_name: str | None,
    baseline_start: Any = None,
    baseline_finish: Any = None,
    baseline_duration_d: float | None = None,
) -> dict[str, Any]:
    return {
        "id": int(item_id),
        "s_item_id": s_item_id,
        "s_item": s_item,
        "working_days": float(working_days),
        "calendar_days": int(calendar_days),
        "total_float": float(total_float),
        "start": _to_iso_date_text(start),
        "finish": _to_iso_date_text(finish),
        "is_critical": bool(is_critical),
        "wbs_path": wbs_path,
        "status": status,
        "percent_complete": percent_complete,
        "level": int(level),
        "is_summary": bool(is_summary),
        "parent_id": parent_id,
        "children_count": int(children_count),
        "group_name": group_name,
        "baseline_start": _to_iso_text_or_none(baseline_start),
        "baseline_finish": _to_iso_text_or_none(baseline_finish),
        "baseline_duration_d": baseline_duration_d,
    }


def build_relationship_projections(
    *,
    raw_relationships: list[dict[str, Any]],
    id_to_code_all: dict[int, str],
    visible_id_set: set[int],
    is_critical_edge: Callable[[int, int], bool] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Build visible and envelope relationship payloads from normalized raw edges.

    Expected raw relationship keys: ``pred_id``, ``succ_id``, ``rel_type``, ``lag_days``.
    """
    visible_relationships: list[dict[str, Any]] = []
    envelope_relationships: list[dict[str, Any]] = []
    visible_relationship_ids: list[str] = []

    seen_visible: set[tuple[int, int, str]] = set()
    seen_all: set[tuple[int, int, str]] = set()

    for rel in raw_relationships:
        pred_id = rel.get("pred_id")
        succ_id = rel.get("succ_id")
        if pred_id is None or succ_id is None:
            continue

        pred_id = int(pred_id)
        succ_id = int(succ_id)
        rel_type = str(rel.get("rel_type") or "FS")
        lag_days = float(rel.get("lag_days") or 0)

        if pred_id in id_to_code_all and succ_id in id_to_code_all:
            all_key = (pred_id, succ_id, rel_type)
            if all_key not in seen_all:
                seen_all.add(all_key)
                pred_code_all = id_to_code_all[pred_id]
                succ_code_all = id_to_code_all[succ_id]
                envelope_relationships.append(
                    {
                        "id": build_relationship_id(pred_code_all, succ_code_all, rel_type),
                        "pred_id": pred_code_all,
                        "succ_id": succ_code_all,
                        "rel_type": rel_type,
                        "lag_days": lag_days,
                    }
                )

        if pred_id in visible_id_set and succ_id in visible_id_set:
            visible_key = (pred_id, succ_id, rel_type)
            if visible_key in seen_visible:
                continue
            seen_visible.add(visible_key)

            pred_code = id_to_code_all.get(pred_id, str(pred_id))
            succ_code = id_to_code_all.get(succ_id, str(succ_id))
            rel_id = build_relationship_id(pred_code, succ_code, rel_type)
            visible_relationship_ids.append(rel_id)
            visible_relationships.append(
                {
                    "pred_id": pred_code,
                    "succ_id": succ_code,
                    "rel_type": rel_type,
                    "lag_days": lag_days,
                    "is_critical": bool(is_critical_edge(pred_id, succ_id)) if is_critical_edge else False,
                }
            )

    return visible_relationships, envelope_relationships, visible_relationship_ids


def _derive_envelope_relationships(relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in relationships:
        pred = str(rel.get("pred_id") or "")
        succ = str(rel.get("succ_id") or "")
        rel_type = str(rel.get("rel_type") or "FS")
        rel_id = _relationship_id(pred, succ, rel_type)
        if rel_id in seen:
            continue
        seen.add(rel_id)
        payload.append(
            {
                "id": rel_id,
                "pred_id": pred,
                "succ_id": succ,
                "rel_type": rel_type,
                "lag_days": float(rel.get("lag_days") or 0),
            }
        )
    return payload


def _derive_visible_relationship_ids(relationships: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for rel in relationships:
        pred = str(rel.get("pred_id") or "")
        succ = str(rel.get("succ_id") or "")
        rel_type = str(rel.get("rel_type") or "FS")
        ids.append(_relationship_id(pred, succ, rel_type))
    return ids


def _derive_own_baseline_rows(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for activity in activities:
        rows.append(
            {
                "id": int(activity.get("id", 0)),
                "s_item_id": str(activity.get("s_item_id") or activity.get("id") or ""),
                "start": activity.get("baseline_start"),
                "finish": activity.get("baseline_finish"),
                "duration_d": activity.get("baseline_duration_d"),
            }
        )
    return rows


def build_v2_gantt_payload(
    *,
    legacy_payload: dict[str, Any],
    view_id: str | None,
    view_title: str,
    project_id: str | int | None,
    schedule_version_id: int | None,
    scenario_id: str | None = None,
    available_baseline_modes: dict[str, bool] | None = None,
    selected_baseline_mode: str | None = None,
    render_options: dict[str, Any] | None = None,
    data_envelope_options: dict[str, Any] | None = None,
    envelope_activities: list[dict[str, Any]] | None = None,
    envelope_relationships: list[dict[str, Any]] | None = None,
    envelope_updates: list[dict[str, Any]] | None = None,
    visible_activity_ids: list[int] | None = None,
    visible_relationship_ids: list[str] | None = None,
    own_baseline_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(legacy_payload)

    items = payload.get("items") or []
    relationships = payload.get("relationships") or []
    filter_applied = payload.get("filter_applied") or {}

    render_options = render_options or {}
    data_envelope_options = data_envelope_options or {}

    if available_baseline_modes is None:
        available_baseline_modes = payload.get("available_baseline_modes") or {
            "own": bool(payload.get("has_baseline")),
            "previous_version": False,
            "database_baseline": False,
        }

    if selected_baseline_mode is None:
        selected_baseline_mode = str(payload.get("baseline_mode") or "own")

    if not available_baseline_modes.get(selected_baseline_mode, False) and available_baseline_modes.get("own", False):
        selected_baseline_mode = "own"

    if envelope_activities is None:
        envelope_activities = list(items)

    if envelope_relationships is None:
        envelope_relationships = _derive_envelope_relationships(list(relationships))

    if visible_activity_ids is None:
        visible_activity_ids = [
            int(item.get("id"))
            for item in items
            if item.get("id") is not None
        ]

    if visible_relationship_ids is None:
        visible_relationship_ids = _derive_visible_relationship_ids(list(relationships))

    if own_baseline_rows is None:
        own_baseline_rows = _derive_own_baseline_rows(envelope_activities)

    include_links = bool(data_envelope_options.get("include_links", True))
    include_updates = bool(data_envelope_options.get("include_updates", True))
    requested_baselines = data_envelope_options.get("include_baselines") or ["own"]

    columns_selected = render_options.get("columns") or ["start", "finish", "duration", "total_float", "percent_complete"]
    columns_available = ["start", "finish", "duration", "total_float", "percent_complete"]

    if envelope_updates is None:
        envelope_updates = payload.get("activity_updates") or []

    payload["schema_version"] = "gantt.custom.v2"
    payload["view"] = {
        "id": view_id,
        "title": view_title,
        "grouping": payload.get("grouping"),
        "source": {
            "project_id": project_id,
            "schedule_version_id": schedule_version_id,
            "scenario_id": scenario_id,
        },
    }

    payload["capabilities"] = {
        "links": {
            "available": bool(envelope_relationships),
            "render_enabled": bool(render_options.get("show_links", True)),
        },
        "updates": {
            "available": bool(envelope_updates),
            "render_enabled": bool(render_options.get("show_updates", True)),
        },
        "baseline_modes": {
            "available": [mode for mode, enabled in available_baseline_modes.items() if enabled],
            "selected": selected_baseline_mode,
        },
        "columns": {
            "available": columns_available,
            "selected": columns_selected,
        },
        "what_if": {
            "supported": True,
            "active_scenario_id": scenario_id,
            "overlay_available": False,
        },
    }

    payload["data_envelope"] = {
        "activities": envelope_activities,
        "relationships": envelope_relationships if include_links else [],
        "baselines": {
            "own": {"activities": own_baseline_rows if "own" in requested_baselines else []},
            "previous_version": {"activities": [] if "previous_version" in requested_baselines else []},
            "database_baseline": {"activities": [] if "database_baseline" in requested_baselines else []},
        },
        "updates": envelope_updates if include_updates else [],
    }

    payload["display"] = {
        "filter_applied": filter_applied,
        "visible_activity_ids": visible_activity_ids,
        "visible_relationship_ids": visible_relationship_ids,
        "project_start": payload.get("project_start", ""),
        "project_finish": payload.get("project_finish", ""),
        "critical_path_length": payload.get("critical_path_length", 0),
        "total_activities": payload.get("total_activities", 0),
        "filtered_activities": payload.get("filtered_activities", 0),
        "preserve_order": payload.get("preserve_order", False),
    }

    payload["available_baseline_modes"] = available_baseline_modes
    payload["baseline_mode"] = selected_baseline_mode
    return payload
