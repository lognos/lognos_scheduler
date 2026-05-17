from pydantic import BaseModel, Field, ConfigDict, field_validator, StrictStr
from typing import Literal, Optional, Union
from datetime import datetime


# ============================================================
# Agent Structured Output Models
# ============================================================

class TaskAction(BaseModel):
    """Represents an action taken on a P6 task."""
    model_config = ConfigDict(strict=True)
    
    task_code: StrictStr = Field(..., description="Task code affected")
    action: Literal["created", "updated", "deleted", "linked"] = Field(..., description="Action performed")
    details: Optional[str] = Field(None, description="Additional details about the action")


class ClarificationRequest(BaseModel):
    """Agent needs more information from the user."""
    model_config = ConfigDict(strict=True)
    
    question: StrictStr = Field(..., description="The clarifying question to ask")
    options: Optional[list[str]] = Field(None, description="Possible options for the user")
    context: Optional[str] = Field(None, description="Why this clarification is needed")


class SchedulingResponse(BaseModel):
    """Successful response with scheduling information."""
    model_config = ConfigDict(strict=True)
    
    message: StrictStr = Field(..., description="Natural language summary for the user")
    actions_taken: list[TaskAction] = Field(default_factory=list, description="List of actions performed")
    affected_tasks: list[str] = Field(default_factory=list, description="Task codes that were affected")


class ErrorResponse(BaseModel):
    """Response when an error occurred that the agent cannot recover from."""
    model_config = ConfigDict(strict=True)
    
    error_type: Literal["validation", "permission", "not_found", "system"] = Field(...)
    message: StrictStr = Field(..., description="User-friendly error message")
    suggestion: Optional[str] = Field(None, description="Suggested next steps")


# Union type for all possible agent outputs
AgentOutput = Union[SchedulingResponse, ClarificationRequest, ErrorResponse]


# ============================================================
# Tool Request Models
# ============================================================

class ActivityCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    
    task_code: str = Field(..., description="The Activity Code (string identifier, e.g. 'A1000'). Do NOT use 'task_id'.")
    task_name: str = Field(..., description="Description of the activity")
    wbs_id: int = Field(..., description="WBS ID where the activity belongs")
    proj_id: int = Field(..., description="Project ID")
    planned_duration: float = Field(default=8.0, description="Planned duration in hours")
    clndr_id: Optional[int] = Field(default=None, description="Calendar ID (optional, defaults to Project default)")

class RelationshipCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    
    pred_task_code: str = Field(..., description="Predecessor Activity ID")
    succ_task_code: str = Field(..., description="Successor Activity ID")
    proj_id: int = Field(..., description="Project ID context")
    pred_type: Literal["PR_FS", "PR_SS", "PR_FF", "PR_SF"] = Field(default="PR_FS", description="Relationship Type")
    lag: float = Field(default=0.0, description="Lag in hours")

class RelationshipDeleteRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    pred_task_code: str = Field(..., description="Predecessor Activity ID")
    succ_task_code: str = Field(..., description="Successor Activity ID")
    proj_id: int = Field(..., description="Project ID context")

class RelationshipUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    pred_task_code: str = Field(..., description="Predecessor Activity ID")
    succ_task_code: str = Field(..., description="Successor Activity ID")
    proj_id: int = Field(..., description="Project ID context")
    new_lag: Optional[float] = Field(None, description="New Lag in hours")
    new_type: Optional[Literal["PR_FS", "PR_SS", "PR_FF", "PR_SF"]] = Field(None, description="New Relationship Type")

class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    project_short_name: str = Field(..., description="Unique Project Short Name (e.g., 'PROJ-001')")
    project_name: str = Field(..., description="Full Project Name")
    planned_start_date: Optional[datetime] = Field(None, description="Planned Start Date")

    @field_validator('planned_start_date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            # Handle "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
            v = v.replace(' ', 'T')
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
        return v

class ProgressUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    
    task_code: str = Field(..., description="Activity ID to update")
    proj_id: int = Field(..., description="Project ID context")
    phys_complete_pct: float = Field(..., ge=0.0, le=100.0, description="Physical % Complete")
    actual_start: Optional[datetime] = Field(default=None, description="Actual Start Date")
    actual_finish: Optional[datetime] = Field(default=None, description="Actual Finish Date (if 100% complete)")

    @field_validator('actual_start', 'actual_finish', mode='before')
    @classmethod
    def parse_dates(cls, v):
        if isinstance(v, str):
            v = v.replace(' ', 'T')
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
        return v

class ActivityDetailsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    task_code: str = Field(..., description="Activity ID")
    proj_id: int = Field(..., description="Project ID")

class ActivityStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    
    task_code: str = Field(..., description="Activity ID")
    proj_id: int = Field(..., description="Project ID")
    
    # The target status drives the logic
    new_status: Literal["Not Started", "In Progress", "Completed"] = Field(..., description="Target Status")
    
    # Conditional Requirements based on new_status
    actual_start_date: Optional[datetime] = Field(None, description="Required if status is 'In Progress' or 'Completed'")
    actual_finish_date: Optional[datetime] = Field(None, description="Required if status is 'Completed'")
    
    # Optional: Update progress while changing status (e.g., Start and set to 50%)
    phys_complete_pct: Optional[float] = Field(None, description="Physical % Complete. Ignored if status is 'Completed' (sets to 100) or 'Not Started' (sets to 0)")

    @field_validator('actual_start_date', 'actual_finish_date', mode='before')
    @classmethod
    def parse_dates(cls, v):
        if isinstance(v, str):
            v = v.replace(' ', 'T')
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
        return v

class AgentResponse(BaseModel):
    response: str
    tool_calls: list[dict] = []

class SearchActivityRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    query: str = Field(..., description="Natural language query describing the activity (e.g., 'Update Earthworks')")
    proj_id: int = Field(..., description="Project ID context")

class IndexProjectRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    proj_id: int = Field(..., description="Project ID to index")

class ListProjectsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    include_eps_nodes: bool = Field(
        default=False, 
        description="If True, include EPS hierarchy nodes. Default shows only actual projects."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Activity Code Models
# ─────────────────────────────────────────────────────────────────────────────


class ListActivityCodesRequest(BaseModel):
    """Request to list available activity codes."""
    model_config = ConfigDict(strict=True)
    
    include_project_codes: bool = Field(
        default=False,
        description="If True, include project-specific codes (requires proj_id). Default shows only global codes."
    )
    proj_id: int | None = Field(
        default=None,
        description="Project ID for project-specific codes. Required if include_project_codes=True."
    )


class AssignActivityCodeRequest(BaseModel):
    """Request to assign activity codes to a single activity."""
    model_config = ConfigDict(strict=True)
    
    task_code: StrictStr = Field(
        ..., 
        description="Activity code (TASK.TASK_CODE) to assign codes to"
    )
    proj_id: int = Field(
        ..., 
        description="Project ID containing the activity"
    )
    code_assignments: dict[str, str] = Field(
        ..., 
        description="Map of code type name to code value. Example: {'PHASE': 'CON', 'DISCIPLINE': 'CIV'}"
    )
    replace_existing: bool = Field(
        default=True,
        description="If True (default), replace existing code for each type. If False, fail if code already assigned."
    )


class RemoveActivityCodeRequest(BaseModel):
    """Request to remove activity codes from an activity."""
    model_config = ConfigDict(strict=True)
    
    task_code: StrictStr = Field(
        ..., 
        description="Activity code (TASK.TASK_CODE) to remove codes from"
    )
    proj_id: int = Field(
        ..., 
        description="Project ID containing the activity"
    )
    code_type_names: list[StrictStr] = Field(
        ..., 
        description="List of code type names to remove (e.g., ['PHASE', 'DISCIPLINE'])"
    )


class BulkAssignActivityCodeRequest(BaseModel):
    """Request to assign activity codes to multiple activities."""
    model_config = ConfigDict(strict=True)
    
    proj_id: int = Field(
        ..., 
        description="Project ID containing the activities"
    )
    code_assignments: dict[str, str] = Field(
        ..., 
        description="Map of code type name to code value. Example: {'PHASE': 'CON', 'DISCIPLINE': 'CIV'}"
    )
    replace_existing: bool = Field(
        default=True,
        description="If True (default), replace existing code for each type. If False, fail if code already assigned."
    )
    # Target selection - one of these must be provided
    task_codes: list[StrictStr] | None = Field(
        default=None,
        description="List of activity codes to assign to. Mutually exclusive with wbs_id."
    )
    wbs_id: int | None = Field(
        default=None,
        description="WBS ID - assign to all activities under this WBS. Mutually exclusive with task_codes."
    )


class GetActivityCurrentCodesRequest(BaseModel):
    """Request to get current activity code assignments for activities."""
    model_config = ConfigDict(strict=True)
    
    task_codes: list[StrictStr] = Field(
        ..., 
        description="List of activity codes to get current assignments for"
    )
    proj_id: int = Field(
        ..., 
        description="Project ID containing the activities"
    )


class ListActivitiesRequest(BaseModel):
    """Request to list activities in a project, optionally filtered by WBS."""
    model_config = ConfigDict(strict=True)
    
    proj_id: int = Field(
        ..., 
        description="Project ID to list activities from"
    )
    wbs_name: StrictStr | None = Field(
        default=None,
        description="Filter by WBS name (WBS_SHORT_NAME). Use partial match. E.g., 'FOUNDATION' or 'PHASE1.CIVIL'"
    )
    wbs_id: int | None = Field(
        default=None,
        description="Filter by WBS ID. If provided, lists activities under this WBS (including nested WBS)."
    )
    include_activity_codes: bool = Field(
        default=True,
        description="If True (default), include activity code assignments for each activity."
    )
    limit: int = Field(
        default=100,
        description="Maximum number of activities to return. Default 100."
    )


# ============================================================================
# Workspace Request Models
# ============================================================================
# Naming convention: {Action}{Entity}WsRequest
# All workspace tools should use these request models for consistency with P6 tools


class LoadScheduleWsRequest(BaseModel):
    """Request to load a P6 schedule into the workspace for analysis."""
    model_config = ConfigDict(strict=True)
    
    proj_id: int = Field(
        ..., 
        description="Project ID to load schedule from"
    )


class CreateScheduleWsRequest(BaseModel):
    """Request to create a new empty schedule workspace for draft planning."""
    model_config = ConfigDict(strict=True)
    
    project_name: StrictStr = Field(
        ...,
        description="Name for the new schedule (e.g., '2km Trail Construction')"
    )
    project_start_date: str | None = Field(
        default=None,
        description="Planned start date in ISO format (YYYY-MM-DD). Used as reference for CPM calculation."
    )
    description: str | None = Field(
        default=None,
        description="Optional description of the schedule purpose (stored for future save to P6)"
    )


class GanttRenderOptions(BaseModel):
    """Optional render intent for custom Gantt views."""
    model_config = ConfigDict(strict=True)

    columns: list[Literal["start", "finish", "duration", "total_float", "percent_complete"]] | None = Field(
        default=None,
        description="Optional list of columns requested by the client for rendering."
    )
    show_links: bool = Field(
        default=True,
        description="If True, enable dependency link rendering when link data is available."
    )
    show_updates: bool = Field(
        default=True,
        description="If True, enable activity update indicators when update data is available."
    )
    baseline_mode: Literal["own", "previous_version", "database_baseline", "what_if"] = Field(
        default="own",
        description="Requested baseline comparison mode for rendering."
    )


class GanttDataEnvelopeRequest(BaseModel):
    """Optional data envelope requirements for custom Gantt views."""
    model_config = ConfigDict(strict=True)

    include_links: bool = Field(
        default=True,
        description="If True, include relationship/link data in the payload envelope."
    )
    include_updates: bool = Field(
        default=True,
        description="If True, include update data in the payload envelope."
    )
    include_baselines: list[Literal["own", "previous_version", "database_baseline", "what_if"]] | None = Field(
        default=None,
        description="Baseline datasets requested in the payload envelope."
    )
    include_optional_fields: list[Literal["percent_complete", "free_float_days"]] | None = Field(
        default=None,
        description="Optional activity fields requested in the payload envelope."
    )
    include_hierarchy: bool = Field(
        default=True,
        description="If True, include hierarchy metadata in envelope activities when available."
    )


class CalculateGanttWsRequest(BaseModel):
    """Request to run CPM calculations and display Gantt chart with optional grouping and filtering."""
    model_config = ConfigDict(strict=True)

    view_id: str | None = Field(
        default=None,
        description="Optional custom view identifier for traceability."
    )
    
    title: str = Field(
        default="Schedule Analysis",
        description="Title for the Gantt chart display"
    )
    group_by: str | None = Field(
        default=None,
        description="Optional grouping field. Use 'wbs' to group by WBS path, or an activity code type name (e.g., 'Phase', 'Discipline') to group activities by that code."
    )
    show_details: bool = Field(
        default=True,
        description="If True (default), show both summary and detail activities. If False, show only summary level."
    )
    
    # Filter parameters
    activity_codes: dict[str, list[str]] | None = Field(
        default=None,
        description=(
            "Filter by activity codes. Dict mapping code type name to list of values. "
            "Example: {'Discipline': ['Mechanical', 'Electrical'], 'Phase': ['Construction']}. "
            "Logic: AND between code types, OR within values."
        )
    )
    date_start: str | None = Field(
        default=None,
        description="Filter activities starting on or after this date (ISO format: YYYY-MM-DD)"
    )
    date_end: str | None = Field(
        default=None,
        description="Filter activities finishing on or before this date (ISO format: YYYY-MM-DD)"
    )
    critical_only: bool = Field(
        default=False,
        description="If True, show only critical path activities"
    )
    status: list[str] | None = Field(
        default=None,
        description="Filter by status: ['not_started', 'in_progress', 'completed']. Default shows all."
    )
    search_term: str | None = Field(
        default=None,
        description="Search term to filter by activity code or name (case-insensitive partial match)"
    )
    wbs_path: str | None = Field(
        default=None,
        description="Filter by WBS path prefix (e.g., 'Project/Phase1/Civil')"
    )
    render_options: GanttRenderOptions | None = Field(
        default=None,
        description="Optional rendering intent such as selected columns, links visibility, and baseline mode."
    )
    data_envelope: GanttDataEnvelopeRequest | None = Field(
        default=None,
        description="Optional data envelope requirements that define which datasets must be present in response."
    )
    render_gantt: bool = Field(
        default=True,
        description=(
            "If true (default), push the Gantt chart to the frontend after calculation. "
            "Set to false to recalculate CPM dates silently without updating the displayed chart. "
            "Useful when another tool (e.g. get_driving_path_ws) will render a focused view afterwards."
        )
    )


class SnapshotBaselineWsRequest(BaseModel):
    """Request to snapshot the current calculated dates as baseline for what-if comparison."""
    model_config = ConfigDict(strict=True)

    label: str = Field(
        default="Baseline",
        description="Human-readable label for the baseline snapshot (e.g. 'Current Plan', 'Before adding crane')"
    )


class WhatIfComparisonWsRequest(BaseModel):
    """Request to compare current calculated schedule against the stored baseline snapshot."""
    model_config = ConfigDict(strict=True)

    threshold_days: int = Field(
        default=0,
        ge=0,
        description="Only return activities whose start or finish shifted by more than this many days. 0 returns all."
    )
    critical_only: bool = Field(
        default=False,
        description="If true, only compare activities on the current critical path."
    )


class GetDrivingPathWsRequest(BaseModel):
    """Request to find the driving path (predecessor chain) to a target activity."""
    model_config = ConfigDict(strict=True)

    target_task_id: int = Field(
        ...,
        description="Task ID of the target activity to trace the driving path to."
    )
    render_gantt: bool = Field(
        default=True,
        description="If true, automatically render a Gantt chart filtered to only the driving path activities."
    )
    date_start: str | None = Field(
        default=None,
        description=(
            "Optional ISO date (YYYY-MM-DD). When set, the Gantt visualization "
            "only shows driving-path activities whose early_start >= this date. "
            "The text report always includes the full chain regardless."
        ),
    )
    date_end: str | None = Field(
        default=None,
        description=(
            "Optional ISO date (YYYY-MM-DD). When set, the Gantt visualization "
            "only shows driving-path activities whose early_finish <= this date."
        ),
    )
    include_summary_parents: bool = Field(
        default=True,
        description=(
            "Include parent/summary activities for context. Walks up the WBS "
            "hierarchy so the Gantt shows where each activity sits in the project structure."
        ),
    )


class ModifyActivityWsRequest(BaseModel):
    """Request to modify an activity in the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_id: int = Field(
        ..., 
        description="Task ID of the activity to modify"
    )
    original_duration: int | None = Field(
        default=None,
        ge=1,
        description="New original duration in hours"
    )
    target_start_date: str | None = Field(
        default=None,
        description="New target start date in ISO format (YYYY-MM-DD)"
    )
    target_end_date: str | None = Field(
        default=None,
        description="New target end date in ISO format (YYYY-MM-DD)"
    )
    task_name: str | None = Field(
        default=None,
        description="New activity name"
    )


class AddActivityWsRequest(BaseModel):
    """Request to add a new activity to the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_code: StrictStr = Field(
        ..., 
        description="Unique activity code for the new activity (e.g., 'A1000')"
    )
    task_name: StrictStr = Field(
        ..., 
        description="Name of the new activity"
    )
    original_duration_hours: int = Field(
        ...,
        ge=1,
        description="Duration in hours (e.g., 40 for 5 days at 8h/day)"
    )
    wbs_id: int | None = Field(
        default=None,
        description="WBS ID to assign the activity to"
    )
    target_start_date: str | None = Field(
        default=None,
        description="Target start date in ISO format (YYYY-MM-DD)"
    )
    activity_codes: dict[str, str] | None = Field(
        default=None,
        description="Dict mapping code type name to code value for grouping. Example: {'Phase': 'Phase 1', 'Discipline': 'Civil'}"
    )


class AddRelationshipWsRequest(BaseModel):
    """Request to add a relationship between activities in the workspace."""
    model_config = ConfigDict(strict=True)
    
    predecessor_task_id: int = Field(
        ..., 
        description="Task ID of the predecessor activity"
    )
    successor_task_id: int = Field(
        ..., 
        description="Task ID of the successor activity"
    )
    relationship_type: Literal["FS", "SS", "FF", "SF"] = Field(
        default="FS",
        description="Relationship type: FS (Finish-to-Start), SS (Start-to-Start), FF (Finish-to-Finish), SF (Start-to-Finish)"
    )
    lag_hours: int = Field(
        default=0,
        description="Lag time in hours (positive = delay, negative = lead)"
    )


class ModifyRelationshipWsRequest(BaseModel):
    """Request to modify an existing relationship in the workspace."""
    model_config = ConfigDict(strict=True)
    
    predecessor_task_id: int = Field(
        ..., 
        description="Task ID of the predecessor activity"
    )
    successor_task_id: int = Field(
        ..., 
        description="Task ID of the successor activity"
    )
    new_relationship_type: Literal["FS", "SS", "FF", "SF"] | None = Field(
        default=None,
        description="New relationship type (FS, SS, FF, SF)"
    )
    new_lag_hours: int | None = Field(
        default=None,
        description="New lag in hours (positive = delay, negative = lead)"
    )


class DeleteRelationshipWsRequest(BaseModel):
    """Request to delete a relationship from the workspace."""
    model_config = ConfigDict(strict=True)
    
    predecessor_task_id: int = Field(
        ..., 
        description="Task ID of the predecessor activity"
    )
    successor_task_id: int = Field(
        ..., 
        description="Task ID of the successor activity"
    )


class DeleteActivityWsRequest(BaseModel):
    """Request to delete an activity from the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_id: int = Field(
        ..., 
        description="Task ID of the activity to delete"
    )


# Workspace Activity Code Models

class AssignActivityCodesWsRequest(BaseModel):
    """Request to assign activity codes to an activity in the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_id: int = Field(
        ..., 
        description="Task ID of the activity to assign codes to"
    )
    code_assignments: dict[str, str] = Field(
        ..., 
        description="Dict mapping code type name to code value name. Example: {'Activity_Type': 'Stations construction', 'Phase': 'Phase 1'}"
    )


class BulkAssignActivityCodesWsRequest(BaseModel):
    """Request to assign activity codes to multiple activities in the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_ids: list[int] = Field(
        ..., 
        min_length=1,
        description="List of Task IDs to assign codes to"
    )
    code_assignments: dict[str, str] = Field(
        ..., 
        description="Dict mapping code type name to code value name. Example: {'Activity_Type': 'Trail construction', 'Phase': 'Phase 1'}"
    )


class RemoveActivityCodesWsRequest(BaseModel):
    """Request to remove activity codes from an activity in the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_id: int = Field(
        ..., 
        description="Task ID of the activity to remove codes from"
    )
    code_type_names: list[str] = Field(
        ..., 
        min_length=1,
        description="List of code type names to remove (e.g., ['Activity_Type', 'Phase'])"
    )


class GetActivityCodesWsRequest(BaseModel):
    """Request to get current activity code assignments in the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_id: int | None = Field(
        default=None,
        description="Optional Task ID to get codes for. If None, returns summary of all codes."
    )


# ============================================================================
# MS Project Schedule Request Models (Supabase)
# ============================================================================

class ListScheduleVersionsMsRequest(BaseModel):
    """Request to list schedule versions for an MS Project."""
    model_config = ConfigDict(strict=True)
    
    project_name: str = Field(..., description="Project name (e.g., 'BIO4-01-0002')")
    include_temp: bool = Field(default=True, description="Include temporary/draft subversions")


class GetScheduleOverviewMsRequest(BaseModel):
    """Request for 3-week lookahead schedule overview."""
    model_config = ConfigDict(strict=True)
    
    project_name: str = Field(..., description="Project name")
    version_id: int | None = Field(None, description="Specific version ID (default: current)")
    reference_date: str | None = Field(None, description="Reference date YYYY-MM-DD (default: today)")
    weeks_back: int = Field(default=1, ge=0, le=4, description="Weeks to look back")
    weeks_forward: int = Field(default=2, ge=1, le=8, description="Weeks to look forward")


class ListActivitiesMsRequest(BaseModel):
    """Request to list activities with filters."""
    model_config = ConfigDict(strict=True)
    
    version_id: int = Field(..., description="Schedule version ID")
    wbs_prefix: str | None = Field(None, description="Filter by WBS prefix (e.g., '1.3')")
    date_start: str | None = Field(None, description="Filter activities starting on/after this date")
    date_end: str | None = Field(None, description="Filter activities finishing on/before this date")
    critical_only: bool = Field(default=False, description="Only critical path activities")
    status: Literal["not_started", "in_progress", "complete"] | None = Field(None)
    owner: str | None = Field(None, description="Filter by activity owner")
    scope_owner: str | None = Field(None, description="Filter by scope owner")
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class GetActivityMsRequest(BaseModel):
    """Request to get a single activity."""
    model_config = ConfigDict(strict=True)
    
    activity_id: int | None = Field(None, description="Internal activity ID")
    ms_uid: int | None = Field(None, description="MS Project UID")
    version_id: int | None = Field(None, description="Version ID (required if using ms_uid)")


class LoadScheduleMsRequest(BaseModel):
    """Request to load MS schedule into workspace."""
    model_config = ConfigDict(strict=True)
    
    project_name: str = Field(..., description="Project name")
    version_id: int | None = Field(None, description="Version to load (default: current)")


class CreateSubversionMsRequest(BaseModel):
    """Request to save workspace as a new subversion."""
    model_config = ConfigDict(strict=True)
    
    version_name: str | None = Field(None, description="Name for subversion (auto-generated if not provided)")
    description: str = Field(..., description="Description of changes made")


class PromoteSubversionMsRequest(BaseModel):
    """Request to promote a subversion to current."""
    model_config = ConfigDict(strict=True)
    
    version_id: int = Field(..., description="Version ID to promote to current")
    expected_current_version_id: int | None = Field(
        None, 
        description="Expected current version for optimistic locking"
    )


class GetProjectConstraintsMsRequest(BaseModel):
    """Request to get project constraints."""
    model_config = ConfigDict(strict=True)
    
    version_id: int = Field(..., description="Schedule version ID")


class GetCalendarMsRequest(BaseModel):
    """Request to get calendar information."""
    model_config = ConfigDict(strict=True)
    
    version_id: int = Field(..., description="Schedule version ID")


# ============================================================================
# Legacy Workspace Models (deprecated - kept for backward compatibility)
# ============================================================================

# These will be removed in a future version. Use the *WsRequest models above.
LoadScheduleToWorkspaceRequest = LoadScheduleWsRequest
CalculateAndDisplayGanttRequest = CalculateGanttWsRequest
ModifyActivityInWorkspaceRequest = ModifyActivityWsRequest
AddActivityToWorkspaceRequest = AddActivityWsRequest
AddRelationshipToWorkspaceRequest = AddRelationshipWsRequest
