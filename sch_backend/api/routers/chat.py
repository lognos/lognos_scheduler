"""
Chat router with SSE streaming support.
Provides endpoints for conversational interaction with the Lognos Scheduling Agent.
"""
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelMessage,
    ToolReturnPart,
)
import logfire

from sch_backend.agents.scheduling_agent import get_scheduling_agent, SCHEDULING_USAGE_LIMITS
from sch_backend.tools._base import AgentDeps
from sch_backend.utils.supabase_client import get_supabase
from sch_backend.repositories.conversation_repository import ConversationRepository
from sch_backend.repositories.ms_schedule_repository import MSScheduleRepository
from sch_backend.repositories.user_context_repository import UserContextRepository
from sch_backend.models.domain import UserContext
from sch_backend.models.io import SchedulingResponse, ClarificationRequest, ErrorResponse
from sch_backend.config.settings import settings

router = APIRouter()


def _build_email_service():
    if not settings.EMAIL_ENABLED:
        return None


def _normalize_project_type(project_type: str) -> str:
    """Keep request compatibility while enforcing the MS-only runtime."""
    normalized = project_type.lower().strip()
    if normalized == "p6":
        raise ValueError("P6 schedules are no longer supported by this MS-only service. Use project_type='msp'.")
    return "msp"

    try:
        from sch_backend.email_tools import EmailRepository, EmailService

        email_repository = EmailRepository()
        return EmailService(repository=email_repository)
    except Exception as error:
        logfire.error(
            "Failed to initialize email service",
            error=str(error),
            error_type=type(error).__name__,
            exc_info=True,
        )
        return None


async def _resolve_user_context(
    user_repo: UserContextRepository,
    sender_email: str,
    project_id: Optional[str],
) -> UserContext:
    """Resolve request user context from lognos_comm.users with safe fallback."""
    try:
        return await user_repo.get_user_context(sender_email, project_id=project_id)
    except Exception as error:
        logfire.error(
            "Failed to resolve user context",
            sender_email=sender_email,
            project_id=project_id,
            error=str(error),
            error_type=type(error).__name__,
        )
        return UserContext(email=sender_email, current_project_id=project_id)


# ============================================================
# Request/Response Models
# ============================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    model_config = ConfigDict(strict=True)
    
    message: str = Field(..., min_length=1)
    sender_email: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    project_type: str = Field(default="msp", min_length=1)


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
        ms_repo = MSScheduleRepository(supabase)
        user_ctx_repo = UserContextRepository(supabase)
        
        conversation_id = req.conversation_id or str(uuid4())
        
        try:
            # Signal start
            yield sse_node_event("Initializing", "working", "Setting up context")

            project_type = _normalize_project_type(req.project_type)
            agent = get_scheduling_agent(project_type)

            if lognos_project_id:
                yield sse_reasoning_event(
                    "Initializing",
                    f"Using MS schedule source for project {lognos_project_id}"
                )
            
            # Create or verify conversation exists
            conv_exists = await conv_repo.conversation_exists(conversation_id)
            if not conv_exists:
                await conv_repo.create_conversation(
                    conversation_id=conversation_id,
                    creator_email=req.sender_email,
                    project_id=lognos_project_id,
                )
            
            # Save user message to display history
            await conv_repo.save_message(
                conversation_id=conversation_id,
                role="user",
                content=req.message,
            )
            
            yield sse_node_event("Processing", "working", "Analyzing request")
            
            # Build context message for agent
            context_parts = []
            context_parts.append(f"Project Type: {project_type.upper()}")
            if lognos_project_id:
                context_parts.append(f"Lognos Project: {lognos_project_id}")

            user_context = await _resolve_user_context(
                user_repo=user_ctx_repo,
                sender_email=req.sender_email,
                project_id=lognos_project_id,
            )
            user_display = user_context.full_name or user_context.first_name or user_context.email
            user_identity = f"User: {user_display} <{user_context.email}>"
            if user_context.role:
                user_identity += f", role={user_context.role}"
            if user_context.app_role:
                user_identity += f", app_role={user_context.app_role}"
            context_parts.append(user_identity)
            
            # Build the user message with context
            user_message = req.message
            if context_parts:
                user_message = f"Context: {', '.join(context_parts)}\n\nRequest: {req.message}"
            
            # Load Pydantic AI message history if available
            message_history: list[ModelMessage] = []
            history_json = await conv_repo.get_agent_message_history(conversation_id)
            if history_json:
                try:
                    message_history = ModelMessagesTypeAdapter.validate_json(history_json)
                except Exception as e:
                    logfire.warning("Failed to parse message history", error=str(e))
                    message_history = []
            
            yield sse_node_event("Scheduling", "working", "Executing agent")
            
            # Initialize dependencies and run agent
            email_service = _build_email_service()
            
            # Queue for gantt panel events from tools
            gantt_event_queue: list[dict] = []

            deps = AgentDeps(
                email_service=email_service,
                gantt_event_queue=gantt_event_queue,
                conversation_id=conversation_id,
                ms_repository=ms_repo,
                supabase_client=supabase,
                user_context=user_context,
                user_context_repository=user_ctx_repo,
            )
            
            with logfire.span(
                "agent_run_stream",
                message=req.message,
                conversation_id=conversation_id,
                project_type=project_type,
                history_length=len(message_history),
            ):
                # Track response for saving
                final_text = ""
                
                # Use capture_run_messages to get tool results even if model fails
                with capture_run_messages() as messages:
                    try:
                        # Run the agent (non-streaming for structured output)
                        # Note: stream_text() cannot be used with output_type
                        result = await agent.run(
                            user_message,
                            deps=deps,
                            message_history=message_history,
                            usage_limits=SCHEDULING_USAGE_LIMITS,
                        )
                        
                        # Get structured output
                        final_result = result.output
                        
                        # Extract message based on output type
                        if isinstance(final_result, SchedulingResponse):
                            final_text = final_result.message
                        elif isinstance(final_result, ClarificationRequest):
                            final_text = final_result.question
                            if final_result.options:
                                final_text += "\n\nOptions:\n" + "\n".join(f"- {opt}" for opt in final_result.options)
                        elif isinstance(final_result, ErrorResponse):
                            final_text = f"Error: {final_result.message}"
                            if final_result.suggestion:
                                final_text += f"\n\nSuggestion: {final_result.suggestion}"
                        else:
                            # Fallback for string or unexpected output
                            final_text = str(final_result)
                        
                        # Send the complete response as a token event
                        yield sse_token_event(final_text)
                                
                    except UnexpectedModelBehavior as model_err:
                        # Gemini sometimes returns empty responses after tool calls
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
                            final_text = "Here is what I found:\n\n" + "\n\n".join(str(r) for r in tool_results)
                            yield sse_token_event(final_text)
                        else:
                            final_text = f"I encountered an issue processing your request: {str(model_err)}"
                            yield sse_token_event(final_text)
                
                # Save the new message history for next turn
                all_messages = list(messages)
                if all_messages:
                    new_history_json = ModelMessagesTypeAdapter.dump_json(all_messages).decode()
                    await conv_repo.save_agent_message_history(conversation_id, new_history_json)
                    
                    logfire.info(
                        "Agent completed",
                        response_length=len(final_text),
                        conversation_id=conversation_id,
                        messages_saved=len(all_messages),
                    )
                
                # Stream any gantt panel events that were queued during tool execution
                logfire.info(
                    "Streaming gantt events",
                    queue_length=len(gantt_event_queue),
                    has_events=bool(gantt_event_queue),
                )
                for gantt_event in gantt_event_queue:
                    _evt_data = gantt_event.get('data') or {}
                    _evt_rels = _evt_data.get('relationships') or []
                    _evt_items = _evt_data.get('items') or []
                    _evt_caps = _evt_data.get('capabilities') or {}
                    logfire.info(
                        "Yielding gantt event",
                        event_type=gantt_event.get('type'),
                        action=gantt_event.get('action'),
                        items_count=len(_evt_items),
                        relationships_count=len(_evt_rels),
                        capabilities_links=_evt_caps.get('links'),
                        relationships_sample=_evt_rels[:3] if _evt_rels else [],
                    )
                    yield sse_event(gantt_event)
            
            # Save assistant response to display history (always save, even if empty)
            if final_text:
                await conv_repo.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=final_text,
                    model_name=settings.GOOGLE_DEFAULT_MODEL,
                )
            
            # Auto-generate title if this is the first exchange
            if not conv_exists:
                auto_title = req.message[:50] + ("..." if len(req.message) > 50 else "")
                await conv_repo.update_title_if_auto(conversation_id, auto_title)
            
            # Send end event with structured data
            yield sse_end_event(final_text)
            
        except Exception as e:
            error_message = f"I encountered an error processing your request: {str(e)}"
            logfire.error("Chat stream error", error=str(e), conversation_id=conversation_id)
            
            # Save error response as assistant message so history shows what happened
            try:
                await conv_repo.save_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=error_message,
                    model_name=settings.GOOGLE_DEFAULT_MODEL,
                    metadata={"error": True, "error_type": type(e).__name__},
                )
            except Exception as save_err:
                logfire.error("Failed to save error message", error=str(save_err))
            
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
    ms_repo = MSScheduleRepository(supabase)
    user_ctx_repo = UserContextRepository(supabase)
    
    conversation_id = req.conversation_id or str(uuid4())
    
    try:
        project_type = _normalize_project_type(req.project_type)
        agent = get_scheduling_agent(project_type)
        
        # Create or verify conversation exists
        conv_exists = await conv_repo.conversation_exists(conversation_id)
        if not conv_exists:
            await conv_repo.create_conversation(
                conversation_id=conversation_id,
                creator_email=req.sender_email,
                project_id=lognos_project_id,
            )
        
        # Save user message
        await conv_repo.save_message(
            conversation_id=conversation_id,
            role="user",
            content=req.message,
        )
        
        # Build context
        context_parts = [f"Project Type: {project_type.upper()}"]
        if lognos_project_id:
            context_parts.append(f"Lognos Project: {lognos_project_id}")

        user_context = await _resolve_user_context(
            user_repo=user_ctx_repo,
            sender_email=req.sender_email,
            project_id=lognos_project_id,
        )
        user_display = user_context.full_name or user_context.first_name or user_context.email
        user_identity = f"User: {user_display} <{user_context.email}>"
        if user_context.role:
            user_identity += f", role={user_context.role}"
        if user_context.app_role:
            user_identity += f", app_role={user_context.app_role}"
        context_parts.append(user_identity)
        
        user_message = req.message
        if context_parts:
            user_message = f"Context: {', '.join(context_parts)}\n\nRequest: {req.message}"
        
        # Load message history
        message_history: list[ModelMessage] = []
        history_json = await conv_repo.get_agent_message_history(conversation_id)
        if history_json:
            try:
                message_history = ModelMessagesTypeAdapter.validate_json(history_json)
            except Exception:
                message_history = []
        
        # Run agent
        email_service = _build_email_service()
        deps = AgentDeps(
            email_service=email_service,
            conversation_id=conversation_id,
            ms_repository=ms_repo,
            supabase_client=supabase,
            user_context=user_context,
            user_context_repository=user_ctx_repo,
        )
        
        with logfire.span("agent_run_sync", message=req.message, project_type=project_type):
            with capture_run_messages() as messages:
                result = await agent.run(
                    user_message,
                    deps=deps,
                    message_history=message_history,
                    usage_limits=SCHEDULING_USAGE_LIMITS,  # Prevent runaway loops
                )
                
                # Extract response based on output type
                final_result = result.output
                if isinstance(final_result, SchedulingResponse):
                    final_response = final_result.message
                elif isinstance(final_result, ClarificationRequest):
                    final_response = final_result.question
                elif isinstance(final_result, ErrorResponse):
                    final_response = final_result.message
                else:
                    final_response = str(final_result)
                
                # Save message history
                all_messages = list(messages)
                if all_messages:
                    new_history_json = ModelMessagesTypeAdapter.dump_json(all_messages).decode()
                    await conv_repo.save_agent_message_history(conversation_id, new_history_json)
        
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
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logfire.error("Chat sync error", error=str(e), conversation_id=conversation_id)
        
        # Save error response as assistant message
        try:
            error_message = f"I encountered an error processing your request: {str(e)}"
            await conv_repo.save_message(
                conversation_id=conversation_id,
                role="assistant",
                content=error_message,
                model_name=settings.GOOGLE_DEFAULT_MODEL,
                metadata={"error": True, "error_type": type(e).__name__},
            )
        except Exception:
            pass  # Don't fail the error handler
        
        raise HTTPException(status_code=500, detail=str(e))
