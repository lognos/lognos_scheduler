"""Workspace loading tools for MS Project schedules."""

from pydantic_ai import RunContext
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import LoadScheduleMsRequest
from backend.services.schedule_state import schedule_state_manager


@logfire.instrument("load_schedule_ms")
async def load_schedule_ms(
    ctx: RunContext[AgentDeps],
    req: LoadScheduleMsRequest
) -> str:
    """Load MS Project schedule from Supabase into workspace for editing.
    
    Creates an in-memory copy that can be modified and visualized without
    affecting the database. Use workspace tools (_ws) to make changes,
    then save with create_schedule_subversion_ms.
    
    Args:
        ctx: Runtime context with ms_repository and conversation_id
        req: Request with project_name and optional version_id
        
    Returns:
        Summary of loaded schedule
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    conversation_id = ctx.deps.conversation_id
    if not conversation_id:
        return "Error: No conversation_id available. Cannot load schedule."
    
    try:
        # Get version (current if not specified)
        if req.version_id:
            version = await ctx.deps.ms_repository.get_version(req.version_id)
        else:
            version = await ctx.deps.ms_repository.get_current_version(req.project_name)
        
        if not version:
            return f"No schedule found for project '{req.project_name}'"
        
        # Load all activities (full schedule, not just lookahead)
        activities = await ctx.deps.ms_repository.get_activities_by_version(
            version_id=version['id'],
            limit=5000,
            include_summary=True
        )
        
        # Load relationships
        relationships = await ctx.deps.ms_repository.get_relationships_by_version(
            version_id=version['id']
        )
        
        # Load calendar info
        calendar_info = await ctx.deps.ms_repository.get_calendar(version['id'])

        # Load project-level constraints and constraint reference types
        project_constraints = await ctx.deps.ms_repository.get_project_constraints(version['id'])
        constraint_types = await ctx.deps.ms_repository.get_constraint_types()
        
        # Load into workspace (stores in schedule_state_manager)
        schedule_state_manager.load_from_ms(
            conversation_id=conversation_id,
            project_name=req.project_name,
            version_id=version['id'],
            activities=activities,
            relationships=relationships,
            calendar_info=calendar_info,
            project_constraints=project_constraints,
            constraint_types=constraint_types,
        )
        
        # Build response
        version_label = version['version_name']
        if version.get('is_current'):
            version_label += " (CURRENT)"
        elif version.get('is_baseline'):
            version_label += " (BASELINE)"
        
        calendar_name = "Default"
        if calendar_info and calendar_info.get('calendar'):
            calendar_name = calendar_info['calendar'].get('calendar_name', 'Default')
        
        # Count non-summary activities
        work_activities = [a for a in activities if not a.get('is_summary')]
        summary_activities = [a for a in activities if a.get('is_summary')]
        
        lines = [
            f"Loaded '{req.project_name}' {version_label}",
            f"Activities: {len(work_activities)} work + {len(summary_activities)} summary",
            f"Relationships: {len(relationships)}",
            f"Calendar: {calendar_name}",
            "",
            "Use workspace tools to modify:",
            "  - modify_activity_ws: Change activity dates/duration",
            "  - add_activity_ws: Add new activities",
            "  - add_relationship_ws: Add dependencies",
            "  - calculate_gantt_ws: Visualize and calculate CPM",
            "",
            "When ready, save with create_schedule_subversion_ms"
        ]
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in load_schedule_ms", error=str(e))
        return f"Error loading schedule: {str(e)}"
