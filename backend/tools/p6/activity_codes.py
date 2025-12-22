"""P6 database activity code mutation tools - assign, remove, bulk assign codes."""

from pydantic_ai import RunContext
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import (
    AssignActivityCodeRequest,
    RemoveActivityCodeRequest,
    BulkAssignActivityCodeRequest,
)


@logfire.instrument("assign_activity_codes_p6")
async def assign_activity_codes_p6(
    ctx: RunContext[AgentDeps], 
    req: AssignActivityCodeRequest
) -> str:
    """Assign one or more activity codes to a single activity in P6 (permanent).
    
    Use this tool to categorize an activity with codes like PHASE, DISCIPLINE, etc.
    Each activity can have one code per code type - assigning a new code replaces
    the existing one (when replace_existing=True, which is default).
    
    Always use get_activity_codes_p6 first to show what will be replaced.
    
    Note: This updates the P6 database permanently.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing:
            - task_code: Activity ID (e.g., "A1000")
            - proj_id: Project ID (e.g., 1234)
            - code_assignments: Dict mapping code type to value, e.g., {"PHASE": "CON", "DISCIPLINE": "CIV"}
            - replace_existing: If True (default), replace existing codes
    
    Example code_assignments format:
        {"PHASE": "ENG", "DISCIPLINE": "MECH", "AREA": "NORTH"}
    
    Returns:
        Summary of assigned and replaced codes, plus any errors.
    """
    try:
        result = ctx.deps.service.assign_activity_codes(req, conn=ctx.deps.conn)
        
        # Mark modified if any codes were assigned or replaced
        if result['assigned'] or result['replaced']:
            ctx.deps.mark_modified()
        
        lines = [f"Assignment results for activity '{result['task_code']}':", ""]
        
        if result['assigned']:
            lines.append("Assigned:")
            for a in result['assigned']:
                lines.append(f"  - {a['code_type']}: {a['code_value']}")
        
        if result['replaced']:
            lines.append("")
            lines.append("Replaced (previous values):")
            for r in result['replaced']:
                lines.append(f"  - {r['code_type']}: {r['old_value']} -> {r['new_value']}")
        
        if result['errors']:
            lines.append("")
            lines.append("Errors:")
            for e in result['errors']:
                lines.append(f"  - {e}")
        
        if not result['assigned'] and not result['errors']:
            lines.append("No codes were assigned.")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in assign_activity_codes_p6", error=str(e))
        return f"Error assigning activity codes: {str(e)}"


@logfire.instrument("remove_activity_codes_p6")
async def remove_activity_codes_p6(
    ctx: RunContext[AgentDeps], 
    req: RemoveActivityCodeRequest
) -> str:
    """Remove activity code assignments from an activity in P6 (permanent).
    
    Use this tool to unassign codes from an activity. Specify which code types
    to remove (e.g., ['PHASE', 'DISCIPLINE']).
    
    Note: This updates the P6 database permanently.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with task_code, proj_id, and code_types list to remove.
    
    Returns:
        Summary of removed codes and any code types that weren't assigned.
    """
    try:
        result = ctx.deps.service.remove_activity_codes(req, conn=ctx.deps.conn)
        
        # Mark modified if any codes were removed
        if result['removed']:
            ctx.deps.mark_modified()
        
        lines = [f"Removal results for activity '{result['task_code']}':", ""]
        
        if result['removed']:
            lines.append("Removed:")
            for r in result['removed']:
                lines.append(f"  - {r['code_type']}: {r['removed_value']}")
        
        if result['not_found']:
            lines.append("")
            lines.append("Not found/not assigned:")
            for nf in result['not_found']:
                lines.append(f"  - {nf}")
        
        if not result['removed'] and not result['not_found']:
            lines.append("No codes were removed.")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in remove_activity_codes_p6", error=str(e))
        return f"Error removing activity codes: {str(e)}"


@logfire.instrument("bulk_assign_activity_codes_p6")
async def bulk_assign_activity_codes_p6(
    ctx: RunContext[AgentDeps], 
    req: BulkAssignActivityCodeRequest
) -> str:
    """Assign activity codes to multiple activities at once in P6 (permanent).
    
    Use this tool for efficient bulk updates. Specify target activities by:
    - task_codes: List of specific activity codes, OR
    - wbs_id: All activities under a WBS (including nested WBS)
    
    The same code assignments are applied to all specified activities.
    
    Note: This updates the P6 database permanently.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing:
            - proj_id: Project ID (e.g., 1234)
            - code_assignments: Dict mapping code type to value, e.g., {"PHASE": "CON", "DISCIPLINE": "CIV"}
            - replace_existing: If True (default), replace existing codes
            - task_codes: List of activity codes (e.g., ["A1000", "A1010"]), OR
            - wbs_id: WBS ID to assign to all activities under it
    
    Example code_assignments format:
        {"PHASE": "ENG", "DISCIPLINE": "MECH"}
    
    Returns:
        Summary with counts of assigned/replaced codes and per-activity details.
    """
    try:
        result = ctx.deps.service.bulk_assign_activity_codes(req, conn=ctx.deps.conn)
        
        if not result['success']:
            lines = ["Bulk assignment failed due to code resolution errors:", ""]
            for err in result['resolution_errors']:
                lines.append(f"  - {err}")
            return "\n".join(lines)
        
        # Mark modified if any codes were assigned
        if result['total_tasks'] > 0:
            ctx.deps.mark_modified()
        
        lines = [f"Bulk assignment completed for {result['total_tasks']} activities:", ""]
        
        # Summary counts
        total_assigned = sum(len(tr['assigned']) for tr in result['task_results'])
        total_replaced = sum(len(tr['replaced']) for tr in result['task_results'])
        
        lines.append(f"Summary: {total_assigned} code(s) assigned, {total_replaced} code(s) replaced")
        lines.append("")
        
        # Detailed results (limit to first 10 if many)
        results_to_show = result['task_results'][:10]
        if len(result['task_results']) > 10:
            lines.append(f"Showing first 10 of {len(result['task_results'])} activities:")
        
        for tr in results_to_show:
            lines.append(f"  {tr['task_code']}: {len(tr['assigned'])} assigned")
            if tr['replaced']:
                replaced_types = [r['code_type'] for r in tr['replaced']]
                lines.append(f"    (replaced: {', '.join(replaced_types)})")
        
        if len(result['task_results']) > 10:
            lines.append(f"  ... and {len(result['task_results']) - 10} more")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in bulk_assign_activity_codes_p6", error=str(e))
        return f"Error in bulk assignment: {str(e)}"
