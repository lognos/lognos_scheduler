"""Workspace mutation tools - operations that modify the in-memory workspace."""

from datetime import datetime
import pandas as pd
import logfire
from pydantic_ai import RunContext
from sch_backend.tools._base import AgentDeps
from sch_backend.services.schedule_state import schedule_state_manager
from sch_backend.services.gantt_payload_builder import (
    build_v2_gantt_payload,
    build_schedule_item_payload,
    build_relationship_projections,
)
from sch_backend.models.io import (
    CreateScheduleWsRequest,
    CalculateGanttWsRequest,
    ModifyActivityWsRequest,
    AddActivityWsRequest,
    AddRelationshipWsRequest,
    ModifyRelationshipWsRequest,
    DeleteRelationshipWsRequest,
    DeleteActivityWsRequest,
    AssignActivityCodesWsRequest,
    BulkAssignActivityCodesWsRequest,
    RemoveActivityCodesWsRequest,
    GetActivityCodesWsRequest,
    SnapshotBaselineWsRequest,
    WhatIfComparisonWsRequest,
)


def _build_ms_project_hierarchy(
    filtered_df: pd.DataFrame,
    hours_per_day: float,
    show_details: bool
) -> list[dict]:
    """
    Build hierarchical Gantt items for MS Project schedules.
    
    MS Project uses WBS dotted notation (1, 1.1, 1.1.1) and is_summary flag
    to define hierarchy. This function:
    1. Uses actual summary tasks (is_summary=True) as parents
    2. Nests children under their immediate parent based on WBS prefix
    3. Calculates outline_level from WBS dot count
    
    Args:
        filtered_df: DataFrame with schedule activities
        hours_per_day: Hours per working day for duration conversion
        show_details: If False, only show summary tasks
        
    Returns:
        List of Gantt items with proper hierarchy
    """
    gantt_items = []
    
    if filtered_df.empty:
        return gantt_items
    
    # Build WBS lookup for parent finding
    # WBS like "1.3.1.2" has parent "1.3.1"
    def get_parent_wbs(wbs: str) -> str | None:
        if not wbs or '.' not in wbs:
            return None
        return wbs.rsplit('.', 1)[0]
    
    def get_outline_level(wbs: str) -> int:
        if not wbs:
            return 1
        return wbs.count('.') + 1
    
    # Create a map of WBS -> task_id for parent lookup
    wbs_to_task_id: dict[str, int] = {}
    for _, row in filtered_df.iterrows():
        wbs = row.get('wbs_path', '') or row.get('wbs', '') or ''
        if wbs:
            wbs_to_task_id[wbs] = int(row['task_id'])
    
    # Build items sorted by WBS for proper order
    df_sorted = filtered_df.copy()
    df_sorted['_wbs'] = df_sorted['wbs_path'].fillna(df_sorted.get('wbs', ''))
    df_sorted = df_sorted.sort_values('_wbs')
    
    for _, row in df_sorted.iterrows():
        is_summary = bool(row.get('is_summary', False))
        
        # Skip detail activities if not showing details
        if not show_details and not is_summary:
            continue
        
        wbs = row.get('wbs_path', '') or row.get('wbs', '') or ''
        outline_level = get_outline_level(wbs)
        
        # Find parent task_id
        parent_wbs = get_parent_wbs(wbs)
        parent_id = None
        if parent_wbs and parent_wbs in wbs_to_task_id:
            parent_id = f"task-{wbs_to_task_id[parent_wbs]}"
        
        # Calculate dates and durations
        early_start = row.get('early_start')
        early_finish = row.get('early_finish')
        duration_hours = float(row.get('target_drtn_hr_cnt', 0)) if pd.notna(row.get('target_drtn_hr_cnt')) else 0
        working_days = duration_hours / hours_per_day

        # For MS summary tasks, tie bar geometry to visible descendant activities
        if is_summary and wbs:
            descendant_prefix = f"{wbs}."
            descendants = df_sorted[
                df_sorted['_wbs'].astype(str).str.startswith(descendant_prefix)
                & (~df_sorted['is_summary'].fillna(False))
            ]

            if not descendants.empty:
                descendant_starts = descendants['early_start'].dropna()
                descendant_finishes = descendants['early_finish'].dropna()

                if not descendant_starts.empty:
                    early_start = descendant_starts.min()
                if not descendant_finishes.empty:
                    early_finish = descendant_finishes.max()

                total_descendant_hours = descendants['target_drtn_hr_cnt'].fillna(0).astype(float).sum()
                working_days = float(total_descendant_hours) / hours_per_day

        if pd.notna(early_start) and pd.notna(early_finish):
            calendar_days = (early_finish - early_start).days + 1
        else:
            calendar_days = 0
        
        # Determine status
        status = 'not_started'
        pct_complete = float(row.get('phys_complete_pct', 0)) if pd.notna(row.get('phys_complete_pct')) else 0
        if pct_complete >= 100:
            status = 'completed'
        elif pct_complete > 0:
            status = 'in_progress'
        
        # Count children for summary tasks
        children_count = 0
        if is_summary and wbs:
            # Count direct children (WBS starts with this + '.')
            prefix = wbs + '.'
            children_count = len([w for w in wbs_to_task_id.keys() if w.startswith(prefix) and w.count('.') == wbs.count('.') + 1])
        
        item = {
            'id': int(row['task_id']),
            's_item_id': str(row.get('task_code', row.get('ms_uid', ''))),
            's_item': row.get('task_name', ''),
            'working_days': working_days,
            'calendar_days': calendar_days,
            'total_float': float(row.get('total_float_days', 0)) if pd.notna(row.get('total_float_days')) else 0,
            'start': early_start.isoformat() if pd.notna(early_start) else '',
            'finish': early_finish.isoformat() if pd.notna(early_finish) else '',
            'is_critical': bool(row.get('is_critical', False)),
            'wbs_path': wbs,
            'status': status,
            'level': outline_level,
            'is_summary': is_summary,
            'parent_id': parent_id,
            'children_count': children_count,
            'group_name': wbs.split('.')[0] if wbs else None,  # Top-level WBS segment
        }
        
        gantt_items.append(item)
    
    logfire.info(
        "Built MS Project hierarchy",
        total_items=len(gantt_items),
        summary_count=len([i for i in gantt_items if i['is_summary']]),
        detail_count=len([i for i in gantt_items if not i['is_summary']]),
        max_level=max([i['level'] for i in gantt_items]) if gantt_items else 0
    )
    
    return gantt_items


@logfire.instrument("calculate_gantt_ws")
async def calculate_gantt_ws(
    ctx: RunContext[AgentDeps],
    req: CalculateGanttWsRequest
) -> str:
    """Calculate CPM schedule and display Gantt chart with optional grouping.
    
    Runs the Critical Path Method algorithm on the workspace data and
    sends a Gantt chart visualization to the frontend panel.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing title, group_by, and show_details options
    
    Returns:
        Summary of calculation results including critical path
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        if workspace.activities_df.empty:
            return "Schedule workspace is empty. Load a schedule first."
        
        # Import here to avoid circular imports
        from sch_backend.services.network_calculator import NetworkCalculator, ScheduleValidationError
        
        # Run CPM calculation
        calculator = NetworkCalculator(
            activities_df=workspace.activities_df,
            relationships_df=workspace.relationships_df,
            project_start_date=workspace.project_start,
            calendar_exceptions=workspace.calendar_exceptions,
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

        ms_validation_summary = None
        if workspace.source == "ms_loaded":
            ms_validation_summary = calculator.validate_against_ms_dates(tolerance_days=1)
            logfire.info(
                "MS date validation summary",
                total_compared=ms_validation_summary['total_compared'],
                matched=ms_validation_summary['matched'],
                match_rate=ms_validation_summary['match_rate'],
                discrepancy_count=len(ms_validation_summary['discrepancies']),
            )
        
        # Apply filters BEFORE building Gantt items
        # This uses the existing filter_activities method which handles all filter logic
        has_filters = any([
            req.activity_codes,
            req.date_start,
            req.date_end,
            req.critical_only,
            req.status,
            req.search_term,
            req.wbs_path
        ])
        
        if has_filters:
            filtered_df = workspace.filter_activities(
                activity_codes=req.activity_codes,
                date_start=req.date_start,
                date_end=req.date_end,
                critical_only=req.critical_only,
                status=req.status,
                search_term=req.search_term,
                wbs_path=req.wbs_path
            )
        else:
            filtered_df = workspace.activities_df
        
        # Build Gantt data for frontend
        hours_per_day = 8.0  # Default working calendar assumption
        
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

            percent_complete = row.get('percent_complete')
            if pd.isna(percent_complete):
                percent_complete = row.get('phys_complete_pct')

            baseline_start = row.get('baseline_start')
            baseline_finish = row.get('baseline_finish')
            baseline_duration = row.get('baseline_duration_d')
            
            return build_schedule_item_payload(
                item_id=int(row['task_id']),
                s_item_id=row['task_code'],
                s_item=row['task_name'],
                working_days=working_days,
                calendar_days=calendar_days,
                total_float=float(row.get('total_float_days', 0)) if pd.notna(row.get('total_float_days')) else 0,
                start=early_start if pd.notna(early_start) else None,
                finish=early_finish if pd.notna(early_finish) else None,
                is_critical=bool(row.get('is_critical', False)),
                wbs_path=row.get('wbs_path', ''),
                status=row.get('status', 'not_started'),
                percent_complete=float(percent_complete) if pd.notna(percent_complete) else None,
                level=level,
                is_summary=False,
                parent_id=parent_id,
                children_count=0,
                group_name=None,
                baseline_start=baseline_start if pd.notna(baseline_start) else None,
                baseline_finish=baseline_finish if pd.notna(baseline_finish) else None,
                baseline_duration_d=float(baseline_duration) if pd.notna(baseline_duration) else None,
            )
        
        gantt_items = []
        grouping_applied = None
        
        # Check if this is an MS Project schedule (has is_summary column with actual summary tasks)
        is_ms_schedule = (
            'is_summary' in filtered_df.columns and 
            filtered_df['is_summary'].any()
        )
        
        # For MS Project schedules, ALWAYS use hierarchical display
        # MS Project data inherently has hierarchy via is_summary and WBS
        if is_ms_schedule:
            grouping_applied = 'WBS'
            gantt_items = _build_ms_project_hierarchy(
                filtered_df, 
                hours_per_day, 
                req.show_details
            )
            # Skip generic group processing - MS hierarchy already built
            groups = None
        elif req.group_by:
            # Determine grouping source for non-MS draft schedules
            if req.group_by.lower() == 'wbs':
                grouping_applied = 'WBS'
                # Group by first WBS segment (use / as separator for draft/imported data)
                groups: dict[str, list[int]] = {}
                for _, row in filtered_df.iterrows():
                    wbs_path = row.get('wbs_path', '') or ''
                    # Use first WBS segment as group, or "Ungrouped" if empty
                    group_key = wbs_path.split('/')[0] if wbs_path else 'Ungrouped'
                    if group_key not in groups:
                        groups[group_key] = []
                    groups[group_key].append(int(row['task_id']))
            else:
                # Group by activity code type
                grouping_applied = req.group_by
                groups = {}
                
                if not workspace.activity_codes_df.empty:
                    # Find activities with this code type
                    code_mask = workspace.activity_codes_df['code_type_name'].str.lower() == req.group_by.lower()
                    codes_for_type = workspace.activity_codes_df[code_mask]
                    
                    # Only include activities that are in the filtered set
                    filtered_task_ids = set(filtered_df['task_id'].tolist())
                    
                    for _, code_row in codes_for_type.iterrows():
                        task_id = int(code_row['task_id'])
                        if task_id not in filtered_task_ids:
                            continue  # Skip activities not in filtered set
                        group_key = code_row.get('code_value_name', 'Unknown')
                        if group_key not in groups:
                            groups[group_key] = []
                        groups[group_key].append(task_id)
                    
                    # Find filtered activities without this code type
                    assigned_task_ids = set(codes_for_type['task_id'].tolist())
                    unassigned = filtered_task_ids - assigned_task_ids
                    if unassigned:
                        groups['Unassigned'] = list(unassigned)
                else:
                    # No activity codes - all filtered activities are unassigned
                    groups['Unassigned'] = filtered_df['task_id'].tolist()
            
            # Build hierarchical items for generic grouping (skip if MS hierarchy was already built)
            if groups is not None:
                summary_id_counter = -1000  # Use negative IDs for synthetic summary items
                
                for group_name, task_ids in sorted(groups.items()):
                    if not task_ids:
                        continue
                        
                    # Get activities in this group from filtered DataFrame
                    group_df = filtered_df[filtered_df['task_id'].isin(task_ids)]
                    
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
                    summary_item = build_schedule_item_payload(
                        item_id=summary_id_counter,
                        s_item_id=f"GRP-{group_name[:8].upper()}",
                        s_item=group_name,
                        working_days=summary_working_days,
                        calendar_days=summary_calendar_days,
                        total_float=0,
                        start=summary_start,
                        finish=summary_finish,
                        is_critical=bool(any_critical),
                        wbs_path='',
                        status='not_started',
                        percent_complete=None,
                        level=1,
                        is_summary=True,
                        parent_id=None,
                        children_count=len(task_ids),
                        group_name=group_name,
                    )
                    gantt_items.append(summary_item)
                    
                    # Add detail items (Level 2) if requested
                    if req.show_details:
                        for _, row in group_df.iterrows():
                            detail_item = build_activity_item(row, level=2, parent_id=parent_id_str)
                            detail_item['group_name'] = group_name
                            gantt_items.append(detail_item)
                    
                    summary_id_counter -= 1
        else:
            # No grouping - flat list (all Level 2) from filtered DataFrame
            for _, row in filtered_df.iterrows():
                gantt_items.append(build_activity_item(row))
        
        # Build relationships data for Gantt arrows
        # Filter relationships to only include those where both activities are in filtered view
        filtered_task_ids = set(filtered_df['task_id'].tolist())
        gantt_relationships: list[dict] = []
        visible_relationship_ids: list[str] = []
        envelope_relationships: list[dict] = []

        # Timeline bounds should follow visible (filtered) activities
        visible_start = result.project_start
        visible_finish = result.project_finish
        if not filtered_df.empty:
            visible_starts = filtered_df['early_start'].dropna()
            visible_finishes = filtered_df['early_finish'].dropna()
            if not visible_starts.empty:
                visible_start = visible_starts.min()
            if not visible_finishes.empty:
                visible_finish = visible_finishes.max()
        
        if not workspace.relationships_df.empty:
            all_task_id_to_code = dict(zip(workspace.activities_df['task_id'], workspace.activities_df['task_code']))
            raw_relationships: list[dict] = []
            for _, rel in workspace.relationships_df.iterrows():
                pred_id = rel.get('pred_task_id')
                succ_id = rel.get('task_id')
                pred_type = rel.get('pred_type', 'PR_FS')
                rel_type = pred_type.replace('PR_', '') if isinstance(pred_type, str) and pred_type.startswith('PR_') else pred_type

                lag_hours = rel.get('lag_hr_cnt', 0)
                lag_days = (float(lag_hours) / hours_per_day) if pd.notna(lag_hours) else 0
                raw_relationships.append({
                    'pred_id': pred_id,
                    'succ_id': succ_id,
                    'rel_type': rel_type if rel_type else 'FS',
                    'lag_days': lag_days,
                })

            critical_path_ids_set = set(result.critical_path_ids)
            gantt_relationships, envelope_relationships, visible_relationship_ids = build_relationship_projections(
                raw_relationships=raw_relationships,
                id_to_code_all={int(k): str(v) for k, v in all_task_id_to_code.items()},
                visible_id_set={int(task_id) for task_id in filtered_task_ids},
                is_critical_edge=lambda pred_id, succ_id: (
                    pred_id in critical_path_ids_set and succ_id in critical_path_ids_set
                ),
            )

        requested_baseline_modes = req.data_envelope.include_baselines if req.data_envelope and req.data_envelope.include_baselines else ['own']
        has_own_baseline = False
        if 'baseline_start' in workspace.activities_df.columns or 'baseline_finish' in workspace.activities_df.columns:
            starts = workspace.activities_df.get('baseline_start')
            finishes = workspace.activities_df.get('baseline_finish')
            has_own_baseline = bool(
                (starts is not None and starts.notna().any()) or
                (finishes is not None and finishes.notna().any())
            )

        available_baseline_modes = {
            'own': has_own_baseline,
            'previous_version': False,
            'database_baseline': False,
        }

        selected_baseline_mode = req.render_options.baseline_mode if req.render_options else 'own'
        if not available_baseline_modes.get(selected_baseline_mode, False) and available_baseline_modes['own']:
            selected_baseline_mode = 'own'

        include_hierarchy = True if req.data_envelope is None else req.data_envelope.include_hierarchy

        envelope_activities = [build_activity_item(row, level=2 if include_hierarchy else 1, parent_id=None) for _, row in workspace.activities_df.iterrows()]

        own_baseline_rows = []
        if has_own_baseline and 'own' in requested_baseline_modes:
            for _, row in workspace.activities_df.iterrows():
                start_raw = row.get('baseline_start')
                finish_raw = row.get('baseline_finish')
                duration_raw = row.get('baseline_duration_d')
                own_baseline_rows.append({
                    'id': int(row['task_id']),
                    's_item_id': row.get('task_code', str(row['task_id'])),
                    'start': start_raw.isoformat() if pd.notna(start_raw) else None,
                    'finish': finish_raw.isoformat() if pd.notna(finish_raw) else None,
                    'duration_d': float(duration_raw) if pd.notna(duration_raw) else None,
                })

        legacy_payload = {
            'items': gantt_items,
            'relationships': gantt_relationships,
            'project_start': visible_start.isoformat(),
            'project_finish': visible_finish.isoformat(),
            'critical_path_length': result.critical_path_length_days,
            'filter_applied': {
                'wbs_path': req.wbs_path,
                'critical_only': req.critical_only,
                'activity_codes': req.activity_codes,
                'status': req.status,
                'search_term': req.search_term,
                'date_start': req.date_start,
                'date_end': req.date_end,
            },
            'total_activities': len(workspace.activities_df),
            'filtered_activities': len(filtered_df),
            'available_activity_codes': workspace.code_types_with_values,
            'grouping': grouping_applied,
            'preserve_order': bool(is_ms_schedule),
            'has_baseline': has_own_baseline,
            'baseline_mode': selected_baseline_mode,
            'available_baseline_modes': available_baseline_modes,
        }

        gantt_payload = build_v2_gantt_payload(
            legacy_payload=legacy_payload,
            view_id=req.view_id,
            view_title=req.title,
            project_id=workspace.project_id,
            schedule_version_id=workspace.source_version_id,
            available_baseline_modes=available_baseline_modes,
            selected_baseline_mode=selected_baseline_mode,
            render_options=req.render_options.model_dump() if req.render_options else None,
            data_envelope_options=req.data_envelope.model_dump() if req.data_envelope else None,
            envelope_activities=envelope_activities,
            envelope_relationships=envelope_relationships,
            visible_activity_ids=[int(task_id) for task_id in filtered_df['task_id'].tolist()],
            visible_relationship_ids=visible_relationship_ids,
            own_baseline_rows=own_baseline_rows,
        )
        
        # Stream Gantt panel event to frontend (skip when render_gantt=False)
        if req.render_gantt:
            gantt_event = {
                'type': 'gantt_panel',
                'action': 'show',
                'data': gantt_payload,
            }
            
            # Store event for streaming (will be picked up by chat router)
            if ctx.deps.gantt_event_queue is not None:
                ctx.deps.gantt_event_queue.append(gantt_event)
        
        # Return summary message
        warning_note = f" ({len(result.warnings)} warnings)" if result.warnings else ""
        grouping_note = f" grouped by {grouping_applied}" if grouping_applied else ""
        summary_count = len([i for i in gantt_items if i.get('is_summary')])
        detail_count = len([i for i in gantt_items if not i.get('is_summary')])
        
        # Build filter note for response
        filter_parts = []
        if req.activity_codes:
            for code_type, values in req.activity_codes.items():
                filter_parts.append(f"{code_type}={','.join(values)}")
        if req.critical_only:
            filter_parts.append("critical only")
        if req.status:
            filter_parts.append(f"status={','.join(req.status)}")
        if req.date_start or req.date_end:
            date_range = f"{req.date_start or 'start'} to {req.date_end or 'end'}"
            filter_parts.append(f"dates: {date_range}")
        if req.search_term:
            filter_parts.append(f"search: '{req.search_term}'")
        if req.wbs_path:
            filter_parts.append(f"WBS: {req.wbs_path}")
        
        filter_note = f" filtered by [{', '.join(filter_parts)}]" if filter_parts else ""
        total_note = f" ({len(filtered_df)} of {len(workspace.activities_df)} total)" if has_filters else ""
        
        verb = "Gantt displayed" if req.render_gantt else "CPM recalculated"
        if grouping_applied:
            validation_note = ""
            if ms_validation_summary and ms_validation_summary['total_compared'] > 0:
                validation_note = (
                    f", MS match {ms_validation_summary['matched']}/"
                    f"{ms_validation_summary['total_compared']} "
                    "within 1 day"
                )
            return f"{verb}: {summary_count} groups, {detail_count} activities{grouping_note}{filter_note}{total_note}, {result.critical_path_length_days:.0f} day critical path{warning_note}{validation_note}"
        else:
            validation_note = ""
            if ms_validation_summary and ms_validation_summary['total_compared'] > 0:
                validation_note = (
                    f", MS match {ms_validation_summary['matched']}/"
                    f"{ms_validation_summary['total_compared']} "
                    "within 1 day"
                )
            return f"{verb}: {detail_count} activities{filter_note}{total_note}, {result.critical_path_length_days:.0f} day critical path{warning_note}{validation_note}"
        
    except Exception as e:
        logfire.error("Error in calculate_gantt_ws", error=str(e))
        return f"Error calculating schedule: {str(e)}"


@logfire.instrument("modify_activity_ws")
async def modify_activity_ws(
    ctx: RunContext[AgentDeps],
    req: ModifyActivityWsRequest
) -> str:
    """Modify an activity in the schedule workspace.
    
    Use this tool to change activity properties like duration, dates, or name
    BEFORE running calculate_gantt_ws to see the impact.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing task_id and optional fields to modify
    
    Returns:
        Confirmation of changes made
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Find the activity
        mask = workspace.activities_df['task_id'] == req.task_id
        if not mask.any():
            return f"Activity with task_id {req.task_id} not found in workspace."
        
        changes = []
        
        # Apply changes
        if req.original_duration is not None:
            old_val = workspace.activities_df.loc[mask, 'target_drtn_hr_cnt'].values[0]
            workspace.activities_df.loc[mask, 'target_drtn_hr_cnt'] = req.original_duration
            changes.append(f"Duration: {old_val}h -> {req.original_duration}h")
        
        if req.target_start_date is not None:
            old_val = workspace.activities_df.loc[mask, 'target_start_date'].values[0]
            new_date = datetime.fromisoformat(req.target_start_date)
            workspace.activities_df.loc[mask, 'target_start_date'] = new_date
            changes.append(f"Target Start: {old_val} -> {new_date}")
        
        if req.target_end_date is not None:
            old_val = workspace.activities_df.loc[mask, 'target_end_date'].values[0]
            new_date = datetime.fromisoformat(req.target_end_date)
            workspace.activities_df.loc[mask, 'target_end_date'] = new_date
            changes.append(f"Target End: {old_val} -> {new_date}")
        
        if req.task_name is not None:
            old_val = workspace.activities_df.loc[mask, 'task_name'].values[0]
            workspace.activities_df.loc[mask, 'task_name'] = req.task_name
            changes.append(f"Name: '{old_val}' -> '{req.task_name}'")
        
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
    req: AddActivityWsRequest
) -> str:
    """Add a new activity to the schedule workspace.
    
    Use this tool to add activities that will be included in the next
    schedule calculation. The activity is added to the in-memory workspace
    and NOT saved to the database until explicitly requested.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing task_code, task_name, duration, and optional fields
    
    Returns:
        Confirmation with the new task_id assigned
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Check if task_code already exists
        if req.task_code in workspace.activities_df['task_code'].values:
            return f"Activity code '{req.task_code}' already exists in workspace."
        
        # Generate a new task_id (negative to indicate it's new and not in DB)
        existing_ids = workspace.activities_df['task_id'].values
        min_id = min(existing_ids) if len(existing_ids) > 0 else 0
        new_task_id = min_id - 1 if min_id >= 0 else min_id - 1
        
        # Parse target start date if provided
        target_start = None
        if req.target_start_date:
            target_start = datetime.fromisoformat(req.target_start_date)
        
        # Create new activity row
        new_row = {
            'task_id': new_task_id,
            'task_code': req.task_code,
            'task_name': req.task_name,
            'target_drtn_hr_cnt': req.original_duration_hours,
            'remain_drtn_hr_cnt': req.original_duration_hours,
            'target_start_date': target_start,
            'target_end_date': None,
            'wbs_id': req.wbs_id,
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
        if req.activity_codes:
            code_rows = [
                {
                    'task_id': new_task_id,
                    'code_type_name': code_type,
                    'code_value_name': code_value
                }
                for code_type, code_value in req.activity_codes.items()
            ]
            workspace.activity_codes_df = pd.concat([
                workspace.activity_codes_df,
                pd.DataFrame(code_rows)
            ], ignore_index=True)
        
        workspace.is_modified = True
        
        # Include task_id - LLM needs it for add_relationship_ws
        codes_info = f", codes={req.activity_codes}" if req.activity_codes else ""
        return f"Added '{req.task_code}' (task_id={new_task_id}, {req.original_duration_hours}h{codes_info}). Use task_id for relationships."
        
    except Exception as e:
        logfire.error("Error in add_activity_ws", error=str(e))
        return f"Error adding activity: {str(e)}"


@logfire.instrument("add_relationship_ws")
async def add_relationship_ws(
    ctx: RunContext[AgentDeps],
    req: AddRelationshipWsRequest
) -> str:
    """Add a relationship between activities in the workspace.
    
    Use this tool to create dependencies between activities.
    The relationship will be used in the next schedule calculation.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing predecessor_task_id, successor_task_id, relationship_type, lag_hours
    
    Returns:
        Confirmation of the relationship added
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Validate activities exist
        pred_exists = req.predecessor_task_id in workspace.activities_df['task_id'].values
        succ_exists = req.successor_task_id in workspace.activities_df['task_id'].values
        
        if not pred_exists:
            return f"Predecessor task_id {req.predecessor_task_id} not found in workspace."
        if not succ_exists:
            return f"Successor task_id {req.successor_task_id} not found in workspace."
        
        # Check for duplicate relationship
        dup_mask = (
            (workspace.relationships_df['pred_task_id'] == req.predecessor_task_id) &
            (workspace.relationships_df['task_id'] == req.successor_task_id)
        )
        if dup_mask.any():
            return f"Relationship from {req.predecessor_task_id} to {req.successor_task_id} already exists."
        
        # Map relationship type to the normalized relationship code used by the workspace
        type_map = {'FS': 'PR_FS', 'SS': 'PR_SS', 'FF': 'PR_FF', 'SF': 'PR_SF'}
        pred_type = type_map[req.relationship_type]
        
        # Create new relationship row
        new_row = {
            'task_pred_id': len(workspace.relationships_df) + 10000,  # Temp ID
            'task_id': req.successor_task_id,
            'pred_task_id': req.predecessor_task_id,
            'pred_type': pred_type,
            'lag_hr_cnt': req.lag_hours,
        }
        
        # Add to DataFrame
        workspace.relationships_df = pd.concat([
            workspace.relationships_df,
            pd.DataFrame([new_row])
        ], ignore_index=True)
        
        workspace.is_modified = True
        
        # Get activity names for confirmation
        pred_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == req.predecessor_task_id, 'task_name'
        ].values[0]
        succ_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == req.successor_task_id, 'task_name'
        ].values[0]
        
        lag_str = f" + {req.lag_hours}h lag" if req.lag_hours > 0 else f" - {abs(req.lag_hours)}h lead" if req.lag_hours < 0 else ""
        
        # Minimal response to reduce token usage
        return f"Added {req.relationship_type}{lag_str} relationship: {pred_name} -> {succ_name}"
        
    except Exception as e:
        logfire.error("Error in add_relationship_ws", error=str(e))
        return f"Error adding relationship: {str(e)}"


@logfire.instrument("modify_relationship_ws")
async def modify_relationship_ws(
    ctx: RunContext[AgentDeps],
    req: ModifyRelationshipWsRequest
) -> str:
    """Modify an existing relationship in the workspace.
    
    Use this tool to change the relationship type or lag between activities
    that are already linked in the workspace.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing predecessor_task_id, successor_task_id, and optional modifications
    
    Returns:
        Confirmation of the relationship modification
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Find the relationship
        rel_mask = (
            (workspace.relationships_df['pred_task_id'] == req.predecessor_task_id) &
            (workspace.relationships_df['task_id'] == req.successor_task_id)
        )
        
        if not rel_mask.any():
            return f"No relationship found from task_id {req.predecessor_task_id} to task_id {req.successor_task_id}."
        
        # Get current values for reporting
        old_type = workspace.relationships_df.loc[rel_mask, 'pred_type'].values[0]
        old_lag = workspace.relationships_df.loc[rel_mask, 'lag_hr_cnt'].values[0]
        
        changes = []
        
        # Update relationship type if provided
        if req.new_relationship_type:
            type_map = {'FS': 'PR_FS', 'SS': 'PR_SS', 'FF': 'PR_FF', 'SF': 'PR_SF'}
            new_pred_type = type_map[req.new_relationship_type]
            workspace.relationships_df.loc[rel_mask, 'pred_type'] = new_pred_type
            
            # Convert old type for display
            old_type_display = old_type.replace('PR_', '') if old_type.startswith('PR_') else old_type
            changes.append(f"type {old_type_display} -> {req.new_relationship_type}")
        
        # Update lag if provided
        if req.new_lag_hours is not None:
            workspace.relationships_df.loc[rel_mask, 'lag_hr_cnt'] = req.new_lag_hours
            changes.append(f"lag {old_lag}h -> {req.new_lag_hours}h")
        
        if not changes:
            return "No changes specified. Provide new_relationship_type or new_lag_hours."
        
        workspace.is_modified = True
        
        # Get activity names for confirmation
        pred_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == req.predecessor_task_id, 'task_name'
        ].values[0]
        succ_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == req.successor_task_id, 'task_name'
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
    req: CreateScheduleWsRequest
) -> str:
    """Create a new empty schedule workspace for draft planning.
    
    Use this tool to start building a schedule from scratch WITHOUT
    creating anything in the database. Perfect for:
    - Draft schedules for review before committing changes
    - What-if analysis and exploration
    - Building schedules collaboratively before approval
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing project_name, optional project_start_date, and description
    
    Returns:
        Confirmation that workspace is ready for adding activities
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
        if req.project_start_date:
            try:
                project_start = pd.to_datetime(req.project_start_date).date()
            except Exception:
                return f"Invalid date format: '{req.project_start_date}'. Use ISO format (YYYY-MM-DD)."
        
        # Create empty workspace using the state manager
        workspace = schedule_state_manager.create_new(
            conversation_id=conversation_id,
            project_name=req.project_name
        )
        
        # Set project start if provided (used by CPM calculation)
        if project_start:
            workspace.project_start = project_start
        
        logfire.info(
            "Created new draft schedule workspace",
            conversation_id=conversation_id,
            project_name=req.project_name,
            project_start=req.project_start_date,
            has_description=bool(req.description)
        )
        
        start_info = f" starting {req.project_start_date}" if req.project_start_date else ""
        return (
            f"Created draft schedule '{req.project_name}'{start_info}. "
            "Add activities with add_activity_ws, then link them with add_relationship_ws. "
            "Use calculate_gantt_ws to visualize and analyze the schedule."
        )
        
    except Exception as e:
        logfire.error("Error in create_schedule_ws", error=str(e))
        return f"Error creating schedule workspace: {str(e)}"


@logfire.instrument("assign_activity_codes_ws")
async def assign_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    req: AssignActivityCodesWsRequest
) -> str:
    """Assign or modify activity codes for an activity in the workspace.
    
    Use this tool to categorize activities with codes like Phase, Discipline, Area, etc.
    Each activity can have one code per code type.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing task_id and code_assignments dict
    
    Returns:
        Summary of assigned and replaced codes
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Validate activity exists
        if req.task_id not in workspace.activities_df['task_id'].values:
            return f"Activity with task_id {req.task_id} not found in workspace."
        
        # Get activity info for response
        task_mask = workspace.activities_df['task_id'] == req.task_id
        task_code = workspace.activities_df.loc[task_mask, 'task_code'].values[0]
        
        assigned = []
        replaced = []
        errors = []
        
        for code_type, code_value in req.code_assignments.items():
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
                (workspace.activity_codes_df['task_id'] == req.task_id) &
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
            else:
                # Add new assignment
                new_row = pd.DataFrame([{
                    'task_id': req.task_id,
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
        lines = [f"Activity code results for '{task_code}' (task_id={req.task_id}):"]
        
        if assigned:
            lines.append("Assigned: " + ", ".join(f"{a['code_type']}={a['code_value']}" for a in assigned))
        
        if replaced:
            lines.append("Replaced: " + ", ".join(f"{r['code_type']}: {r['old_value']} -> {r['new_value']}" for r in replaced))
        
        if errors:
            lines.append("Errors: " + "; ".join(errors))
        
        if not assigned and not replaced and not errors:
            lines.append("No changes made (values already match).")
        
        return " ".join(lines)
        
    except Exception as e:
        logfire.error("Error in assign_activity_codes_ws", error=str(e))
        return f"Error assigning activity codes: {str(e)}"


@logfire.instrument("bulk_assign_activity_codes_ws")
async def bulk_assign_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    req: BulkAssignActivityCodesWsRequest
) -> str:
    """Assign activity codes to multiple activities at once in the workspace.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing task_ids list and code_assignments dict
    
    Returns:
        Summary with counts of assigned/replaced codes
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Validate all activities exist
        existing_task_ids = set(workspace.activities_df['task_id'].values)
        missing = [tid for tid in req.task_ids if tid not in existing_task_ids]
        if missing:
            return f"Activities not found in workspace: {missing[:10]}{'...' if len(missing) > 10 else ''}"
        
        # Validate code types and values once
        validated_assignments: dict[str, str] = {}
        errors = []
        
        for code_type, code_value in req.code_assignments.items():
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
                    errors.append(f"Code value '{code_value}' not found in type '{matching_type}'")
                    continue
                
                validated_assignments[matching_type] = matching_value
            else:
                validated_assignments[code_type] = code_value
        
        if errors:
            return "Validation errors: " + "; ".join(errors)
        
        # Apply assignments to all tasks
        total_assigned = 0
        total_replaced = 0
        
        for task_id in req.task_ids:
            for code_type, code_value in validated_assignments.items():
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
        
        if total_assigned > 0 or total_replaced > 0:
            workspace.mark_modified()
        
        codes_summary = ", ".join(f"{k}={v}" for k, v in validated_assignments.items())
        return f"Bulk assignment: {len(req.task_ids)} activities, {codes_summary}. New: {total_assigned}, replaced: {total_replaced}."
        
    except Exception as e:
        logfire.error("Error in bulk_assign_activity_codes_ws", error=str(e))
        return f"Error in bulk assignment: {str(e)}"


@logfire.instrument("remove_activity_codes_ws")
async def remove_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    req: RemoveActivityCodesWsRequest
) -> str:
    """Remove activity code assignments from an activity in the workspace.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing task_id and code_type_names to remove
    
    Returns:
        Summary of removed codes
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Validate activity exists
        if req.task_id not in workspace.activities_df['task_id'].values:
            return f"Activity with task_id {req.task_id} not found in workspace."
        
        # Get activity info for response
        task_mask = workspace.activities_df['task_id'] == req.task_id
        task_code = workspace.activities_df.loc[task_mask, 'task_code'].values[0]
        
        removed = []
        not_found = []
        
        for code_type in req.code_type_names:
            # Find matching code type (case-insensitive)
            matching_type = code_type
            if workspace.code_types_with_values:
                for available_type in workspace.code_types_with_values.keys():
                    if available_type.lower() == code_type.lower():
                        matching_type = available_type
                        break
            
            # Find and remove the assignment
            remove_mask = (
                (workspace.activity_codes_df['task_id'] == req.task_id) &
                (workspace.activity_codes_df['code_type_name'].str.lower() == matching_type.lower())
            )
            
            if remove_mask.any():
                removed_value = workspace.activity_codes_df.loc[remove_mask, 'code_value_name'].values[0]
                workspace.activity_codes_df = workspace.activity_codes_df[~remove_mask]
                removed.append(f"{matching_type}={removed_value}")
            else:
                not_found.append(code_type)
        
        if removed:
            workspace.mark_modified()
        
        result = f"Removed from '{task_code}': {', '.join(removed)}" if removed else f"No codes removed from '{task_code}'"
        if not_found:
            result += f". Not found: {', '.join(not_found)}"
        return result
        
    except Exception as e:
        logfire.error("Error in remove_activity_codes_ws", error=str(e))
        return f"Error removing activity codes: {str(e)}"


@logfire.instrument("get_activity_codes_ws")
async def get_activity_codes_ws(
    ctx: RunContext[AgentDeps],
    req: GetActivityCodesWsRequest
) -> str:
    """Get current activity code assignments in the workspace.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request with optional task_id. If None, returns summary of all codes.
    
    Returns:
        Current activity code assignments
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        if workspace.activity_codes_df.empty:
            return "No activity codes assigned in workspace."
        
        if req.task_id is not None:
            # Get codes for specific activity
            if req.task_id not in workspace.activities_df['task_id'].values:
                return f"Activity with task_id {req.task_id} not found in workspace."
            
            task_mask = workspace.activities_df['task_id'] == req.task_id
            task_code = workspace.activities_df.loc[task_mask, 'task_code'].values[0]
            task_name = workspace.activities_df.loc[task_mask, 'task_name'].values[0]
            
            codes_mask = workspace.activity_codes_df['task_id'] == req.task_id
            codes = workspace.activity_codes_df[codes_mask]
            
            if codes.empty:
                return f"Activity '{task_code}' has no activity codes assigned."
            
            codes_str = ", ".join(f"{r['code_type_name']}={r['code_value_name']}" for _, r in codes.iterrows())
            return f"Activity '{task_code}' ({task_name}): {codes_str}"
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
    This does not affect persisted schedule data; only the in-memory draft is cleared.
    
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
        
        source_info = "(loaded from MS)" if source == "ms_loaded" else "(draft)"
        return (
            f"Cleared workspace '{project_name}' {source_info} "
            f"with {activity_count} activities and {relationship_count} relationships. "
            "Ready for a new schedule."
        )
        
    except Exception as e:
        logfire.error("Error in clear_schedule_ws", error=str(e))
        return f"Error clearing workspace: {str(e)}"


@logfire.instrument("delete_relationship_ws")
async def delete_relationship_ws(
    ctx: RunContext[AgentDeps],
    req: DeleteRelationshipWsRequest
) -> str:
    """Delete a relationship between activities in the workspace.
    
    Use this tool to remove a dependency link between two activities.
    This is a temporary workspace change.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing predecessor_task_id and successor_task_id
    
    Returns:
        Confirmation of the deleted relationship
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Find the relationship
        rel_mask = (
            (workspace.relationships_df['pred_task_id'] == req.predecessor_task_id) &
            (workspace.relationships_df['task_id'] == req.successor_task_id)
        )
        
        if not rel_mask.any():
            return f"No relationship found from task_id {req.predecessor_task_id} to task_id {req.successor_task_id}."
        
        # Get activity names for confirmation message
        pred_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == req.predecessor_task_id, 'task_name'
        ]
        succ_name = workspace.activities_df.loc[
            workspace.activities_df['task_id'] == req.successor_task_id, 'task_name'
        ]
        pred_name = pred_name.values[0] if len(pred_name) > 0 else str(req.predecessor_task_id)
        succ_name = succ_name.values[0] if len(succ_name) > 0 else str(req.successor_task_id)
        
        # Get relationship type for confirmation
        rel_type = workspace.relationships_df.loc[rel_mask, 'pred_type'].values[0]
        rel_type_display = rel_type.replace('PR_', '') if rel_type.startswith('PR_') else rel_type
        
        # Remove the relationship
        workspace.relationships_df = workspace.relationships_df[~rel_mask]
        workspace.is_modified = True
        
        logfire.info(
            "Deleted relationship from workspace",
            conversation_id=conversation_id,
            pred_task_id=req.predecessor_task_id,
            succ_task_id=req.successor_task_id,
            relationship_type=rel_type_display
        )
        
        return f"Deleted {rel_type_display} relationship: {pred_name} -> {succ_name}. Run calculate_gantt_ws to see impact."
        
    except Exception as e:
        logfire.error("Error in delete_relationship_ws", error=str(e))
        return f"Error deleting relationship: {str(e)}"


@logfire.instrument("delete_activity_ws")
async def delete_activity_ws(
    ctx: RunContext[AgentDeps],
    req: DeleteActivityWsRequest
) -> str:
    """Delete an activity from the schedule workspace.
    
    Use this tool to remove an activity and all its relationships from the workspace.
    This is a temporary workspace change.
    
    Note: Any relationships where this activity is predecessor or successor
    will also be automatically removed.
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Request containing task_id of the activity to delete
    
    Returns:
        Confirmation of the deleted activity and relationships
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        # Find the activity
        activity_mask = workspace.activities_df['task_id'] == req.task_id
        
        if not activity_mask.any():
            return f"Activity with task_id {req.task_id} not found in workspace."
        
        # Get activity info for confirmation message
        task_code = workspace.activities_df.loc[activity_mask, 'task_code'].values[0]
        task_name = workspace.activities_df.loc[activity_mask, 'task_name'].values[0]
        
        # Find and count relationships to remove
        pred_mask = workspace.relationships_df['pred_task_id'] == req.task_id
        succ_mask = workspace.relationships_df['task_id'] == req.task_id
        rel_mask = pred_mask | succ_mask
        removed_rel_count = rel_mask.sum()
        
        # Remove relationships connected to this activity
        if removed_rel_count > 0:
            workspace.relationships_df = workspace.relationships_df[~rel_mask]
        
        # Remove activity codes for this activity
        if not workspace.activity_codes_df.empty:
            code_mask = workspace.activity_codes_df['task_id'] == req.task_id
            removed_code_count = code_mask.sum()
            if removed_code_count > 0:
                workspace.activity_codes_df = workspace.activity_codes_df[~code_mask]
        else:
            removed_code_count = 0
        
        # Remove the activity
        workspace.activities_df = workspace.activities_df[~activity_mask]
        workspace.is_modified = True
        
        logfire.info(
            "Deleted activity from workspace",
            conversation_id=conversation_id,
            task_id=req.task_id,
            task_code=task_code,
            task_name=task_name,
            removed_relationships=removed_rel_count,
            removed_codes=removed_code_count
        )
        
        rel_info = f" and {removed_rel_count} relationship(s)" if removed_rel_count > 0 else ""
        return f"Deleted activity '{task_code}' ({task_name}){rel_info}. Run calculate_gantt_ws to see impact."
        
    except Exception as e:
        logfire.error("Error in delete_activity_ws", error=str(e))
        return f"Error deleting activity: {str(e)}"


# ---------------------------------------------------------------------------
# What-If Baseline Tools
# ---------------------------------------------------------------------------


async def snapshot_baseline_ws(
    ctx: RunContext[AgentDeps],
    req: SnapshotBaselineWsRequest,
) -> str:
    """Snapshot the current calculated schedule dates as the baseline reference.

    Call this AFTER calculate_gantt_ws so that early_start / early_finish
    values exist. The snapshot is stored in-memory and written into the
    activities DataFrame as baseline_start / baseline_finish /
    baseline_duration_d.  Subsequent calculate_gantt_ws calls will
    automatically render baseline ghost bars on every activity.

    Typical what-if workflow:
    1. load_schedule_ms
    2. calculate_gantt_ws          -> see current plan
    3. snapshot_baseline_ws        -> freeze dates as baseline
    4. modify_activity_ws (one or more changes)
    5. calculate_gantt_ws          -> see updated plan WITH baseline bars
    6. get_whatif_comparison_ws    -> structured delta report

    Args:
        ctx: Runtime context with conversation_id in deps
        req: Label for the baseline snapshot

    Returns:
        Confirmation message with activity count and baseline label
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)

        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms first."

        if workspace.activities_df.empty:
            return "Schedule workspace is empty. Load a schedule first."

        if 'early_start' not in workspace.activities_df.columns:
            return (
                "No calculated dates found. "
                "Run calculate_gantt_ws before snapshotting a baseline."
            )

        snapshot = workspace.snapshot_as_baseline(label=req.label)
        count = len(snapshot.activities)

        logfire.info(
            "Baseline snapshot created",
            conversation_id=conversation_id,
            label=req.label,
            activity_count=count,
        )

        return (
            f"Baseline '{req.label}' saved for {count} activities. "
            "Make your changes, then run calculate_gantt_ws to see baseline ghost bars, "
            "or get_whatif_comparison_ws for a structured delta report."
        )

    except ValueError as ve:
        return str(ve)
    except Exception as e:
        logfire.error("Error in snapshot_baseline_ws", error=str(e))
        return f"Error creating baseline snapshot: {str(e)}"


async def get_whatif_comparison_ws(
    ctx: RunContext[AgentDeps],
    req: WhatIfComparisonWsRequest,
) -> str:
    """Compare current calculated dates against the stored baseline snapshot.

    Returns a structured text report listing activities whose start or
    finish dates shifted compared to the baseline snapshot. Activities can
    be filtered by shift threshold (days) and critical-path membership.

    Prerequisite: snapshot_baseline_ws must have been called earlier in the
    conversation, AND calculate_gantt_ws must have been run after making
    changes.

    Args:
        ctx: Runtime context with conversation_id in deps
        req: Comparison filters (threshold_days, critical_only)

    Returns:
        Multi-line comparison report summarizing schedule deltas
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)

        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms first."

        if workspace.baseline_snapshot is None:
            return (
                "No baseline snapshot exists. "
                "Run snapshot_baseline_ws first to freeze a reference point."
            )

        if 'early_start' not in workspace.activities_df.columns:
            return (
                "No calculated dates in workspace. "
                "Run calculate_gantt_ws after making changes."
            )

        baseline_df = workspace.baseline_snapshot.activities.copy()
        current_df = workspace.activities_df[
            ['task_id', 'task_code', 'task_name', 'early_start', 'early_finish', 'is_critical']
        ].copy()

        merged = current_df.merge(
            baseline_df, on='task_id', how='inner', suffixes=('', '_bl'),
        )

        if merged.empty:
            return "No matching activities between current schedule and baseline."

        # Calculate deltas in days
        merged['start_delta_days'] = merged.apply(
            lambda r: (r['early_start'] - r['baseline_start']).days
            if pd.notna(r['early_start']) and pd.notna(r['baseline_start'])
            else None,
            axis=1,
        )
        merged['finish_delta_days'] = merged.apply(
            lambda r: (r['early_finish'] - r['baseline_finish']).days
            if pd.notna(r['early_finish']) and pd.notna(r['baseline_finish'])
            else None,
            axis=1,
        )

        # Apply filters
        if req.critical_only:
            merged = merged[merged['is_critical'] == True]  # noqa: E712

        if req.threshold_days > 0:
            mask = (
                (merged['start_delta_days'].abs() > req.threshold_days) |
                (merged['finish_delta_days'].abs() > req.threshold_days)
            )
            merged = merged[mask]

        if merged.empty:
            return (
                f"No activities shifted more than {req.threshold_days} day(s) "
                f"{'on the critical path ' if req.critical_only else ''}"
                "compared to baseline."
            )

        # Build report
        delayed = merged[merged['finish_delta_days'] > 0]
        accelerated = merged[merged['finish_delta_days'] < 0]
        unchanged = merged[merged['finish_delta_days'] == 0]

        lines: list[str] = []
        lines.append(
            f"What-If Comparison vs '{workspace.baseline_snapshot.label}' "
            f"(snapshot at {workspace.baseline_snapshot.snapshot_at.strftime('%H:%M')})"
        )
        lines.append(
            f"Total compared: {len(merged)} | "
            f"Delayed: {len(delayed)} | "
            f"Accelerated: {len(accelerated)} | "
            f"Unchanged: {len(unchanged)}"
        )

        # Overall project impact
        max_finish_delta = merged['finish_delta_days'].max()
        min_finish_delta = merged['finish_delta_days'].min()
        if pd.notna(max_finish_delta) and max_finish_delta > 0:
            lines.append(f"Max delay: +{int(max_finish_delta)} day(s)")
        if pd.notna(min_finish_delta) and min_finish_delta < 0:
            lines.append(f"Max acceleration: {int(min_finish_delta)} day(s)")

        lines.append("")

        # Detail top shifted activities (limit to 15 for readability)
        sorted_df = merged.reindex(
            merged['finish_delta_days'].abs().sort_values(ascending=False).index
        )
        detail_rows = sorted_df.head(15)

        for _, row in detail_rows.iterrows():
            code = row.get('task_code', '')
            name = row.get('task_name', '')
            s_delta = int(row['start_delta_days']) if pd.notna(row['start_delta_days']) else 0
            f_delta = int(row['finish_delta_days']) if pd.notna(row['finish_delta_days']) else 0
            crit = " [CRITICAL]" if row.get('is_critical') else ""
            sign_s = f"+{s_delta}" if s_delta > 0 else str(s_delta)
            sign_f = f"+{f_delta}" if f_delta > 0 else str(f_delta)
            lines.append(
                f"  {code} {name}: start {sign_s}d, finish {sign_f}d{crit}"
            )

        if len(sorted_df) > 15:
            lines.append(f"  ... and {len(sorted_df) - 15} more activities")

        report = "\n".join(lines)

        logfire.info(
            "What-if comparison generated",
            conversation_id=conversation_id,
            compared=len(merged),
            delayed=len(delayed),
            accelerated=len(accelerated),
            threshold_days=req.threshold_days,
        )

        return report

    except Exception as e:
        logfire.error("Error in get_whatif_comparison_ws", error=str(e))
        return f"Error generating comparison: {str(e)}"
