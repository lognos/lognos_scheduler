"""Base classes and dependencies for scheduling agent tools."""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.models.domain import UserContext
    from backend.repositories.user_context_repository import UserContextRepository
    from backend.repositories.ms_schedule_repository import MSScheduleRepository
    from supabase import Client


@dataclass
class AgentDeps:
    """Dependencies for the scheduling agent.
    
    Attributes:
        email_service: Optional email service for scheduling email tools.
        gantt_event_queue: Queue for gantt panel events to be streamed to frontend.
        conversation_id: Unique conversation ID for workspace isolation.
        ms_repository: Optional repository for MS Project schedules (Supabase).
        supabase_client: Optional Supabase client for direct access.
        user_context: Optional request user context.
        user_context_repository: Optional repository for user/team lookups.
    """
    email_service: Optional[Any] = None
    gantt_event_queue: Optional[list] = None
    conversation_id: Optional[str] = None
    ms_repository: Optional["MSScheduleRepository"] = None
    supabase_client: Optional["Client"] = None
    user_context: Optional["UserContext"] = None
    user_context_repository: Optional["UserContextRepository"] = None
