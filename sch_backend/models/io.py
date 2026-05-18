from pydantic import BaseModel, Field, ConfigDict, StrictStr
from typing import Literal, Optional, Union


# ============================================================
# Agent Structured Output Models
# ============================================================

class TaskAction(BaseModel):
    """Represents an action taken on a schedule task."""
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

class AgentResponse(BaseModel):
    response: str
    tool_calls: list[dict] = []


# ============================================================================
# Workspace Request Models
# ============================================================================
# Naming convention: {Action}{Entity}WsRequest


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
        description="Optional description of the schedule purpose"
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


class SearchActivitiesMsRequest(BaseModel):
    """Request to semantically search MS schedule activities."""
    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1, description="Natural language description of the activity to find")
    project_name: str | None = Field(None, description="Project name used to resolve the current version when version_id is omitted")
    version_id: int | None = Field(None, description="Specific schedule version ID to search")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum matching activities to return")
    match_threshold: float = Field(default=0.2, ge=0.0, le=1.0, description="Minimum cosine similarity threshold")
    wbs_prefix: str | None = Field(None, description="Optional WBS prefix filter")
    owner: str | None = Field(None, description="Optional activity owner filter")
    scope_owner: str | None = Field(None, description="Optional scope owner filter")


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
CalculateAndDisplayGanttRequest = CalculateGanttWsRequest
ModifyActivityInWorkspaceRequest = ModifyActivityWsRequest
AddActivityToWorkspaceRequest = AddActivityWsRequest
AddRelationshipToWorkspaceRequest = AddRelationshipWsRequest
