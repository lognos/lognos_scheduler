from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal, Optional, Union
from datetime import datetime

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
