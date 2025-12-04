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
    ListActivitiesRequest,
)


@dataclass
class AgentDeps:
    """Dependencies for the scheduling agent.
    
    Attributes:
        service: The scheduling service for P6 operations.
        vector_service: Optional vector search service for semantic search.
        conn: Optional database connection for direct queries.
        gantt_event_queue: Queue for gantt panel events to be streamed to frontend.
        conversation_id: Unique conversation ID for workspace isolation.
    """
    service: SchedulingService
    vector_service: Optional[VectorService] = None
    conn: Optional[object] = None
    gantt_event_queue: Optional[list] = None
    conversation_id: Optional[str] = None

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


@logfire.instrument("list_activities_tool")
async def list_activities_tool(ctx: RunContext[AgentDeps], req: ListActivitiesRequest) -> str:
    """List activities in a project, optionally filtered by WBS.
    
    Use this tool to:
    - List all activities in a project
    - List activities under a specific WBS element (by name or ID)
    - Show activity codes assigned to each activity
    
    The tool returns a formatted table with activity details and their codes.
    
    Filtering by WBS:
    - Use wbs_name for partial name matching (e.g., "FOUNDATION", "CIVIL")
    - Use wbs_id if you know the exact WBS ID
    - If wbs_name matches multiple WBS elements, you'll get options to clarify
    
    Args:
        ctx: Runtime context with dependencies (service, connection).
        req: Request containing:
            - proj_id: Project ID (required)
            - wbs_name: Filter by WBS name (partial match)
            - wbs_id: Filter by exact WBS ID
            - include_activity_codes: Include code assignments (default True)
            - limit: Max activities to return (default 100)
    
    Returns:
        Formatted table of activities with their codes and details.
    """
    try:
        result = ctx.deps.service.list_activities(req, conn=ctx.deps.conn)
        
        activities = result['activities']
        
        if not activities:
            if req.wbs_name:
                return f"No activities found under WBS matching '{req.wbs_name}' in project {req.proj_id}."
            elif req.wbs_id:
                return f"No activities found under WBS ID {req.wbs_id} in project {req.proj_id}."
            else:
                return f"No activities found in project {req.proj_id}."
        
        # Build formatted output
        lines = []
        
        # Header with filter info
        if result['wbs_filter']:
            wbs_info = result['wbs_filter']
            lines.append(f"Activities under WBS: {wbs_info['wbs_path']} ({wbs_info['wbs_name']})")
        else:
            lines.append(f"Activities in Project {req.proj_id}")
        
        lines.append(f"Showing {result['count']} activities" + (" (truncated)" if result['truncated'] else ""))
        lines.append("")
        
        # Collect all unique code types across activities for table headers
        code_types = set()
        if req.include_activity_codes:
            for act in activities:
                for code in act.get('activity_codes', []):
                    code_types.add(code['code_type_name'])
        code_types_list = sorted(code_types)
        
        # Build table header
        header_parts = ["Task Code", "Task Name", "Status", "Duration", "%Comp"]
        header_parts.extend(code_types_list)
        
        # Calculate column widths
        col_widths = {
            "Task Code": 12,
            "Task Name": 35,
            "Status": 10,
            "Duration": 10,
            "%Comp": 6,
        }
        for ct in code_types_list:
            col_widths[ct] = max(8, len(ct) + 2)
        
        # Format header
        header = ""
        for part in header_parts:
            header += f"{part:<{col_widths.get(part, 10)}}"
        lines.append(header)
        lines.append("-" * len(header))
        
        # Format each activity
        for act in activities:
            task_code = act['task_code'] or '-'
            task_name = act['task_name'] or '-'
            if len(task_name) > 33:
                task_name = task_name[:30] + '...'
            
            # Status mapping
            status_map = {
                'TK_NotStart': 'Not Start',
                'TK_Active': 'Active',
                'TK_Complete': 'Complete'
            }
            status = status_map.get(act['status_code'], act['status_code'] or '-')
            
            # Duration in days (assuming 8 hr workday)
            duration_hrs = act.get('duration_hrs') or 0
            duration_str = f"{duration_hrs/8:.1f}d" if duration_hrs else '-'
            
            # Percent complete
            pct = act.get('phys_complete_pct')
            pct_str = f"{pct:.0f}%" if pct is not None else '-'
            
            # Build row
            row = f"{task_code:<{col_widths['Task Code']}}"
            row += f"{task_name:<{col_widths['Task Name']}}"
            row += f"{status:<{col_widths['Status']}}"
            row += f"{duration_str:<{col_widths['Duration']}}"
            row += f"{pct_str:<{col_widths['%Comp']}}"
            
            # Add activity codes
            codes_by_type = {c['code_type_name']: c['short_name'] for c in act.get('activity_codes', [])}
            for ct in code_types_list:
                code_val = codes_by_type.get(ct, '-')
                row += f"{code_val:<{col_widths[ct]}}"
            
            lines.append(row)
        
        # Summary
        lines.append("")
        lines.append(f"Total: {result['count']} activities")
        
        # Show activities without codes if any
        if req.include_activity_codes:
            activities_without_codes = [
                a['task_code'] for a in activities 
                if not a.get('activity_codes')
            ]
            if activities_without_codes:
                lines.append("")
                lines.append(f"Activities without activity codes ({len(activities_without_codes)}):")
                lines.append(", ".join(activities_without_codes[:20]))
                if len(activities_without_codes) > 20:
                    lines.append(f"  ... and {len(activities_without_codes) - 20} more")
        
        return "\n".join(lines)
    except ValueError as e:
        # Could be WBS not found or multiple matches
        return str(e)
    except Exception as e:
        logfire.error("Error in list_activities_tool", error=str(e))
        return f"Error listing activities: {str(e)}"


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


# ─────────────────────────────────────────────────────────────────────────────────
# Schedule Workspace & Gantt Tools
# ─────────────────────────────────────────────────────────────────────────────────

import pandas as pd
from backend.services.schedule_state import schedule_state_manager, ScheduleWorkspace
from backend.services.network_calculator import NetworkCalculator, CalculationResult, ScheduleValidationError


@logfire.instrument("load_schedule_to_workspace_tool")
async def load_schedule_to_workspace_tool(
    ctx: RunContext[AgentDeps], 
    proj_id: int
) -> str:
    """Load a P6 schedule into the working workspace for visualization and editing.
    
    Use this tool when the user wants to:
    - View a schedule as a Gantt chart
    - Analyze schedule data (critical path, float, etc.)
    - Prepare for schedule modifications
    
    This loads ALL activities and relationships from P6 into memory.
    After loading, use calculate_and_display_gantt_tool to show the Gantt chart.
    
    Args:
        ctx: Runtime context with dependencies (includes conversation_id)
        proj_id: P6 Project ID to load
    
    Returns:
        Summary of loaded schedule (activity count, relationship count, etc.)
    """
    try:
        conversation_id = ctx.deps.conversation_id
        
        # Load schedule data from P6
        schedule_data = ctx.deps.service.load_schedule_for_workspace(
            proj_id, 
            conn=ctx.deps.conn
        )
        
        project_info = schedule_data['project_info']
        
        # Convert to DataFrames
        activities_df = pd.DataFrame(schedule_data['activities'])
        relationships_df = pd.DataFrame(schedule_data['relationships'])
        activity_codes_df = pd.DataFrame(schedule_data['activity_codes'])
        
        # Parse P6 project dates
        p6_start = None
        p6_finish = None
        if project_info.get('plan_start_date'):
            try:
                p6_start = pd.to_datetime(project_info['plan_start_date']).date()
            except Exception:
                pass
        if project_info.get('plan_end_date'):
            try:
                p6_finish = pd.to_datetime(project_info['plan_end_date']).date()
            except Exception:
                pass
        
        # Load into workspace
        workspace = schedule_state_manager.load_from_p6(
            conversation_id=conversation_id,
            project_id=proj_id,
            project_name=project_info.get('project_name', 'Unknown'),
            activities_df=activities_df,
            relationships_df=relationships_df,
            activity_codes_df=activity_codes_df,
            code_types_with_values=schedule_data['available_codes'],
            project_start=p6_start,
            project_finish=p6_finish
        )
        
        # Return minimal summary to reduce token usage in conversation history
        # Rich data is already in the workspace and will be streamed to frontend
        activity_count = workspace.get_activity_count()
        return f"Loaded '{project_info.get('project_name', 'Unknown')}': {activity_count} activities. Ready for calculate_and_display_gantt_tool."
        
    except ValueError as e:
        return f"Error loading schedule: {e}"
    except Exception as e:
        logfire.error("Error in load_schedule_to_workspace_tool", error=str(e))
        return f"Error loading schedule: {str(e)}"


@logfire.instrument("calculate_and_display_gantt_tool")
async def calculate_and_display_gantt_tool(
    ctx: RunContext[AgentDeps], 
    filter_activity_codes: dict[str, list[str]] | None = None,
    filter_wbs: str | None = None,
    filter_critical_only: bool = False,
    filter_status: list[str] | None = None,
    filter_search: str | None = None,
    filter_date_start: str | None = None,
    filter_date_end: str | None = None
) -> str:
    """Calculate CPM and display Gantt chart in the UI.
    
    Use this tool to:
    - Show the Gantt chart panel to the user
    - Recalculate schedule after modifications
    - Apply filters to show a subset of activities
    
    FILTERING (all done in-memory, no database queries):
    - filter_activity_codes: PRIMARY filter - dict of code_type -> list of values
      Example: {"Phase": ["Construction"], "Area": ["Building A", "Building B"]}
    - filter_wbs: Show only activities under this WBS path
    - filter_critical_only: Show only critical path activities
    - filter_status: Filter by status list
    - filter_search: Search in task code/name
    - filter_date_start/end: Date range filter
    
    Args:
        ctx: Runtime context with dependencies (includes conversation_id)
        filter_activity_codes: Filter by activity codes dict
        filter_wbs: Filter by WBS path
        filter_critical_only: Show only critical activities
        filter_status: Filter by status list
        filter_search: Search in task code/name
        filter_date_start: Filter activities starting after this date (ISO format)
        filter_date_end: Filter activities ending before this date (ISO format)
    
    Returns:
        Summary of displayed schedule and filter applied
    """
    try:
        conversation_id = ctx.deps.conversation_id
        
        # Get workspace
        workspace = schedule_state_manager.get(conversation_id)
        if not workspace:
            return "No schedule loaded. Use load_schedule_to_workspace_tool first."
        
        if workspace.activities_df.empty:
            return "Schedule workspace is empty. Load a schedule first."
        
        # Run CPM calculation
        calculator = NetworkCalculator(
            activities_df=workspace.activities_df,
            relationships_df=workspace.relationships_df,
            project_start_date=workspace.project_start
        )
        
        try:
            result = calculator.calculate()
        except ScheduleValidationError as e:
            return f"Schedule validation failed: {'; '.join(e.errors)}"
        
        # Update workspace with calculation results
        calc_df = pd.DataFrame([{
            'task_id': a.task_id,
            'early_start': a.early_start,
            'early_finish': a.early_finish,
            'late_start': a.late_start,
            'late_finish': a.late_finish,
            'total_float_days': a.total_float_days,
            'free_float_days': a.free_float_days,
            'is_critical': a.is_critical,
            'status': a.status,
        } for a in result.activities])
        
        workspace.update_from_calculation(
            activities_with_dates=calc_df,
            project_start=result.project_start,
            project_finish=result.project_finish,
            critical_path_ids=result.critical_path_ids
        )
        
        # Apply filters (ALL IN-MEMORY - no database queries)
        filtered_df = workspace.filter_activities(
            wbs_path=filter_wbs,
            date_start=filter_date_start,
            date_end=filter_date_end,
            critical_only=filter_critical_only,
            status=filter_status,
            search_term=filter_search,
            activity_codes=filter_activity_codes
        )
        
        # Build Gantt data for streaming
        gantt_items = []
        for _, row in filtered_df.iterrows():
            gantt_items.append({
                'id': int(row['task_id']),
                's_item_id': row['task_code'],
                's_item': row['task_name'],
                'total_duration': float(row.get('total_float_days', 0)) if pd.notna(row.get('total_float_days')) else 0,
                'start': row['early_start'].isoformat() if pd.notna(row.get('early_start')) else '',
                'finish': row['early_finish'].isoformat() if pd.notna(row.get('early_finish')) else '',
                'is_critical': bool(row.get('is_critical', False)),
                'wbs_path': row.get('wbs_path', ''),
                'status': row.get('status', 'not_started'),
            })
        
        # Build filter description
        filter_parts = []
        if filter_activity_codes:
            for code_type, values in filter_activity_codes.items():
                filter_parts.append(f"{code_type}={' or '.join(values)}")
        if filter_wbs:
            filter_parts.append(f"WBS={filter_wbs}")
        if filter_critical_only:
            filter_parts.append("Critical Path Only")
        if filter_status:
            filter_parts.append(f"Status={', '.join(filter_status)}")
        if filter_search:
            filter_parts.append(f"Search='{filter_search}'")
        
        filter_desc = " AND ".join(filter_parts) if filter_parts else "None"
        
        # Stream Gantt panel event to frontend
        # This will be picked up by the AG-UI stream handler
        gantt_event = {
            'type': 'gantt_panel',
            'action': 'show',
            'data': {
                'items': gantt_items,
                'project_start': result.project_start.isoformat(),
                'project_finish': result.project_finish.isoformat(),
                'critical_path_length': result.critical_path_length_days,
                'filter_applied': {
                    'wbs_path': filter_wbs,
                    'critical_only': filter_critical_only,
                    'activity_codes': filter_activity_codes,
                    'status': filter_status,
                    'search_term': filter_search,
                },
                'total_activities': workspace.get_activity_count(),
                'filtered_activities': len(gantt_items),
                'available_activity_codes': workspace.code_types_with_values,
            }
        }
        
        # Store event for streaming (will be picked up by chat router)
        if hasattr(ctx.deps, 'gantt_event_queue'):
            ctx.deps.gantt_event_queue.append(gantt_event)
        
        # Return minimal summary - full data already streamed to frontend via gantt_event
        # This reduces token accumulation in conversation history
        warning_note = f" ({len(result.warnings)} warnings)" if result.warnings else ""
        return f"Gantt displayed: {len(gantt_items)}/{workspace.get_activity_count()} activities, {result.critical_path_length_days:.0f} day critical path{warning_note}"
        
    except Exception as e:
        logfire.error("Error in calculate_and_display_gantt_tool", error=str(e))
        return f"Error displaying Gantt: {str(e)}"


@logfire.instrument("hide_gantt_panel_tool")
async def hide_gantt_panel_tool(ctx: RunContext[AgentDeps]) -> str:
    """Hide the Gantt panel from the UI.
    
    Use this tool when the user is done reviewing the schedule or
    switches to a different topic.
    
    Args:
        ctx: Runtime context with conversation_id in deps
    
    Returns:
        Confirmation message
    """
    try:
        # Stream hide event to frontend
        gantt_event = {
            'type': 'gantt_panel',
            'action': 'hide'
        }
        
        if hasattr(ctx.deps, 'gantt_event_queue'):
            ctx.deps.gantt_event_queue.append(gantt_event)
        
        return "Gantt panel hidden."
        
    except Exception as e:
        logfire.error("Error in hide_gantt_panel_tool", error=str(e))
        return f"Error hiding Gantt panel: {str(e)}"


@logfire.instrument("get_workspace_status_tool")
async def get_workspace_status_tool(ctx: RunContext[AgentDeps]) -> str:
    """Get the current status of the schedule workspace.
    
    Use this tool to check if a schedule is loaded and its current state.
    
    Args:
        ctx: Runtime context with conversation_id in deps
    
    Returns:
        Workspace status summary
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_to_workspace_tool to load a schedule."
        
        # Minimal response to reduce token usage
        modified = "modified" if workspace.is_modified else "unmodified"
        return f"Workspace: '{workspace.project_name}', {workspace.get_activity_count()} activities, {modified}"
        
    except Exception as e:
        logfire.error("Error in get_workspace_status_tool", error=str(e))
        return f"Error getting workspace status: {str(e)}"


# ============================================================================
# Workspace Modification Tools
# ============================================================================

@logfire.instrument("modify_activity_in_workspace_tool")
async def modify_activity_in_workspace_tool(
    ctx: RunContext[AgentDeps],
    task_id: int,
    original_duration: int | None = None,
    target_start_date: str | None = None,
    target_end_date: str | None = None,
    task_name: str | None = None
) -> str:
    """Modify an activity in the schedule workspace.
    
    Use this tool to change activity properties like duration, dates, or name
    BEFORE running calculate_and_display_gantt to see the impact.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        task_id: Task ID of the activity to modify
        original_duration: New original duration in hours (optional)
        target_start_date: New target start date in ISO format (optional)
        target_end_date: New target end date in ISO format (optional)
        task_name: New activity name (optional)
    
    Returns:
        Confirmation of changes made
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_to_workspace_tool first."
        
        # Find the activity
        mask = workspace.activities_df['task_id'] == task_id
        if not mask.any():
            return f"Activity with task_id {task_id} not found in workspace."
        
        changes = []
        
        # Apply changes
        if original_duration is not None:
            old_val = workspace.activities_df.loc[mask, 'target_drtn_hr_cnt'].values[0]
            workspace.activities_df.loc[mask, 'target_drtn_hr_cnt'] = original_duration
            changes.append(f"Duration: {old_val}h -> {original_duration}h")
        
        if target_start_date is not None:
            from datetime import datetime
            old_val = workspace.activities_df.loc[mask, 'target_start_date'].values[0]
            new_date = datetime.fromisoformat(target_start_date)
            workspace.activities_df.loc[mask, 'target_start_date'] = new_date
            changes.append(f"Target Start: {old_val} -> {new_date}")
        
        if target_end_date is not None:
            from datetime import datetime
            old_val = workspace.activities_df.loc[mask, 'target_end_date'].values[0]
            new_date = datetime.fromisoformat(target_end_date)
            workspace.activities_df.loc[mask, 'target_end_date'] = new_date
            changes.append(f"Target End: {old_val} -> {new_date}")
        
        if task_name is not None:
            old_val = workspace.activities_df.loc[mask, 'task_name'].values[0]
            workspace.activities_df.loc[mask, 'task_name'] = task_name
            changes.append(f"Name: '{old_val}' -> '{task_name}'")
        
        if not changes:
            return "No changes specified."
        
        workspace.is_modified = True
        
        task_code = workspace.activities_df.loc[mask, 'task_code'].values[0]
        # Minimal response to reduce token usage
        return f"Modified {task_code}: {', '.join(changes)}. Run calculate_and_display_gantt to see impact."
        
    except Exception as e:
        logfire.error("Error in modify_activity_in_workspace_tool", error=str(e))
        return f"Error modifying activity: {str(e)}"


@logfire.instrument("add_activity_to_workspace_tool")
async def add_activity_to_workspace_tool(
    ctx: RunContext[AgentDeps],
    task_code: str,
    task_name: str,
    original_duration_hours: int,
    wbs_id: int | None = None,
    target_start_date: str | None = None
) -> str:
    """Add a new activity to the schedule workspace.
    
    Use this tool to add activities that will be included in the next
    schedule calculation. The activity is added to the in-memory workspace
    and NOT saved to the database until explicitly requested.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        task_code: Unique activity code for the new activity
        task_name: Name of the new activity
        original_duration_hours: Duration in hours (e.g., 40 for 5 days)
        wbs_id: WBS ID to assign the activity to (optional)
        target_start_date: Target start date in ISO format (optional)
    
    Returns:
        Confirmation with the new task_id assigned
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_to_workspace_tool first."
        
        # Check if task_code already exists
        if task_code in workspace.activities_df['task_code'].values:
            return f"Activity code '{task_code}' already exists in workspace."
        
        # Generate a new task_id (negative to indicate it's new and not in DB)
        existing_ids = workspace.activities_df['task_id'].values
        min_id = min(existing_ids) if len(existing_ids) > 0 else 0
        new_task_id = min_id - 1 if min_id >= 0 else min_id - 1
        
        # Parse target start date if provided
        target_start = None
        if target_start_date:
            from datetime import datetime
            target_start = datetime.fromisoformat(target_start_date)
        
        # Create new activity row
        new_row = {
            'task_id': new_task_id,
            'task_code': task_code,
            'task_name': task_name,
            'target_drtn_hr_cnt': original_duration_hours,
            'remain_drtn_hr_cnt': original_duration_hours,
            'target_start_date': target_start,
            'target_end_date': None,
            'wbs_id': wbs_id,
            'wbs_path': None,  # Will be resolved if wbs_id provided
            'status_code': 'TK_NotStart',
            'total_float_hr_cnt': None,
            'free_float_hr_cnt': None,
        }
        
        # Add to DataFrame
        workspace.activities_df = pd.concat([
            workspace.activities_df,
            pd.DataFrame([new_row])
        ], ignore_index=True)
        
        workspace.is_modified = True
        
        # Include task_id - LLM needs it for add_relationship_to_workspace
        return f"Added '{task_code}' (task_id={new_task_id}, {original_duration_hours}h). Use task_id for relationships."
        
    except Exception as e:
        logfire.error("Error in add_activity_to_workspace_tool", error=str(e))
        return f"Error adding activity: {str(e)}"


@logfire.instrument("add_relationship_to_workspace_tool")
async def add_relationship_to_workspace_tool(
    ctx: RunContext[AgentDeps],
    predecessor_task_id: int,
    successor_task_id: int,
    relationship_type: str = "FS",
    lag_hours: int = 0
) -> str:
    """Add a relationship between activities in the workspace.
    
    Use this tool to create dependencies between activities.
    The relationship will be used in the next schedule calculation.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        predecessor_task_id: Task ID of the predecessor activity
        successor_task_id: Task ID of the successor activity
        relationship_type: FS (Finish-to-Start), SS, FF, or SF
        lag_hours: Lag time in hours (positive = delay, negative = lead)
    
    Returns:
        Confirmation of the relationship added
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_to_workspace_tool first."
        
        # Validate activities exist
        pred_exists = predecessor_task_id in workspace.activities_df['task_id'].values
        succ_exists = successor_task_id in workspace.activities_df['task_id'].values
        
        if not pred_exists:
            return f"Predecessor task_id {predecessor_task_id} not found in workspace."
        if not succ_exists:
            return f"Successor task_id {successor_task_id} not found in workspace."
        
        # Validate relationship type
        valid_types = ['FS', 'SS', 'FF', 'SF']
        if relationship_type.upper() not in valid_types:
            return f"Invalid relationship type '{relationship_type}'. Use one of: {', '.join(valid_types)}"
        
        # Check for duplicate relationship
        dup_mask = (
            (workspace.relationships_df['pred_task_id'] == predecessor_task_id) &
            (workspace.relationships_df['task_id'] == successor_task_id)
        )
        if dup_mask.any():
            return f"Relationship from {predecessor_task_id} to {successor_task_id} already exists."
        
        # Map relationship type to P6 code
        type_map = {'FS': 'PR_FS', 'SS': 'PR_SS', 'FF': 'PR_FF', 'SF': 'PR_SF'}
        pred_type = type_map[relationship_type.upper()]
        
        # Create new relationship row
        new_row = {
            'task_pred_id': len(workspace.relationships_df) + 10000,  # Temp ID
            'task_id': successor_task_id,
            'pred_task_id': predecessor_task_id,
            'pred_type': pred_type,
            'lag_hr_cnt': lag_hours,
        }
        
        # Add to DataFrame
        workspace.relationships_df = pd.concat([
            workspace.relationships_df,
            pd.DataFrame([new_row])
        ], ignore_index=True)
        
        workspace.is_modified = True
        
        # Get activity names for confirmation
        pred_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == predecessor_task_id, 'task_name'
        ].values[0]
        succ_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == successor_task_id, 'task_name'
        ].values[0]
        
        lag_str = f" + {lag_hours}h lag" if lag_hours > 0 else f" - {abs(lag_hours)}h lead" if lag_hours < 0 else ""
        
        # Minimal response to reduce token usage
        return f"Added {relationship_type}{lag_str} relationship: {pred_name} -> {succ_name}"
        
    except Exception as e:
        logfire.error("Error in add_relationship_to_workspace_tool", error=str(e))
        return f"Error adding relationship: {str(e)}"


@logfire.instrument("modify_relationship_in_workspace_tool")
async def modify_relationship_in_workspace_tool(
    ctx: RunContext[AgentDeps],
    predecessor_task_id: int,
    successor_task_id: int,
    new_relationship_type: str | None = None,
    new_lag_hours: int | None = None
) -> str:
    """Modify an existing relationship in the workspace.
    
    Use this tool to change the relationship type or lag between activities
    that are already linked in the workspace. Use this when:
    - Changing relationship type (e.g., FF to SS)
    - Adjusting lag/lead times
    
    Args:
        ctx: Runtime context with conversation_id in deps
        predecessor_task_id: Task ID of the predecessor activity
        successor_task_id: Task ID of the successor activity
        new_relationship_type: New type (FS, SS, FF, SF) - optional
        new_lag_hours: New lag in hours (positive = delay, negative = lead) - optional
    
    Returns:
        Confirmation of the relationship modification
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_to_workspace_tool first."
        
        # Find the relationship
        rel_mask = (
            (workspace.relationships_df['pred_task_id'] == predecessor_task_id) &
            (workspace.relationships_df['task_id'] == successor_task_id)
        )
        
        if not rel_mask.any():
            return f"No relationship found from task_id {predecessor_task_id} to task_id {successor_task_id}."
        
        # Get current values for reporting
        old_type = workspace.relationships_df.loc[rel_mask, 'pred_type'].values[0]
        old_lag = workspace.relationships_df.loc[rel_mask, 'lag_hr_cnt'].values[0]
        
        changes = []
        
        # Update relationship type if provided
        if new_relationship_type:
            valid_types = ['FS', 'SS', 'FF', 'SF']
            if new_relationship_type.upper() not in valid_types:
                return f"Invalid relationship type '{new_relationship_type}'. Use one of: {', '.join(valid_types)}"
            
            type_map = {'FS': 'PR_FS', 'SS': 'PR_SS', 'FF': 'PR_FF', 'SF': 'PR_SF'}
            new_pred_type = type_map[new_relationship_type.upper()]
            workspace.relationships_df.loc[rel_mask, 'pred_type'] = new_pred_type
            
            # Convert old type for display
            old_type_display = old_type.replace('PR_', '') if old_type.startswith('PR_') else old_type
            changes.append(f"type {old_type_display} -> {new_relationship_type.upper()}")
        
        # Update lag if provided
        if new_lag_hours is not None:
            workspace.relationships_df.loc[rel_mask, 'lag_hr_cnt'] = new_lag_hours
            changes.append(f"lag {old_lag}h -> {new_lag_hours}h")
        
        if not changes:
            return "No changes specified. Provide new_relationship_type or new_lag_hours."
        
        workspace.is_modified = True
        
        # Get activity names for confirmation
        pred_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == predecessor_task_id, 'task_name'
        ].values[0]
        succ_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == successor_task_id, 'task_name'
        ].values[0]
        
        return f"Modified relationship {pred_name} -> {succ_name}: {', '.join(changes)}"
        
    except Exception as e:
        logfire.error("Error in modify_relationship_in_workspace_tool", error=str(e))
        return f"Error modifying relationship: {str(e)}"

