from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal


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


class UserContext(BaseModel):
    """Resolved user context from lognos_comm.users."""
    model_config = ConfigDict(strict=True)

    email: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    role: Optional[str] = None
    app_role: Optional[str] = None
    department: Optional[str] = None
    reports_to: Optional[str] = None
    active: bool = True
    current_project_id: Optional[str] = None


class TeamMemberContext(BaseModel):
    """Project team member context resolved from users and user_project_access."""
    model_config = ConfigDict(strict=True)

    email: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    role: Optional[str] = None
    app_role: Optional[str] = None
    department: Optional[str] = None
    reports_to: Optional[str] = None
    active: bool = True
    project_id: Optional[str] = None
    access_level: Optional[str] = None
    project_role: Optional[str] = None
    project_reports_to: Optional[str] = None
    can_own_risks: Optional[bool] = None
    can_review_risks: Optional[bool] = None
    project_purview: Optional[dict] = None


# ============================================================
# Conversation Domain Models
# ============================================================

class ConversationCreate(BaseModel):
    """Input model for creating a conversation."""
    model_config = ConfigDict(strict=True)
    
    conversation_id: str
    creator_email: str
    project_id: Optional[str] = None
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
    title: str
    message_count: int
    last_message_at: Optional[str] = None
    status: str
    created_at: str
    messages: list[MessageRecord]
