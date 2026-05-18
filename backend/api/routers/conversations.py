"""
Conversations router for managing schedule conversation history.
Provides endpoints for listing, fetching, and updating conversations.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
import logfire

from backend.utils.supabase_client import get_supabase
from backend.repositories.conversation_repository import ConversationRepository
from backend.models.domain import ConversationSummary, ConversationUpdate, MessageRecord

router = APIRouter()


# ============================================================
# Response Models
# ============================================================

class ConversationListResponse(BaseModel):
    """Response model for conversation list."""
    conversations: list[ConversationSummary]


class ConversationDetailResponse(BaseModel):
    """Response model for single conversation with messages."""
    conversation_id: str
    title: str
    creator_email: str
    project_id: Optional[str] = None
    message_count: int
    status: str
    created_at: str
    messages: list[MessageRecord]


class ConversationUpdateRequest(BaseModel):
    """Request model for updating a conversation."""
    model_config = ConfigDict(strict=True)
    
    title: Optional[str] = None
    visible: Optional[bool] = None


# ============================================================
# Endpoints
# ============================================================

@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    user_email: str = Query(..., description="User email to filter conversations"),
    lognos_project_id: Optional[str] = Header(None, alias="Lognos-ProjectID"),
):
    """
    List conversations for a user.
    Optionally filter by project via Lognos-ProjectID header.
    """
    supabase = get_supabase()
    repo = ConversationRepository(supabase)
    
    try:
        conversations = await repo.list_conversations(
            user_email=user_email,
            project_id=lognos_project_id,
        )
        return ConversationListResponse(conversations=conversations)
    except Exception as e:
        logfire.error("Error listing conversations", error=str(e), user_email=user_email)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    user_email: str = Query(..., description="User email for authorization"),
):
    """
    Get a conversation with all its messages.
    """
    supabase = get_supabase()
    repo = ConversationRepository(supabase)
    
    try:
        conversation = await repo.get_conversation(
            conversation_id=conversation_id,
            user_email=user_email,
        )
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return ConversationDetailResponse(
            conversation_id=conversation.conversation_id,
            title=conversation.title,
            creator_email=conversation.creator_email,
            project_id=conversation.project_id,
            message_count=conversation.message_count,
            status=conversation.status,
            created_at=conversation.created_at,
            messages=conversation.messages,
        )
    except HTTPException:
        raise
    except Exception as e:
        logfire.error("Error fetching conversation", error=str(e), conversation_id=conversation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    update: ConversationUpdateRequest,
    user_email: str = Query(..., description="User email for authorization"),
):
    """
    Update a conversation (title, visibility).
    """
    supabase = get_supabase()
    repo = ConversationRepository(supabase)
    
    try:
        # Convert request to domain model
        domain_update = ConversationUpdate(
            title=update.title,
            visible=update.visible,
        )
        
        success = await repo.update_conversation(
            conversation_id=conversation_id,
            user_email=user_email,
            update=domain_update,
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found or not authorized")
        
        return {"status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        logfire.error("Error updating conversation", error=str(e), conversation_id=conversation_id)
        raise HTTPException(status_code=500, detail=str(e))
