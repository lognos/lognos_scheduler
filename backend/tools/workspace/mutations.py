"""Workspace mutation tools - operations that modify the in-memory workspace."""

from datetime import datetime
import pandas as pd
import logfire
from pydantic_ai import RunContext
from backend.tools._base import AgentDeps
from backend.services.schedule_state import schedule_state_manager


@logfire.instrument("load_schedule_ws")
async def load_schedule_ws(
    ctx: RunContext[AgentDeps],
    proj_id: int
) -> str:
    """Load a P6 project schedule into the workspace for analysis.
    
    This creates an in-memory copy of the schedule that can be modified
    and recalculated without affecting the P6 database.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        proj_id: The P6 project ID to load
    
    Returns:
        Summary of loaded activities and relationships
    """
    try:
        conversation_id = ctx.deps.conversation_id
        if not conversation_id:
            return "Error: No conversation_id available. Cannot load workspace."
        
        # Load schedule data from P6 via service
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
        
        # Minimal response to reduce token usage
        activity_count = len(workspace.activities_df)
        return f"Loaded '{project_info.get('project_name', 'Unknown')}': {activity_count} activities. Use calculate_gantt_ws to see Gantt chart."
        
    except ValueError as e:
        return f"Error loading schedule: {e}"
    except Exception as e:
        logfire.error("Error in load_schedule_ws", error=str(e))
        return f"Error loading schedule: {str(e)}"


@logfire.instrument("calculate_gantt_ws")
async def calculate_gantt_ws(
    ctx: RunContext[AgentDeps],
    title: str = "Schedule Analysis",
    group_by: str | None = None,
    show_details: bool = True
) -> str:
    """Calculate CPM schedule and display Gantt chart with optional grouping.
    
    Runs the Critical Path Method algorithm on the workspace data and
    sends a Gantt chart visualization to the frontend panel.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        title: Title for the Gantt chart display
        group_by: Optional grouping field. Use 'wbs' to group by WBS path,
                  or an activity code type name (e.g., 'Phase', 'Discipline')
                  to group activities by that code. When set, creates summary
                  bars that span their child activities.
        show_details: If True (default), show both summary and detail activities.
                     If False, show only summary level (Level 1).
    
    Returns:
        Summary of calculation results including critical path
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
        if workspace.activities_df.empty:
            return "Schedule workspace is empty. Load a schedule first."
        
        # Import here to avoid circular imports
        from backend.services.network_calculator import NetworkCalculator, ScheduleValidationError
        
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
        
        # Build Gantt data for frontend
        hours_per_day = 8.0  # Standard P6 calendar assumption
        
        def build_activity_item(row: pd.Series, level: int = 2, parent_id: str | None = None) -> dict:
            """Build a Gantt item dict from a DataFrame row."""
            duration_hours = float(row.get('target_drtn_hr_cnt', 0)) if pd.notna(row.get('target_drtn_hr_cnt')) else 0
            working_days = duration_hours / hours_per_day
            
            early_start = row.get('early_start')
            early_finish = row.get('early_finish')
            if pd.notna(early_start) and pd.notna(early_finish):
                calendar_days = (early_finish - early_start).days + 1
            else:
                calendar_days = 0
            
            return {
                'id': int(row['task_id']),
                's_item_id': row['task_code'],
                's_item': row['task_name'],
                'working_days': working_days,
                'calendar_days': calendar_days,
                'total_float': float(row.get('total_float_days', 0)) if pd.notna(row.get('total_float_days')) else 0,
                'start': early_start.isoformat() if pd.notna(early_start) else '',
                'finish': early_finish.isoformat() if pd.notna(early_finish) else '',
                'is_critical': bool(row.get('is_critical', False)),
                'wbs_path': row.get('wbs_path', ''),
                'status': row.get('status', 'not_started'),
                'level': level,
                'is_summary': False,
                'parent_id': parent_id,
                'children_count': 0,
                'group_name': None,
            }
        
        gantt_items = []
        grouping_applied = None
        
        if group_by:
            # Determine grouping source
            if group_by.lower() == 'wbs':
                # Group by WBS path (use first segment as group)
                grouping_applied = 'WBS'
                groups: dict[str, list[int]] = {}
                for _, row in workspace.activities_df.iterrows():
                    wbs_path = row.get('wbs_path', '') or ''
                    # Use first WBS segment as group, or "Ungrouped" if empty
                    group_key = wbs_path.split('/')[0] if wbs_path else 'Ungrouped'
                    if group_key not in groups:
                        groups[group_key] = []
                    groups[group_key].append(int(row['task_id']))
            else:
                # Group by activity code type
                grouping_applied = group_by
                groups = {}
                
                if not workspace.activity_codes_df.empty:
                    # Find activities with this code type
                    code_mask = workspace.activity_codes_df['code_type_name'].str.lower() == group_by.lower()
                    codes_for_type = workspace.activity_codes_df[code_mask]
                    
                    for _, code_row in codes_for_type.iterrows():
                        group_key = code_row.get('code_value_name', 'Unknown')
                        task_id = int(code_row['task_id'])
                        if group_key not in groups:
                            groups[group_key] = []
                        groups[group_key].append(task_id)
                    
                    # Find activities without this code type
                    assigned_task_ids = set(codes_for_type['task_id'].tolist())
                    all_task_ids = set(workspace.activities_df['task_id'].tolist())
                    unassigned = all_task_ids - assigned_task_ids
                    if unassigned:
                        groups['Unassigned'] = list(unassigned)
                else:
                    # No activity codes - all activities are unassigned
                    groups['Unassigned'] = workspace.activities_df['task_id'].tolist()
            
            # Build hierarchical items: summary bars + optional details
            summary_id_counter = -1000  # Use negative IDs for synthetic summary items
            
            for group_name, task_ids in sorted(groups.items()):
                if not task_ids:
                    continue
                    
                # Get activities in this group
                group_df = workspace.activities_df[workspace.activities_df['task_id'].isin(task_ids)]
                
                if group_df.empty:
                    continue
                
                # Calculate summary bar dates (min start, max finish)
                valid_starts = group_df['early_start'].dropna()
                valid_finishes = group_df['early_finish'].dropna()
                
                if valid_starts.empty or valid_finishes.empty:
                    continue
                
                summary_start = valid_starts.min()
                summary_finish = valid_finishes.max()
                summary_calendar_days = (summary_finish - summary_start).days + 1
                
                # Sum working days for summary
                total_working_hours = group_df['target_drtn_hr_cnt'].fillna(0).sum()
                summary_working_days = float(total_working_hours) / hours_per_day
                
                # Check if any child is critical
                any_critical = group_df['is_critical'].any() if 'is_critical' in group_df.columns else False
                
                parent_id_str = f"summary-{summary_id_counter}"
                
                # Create summary item (Level 1)
                summary_item = {
                    'id': summary_id_counter,
                    's_item_id': f"GRP-{group_name[:8].upper()}",
                    's_item': group_name,
                    'working_days': summary_working_days,
                    'calendar_days': summary_calendar_days,
                    'total_float': 0,  # Summary bars don't have float
                    'start': summary_start.isoformat(),
                    'finish': summary_finish.isoformat(),
                    'is_critical': bool(any_critical),
                    'wbs_path': '',
                    'status': 'not_started',  # Could compute from children
                    'level': 1,
                    'is_summary': True,
                    'parent_id': None,
                    'children_count': len(task_ids),
                    'group_name': group_name,
                }
                gantt_items.append(summary_item)
                
                # Add detail items (Level 2) if requested
                if show_details:
                    for _, row in group_df.iterrows():
                        detail_item = build_activity_item(row, level=2, parent_id=parent_id_str)
                        detail_item['group_name'] = group_name
                        gantt_items.append(detail_item)
                
                summary_id_counter -= 1
        else:
            # No grouping - flat list (all Level 2)
            for _, row in workspace.activities_df.iterrows():
                gantt_items.append(build_activity_item(row))
        
        # Stream Gantt panel event to frontend
        gantt_event = {
            'type': 'gantt_panel',
            'action': 'show',
            'data': {
                'items': gantt_items,
                'project_start': result.project_start.isoformat(),
                'project_finish': result.project_finish.isoformat(),
                'critical_path_length': result.critical_path_length_days,
                'filter_applied': {
                    'wbs_path': None,
                    'critical_only': False,
                    'activity_codes': None,
                    'status': None,
                    'search_term': None,
                },
                'total_activities': len(workspace.activities_df),
                'filtered_activities': len([i for i in gantt_items if not i.get('is_summary')]),
                'available_activity_codes': workspace.code_types_with_values,
                'grouping': grouping_applied,
            }
        }
        
        # Store event for streaming (will be picked up by chat router)
        if ctx.deps.gantt_event_queue is not None:
            ctx.deps.gantt_event_queue.append(gantt_event)
        
        # Return summary message
        warning_note = f" ({len(result.warnings)} warnings)" if result.warnings else ""
        grouping_note = f" grouped by {grouping_applied}" if grouping_applied else ""
        summary_count = len([i for i in gantt_items if i.get('is_summary')])
        detail_count = len([i for i in gantt_items if not i.get('is_summary')])
        
        if grouping_applied:
            return f"Gantt displayed: {summary_count} groups, {detail_count} activities{grouping_note}, {result.critical_path_length_days:.0f} day critical path{warning_note}"
        else:
            return f"Gantt displayed: {detail_count} activities, {result.critical_path_length_days:.0f} day critical path{warning_note}"
        
    except Exception as e:
        logfire.error("Error in calculate_gantt_ws", error=str(e))
        return f"Error calculating schedule: {str(e)}"


@logfire.instrument("modify_activity_ws")
async def modify_activity_ws(
    ctx: RunContext[AgentDeps],
    task_id: int,
    original_duration: int | None = None,
    target_start_date: str | None = None,
    target_end_date: str | None = None,
    task_name: str | None = None
) -> str:
    """Modify an activity in the schedule workspace.
    
    Use this tool to change activity properties like duration, dates, or name
    BEFORE running calculate_gantt_ws to see the impact.
    
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
            return "No schedule workspace active. Use load_schedule_ws first."
        
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
            old_val = workspace.activities_df.loc[mask, 'target_start_date'].values[0]
            new_date = datetime.fromisoformat(target_start_date)
            workspace.activities_df.loc[mask, 'target_start_date'] = new_date
            changes.append(f"Target Start: {old_val} -> {new_date}")
        
        if target_end_date is not None:
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
        return f"Modified {task_code}: {', '.join(changes)}. Run calculate_gantt_ws to see impact."
        
    except Exception as e:
        logfire.error("Error in modify_activity_ws", error=str(e))
        return f"Error modifying activity: {str(e)}"


@logfire.instrument("add_activity_ws")
async def add_activity_ws(
    ctx: RunContext[AgentDeps],
    task_code: str,
    task_name: str,
    original_duration_hours: int,
    wbs_id: int | None = None,
    target_start_date: str | None = None,
    activity_codes: dict[str, str] | None = None
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
        activity_codes: Dict mapping code type name to code value (optional)
                       Example: {"Phase": "Phase 1", "Discipline": "Civil"}
                       Used for grouping activities in calculate_gantt_ws
    
    Returns:
        Confirmation with the new task_id assigned
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
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
        
        # Add activity codes if provided (for grouping in calculate_gantt_ws)
        if activity_codes:
            code_rows = [
                {
                    'task_id': new_task_id,
                    'code_type_name': code_type,
                    'code_value_name': code_value
                }
                for code_type, code_value in activity_codes.items()
            ]
            workspace.activity_codes_df = pd.concat([
                workspace.activity_codes_df,
                pd.DataFrame(code_rows)
            ], ignore_index=True)
        
        workspace.is_modified = True
        
        # Include task_id - LLM needs it for add_relationship_ws
        codes_info = f", codes={activity_codes}" if activity_codes else ""
        return f"Added '{task_code}' (task_id={new_task_id}, {original_duration_hours}h{codes_info}). Use task_id for relationships."
        
    except Exception as e:
        logfire.error("Error in add_activity_ws", error=str(e))
        return f"Error adding activity: {str(e)}"


@logfire.instrument("add_relationship_ws")
async def add_relationship_ws(
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
            return "No schedule workspace active. Use load_schedule_ws first."
        
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
        logfire.error("Error in add_relationship_ws", error=str(e))
        return f"Error adding relationship: {str(e)}"


@logfire.instrument("modify_relationship_ws")
async def modify_relationship_ws(
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
            return "No schedule workspace active. Use load_schedule_ws first."
        
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
        logfire.error("Error in modify_relationship_ws", error=str(e))
        return f"Error modifying relationship: {str(e)}"


@logfire.instrument("hide_gantt_ws")
async def hide_gantt_ws(ctx: RunContext[AgentDeps]) -> str:
    """Hide the Gantt panel on the frontend.
    
    Use this tool when the user is done viewing the Gantt chart and wants
    to dismiss the panel. This does not clear the workspace data.
    
    Returns:
        Confirmation that hide command was sent
    """
    try:
        if ctx.deps.gantt_event_queue is not None:
            hide_event = {
                'type': 'gantt_hide',
                'data': {}
            }
            ctx.deps.gantt_event_queue.append(hide_event)
            return "Gantt panel hidden."
        else:
            return "No event queue available to send hide command."
            
    except Exception as e:
        logfire.error("Error in hide_gantt_ws", error=str(e))
        return f"Error hiding gantt panel: {str(e)}"


@logfire.instrument("create_schedule_ws")
async def create_schedule_ws(
    ctx: RunContext[AgentDeps],
    project_name: str,
    project_start_date: str | None = None,
    description: str | None = None
) -> str:
    """Create a new empty schedule workspace for draft planning.
    
    Use this tool to start building a schedule from scratch WITHOUT
    creating anything in the P6 database. Perfect for:
    - Draft schedules for review before committing to P6
    - What-if analysis and exploration
    - Building schedules collaboratively before approval
    
    The schedule exists only in the workspace until explicitly saved
    to P6 using save_schedule_p6 (future capability).
    
    Args:
        ctx: Runtime context with conversation_id in deps
        project_name: Name for the new schedule (e.g., "2km Trail Construction")
        project_start_date: Planned start date in ISO format (YYYY-MM-DD). 
                           Used as reference for CPM calculation.
        description: Optional description of the schedule purpose (stored for 
                    future save to P6)
    
    Returns:
        Confirmation that workspace is ready for adding activities
    
    Example workflow:
        1. create_schedule_ws("2km Trail Construction", "2025-01-15")
        2. add_activity_ws(...) - add activities
        3. add_relationship_ws(...) - add dependencies
        4. calculate_gantt_ws() - run CPM and view Gantt
        5. (future) save_schedule_p6() - persist to P6 database
    """
    try:
        conversation_id = ctx.deps.conversation_id
        if not conversation_id:
            return "Error: No conversation_id available. Cannot create workspace."
        
        # Check if workspace already exists
        existing = schedule_state_manager.get(conversation_id)
        if existing:
            return (
                f"A workspace already exists with {len(existing.activities_df)} activities "
                f"(project: '{existing.project_name}'). "
                "Use clear_schedule_ws first to start fresh, or continue adding to the existing schedule."
            )
        
        # Parse project start date
        project_start = None
        if project_start_date:
            try:
                project_start = pd.to_datetime(project_start_date).date()
            except Exception:
                return f"Invalid date format: '{project_start_date}'. Use ISO format (YYYY-MM-DD)."
        
        # Create empty workspace using the state manager
        workspace = schedule_state_manager.create_new(
            conversation_id=conversation_id,
            project_name=project_name
        )
        
        # Set project start if provided (used by CPM calculation)
        if project_start:
            workspace.project_start = project_start
        
        # Store description as metadata for future P6 save
        # The ScheduleWorkspace dataclass can be extended later to include this
        # For now, we acknowledge it in the response
        
        logfire.info(
            "Created new draft schedule workspace",
            conversation_id=conversation_id,
            project_name=project_name,
            project_start=project_start_date,
            has_description=bool(description)
        )
        
        start_info = f" starting {project_start_date}" if project_start_date else ""
        return (
            f"Created draft schedule '{project_name}'{start_info}. "
            "Add activities with add_activity_ws, then link them with add_relationship_ws. "
            "Use calculate_gantt_ws to visualize and analyze the schedule."
        )
        
    except Exception as e:
        logfire.error("Error in create_schedule_ws", error=str(e))
        return f"Error creating schedule workspace: {str(e)}"


@logfire.instrument("assign_activity_codes_ws")
async def assign_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    task_id: int,
    code_assignments: dict[str, str]
) -> str:
    """Assign or modify activity codes for an activity in the workspace.
    
    Use this tool to categorize activities with codes like Phase, Discipline, Area, etc.
    Each activity can have one code per code type - assigning a new code replaces
    any existing value for that type.
    
    This modifies the workspace (in-memory) only. Changes are NOT saved to P6
    until the schedule is persisted.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        task_id: Task ID of the activity to assign codes to
        code_assignments: Dict mapping code type name to code value name.
                         Example: {"Activity_Type": "Stations construction", "Phase": "Phase 1"}
                         Use the exact names as shown in the Gantt grouping options.
    
    Returns:
        Summary of assigned and replaced codes
    
    Example:
        assign_activity_codes_ws(task_id=12345, code_assignments={"Activity_Type": "Trail construction"})
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
        # Validate activity exists
        if task_id not in workspace.activities_df['task_id'].values:
            return f"Activity with task_id {task_id} not found in workspace."
        
        # Get activity info for response
        task_mask = workspace.activities_df['task_id'] == task_id
        task_code = workspace.activities_df.loc[task_mask, 'task_code'].values[0]
        
        assigned = []
        replaced = []
        errors = []
        
        for code_type, code_value in code_assignments.items():
            # Validate code type exists
            if workspace.code_types_with_values:
                # Find matching code type (case-insensitive)
                matching_type = None
                for available_type in workspace.code_types_with_values.keys():
                    if available_type.lower() == code_type.lower():
                        matching_type = available_type
                        break
                
                if not matching_type:
                    available_types = list(workspace.code_types_with_values.keys())
                    errors.append(f"Code type '{code_type}' not found. Available: {available_types}")
                    continue
                
                # Validate code value exists for this type
                available_values = workspace.code_types_with_values.get(matching_type, [])
                matching_value = None
                for available_value in available_values:
                    if available_value.lower() == code_value.lower():
                        matching_value = available_value
                        break
                
                if not matching_value:
                    errors.append(f"Code value '{code_value}' not found in type '{matching_type}'. Available: {available_values}")
                    continue
                
                # Use the correctly-cased names
                code_type = matching_type
                code_value = matching_value
            
            # Check if this task already has a code for this type
            existing_mask = (
                (workspace.activity_codes_df['task_id'] == task_id) &
                (workspace.activity_codes_df['code_type_name'] == code_type)
            )
            
            if existing_mask.any():
                # Get old value for reporting
                old_value = workspace.activity_codes_df.loc[existing_mask, 'code_value_name'].values[0]
                
                if old_value != code_value:
                    # Update existing assignment
                    workspace.activity_codes_df.loc[existing_mask, 'code_value_name'] = code_value
                    replaced.append({
                        'code_type': code_type,
                        'old_value': old_value,
                        'new_value': code_value
                    })
                # else: same value, no change needed
            else:
                # Add new assignment
                new_row = pd.DataFrame([{
                    'task_id': task_id,
                    'code_type_name': code_type,
                    'code_value_name': code_value
                }])
                workspace.activity_codes_df = pd.concat([
                    workspace.activity_codes_df,
                    new_row
                ], ignore_index=True)
                assigned.append({
                    'code_type': code_type,
                    'code_value': code_value
                })
        
        # Mark workspace as modified if any changes were made
        if assigned or replaced:
            workspace.mark_modified()
        
        # Build response
        lines = [f"Activity code results for '{task_code}' (task_id={task_id}):", ""]
        
        if assigned:
            lines.append("Assigned:")
            for a in assigned:
                lines.append(f"  - {a['code_type']}: {a['code_value']}")
        
        if replaced:
            lines.append("")
            lines.append("Replaced:")
            for r in replaced:
                lines.append(f"  - {r['code_type']}: {r['old_value']} -> {r['new_value']}")
        
        if errors:
            lines.append("")
            lines.append("Errors:")
            for e in errors:
                lines.append(f"  - {e}")
        
        if not assigned and not replaced and not errors:
            lines.append("No changes made (values already match).")
        
        if assigned or replaced:
            lines.append("")
            lines.append("Run calculate_gantt_ws to see updated grouping.")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in assign_activity_codes_ws", error=str(e))
        return f"Error assigning activity codes: {str(e)}"


@logfire.instrument("bulk_assign_activity_codes_ws")
async def bulk_assign_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    task_ids: list[int],
    code_assignments: dict[str, str]
) -> str:
    """Assign activity codes to multiple activities at once in the workspace.
    
    Use this tool for efficient bulk updates when multiple activities need
    the same code assignments. Each activity can have one code per code type.
    
    This modifies the workspace (in-memory) only. Changes are NOT saved to P6
    until the schedule is persisted.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        task_ids: List of Task IDs to assign codes to
        code_assignments: Dict mapping code type name to code value name.
                         Example: {"Activity_Type": "Trail construction", "Phase": "Phase 1"}
    
    Returns:
        Summary with counts of assigned/replaced codes
    
    Example:
        bulk_assign_activity_codes_ws(
            task_ids=[12345, 12346, 12347],
            code_assignments={"Activity_Type": "Stations construction"}
        )
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
        if not task_ids:
            return "No task_ids provided."
        
        # Validate all activities exist
        existing_task_ids = set(workspace.activities_df['task_id'].values)
        missing = [tid for tid in task_ids if tid not in existing_task_ids]
        if missing:
            return f"Activities not found in workspace: {missing[:10]}{'...' if len(missing) > 10 else ''}"
        
        # Validate code types and values once
        validated_assignments: dict[str, str] = {}
        errors = []
        
        for code_type, code_value in code_assignments.items():
            if workspace.code_types_with_values:
                # Find matching code type (case-insensitive)
                matching_type = None
                for available_type in workspace.code_types_with_values.keys():
                    if available_type.lower() == code_type.lower():
                        matching_type = available_type
                        break
                
                if not matching_type:
                    available_types = list(workspace.code_types_with_values.keys())
                    errors.append(f"Code type '{code_type}' not found. Available: {available_types}")
                    continue
                
                # Validate code value exists for this type
                available_values = workspace.code_types_with_values.get(matching_type, [])
                matching_value = None
                for available_value in available_values:
                    if available_value.lower() == code_value.lower():
                        matching_value = available_value
                        break
                
                if not matching_value:
                    errors.append(f"Code value '{code_value}' not found in type '{matching_type}'. Available: {available_values}")
                    continue
                
                validated_assignments[matching_type] = matching_value
            else:
                # No validation data - accept as-is
                validated_assignments[code_type] = code_value
        
        if errors:
            return "Validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
        
        # Apply assignments to all tasks
        total_assigned = 0
        total_replaced = 0
        
        for task_id in task_ids:
            for code_type, code_value in validated_assignments.items():
                # Check if this task already has a code for this type
                existing_mask = (
                    (workspace.activity_codes_df['task_id'] == task_id) &
                    (workspace.activity_codes_df['code_type_name'] == code_type)
                )
                
                if existing_mask.any():
                    old_value = workspace.activity_codes_df.loc[existing_mask, 'code_value_name'].values[0]
                    if old_value != code_value:
                        workspace.activity_codes_df.loc[existing_mask, 'code_value_name'] = code_value
                        total_replaced += 1
                else:
                    new_row = pd.DataFrame([{
                        'task_id': task_id,
                        'code_type_name': code_type,
                        'code_value_name': code_value
                    }])
                    workspace.activity_codes_df = pd.concat([
                        workspace.activity_codes_df,
                        new_row
                    ], ignore_index=True)
                    total_assigned += 1
        
        # Mark workspace as modified
        if total_assigned > 0 or total_replaced > 0:
            workspace.mark_modified()
        
        codes_summary = ", ".join(f"{k}={v}" for k, v in validated_assignments.items())
        return (
            f"Bulk assignment completed for {len(task_ids)} activities:\n"
            f"  Codes: {codes_summary}\n"
            f"  New assignments: {total_assigned}\n"
            f"  Replaced: {total_replaced}\n\n"
            "Run calculate_gantt_ws to see updated grouping."
        )
        
    except Exception as e:
        logfire.error("Error in bulk_assign_activity_codes_ws", error=str(e))
        return f"Error in bulk assignment: {str(e)}"


@logfire.instrument("remove_activity_codes_ws")
async def remove_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    task_id: int,
    code_type_names: list[str]
) -> str:
    """Remove activity code assignments from an activity in the workspace.
    
    Use this tool to unassign codes from an activity. Specify which code types
    to remove (e.g., ['Phase', 'Discipline']).
    
    This modifies the workspace (in-memory) only. Changes are NOT saved to P6
    until the schedule is persisted.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        task_id: Task ID of the activity to remove codes from
        code_type_names: List of code type names to remove (e.g., ['Activity_Type', 'Phase'])
    
    Returns:
        Summary of removed codes and any code types that weren't assigned
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
        # Validate activity exists
        if task_id not in workspace.activities_df['task_id'].values:
            return f"Activity with task_id {task_id} not found in workspace."
        
        # Get activity info for response
        task_mask = workspace.activities_df['task_id'] == task_id
        task_code = workspace.activities_df.loc[task_mask, 'task_code'].values[0]
        
        removed = []
        not_found = []
        
        for code_type in code_type_names:
            # Find matching code type (case-insensitive)
            matching_type = code_type
            if workspace.code_types_with_values:
                for available_type in workspace.code_types_with_values.keys():
                    if available_type.lower() == code_type.lower():
                        matching_type = available_type
                        break
            
            # Find and remove the assignment
            remove_mask = (
                (workspace.activity_codes_df['task_id'] == task_id) &
                (workspace.activity_codes_df['code_type_name'].str.lower() == matching_type.lower())
            )
            
            if remove_mask.any():
                removed_value = workspace.activity_codes_df.loc[remove_mask, 'code_value_name'].values[0]
                workspace.activity_codes_df = workspace.activity_codes_df[~remove_mask]
                removed.append({
                    'code_type': matching_type,
                    'removed_value': removed_value
                })
            else:
                not_found.append(code_type)
        
        # Mark workspace as modified if any codes were removed
        if removed:
            workspace.mark_modified()
        
        # Build response
        lines = [f"Removal results for '{task_code}' (task_id={task_id}):", ""]
        
        if removed:
            lines.append("Removed:")
            for r in removed:
                lines.append(f"  - {r['code_type']}: {r['removed_value']}")
        
        if not_found:
            lines.append("")
            lines.append("Not found/not assigned:")
            for nf in not_found:
                lines.append(f"  - {nf}")
        
        if not removed and not not_found:
            lines.append("No codes were removed.")
        
        if removed:
            lines.append("")
            lines.append("Run calculate_gantt_ws to see updated grouping.")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in remove_activity_codes_ws", error=str(e))
        return f"Error removing activity codes: {str(e)}"


@logfire.instrument("get_activity_codes_ws")
async def get_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    task_id: int | None = None
) -> str:
    """Get current activity code assignments in the workspace.
    
    Use this tool to see what codes are currently assigned to activities.
    Can query a specific activity or get a summary of all codes.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        task_id: Optional Task ID to get codes for. If None, returns summary of all codes.
    
    Returns:
        Current activity code assignments
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
        if workspace.activity_codes_df.empty:
            return "No activity codes assigned in workspace."
        
        if task_id is not None:
            # Get codes for specific activity
            if task_id not in workspace.activities_df['task_id'].values:
                return f"Activity with task_id {task_id} not found in workspace."
            
            task_mask = workspace.activities_df['task_id'] == task_id
            task_code = workspace.activities_df.loc[task_mask, 'task_code'].values[0]
            task_name = workspace.activities_df.loc[task_mask, 'task_name'].values[0]
            
            codes_mask = workspace.activity_codes_df['task_id'] == task_id
            codes = workspace.activity_codes_df[codes_mask]
            
            if codes.empty:
                return f"Activity '{task_code}' ({task_name}) has no activity codes assigned."
            
            lines = [f"Activity codes for '{task_code}' ({task_name}):", ""]
            for _, row in codes.iterrows():
                lines.append(f"  - {row['code_type_name']}: {row['code_value_name']}")
            
            return "\n".join(lines)
        else:
            # Summary of all codes
            code_summary = workspace.activity_codes_df.groupby('code_type_name')['code_value_name'].value_counts()
            
            lines = ["Activity code summary in workspace:", ""]
            current_type = None
            for (code_type, code_value), count in code_summary.items():
                if code_type != current_type:
                    if current_type is not None:
                        lines.append("")
                    lines.append(f"{code_type}:")
                    current_type = code_type
                lines.append(f"  - {code_value}: {count} activities")
            
            lines.append("")
            lines.append(f"Total assignments: {len(workspace.activity_codes_df)}")
            
            # Also show available code types
            if workspace.code_types_with_values:
                lines.append("")
                lines.append(f"Available code types: {list(workspace.code_types_with_values.keys())}")
            
            return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in get_activity_codes_ws", error=str(e))
        return f"Error getting activity codes: {str(e)}"


@logfire.instrument("clear_schedule_ws")
async def clear_schedule_ws(ctx: RunContext[AgentDeps]) -> str:
    """Clear the current schedule workspace to start fresh.
    
    Use this to discard all unsaved changes and start with an empty workspace.
    This does NOT affect any data in P6 - only the in-memory draft is cleared.
    
    Warning: This action cannot be undone. All activities and relationships
    in the current workspace will be lost.
    
    Returns:
        Confirmation that workspace was cleared
    """
    try:
        conversation_id = ctx.deps.conversation_id
        if not conversation_id:
            return "Error: No conversation_id available."
        
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No active workspace to clear."
        
        activity_count = len(workspace.activities_df)
        relationship_count = len(workspace.relationships_df)
        project_name = workspace.project_name
        source = workspace.source
        
        schedule_state_manager.clear(conversation_id)
        
        logfire.info(
            "Cleared schedule workspace",
            conversation_id=conversation_id,
            project_name=project_name,
            activity_count=activity_count,
            relationship_count=relationship_count,
            source=source
        )
        
        source_info = "(loaded from P6)" if source == "p6_loaded" else "(draft)"
        return (
            f"Cleared workspace '{project_name}' {source_info} "
            f"with {activity_count} activities and {relationship_count} relationships. "
            "Ready for a new schedule."
        )
        
    except Exception as e:
        logfire.error("Error in clear_schedule_ws", error=str(e))
        return f"Error clearing workspace: {str(e)}"
