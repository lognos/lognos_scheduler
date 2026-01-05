"""P6 database query tools - read-only operations."""

from pydantic_ai import RunContext, ModelRetry
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import (
    ActivityDetailsRequest,
    SearchActivityRequest,
    ListProjectsRequest,
    ListActivitiesRequest,
    ListActivityCodesRequest,
    GetActivityCurrentCodesRequest,
)


@logfire.instrument("get_activity_p6")
async def get_activity_p6(ctx: RunContext[AgentDeps], req: ActivityDetailsRequest) -> dict | str:
    """Get details of a specific activity from P6 database.
    
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
            raise ModelRetry(f"Activity '{req.task_code}' not found in project {req.proj_id}. Use search_activities_p6 to find the correct task code.")
        return result
    except ModelRetry:
        raise
    except Exception as e:
        logfire.error("Error in get_activity_p6", error=str(e))
        return f"Error retrieving details: {str(e)}"


@logfire.instrument("search_activities_p6")
async def search_activities_p6(ctx: RunContext[AgentDeps], req: SearchActivityRequest) -> str:
    """Search P6 activities using natural language description (vector search).
    
    Use this tool when the user refers to an activity by description rather than
    task code. Returns matching activities with their codes and similarity scores.
    
    If no results found, suggest using index_project first to index the project.
    
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
            return f"No matching activities found for '{req.query}'. Try using index_project first to index project {req.proj_id}, then search again."
        
        # Format results for the agent
        response = "Found matching activities:\n"
        for task_id, score in results:
            cursor = ctx.deps.conn.cursor()
            cursor.execute("SELECT TASK_CODE, TASK_NAME FROM TASK WHERE TASK_ID = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                response += f"- {row[0]} (task_id={task_id}): {row[1]} (Score: {score:.2f})\n"
            else:
                response += f"- task_id={task_id} (Score: {score:.2f})\n"
                
        return response
    except Exception as e:
        logfire.error("Error in search_activities_p6", error=str(e))
        return f"Error searching activities: {str(e)}"


@logfire.instrument("list_projects_p6")
async def list_projects_p6(ctx: RunContext[AgentDeps], req: ListProjectsRequest) -> str:
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
        logfire.error("Error in list_projects_p6", error=str(e))
        return f"Error listing projects: {str(e)}"


@logfire.instrument("list_activities_p6")
async def list_activities_p6(ctx: RunContext[AgentDeps], req: ListActivitiesRequest) -> str:
    """List activities in a P6 project, optionally filtered by WBS.
    
    Use this tool to:
    - List all activities in a project
    - List activities under a specific WBS element (by name or ID)
    - Show activity codes assigned to each activity
    
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
        logfire.error("Error in list_activities_p6", error=str(e))
        return f"Error listing activities: {str(e)}"


@logfire.instrument("list_activity_codes_p6")
async def list_activity_codes_p6(ctx: RunContext[AgentDeps], req: ListActivityCodesRequest) -> str:
    """List available activity code types and their values from P6.
    
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
        logfire.error("Error in list_activity_codes_p6", error=str(e))
        return f"Error listing activity codes: {str(e)}"


@logfire.instrument("get_activity_codes_p6")
async def get_activity_codes_p6(
    ctx: RunContext[AgentDeps], 
    req: GetActivityCurrentCodesRequest
) -> str:
    """Get current activity code assignments for one or more activities from P6.
    
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
        logfire.error("Error in get_activity_codes_p6", error=str(e))
        return f"Error getting current codes: {str(e)}"
