"""
P6 Schedules router for managing schedule mappings.
Provides endpoints for listing and managing P6 schedule associations.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
import logfire

from backend.utils.supabase_client import get_supabase
from backend.repositories.p6_schedule_repository import P6ScheduleRepository
from backend.models.domain import P6ScheduleCreate

router = APIRouter()


# ============================================================
# Response Models
# ============================================================

class P6ScheduleResponse(BaseModel):
    """Response model for P6 schedule."""
    id: str
    project_id: str
    p6_proj_id: int
    p6_proj_short_name: Optional[str] = None
    schedule_name: str
    schedule_type: str
    is_active: bool
    created_at: str


class P6ScheduleListResponse(BaseModel):
    """Response model for P6 schedule list."""
    schedules: list[P6ScheduleResponse]


class P6ScheduleCreateRequest(BaseModel):
    """Request model for creating a P6 schedule mapping."""
    model_config = ConfigDict(strict=True)
    
    p6_proj_id: int = Field(..., description="P6 project ID (integer)")
    p6_proj_short_name: Optional[str] = Field(None, description="P6 project short name")
    schedule_name: str = Field(..., description="User-friendly schedule name")
    schedule_type: str = Field(default="current", description="Schedule type (baseline, current, what-if)")


# ============================================================
# Endpoints
# ============================================================

@router.get("", response_model=P6ScheduleListResponse)
async def list_p6_schedules(
    lognos_project_id: str = Header(..., alias="Lognos-ProjectID"),
    active_only: bool = Query(True, description="Only return active schedules"),
):
    """
    List all P6 schedules for a Lognos project.
    """
    supabase = get_supabase()
    repo = P6ScheduleRepository(supabase)
    
    try:
        schedules = await repo.list_by_project(
            project_id=lognos_project_id,
            active_only=active_only,
        )
        
        return P6ScheduleListResponse(
            schedules=[
                P6ScheduleResponse(
                    id=s.id,
                    project_id=s.project_id,
                    p6_proj_id=s.p6_proj_id,
                    p6_proj_short_name=s.p6_proj_short_name,
                    schedule_name=s.schedule_name,
                    schedule_type=s.schedule_type,
                    is_active=s.is_active,
                    created_at=s.created_at,
                )
                for s in schedules
            ]
        )
    except Exception as e:
        logfire.error("Error listing P6 schedules", error=str(e), project_id=lognos_project_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=P6ScheduleResponse)
async def create_p6_schedule(
    request: P6ScheduleCreateRequest,
    lognos_project_id: str = Header(..., alias="Lognos-ProjectID"),
):
    """
    Create a new P6 schedule mapping for a Lognos project.
    """
    supabase = get_supabase()
    repo = P6ScheduleRepository(supabase)
    
    try:
        schedule_create = P6ScheduleCreate(
            project_id=lognos_project_id,
            p6_proj_id=request.p6_proj_id,
            p6_proj_short_name=request.p6_proj_short_name,
            schedule_name=request.schedule_name,
            schedule_type=request.schedule_type,
        )
        
        schedule = await repo.create(schedule_create)
        
        return P6ScheduleResponse(
            id=schedule.id,
            project_id=schedule.project_id,
            p6_proj_id=schedule.p6_proj_id,
            p6_proj_short_name=schedule.p6_proj_short_name,
            schedule_name=schedule.schedule_name,
            schedule_type=schedule.schedule_type,
            is_active=schedule.is_active,
            created_at=schedule.created_at,
        )
    except Exception as e:
        logfire.error("Error creating P6 schedule", error=str(e), project_id=lognos_project_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{schedule_id}", response_model=P6ScheduleResponse)
async def get_p6_schedule(schedule_id: str):
    """
    Get a specific P6 schedule by ID.
    """
    supabase = get_supabase()
    repo = P6ScheduleRepository(supabase)
    
    try:
        schedule = await repo.get_by_id(schedule_id)
        
        if not schedule:
            raise HTTPException(status_code=404, detail="P6 schedule not found")
        
        return P6ScheduleResponse(
            id=schedule.id,
            project_id=schedule.project_id,
            p6_proj_id=schedule.p6_proj_id,
            p6_proj_short_name=schedule.p6_proj_short_name,
            schedule_name=schedule.schedule_name,
            schedule_type=schedule.schedule_type,
            is_active=schedule.is_active,
            created_at=schedule.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logfire.error("Error fetching P6 schedule", error=str(e), schedule_id=schedule_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{schedule_id}")
async def deactivate_p6_schedule(schedule_id: str):
    """
    Deactivate (soft-delete) a P6 schedule mapping.
    """
    supabase = get_supabase()
    repo = P6ScheduleRepository(supabase)
    
    try:
        success = await repo.deactivate(schedule_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="P6 schedule not found")
        
        return {"status": "deactivated"}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error("Error deactivating P6 schedule", error=str(e), schedule_id=schedule_id)
        raise HTTPException(status_code=500, detail=str(e))
