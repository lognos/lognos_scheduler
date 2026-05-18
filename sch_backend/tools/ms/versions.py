"""Version management tools for MS Project schedules."""

from pydantic_ai import RunContext
import logfire

from sch_backend.tools._base import AgentDeps
from sch_backend.models.io import CreateSubversionMsRequest, PromoteSubversionMsRequest
from sch_backend.services.schedule_state import schedule_state_manager


@logfire.instrument("create_schedule_subversion_ms")
async def create_schedule_subversion_ms(
    ctx: RunContext[AgentDeps],
    req: CreateSubversionMsRequest
) -> str:
    """Save current workspace as a new schedule subversion in Supabase.
    
    Creates a temporary version that is NOT current. Use this to save
    work-in-progress changes before they're ready for production.
    
    The workspace must have been loaded from an MS schedule (load_schedule_ms).
    
    Args:
        ctx: Runtime context with ms_repository and conversation_id
        req: Request with optional version_name and required description
        
    Returns:
        Success message with new version ID
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    conversation_id = ctx.deps.conversation_id
    if not conversation_id:
        return "Error: No conversation_id available."
    
    # Get workspace
    workspace = schedule_state_manager.get(conversation_id)
    if not workspace:
        return "No workspace loaded. Use load_schedule_ms first."
    
    if workspace.source != "ms_loaded":
        return f"Workspace source is '{workspace.source}', not 'ms_loaded'. This tool only works with MS schedules loaded via load_schedule_ms."
    
    if not workspace.source_version_id:
        return "Workspace has no source version ID. Cannot determine base version."
    
    try:
        # Create subversion from workspace data
        new_version_id = await ctx.deps.ms_repository.create_subversion(
            base_version_id=workspace.source_version_id,
            version_name=req.version_name,
            description=req.description,
            activities_df=workspace.activities_df,
            relationships_df=workspace.relationships_df
        )
        
        # Get the created version details
        new_version = await ctx.deps.ms_repository.get_version(new_version_id)
        version_name = new_version['version_name'] if new_version else f"ID {new_version_id}"
        
        lines = [
            f"Created subversion: {version_name}",
            f"Version ID: {new_version_id}",
            "Status: Draft (not current)",
            f"Activities saved: {len(workspace.activities_df)}",
            f"Relationships saved: {len(workspace.relationships_df)}",
            "",
            "To make this the current version:",
            f"  promote_subversion_ms(version_id={new_version_id})"
        ]
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in create_schedule_subversion_ms", error=str(e))
        return f"Error creating subversion: {str(e)}"


@logfire.instrument("promote_subversion_ms")
async def promote_subversion_ms(
    ctx: RunContext[AgentDeps],
    req: PromoteSubversionMsRequest
) -> str:
    """Promote a subversion to become the current version.
    
    This will:
    1. Unset is_current on the previous current version
    2. Set is_current=true on the specified version
    3. Return a diff summary of changes
    
    Use expected_current_version_id for optimistic locking - if the current
    version has changed since you last checked, the operation will fail.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with version_id and optional expected_current_version_id
        
    Returns:
        Success message with diff summary
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    try:
        # Get version info before promoting
        version = await ctx.deps.ms_repository.get_version(req.version_id)
        if not version:
            return f"Version {req.version_id} not found."
        
        if version.get('is_current'):
            return f"Version {req.version_id} ({version['version_name']}) is already current."
        
        # Perform promotion with optimistic lock
        result = await ctx.deps.ms_repository.promote_to_current(
            version_id=req.version_id,
            expected_current_version_id=req.expected_current_version_id
        )
        
        lines = [
            f"Promoted version {req.version_id} ({version['version_name']}) to CURRENT",
            "",
        ]
        
        # Include diff summary if available
        diff = result.get('diff')
        if diff:
            lines.append("Changes from previous version:")
            lines.append(f"  - Added: {diff.get('added_count', 0)} activities")
            lines.append(f"  - Removed: {diff.get('removed_count', 0)} activities")
            lines.append(f"  - Modified: {diff.get('modified_count', 0)} activities")
            
            # Show some modified details
            modified = diff.get('modified', [])
            if modified:
                lines.append("")
                lines.append("Modified activities (sample):")
                for m in modified[:5]:
                    changes = m.get('changes', {})
                    change_strs = []
                    for field, vals in changes.items():
                        old_val = vals.get('old', '?')
                        new_val = vals.get('new', '?')
                        # Truncate dates
                        if isinstance(old_val, str) and len(old_val) > 10:
                            old_val = old_val[:10]
                        if isinstance(new_val, str) and len(new_val) > 10:
                            new_val = new_val[:10]
                        change_strs.append(f"{field}: {old_val} -> {new_val}")
                    lines.append(f"  - {m.get('name', '?')[:30]}: {', '.join(change_strs)}")
        else:
            lines.append("(No previous current version - first promotion)")
        
        if result.get('previous_current_id'):
            lines.append("")
            lines.append(f"Previous current version ID: {result['previous_current_id']}")
        
        return "\n".join(lines)
        
    except ValueError as e:
        # Optimistic lock failure
        return f"Promotion failed: {str(e)}"
    except Exception as e:
        logfire.error("Error in promote_subversion_ms", error=str(e))
        return f"Error promoting version: {str(e)}"
