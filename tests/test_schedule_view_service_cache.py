import asyncio
import os
from copy import deepcopy

os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")

from sch_backend.services.schedule_view_service import ScheduleViewService


CURRENT_SIGNATURE = {
    "relationship_count": 488,
    "max_relationship_id": 17745,
    "relationship_checksum": "current",
}
STALE_SIGNATURE = {
    "relationship_count": 429,
    "max_relationship_id": 17686,
    "relationship_checksum": "stale",
}
TARGET_RELATIONSHIP = {
    "pred_id": "27",
    "succ_id": "5",
    "rel_type": "FS",
    "lag_days": 0,
    "is_critical": False,
}
LONGEST_PATH_CONFIG = {
    "critical_only": True,
    "critical_definition": "longest_path",
}


class FakeMSScheduleRepository:
    async def get_current_version(self, project_name: str) -> dict:
        return {
            "id": 28,
            "project_name": project_name,
            "version_number": 1,
        }

    async def get_previous_version(self, project_name: str, current_version_number: int) -> None:
        return None

    async def get_baseline_version(self, project_name: str) -> dict:
        return {
            "id": 28,
            "project_name": project_name,
            "version_number": 1,
        }

    async def get_relationship_cache_signature(self, version_id: int) -> dict:
        return CURRENT_SIGNATURE

    async def get_update_logs_by_version(self, version_id: int) -> list[dict]:
        return []


class FakeScheduleViewRepository:
    def __init__(self) -> None:
        self.saved_payload: dict | None = None

    async def get_definition(self, *, project_id: str, schedule_version_id: int, view_key: str) -> dict:
        return {
            "id": "view-definition-id",
            "view_key": view_key,
            "view_name": "Full",
            "config": {},
        }

    async def get_snapshot(self, *, view_definition_id: str, schedule_version_id: int) -> dict:
        payload = ScheduleViewService._inject_cache_metadata(
            {
                "items": [],
                "relationships": [],
                "has_baseline": False,
                "capabilities": {
                    "updates": {"available": False, "render_enabled": True},
                    "baseline_modes": {"available": [], "selected": "own"},
                },
                "baseline_mode": "own",
            },
            relationship_signature=STALE_SIGNATURE,
            config_signature=ScheduleViewService._view_config_signature({}),
        )
        return {"payload": payload, "computed_at": "old"}

    async def upsert_snapshot(
        self,
        *,
        view_definition_id: str,
        schedule_version_id: int,
        payload: dict,
        checksum: str | None = None,
    ) -> dict:
        self.saved_payload = deepcopy(payload)
        return {"payload": payload, "computed_at": "new"}


class CacheAwareScheduleViewService(ScheduleViewService):
    async def build_view_payload(
        self,
        *,
        schedule_version_id: int,
        view_key: str,
        config: dict,
        baseline_mode: str = "own",
    ) -> dict:
        return {
            "items": [{"id": 16747, "s_item_id": "27"}],
            "relationships": [TARGET_RELATIONSHIP],
            "has_baseline": False,
            "capabilities": {
                "updates": {"available": False, "render_enabled": True},
                "baseline_modes": {"available": [], "selected": "own"},
            },
            "baseline_mode": baseline_mode,
        }


def test_get_view_rebuilds_snapshot_when_relationship_signature_changes() -> None:
    view_repository = FakeScheduleViewRepository()
    service = CacheAwareScheduleViewService(
        ms_repository=FakeMSScheduleRepository(),
        view_repository=view_repository,
    )

    result = asyncio.run(
        service.get_view(
            project_id="BIO4-25204",
            view_key="full_schedule",
        )
    )

    assert view_repository.saved_payload is not None
    assert TARGET_RELATIONSHIP in result["payload"]["relationships"]
    assert (
        result["payload"]["cache_metadata"]["relationship_signature"]
        == CURRENT_SIGNATURE
    )


def _parsed_item(
    item_id: int,
    start: str,
    finish: str,
    total_float: float,
    duration: float,
) -> dict:
    return {
        "id": item_id,
        "is_summary": False,
        "start_dt": ScheduleViewService._normalize_datetime(start),
        "finish_dt": ScheduleViewService._normalize_datetime(finish),
        "total_float": total_float,
        "working_days": duration,
    }


def test_longest_path_extends_through_positive_float_successors() -> None:
    parsed = [
        _parsed_item(1, "2026-05-01", "2026-05-05", 0, 5),
        _parsed_item(2, "2026-05-06", "2026-05-10", 45, 5),
        _parsed_item(3, "2026-05-11", "2026-05-12", 45, 0),
    ]
    relationships = [
        {"pred_id": 1, "succ_id": 2, "rel_type": "FS", "lag_d": 0},
        {"pred_id": 2, "succ_id": 3, "rel_type": "FS", "lag_d": 0},
    ]

    assert ScheduleViewService._critical_activity_ids_for_config(
        parsed,
        relationships,
        LONGEST_PATH_CONFIG,
    ) == {1, 2, 3}


def test_total_float_critical_keeps_zero_float_semantics() -> None:
    parsed = [
        _parsed_item(1, "2026-05-01", "2026-05-05", 0, 5),
        _parsed_item(2, "2026-05-06", "2026-05-10", 45, 5),
        _parsed_item(3, "2026-05-11", "2026-05-12", 45, 0),
    ]

    assert ScheduleViewService._critical_activity_ids_for_config(
        parsed,
        [],
        {"critical_definition": "total_float", "float_threshold_d": 0},
    ) == {1}
