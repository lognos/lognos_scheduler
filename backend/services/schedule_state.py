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
class ScheduleWorkspace:
    """
    In-memory working state for a schedule being edited.
    
    Maintains DataFrames + metadata per conversation session.
    
    Activity Codes are loaded from P6 tables:
    - ACTVTYPE: Code type definitions (Phase, Area, Responsibility, etc.)
    - ACTVCODE: Code values (hierarchical, e.g., Construction -> Civil)
    - TASKACTV: Code assignments to tasks (one value per code type per task)
    
    All filtering happens on these DataFrames - no database queries.
    """
    conversation_id: str
    project_id: Optional[int] = None  # None if creating new schedule
    project_name: Optional[str] = None
    
    # Core schedule data
    activities_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    relationships_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # Activity Code data (loaded from P6, used for filtering)
    # Columns: task_id, code_type_name, code_value_name
    activity_codes_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # Available code types and their values for UI filter dropdowns
    # Example: {"Phase": ["Design", "Construction", "Closeout"], "Area": ["Building A", "Building B"]}
    code_types_with_values: dict[str, list[str]] = field(default_factory=dict)
    
    # State tracking
    is_modified: bool = False
    source: str = "new"  # "new" | "p6_loaded"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Calculation results (populated after CPM calculation)
    last_calculation_at: Optional[datetime] = None
    project_start: Optional[date] = None
    project_finish: Optional[date] = None
    critical_path_ids: list[int] = field(default_factory=list)
    
    def mark_modified(self) -> None:
        """Mark workspace as modified (needs recalculation/save)."""
        self.is_modified = True
        self.updated_at = datetime.now()
    
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
            df = df[df['wbs_path'].fillna('').str.startswith(wbs_path)]
        
        # Date range filters (using early_start/early_finish from calculation)
        if date_start and 'early_start' in df.columns:
            date_start_parsed = pd.to_datetime(date_start).date()
            df = df[df['early_start'] >= date_start_parsed]
        
        if date_end and 'early_finish' in df.columns:
            date_end_parsed = pd.to_datetime(date_end).date()
            df = df[df['early_finish'] <= date_end_parsed]
        
        # Critical path filter
        if critical_only and 'is_critical' in df.columns:
            df = df[df['is_critical'] == True]
        
        # Status filter
        if status and 'status' in df.columns:
            df = df[df['status'].isin(status)]
        
        # Search term filter
        if search_term:
            mask = pd.Series([False] * len(df), index=df.index)
            if 'task_code' in df.columns:
                mask |= df['task_code'].fillna('').str.contains(search_term, case=False, na=False)
            if 'task_name' in df.columns:
                mask |= df['task_name'].fillna('').str.contains(search_term, case=False, na=False)
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
    
    @logfire.instrument("schedule_state_manager.load_from_p6")
    def load_from_p6(
        self, 
        conversation_id: str,
        project_id: int,
        project_name: str,
        activities_df: pd.DataFrame,
        relationships_df: pd.DataFrame,
        activity_codes_df: Optional[pd.DataFrame] = None,
        code_types_with_values: Optional[dict[str, list[str]]] = None,
        project_start: Optional[date] = None,
        project_finish: Optional[date] = None
    ) -> ScheduleWorkspace:
        """
        Load schedule data from P6 into a workspace.
        
        This is the ONLY time we query the database for this conversation.
        All subsequent operations work on the in-memory DataFrames.
        
        Args:
            conversation_id: Unique conversation identifier
            project_id: P6 project ID
            project_name: Project name for display
            activities_df: DataFrame with activity data
                Required columns: task_id, task_code, task_name, duration_hours
                Optional: wbs_id, wbs_path, status_code, constraint_type, constraint_date
            relationships_df: DataFrame with relationship data
                Required columns: task_id, pred_task_id
                Optional: pred_type, lag_hr_cnt
            activity_codes_df: DataFrame with code assignments
                Required columns: task_id, code_type_name, code_value_name
            code_types_with_values: Dict of available code types and values
                Used by frontend to populate filter dropdowns
                
        Returns:
            Populated ScheduleWorkspace
        """
        workspace = ScheduleWorkspace(
            conversation_id=conversation_id,
            project_id=project_id,
            project_name=project_name,
            activities_df=activities_df,
            relationships_df=relationships_df,
            activity_codes_df=activity_codes_df if activity_codes_df is not None else pd.DataFrame(),
            code_types_with_values=code_types_with_values or {},
            source="p6_loaded",
            project_start=project_start,
            project_finish=project_finish
        )
        self._workspaces[conversation_id] = workspace
        
        logfire.info(
            "Loaded P6 schedule into workspace",
            conversation_id=conversation_id,
            project_id=project_id,
            activity_count=len(activities_df),
            relationship_count=len(relationships_df),
            code_types=list(code_types_with_values.keys()) if code_types_with_values else []
        )
        
        return workspace
    
    def create_new(
        self,
        conversation_id: str,
        project_name: Optional[str] = None
    ) -> ScheduleWorkspace:
        """
        Create a new empty workspace for building a schedule from scratch.
        
        Use case (c): Create new schedules before saving to P6.
        """
        workspace = ScheduleWorkspace(
            conversation_id=conversation_id,
            project_name=project_name or "New Schedule",
            source="new"
        )
        self._workspaces[conversation_id] = workspace
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


# Global instance for the application
# In production, consider dependency injection or request-scoped instances
schedule_state_manager = ScheduleStateManager()
