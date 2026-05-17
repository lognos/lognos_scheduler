"""Repository for persisted schedule view definitions and snapshots."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import logfire
from supabase import Client


@dataclass
class ScheduleViewRepository:
    """Repository for lognos_schedule view metadata and cached payload snapshots."""

    supabase: Client
    SCHEMA: str = "lognos_schedule"

    def _table(self, name: str):
        return self.supabase.schema(self.SCHEMA).table(name)

    @logfire.instrument("schedule_view_repo.upsert_definition")
    async def upsert_definition(
        self,
        *,
        project_id: str,
        schedule_version_id: int,
        view_key: str,
        view_name: str,
        view_type: str,
        is_default: bool,
        config: dict,
        created_by: Optional[str] = None,
    ) -> dict:
        payload = {
            "project_id": project_id,
            "schedule_version_id": schedule_version_id,
            "view_key": view_key,
            "view_name": view_name,
            "view_type": view_type,
            "is_default": is_default,
            "config": config,
            "created_by": created_by,
        }

        self._table("schedule_view_definitions").upsert(
            payload,
            on_conflict="project_id,schedule_version_id,view_key",
        ).execute()

        return self._table("schedule_view_definitions") \
            .select("*") \
            .eq("project_id", project_id) \
            .eq("schedule_version_id", schedule_version_id) \
            .eq("view_key", view_key) \
            .single() \
            .execute().data

    @logfire.instrument("schedule_view_repo.list_definitions")
    async def list_definitions(self, *, project_id: str, schedule_version_id: int) -> list[dict]:
        return self._table("schedule_view_definitions") \
            .select("*") \
            .eq("project_id", project_id) \
            .eq("schedule_version_id", schedule_version_id) \
            .order("view_key") \
            .execute().data or []

    @logfire.instrument("schedule_view_repo.get_definition")
    async def get_definition(
        self,
        *,
        project_id: str,
        schedule_version_id: int,
        view_key: str,
    ) -> Optional[dict]:
        try:
            return self._table("schedule_view_definitions") \
                .select("*") \
                .eq("project_id", project_id) \
                .eq("schedule_version_id", schedule_version_id) \
                .eq("view_key", view_key) \
                .single() \
                .execute().data
        except Exception:
            return None

    @logfire.instrument("schedule_view_repo.get_snapshot")
    async def get_snapshot(self, *, view_definition_id: str, schedule_version_id: int) -> Optional[dict]:
        rows = self._table("schedule_view_snapshots") \
            .select("*") \
            .eq("view_definition_id", view_definition_id) \
            .eq("schedule_version_id", schedule_version_id) \
            .order("computed_at", desc=True) \
            .limit(1) \
            .execute().data or []
        return rows[0] if rows else None

    @logfire.instrument("schedule_view_repo.upsert_snapshot")
    async def upsert_snapshot(
        self,
        *,
        view_definition_id: str,
        schedule_version_id: int,
        payload: dict,
        checksum: Optional[str] = None,
    ) -> dict:
        body = {
            "view_definition_id": view_definition_id,
            "schedule_version_id": schedule_version_id,
            "payload": payload,
            "checksum": checksum,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        self._table("schedule_view_snapshots").upsert(
            body,
            on_conflict="view_definition_id,schedule_version_id",
        ).execute()

        return self._table("schedule_view_snapshots") \
            .select("*") \
            .eq("view_definition_id", view_definition_id) \
            .eq("schedule_version_id", schedule_version_id) \
            .single() \
            .execute().data
