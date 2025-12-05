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
        
        # Load from P6 using the service's connection
        workspace = schedule_state_manager.load_from_p6(
            conversation_id=conversation_id,
            conn=ctx.deps.conn,
            proj_id=proj_id
        )
        
        # Minimal response to reduce token usage
        return f"Loaded proj_id={proj_id}: {len(workspace.activities_df)} activities, {len(workspace.relationships_df)} relationships. Use calculate_gantt_ws to see Gantt chart."
        
    except Exception as e:
        logfire.error("Error in load_schedule_ws", error=str(e))
        return f"Error loading schedule: {str(e)}"


@logfire.instrument("calculate_gantt_ws")
async def calculate_gantt_ws(
    ctx: RunContext[AgentDeps],
    title: str = "Schedule Analysis"
) -> str:
    """Calculate CPM schedule and display Gantt chart.
    
    Runs the Critical Path Method algorithm on the workspace data and
    sends a Gantt chart visualization to the frontend panel.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        title: Title for the Gantt chart display
    
    Returns:
        Summary of calculation results including critical path
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ws first."
        
        # Import here to avoid circular imports
        from backend.services.cpm_calculator import CPMCalculator
        
        # Run CPM calculation
        calculator = CPMCalculator(
            activities_df=workspace.activities_df,
            relationships_df=workspace.relationships_df
        )
        
        result = calculator.calculate()
        workspace.calculation_result = result
        
        # Build Gantt data for frontend
        gantt_activities = []
        for _, row in workspace.activities_df.iterrows():
            task_id = row['task_id']
            
            # Get calculated dates from result
            calc_data = result['activities'].get(task_id, {})
            
            gantt_activities.append({
                'id': str(task_id),
                'task_id': task_id,
                'task_code': row['task_code'],
                'task_name': row['task_name'],
                'early_start': calc_data.get('early_start'),
                'early_finish': calc_data.get('early_finish'),
                'late_start': calc_data.get('late_start'),
                'late_finish': calc_data.get('late_finish'),
                'duration_hours': row['target_drtn_hr_cnt'],
                'total_float': calc_data.get('total_float', 0),
                'is_critical': task_id in result.get('critical_path', []),
                'status_code': row.get('status_code', 'TK_NotStart'),
                'wbs_path': row.get('wbs_path'),
            })
        
        # Build relationships for frontend
        gantt_relationships = []
        for _, row in workspace.relationships_df.iterrows():
            gantt_relationships.append({
                'predecessor_id': str(row['pred_task_id']),
                'successor_id': str(row['task_id']),
                'type': row['pred_type'].replace('PR_', '') if row['pred_type'].startswith('PR_') else row['pred_type'],
                'lag_hours': row.get('lag_hr_cnt', 0),
            })
        
        # Send to frontend via event queue
        if ctx.deps.gantt_event_queue is not None:
            gantt_event = {
                'type': 'gantt_data',
                'data': {
                    'title': title,
                    'project_id': workspace.project_id,
                    'activities': gantt_activities,
                    'relationships': gantt_relationships,
                    'critical_path': result.get('critical_path', []),
                    'project_duration_days': result.get('project_duration_days'),
                }
            }
            ctx.deps.gantt_event_queue.append(gantt_event)
        
        # Build summary response
        critical_count = len(result.get('critical_path', []))
        duration_days = result.get('project_duration_days', 'N/A')
        
        return f"Calculated schedule: {len(gantt_activities)} activities, {critical_count} critical, {duration_days} days duration. Gantt chart displayed."
        
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
        
        workspace.is_modified = True
        
        # Include task_id - LLM needs it for add_relationship_ws
        return f"Added '{task_code}' (task_id={new_task_id}, {original_duration_hours}h). Use task_id for relationships."
        
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
