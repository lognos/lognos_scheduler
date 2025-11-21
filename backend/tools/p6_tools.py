from pydantic_ai import RunContext
import logfire
from backend.services.scheduling_service import SchedulingService
from backend.models.io import ActivityCreateRequest, RelationshipCreateRequest, ProgressUpdateRequest, ActivityDetailsRequest, ActivityStatusUpdateRequest, ProjectCreateRequest

# We define the dependencies class
class AgentDeps:
    def __init__(self, service: SchedulingService, conn=None):
        self.service = service
        self.conn = conn

@logfire.instrument("get_activity_details_tool")
async def get_activity_details_tool(ctx: RunContext[AgentDeps], req: ActivityDetailsRequest) -> dict | str:
    """
    Retrieves current details (status, dates, % complete) for an activity.
    """
    try:
        return ctx.deps.service.get_activity_details(req, conn=ctx.deps.conn)
    except Exception as e:
        logfire.error("Error in get_activity_details_tool", error=str(e))
        return f"Error retrieving details: {str(e)}"

@logfire.instrument("update_activity_status_tool")
async def update_activity_status_tool(ctx: RunContext[AgentDeps], req: ActivityStatusUpdateRequest) -> str:
    """
    Updates the status of an activity (Not Started, In Progress, Completed) with strict validation.
    """
    try:
        return ctx.deps.service.update_activity_status(req, conn=ctx.deps.conn)
    except Exception as e:
        logfire.error("Error in update_activity_status_tool", error=str(e))
        return f"Error updating status: {str(e)}"

@logfire.instrument("create_activity_tool")
async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """
    Creates a new activity in the P6 schedule.
    """
    try:
        task_id = ctx.deps.service.create_activity(req, conn=ctx.deps.conn)
        return f"Successfully created activity {req.task_code} with ID {task_id}."
    except Exception as e:
        logfire.error("Error in create_activity_tool", error=str(e))
        return f"Error creating activity: {str(e)}"

@logfire.instrument("create_relationship_tool")
async def create_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipCreateRequest) -> str:
    """
    Creates a relationship between two activities.
    """
    try:
        rel_id = ctx.deps.service.create_relationship(req, conn=ctx.deps.conn)
        return f"Successfully linked {req.pred_task_code} -> {req.succ_task_code} ({req.pred_type})."
    except Exception as e:
        logfire.error("Error in create_relationship_tool", error=str(e))
        return f"Error creating relationship: {str(e)}"

@logfire.instrument("update_progress_tool")
async def update_progress_tool(ctx: RunContext[AgentDeps], req: ProgressUpdateRequest) -> str:
    """
    Updates the physical % complete of an activity.
    """
    try:
        result = ctx.deps.service.update_progress(req, conn=ctx.deps.conn)
        return result
    except Exception as e:
        logfire.error("Error in update_progress_tool", error=str(e))
        return f"Error updating progress: {str(e)}"

@logfire.instrument("create_project_tool")
async def create_project_tool(ctx: RunContext[AgentDeps], req: ProjectCreateRequest) -> str:
    """
    Creates a new project in the P6 database.
    """
    try:
        proj_id = ctx.deps.service.create_project(req, conn=ctx.deps.conn)
        return f"Successfully created project '{req.project_short_name}' with ID {proj_id}."
    except Exception as e:
        logfire.error("Error in create_project_tool", error=str(e))
        return f"Error creating project: {str(e)}"
