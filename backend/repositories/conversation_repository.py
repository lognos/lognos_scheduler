"""
Repository for schedule conversation persistence operations.
Uses Supabase for storage in lognos_comm schema.
"""
from typing import Optional
import logfire
from supabase import Client

from backend.models.domain import (
    ConversationUpdate,
    ConversationSummary,
    ConversationWithMessages,
    MessageRecord,
)


class ConversationRepository:
    """Repository for schedule_conversations and schedule_chat_messages tables."""
    
    CONVERSATIONS_TABLE = "schedule_conversations"
    MESSAGES_TABLE = "schedule_chat_messages"
    SCHEMA = "lognos_comm"
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    @logfire.instrument("repo.create_conversation")
    async def create_conversation(
        self,
        conversation_id: str,
        creator_email: str,
        project_id: Optional[str] = None,
        p6_schedule_id: Optional[str] = None,
        title: str = "New conversation",
    ) -> dict:
        """Create a new conversation record."""
        data = {
            "conversation_id": conversation_id,
            "creator_email": creator_email,
            "title": title,
            "title_auto_generated": True,
        }
        if project_id:
            data["project_id"] = project_id
        if p6_schedule_id:
            data["p6_schedule_id"] = p6_schedule_id
            
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.CONVERSATIONS_TABLE)
            .insert(data)
            .execute()
        )
        return result.data[0] if result.data else None
    
    @logfire.instrument("repo.get_conversation")
    async def get_conversation(
        self,
        conversation_id: str,
        user_email: str,
    ) -> Optional[ConversationWithMessages]:
        """Get a conversation with all its messages."""
        # Fetch conversation
        conv_result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.CONVERSATIONS_TABLE)
            .select("*")
            .eq("conversation_id", conversation_id)
            .eq("creator_email", user_email)
            .single()
            .execute()
        )
        
        if not conv_result.data:
            return None
        
        # Fetch messages
        msg_result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.MESSAGES_TABLE)
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("timestamp", desc=False)
            .execute()
        )
        
        messages = [
            MessageRecord(
                message_id=m["message_id"],
                conversation_id=m["conversation_id"],
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                tool_call_id=m.get("tool_call_id"),
                tool_name=m.get("tool_name"),
                model_name=m.get("model_name"),
                metadata=m.get("metadata", {}),
            )
            for m in (msg_result.data or [])
        ]
        
        conv = conv_result.data
        return ConversationWithMessages(
            conversation_id=conv["conversation_id"],
            creator_email=conv["creator_email"],
            project_id=conv.get("project_id"),
            p6_schedule_id=conv.get("p6_schedule_id"),
            title=conv["title"],
            message_count=conv["message_count"],
            last_message_at=conv.get("last_message_at"),
            status=conv["status"],
            created_at=conv["created_at"],
            messages=messages,
        )
    
    @logfire.instrument("repo.list_conversations")
    async def list_conversations(
        self,
        user_email: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[ConversationSummary]:
        """List conversations for a user, optionally filtered by project."""
        query = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.CONVERSATIONS_TABLE)
            .select("conversation_id, title, last_message_at, message_count, status")
            .eq("creator_email", user_email)
            .eq("visible", True)
            .order("last_message_at", desc=True, nullsfirst=False)
            .limit(limit)
        )
        
        if project_id:
            query = query.eq("project_id", project_id)
        
        result = query.execute()
        
        return [
            ConversationSummary(
                conversation_id=c["conversation_id"],
                title=c["title"],
                last_message_at=c.get("last_message_at"),
                message_count=c["message_count"],
                status=c["status"],
            )
            for c in (result.data or [])
        ]
    
    @logfire.instrument("repo.update_conversation")
    async def update_conversation(
        self,
        conversation_id: str,
        user_email: str,
        update: ConversationUpdate,
    ) -> bool:
        """Update conversation fields (title, visible, status)."""
        data = update.model_dump(exclude_unset=True)
        if not data:
            return True
        
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.CONVERSATIONS_TABLE)
            .update(data)
            .eq("conversation_id", conversation_id)
            .eq("creator_email", user_email)
            .execute()
        )
        return len(result.data) > 0 if result.data else False
    
    @logfire.instrument("repo.save_message")
    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        model_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Save a message to a conversation."""
        data = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
        }
        if message_id:
            data["message_id"] = message_id
        if tool_call_id:
            data["tool_call_id"] = tool_call_id
        if tool_name:
            data["tool_name"] = tool_name
        if model_name:
            data["model_name"] = model_name
        if metadata:
            data["metadata"] = metadata
        
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.MESSAGES_TABLE)
            .insert(data)
            .execute()
        )
        return result.data[0] if result.data else None
    
    @logfire.instrument("repo.get_message_history")
    async def get_message_history(
        self,
        conversation_id: str,
        limit: int = 50,
    ) -> list[MessageRecord]:
        """Get message history for a conversation (for agent context)."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.MESSAGES_TABLE)
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("timestamp", desc=False)
            .limit(limit)
            .execute()
        )
        
        return [
            MessageRecord(
                message_id=m["message_id"],
                conversation_id=m["conversation_id"],
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                tool_call_id=m.get("tool_call_id"),
                tool_name=m.get("tool_name"),
                model_name=m.get("model_name"),
                metadata=m.get("metadata", {}),
            )
            for m in (result.data or [])
        ]
    
    @logfire.instrument("repo.update_conversation_title")
    async def update_title_if_auto(
        self,
        conversation_id: str,
        new_title: str,
    ) -> bool:
        """Update title only if it was auto-generated."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.CONVERSATIONS_TABLE)
            .update({"title": new_title, "title_auto_generated": False})
            .eq("conversation_id", conversation_id)
            .eq("title_auto_generated", True)
            .execute()
        )
        return len(result.data) > 0 if result.data else False
    
    @logfire.instrument("repo.conversation_exists")
    async def conversation_exists(self, conversation_id: str) -> bool:
        """Check if a conversation exists."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.CONVERSATIONS_TABLE)
            .select("conversation_id")
            .eq("conversation_id", conversation_id)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0 if result.data else False
