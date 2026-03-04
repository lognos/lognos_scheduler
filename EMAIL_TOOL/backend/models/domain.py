"""
Domain models for business entities.

This module contains DTOs (Data Transfer Objects) that represent
core business entities with strict type safety and validation.
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
import json
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import StrictStr
from typing import Literal

# Communications models


class Project(BaseModel):
    """
    DTO for project information.
    """

    model_config = ConfigDict(strict=False, frozen=True)

    project_id: StrictStr = Field(description="Unique project identifier")
    project_name: StrictStr = Field(description="Display name of the project")
    company_id: StrictStr | None = Field(None, description="Company ID")
    project_overview: StrictStr | None = Field(None, description="Project description")

    # Metadata
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class CommunicationRecord(BaseModel):
    """
    DTO for communication records from agent_comm_memory table.

    **IMPORTANT**: This model reflects the ACTUAL database schema (agent_comm_memory),
    which is AI-focused with embeddings, extracted data, and rich metadata.

    Design decisions:
    - strict=False: Allow flexible input validation
    - frozen=True: Immutable after creation
    - Matches actual table: memory_id, source_id, etc.
    - Provides computed properties for backward compatibility with legacy code
    """

    model_config = ConfigDict(
        strict=False,
        frozen=True,
        str_strip_whitespace=True,
        extra="ignore",
    )

    # Primary key
    memory_id: UUID = Field(description="Unique memory ID (UUID primary key)")

    # Core fields
    source_id: StrictStr = Field(
        description="Original source ID (e.g. Message-ID or Thread-ID)"
    )
    source_type: StrictStr = Field(
        description="Type of source (email_thread, chat_conversation)"
    )
    project_id: StrictStr | None = Field(None, description="Project ID")

    summary: StrictStr = Field(description="AI generated summary")
    summary_embedding: list[float] | None = Field(None, description="Vector embedding")

    # JSONB fields
    participants: list[dict] = Field(
        default_factory=list, description="List of participants with roles"
    )
    risks_issues: list[dict] = Field(
        default_factory=list, description="Extracted risks and issues"
    )
    metadata: dict = Field(default_factory=dict, description="Additional metadata")

    # Timestamps
    created_at: datetime = Field(description="Record creation timestamp")
    updated_at: datetime | None = Field(None, description="Record update timestamp")
    last_processed_at: datetime | None = Field(
        None, description="Last AI processing timestamp"
    )
    source_last_updated_at: datetime | None = Field(
        None, description="Last update time of the source content"
    )

    # ========================================================================
    # Legacy Compatibility Properties
    # These properties map the new schema to the old interface expected by agents
    # ========================================================================

    @property
    def communication_id(self) -> UUID:
        """Alias for memory_id."""
        return self.memory_id

    @property
    def communication_method(self) -> str:
        """Alias for source_type."""
        return self.source_type

    @property
    def originator_email(self) -> str:
        """Extract sender email from participants."""
        for p in self.participants:
            if isinstance(p, dict) and p.get("role") == "sender":
                return p.get("email", "unknown")
        # Fallback to first participant if no sender found
        if self.participants and isinstance(self.participants[0], dict):
            return self.participants[0].get("email", "unknown")
        return "unknown"

    @property
    def comm_subject(self) -> str | None:
        """Extract subject from metadata."""
        return self.metadata.get("subject")

    @property
    def summary_text(self) -> str:
        """Alias for summary."""
        return self.summary

    @property
    def first_message_time(self) -> datetime | None:
        """Extract first message time from metadata or fallback to last update."""
        if val := self.metadata.get("first_message_time"):
            try:
                # Handle ISO string parsing
                if isinstance(val, str):
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                return val
            except (ValueError, TypeError):
                pass
        return self.source_last_updated_at

    @property
    def latest_message_time(self) -> datetime | None:
        """Alias for source_last_updated_at."""
        return self.source_last_updated_at

    @property
    def risks_issues_actions(self) -> list[dict]:
        """Alias for risks_issues."""
        return self.risks_issues

    @property
    def attachments_referenced(self) -> list[dict] | None:
        """Extract attachments from metadata."""
        return self.metadata.get("attachments")

    @property
    def related_communications(self) -> list[dict] | None:
        """Extract related comms from metadata."""
        return self.metadata.get("related_communications")

    @property
    def tags(self) -> list[str] | None:
        """Extract tags from metadata."""
        return self.metadata.get("tags")

    @property
    def source_comm_id(self) -> str:
        """Alias for source_id."""
        return self.source_id

    # ========================================================================
    # Computed Properties
    # ========================================================================

    @property
    def is_recent(self) -> bool:
        """Check if communication is from last 7 days."""
        if not self.source_last_updated_at:
            return False
        age = datetime.now(timezone.utc) - self.source_last_updated_at
        return age.days < 7

    @property
    def participant_count(self) -> int:
        """Number of participants in communication."""
        return len(self.participants)

    @property
    def has_risks(self) -> bool:
        """True if risks/issues were extracted."""
        return len(self.risks_issues) > 0

    @property
    def has_embedding(self) -> bool:
        """True if summary embedding exists."""
        return self.summary_embedding is not None

    @property
    def thread_duration_days(self) -> int | None:
        """Duration of communication thread in days."""
        if not self.latest_message_time or not self.first_message_time:
            return None
        duration = self.latest_message_time - self.first_message_time
        return duration.days

    @property
    def age_days(self) -> int | None:
        """Age of communication since last message in days."""
        if not self.latest_message_time:
            return None
        age = datetime.now(timezone.utc) - self.latest_message_time
        return age.days

    def summary_dict(self) -> dict:
        """
        Return simplified dict for agent consumption.
        """
        return {
            "id": str(self.memory_id),
            "project_id": self.project_id,
            "method": self.source_type,
            "from": self.originator_email,
            "participants": self.participants,
            "subject": self.comm_subject,
            "summary": self.summary[:200] + "..."
            if len(self.summary) > 200
            else self.summary,
            "first_message": self.first_message_time.isoformat()
            if self.first_message_time
            else None,
            "last_activity": self.source_last_updated_at.isoformat()
            if self.source_last_updated_at
            else None,
            "is_recent": self.is_recent,
            "age_days": self.age_days,
            "thread_duration_days": self.thread_duration_days,
            "has_risks": self.has_risks,
            "has_embedding": self.has_embedding,
            "participant_count": self.participant_count,
        }

    def get_participant_emails(self) -> list[str]:
        """Extract email addresses from participants."""
        emails = []
        for p in self.participants:
            if isinstance(p, dict) and "email" in p:
                emails.append(p["email"])
            elif isinstance(p, str) and "@" in p:
                emails.append(p)
        return emails

    # Validators (business rules for data)
    @field_validator("summary_embedding", mode="before")
    @classmethod
    def parse_embedding(cls, v):
        """Parse summary_embedding from JSON string if needed."""
        if v is None:
            return None
        # If it's a string, parse it as JSON
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If it's a string but not JSON, it might be a postgres vector string format "[1,2,3]"
                # which json.loads handles if it looks like JSON array.
                # If it fails, we might need more complex parsing, but usually json.loads works for vector strings.
                return None
        return v

    @field_validator("risks_issues", mode="before")
    @classmethod
    def parse_risks_issues(cls, v):
        """Handle risks_issues from database (dict or list)."""
        if v is None:
            return []
        # If it's a dict with structure, wrap it in a list
        if isinstance(v, dict):
            return [v]
        return v


class DateRangeFilter(BaseModel):
    """
    Input validation model for date range queries.

    Validates ISO date strings and provides typed access.
    No changes needed - this model is query-focused, not table-focused.
    """

    model_config = ConfigDict(strict=True)

    date_from: datetime | None = Field(
        None, description="Start date for filtering (inclusive)"
    )
    date_to: datetime | None = Field(
        None, description="End date for filtering (inclusive)"
    )

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_not_future(cls, v: datetime | None) -> datetime | None:
        """Ensure dates are not in the future."""
        if v and v > datetime.now(timezone.utc):
            raise ValueError("Date cannot be in the future")
        return v

    def to_iso_strings(self) -> tuple[str | None, str | None]:
        """Convert to ISO format strings for database queries."""
        return (
            self.date_from.isoformat() if self.date_from else None,
            self.date_to.isoformat() if self.date_to else None,
        )


# Email models


class EmailRecipient(BaseModel):
    """
    DTO for email recipient information.

    Simplified version of legacy RecipientInfo - only essential fields.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    email: StrictStr = Field(description="Email address of recipient")
    name: StrictStr | None = Field(None, description="Display name (optional)")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Ensure email contains @ symbol."""
        v = v.lower().strip()
        if "@" not in v or "." not in v.split("@")[1]:
            raise ValueError(f"Invalid email format: {v}")
        return v


class EmailAttachment(BaseModel):
    """
    DTO for email attachment.

    Simplified version of legacy AttachmentData.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    filename: StrictStr = Field(description="Name of the file")
    content: bytes = Field(description="File content as bytes")
    content_type: StrictStr | None = Field(
        None, description="MIME type (e.g., 'application/pdf')"
    )


class EmailMessage(BaseModel):
    """
    DTO for composing an email message.

    Used as input to email service/repository methods.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    to_recipients: list[EmailRecipient] = Field(
        description="Primary recipients (TO field)"
    )
    subject: StrictStr = Field(description="Email subject line")
    body: StrictStr = Field(description="Email body content (markdown supported)")

    cc_recipients: list[EmailRecipient] | None = Field(
        None, description="CC recipients (optional)"
    )
    bcc_recipients: list[EmailRecipient] | None = Field(
        None, description="BCC recipients (optional)"
    )
    attachments: list[EmailAttachment] | None = Field(
        None, description="File attachments (optional)"
    )
    sender_email: StrictStr = Field(
        description="Email address sending from (must have permissions)"
    )

    @field_validator("to_recipients")
    @classmethod
    def validate_has_recipients(cls, v: list[EmailRecipient]) -> list[EmailRecipient]:
        """Ensure at least one recipient."""
        if not v or len(v) == 0:
            raise ValueError("Email must have at least one recipient")
        return v


class SentEmailResult(BaseModel):
    """
    DTO for email send operation result.

    Returned by repository after successful send.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    success: bool = Field(description="Whether email was sent successfully")
    message_id: StrictStr | None = Field(
        None, description="Message ID from MS Graph (if available)"
    )
    recipients_count: int = Field(description="Total number of recipients")
    subject: StrictStr = Field(description="Subject line of sent email")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When email was sent",
    )
    error_message: StrictStr | None = Field(
        None, description="Error details if success=False"
    )


# ============================================================================
# Email Search & Response Models (Added for email response feature)
# ============================================================================


class EmailSearchFilters(BaseModel):
    """
    DTO for email search filter parameters.

    Used by search_emails_tool to build MS Graph OData queries.
    Validates all filter parameters before making API calls.
    """

    model_config = ConfigDict(strict=True)

    folder: Literal["inbox", "sent", "drafts"] = "inbox"
    sender: StrictStr | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    is_unread: bool | None = None
    subject_contains: StrictStr | None = None
    has_attachments: bool | None = None
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("sender")
    @classmethod
    def validate_sender_email(cls, v: str | None) -> str | None:
        """Ensure sender looks like an email address."""
        if v and "@" not in v:
            raise ValueError("sender must contain '@' character")
        return v


class UnreadEmail(BaseModel):
    """
    DTO for fetched email from MS Graph.

    Represents a single email message with all metadata needed
    for the agent to analyze and draft a response.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    message_id: StrictStr
    conversation_id: StrictStr | None
    from_email: StrictStr
    from_name: StrictStr | None
    to_recipients: list[EmailRecipient]
    cc_recipients: list[EmailRecipient] | None
    subject: StrictStr
    body_preview: StrictStr  # First 255 chars
    body_content: StrictStr  # Full body
    received_datetime: datetime
    is_read: bool
    has_attachments: bool


class EmailDraft(BaseModel):
    """
    DTO for drafted email response.

    Represents a draft saved to MS Graph, ready for human review.

    Note: original_message_id is optional:
    - Set when creating reply drafts via MS Graph createReply API
    - None when creating standalone new drafts via POST /messages
    """

    model_config = ConfigDict(strict=True, frozen=True)

    draft_id: StrictStr | None  # MS Graph draft ID (set after creation)
    original_message_id: StrictStr | None = (
        None  # ID of message being replied to (None for standalone drafts)
    )
    to_recipients: list[EmailRecipient]
    cc_recipients: list[EmailRecipient] | None = None
    subject: StrictStr
    body_markdown: StrictStr
    body_html: StrictStr
    created_at: datetime
    status: Literal["draft", "sent", "failed"]


class EmailProcessingResult(BaseModel):
    """
    DTO for batch email processing result.

    Returned by agent after processing multiple emails.
    Contains summary of successes and failures.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    processed_count: int
    drafts_created: list[EmailDraft]
    errors: list[dict] | None
    timestamp: datetime


# ============================================================================
# Risk Domain Models (NA in Stage 1)
# ============================================================================


class RiskInfo(BaseModel):
    """
    Individual risk information.

    Phase 1: Populated by agent from web search results
    Phase 2: Extended with database fields
    """

    model_config = ConfigDict(strict=True)

    # Core fields (Phase 1)
    category: StrictStr  # e.g., "technical", "regulatory", "environmental"
    description: StrictStr
    severity: Literal["low", "medium", "high", "critical"]
    source_url: StrictStr | None = None

    # Future fields (Phase 2)
    # probability: float | None = None
    # impact_cost: StrictStr | None = None
    # mitigation_strategies: list[str] = Field(default_factory=list)
    # risk_id: StrictStr | None = None


class RiskFramework(BaseModel):
    """
    Common risk categorization framework.

    Phase 1: Used by agent for consistent categorization
    Phase 2: Extended with industry-specific frameworks
    """

    model_config = ConfigDict(strict=True)

    categories: list[StrictStr] = Field(
        default_factory=lambda: [
            "technical",
            "regulatory",
            "environmental",
            "financial",
            "schedule",
            "resource",
            "stakeholder",
            "safety",
        ]
    )
    severity_levels: list[StrictStr] = Field(
        default_factory=lambda: ["low", "medium", "high", "critical"]
    )


# ============================================================================
# User Context & Preferences Models
# ============================================================================


class UserPreferences(BaseModel):
    """
    DTO for user preferences (JSONB in database).

    Stores UI settings, notification preferences, and default parameters.

    Fields:
        ui_language: Language for frontend UI labels (e.g., 'en', 'es-AR')
        response_language: Language for AI-generated responses (e.g., 'en', 'es-AR')
        response_tone: Tone for AI responses ('professional', 'casual', 'formal')
        response_verbosity: Verbosity level for AI responses (1-5, where 3 is default)
        agent_instructions: Custom per-user directives for agents (JSONB)
    """

    model_config = ConfigDict(strict=True, frozen=True)

    theme: Literal["light", "dark", "system"] = "system"

    # UI language (for frontend labels/app shell)
    ui_language: StrictStr = "en"

    # AI response preferences
    response_language: StrictStr = "en"
    response_tone: Literal["professional", "casual", "formal"] = "professional"
    response_verbosity: int = Field(default=3, ge=1, le=5)

    # Custom agent instructions (per-user directives)
    agent_instructions: dict[str, str] | None = None

    # Notification settings
    notifications_enabled: bool = True
    default_project_id: StrictStr | None = None

    # Flexible extra preferences (backward compatibility)
    extra_settings: dict | None = None

    # Backward compatibility property
    @property
    def language(self) -> str:
        """Deprecated: Use ui_language or response_language instead."""
        return self.ui_language


class SessionContext(BaseModel):
    """
    Transient context for a single conversation turn.

    This is computed at the start of each turn based on:
    - User preferences (fallback)
    - Task context overrides (e.g., workflow language)
    - Input language detection (mirroring)
    - Explicit session overrides (e.g., "switch to English")

    NOT persisted to database - ephemeral per-turn state.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    # Resolved language for this turn (result of precedence logic)
    target_language: StrictStr = "en"

    # Detected language of user's input (for logging/debugging)
    input_language: StrictStr | None = None
    input_language_confidence: float = 0.0

    # Override source (for debugging/logging)
    language_source: Literal[
        "task_context",  # Task/workflow mandated language
        "session_override",  # User explicitly requested language change
        "input_mirror",  # Mirrored from user input
        "user_preference",  # Fallback to stored preference
    ] = "user_preference"

    # Resolved tone for this turn
    target_tone: Literal["professional", "casual", "formal"] = "professional"

    # Custom instructions active for this turn
    custom_instructions: str | None = None


class UserContext(BaseModel):
    """
    DTO for authenticated user context.

    Passed to agents and services to provide user-specific context.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    user_id: UUID
    email: StrictStr
    full_name: StrictStr | None
    first_name: StrictStr | None  # Computed field

    # Role-based access (simplified for now)
    roles: list[StrictStr] = Field(default_factory=list)

    # Preferences
    preferences: UserPreferences

    # Current active context (optional)
    active_project_id: StrictStr | None = None

    @property
    def display_name(self) -> str:
        """Return best available name for display."""
        if self.full_name:
            return self.full_name
        return self.email.split("@")[0]
