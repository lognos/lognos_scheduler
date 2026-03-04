"""Service for schedule preloading and persisted view payload generation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha1
from typing import Optional

import logfire

from backend.repositories.ms_schedule_repository import MSScheduleRepository
from backend.repositories.schedule_view_repository import ScheduleViewRepository
from backend.services.gantt_payload_builder import (
    build_v2_gantt_payload,
    build_relationship_projections,
    build_schedule_item_payload,
)


class ScheduleViewService:
    """Build and cache schedule views for instant UI switching."""

    VIEW_KEYS = ("critical_path", "lookahead_4w", "full_schedule", "updates")

    def __init__(
        self,
        ms_repository: MSScheduleRepository,
        view_repository: ScheduleViewRepository,
    ):
        self.ms_repository = ms_repository
        self.view_repository = view_repository

    @staticmethod
    def _normalize_datetime(raw: object) -> Optional[datetime]:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, date):
            return datetime.combine(raw, datetime.min.time())
        try:
            text = str(raw)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text)
        except Exception:
            return None

    @staticmethod
    def _activity_status(activity: dict) -> str:
        percent = float(activity.get("percent_complete") or 0)
        actual_start = activity.get("actual_start")
        if percent >= 100:
            return "completed"
        if actual_start or percent > 0:
            return "in_progress"
        return "not_started"

    @staticmethod
    def _is_critical(activity: dict) -> bool:
        value = activity.get("total_float_d")
        if value is None:
            return False
        try:
            return float(value) <= 0
        except Exception:
            return False

    @staticmethod
    def _wbs_level(wbs: str | None) -> int:
        if not wbs:
            return 1
        return max(1, len(str(wbs).split(".")))

    @staticmethod
    def _duration_days(start_dt: Optional[datetime], finish_dt: Optional[datetime]) -> int:
        if not start_dt or not finish_dt:
            return 0
        return max(0, (finish_dt.date() - start_dt.date()).days + 1)

    @staticmethod
    def _is_effectively_empty_payload(payload: object) -> bool:
        if not isinstance(payload, dict):
            return True
        items = payload.get("items")
        if not isinstance(items, list):
            return True
        return len(items) == 0

    @classmethod
    def _should_refresh_snapshot(cls, *, view_key: str, snapshot: Optional[dict]) -> bool:
        if snapshot is None:
            return True
        payload = snapshot.get("payload")
        if view_key == "critical_path" and cls._is_effectively_empty_payload(payload):
            return True
        # Updates view is always recomputed (updates can arrive at any time)
        if view_key == "updates":
            return True
        # Refresh stale snapshots that predate the baseline feature
        if isinstance(payload, dict) and "has_baseline" not in payload:
            return True
        return False

    async def _build_cross_version_baseline(
        self, reference_version_id: int,
    ) -> tuple[dict[str, tuple], dict[int, dict]]:
        """Build ms_uid -> (start_dt, finish_dt, duration_d) map from a reference version.

        Args:
            reference_version_id: PK of the reference schedule_versions row.

        Returns:
            Tuple of (baseline lookup, activity_by_id map for the reference version).
        """
        ref_activities = await self.ms_repository.get_activities_by_version(
            version_id=reference_version_id,
            limit=5000,
            include_summary=True,
        )
        ref_activity_by_id: dict[int, dict] = {
            a["id"]: a for a in ref_activities if a.get("id") is not None
        }
        lookup: dict[str, tuple] = {}
        for a in ref_activities:
            ms_uid = a.get("ms_uid")
            if ms_uid is None:
                continue
            key = str(ms_uid)
            start_dt = self._normalize_datetime(a.get("start"))
            finish_dt = self._normalize_datetime(a.get("finish"))
            dur = float(a.get("duration_d") or 0) if a.get("duration_d") is not None else None
            lookup[key] = (start_dt, finish_dt, dur)
        return lookup, ref_activity_by_id

    async def _resolve_baseline_mode_metadata(
        self, project_name: str, current_version_number: int, current_version_id: int,
    ) -> dict:
        """Check which baseline modes are available for a project."""
        prev = await self.ms_repository.get_previous_version(project_name, current_version_number)
        bl = await self.ms_repository.get_baseline_version(project_name)
        return {
            "own": True,
            "previous_version": prev is not None,
            "database_baseline": bl is not None and bl["id"] != current_version_id,
        }

    @staticmethod
    def _build_system_configs(reference_date: date) -> dict[str, dict]:
        return {
            "critical_path": {
                "critical_only": True,
                "date_start": None,
                "date_end": None,
                "overlap_window": False,
            },
            "lookahead_4w": {
                "critical_only": False,
                "date_start": (reference_date - timedelta(days=7)).isoformat(),
                "date_end": (reference_date + timedelta(days=21)).isoformat(),
                "overlap_window": True,
            },
            "full_schedule": {
                "critical_only": False,
                "date_start": None,
                "date_end": None,
                "overlap_window": False,
            },
            "updates": {
                "critical_only": False,
                "date_start": None,
                "date_end": None,
                "overlap_window": False,
                "updates_only": True,
            },
        }

    @logfire.instrument("schedule_view_service.resolve_current_version")
    async def resolve_current_version(self, project_name: str) -> Optional[dict]:
        current = await self.ms_repository.get_current_version(project_name)
        if current:
            return current

        versions = await self.ms_repository.list_versions(project_name, include_temp=True)
        return versions[0] if versions else None

    @logfire.instrument("schedule_view_service.ensure_system_views")
    async def ensure_system_views(
        self,
        *,
        project_id: str,
        schedule_version_id: int,
        reference_date: date,
    ) -> list[dict]:
        configs = self._build_system_configs(reference_date)

        definitions: list[dict] = []
        for view_key in self.VIEW_KEYS:
            view_name = {
                "critical_path": "Critical Path",
                "lookahead_4w": "4-Week",
                "full_schedule": "Full",
                "updates": "Updates",
            }[view_key]
            definition = await self.view_repository.upsert_definition(
                project_id=project_id,
                schedule_version_id=schedule_version_id,
                view_key=view_key,
                view_name=view_name,
                view_type="system",
                is_default=view_key == "critical_path",
                config=configs[view_key],
            )
            definitions.append(definition)

        return definitions

    @logfire.instrument("schedule_view_service.build_payload")
    async def build_view_payload(
        self,
        *,
        schedule_version_id: int,
        view_key: str,
        config: dict,
        baseline_mode: str = "own",
    ) -> dict:
        activities = await self.ms_repository.get_activities_by_version(
            version_id=schedule_version_id,
            limit=5000,
            include_summary=True,
        )
        relationships = await self.ms_repository.get_relationships_by_version(schedule_version_id)

        if not activities:
            return {
                "items": [],
                "relationships": [],
                "project_start": "",
                "project_finish": "",
                "critical_path_length": 0,
                "filter_applied": config,
                "total_activities": 0,
                "filtered_activities": 0,
                "available_activity_codes": {},
                "grouping": None,
                "preserve_order": True,
            }

        activity_by_id = {a["id"]: a for a in activities if a.get("id") is not None}

        parsed = []
        for a in activities:
            start_dt = self._normalize_datetime(a.get("start"))
            finish_dt = self._normalize_datetime(a.get("finish"))
            bl_start_raw = a.get("baseline_start")
            bl_finish_raw = a.get("baseline_finish")
            bl_dur_raw = a.get("baseline_duration_d")
            parsed.append(
                {
                    "raw": a,
                    "id": a.get("id"),
                    "s_item_id": str(a.get("ms_uid") or a.get("id")),
                    "s_item": a.get("name") or "Unnamed activity",
                    "wbs": a.get("wbs") or "",
                    "start_dt": start_dt,
                    "finish_dt": finish_dt,
                    "working_days": float(a.get("duration_d") or 0),
                    "calendar_days": self._duration_days(start_dt, finish_dt),
                    "total_float": float(a.get("total_float_d") or 0),
                    "percent_complete": float(a.get("percent_complete") or 0),
                    "status": self._activity_status(a),
                    "is_summary": bool(a.get("is_summary", False)),
                    "is_critical": self._is_critical(a),
                    "level": self._wbs_level(a.get("wbs")),
                    "baseline_start_dt": self._normalize_datetime(bl_start_raw),
                    "baseline_finish_dt": self._normalize_datetime(bl_finish_raw),
                    "baseline_duration_d": float(bl_dur_raw) if bl_dur_raw is not None else None,
                }
            )

        # --- Cross-version baseline overlay ---
        baseline_label: Optional[str] = None
        _ref_version_id: Optional[int] = None
        _ref_activity_by_id: dict[int, dict] = {}
        if baseline_mode in ("previous_version", "database_baseline"):
            current_version = await self.ms_repository.get_version(schedule_version_id)
            ref_version = None
            if baseline_mode == "previous_version" and current_version:
                ref_version = await self.ms_repository.get_previous_version(
                    current_version["project_name"],
                    current_version["version_number"],
                )
            elif baseline_mode == "database_baseline" and current_version:
                ref_version = await self.ms_repository.get_baseline_version(
                    current_version["project_name"],
                )

            if ref_version:
                cross_baseline, ref_act_map = await self._build_cross_version_baseline(ref_version["id"])
                _ref_version_id = ref_version["id"]
                _ref_activity_by_id = ref_act_map
                baseline_label = ref_version.get("version_name") or str(ref_version.get("version_number", ""))
                for item in parsed:
                    ref = cross_baseline.get(item["s_item_id"])
                    if ref:
                        item["baseline_start_dt"] = ref[0]
                        item["baseline_finish_dt"] = ref[1]
                        item["baseline_duration_d"] = ref[2]
                    else:
                        item["baseline_start_dt"] = None
                        item["baseline_finish_dt"] = None
                        item["baseline_duration_d"] = None
            else:
                # Reference version not found; clear all baseline
                for item in parsed:
                    item["baseline_start_dt"] = None
                    item["baseline_finish_dt"] = None
                    item["baseline_duration_d"] = None

        date_start = config.get("date_start")
        date_end = config.get("date_end")
        overlap_window = bool(config.get("overlap_window"))
        critical_only = bool(config.get("critical_only"))

        start_limit = date.fromisoformat(str(date_start)[:10]) if date_start else None
        end_limit = date.fromisoformat(str(date_end)[:10]) if date_end else None

        filtered_non_summary: list[dict] = []
        for item in parsed:
            if item["is_summary"]:
                continue

            if critical_only and not item["is_critical"]:
                continue

            if start_limit or end_limit:
                start_dt = item["start_dt"]
                finish_dt = item["finish_dt"]

                if not start_dt or not finish_dt:
                    continue

                start_day = start_dt.date()
                finish_day = finish_dt.date()

                if overlap_window:
                    if start_limit and finish_day < start_limit:
                        continue
                    if end_limit and start_day > end_limit:
                        continue
                else:
                    if start_limit and start_day < start_limit:
                        continue
                    if end_limit and finish_day > end_limit:
                        continue

            filtered_non_summary.append(item)

        if critical_only and not filtered_non_summary:
            candidates = [item for item in parsed if not item["is_summary"]]
            if candidates:
                min_float = min(item["total_float"] for item in candidates)
                tolerance = 1e-9
                filtered_non_summary = [
                    item for item in candidates
                    if abs(item["total_float"] - min_float) <= tolerance
                ]

        # Updates-only filter: restrict to activities that have update logs
        updates_only = bool(config.get("updates_only"))
        if updates_only:
            pre_update_logs = await self.ms_repository.get_update_logs_by_version(
                schedule_version_id,
            )
            updated_activity_ids: set[int] = {
                log["activity_id"]
                for log in pre_update_logs
                if log.get("activity_id") is not None
            }

            # When the update is on a summary activity, include its children
            # so the summary itself is pulled in via WBS ancestry.
            updated_summary_wbs_prefixes: list[str] = []
            for item in parsed:
                if item["is_summary"] and item["id"] in updated_activity_ids and item["wbs"]:
                    updated_summary_wbs_prefixes.append(item["wbs"] + ".")

            filtered_non_summary = [
                item for item in filtered_non_summary
                if item["id"] in updated_activity_ids
                or any(
                    item["wbs"].startswith(prefix)
                    for prefix in updated_summary_wbs_prefixes
                )
            ]

        # Include summary ancestors for visible hierarchy
        visible_wbs_prefixes = {item["wbs"] for item in filtered_non_summary if item["wbs"]}
        for item in list(filtered_non_summary):
            wbs = item["wbs"]
            if not wbs:
                continue
            parts = wbs.split(".")
            for idx in range(1, len(parts)):
                visible_wbs_prefixes.add(".".join(parts[:idx]))

        filtered_items = [
            item for item in parsed
            if (not item["is_summary"] and item in filtered_non_summary)
            or (item["is_summary"] and item["wbs"] in visible_wbs_prefixes)
        ]

        # Preserve stable WBS order
        filtered_items.sort(key=lambda item: item["wbs"])

        filtered_id_set = {item["id"] for item in filtered_items if item["id"] is not None}

        # Parent linkage for summary and detail rows
        summary_by_wbs = {item["wbs"]: item for item in filtered_items if item["is_summary"] and item["wbs"]}

        def parent_id_for(item: dict) -> Optional[str]:
            wbs = item["wbs"]
            if not wbs:
                return None
            parts = wbs.split(".")
            for idx in range(len(parts) - 1, 0, -1):
                prefix = ".".join(parts[:idx])
                parent = summary_by_wbs.get(prefix)
                if parent:
                    return parent["s_item_id"]
            return None

        summary_children_count: dict[str, int] = {}
        for summary in summary_by_wbs.values():
            prefix = summary["wbs"] + "."
            count = sum(
                1
                for item in filtered_items
                if not item["is_summary"] and item["wbs"].startswith(prefix)
            )
            summary_children_count[summary["s_item_id"]] = count

        items_payload = []
        for item in filtered_items:
            bl_start_dt = item.get("baseline_start_dt")
            bl_finish_dt = item.get("baseline_finish_dt")
            item_payload = build_schedule_item_payload(
                item_id=int(item["id"]),
                s_item_id=item["s_item_id"],
                s_item=item["s_item"],
                working_days=float(item["working_days"]),
                calendar_days=int(item["calendar_days"]),
                total_float=float(item["total_float"]),
                start=item["start_dt"],
                finish=item["finish_dt"],
                is_critical=bool(item["is_critical"]),
                wbs_path=item["wbs"],
                status=item["status"],
                percent_complete=item.get("percent_complete"),
                level=int(item["level"]),
                is_summary=bool(item["is_summary"]),
                parent_id=parent_id_for(item),
                children_count=summary_children_count.get(item["s_item_id"], 0),
                group_name=None,
                baseline_start=bl_start_dt,
                baseline_finish=bl_finish_dt,
                baseline_duration_d=item.get("baseline_duration_d"),
            )
            items_payload.append(item_payload)

        all_id_to_sitem = {
            item["id"]: item["s_item_id"]
            for item in parsed
            if item.get("id") is not None
        }
        raw_relationships = [
            {
                "pred_id": rel.get("pred_id"),
                "succ_id": rel.get("succ_id"),
                "rel_type": rel.get("rel_type") or "FS",
                "lag_days": float(rel.get("lag_d") or 0),
            }
            for rel in relationships
        ]

        relationships_payload, envelope_relationships, visible_relationship_ids = build_relationship_projections(
            raw_relationships=raw_relationships,
            id_to_code_all={int(k): str(v) for k, v in all_id_to_sitem.items()},
            visible_id_set={int(task_id) for task_id in filtered_id_set},
            is_critical_edge=lambda pred_id, succ_id: (
                self._is_critical(activity_by_id.get(pred_id) or {})
                and self._is_critical(activity_by_id.get(succ_id) or {})
            ),
        )

        all_dates = [item["start_dt"] for item in filtered_items if item["start_dt"]] + [
            item["finish_dt"] for item in filtered_items if item["finish_dt"]
        ]

        if all_dates:
            project_start = min(all_dates).date().isoformat()
            project_finish = max(all_dates).date().isoformat()
        else:
            project_start = ""
            project_finish = ""

        critical_dates = [
            item["start_dt"]
            for item in filtered_items
            if item["is_critical"] and item["start_dt"]
        ] + [
            item["finish_dt"]
            for item in filtered_items
            if item["is_critical"] and item["finish_dt"]
        ]
        if critical_dates:
            critical_span = (max(critical_dates).date() - min(critical_dates).date()).days + 1
        else:
            critical_span = 0

        has_baseline = any(
            item.get("baseline_start_dt") is not None
            for item in filtered_items
            if not item["is_summary"]
        )

        # Fetch update logs for this version and map to s_item_id
        update_logs = await self.ms_repository.get_update_logs_by_version(
            schedule_version_id,
        )
        activity_updates_payload = self._map_update_logs(
            update_logs,
            activity_by_id=activity_by_id,
            filtered_id_set=filtered_id_set,
        )

        # Fetch update logs for the reference version (cross-version mode only)
        baseline_activity_updates: list[dict] = []
        if _ref_version_id is not None:
            ref_update_logs = await self.ms_repository.get_update_logs_by_version(
                _ref_version_id,
            )
            visible_sitem_ids = {item["s_item_id"] for item in filtered_items}
            baseline_activity_updates = self._map_baseline_update_logs(
                ref_update_logs,
                ref_activity_by_id=_ref_activity_by_id,
                visible_sitem_ids=visible_sitem_ids,
            )

        legacy_payload = {
            "items": items_payload,
            "relationships": relationships_payload,
            "project_start": project_start,
            "project_finish": project_finish,
            "critical_path_length": float(critical_span),
            "filter_applied": {
                "critical_only": critical_only,
                "date_start": date_start,
                "date_end": date_end,
                "wbs_path": None,
                "activity_codes": None,
                "status": None,
                "search_term": None,
            },
            "total_activities": len(parsed),
            "filtered_activities": len(filtered_items),
            "available_activity_codes": {},
            "grouping": None,
            "preserve_order": True,
            "has_baseline": has_baseline,
            "baseline_mode": baseline_mode,
            "baseline_label": baseline_label,
            "activity_updates": activity_updates_payload,
            "baseline_activity_updates": baseline_activity_updates,
        }

        current_version = await self.ms_repository.get_version(schedule_version_id)
        available_baseline_modes = {
            "own": has_baseline,
            "previous_version": False,
            "database_baseline": False,
        }
        if current_version:
            available_baseline_modes = await self._resolve_baseline_mode_metadata(
                current_version["project_name"],
                current_version["version_number"],
                schedule_version_id,
            )
            available_baseline_modes["own"] = has_baseline

        return build_v2_gantt_payload(
            legacy_payload=legacy_payload,
            view_id=str(view_key),
            view_title=str(view_key).replace("_", " ").title(),
            project_id=current_version.get("project_name") if current_version else None,
            schedule_version_id=schedule_version_id,
            available_baseline_modes=available_baseline_modes,
            selected_baseline_mode=baseline_mode,
            envelope_activities=items_payload,
            envelope_relationships=envelope_relationships,
            envelope_updates=activity_updates_payload,
            visible_activity_ids=[int(item["id"]) for item in items_payload],
            visible_relationship_ids=visible_relationship_ids,
        )

    @staticmethod
    def _map_update_logs(
        update_logs: list[dict],
        *,
        activity_by_id: dict[int, dict],
        filtered_id_set: set[int],
    ) -> list[dict]:
        """Map raw update-log rows to Gantt payload format.

        Uses *activity_by_id* to resolve the database PK to ``ms_uid``
        (which becomes ``s_item_id`` on the frontend) and filters by
        *filtered_id_set*.
        """
        result: list[dict] = []
        for log in update_logs:
            activity_id = log.get("activity_id")
            if activity_id is None:
                continue
            activity = activity_by_id.get(activity_id)
            if activity is None:
                continue
            if int(activity_id) not in filtered_id_set:
                continue
            s_item_id = str(activity.get("ms_uid") or activity_id)
            result.append(
                {
                    "log_id": log["log_id"],
                    "s_item_id": s_item_id,
                    "update_type": log["update_type"],
                    "details": log["details"],
                    "reported_value": log.get("reported_value"),
                    "reported_by": log["reported_by"],
                    "reported_at": log["reported_at"],
                    "processed": log["processed"],
                }
            )
        return result

    @staticmethod
    def _map_baseline_update_logs(
        update_logs: list[dict],
        *,
        ref_activity_by_id: dict[int, dict],
        visible_sitem_ids: set[str],
    ) -> list[dict]:
        """Map update logs from a reference version to ``s_item_id`` format.

        Filters to only include activities visible in the current view.
        """
        result: list[dict] = []
        for log in update_logs:
            activity_id = log.get("activity_id")
            if activity_id is None:
                continue
            activity = ref_activity_by_id.get(activity_id)
            if activity is None:
                continue
            s_item_id = str(activity.get("ms_uid") or activity_id)
            if s_item_id not in visible_sitem_ids:
                continue
            result.append(
                {
                    "log_id": log["log_id"],
                    "s_item_id": s_item_id,
                    "update_type": log["update_type"],
                    "details": log["details"],
                    "reported_value": log.get("reported_value"),
                    "reported_by": log["reported_by"],
                    "reported_at": log["reported_at"],
                    "processed": log["processed"],
                }
            )
        return result

    @staticmethod
    def _inject_fresh_updates(
        payload: dict,
        update_logs: list[dict],
    ) -> dict:
        """Overlay fresh update logs onto a (possibly cached) payload.

        Builds the ``activity_id → s_item_id`` mapping directly from the
        payload ``items`` list so this can run outside ``build_view_payload``.
        """
        items = payload.get("items") or []
        id_to_sitem: dict[int, str] = {}
        sitem_set: set[str] = set()
        for item in items:
            item_id = item.get("id")
            s_id = item.get("s_item_id")
            if item_id is not None and s_id is not None:
                id_to_sitem[int(item_id)] = str(s_id)
                sitem_set.add(str(s_id))

        updates: list[dict] = []
        for log in update_logs:
            s_item_id = id_to_sitem.get(log.get("activity_id"))  # type: ignore[arg-type]
            if s_item_id is None:
                continue
            updates.append(
                {
                    "log_id": log["log_id"],
                    "s_item_id": s_item_id,
                    "update_type": log["update_type"],
                    "details": log["details"],
                    "reported_value": log.get("reported_value"),
                    "reported_by": log["reported_by"],
                    "reported_at": log["reported_at"],
                    "processed": log["processed"],
                }
            )

        payload = dict(payload)
        payload["activity_updates"] = updates
        if isinstance(payload.get("data_envelope"), dict):
            envelope = dict(payload["data_envelope"])
            envelope["updates"] = updates
            payload["data_envelope"] = envelope
        if isinstance(payload.get("capabilities"), dict):
            capabilities = dict(payload["capabilities"])
            updates_cap = dict(capabilities.get("updates") or {})
            updates_cap["available"] = bool(updates)
            updates_cap.setdefault("render_enabled", True)
            capabilities["updates"] = updates_cap
            payload["capabilities"] = capabilities
        return payload

    @staticmethod
    def _inject_baseline_mode_metadata(payload: dict, available_baseline_modes: dict) -> dict:
        patched = dict(payload)
        patched["available_baseline_modes"] = available_baseline_modes
        if isinstance(patched.get("capabilities"), dict):
            capabilities = dict(patched["capabilities"])
            baseline_modes = dict(capabilities.get("baseline_modes") or {})
            baseline_modes["available"] = [
                mode for mode, enabled in available_baseline_modes.items() if enabled
            ]
            selected = str(baseline_modes.get("selected") or patched.get("baseline_mode") or "own")
            if not available_baseline_modes.get(selected, False) and available_baseline_modes.get("own", False):
                selected = "own"
            baseline_modes["selected"] = selected
            capabilities["baseline_modes"] = baseline_modes
            patched["capabilities"] = capabilities
            patched["baseline_mode"] = selected
        return patched

    @staticmethod
    def _normalize_available_baseline_modes(payload: dict, available_baseline_modes: dict) -> dict:
        normalized = dict(available_baseline_modes)
        normalized["own"] = bool(payload.get("has_baseline", normalized.get("own", False)))
        return normalized

    @logfire.instrument("schedule_view_service.preload")
    async def preload(self, *, project_id: str, baseline_mode: str = "own") -> dict:
        version = await self.resolve_current_version(project_id)
        if not version:
            raise ValueError(f"No schedule versions found for project '{project_id}'")

        schedule_version_id = int(version["id"])
        definitions = await self.ensure_system_views(
            project_id=project_id,
            schedule_version_id=schedule_version_id,
            reference_date=date.today(),
        )

        # Resolve available baseline modes for this project
        available_baseline_modes = await self._resolve_baseline_mode_metadata(
            version["project_name"],
            version["version_number"],
            schedule_version_id,
        )

        use_cross_baseline = baseline_mode != "own" and available_baseline_modes.get(baseline_mode, False)

        views = []
        default_payload = None
        for definition in definitions:
            config = definition.get("config") or {}
            snapshot = await self.view_repository.get_snapshot(
                view_definition_id=definition["id"],
                schedule_version_id=schedule_version_id,
            )
            if use_cross_baseline or self._should_refresh_snapshot(view_key=definition["view_key"], snapshot=snapshot):
                payload = await self.build_view_payload(
                    schedule_version_id=schedule_version_id,
                    view_key=definition["view_key"],
                    config=config,
                    baseline_mode=baseline_mode if use_cross_baseline else "own",
                )
                if not use_cross_baseline:
                    checksum = sha1(str(payload).encode("utf-8")).hexdigest()
                    snapshot = await self.view_repository.upsert_snapshot(
                        view_definition_id=definition["id"],
                        schedule_version_id=schedule_version_id,
                        payload=payload,
                        checksum=checksum,
                    )
                else:
                    # For cross-baseline: use the computed payload directly, don't save to snapshot
                    snapshot = {"payload": payload, "computed_at": datetime.utcnow().isoformat()}

            views.append(
                {
                    "view_key": definition["view_key"],
                    "view_name": definition["view_name"],
                    "view_type": definition["view_type"],
                    "is_default": bool(definition.get("is_default", False)),
                    "computed_at": snapshot.get("computed_at"),
                }
            )

            if definition.get("is_default"):
                default_payload = snapshot.get("payload")

        if default_payload is None and definitions:
            fallback_def = definitions[0]
            fallback_snapshot = await self.view_repository.get_snapshot(
                view_definition_id=fallback_def["id"],
                schedule_version_id=schedule_version_id,
            )
            default_payload = fallback_snapshot.get("payload") if fallback_snapshot else None

        # Always fresh-fetch update logs (they can arrive outside imports)
        if default_payload and isinstance(default_payload, dict):
            fresh_logs = await self.ms_repository.get_update_logs_by_version(
                schedule_version_id,
            )
            default_payload = self._inject_fresh_updates(default_payload, fresh_logs)

        # Inject baseline availability metadata into default payload
        if default_payload and isinstance(default_payload, dict):
            effective_baseline_modes = self._normalize_available_baseline_modes(
                default_payload,
                available_baseline_modes,
            )
            default_payload = self._inject_baseline_mode_metadata(
                default_payload,
                effective_baseline_modes,
            )

        return {
            "project_id": project_id,
            "schedule_version_id": schedule_version_id,
            "default_view_key": "critical_path",
            "views": views,
            "payload": default_payload,
        }

    @logfire.instrument("schedule_view_service.get_view")
    async def get_view(self, *, project_id: str, view_key: str, baseline_mode: str = "own") -> dict:
        if view_key not in self.VIEW_KEYS:
            raise ValueError(f"Unsupported view_key '{view_key}'")

        version = await self.resolve_current_version(project_id)
        if not version:
            raise ValueError(f"No schedule versions found for project '{project_id}'")

        schedule_version_id = int(version["id"])

        # Resolve available baseline modes
        available_baseline_modes = await self._resolve_baseline_mode_metadata(
            version["project_name"],
            version["version_number"],
            schedule_version_id,
        )
        use_cross_baseline = baseline_mode != "own" and available_baseline_modes.get(baseline_mode, False)

        schedule_version_id = int(version["id"])
        definition = await self.view_repository.get_definition(
            project_id=project_id,
            schedule_version_id=schedule_version_id,
            view_key=view_key,
        )
        if definition is None:
            definitions = await self.ensure_system_views(
                project_id=project_id,
                schedule_version_id=schedule_version_id,
                reference_date=date.today(),
            )
            definition = next((d for d in definitions if d["view_key"] == view_key), None)

        if definition is None:
            raise ValueError(f"Could not resolve view definition for '{view_key}'")

        snapshot = await self.view_repository.get_snapshot(
            view_definition_id=definition["id"],
            schedule_version_id=schedule_version_id,
        )

        if use_cross_baseline or self._should_refresh_snapshot(view_key=view_key, snapshot=snapshot):
            payload = await self.build_view_payload(
                schedule_version_id=schedule_version_id,
                view_key=view_key,
                config=definition.get("config") or {},
                baseline_mode=baseline_mode if use_cross_baseline else "own",
            )
            if not use_cross_baseline:
                checksum = sha1(str(payload).encode("utf-8")).hexdigest()
                snapshot = await self.view_repository.upsert_snapshot(
                    view_definition_id=definition["id"],
                    schedule_version_id=schedule_version_id,
                    payload=payload,
                    checksum=checksum,
                )
            else:
                snapshot = {"payload": payload, "computed_at": datetime.utcnow().isoformat()}

        view_payload = snapshot.get("payload")

        # Always fresh-fetch update logs (they can arrive outside imports)
        if view_payload and isinstance(view_payload, dict):
            fresh_logs = await self.ms_repository.get_update_logs_by_version(
                schedule_version_id,
            )
            view_payload = self._inject_fresh_updates(view_payload, fresh_logs)

        # Inject baseline availability metadata
        if view_payload and isinstance(view_payload, dict):
            effective_baseline_modes = self._normalize_available_baseline_modes(
                view_payload,
                available_baseline_modes,
            )
            view_payload = self._inject_baseline_mode_metadata(
                view_payload,
                effective_baseline_modes,
            )

        return {
            "project_id": project_id,
            "schedule_version_id": schedule_version_id,
            "view_key": definition["view_key"],
            "view_name": definition["view_name"],
            "computed_at": snapshot.get("computed_at"),
            "payload": view_payload,
        }
