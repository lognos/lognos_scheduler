"""Service for schedule preloading and persisted view payload generation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha1
from typing import Optional

import logfire

from backend.repositories.ms_schedule_repository import MSScheduleRepository
from backend.repositories.schedule_view_repository import ScheduleViewRepository


class ScheduleViewService:
    """Build and cache schedule views for instant UI switching."""

    VIEW_KEYS = ("critical_path", "lookahead_4w", "full_schedule")

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
        # Refresh stale snapshots that predate the baseline feature
        if isinstance(payload, dict) and "has_baseline" not in payload:
            return True
        return False

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
                    "status": self._activity_status(a),
                    "is_summary": bool(a.get("is_summary", False)),
                    "is_critical": self._is_critical(a),
                    "level": self._wbs_level(a.get("wbs")),
                    "baseline_start_dt": self._normalize_datetime(bl_start_raw),
                    "baseline_finish_dt": self._normalize_datetime(bl_finish_raw),
                    "baseline_duration_d": float(bl_dur_raw) if bl_dur_raw is not None else None,
                }
            )

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

        id_to_sitem = {item["id"]: item["s_item_id"] for item in filtered_items if item["id"] is not None}
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
            start_text = item["start_dt"].date().isoformat() if item["start_dt"] else ""
            finish_text = item["finish_dt"].date().isoformat() if item["finish_dt"] else ""
            bl_start_dt = item.get("baseline_start_dt")
            bl_finish_dt = item.get("baseline_finish_dt")
            item_payload = {
                "id": int(item["id"]),
                "s_item_id": item["s_item_id"],
                "s_item": item["s_item"],
                "working_days": item["working_days"],
                "calendar_days": item["calendar_days"],
                "total_float": item["total_float"],
                "start": start_text,
                "finish": finish_text,
                "is_critical": item["is_critical"],
                "wbs_path": item["wbs"],
                "status": item["status"],
                "level": item["level"],
                "is_summary": item["is_summary"],
                "parent_id": parent_id_for(item),
                "children_count": summary_children_count.get(item["s_item_id"], 0),
                "group_name": None,
                "baseline_start": bl_start_dt.date().isoformat() if bl_start_dt else None,
                "baseline_finish": bl_finish_dt.date().isoformat() if bl_finish_dt else None,
                "baseline_duration_d": item.get("baseline_duration_d"),
            }
            items_payload.append(item_payload)

        relationships_payload = []
        for rel in relationships:
            pred_id = rel.get("pred_id")
            succ_id = rel.get("succ_id")
            if pred_id not in filtered_id_set or succ_id not in filtered_id_set:
                continue

            pred = activity_by_id.get(pred_id) or {}
            succ = activity_by_id.get(succ_id) or {}
            relationships_payload.append(
                {
                    "pred_id": id_to_sitem.get(pred_id, str(pred_id)),
                    "succ_id": id_to_sitem.get(succ_id, str(succ_id)),
                    "rel_type": rel.get("rel_type") or "FS",
                    "lag_days": float(rel.get("lag_d") or 0),
                    "is_critical": self._is_critical(pred) and self._is_critical(succ),
                }
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

        return {
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
        }

    @logfire.instrument("schedule_view_service.preload")
    async def preload(self, *, project_id: str) -> dict:
        version = await self.resolve_current_version(project_id)
        if not version:
            raise ValueError(f"No schedule versions found for project '{project_id}'")

        schedule_version_id = int(version["id"])
        definitions = await self.ensure_system_views(
            project_id=project_id,
            schedule_version_id=schedule_version_id,
            reference_date=date.today(),
        )

        views = []
        default_payload = None
        for definition in definitions:
            config = definition.get("config") or {}
            snapshot = await self.view_repository.get_snapshot(
                view_definition_id=definition["id"],
                schedule_version_id=schedule_version_id,
            )
            if self._should_refresh_snapshot(view_key=definition["view_key"], snapshot=snapshot):
                payload = await self.build_view_payload(
                    schedule_version_id=schedule_version_id,
                    view_key=definition["view_key"],
                    config=config,
                )
                checksum = sha1(str(payload).encode("utf-8")).hexdigest()
                snapshot = await self.view_repository.upsert_snapshot(
                    view_definition_id=definition["id"],
                    schedule_version_id=schedule_version_id,
                    payload=payload,
                    checksum=checksum,
                )

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

        return {
            "project_id": project_id,
            "schedule_version_id": schedule_version_id,
            "default_view_key": "critical_path",
            "views": views,
            "payload": default_payload,
        }

    @logfire.instrument("schedule_view_service.get_view")
    async def get_view(self, *, project_id: str, view_key: str) -> dict:
        if view_key not in self.VIEW_KEYS:
            raise ValueError(f"Unsupported view_key '{view_key}'")

        version = await self.resolve_current_version(project_id)
        if not version:
            raise ValueError(f"No schedule versions found for project '{project_id}'")

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

        if self._should_refresh_snapshot(view_key=view_key, snapshot=snapshot):
            payload = await self.build_view_payload(
                schedule_version_id=schedule_version_id,
                view_key=view_key,
                config=definition.get("config") or {},
            )
            checksum = sha1(str(payload).encode("utf-8")).hexdigest()
            snapshot = await self.view_repository.upsert_snapshot(
                view_definition_id=definition["id"],
                schedule_version_id=schedule_version_id,
                payload=payload,
                checksum=checksum,
            )

        return {
            "project_id": project_id,
            "schedule_version_id": schedule_version_id,
            "view_key": definition["view_key"],
            "view_name": definition["view_name"],
            "computed_at": snapshot.get("computed_at"),
            "payload": snapshot.get("payload"),
        }
