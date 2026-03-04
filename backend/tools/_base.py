"""Base classes and dependencies for scheduling agent tools."""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Any

from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService

if TYPE_CHECKING:
    from backend.models.domain import UserContext
    from backend.repositories.user_context_repository import UserContextRepository
    from backend.utils.safe_db import SafeP6Transaction
    from backend.repositories.ms_schedule_repository import MSScheduleRepository
    from supabase import Client


@dataclass
class AgentDeps:
    """Dependencies for the scheduling agent.
    
    Attributes:
        service: The scheduling service for P6 operations.
        vector_service: Optional vector search service for semantic search.
        email_service: Optional email service for scheduling email tools.
        conn: Optional database connection for direct queries.
        transaction: Optional SafeP6Transaction for marking modifications.
        gantt_event_queue: Queue for gantt panel events to be streamed to frontend.
        conversation_id: Unique conversation ID for workspace isolation.
        ms_repository: Optional repository for MS Project schedules (Supabase).
        supabase_client: Optional Supabase client for direct access.
        user_context: Optional request user context.
        user_context_repository: Optional repository for user/team lookups.
    """
    service: SchedulingService
    vector_service: Optional[VectorService] = None
    email_service: Optional[Any] = None
    conn: Optional[object] = None
    transaction: Optional["SafeP6Transaction"] = None
    gantt_event_queue: Optional[list] = None
    conversation_id: Optional[str] = None
    ms_repository: Optional["MSScheduleRepository"] = None
    supabase_client: Optional["Client"] = None
    user_context: Optional["UserContext"] = None
    user_context_repository: Optional["UserContextRepository"] = None
    
    def mark_modified(self):
        """Mark the transaction as modified so the database will be backed up and saved."""
        if self.transaction:
            self.transaction.mark_modified()
