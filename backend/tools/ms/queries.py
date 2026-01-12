"""Query tools for MS Project schedules (read-only operations)."""

from datetime import date
from pydantic_ai import RunContext
import logfire

from backend.tools._base import AgentDeps
from backend.models.io import (
    ListScheduleVersionsMsRequest,
    GetScheduleOverviewMsRequest,
    ListActivitiesMsRequest,
    GetActivityMsRequest,
    GetProjectConstraintsMsRequest,
    GetCalendarMsRequest,
)


@logfire.instrument("list_schedule_versions_ms")
async def list_schedule_versions_ms(
    ctx: RunContext[AgentDeps],
    req: ListScheduleVersionsMsRequest
) -> str:
    """List all schedule versions for an MS Project.
    
    Shows available versions including baselines, current, and temporary drafts.
    Use this to understand version history before loading or comparing schedules.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with project_name and include_temp flag
        
    Returns:
        Formatted list of versions with metadata
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    try:
        versions = await ctx.deps.ms_repository.list_versions(
            project_name=req.project_name,
            include_temp=req.include_temp
        )
        
        if not versions:
            return f"No schedule versions found for project '{req.project_name}'"
        
        lines = [
            f"Schedule Versions for {req.project_name}:",
            f"{'ID':<6} {'Name':<25} {'Current':<8} {'Baseline':<9} {'Status Date':<12}",
            "-" * 70
        ]
        
        for v in versions:
            status_date = v.get('status_date', '')
            if status_date:
                status_date = status_date[:10]  # Just date part
            
            current = "YES" if v.get('is_current') else ""
            baseline = "YES" if v.get('is_baseline') else ""
            
            lines.append(
                f"{v['id']:<6} {v['version_name']:<25} {current:<8} {baseline:<9} {status_date:<12}"
            )
        
        lines.append("")
        lines.append(f"Total: {len(versions)} version(s)")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in list_schedule_versions_ms", error=str(e))
        return f"Error listing versions: {str(e)}"


@logfire.instrument("get_schedule_overview_ms")
async def get_schedule_overview_ms(
    ctx: RunContext[AgentDeps],
    req: GetScheduleOverviewMsRequest
) -> str:
    """Get 3-week lookahead schedule overview from MS Project (Supabase).
    
    Shows activities from a configurable window (default: last week + next 2 weeks),
    grouped by status. Use this to quickly understand current schedule state.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with project_name, optional version_id and date range
        
    Returns:
        Formatted overview with activity counts, critical activities, and lookahead
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    try:
        # Get version (current if not specified)
        if req.version_id:
            version = await ctx.deps.ms_repository.get_version(req.version_id)
        else:
            version = await ctx.deps.ms_repository.get_current_version(req.project_name)
        
        if not version:
            return f"No schedule found for project '{req.project_name}'"
        
        # Parse reference date
        ref_date = date.fromisoformat(req.reference_date) if req.reference_date else date.today()
        
        # Get lookahead activities
        activities = await ctx.deps.ms_repository.get_activities_lookahead(
            version_id=version['id'],
            reference_date=ref_date,
            weeks_back=req.weeks_back,
            weeks_forward=req.weeks_forward
        )
        
        # Get project constraints for status date
        constraints = await ctx.deps.ms_repository.get_project_constraints(version['id'])
        status_date = constraints.get('status_date', '')[:10] if constraints else 'N/A'
        
        # Build response
        version_label = f"{version['version_name']}"
        if version.get('is_current'):
            version_label += " (CURRENT)"
        elif version.get('is_baseline'):
            version_label += " (BASELINE)"
        else:
            version_label += " (DRAFT)"
        
        lines = [
            f"Schedule Overview: {req.project_name}",
            f"Version: {version_label}",
            f"Status Date: {status_date}",
            f"Reference: {ref_date.isoformat()}",
            f"Window: {req.weeks_back} week(s) back, {req.weeks_forward} week(s) forward",
            "",
            f"Activities in window: {len(activities)}",
        ]
        
        # Group by status
        not_started = [a for a in activities if (a.get('percent_complete') or 0) == 0 and not a.get('actual_start')]
        in_progress = [a for a in activities if a.get('actual_start') and (a.get('percent_complete') or 0) < 100]
        complete = [a for a in activities if (a.get('percent_complete') or 0) >= 100]
        
        lines.append(f"  - Not Started: {len(not_started)}")
        lines.append(f"  - In Progress: {len(in_progress)}")
        lines.append(f"  - Complete: {len(complete)}")
        
        # Critical activities
        critical = [a for a in activities if (a.get('total_float_d') or 0) == 0 and not a.get('is_summary')]
        if critical:
            lines.append("")
            lines.append(f"Critical Activities ({len(critical)}):")
            for act in critical[:10]:
                start = act.get('start', '')[:10] if act.get('start') else '?'
                finish = act.get('finish', '')[:10] if act.get('finish') else '?'
                name = act.get('name', 'Unknown')[:45]
                wbs = act.get('wbs', '')
                lines.append(f"  - {wbs}: {name} ({start} - {finish})")
            if len(critical) > 10:
                lines.append(f"  ... and {len(critical) - 10} more critical activities")
        
        # In-progress activities
        if in_progress:
            lines.append("")
            lines.append(f"In Progress ({len(in_progress)}):")
            for act in in_progress[:8]:
                pct = act.get('percent_complete', 0)
                name = act.get('name', 'Unknown')[:40]
                wbs = act.get('wbs', '')
                lines.append(f"  - {wbs}: {name} ({pct:.0f}%)")
            if len(in_progress) > 8:
                lines.append(f"  ... and {len(in_progress) - 8} more in progress")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in get_schedule_overview_ms", error=str(e))
        return f"Error: {str(e)}"


@logfire.instrument("list_activities_ms")
async def list_activities_ms(
    ctx: RunContext[AgentDeps],
    req: ListActivitiesMsRequest
) -> str:
    """List activities from MS Project schedule with filters.
    
    Supports filtering by WBS prefix, date range, status, criticality, and owner.
    Results are paginated.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with version_id and filter criteria
        
    Returns:
        Formatted list of activities matching filters
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    try:
        # Apply status filter logic
        activities = await ctx.deps.ms_repository.get_activities_by_version(
            version_id=req.version_id,
            limit=req.limit,
            offset=req.offset,
            wbs_prefix=req.wbs_prefix,
            critical_only=req.critical_only,
            owner=req.owner,
            scope_owner=req.scope_owner,
            include_summary=False
        )
        
        # Additional status filtering
        if req.status:
            filtered = []
            for a in activities:
                pct = a.get('percent_complete') or 0
                has_start = a.get('actual_start') is not None
                
                if req.status == "not_started" and pct == 0 and not has_start:
                    filtered.append(a)
                elif req.status == "in_progress" and has_start and pct < 100:
                    filtered.append(a)
                elif req.status == "complete" and pct >= 100:
                    filtered.append(a)
            activities = filtered
        
        # Date filtering
        if req.date_start:
            start_filter = req.date_start
            activities = [a for a in activities if (a.get('start') or '') >= start_filter]
        
        if req.date_end:
            end_filter = req.date_end
            activities = [a for a in activities if (a.get('finish') or '') <= end_filter]
        
        if not activities:
            return "No activities match the specified filters."
        
        # Format output
        lines = [
            f"Activities (showing {len(activities)}, offset {req.offset}):",
            f"{'WBS':<12} {'Name':<35} {'Start':<12} {'Finish':<12} {'%':<5} {'Float':<6}",
            "-" * 90
        ]
        
        for a in activities:
            wbs = (a.get('wbs') or '')[:11]
            name = (a.get('name') or 'Unknown')[:34]
            start = (a.get('start') or '')[:10]
            finish = (a.get('finish') or '')[:10]
            pct = a.get('percent_complete') or 0
            float_d = a.get('total_float_d')
            float_str = f"{float_d:.0f}d" if float_d is not None else "-"
            
            lines.append(f"{wbs:<12} {name:<35} {start:<12} {finish:<12} {pct:<5.0f} {float_str:<6}")
        
        if len(activities) == req.limit:
            lines.append("")
            lines.append(f"More results available. Use offset={req.offset + req.limit} to see next page.")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in list_activities_ms", error=str(e))
        return f"Error: {str(e)}"


@logfire.instrument("get_activity_ms")
async def get_activity_ms(
    ctx: RunContext[AgentDeps],
    req: GetActivityMsRequest
) -> str:
    """Get detailed information for a single activity.
    
    Can look up by internal ID or MS Project UID (requires version_id).
    Shows all activity fields including relationships.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with activity_id or ms_uid+version_id
        
    Returns:
        Detailed activity information
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    if not req.activity_id and not (req.ms_uid and req.version_id):
        return "Error: Provide either activity_id or both ms_uid and version_id"
    
    try:
        # Fetch activity
        if req.activity_id:
            activity = await ctx.deps.ms_repository.get_activity_by_id(req.activity_id)
        else:
            activity = await ctx.deps.ms_repository.get_activity_by_ms_uid(
                version_id=req.version_id,
                ms_uid=req.ms_uid
            )
        
        if not activity:
            return "Activity not found."
        
        # Get relationships
        rels = await ctx.deps.ms_repository.get_relationships_for_activity(activity['id'])
        
        # Format output
        lines = [
            f"Activity Details: {activity.get('name', 'Unknown')}",
            "-" * 50,
            f"ID: {activity['id']}",
            f"MS UID: {activity.get('ms_uid')}",
            f"WBS: {activity.get('wbs')}",
            f"Name (Verbose): {activity.get('name_verbose', '-')}",
            "",
            "Schedule:",
            f"  Start: {activity.get('start', '-')}",
            f"  Finish: {activity.get('finish', '-')}",
            f"  Duration: {activity.get('duration_d', '-')} days",
            f"  Total Float: {activity.get('total_float_d', '-')} days",
            "",
            "Progress:",
            f"  % Complete: {activity.get('percent_complete', 0)}%",
            f"  Actual Start: {activity.get('actual_start', '-')}",
            f"  Actual Finish: {activity.get('actual_finish', '-')}",
        ]
        
        # Constraint info
        if activity.get('constraint_type'):
            lines.append("")
            lines.append("Constraint:")
            lines.append(f"  Type: {activity.get('constraint_type')}")
            lines.append(f"  Date: {activity.get('constraint_date', '-')}")
        
        if activity.get('deadline_date'):
            lines.append(f"  Deadline: {activity.get('deadline_date')}")
        
        # Baseline info
        if activity.get('baseline_start') or activity.get('baseline_finish'):
            lines.append("")
            lines.append("Baseline:")
            lines.append(f"  Start: {activity.get('baseline_start', '-')}")
            lines.append(f"  Finish: {activity.get('baseline_finish', '-')}")
            lines.append(f"  Duration: {activity.get('baseline_duration_d', '-')} days")
        
        # Owner info
        if activity.get('owner') or activity.get('scope_owner'):
            lines.append("")
            lines.append("Assignments:")
            if activity.get('owner'):
                lines.append(f"  Owner: {activity.get('owner')}")
            if activity.get('scope_owner'):
                lines.append(f"  Scope Owner: {activity.get('scope_owner')}")
        
        # Relationships
        preds = rels.get('predecessors', [])
        succs = rels.get('successors', [])
        
        if preds:
            lines.append("")
            lines.append(f"Predecessors ({len(preds)}):")
            for r in preds[:5]:
                pred = r.get('pred', {})
                lag = r.get('lag_d', 0)
                lag_str = f" +{lag}d" if lag else ""
                lines.append(f"  - {pred.get('wbs', '?')}: {pred.get('name', '?')[:30]} ({r.get('rel_type', 'FS')}{lag_str})")
        
        if succs:
            lines.append("")
            lines.append(f"Successors ({len(succs)}):")
            for r in succs[:5]:
                succ = r.get('succ', {})
                lag = r.get('lag_d', 0)
                lag_str = f" +{lag}d" if lag else ""
                lines.append(f"  - {succ.get('wbs', '?')}: {succ.get('name', '?')[:30]} ({r.get('rel_type', 'FS')}{lag_str})")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in get_activity_ms", error=str(e))
        return f"Error: {str(e)}"


@logfire.instrument("get_project_constraints_ms")
async def get_project_constraints_ms(
    ctx: RunContext[AgentDeps],
    req: GetProjectConstraintsMsRequest
) -> str:
    """Get project constraints including status date and scheduling direction.
    
    Returns project-level scheduling parameters like start/finish dates,
    status date (data date), and forward/backward scheduling direction.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with version_id
        
    Returns:
        Project constraint information
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    try:
        constraints = await ctx.deps.ms_repository.get_project_constraints(req.version_id)
        
        if not constraints:
            return f"No project constraints found for version {req.version_id}"
        
        lines = [
            f"Project Constraints (Version {req.version_id}):",
            "-" * 40,
            f"Project Start: {constraints.get('project_start_date', '-')}",
            f"Project Finish: {constraints.get('project_finish_date', '-')}",
            f"Status Date: {constraints.get('status_date', '-')}",
            f"Schedule From: {'Start (Forward)' if constraints.get('schedule_from_start') else 'Finish (Backward)'}",
        ]
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in get_project_constraints_ms", error=str(e))
        return f"Error: {str(e)}"


@logfire.instrument("get_calendar_ms")
async def get_calendar_ms(
    ctx: RunContext[AgentDeps],
    req: GetCalendarMsRequest
) -> str:
    """Get calendar information including exceptions.
    
    Returns working days/hours configuration and any calendar exceptions
    (holidays, non-working days).
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with version_id
        
    Returns:
        Calendar configuration and exceptions
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available. Check configuration."
    
    try:
        cal_info = await ctx.deps.ms_repository.get_calendar(req.version_id)
        
        cal = cal_info.get('calendar')
        if not cal:
            return f"No calendar found for version {req.version_id}"
        
        lines = [
            f"Calendar: {cal.get('calendar_name', 'Unknown')}",
            "-" * 40,
            f"Working Days/Week: {cal.get('working_days_per_week', '-')}",
            f"Working Hours/Day: {cal.get('working_hours_per_day', '-')}",
            f"Base Calendar: {'Yes' if cal.get('is_base_calendar') else 'No'}",
        ]
        
        exceptions = cal_info.get('exceptions', [])
        if exceptions:
            lines.append("")
            lines.append(f"Exceptions ({len(exceptions)}):")
            for exc in exceptions[:15]:
                exc_date = exc.get('exception_date', '')[:10]
                is_work = "Working" if exc.get('is_working_day') else "Non-working"
                exc_type = exc.get('exception_type', '')
                hours = exc.get('working_hours', '')
                
                detail = f"{exc_type}" if exc_type else is_work
                if hours and exc.get('is_working_day'):
                    detail += f" ({hours}h)"
                
                lines.append(f"  - {exc_date}: {detail}")
            
            if len(exceptions) > 15:
                lines.append(f"  ... and {len(exceptions) - 15} more exceptions")
        else:
            lines.append("")
            lines.append("No calendar exceptions defined.")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in get_calendar_ms", error=str(e))
        return f"Error: {str(e)}"
