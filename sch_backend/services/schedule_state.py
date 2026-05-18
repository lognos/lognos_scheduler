"""
Schedule state management for in-memory DataFrame-based schedule editing.

This module provides session-scoped schedule workspaces that maintain:
- Activities DataFrame (working state)
- Relationships DataFrame
- Activity Codes (for filtering)
- Modification tracking

All filtering operations happen in-memory on pandas DataFrames,
NOT in the database. Database is only touched for initial load and final save.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
import pandas as pd
import logfire


@dataclass
class BaselineSnapshot:
    """Point-in-time snapshot of calculated schedule dates used as a baseline reference.

    Created by snapshot_baseline_ws after a CPM calculation, these dates are
    written back into the workspace DataFrame as baseline_start / baseline_finish /
    baseline_duration_d so that subsequent calculate_gantt_ws calls can render
    baseline ghost bars without any external data source.
    """
    snapshot_at: datetime
    label: str  # Human-readable label, e.g. "Current Plan" or "Before adding crane"
    activities: pd.DataFrame  # Columns: task_id, baseline_start, baseline_finish, baseline_duration_d


@dataclass
class ScheduleWorkspace:
    """
    In-memory working state for a schedule being edited.
    
    Maintains DataFrames + metadata per conversation session.
    
    Activity codes are represented as task/code type/code value rows when
    available from a schedule source or draft workspace.
    
    All filtering happens on these DataFrames - no database queries.
    """
    conversation_id: str
    project_id: Optional[int] = None  # None if creating new schedule
    project_name: Optional[str] = None
    
    # Core schedule data
    activities_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    relationships_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # Activity Code data used for filtering
    # Columns: task_id, code_type_name, code_value_name
    activity_codes_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # Available code types and their values for UI filter dropdowns
    # Example: {"Phase": ["Design", "Construction", "Closeout"], "Area": ["Building A", "Building B"]}
    code_types_with_values: dict[str, list[str]] = field(default_factory=dict)
    
    # State tracking
    is_modified: bool = False
    source: str = "new"  # "new" | "ms_loaded"
    source_version_id: Optional[int] = None  # For MS schedules: Supabase version ID
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Calculation results (populated after CPM calculation)
    last_calculation_at: Optional[datetime] = None
    project_start: Optional[date] = None
    project_finish: Optional[date] = None
    calendar_exceptions: list[date] = field(default_factory=list)
    critical_path_ids: list[int] = field(default_factory=list)
    
    # What-if baseline snapshot (populated by snapshot_baseline_ws)
    baseline_snapshot: Optional[BaselineSnapshot] = None
    
    def mark_modified(self) -> None:
        """Mark workspace as modified (needs recalculation/save)."""
        self.is_modified = True
        self.updated_at = datetime.now()
    
    def snapshot_as_baseline(self, label: str = "Baseline") -> BaselineSnapshot:
        """Capture current calculated dates as the baseline reference.

        Copies early_start / early_finish into baseline_start / baseline_finish
        on the activities DataFrame so calculate_gantt_ws renders ghost bars.

        Raises ValueError if no calculation has been run yet.
        """
        if 'early_start' not in self.activities_df.columns:
            raise ValueError(
                "No calculated dates in workspace. "
                "Run calculate_gantt_ws before snapshotting a baseline."
            )

        hours_per_day = 8.0
        snapshot_df = self.activities_df[['task_id', 'early_start', 'early_finish', 'target_drtn_hr_cnt']].copy()
        snapshot_df = snapshot_df.rename(columns={
            'early_start': 'baseline_start',
            'early_finish': 'baseline_finish',
        })
        snapshot_df['baseline_duration_d'] = (
            snapshot_df['target_drtn_hr_cnt'].fillna(0) / hours_per_day
        )
        snapshot_df = snapshot_df.drop(columns=['target_drtn_hr_cnt'])

        snapshot = BaselineSnapshot(
            snapshot_at=datetime.now(),
            label=label,
            activities=snapshot_df,
        )
        self.baseline_snapshot = snapshot

        # Write baseline columns back into activities_df so gantt builder picks them up
        self.activities_df = self.activities_df.drop(
            columns=['baseline_start', 'baseline_finish', 'baseline_duration_d'],
            errors='ignore',
        )
        self.activities_df = self.activities_df.merge(
            snapshot_df, on='task_id', how='left',
        )
        self.updated_at = datetime.now()
        return snapshot
    
    def update_from_calculation(
        self,
        activities_with_dates: pd.DataFrame,
        project_start: date,
        project_finish: date,
        critical_path_ids: list[int]
    ) -> None:
        """Update workspace with CPM calculation results."""
        # Merge calculated dates into activities DataFrame
        calc_columns = [
            'task_id', 'early_start', 'early_finish', 'late_start', 'late_finish',
            'total_float_days', 'free_float_days', 'is_critical'
        ]
        
        if not activities_with_dates.empty:
            # Create a mapping from calculation results
            calc_df = activities_with_dates[
                [c for c in calc_columns if c in activities_with_dates.columns]
            ].copy()
            
            # Merge into activities_df
            if 'task_id' in self.activities_df.columns and 'task_id' in calc_df.columns:
                # Drop existing calculation columns if present
                for col in calc_columns[1:]:  # Skip task_id
                    if col in self.activities_df.columns:
                        self.activities_df = self.activities_df.drop(columns=[col])
                
                self.activities_df = self.activities_df.merge(
                    calc_df, on='task_id', how='left'
                )
        
        self.project_start = project_start
        self.project_finish = project_finish
        self.critical_path_ids = critical_path_ids
        self.last_calculation_at = datetime.now()
    
    @logfire.instrument("schedule_workspace.filter_activities")
    def filter_activities(
        self,
        wbs_path: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        critical_only: bool = False,
        status: Optional[list[str]] = None,
        search_term: Optional[str] = None,
        activity_codes: Optional[dict[str, list[str]]] = None
    ) -> pd.DataFrame:
        """
        Return filtered view of activities DataFrame.
        
        ALL FILTERING HAPPENS IN-MEMORY - no database queries.
        Does not modify the underlying data - returns a filtered copy.
        
        Activity Code filtering (PRIMARY mechanism):
        - activity_codes is a dict: code_type_name -> list of code_value_names
        - Example: {"Phase": ["Construction"], "Area": ["Building A", "Building B"]}
        - Logic: AND between code types, OR within a code type
        - Above example: Phase=Construction AND (Area=Building A OR Area=Building B)
        
        Args:
            wbs_path: Filter by WBS path prefix
            date_start: Filter activities starting on or after this date (ISO format)
            date_end: Filter activities finishing on or before this date (ISO format)
            critical_only: Only return critical path activities
            status: Filter by status list ['not_started', 'active', 'complete']
            search_term: Search in task_code and task_name
            activity_codes: Dict of code_type -> list of code_values (PRIMARY filter)
            
        Returns:
            Filtered copy of activities DataFrame
        """
        if self.activities_df.empty:
            return self.activities_df.copy()
            
        df = self.activities_df.copy()
        
        # Activity Code filter (PRIMARY - filter first for efficiency)
        if activity_codes and not self.activity_codes_df.empty:
            matching_task_ids = self._filter_by_activity_codes(activity_codes)
            if matching_task_ids is not None:
                df = df[df['task_id'].isin(matching_task_ids)]
        
        # WBS path filter
        if wbs_path and 'wbs_path' in df.columns:
            wbs_path_series = df['wbs_path'].astype('string').fillna('')
            df = df[wbs_path_series.str.startswith(wbs_path)]
        
        # Date range filters (using early_start/early_finish from calculation)
        if date_start and 'early_start' in df.columns:
            date_start_parsed = pd.to_datetime(date_start).date()
            df = df[df['early_start'] >= date_start_parsed]
        
        if date_end and 'early_finish' in df.columns:
            date_end_parsed = pd.to_datetime(date_end).date()
            df = df[df['early_finish'] <= date_end_parsed]
        
        # Critical path filter
        if critical_only and 'is_critical' in df.columns:
            df = df[df['is_critical']]
        
        # Status filter
        if status and 'status' in df.columns:
            df = df[df['status'].isin(status)]
        
        # Search term filter
        if search_term:
            mask = pd.Series([False] * len(df), index=df.index)
            if 'task_code' in df.columns:
                task_code_series = df['task_code'].astype('string').fillna('')
                mask |= task_code_series.str.contains(search_term, case=False, na=False)
            if 'task_name' in df.columns:
                task_name_series = df['task_name'].astype('string').fillna('')
                mask |= task_name_series.str.contains(search_term, case=False, na=False)
            df = df[mask]
        
        return df
    
    def _filter_by_activity_codes(
        self,
        activity_codes: dict[str, list[str]]
    ) -> Optional[set[int]]:
        """
        Filter task IDs by Activity Code criteria.
        
        Logic:
        - AND between code types (must match ALL specified types)
        - OR within a code type (can match ANY value within a type)
        
        Example: {"Phase": ["Construction"], "Area": ["Building A", "Building B"]}
        Returns tasks where Phase=Construction AND (Area=Building A OR Area=Building B)
        """
        if not activity_codes or self.activity_codes_df.empty:
            return None
        
        matching_task_ids: Optional[set[int]] = None
        
        for code_type, code_values in activity_codes.items():
            if not code_values:
                continue
                
            # Find tasks that have ANY of the specified values for this code type
            type_matches = self.activity_codes_df[
                (self.activity_codes_df['code_type_name'] == code_type) &
                (self.activity_codes_df['code_value_name'].isin(code_values))
            ]['task_id'].unique()
            
            type_match_set = set(type_matches)
            
            if matching_task_ids is None:
                # First code type - initialize
                matching_task_ids = type_match_set
            else:
                # AND logic: intersect with previous code type matches
                matching_task_ids = matching_task_ids & type_match_set
        
        return matching_task_ids
    
    def get_activity_count(self) -> int:
        """Get total number of activities in workspace."""
        return len(self.activities_df)
    
    def get_relationship_count(self) -> int:
        """Get total number of relationships in workspace."""
        return len(self.relationships_df)


class ScheduleStateManager:
    """
    Manages schedule workspaces per conversation.
    
    Each conversation has at most one active workspace.
    In production, could be backed by Redis for persistence
    across server restarts. For MVP, in-memory dict is sufficient.
    """
    
    def __init__(self):
        self._workspaces: dict[str, ScheduleWorkspace] = {}
    
    def get(self, conversation_id: str) -> Optional[ScheduleWorkspace]:
        """Get workspace for conversation, if exists."""
        return self._workspaces.get(conversation_id)
    
    def get_or_create(self, conversation_id: str) -> ScheduleWorkspace:
        """Get existing workspace or create new empty one."""
        if conversation_id not in self._workspaces:
            self._workspaces[conversation_id] = ScheduleWorkspace(
                conversation_id=conversation_id
            )
        return self._workspaces[conversation_id]
    
    def create_new(
        self,
        conversation_id: str,
        project_name: Optional[str] = None
    ) -> ScheduleWorkspace:
        """
        Create a new empty workspace for building a schedule from scratch.
        
        Use case: Create new schedules before saving or presenting for review.
        
        Initializes empty DataFrames with all required columns so that
        add_activity_ws and add_relationship_ws tools work correctly.
        """
        # Initialize empty DataFrames with required columns
        # This matches the workspace structure expected by mutation/calculation tools.
        activities_df = pd.DataFrame(columns=[
            'task_id', 'task_code', 'task_name', 'target_drtn_hr_cnt', 'remain_drtn_hr_cnt',
            'target_start_date', 'target_end_date', 'wbs_id', 'wbs_path',
            'status_code', 'total_float_hr_cnt', 'free_float_hr_cnt'
        ])
        
        relationships_df = pd.DataFrame(columns=[
            'task_pred_id', 'task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt'
        ])
        
        activity_codes_df = pd.DataFrame(columns=[
            'task_id', 'code_type_name', 'code_value_name'
        ])
        
        workspace = ScheduleWorkspace(
            conversation_id=conversation_id,
            project_name=project_name or "New Schedule",
            activities_df=activities_df,
            relationships_df=relationships_df,
            activity_codes_df=activity_codes_df,
            code_types_with_values={},
            source="new"
        )
        self._workspaces[conversation_id] = workspace
        
        logfire.info(
            "Created new schedule workspace",
            conversation_id=conversation_id,
            project_name=project_name or "New Schedule"
        )
        
        return workspace
    
    def clear(self, conversation_id: str) -> None:
        """Remove workspace for a conversation."""
        self._workspaces.pop(conversation_id, None)
    
    def has_workspace(self, conversation_id: str) -> bool:
        """Check if conversation has an active workspace."""
        return conversation_id in self._workspaces
    
    def get_all_conversation_ids(self) -> list[str]:
        """Get all conversation IDs with active workspaces."""
        return list(self._workspaces.keys())
    
    @logfire.instrument("schedule_state_manager.load_from_ms")
    def load_from_ms(
        self,
        conversation_id: str,
        project_name: str,
        version_id: int,
        activities: list[dict],
        relationships: list[dict],
        calendar_info: Optional[dict] = None,
        project_constraints: Optional[dict] = None,
        constraint_types: Optional[list[dict]] = None,
    ) -> ScheduleWorkspace:
        """
        Load MS Project schedule from Supabase into a workspace.
        
        Converts MS Project data structure to workspace-compatible format
        that can be used with existing _ws tools (modify, Gantt, etc.)
        
        Args:
            conversation_id: Unique conversation identifier
            project_name: Project name for display
            version_id: Supabase schedule_versions.id
            activities: List of activity dicts from schedule_activities
            relationships: List of relationship dicts from schedule_links
            calendar_info: Optional calendar configuration
            
        Returns:
            Populated ScheduleWorkspace
        """
        def parse_date(value: object) -> Optional[date]:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return None
            if isinstance(value, date):
                return value
            parsed = pd.to_datetime(value, errors='coerce')
            if pd.isna(parsed):
                return None
            return parsed.date()

        def map_constraint_type(raw_value: object) -> Optional[str]:
            if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
                return None

            raw_str = str(raw_value).strip()
            if raw_str.startswith('CS_'):
                return raw_str

            normalized_by_id: dict[int, str] = {}
            for ct in constraint_types or []:
                ct_id = ct.get('id')
                if ct_id is None:
                    continue
                label_parts = [
                    str(ct.get('constraint_type') or ''),
                    str(ct.get('name') or ''),
                    str(ct.get('description') or ''),
                    str(ct.get('code') or ''),
                ]
                label = ' '.join(label_parts).lower()
                if 'start no earlier' in label:
                    normalized_by_id[int(ct_id)] = 'CS_SNET'
                elif 'must start' in label:
                    normalized_by_id[int(ct_id)] = 'CS_MSOA'
                elif 'as soon as possible' in label or 'asap' in label:
                    normalized_by_id[int(ct_id)] = 'CS_ASAP'

            if raw_str.isdigit():
                mapped = normalized_by_id.get(int(raw_str))
                if mapped:
                    return mapped

            lowered = raw_str.lower()
            if 'start no earlier' in lowered:
                return 'CS_SNET'
            if 'must start' in lowered:
                return 'CS_MSOA'
            if lowered in {'asap', 'as soon as possible'}:
                return 'CS_ASAP'
            return None

        # Convert activities to DataFrame with workspace-compatible column names
        activities_df = pd.DataFrame(activities) if activities else pd.DataFrame()
        
        if not activities_df.empty:
            # Rename MS columns to workspace-compatible names
            column_mapping = {
                'id': 'task_id',
                'name': 'task_name', 
                'ms_uid': 'task_code',  # Use ms_uid as task identifier
                'start': 'target_start_date',
                'finish': 'target_end_date',
                'percent_complete': 'phys_complete_pct',
                'total_float_d': 'total_float_days',
                'actual_start': 'act_start_date',
                'actual_finish': 'act_end_date',
                'constraint_date': 'constraint_date',
            }
            
            for old_name, new_name in column_mapping.items():
                if old_name in activities_df.columns:
                    activities_df[new_name] = activities_df[old_name]

            # Preserve original MS dates for validation after recalculation
            if 'start' in activities_df.columns:
                activities_df['original_start'] = activities_df['start']
            if 'finish' in activities_df.columns:
                activities_df['original_finish'] = activities_df['finish']
            
            # Convert duration from days to hours (8 hrs/day for workspace compatibility)
            if 'duration_d' in activities_df.columns:
                activities_df['target_drtn_hr_cnt'] = activities_df['duration_d'] * 8

            if 'phys_complete_pct' not in activities_df.columns:
                activities_df['phys_complete_pct'] = 0
            activities_df['phys_complete_pct'] = pd.to_numeric(
                activities_df['phys_complete_pct'],
                errors='coerce'
            ).fillna(0).clip(lower=0, upper=100)

            if 'target_drtn_hr_cnt' not in activities_df.columns:
                activities_df['target_drtn_hr_cnt'] = 0.0

            activities_df['remain_drtn_hr_cnt'] = (
                activities_df['target_drtn_hr_cnt'] *
                (1 - (activities_df['phys_complete_pct'] / 100.0))
            )

            activities_df['status_code'] = activities_df['phys_complete_pct'].apply(
                lambda pct: 'TK_NotStart' if pct <= 0 else ('TK_Complete' if pct >= 100 else 'TK_Active')
            )

            if 'constraint_type' in activities_df.columns:
                activities_df['constraint_type'] = activities_df['constraint_type'].apply(map_constraint_type)

            if 'constraint_date' in activities_df.columns:
                activities_df['constraint_date'] = activities_df['constraint_date'].apply(parse_date)

            for date_col in ['target_start_date', 'target_end_date', 'original_start', 'original_finish', 'act_start_date', 'act_end_date']:
                if date_col in activities_df.columns:
                    activities_df[date_col] = activities_df[date_col].apply(parse_date)
            
            # Parse baseline date columns (populated when DB version has a baseline)
            for bl_col in ['baseline_start', 'baseline_finish']:
                if bl_col in activities_df.columns:
                    activities_df[bl_col] = activities_df[bl_col].apply(parse_date)
            
            # Ensure required columns exist
            required_cols = [
                'task_id', 'task_code', 'task_name', 'target_drtn_hr_cnt',
                'remain_drtn_hr_cnt', 'target_start_date', 'target_end_date',
                'wbs', 'total_float_days', 'status_code', 'constraint_type',
                'constraint_date', 'original_start', 'original_finish'
            ]
            for col in required_cols:
                if col not in activities_df.columns:
                    activities_df[col] = None
            
            # Map wbs to wbs_path for filtering compatibility
            if 'wbs' in activities_df.columns:
                activities_df['wbs_path'] = activities_df['wbs']

        # Determine project start from constraints or activity minimum start
        project_start = None
        if project_constraints:
            for key in ('project_start', 'start_date', 'planned_start', 'schedule_start', 'data_date'):
                if key in project_constraints and project_constraints.get(key):
                    project_start = parse_date(project_constraints.get(key))
                    if project_start:
                        break

        if project_start is None and not activities_df.empty and 'target_start_date' in activities_df.columns:
            if 'is_summary' in activities_df.columns:
                activity_starts = activities_df[~activities_df['is_summary'].fillna(False).astype(bool)]['target_start_date']
            else:
                activity_starts = activities_df['target_start_date']
            activity_starts = activity_starts.dropna()
            if not activity_starts.empty:
                project_start = min(activity_starts)
        
        # Convert relationships to DataFrame
        relationships_df = pd.DataFrame(relationships) if relationships else pd.DataFrame()
        
        if not relationships_df.empty:
            # Rename columns for workspace compatibility
            rel_mapping = {
                'id': 'task_pred_id',
                'succ_id': 'task_id',
                'pred_id': 'pred_task_id',
                'rel_type': 'pred_type',
                'lag_d': 'lag_hr_cnt'
            }
            
            for old_name, new_name in rel_mapping.items():
                if old_name in relationships_df.columns:
                    relationships_df[new_name] = relationships_df[old_name]
            
            # Convert lag from days to hours
            if 'lag_d' in relationships_df.columns:
                relationships_df['lag_hr_cnt'] = relationships_df['lag_d'] * 8
            
            # Add pred_type prefix if needed (PR_FS format)
            if 'pred_type' in relationships_df.columns:
                relationships_df['pred_type'] = relationships_df['pred_type'].apply(
                    lambda x: f"PR_{x}" if x and not str(x).startswith('PR_') else x
                )

        calendar_exceptions: list[date] = []
        for exception in (calendar_info or {}).get('exceptions', []):
            exception_date = parse_date(exception.get('exception_date'))
            if exception_date:
                calendar_exceptions.append(exception_date)
        
        # Create workspace
        workspace = ScheduleWorkspace(
            conversation_id=conversation_id,
            project_name=project_name,
            activities_df=activities_df,
            relationships_df=relationships_df,
            activity_codes_df=pd.DataFrame(),
            code_types_with_values={},
            source="ms_loaded",
            source_version_id=version_id,
            project_start=project_start,
            calendar_exceptions=sorted(set(calendar_exceptions))
        )
        self._workspaces[conversation_id] = workspace
        
        logfire.info(
            "Loaded MS schedule into workspace",
            conversation_id=conversation_id,
            project_name=project_name,
            version_id=version_id,
            activity_count=len(activities_df),
            relationship_count=len(relationships_df),
            project_start=project_start.isoformat() if project_start else None,
            calendar_exception_count=len(calendar_exceptions)
        )
        
        return workspace


# Global instance for the application
# In production, consider dependency injection or request-scoped instances
schedule_state_manager = ScheduleStateManager()
