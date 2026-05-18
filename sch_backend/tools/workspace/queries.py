"""Workspace query tools - read operations on the in-memory workspace."""

import pandas as pd
import logfire
from pydantic_ai import RunContext
from sch_backend.tools._base import AgentDeps
from sch_backend.services.schedule_state import schedule_state_manager
from sch_backend.models.io import GetDrivingPathWsRequest
from sch_backend.services.gantt_payload_builder import (
    build_v2_gantt_payload,
    build_schedule_item_payload,
    build_relationship_projections,
)


@logfire.instrument("get_workspace_status_ws")
async def get_workspace_status_ws(ctx: RunContext[AgentDeps]) -> str:
    """Get the current status of the schedule workspace.
    
    Use this tool to check if a schedule is loaded and what modifications
    have been made. Returns information about loaded activities, relationships,
    and whether there are unsaved changes.
    
    Returns:
        Status summary of the current workspace state.
    """
    try:
        conversation_id = ctx.deps.conversation_id
        workspace = schedule_state_manager.get(conversation_id)
        
        if not workspace:
            return "No schedule workspace active. Use load_schedule_ms or create_schedule_ws first."
        
        status_parts = [
            f"Project: {workspace.project_name or workspace.project_id}",
            f"Source: {workspace.source}",
            f"Activities: {len(workspace.activities_df)}",
            f"Relationships: {len(workspace.relationships_df)}",
            f"Modified: {workspace.is_modified}",
        ]
        
        if workspace.last_calculation_at:
            cp_count = len(workspace.critical_path_ids)
            status_parts.append(f"Critical path activities: {cp_count}")
            status_parts.append(f"Last calculated: {workspace.last_calculation_at.strftime('%H:%M')}")
        else:
            status_parts.append("Last calculated: No")
        
        return " | ".join(status_parts)
        
    except Exception as e:
        logfire.error("Error in get_workspace_status_ws", error=str(e))
        return f"Error getting workspace status: {str(e)}"


@logfire.instrument("get_driving_path_ws")
async def get_driving_path_ws(
    ctx: RunContext[AgentDeps],
    req: GetDrivingPathWsRequest,
) -> str:
    """Trace the driving (longest) predecessor path to a target activity.

    Given a target task_id, this tool walks backward through the relationship
    graph to find ALL predecessor chains that lead to that activity and
    identifies the **driving path** (the longest / critical chain).

    Use this when the user asks:
    - "show me the path to activity X"
    - "what drives activity X"
    - "predecessors of activity X"
    - "what needs to happen before activity X"

    Prerequisites: schedule must be loaded AND calculate_gantt_ws must have
    been run so that early_start / early_finish are available.

    If render_gantt is True (default), a filtered Gantt chart showing only
    the driving path activities and their relationships will be streamed
    to the frontend automatically.

    Args:
        ctx: Runtime context with conversation_id in deps
        req: Target task ID and render options

    Returns:
        Text description of the driving path with activity details
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
                "No calculated dates. Run calculate_gantt_ws first "
                "so the driving path can be determined."
            )

        target_id = req.target_task_id
        df = workspace.activities_df
        rels = workspace.relationships_df

        # Verify target exists; fallback: treat input as ms_uid (task_code)
        if target_id not in df['task_id'].values:
            code_match = df[df['task_code'].astype(str) == str(target_id)]
            if not code_match.empty:
                target_id = int(code_match.iloc[0]['task_id'])
            else:
                return (
                    f"Activity {target_id} not found in workspace by task_id "
                    f"or task_code (ms_uid). Use get_activity_ms to look up "
                    f"the correct identifier, then retry."
                )

        # Build a quick adjacency lookup: succ_id -> list of pred_ids
        pred_map: dict[int, list[int]] = {}
        if not rels.empty:
            for _, rel in rels.iterrows():
                succ = int(rel['task_id'])
                pred = int(rel['pred_task_id'])
                pred_map.setdefault(succ, []).append(pred)

        # BFS/DFS backward from target to find all ancestors
        all_ancestors: set[int] = set()
        queue = [target_id]
        while queue:
            current = queue.pop()
            for pred in pred_map.get(current, []):
                if pred not in all_ancestors:
                    all_ancestors.add(pred)
                    queue.append(pred)

        if not all_ancestors:
            target_row = df[df['task_id'] == target_id].iloc[0]
            return (
                f"Activity {target_row.get('task_code', target_id)} "
                f"'{target_row.get('task_name', '')}' has no predecessors. "
                "It starts at the project start date."
            )

        # Build early_finish lookup for driving path determination
        ef_lookup: dict[int, object] = {}
        for _, row in df.iterrows():
            tid = int(row['task_id'])
            ef = row.get('early_finish')
            if pd.notna(ef):
                ef_lookup[tid] = ef

        # Trace the DRIVING path (longest chain) backward from target
        driving_path: list[int] = [target_id]
        current = target_id
        while current in pred_map:
            preds = pred_map[current]
            if not preds:
                break
            # Pick the predecessor with the latest early_finish (the driver)
            best_pred = None
            best_ef = None
            for p in preds:
                p_ef = ef_lookup.get(p)
                if p_ef is not None and (best_ef is None or p_ef > best_ef):
                    best_ef = p_ef
                    best_pred = p
            if best_pred is None:
                # Fallback: pick first predecessor
                best_pred = preds[0]
            if best_pred in driving_path:
                break  # Avoid cycles
            driving_path.append(best_pred)
            current = best_pred

        driving_path.reverse()  # Root -> target order

        # Collect all path activity IDs (driving + all ancestors + target)
        path_ids = all_ancestors | {target_id}

        # Build text report
        lines: list[str] = []
        target_row = df[df['task_id'] == target_id].iloc[0]
        lines.append(
            f"Driving path to: {target_row.get('task_code', target_id)} "
            f"'{target_row.get('task_name', '')}'"
        )
        lines.append(
            f"Driving chain: {len(driving_path)} activities | "
            f"All predecessors: {len(all_ancestors)} activities"
        )
        lines.append("")

        # Detail the driving chain
        hours_per_day = 8.0
        for i, tid in enumerate(driving_path):
            row = df[df['task_id'] == tid].iloc[0]
            code = row.get('task_code', '')
            name = row.get('task_name', '')
            es = row.get('early_start')
            ef = row.get('early_finish')
            dur_h = row.get('target_drtn_hr_cnt', 0) or 0
            dur_d = dur_h / hours_per_day
            is_crit = row.get('is_critical', False)
            tf = row.get('total_float_days', 0) or 0

            es_str = es.isoformat() if pd.notna(es) else '?'
            ef_str = ef.isoformat() if pd.notna(ef) else '?'
            crit_tag = " [CRITICAL]" if is_crit else ""
            arrow = " -> " if i < len(driving_path) - 1 else " (TARGET)"

            lines.append(
                f"  {i+1}. {code} '{name}' | "
                f"{dur_d:.0f}d | {es_str} - {ef_str} | "
                f"TF={tf:.0f}d{crit_tag}{arrow}"
            )

        logfire.info(
            "Driving path traced",
            conversation_id=conversation_id,
            target_task_id=target_id,
            driving_chain_length=len(driving_path),
            total_predecessors=len(all_ancestors),
        )

        # Optionally render Gantt filtered to path activities
        if req.render_gantt and ctx.deps.gantt_event_queue is not None:
            # Apply date filters to the visual set (text report is always full)
            vis_ids = path_ids.copy()
            if req.date_start or req.date_end:
                date_mask = pd.Series(True, index=df.index)
                if req.date_start:
                    ds = pd.to_datetime(req.date_start).date()
                    date_mask &= df['early_start'] >= ds
                if req.date_end:
                    de = pd.to_datetime(req.date_end).date()
                    date_mask &= df['early_finish'] <= de
                date_filtered_ids = set(df.loc[date_mask, 'task_id'].tolist())
                vis_ids = vis_ids & date_filtered_ids

            path_df = df[df['task_id'].isin(vis_ids)]

            # ---- Collect parent/summary tasks for hierarchy context ----
            summary_ids: set[int] = set()
            if req.include_summary_parents and 'is_summary' in df.columns:
                all_summaries = df[df['is_summary'].fillna(False).astype(bool)]
                wbs_to_tid: dict[str, int] = {}
                for _, srow in all_summaries.iterrows():
                    swbs = srow.get('wbs_path', '') or srow.get('wbs', '') or ''
                    if swbs:
                        wbs_to_tid[swbs] = int(srow['task_id'])

                for _, row in path_df.iterrows():
                    wbs = row.get('wbs_path', '') or row.get('wbs', '') or ''
                    while '.' in wbs:
                        wbs = wbs.rsplit('.', 1)[0]
                        if wbs in wbs_to_tid:
                            summary_ids.add(wbs_to_tid[wbs])

            # Build combined visible DataFrame (path activities + summary parents)
            all_vis_ids = vis_ids | summary_ids
            combined_df = df[df['task_id'].isin(all_vis_ids)]

            # Sort by WBS so hierarchy renders in correct order
            wbs_col = 'wbs_path' if 'wbs_path' in combined_df.columns else 'wbs'
            if wbs_col in combined_df.columns:
                combined_df = combined_df.copy()
                combined_df['_sort_wbs'] = combined_df[wbs_col].fillna('')
                combined_df = combined_df.sort_values('_sort_wbs')

            # Build WBS→task_id map for parent_id resolution
            wbs_to_task_id: dict[str, int] = {}
            for _, row in combined_df.iterrows():
                w = row.get('wbs_path', '') or row.get('wbs', '') or ''
                if w:
                    wbs_to_task_id[w] = int(row['task_id'])

            gantt_items = []
            for _, row in combined_df.iterrows():
                is_summary = bool(row.get('is_summary', False))
                wbs = row.get('wbs_path', '') or row.get('wbs', '') or ''
                outline_level = wbs.count('.') + 1 if wbs else 1

                # Resolve parent
                parent_id = None
                if wbs and '.' in wbs:
                    parent_wbs = wbs.rsplit('.', 1)[0]
                    if parent_wbs in wbs_to_task_id:
                        parent_id = f"task-{wbs_to_task_id[parent_wbs]}"

                dur_h = float(row.get('target_drtn_hr_cnt', 0)) if pd.notna(row.get('target_drtn_hr_cnt')) else 0
                working_days = dur_h / hours_per_day
                es = row.get('early_start')
                ef = row.get('early_finish')

                # For summary rows, derive bar geometry from visible descendants
                if is_summary and wbs:
                    desc_prefix = f"{wbs}."
                    descendants = combined_df[
                        combined_df.get('_sort_wbs', combined_df.get(wbs_col, pd.Series(dtype=str)))
                        .astype(str).str.startswith(desc_prefix)
                        & (~combined_df['is_summary'].fillna(False))
                    ]
                    if not descendants.empty:
                        d_starts = descendants['early_start'].dropna()
                        d_finishes = descendants['early_finish'].dropna()
                        if not d_starts.empty:
                            es = d_starts.min()
                        if not d_finishes.empty:
                            ef = d_finishes.max()
                        working_days = float(descendants['target_drtn_hr_cnt'].fillna(0).astype(float).sum()) / hours_per_day

                cal_days = (ef - es).days + 1 if pd.notna(es) and pd.notna(ef) else 0
                pct = row.get('percent_complete')
                if pd.isna(pct):
                    pct = row.get('phys_complete_pct')
                bl_s = row.get('baseline_start')
                bl_f = row.get('baseline_finish')
                bl_d = row.get('baseline_duration_d')

                if is_summary and wbs:
                    desc_prefix = f"{wbs}."
                    baseline_descendants = combined_df[
                        combined_df.get('_sort_wbs', combined_df.get(wbs_col, pd.Series(dtype=str)))
                        .astype(str).str.startswith(desc_prefix)
                        & (~combined_df['is_summary'].fillna(False))
                    ]
                    if not baseline_descendants.empty:
                        bd_starts = baseline_descendants['baseline_start'].dropna() if 'baseline_start' in baseline_descendants.columns else pd.Series(dtype='datetime64[ns]')
                        bd_finishes = baseline_descendants['baseline_finish'].dropna() if 'baseline_finish' in baseline_descendants.columns else pd.Series(dtype='datetime64[ns]')
                        bd_durations = baseline_descendants['baseline_duration_d'].dropna() if 'baseline_duration_d' in baseline_descendants.columns else pd.Series(dtype='float')

                        bl_s = bd_starts.min() if not bd_starts.empty else None
                        bl_f = bd_finishes.max() if not bd_finishes.empty else None
                        bl_d = float(bd_durations.astype(float).sum()) if not bd_durations.empty else None

                children_count = 0
                if is_summary and wbs:
                    prefix = wbs + '.'
                    children_count = len([
                        w for w in wbs_to_task_id
                        if w.startswith(prefix) and w.count('.') == wbs.count('.') + 1
                    ])

                # Determine status
                pct_val = float(pct) if pd.notna(pct) else 0
                status = 'completed' if pct_val >= 100 else ('in_progress' if pct_val > 0 else 'not_started')

                item = build_schedule_item_payload(
                    item_id=int(row['task_id']),
                    s_item_id=str(row['task_code']),
                    s_item=row['task_name'],
                    working_days=working_days,
                    calendar_days=cal_days,
                    total_float=float(row.get('total_float_days', 0)) if pd.notna(row.get('total_float_days')) else 0,
                    start=es if pd.notna(es) else None,
                    finish=ef if pd.notna(ef) else None,
                    is_critical=bool(row.get('is_critical', False)),
                    wbs_path=wbs,
                    status=status,
                    percent_complete=float(pct) if pd.notna(pct) else None,
                    level=outline_level,
                    is_summary=is_summary,
                    parent_id=parent_id,
                    children_count=children_count,
                    group_name=wbs.split('.')[0] if wbs else None,
                    baseline_start=bl_s if pd.notna(bl_s) else None,
                    baseline_finish=bl_f if pd.notna(bl_f) else None,
                    baseline_duration_d=float(bl_d) if pd.notna(bl_d) else None,
                )
                gantt_items.append(item)

            if gantt_items:
                # Build relationships for visible work activities (exclude summaries)
                work_ids = vis_ids  # relationships reference work tasks, not summaries
                gantt_relationships: list[dict] = []
                visible_rel_ids: list[str] = []
                envelope_rels: list[dict] = []

                logfire.info(
                    "Driving path rels check",
                    rels_empty=rels.empty,
                    rels_count=len(rels),
                    rels_columns=list(rels.columns) if not rels.empty else [],
                    work_ids_count=len(work_ids),
                    gantt_items_count=len(gantt_items),
                )

                if not rels.empty:
                    id_to_code = dict(zip(df['task_id'], df['task_code']))
                    raw_rels: list[dict] = []
                    for _, rel in rels.iterrows():
                        pred_id = rel.get('pred_task_id')
                        succ_id = rel.get('task_id')
                        pred_type = rel.get('pred_type', 'PR_FS')
                        rel_type = pred_type.replace('PR_', '') if isinstance(pred_type, str) and pred_type.startswith('PR_') else pred_type
                        lag_hours = rel.get('lag_hr_cnt', 0)
                        lag_days = (float(lag_hours) / hours_per_day) if pd.notna(lag_hours) else 0
                        raw_rels.append({
                            'pred_id': pred_id,
                            'succ_id': succ_id,
                            'rel_type': rel_type if rel_type else 'FS',
                            'lag_days': lag_days,
                        })

                    critical_set = set(workspace.critical_path_ids)
                    _vis_set = {int(t) for t in work_ids}
                    _id_to_code_map = {int(k): str(v) for k, v in id_to_code.items()}
                    logfire.info(
                        "Driving path relationship debug",
                        raw_rels_count=len(raw_rels),
                        visible_id_set_count=len(_vis_set),
                        visible_id_set_sample=sorted(list(_vis_set))[:20],
                        raw_rels_sample=[
                            {"pred": r["pred_id"], "succ": r["succ_id"]}
                            for r in raw_rels[:20]
                        ],
                        id_to_code_sample={str(k): v for k, v in list(_id_to_code_map.items())[:20]},
                    )
                    gantt_relationships, envelope_rels, visible_rel_ids = build_relationship_projections(
                        raw_relationships=raw_rels,
                        id_to_code_all=_id_to_code_map,
                        visible_id_set=_vis_set,
                        is_critical_edge=lambda p, s: p in critical_set and s in critical_set,
                    )
                    logfire.info(
                        "Driving path relationship results",
                        gantt_relationships_count=len(gantt_relationships),
                        envelope_rels_count=len(envelope_rels),
                        visible_rel_ids_count=len(visible_rel_ids),
                        gantt_relationships_sample=gantt_relationships[:5] if gantt_relationships else [],
                    )

                # Timeline bounds from visible work activities
                vis_starts = path_df['early_start'].dropna()
                vis_finishes = path_df['early_finish'].dropna()
                vis_start = vis_starts.min() if not vis_starts.empty else workspace.project_start
                vis_finish = vis_finishes.max() if not vis_finishes.empty else workspace.project_finish

                has_own_baseline = False
                if 'baseline_start' in df.columns or 'baseline_finish' in df.columns:
                    starts = df.get('baseline_start')
                    finishes = df.get('baseline_finish')
                    has_own_baseline = bool(
                        (starts is not None and starts.notna().any()) or
                        (finishes is not None and finishes.notna().any())
                    )

                filter_desc: dict = {'driving_path_to': req.target_task_id}
                if req.date_start:
                    filter_desc['date_start'] = req.date_start
                if req.date_end:
                    filter_desc['date_end'] = req.date_end

                legacy_payload = {
                    'items': gantt_items,
                    'relationships': gantt_relationships,
                    'project_start': vis_start.isoformat() if vis_start else '',
                    'project_finish': vis_finish.isoformat() if vis_finish else '',
                    'critical_path_length': 0,
                    'filter_applied': filter_desc,
                    'total_activities': len(df),
                    'filtered_activities': len(combined_df),
                    'available_activity_codes': workspace.code_types_with_values,
                    'grouping': 'WBS' if summary_ids else None,
                    'preserve_order': True,
                    'has_baseline': has_own_baseline,
                    'baseline_mode': 'what_if' if has_own_baseline else None,
                    'available_baseline_modes': {
                        'own': has_own_baseline,
                        'previous_version': False,
                        'database_baseline': False,
                        'what_if': has_own_baseline,
                    },
                }

                gantt_payload = build_v2_gantt_payload(
                    legacy_payload=legacy_payload,
                    view_id=None,
                    view_title=f"Driving path to {target_row.get('task_code', target_id)}",
                    project_id=workspace.project_id,
                    schedule_version_id=workspace.source_version_id,
                    available_baseline_modes=legacy_payload['available_baseline_modes'],
                    selected_baseline_mode='what_if' if has_own_baseline else None,
                    render_options={"show_links": True},
                    data_envelope_options=None,
                    envelope_activities=gantt_items,
                    envelope_relationships=envelope_rels,
                    visible_activity_ids=[int(t) for t in combined_df['task_id'].tolist()],
                    visible_relationship_ids=visible_rel_ids,
                    own_baseline_rows=[],
                )

                gantt_event = {
                    'type': 'gantt_panel',
                    'action': 'show',
                    'data': gantt_payload,
                }
                ctx.deps.gantt_event_queue.append(gantt_event)

        return "\n".join(lines)

    except Exception as e:
        logfire.error("Error in get_driving_path_ws", error=str(e))
        return f"Error tracing driving path: {str(e)}"
