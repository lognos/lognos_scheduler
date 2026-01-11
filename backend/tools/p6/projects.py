"""P6 database project mutation tools - create projects."""

from pydantic_ai import RunContext
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import ProjectCreateRequest


@logfire.instrument("create_project_p6")
async def create_project_p6(ctx: RunContext[AgentDeps], req: ProjectCreateRequest) -> str:
    """Create a new project in the P6 database (permanent).
    
    Use this tool to set up a new project with its root WBS structure.
    The project short name must be unique across the P6 database.
    
    Note: This creates a PERMANENT record in P6.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with project_short_name, project_name, and optional planned_start_date.
    
    Returns:
        Success message with the new project ID and root WBS ID.
    """
    try:
        # Idempotency check: does project already exist?
        cursor = ctx.deps.conn.cursor()
        cursor.execute(
            "SELECT PROJ_ID FROM PROJECT WHERE PROJ_SHORT_NAME = ?",
            (req.project_short_name,)
        )
        existing = cursor.fetchone()
        if existing:
            return f"Project '{req.project_short_name}' already exists (proj_id={existing[0]}). No action taken."
        
        proj_id, wbs_id = ctx.deps.service.create_project(req, conn=ctx.deps.conn)
        ctx.deps.mark_modified()  # Mark transaction as modified for backup
        return f"Successfully created project '{req.project_short_name}' ({req.project_name}) with ID {proj_id}. Root WBS ID: {wbs_id}."
    except Exception as e:
        logfire.error("Error in create_project_p6", error=str(e))
        return f"Error creating project: {str(e)}"
