"""P6 database relationship mutation tools - create, update, delete relationships."""

from pydantic_ai import RunContext, ModelRetry
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import (
    RelationshipCreateRequest,
    RelationshipUpdateRequest,
    RelationshipDeleteRequest,
)


@logfire.instrument("create_relationship_p6")
async def create_relationship_p6(ctx: RunContext[AgentDeps], req: RelationshipCreateRequest) -> str:
    """Create a dependency relationship between two P6 activities (permanent).
    
    Use this tool to link activities with predecessor/successor relationships.
    Supports all P6 relationship types: FS (Finish-to-Start), SS, FF, SF.
    
    Note: This creates a PERMANENT record in P6. For temporary/draft relationships,
    use create_relationship_ws instead.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with pred_task_code, succ_task_code, proj_id, pred_type, and optional lag.
    
    Returns:
        Success message confirming the relationship was created.
    
    Raises:
        ModelRetry: If either activity not found (use search_activities_p6 to find codes).
    """
    try:
        ctx.deps.service.create_relationship(req, conn=ctx.deps.conn)
        lag_info = f" with lag {req.lag}h" if req.lag else ""
        return f"Successfully linked {req.pred_task_code} -> {req.succ_task_code} ({req.pred_type}){lag_info}."
    except ValueError as e:
        raise ModelRetry(f"Cannot create relationship: {e}. Use search_activities_p6 to verify task codes.")
    except Exception as e:
        logfire.error("Error in create_relationship_p6", error=str(e))
        return f"Error creating relationship: {str(e)}"


@logfire.instrument("update_relationship_p6")
async def update_relationship_p6(ctx: RunContext[AgentDeps], req: RelationshipUpdateRequest) -> str:
    """Update an existing relationship's lag or type in P6 (permanent).
    
    Use this tool to modify the lag duration or relationship type (FS, SS, FF, SF)
    between two linked activities that exist in the P6 database.
    
    Note: This updates the P6 database permanently. For modifying relationships
    in the workspace, use update_relationship_ws instead.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing task codes, proj_id, and optional new_lag or new_type.
    
    Returns:
        Success message with updated relationship details.
    
    Raises:
        ModelRetry: If relationship not found (may need to verify task codes).
    """
    try:
        return ctx.deps.service.update_relationship(req, conn=ctx.deps.conn)
    except ValueError as e:
        # Relationship not found
        raise ModelRetry(f"Relationship not found: {e}. Verify task codes using search_activities_p6.")
    except Exception as e:
        logfire.error("Error in update_relationship_p6", error=str(e))
        return f"Error updating relationship: {str(e)}"


@logfire.instrument("delete_relationship_p6")
async def delete_relationship_p6(ctx: RunContext[AgentDeps], req: RelationshipDeleteRequest) -> str:
    """Delete an existing relationship between two P6 activities (permanent).
    
    Use this tool when the user wants to remove a dependency link between activities.
    The relationship is identified by the predecessor and successor task codes.
    
    Note: This deletes from the P6 database permanently.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing pred_task_code, succ_task_code, and proj_id.
    
    Returns:
        Success message confirming the relationship was deleted.
    
    Raises:
        ModelRetry: If relationship not found (may need to search for correct task codes).
    """
    try:
        return ctx.deps.service.delete_relationship(req, conn=ctx.deps.conn)
    except ValueError as e:
        # Relationship not found - agent should search for correct task codes
        raise ModelRetry(f"Relationship not found: {e}. Use search_activities_p6 to find correct task codes.")
    except Exception as e:
        logfire.error("Error in delete_relationship_p6", error=str(e))
        return f"Error deleting relationship: {str(e)}"
