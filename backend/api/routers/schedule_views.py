"""Schedule view preload and retrieval endpoints."""

from typing import Optional

import logfire
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.repositories.ms_schedule_repository import MSScheduleRepository
from backend.repositories.schedule_view_repository import ScheduleViewRepository
from backend.services.schedule_view_service import ScheduleViewService
from backend.utils.supabase_client import get_supabase

router = APIRouter()


class ScheduleViewMetaResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    view_key: str
    view_name: str
    view_type: str
    is_default: bool
    computed_at: Optional[str] = None


class ScheduleViewsPreloadResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    project_id: str
    schedule_version_id: int
    default_view_key: str
    views: list[ScheduleViewMetaResponse]
    payload: dict


class ScheduleViewResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    project_id: str
    schedule_version_id: int
    view_key: str
    view_name: str
    computed_at: Optional[str] = None
    payload: dict


@router.get("/preload", response_model=ScheduleViewsPreloadResponse)
async def preload_schedule_views(
    lognos_project_id: str = Header(..., alias="Lognos-ProjectID"),
):
    """Preload default schedule view + metadata for fast first render."""
    supabase = get_supabase()
    service = ScheduleViewService(
        ms_repository=MSScheduleRepository(supabase),
        view_repository=ScheduleViewRepository(supabase),
    )

    try:
        result = await service.preload(project_id=lognos_project_id)
        return ScheduleViewsPreloadResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logfire.error("Failed to preload schedule views", error=str(exc), project_id=lognos_project_id)
        raise HTTPException(status_code=500, detail="Failed to preload schedule views") from exc


@router.get("/{view_key}", response_model=ScheduleViewResponse)
async def get_schedule_view(
    view_key: str,
    lognos_project_id: str = Header(..., alias="Lognos-ProjectID"),
):
    """Return a single persisted schedule view payload."""
    supabase = get_supabase()
    service = ScheduleViewService(
        ms_repository=MSScheduleRepository(supabase),
        view_repository=ScheduleViewRepository(supabase),
    )

    try:
        result = await service.get_view(project_id=lognos_project_id, view_key=view_key)
        return ScheduleViewResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logfire.error(
            "Failed to load schedule view",
            error=str(exc),
            project_id=lognos_project_id,
            view_key=view_key,
        )
        raise HTTPException(status_code=500, detail="Failed to load schedule view") from exc
