"""P6 database activity mutation tools - create, update, delete activities."""

from pydantic_ai import RunContext, ModelRetry
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import (
    ActivityCreateRequest,
    ProgressUpdateRequest,
    ActivityStatusUpdateRequest,
)


@logfire.instrument("create_activity_p6")
async def create_activity_p6(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """Create a new activity in the P6 database (permanent).
    
    Use this tool to add a new task/activity to a project. Requires the WBS ID
    where the activity should be placed.
    
    Important: Use 'task_code' for the Activity ID (e.g., 'A1000'), NOT 'task_id'.
    
    Note: This creates a PERMANENT record in P6. For temporary/draft activities,
    use create_activity_ws instead.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with task_code, task_name, wbs_id, proj_id, and optional duration/calendar.
    
    Returns:
        Success message with the created task code and internal task_id.
    """
    try:
        task_id = ctx.deps.service.create_activity(req, conn=ctx.deps.conn)
        return f"Successfully created activity '{req.task_code}' ({req.task_name}) with internal ID {task_id}."
    except Exception as e:
        logfire.error("Error in create_activity_p6", error=str(e))
        return f"Error creating activity: {str(e)}"


@logfire.instrument("update_progress_p6")
async def update_progress_p6(ctx: RunContext[AgentDeps], req: ProgressUpdateRequest) -> str:
    """Update the physical percent complete of a P6 activity (permanent).
    
    Use this tool to record progress on an activity. If updating to 100%,
    an actual finish date should also be provided.
    
    Note: This updates the P6 database permanently.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with task_code, proj_id, phys_complete_pct (0-100), and optional dates.
    
    Returns:
        Success message with the updated progress value.
    """
    try:
        result = ctx.deps.service.update_progress(req, conn=ctx.deps.conn)
        return result
    except Exception as e:
        logfire.error("Error in update_progress_p6", error=str(e))
        return f"Error updating progress: {str(e)}"


@logfire.instrument("update_activity_status_p6")
async def update_activity_status_p6(ctx: RunContext[AgentDeps], req: ActivityStatusUpdateRequest) -> str:
    """Update the status of a P6 activity with business rule validation (permanent).
    
    Use this tool to change an activity's status. Enforces P6 rules:
    - 'In Progress' requires Actual Start date
    - 'Completed' requires both Actual Start and Actual Finish dates
    
    Always use get_activity_p6 first to check current status.
    
    Note: This updates the P6 database permanently.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing task_code, proj_id, new_status, and optional dates.
    
    Returns:
        Success message confirming the status update.
    
    Raises:
        ModelRetry: If validation fails (e.g., missing required dates for status transition).
    """
    try:
        return ctx.deps.service.update_activity_status(req, conn=ctx.deps.conn)
    except ValueError as e:
        # P6 business rule violation - agent should provide required dates
        raise ModelRetry(f"Status update failed: {e}. Please provide the required dates.")
    except Exception as e:
        logfire.error("Error in update_activity_status_p6", error=str(e))
        return f"Error updating status: {str(e)}"
