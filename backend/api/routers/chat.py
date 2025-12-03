"""
Chat router with SSE streaming support.
Provides endpoints for conversational interaction with the P6 Scheduling Agent.
"""
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ToolReturnPart
import logfire

from backend.agents.scheduling_agent import scheduling_agent
from backend.tools.p6_tools import AgentDeps
from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService
from backend.utils.safe_db import SafeP6Transaction
from backend.utils.supabase_client import get_supabase
from backend.repositories.conversation_repository import ConversationRepository
from backend.repositories.p6_schedule_repository import P6ScheduleRepository
from backend.config.settings import settings

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    model_config = ConfigDict(strict=True)
    
    message: str = Field(..., min_length=1)
    sender_email: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    p6_schedule_id: Optional[str] = None  # Specific P6 schedule to use


class ChatResponse(BaseModel):
    """Non-streaming response model (for fallback)."""
    response: str
    conversation_id: str
    tool_calls: list[dict] = []


# ============================================================
# SSE Event Helpers
# ============================================================

def sse_event(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"


def sse_node_event(node: str, status: str = "working", intent: str = None) -> str:
    """Create a node status SSE event."""
    event = {"node": node, "status": status}
    if intent:
        event["intent"] = intent
    return sse_event(event)


def sse_reasoning_event(node: str, content: str) -> str:
    """Create a reasoning SSE event (for thinking indicator)."""
    return sse_event({"type": "reasoning", "node": node, "content": content})


def sse_token_event(content: str) -> str:
    """Create a token SSE event (for streaming response)."""
    return sse_event({"type": "token", "content": content})


def sse_end_event(output: str) -> str:
    """Create an end SSE event."""
    return sse_event({"node": "End", "output": output})


def sse_error_event(error: str) -> str:
    """Create an error SSE event."""
    return sse_event({"node": "Error", "status": "error", "error": error})


# ============================================================
# Chat Endpoint (SSE Streaming)
# ============================================================

@router.post("/chat")
async def chat_stream(
    req: ChatRequest,
    lognos_project_id: Optional[str] = Header(None, alias="Lognos-ProjectID"),
):
    """
    Stream chat responses using Server-Sent Events (SSE).
    
    SSE Event Types:
    - {node: "...", status: "working"} - Agent state update
    - {type: "reasoning", node: "...", content: "..."} - Thinking/reasoning text
    - {type: "token", content: "..."} - Response token (for streaming)
    - {node: "End", output: "..."} - Final response
    - {node: "Error", error: "..."} - Error occurred
    """
    
    async def event_generator():
        supabase = get_supabase()
        conv_repo = ConversationRepository(supabase)
        p6_repo = P6ScheduleRepository(supabase)
        
        conversation_id = req.conversation_id or str(uuid4())
        
        try:
            # Signal start
            yield sse_node_event("Initializing", "working", "Setting up context")
            
            # Resolve P6 project ID
            p6_proj_id = None
            if lognos_project_id:
                p6_proj_id = await p6_repo.resolve_p6_proj_id(
                    lognos_project_id,
                    req.p6_schedule_id
                )
                yield sse_reasoning_event(
                    "Initializing",
                    f"Using P6 project {p6_proj_id}" if p6_proj_id else "No P6 schedule linked"
                )
            
            # Create or verify conversation exists
            conv_exists = await conv_repo.conversation_exists(conversation_id)
            if not conv_exists:
                await conv_repo.create_conversation(
                    conversation_id=conversation_id,
                    creator_email=req.sender_email,
                    project_id=lognos_project_id,
                    p6_schedule_id=req.p6_schedule_id,
                )
            
            # Save user message
            await conv_repo.save_message(
                conversation_id=conversation_id,
                role="user",
                content=req.message,
            )
            
            yield sse_node_event("Processing", "working", "Analyzing request")
            
            # Build context message for agent
            context_parts = []
            if p6_proj_id:
                context_parts.append(f"P6 Project ID: {p6_proj_id}")
            if lognos_project_id:
                context_parts.append(f"Lognos Project: {lognos_project_id}")
            
            # Get message history for context
            history = await conv_repo.get_message_history(conversation_id, limit=20)
            history_text = ""
            if len(history) > 1:  # More than just the current message
                history_text = "\n\nConversation history:\n"
                for msg in history[:-1]:  # Exclude current message
                    role = "User" if msg.role == "user" else "Assistant"
                    history_text += f"{role}: {msg.content}\n"
            
            full_message = ""
            if context_parts:
                full_message = f"Context: {', '.join(context_parts)}\n"
            if history_text:
                full_message += history_text + "\n"
            full_message += f"Current request: {req.message}"
            
            yield sse_node_event("Scheduling", "working", "Executing agent")
            
            # Initialize services and run agent
            service = SchedulingService()
            vector_service = VectorService()
            
            with SafeP6Transaction() as conn:
                deps = AgentDeps(
                    service=service,
                    vector_service=vector_service,
                    conn=conn
                )
                
                with logfire.span(
                    "agent_run_stream",
                    message=req.message,
                    conversation_id=conversation_id,
                    p6_proj_id=p6_proj_id,
                ):
                    # Use capture_run_messages to get tool results even if model fails
                    with capture_run_messages() as messages:
                        try:
                            # Run the agent with streaming
                            async with scheduling_agent.run_stream(full_message, deps=deps) as result:
                                full_response = ""
                                
                                # Stream tokens as they arrive
                                async for text in result.stream_text(delta=True):
                                    full_response += text
                                    yield sse_token_event(text)
                                
                                # Get final structured output if available
                                final_result = await result.get_output()
                                
                                # Determine final response text
                                if hasattr(final_result, 'data'):
                                    final_text = str(final_result.data)
                                elif hasattr(final_result, 'output'):
                                    final_text = str(final_result.output)
                                else:
                                    final_text = full_response or str(final_result)
                                    
                        except UnexpectedModelBehavior as model_err:
                            # Gemini sometimes returns empty responses after tool calls
                            # Extract tool results from captured messages as fallback
                            logfire.warning(
                                "Model output validation failed, extracting tool results",
                                error=str(model_err),
                            )
                            
                            # Find tool return parts from the messages
                            tool_results = []
                            for msg in messages:
                                if hasattr(msg, 'parts'):
                                    for part in msg.parts:
                                        if isinstance(part, ToolReturnPart):
                                            tool_results.append(part.content)
                            
                            if tool_results:
                                # Build a response from the tool results
                                final_text = "Here is what I found:\n\n" + "\n\n".join(str(r) for r in tool_results)
                                # Stream this fallback response
                                yield sse_token_event(final_text)
                            else:
                                # No tool results - re-raise
                                raise
                        
                        logfire.info(
                            "Agent completed",
                            response_length=len(final_text),
                            conversation_id=conversation_id,
                        )
            
            # Save assistant response
            await conv_repo.save_message(
                conversation_id=conversation_id,
                role="assistant",
                content=final_text,
                model_name=settings.GOOGLE_DEFAULT_MODEL,
            )
            
            # Auto-generate title if this is the first exchange
            if not conv_exists or len(history) <= 1:
                # Use first ~50 chars of user message as title
                auto_title = req.message[:50] + ("..." if len(req.message) > 50 else "")
                await conv_repo.update_title_if_auto(conversation_id, auto_title)
            
            # Send end event
            yield sse_end_event(final_text)
            
        except Exception as e:
            logfire.error("Chat stream error", error=str(e), conversation_id=conversation_id)
            yield sse_error_event(str(e))
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# ============================================================
# Non-Streaming Chat Endpoint (Fallback)
# ============================================================

@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(
    req: ChatRequest,
    lognos_project_id: Optional[str] = Header(None, alias="Lognos-ProjectID"),
):
    """
    Synchronous chat endpoint (non-streaming).
    Use /chat for streaming responses.
    """
    supabase = get_supabase()
    conv_repo = ConversationRepository(supabase)
    p6_repo = P6ScheduleRepository(supabase)
    
    conversation_id = req.conversation_id or str(uuid4())
    
    try:
        # Resolve P6 project ID
        p6_proj_id = None
        if lognos_project_id:
            p6_proj_id = await p6_repo.resolve_p6_proj_id(
                lognos_project_id,
                req.p6_schedule_id
            )
        
        # Create or verify conversation exists
        conv_exists = await conv_repo.conversation_exists(conversation_id)
        if not conv_exists:
            await conv_repo.create_conversation(
                conversation_id=conversation_id,
                creator_email=req.sender_email,
                project_id=lognos_project_id,
                p6_schedule_id=req.p6_schedule_id,
            )
        
        # Save user message
        await conv_repo.save_message(
            conversation_id=conversation_id,
            role="user",
            content=req.message,
        )
        
        # Build context
        context_parts = []
        if p6_proj_id:
            context_parts.append(f"P6 Project ID: {p6_proj_id}")
        
        full_message = ""
        if context_parts:
            full_message = f"Context: {', '.join(context_parts)}\n\n"
        full_message += req.message
        
        # Run agent
        service = SchedulingService()
        vector_service = VectorService()
        
        with SafeP6Transaction() as conn:
            deps = AgentDeps(
                service=service,
                vector_service=vector_service,
                conn=conn
            )
            
            with logfire.span("agent_run_sync", message=req.message, p6_proj_id=p6_proj_id):
                result = await scheduling_agent.run(full_message, deps=deps)
                
                response_data = getattr(result, 'data', getattr(result, 'output', str(result)))
                final_response = str(response_data)
        
        # Save assistant response
        await conv_repo.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content=final_response,
            model_name=settings.GOOGLE_DEFAULT_MODEL,
        )
        
        return ChatResponse(
            response=final_response,
            conversation_id=conversation_id,
            tool_calls=[],
        )
        
    except Exception as e:
        logfire.error("Chat sync error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
