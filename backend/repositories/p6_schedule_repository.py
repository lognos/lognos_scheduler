"""
Repository for P6 schedule mapping operations.
Maps Lognos projects to P6 schedule instances.
"""
from typing import Optional
import logfire
from supabase import Client

from backend.models.domain import P6Schedule, P6ScheduleCreate


class P6ScheduleRepository:
    """Repository for p6_schedules table."""
    
    TABLE = "p6_schedules"
    SCHEMA = "lognos_comm"
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    @logfire.instrument("repo.create_p6_schedule")
    async def create(self, schedule: P6ScheduleCreate) -> P6Schedule:
        """Create a new P6 schedule mapping."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .insert(schedule.model_dump())
            .execute()
        )
        if result.data:
            return P6Schedule(**result.data[0])
        raise ValueError("Failed to create P6 schedule mapping")
    
    @logfire.instrument("repo.get_p6_schedule_by_id")
    async def get_by_id(self, schedule_id: str) -> Optional[P6Schedule]:
        """Get a P6 schedule by its UUID."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .select("*")
            .eq("id", schedule_id)
            .single()
            .execute()
        )
        if result.data:
            return P6Schedule(**result.data)
        return None
    
    @logfire.instrument("repo.get_p6_schedule_by_proj_id")
    async def get_by_p6_proj_id(
        self,
        project_id: str,
        p6_proj_id: int,
    ) -> Optional[P6Schedule]:
        """Get a P6 schedule by Lognos project_id and P6 proj_id."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .select("*")
            .eq("project_id", project_id)
            .eq("p6_proj_id", p6_proj_id)
            .single()
            .execute()
        )
        if result.data:
            return P6Schedule(**result.data)
        return None
    
    @logfire.instrument("repo.list_p6_schedules")
    async def list_by_project(
        self,
        project_id: str,
        active_only: bool = True,
    ) -> list[P6Schedule]:
        """List all P6 schedules for a Lognos project."""
        query = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .select("*")
            .eq("project_id", project_id)
            .order("created_at", desc=True)
        )
        
        if active_only:
            query = query.eq("is_active", True)
        
        result = query.execute()
        return [P6Schedule(**s) for s in (result.data or [])]
    
    @logfire.instrument("repo.get_default_p6_schedule")
    async def get_default_for_project(
        self,
        project_id: str,
    ) -> Optional[P6Schedule]:
        """
        Get the default P6 schedule for a project.
        Prefers 'current' type, falls back to most recent active.
        """
        # First try to find a 'current' type schedule
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .select("*")
            .eq("project_id", project_id)
            .eq("is_active", True)
            .eq("schedule_type", "current")
            .limit(1)
            .execute()
        )
        
        if result.data:
            return P6Schedule(**result.data[0])
        
        # Fall back to most recent active schedule
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .select("*")
            .eq("project_id", project_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        
        if result.data:
            return P6Schedule(**result.data[0])
        
        return None
    
    @logfire.instrument("repo.update_p6_schedule")
    async def update(
        self,
        schedule_id: str,
        **updates,
    ) -> bool:
        """Update a P6 schedule mapping."""
        if not updates:
            return True
        
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.TABLE)
            .update(updates)
            .eq("id", schedule_id)
            .execute()
        )
        return len(result.data) > 0 if result.data else False
    
    @logfire.instrument("repo.deactivate_p6_schedule")
    async def deactivate(self, schedule_id: str) -> bool:
        """Soft-delete a P6 schedule by setting is_active to False."""
        return await self.update(schedule_id, is_active=False)
    
    @logfire.instrument("repo.get_p6_proj_id")
    async def resolve_p6_proj_id(
        self,
        project_id: str,
        p6_schedule_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Resolve the P6 proj_id for a project.
        If p6_schedule_id is provided, use that specific schedule.
        Otherwise, use the default schedule for the project.
        """
        if p6_schedule_id:
            schedule = await self.get_by_id(p6_schedule_id)
        else:
            schedule = await self.get_default_for_project(project_id)
        
        if schedule:
            return schedule.p6_proj_id
        return None
