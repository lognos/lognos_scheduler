"""Base classes and dependencies for scheduling agent tools."""

from dataclasses import dataclass
from typing import Optional

from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService


@dataclass
class AgentDeps:
    """Dependencies for the scheduling agent.
    
    Attributes:
        service: The scheduling service for P6 operations.
        vector_service: Optional vector search service for semantic search.
        conn: Optional database connection for direct queries.
        gantt_event_queue: Queue for gantt panel events to be streamed to frontend.
        conversation_id: Unique conversation ID for workspace isolation.
    """
    service: SchedulingService
    vector_service: Optional[VectorService] = None
    conn: Optional[object] = None
    gantt_event_queue: Optional[list] = None
    conversation_id: Optional[str] = None
