from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, Literal


# ============================================================
# P6 Domain Models
# ============================================================

class P6Activity(BaseModel):
    task_id: int
    proj_id: int
    wbs_id: int
    clndr_id: Optional[int]
    task_code: str
    task_name: str
    status_code: str
    task_type: str
    duration_type: str
    target_drtn_hr_cnt: float
    remain_drtn_hr_cnt: float
    phys_complete_pct: float
    create_date: datetime
    update_date: datetime
    create_user: str
    update_user: str

class P6Relationship(BaseModel):
    task_pred_id: int
    task_id: int
    pred_task_id: int
    proj_id: int
    pred_proj_id: int
    pred_type: str
    lag_hr_cnt: float


# ============================================================
# Project Domain Models
# ============================================================

class Project(BaseModel):
    """Project domain model."""
    project_id: str
    project_name: str
    company_id: Optional[str] = None
    project_overview: Optional[str] = None
    metadata: dict = {}
    created_at: Optional[str] = None


# ============================================================
# Conversation Domain Models
# ============================================================

class ConversationCreate(BaseModel):
    """Input model for creating a conversation."""
    model_config = ConfigDict(strict=True)
    
    conversation_id: str
    creator_email: str
    project_id: Optional[str] = None
    p6_schedule_id: Optional[str] = None
    title: str = "New conversation"


class ConversationUpdate(BaseModel):
    """Input model for updating a conversation."""
    model_config = ConfigDict(strict=True)
    
    title: Optional[str] = None
    visible: Optional[bool] = None
    status: Optional[str] = None


class ConversationSummary(BaseModel):
    """Summary view of a conversation for listing."""
    conversation_id: str
    title: str
    last_message_at: Optional[str] = None
    message_count: int
    status: str


class MessageCreate(BaseModel):
    """Input model for creating a message."""
    model_config = ConfigDict(strict=True)
    
    conversation_id: str
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    model_name: Optional[str] = None
    metadata: Optional[dict] = None


class MessageRecord(BaseModel):
    """Message as stored in database."""
    message_id: str
    conversation_id: str
    role: str
    content: str
    timestamp: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    model_name: Optional[str] = None
    metadata: dict = {}


class ConversationWithMessages(BaseModel):
    """Full conversation with all messages."""
    conversation_id: str
    creator_email: str
    project_id: Optional[str] = None
    p6_schedule_id: Optional[str] = None
    title: str
    message_count: int
    last_message_at: Optional[str] = None
    status: str
    created_at: str
    messages: list[MessageRecord]


# ============================================================
# P6 Schedule Domain Models
# ============================================================

class P6Schedule(BaseModel):
    """P6 Schedule mapping record."""
    id: str
    project_id: str
    p6_proj_id: int
    p6_proj_short_name: Optional[str] = None
    schedule_name: str
    schedule_type: str = "current"
    is_active: bool = True
    created_at: str
    updated_at: str
    metadata: dict = {}


class P6ScheduleCreate(BaseModel):
    """Input model for creating a P6 schedule mapping."""
    model_config = ConfigDict(strict=True)
    
    project_id: str
    p6_proj_id: int
    p6_proj_short_name: Optional[str] = None
    schedule_name: str
    schedule_type: str = "current"
