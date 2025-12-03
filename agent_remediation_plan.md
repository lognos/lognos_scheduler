# Pydantic AI Agent Remediation Plan

## Executive Summary

This document identifies issues with the current Pydantic AI implementation compared to official documentation best practices. The analysis covers agent setup, tool registration, streaming, message history, dependencies, and observability.

**Current Status**: IMPLEMENTED - The majority of issues have been addressed.

---

## Implementation Status

| Issue | Status | Notes |
|-------|--------|-------|
| 1.1 Missing output_type | IMPLEMENTED | Added `AgentOutput` union type (SchedulingResponse, ClarificationRequest, ErrorResponse) |
| 1.2 Tools via constructor | SKIPPED | Current approach is valid per docs |
| 1.3 Logfire instrumentation | IMPLEMENTED | Changed to `logfire.instrument_pydantic_ai()` |
| 2.1 Custom SSE streaming | IMPROVED | Better event types, type guards added |
| 2.2 stream_text(delta=True) | IMPROVED | Proper message history now preserved |
| 3.1 Manual history concatenation | IMPLEMENTED | Using `message_history` parameter with `ModelMessagesTypeAdapter` |
| 4.1 AgentDeps as regular class | IMPLEMENTED | Converted to `@dataclass` |
| 5.1 Tool docstrings | IMPLEMENTED | Added detailed Args/Returns/Raises docstrings |
| 5.2 Error as strings | IMPLEMENTED | Added `ModelRetry` for recoverable errors |
| 5.3 Direct DB access | KEPT | Pragmatic for current use case |
| 6.1 Custom SSE events | IMPROVED | Added typed SSE events in frontend |
| 7.1 Missing UsageLimits | IMPLEMENTED | Added request/token limits |
| 7.2 Model fallback | SKIPPED | Per user request |
| 8.1 AG-UI protocol | PARTIAL | Improved typing, full AG-UI for later |
| 8.2 Structured outputs | IMPLEMENTED | Added AgentOutput union type |
| 8.3 Testing infrastructure | SKIPPED | Per user request |

---

## 1. Agent Definition Issues

### Issue 1.1: Missing Type Annotations for Agent Generic Parameters [IMPLEMENTED]

**Current Implementation** (`backend/agents/scheduling_agent.py`):
```python
scheduling_agent = Agent(
    settings.GOOGLE_DEFAULT_MODEL,
    deps_type=AgentDeps,
    # ... no output_type specified
)
```

**Problem**: 
- The `Agent` class is generic over `DepsType` and `OutputType`
- Not specifying `output_type` means the agent returns unstructured `str` output
- No type safety for agent responses

**Official Documentation Pattern**:
```python
from pydantic import BaseModel

class SchedulingOutput(BaseModel):
    response: str
    tool_calls_made: list[str] = []
    requires_clarification: bool = False

agent = Agent[AgentDeps, SchedulingOutput](
    'google-gla:gemini-2.5-flash',
    deps_type=AgentDeps,
    output_type=SchedulingOutput,
)
```

**Fix Applied**:
- Added `AgentOutput` union type to `backend/models/io.py`
- Agent now uses `output_type=AgentOutput`
- Responses are typed as `SchedulingResponse | ClarificationRequest | ErrorResponse`

**Priority**: Medium

---

### Issue 1.2: Tools Registered via Constructor Instead of Decorator

**Current Implementation** (`backend/agents/scheduling_agent.py`):
```python
scheduling_agent = Agent(
    # ...
    tools=[
        create_activity_tool, 
        create_relationship_tool, 
        # ... 16+ tools listed
    ],
)
```

**Problem**:
- Tools are standalone async functions passed to `tools=[]`
- This is valid but less idiomatic than the decorator approach
- Makes it harder to organize tools and their relationship to the agent

**Official Documentation Pattern** (preferred):
```python
scheduling_agent = Agent(
    'google-gla:gemini-2.5-flash',
    deps_type=AgentDeps,
)

@scheduling_agent.tool
async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """Creates a new activity in the P6 schedule."""
    # ...
```

**Status**: SKIPPED - Current approach is valid per docs: "Tools can also be passed to the `tools` kwarg"

**Priority**: Low (current approach is valid, just less idiomatic)

---

### Issue 1.3: Missing `instrument` Configuration for Logfire [IMPLEMENTED]

**Current Implementation** (`backend/api/main.py`):
```python
if settings.LOGFIRE_TOKEN:
    logfire.configure(token=settings.LOGFIRE_TOKEN)
    logfire.instrument_fastapi(app)
    logfire.instrument_pydantic()  # This is incorrect API
```

**Problem**:
- `logfire.instrument_pydantic()` is not the correct API
- Missing `logfire.instrument_pydantic_ai()` which is the proper integration
- Agent runs are not being instrumented at the SDK level

**Official Documentation Pattern**:
```python
import logfire
from pydantic_ai import Agent

logfire.configure(send_to_logfire='if-token-present')  # or with token
logfire.instrument_pydantic_ai()  # THIS IS THE CORRECT CALL

agent = Agent('openai:gpt-4')
```

**Proposed Fix**:
```python
# backend/api/main.py
if settings.LOGFIRE_TOKEN:
    logfire.configure(token=settings.LOGFIRE_TOKEN)
    logfire.instrument_fastapi(app)
    logfire.instrument_pydantic_ai()  # Add this
    # logfire.instrument_httpx(capture_all=True)  # Optional: capture HTTP requests
```

**Priority**: High - Critical for production observability

---

## 2. Streaming Implementation Issues

### Issue 2.1: Custom SSE Implementation Instead of Using Built-in Methods

**Current Implementation** (`backend/api/routers/chat.py`):
```python
def sse_event(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"

# Manual streaming with custom events
async with scheduling_agent.run_stream(full_message, deps=deps) as result:
    async for text in result.stream_text(delta=True):
        yield sse_token_event(text)
```

**Problem**:
- Custom SSE formatting is fragile and doesn't follow AG-UI protocol
- Missing tool call events (`FunctionToolCallEvent`, `FunctionToolResultEvent`)
- Missing proper event types for frontend state synchronization
- `run_stream()` stops at first output - may miss tool calls after output

**Official Documentation - AG-UI Pattern**:
```python
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter

@app.post('/chat/')
async def run_agent(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(request, agent=agent, deps=deps)
```

**Official Documentation - Manual Streaming with Events**:
```python
# For full control, use run_stream_events() or agent.iter()
async with agent.run_stream_events(prompt, deps=deps) as stream:
    async for event in stream:
        if isinstance(event, PartStartEvent):
            # Handle start of new part
        elif isinstance(event, PartDeltaEvent):
            # Handle streaming delta
        elif isinstance(event, FunctionToolCallEvent):
            # Tool is being called
        elif isinstance(event, FunctionToolResultEvent):
            # Tool returned result
        elif isinstance(event, FinalResultEvent):
            # Agent completed
```

**Proposed Fix**:
1. **Option A (Recommended)**: Adopt AG-UI protocol for frontend compatibility
   - Install `pydantic-ai-slim[ag-ui]`
   - Use `AGUIAdapter` for standardized events
   - Update frontend to use AG-UI client

2. **Option B**: Use `run_stream_events()` for custom streaming
   - Emit tool call events to frontend
   - Better state management for thinking indicators

**Priority**: High - Affects UX and debugging capability

---

### Issue 2.2: Using `result.stream_text(delta=True)` May Lose Final Message

**Current Implementation**:
```python
async for text in result.stream_text(delta=True):
    full_response += text
    yield sse_token_event(text)
```

**Problem**:
Per documentation: "The final output message will NOT be added to result messages if you use `.stream_text(delta=True)`"

This means message history may be incomplete.

**Proposed Fix**:
```python
async with scheduling_agent.run_stream(full_message, deps=deps) as result:
    async for text in result.stream_text():  # Remove delta=True
        yield sse_token_event(text)
    
    # Use new_messages() for proper history
    new_msgs = result.new_messages()
```

Or use `stream_output()` for structured output streaming.

**Priority**: Medium

---

## 3. Message History Management Issues

### Issue 3.1: Manual History Management Instead of Using Pydantic AI's Built-in

**Current Implementation**:
```python
# Custom conversation storage in Supabase
history = await conv_repo.get_message_history(conversation_id, limit=20)
history_text = ""
if len(history) > 1:
    history_text = "\n\nConversation history:\n"
    for msg in history[:-1]:
        role = "User" if msg.role == "user" else "Assistant"
        history_text += f"{role}: {msg.content}\n"

full_message = f"...{history_text}\nCurrent request: {req.message}"
```

**Problem**:
- History is concatenated as plain text, not using Pydantic AI's `message_history` parameter
- Loses tool call context between messages
- Loses message metadata (timestamps, parts structure)
- Agent doesn't have access to proper conversation context

**Official Documentation Pattern**:
```python
from pydantic_ai import ModelMessagesTypeAdapter

# Store messages using the type adapter
await database.add_messages(result.new_messages_json())

# Load and pass to agent
messages = await database.get_messages()
message_list = []
for row in messages:
    message_list.extend(ModelMessagesTypeAdapter.validate_json(row[0]))

# Pass as message_history parameter
async with agent.run_stream(
    prompt, 
    message_history=message_list,  # THIS IS THE KEY
    deps=deps
) as result:
    # ...
```

**Proposed Fix**:
1. Store messages using `result.new_messages_json()` which serializes the proper `ModelMessage` structure
2. Load using `ModelMessagesTypeAdapter.validate_json()`
3. Pass to agent via `message_history=` parameter
4. This preserves tool calls, parts, timestamps, and all metadata

**Database Schema Update Required**:
```sql
-- Current: stores simple role/content
-- Needed: stores serialized ModelMessage JSON
ALTER TABLE conversation_messages ADD COLUMN message_list JSONB;
```

**Priority**: High - Critical for multi-turn conversations with tools

---

### Issue 3.2: Message History Processor Not Used

**Problem**:
For conversations, you may want to limit history size or summarize old messages. Pydantic AI provides `ModelHistoryProcessor` for this.

**Official Documentation Pattern**:
```python
from pydantic_ai.settings import ModelSettings

agent = Agent(
    'openai:gpt-4',
    model_settings=ModelSettings(
        # Configure history processing
    ),
)
```

**Proposed Fix**:
Consider implementing a history processor to:
- Limit context window usage
- Summarize older messages
- Remove tool call details from old messages

**Priority**: Low - Nice to have for cost optimization

---

## 4. Dependencies Implementation Issues

### Issue 4.1: AgentDeps Not Defined as Dataclass

**Current Implementation** (`backend/tools/p6_tools.py`):
```python
class AgentDeps:
    def __init__(self, service: SchedulingService, vector_service: VectorService = None, conn=None):
        self.service = service
        self.vector_service = vector_service
        self.conn = conn
```

**Problem**:
- Not a dataclass as recommended by documentation
- Missing type hints on instance variables
- Manual `__init__` instead of generated one

**Official Documentation Pattern**:
```python
from dataclasses import dataclass

@dataclass
class AgentDeps:
    service: SchedulingService
    vector_service: VectorService | None = None
    conn: Any | None = None  # Consider proper typing
```

**Proposed Fix**:
```python
from dataclasses import dataclass
from typing import Any

@dataclass
class AgentDeps:
    service: SchedulingService
    vector_service: VectorService | None = None
    conn: Any | None = None  # Or use proper connection type
```

**Priority**: Low - Current implementation works, but dataclass is cleaner

---

## 5. Tool Implementation Issues

### Issue 5.1: Tools Not Using Proper Docstrings for Schema Generation

**Current Implementation**:
```python
async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """
    Creates a new activity in the P6 schedule.
    """
```

**Problem**:
- Docstrings are minimal
- Missing parameter documentation for the model
- The model relies on docstrings for understanding tool usage

**Official Documentation Guidance**:
> "Pydantic AI extracts the [JSON schema](https://json-schema.org/) from the function's signature and docstring to build the tool schema."

**Proposed Fix**:
```python
async def create_activity_tool(
    ctx: RunContext[AgentDeps], 
    req: ActivityCreateRequest
) -> str:
    """Creates a new activity in the P6 schedule.
    
    Use this tool when the user wants to add a new task/activity to their project.
    Requires: task_code (unique ID like 'A1000'), task_name, wbs_id, and proj_id.
    
    Args:
        ctx: Agent context with database connection
        req: Activity creation request with task details
        
    Returns:
        Success message with created activity ID, or error message
    """
```

**Priority**: Medium - Improves model's tool selection accuracy

---

### Issue 5.2: Error Handling Returns Strings Instead of Raising ModelRetry

**Current Implementation**:
```python
async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    try:
        task_id = ctx.deps.service.create_activity(req, conn=ctx.deps.conn)
        return f"Successfully created activity {req.task_code} with ID {task_id}."
    except Exception as e:
        logfire.error("Error in create_activity_tool", error=str(e))
        return f"Error creating activity: {str(e)}"
```

**Problem**:
- Errors returned as strings don't trigger retry logic
- Model doesn't get proper feedback to try again with different parameters
- No structured error handling

**Official Documentation Pattern**:
```python
from pydantic_ai import ModelRetry

async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    try:
        task_id = ctx.deps.service.create_activity(req, conn=ctx.deps.conn)
        return f"Successfully created activity {req.task_code} with ID {task_id}."
    except ValidationError as e:
        # Retryable error - model should try with different parameters
        raise ModelRetry(f"Invalid parameters: {e}. Please check task_code format.")
    except DuplicateKeyError as e:
        raise ModelRetry(f"Activity {req.task_code} already exists. Use a different task_code.")
    except Exception as e:
        # Non-retryable error - return as message
        logfire.error("Error in create_activity_tool", error=str(e))
        return f"Error creating activity: {str(e)}"
```

**Proposed Fix**:
- Use `ModelRetry` for errors where the model can fix the input
- Return error strings only for non-recoverable errors
- Configure retry limits: `retries=3` in agent definition

**Priority**: Medium - Improves agent self-correction

---

### Issue 5.3: Direct Database Access in Tools

**Current Implementation** (`search_activity_tool`):
```python
# Direct SQL query inside tool
cursor = ctx.deps.conn.cursor()
cursor.execute("SELECT TASK_CODE, TASK_NAME FROM TASK WHERE TASK_ID = ?", (task_id,))
```

**Problem**:
- Violates architecture guidelines (tools should use services/repos)
- Mixes data access with agent logic
- Makes testing harder

**Proposed Fix**:
- Add helper methods to `SchedulingService` for these queries
- Tools should only call service methods

**Priority**: Medium - Architecture improvement

---

## 6. Frontend Streaming Issues

### Issue 6.1: Custom SSE Parsing Instead of AG-UI SDK

**Current Implementation** (`frontend/hooks/useAGUIStream.ts`):
```typescript
// Manual SSE parsing
if (line.startsWith('data: ')) {
    const dataStr = line.slice(6);
    const data = JSON.parse(dataStr);
    
    if (data.type === 'token') {
        // ...
    } else if (data.type === 'reasoning') {
        // ...
    }
}
```

**Problem**:
- File is named `useAGUIStream` but doesn't use AG-UI protocol
- Custom event types don't match any standard
- Missing tool call visualization
- No state synchronization support

**Official AG-UI Integration**:
The AG-UI protocol provides:
- Standardized events: `PartStartEvent`, `PartDeltaEvent`, `ToolCallEvent`, etc.
- State management between frontend and backend
- Frontend tool execution support
- CopilotKit compatibility

**Proposed Fix**:
1. Backend: Use `AGUIAdapter` from `pydantic_ai.ui.ag_ui`
2. Frontend: Use AG-UI client library or CopilotKit
3. This provides standardized streaming with tool call visualization

**Frontend Integration Option**:
```typescript
// Using CopilotKit (compatible with AG-UI)
import { CopilotKit } from "@copilotkit/react-core";

// Or direct AG-UI client
import { AGUIClient } from "@ag-ui/client";
```

**Priority**: High - Significant UX improvement

---

## 7. Production Readiness Issues

### Issue 7.1: Missing Usage Limits Configuration

**Problem**:
No limits on token usage per request, which could lead to cost issues.

**Official Documentation Pattern**:
```python
from pydantic_ai.settings import UsageLimits

result = await agent.run(
    prompt,
    usage_limits=UsageLimits(
        request_limit=10,        # Max model requests per run
        response_token_limit=2000,  # Max output tokens
    ),
)
```

**Proposed Fix**:
Add usage limits to prevent runaway costs:
```python
from pydantic_ai.settings import UsageLimits

DEFAULT_USAGE_LIMITS = UsageLimits(
    request_limit=15,  # Max tool call loops
    response_token_limit=4000,
)

async with agent.run_stream(msg, deps=deps, usage_limits=DEFAULT_USAGE_LIMITS) as result:
    # ...
```

**Priority**: High - Production cost control

---

### Issue 7.2: Missing Model Fallback Configuration

**Problem**:
Single model configuration - if Gemini fails, everything fails.

**Official Documentation Pattern**:
```python
from pydantic_ai.models import FallbackModel

model = FallbackModel(
    'google-gla:gemini-2.5-flash',  # Primary
    'openai:gpt-4o-mini',            # Fallback
)

agent = Agent(model, deps_type=AgentDeps)
```

**Proposed Fix**:
Configure fallback model for reliability.

**Priority**: Medium - Production reliability

---

### Issue 7.3: Missing Output Validators

**Problem**:
No validation of model responses before returning to user.

**Official Documentation Pattern**:
```python
@agent.output_validator
async def validate_response(ctx: RunContext[AgentDeps], output: SchedulingOutput) -> SchedulingOutput:
    """Validate agent output before returning."""
    if not output.response:
        raise ModelRetry("Response cannot be empty")
    if len(output.response) < 10:
        raise ModelRetry("Response too short, please provide more detail")
    return output
```

**Proposed Fix**:
Add output validators to ensure response quality.

**Priority**: Low - Nice to have

---

## 8. Missing Features for Production

### Issue 8.1: No AG-UI Protocol Support

**Description**:
The application doesn't implement AG-UI protocol which provides:
- Standardized frontend-backend communication
- Tool call visualization
- State synchronization
- CopilotKit integration readiness

**Proposed Implementation**:

**Backend** (`backend/api/routers/chat_agui.py`):
```python
from fastapi import FastAPI, Request
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter

@router.post("/chat/agui")
async def run_agent(request: Request) -> Response:
    # Build deps from request context
    deps = await build_deps_from_request(request)
    return await AGUIAdapter.dispatch_request(
        request, 
        agent=scheduling_agent,
        deps=deps,
    )
```

**Frontend**: Use AG-UI client or CopilotKit

**Priority**: High - Modern UI integration

---

### Issue 8.2: No Structured Output Types

**Description**:
Agent returns plain strings. Should return structured data for:
- Clarification requests
- Action confirmations
- Error states
- Multi-part responses

**Proposed Models**:
```python
from pydantic import BaseModel
from typing import Literal

class ClarificationRequest(BaseModel):
    """Agent needs more information."""
    question: str
    options: list[str] | None = None

class ActionResult(BaseModel):
    """Result of a tool action."""
    success: bool
    message: str
    action_type: str
    affected_items: list[str] = []

class SchedulingResponse(BaseModel):
    """Main agent response."""
    response_type: Literal["message", "clarification", "action_result", "error"]
    content: str
    clarification: ClarificationRequest | None = None
    actions: list[ActionResult] = []

# Use as output_type
agent = Agent[AgentDeps, SchedulingResponse](
    model,
    deps_type=AgentDeps,
    output_type=SchedulingResponse,
)
```

**Priority**: Medium - Better frontend handling

---

### Issue 8.3: No Testing Infrastructure

**Description**:
No test files for agent behavior using `TestModel`.

**Official Documentation Pattern**:
```python
from pydantic_ai.models.test import TestModel

def test_scheduling_agent():
    model = TestModel()
    
    with scheduling_agent.override(model=model):
        result = scheduling_agent.run_sync("Create activity A1000")
        
    # Assert on calls made
    assert len(model.calls) == 1
    assert "create_activity" in str(model.calls[0].tool_name)
```

**Proposed Fix**:
Add test suite in `backend/tests/test_scheduling_agent.py`

**Priority**: High - Production testing

---

## Summary: Priority Matrix

| Issue | Priority | Effort | Impact |
|-------|----------|--------|--------|
| 1.3 Logfire instrument_pydantic_ai | High | Low | Observability |
| 2.1 AG-UI Protocol | High | High | UX, Debugging |
| 3.1 Proper Message History | High | Medium | Conversation Quality |
| 6.1 Frontend AG-UI | High | High | UX |
| 7.1 Usage Limits | High | Low | Cost Control |
| 8.3 Testing Infrastructure | High | Medium | Reliability |
| 1.1 Structured Output Types | Medium | Medium | Type Safety |
| 2.2 stream_text delta issue | Medium | Low | History |
| 5.1 Tool Docstrings | Medium | Low | Tool Selection |
| 5.2 ModelRetry Usage | Medium | Medium | Self-Correction |
| 5.3 Direct DB Access | Medium | Medium | Architecture |
| 7.2 Model Fallback | Medium | Low | Reliability |
| 8.2 Structured Output | Medium | Medium | Frontend UX |
| 1.2 Tool Decorator Style | Low | Medium | Code Style |
| 3.2 History Processor | Low | Medium | Cost Optimization |
| 4.1 Dataclass Deps | Low | Low | Code Style |
| 7.3 Output Validators | Low | Low | Quality |

---

## Recommended Implementation Order

### Phase 1: Critical Fixes (Week 1)
1. ✅ Fix `logfire.instrument_pydantic_ai()` call
2. ✅ Add usage limits to prevent cost overruns
3. ✅ Fix message history to use `message_history` parameter

### Phase 2: Streaming Improvements (Week 2)
4. Implement AG-UI adapter on backend
5. Add basic test infrastructure
6. Update frontend to use AG-UI events (or simplified version)

### Phase 3: Quality Improvements (Week 3)
7. Add structured output types
8. Improve tool docstrings
9. Implement ModelRetry for recoverable errors
10. Add output validators

### Phase 4: Architecture & Polish (Week 4)
11. Refactor tools to use services (no direct DB)
12. Add model fallback
13. Convert AgentDeps to dataclass
14. Add comprehensive test suite

---

## Required Package Updates

```pip
# requirements.txt additions/updates
pydantic-ai>=1.26.0  # Ensure latest version
pydantic-ai-slim[ag-ui]  # AG-UI support (alternative to full pydantic-ai)
logfire>=2.0  # Latest logfire
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/api/main.py` | Fix logfire instrumentation |
| `backend/agents/scheduling_agent.py` | Add output_type, usage_limits |
| `backend/api/routers/chat.py` | Implement proper message history, AG-UI adapter |
| `backend/tools/p6_tools.py` | Convert to dataclass, add ModelRetry |
| `backend/models/io.py` | Add structured output models |
| `backend/repositories/conversation_repository.py` | Store/load ModelMessage JSON |
| `frontend/hooks/useAGUIStream.ts` | Update to handle AG-UI events |
| `requirements.txt` | Add AG-UI dependencies |

---

**Document Version**: 1.0  
**Created**: Based on Pydantic AI v1.26.0 documentation  
**Status**: Pending Review
