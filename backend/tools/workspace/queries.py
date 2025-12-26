"""Workspace query tools - read operations on the in-memory workspace."""

import logfire
from pydantic_ai import RunContext
from backend.tools._base import AgentDeps
from backend.services.schedule_state import schedule_state_manager


@logfire.instrument("get_workspace_status_ws")
async def get_workspace_status_ws(ctx: RunContext[AgentDeps]) -> str:
    """Get the current status of the schedule workspace.
    
    Use this tool to check if a schedule is loaded and what modifications
    have been made. Returns information about loaded activities, relationships,
    and whether there are unsaved changes.
    
    Returns:
        Status summary of the current workspace state.
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws to load a project."
        
        status_parts = [
            f"Project: {workspace.project_name or workspace.project_id}",
            f"Source: {workspace.source}",
            f"Activities: {len(workspace.activities_df)}",
            f"Relationships: {len(workspace.relationships_df)}",
            f"Modified: {workspace.is_modified}",
        ]
        
        if workspace.last_calculation_at:
            cp_count = len(workspace.critical_path_ids)
            status_parts.append(f"Critical path activities: {cp_count}")
            status_parts.append(f"Last calculated: {workspace.last_calculation_at.strftime('%H:%M')}")
        else:
            status_parts.append("Last calculated: No")
        
        return " | ".join(status_parts)
        
    except Exception as e:
        logfire.error("Error in get_workspace_status_ws", error=str(e))
        return f"Error getting workspace status: {str(e)}"
