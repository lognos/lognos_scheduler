from dataclasses import dataclass
from typing import Optional

from pydantic_ai import RunContext, ModelRetry
import logfire
from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService
from backend.models.io import (
    ActivityCreateRequest, 
    RelationshipCreateRequest, 
    ProgressUpdateRequest, 
    ActivityDetailsRequest, 
    ActivityStatusUpdateRequest, 
    ProjectCreateRequest, 
    SearchActivityRequest, 
    IndexProjectRequest, 
    RelationshipDeleteRequest, 
    RelationshipUpdateRequest, 
    ListProjectsRequest,
    ListActivityCodesRequest,
    AssignActivityCodeRequest,
    RemoveActivityCodeRequest,
    BulkAssignActivityCodeRequest,
    GetActivityCurrentCodesRequest,
)


@dataclass
class AgentDeps:
    """Dependencies for the scheduling agent.
    
    Attributes:
        service: The scheduling service for P6 operations.
        vector_service: Optional vector search service for semantic search.
        conn: Optional database connection for direct queries.
    """
    service: SchedulingService
    vector_service: Optional[VectorService] = None
    conn: Optional[object] = None

@logfire.instrument("delete_relationship_tool")
async def delete_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipDeleteRequest) -> str:
    """Delete an existing relationship between two P6 activities.
    
    Use this tool when the user wants to remove a dependency link between activities.
    The relationship is identified by the predecessor and successor task codes.
    
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
        raise ModelRetry(f"Relationship not found: {e}. Use search_activity_tool to find correct task codes.")
    except Exception as e:
        logfire.error("Error in delete_relationship_tool", error=str(e))
        return f"Error deleting relationship: {str(e)}"

@logfire.instrument("update_relationship_tool")
async def update_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipUpdateRequest) -> str:
    """Update an existing relationship's lag or type.
    
    Use this tool to modify the lag duration or relationship type (FS, SS, FF, SF)
    between two linked activities.
    
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
        raise ModelRetry(f"Relationship not found: {e}. Verify task codes using search_activity_tool.")
    except Exception as e:
        logfire.error("Error in update_relationship_tool", error=str(e))
        return f"Error updating relationship: {str(e)}"

@logfire.instrument("search_activity_tool")
async def search_activity_tool(ctx: RunContext[AgentDeps], req: SearchActivityRequest) -> str:
    """Search for activities using natural language description.
    
    Use this tool when the user refers to an activity by description rather than
    task code. Returns matching activities with their codes and similarity scores.
    
    If no results found, suggest using index_project_tool first to index the project.
    
    Args:
        ctx: Runtime context with dependencies (service, vector_service, connection).
        req: Request containing query text and proj_id for filtering.
    
    Returns:
        Formatted list of matching activities with task codes, names, and scores.
        Returns suggestion to index if no matches found.
    
    Raises:
        ModelRetry: If vector service unavailable (system configuration issue).
    """
    if not ctx.deps.vector_service:
        raise ModelRetry("Vector search service is not available. Please try using the task code directly.")
    
    try:
        results = ctx.deps.vector_service.search_activities(req.query, req.proj_id, threshold=0.5, conn=ctx.deps.conn)
        if not results:
            return f"No matching activities found for '{req.query}'. Try using index_project_tool to index project {req.proj_id} first, then search again."
        
        # Format results for the agent
        response = "Found matching activities:\n"
        for task_id, score in results:
            cursor = ctx.deps.conn.cursor()
            cursor.execute("SELECT TASK_CODE, TASK_NAME FROM TASK WHERE TASK_ID = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                response += f"- {row[0]}: {row[1]} (Score: {score:.2f})\n"
            else:
                response += f"- ID {task_id} (Score: {score:.2f})\n"
                
        return response
    except Exception as e:
        logfire.error("Error in search_activity_tool", error=str(e))
        return f"Error searching activities: {str(e)}"

@logfire.instrument("index_project_tool")
async def index_project_tool(ctx: RunContext[AgentDeps], req: IndexProjectRequest) -> str:
    """Index a P6 project for vector-based activity search.
    
    Use this tool to enable natural language search on a project's activities.
    Generates embeddings for all activities in the project. Should be called
    before search_activity_tool if searches return no results.
    
    Args:
        ctx: Runtime context with dependencies (service, vector_service, connection).
        req: Request containing the proj_id to index.
    
    Returns:
        Success message confirming indexing is complete.
    
    Raises:
        ModelRetry: If vector service unavailable (system configuration issue).
    """
    if not ctx.deps.vector_service:
        raise ModelRetry("Vector search service is not available. Activity search by description is disabled.")

    try:
        ctx.deps.vector_service.index_project(req.proj_id, conn=ctx.deps.conn)
        return f"Successfully indexed project {req.proj_id}. You can now search for activities by description."
    except Exception as e:
        logfire.error("Error in index_project_tool", error=str(e))
        return f"Error indexing project: {str(e)}"

@logfire.instrument("get_activity_details_tool")
async def get_activity_details_tool(ctx: RunContext[AgentDeps], req: ActivityDetailsRequest) -> dict | str:
    """Retrieve current details for a P6 activity.
    
    Use this tool to check an activity's status, dates, and progress before
    making updates. Essential for validating status transitions and calculating
    relative dates.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing task_code and proj_id.
    
    Returns:
        Dictionary with status_code, phys_complete_pct, act_start_date, act_end_date,
        target_start_date (Planned Start), target_end_date (Planned Finish).
    
    Raises:
        ModelRetry: If activity not found (may need to search for correct task code).
    """
    try:
        result = ctx.deps.service.get_activity_details(req, conn=ctx.deps.conn)
        if result is None:
            raise ModelRetry(f"Activity '{req.task_code}' not found in project {req.proj_id}. Use search_activity_tool to find the correct task code.")
        return result
    except ModelRetry:
        raise
    except Exception as e:
        logfire.error("Error in get_activity_details_tool", error=str(e))
        return f"Error retrieving details: {str(e)}"

@logfire.instrument("update_activity_status_tool")
async def update_activity_status_tool(ctx: RunContext[AgentDeps], req: ActivityStatusUpdateRequest) -> str:
    """Update the status of a P6 activity with P6 business rule validation.
    
    Use this tool to change an activity's status. Enforces P6 rules:
    - 'In Progress' requires Actual Start date
    - 'Completed' requires both Actual Start and Actual Finish dates
    
    Always use get_activity_details_tool first to check current status.
    
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
        logfire.error("Error in update_activity_status_tool", error=str(e))
        return f"Error updating status: {str(e)}"

@logfire.instrument("create_activity_tool")
async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """Create a new activity in the P6 schedule.
    
    Use this tool to add a new task/activity to a project. Requires the WBS ID
    where the activity should be placed.
    
    Important: Use 'task_code' for the Activity ID (e.g., 'A1000'), NOT 'task_id'.
    
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
        logfire.error("Error in create_activity_tool", error=str(e))
        return f"Error creating activity: {str(e)}"

@logfire.instrument("create_relationship_tool")
async def create_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipCreateRequest) -> str:
    """Create a dependency relationship between two P6 activities.
    
    Use this tool to link activities with predecessor/successor relationships.
    Supports all P6 relationship types: FS (Finish-to-Start), SS, FF, SF.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with pred_task_code, succ_task_code, proj_id, pred_type, and optional lag.
    
    Returns:
        Success message confirming the relationship was created.
    
    Raises:
        ModelRetry: If either activity not found (use search_activity_tool to find codes).
    """
    try:
        ctx.deps.service.create_relationship(req, conn=ctx.deps.conn)
        lag_info = f" with lag {req.lag}h" if req.lag else ""
        return f"Successfully linked {req.pred_task_code} -> {req.succ_task_code} ({req.pred_type}){lag_info}."
    except ValueError as e:
        raise ModelRetry(f"Cannot create relationship: {e}. Use search_activity_tool to verify task codes.")
    except Exception as e:
        logfire.error("Error in create_relationship_tool", error=str(e))
        return f"Error creating relationship: {str(e)}"

@logfire.instrument("update_progress_tool")
async def update_progress_tool(ctx: RunContext[AgentDeps], req: ProgressUpdateRequest) -> str:
    """Update the physical percent complete of a P6 activity.
    
    Use this tool to record progress on an activity. If updating to 100%,
    an actual finish date should also be provided.
    
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
        logfire.error("Error in update_progress_tool", error=str(e))
        return f"Error updating progress: {str(e)}"

@logfire.instrument("create_project_tool")
async def create_project_tool(ctx: RunContext[AgentDeps], req: ProjectCreateRequest) -> str:
    """Create a new project in the P6 database.
    
    Use this tool to set up a new project with its root WBS structure.
    The project short name must be unique across the P6 database.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with project_short_name, project_name, and optional planned_start_date.
    
    Returns:
        Success message with the new project ID and root WBS ID.
    """
    try:
        proj_id, wbs_id = ctx.deps.service.create_project(req, conn=ctx.deps.conn)
        return f"Successfully created project '{req.project_short_name}' ({req.project_name}) with ID {proj_id}. Root WBS ID: {wbs_id}."
    except Exception as e:
        logfire.error("Error in create_project_tool", error=str(e))
        return f"Error creating project: {str(e)}"

@logfire.instrument("list_projects_tool")
async def list_projects_tool(ctx: RunContext[AgentDeps], req: ListProjectsRequest) -> str:
    """List all projects available in the P6 database.
    
    Use this tool to discover project IDs and see project information.
    Returns a formatted table with project details including activity counts.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Empty request (no parameters needed).
    
    Returns:
        Formatted table of projects with ID, name, dates, activity count, and description.
    """
    try:
        projects = ctx.deps.service.list_projects(req, conn=ctx.deps.conn)
        
        if not projects:
            return "No projects found in the database."
        
        # Build formatted table output
        lines = ["Available Projects:", ""]
        
        # Table header
        header = f"{'PROJ_ID':<10} {'Short Name':<15} {'Project Name':<35} {'Plan Start':<12} {'Plan End':<12} {'Activities':<10} {'Description'}"
        lines.append(header)
        lines.append("-" * 130)
        
        for proj in projects:
            proj_id = proj.get('PROJ_ID', '-')
            short_name = proj.get('PROJ_SHORT_NAME', '-') or '-'
            project_name = proj.get('PROJECT_NAME', '-') or '-'
            plan_start = proj.get('PLAN_START_DATE', '-') or '-'
            plan_end = proj.get('PLAN_END_DATE', '-') or '-'
            activity_count = proj.get('ACTIVITY_COUNT', 0) or 0
            description = proj.get('DESCRIPTION') or '-'
            
            # Truncate long fields
            if len(project_name) > 33:
                project_name = project_name[:30] + '...'
            if len(short_name) > 13:
                short_name = short_name[:10] + '...'
            if len(description) > 50:
                description = description[:47] + '...'
            
            row = f"{proj_id:<10} {short_name:<15} {project_name:<35} {plan_start:<12} {plan_end:<12} {activity_count:<10} {description}"
            lines.append(row)
        
        lines.append("")
        lines.append(f"Total: {len(projects)} project(s)")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in list_projects_tool", error=str(e))
        return f"Error listing projects: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# Activity Code Tools
# ─────────────────────────────────────────────────────────────────────────────


@logfire.instrument("list_activity_codes_tool")
async def list_activity_codes_tool(ctx: RunContext[AgentDeps], req: ListActivityCodesRequest) -> str:
    """List available activity code types and their values.
    
    Use this tool to discover what activity codes can be assigned to activities.
    Shows both global codes and optionally project-specific codes.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with optional proj_id and include_project_codes flag.
    
    Returns:
        Formatted list of code types (e.g., PHASE, DISCIPLINE) with available values.
    """
    try:
        code_types = ctx.deps.service.list_activity_codes(req, conn=ctx.deps.conn)
        
        if not code_types:
            return "No activity codes found."
        
        # Build formatted output
        lines = ["Available Activity Codes:", ""]
        
        for code_type in code_types:
            scope_label = "(Global)" if code_type['scope'] == 'AS_Global' else "(Project)"
            lines.append(f"Code Type: {code_type['actv_code_type']} {scope_label}")
            lines.append("-" * 50)
            
            if code_type['values']:
                lines.append(f"  {'Short Name':<15} {'Description':<40}")
                for val in code_type['values']:
                    short = val['short_name'] or '-'
                    name = val['actv_code_name'] or '-'
                    if len(name) > 38:
                        name = name[:35] + '...'
                    lines.append(f"  {short:<15} {name:<40}")
            else:
                lines.append("  (No values defined)")
            
            lines.append("")
        
        lines.append(f"Total: {len(code_types)} code type(s)")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in list_activity_codes_tool", error=str(e))
        return f"Error listing activity codes: {str(e)}"


@logfire.instrument("get_activity_current_codes_tool")
async def get_activity_current_codes_tool(
    ctx: RunContext[AgentDeps], 
    req: GetActivityCurrentCodesRequest
) -> str:
    """Get current activity code assignments for one or more activities.
    
    Use this tool BEFORE assigning codes to show the user what will be replaced.
    Each activity can only have one code per code type.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with task_codes list and proj_id.
    
    Returns:
        Formatted list of current code assignments per activity.
    """
    try:
        result = ctx.deps.service.get_activity_current_codes(req, conn=ctx.deps.conn)
        
        lines = ["Current Activity Code Assignments:", ""]
        
        for task_code, codes in result.items():
            lines.append(f"Activity: {task_code}")
            if codes:
                for code in codes:
                    lines.append(f"  - {code['code_type_name']}: {code['short_name']} ({code['code_name']})")
            else:
                lines.append("  (No codes assigned)")
            lines.append("")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in get_activity_current_codes_tool", error=str(e))
        return f"Error getting current codes: {str(e)}"


@logfire.instrument("assign_activity_codes_tool")
async def assign_activity_codes_tool(
    ctx: RunContext[AgentDeps], 
    req: AssignActivityCodeRequest
) -> str:
    """Assign one or more activity codes to a single activity.
    
    Use this tool to categorize an activity with codes like PHASE, DISCIPLINE, etc.
    Each activity can have one code per code type - assigning a new code replaces
    the existing one (when replace_existing=True, which is default).
    
    Always use get_activity_current_codes_tool first to show what will be replaced.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with task_code, proj_id, code_assignments, and optional replace_existing flag.
    
    Returns:
        Summary of assigned and replaced codes, plus any errors.
    """
    try:
        result = ctx.deps.service.assign_activity_codes(req, conn=ctx.deps.conn)
        
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
        logfire.error("Error in assign_activity_codes_tool", error=str(e))
        return f"Error assigning activity codes: {str(e)}"


@logfire.instrument("remove_activity_codes_tool")
async def remove_activity_codes_tool(
    ctx: RunContext[AgentDeps], 
    req: RemoveActivityCodeRequest
) -> str:
    """Remove activity code assignments from an activity.
    
    Use this tool to unassign codes from an activity. Specify which code types
    to remove (e.g., ['PHASE', 'DISCIPLINE']).
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with task_code, proj_id, and code_types list to remove.
    
    Returns:
        Summary of removed codes and any code types that weren't assigned.
    """
    try:
        result = ctx.deps.service.remove_activity_codes(req, conn=ctx.deps.conn)
        
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
        logfire.error("Error in remove_activity_codes_tool", error=str(e))
        return f"Error removing activity codes: {str(e)}"


@logfire.instrument("bulk_assign_activity_codes_tool")
async def bulk_assign_activity_codes_tool(
    ctx: RunContext[AgentDeps], 
    req: BulkAssignActivityCodeRequest
) -> str:
    """Assign activity codes to multiple activities at once.
    
    Use this tool for efficient bulk updates. Specify target activities by:
    - task_codes: List of specific activity codes, OR
    - wbs_id: All activities under a WBS (including nested WBS)
    
    The same code assignments are applied to all specified activities.
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request with proj_id, code_assignments, and either task_codes or wbs_id.
    
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
        logfire.error("Error in bulk_assign_activity_codes_tool", error=str(e))
        return f"Error in bulk assignment: {str(e)}"
