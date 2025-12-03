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
