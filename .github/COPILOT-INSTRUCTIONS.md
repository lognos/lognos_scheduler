# GitHub Copilot Instructions

### Backend-Only Assistant Services

## Purpose

Guide GitHub Copilot when generating backend services that expose:

* **Typed FastAPI endpoints**
* **Pydantic AI agents** processing structured/unstructured content
* **Internal Pydantic AI Tool functions** for local side-effects
* **External MCP tools** for interoperability
* **A2A protocol** for Lognos internal agent-to-agent communication


No icons or emojis are allowed in the codebase.

---

## 1) Project Scope & Output Rules

Valid output includes:

* FastAPI routers
* Pydantic v2 IO models and domain models
* Services for workflow orchestration and transactions
* Repositories for persistence abstraction
* Pydantic AI agents (reasoning only)
* Internal Pydantic AI Tools for local actions
* MCP server + MCP tool wrappers for **external** calls
* Async test suites (pytest)
* CI/CD scripts, dockerization, changelog updates

Prohibited:

* Direct database access from routers or agents
* Silent logging or handling of errors
* Runtime type coercion (strict input/output validation required)

---

## 2) Architecture Structure

```
/sch_backend
  /routers          # FastAPI endpoints (IO validation + auth only)
  /services         # Business logic, transactions, orchestration
  /agents           # Pydantic AI agents (reasoning & internal tools use)
  /repositories     # Data persistence adapters (DB/API)
  /mcp              # MCP server + tool wrappers for external access
  /models           # io_request.py / io_response.py / domain.py
  /config           # strict environment configuration
  /utils            # helpers, error mapping, validation helpers
  main.py           # FastAPI app creation
CHANGELOG.md
docs/changes/
Dockerfile
```

Boundaries:

```
Router → Service → Repository
               ↑
           Agent (local tools only)
               ↑
         A2A + External MCP
```

Copilot must maintain this separation.

---

## 3) API Surface (FastAPI)

Base path:

```
/api/v1/
```

Each endpoint must:

* Use **strict** Pydantic IO models (`ConfigDict(strict=True)`)
* Return **typed responses**
* Be fully async
* Delegate all business logic to **services**

Security & validation:

* Routers handle authentication / authorization only
* No database logic in routers

---

## 4) Agents (Pydantic AI)

Source of truth: [https://ai.pydantic.dev/](https://ai.pydantic.dev/)

### Agent responsibilities

Agents perform reasoning tasks:

* Summarization
* Classification
* Recommendation
* Action extraction
* Entity extraction
* Contextual interpretation
* Natural language understanding and generation
* Tool selection and orchestration (automatic via Pydantic AI)

### Conversational agents

Agents should support **multi-turn conversations** with context preservation:

* Accept `conversation_id` to track dialogue state
* Accept `message_history` for context from previous turns
* Store conversation history in database for stateful interactions
* Generate responses considering full conversation context

Example:
```python
class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    
    conversation_id: StrictStr | None = None  # Track multi-turn dialogue
    message: StrictStr
    message_history: list[Message] | None = None  # Previous turns
    sender_email: StrictStr

# Agent processes with context
result = await agent.run(
    ChatRequest(
        conversation_id="conv_123",
        message="add Sarah too",  # References previous context
        message_history=[...],  # Previous messages
        sender_email="user@company.com"
    )
)
```

### Internal rules

* Agents **do not** perform writes directly
* Agents **do not** call this service's HTTP or MCP server endpoints
* Agents **do not** call other services via HTTP (use A2A protocol instead)

### Allowed internal actions

* Local **Pydantic AI Tools** for side effects (e.g. write to memory, send notifications, query data)
* Pydantic AI automatically determines which tools to invoke based on agent's reasoning

### Strict models required

* `input_model` - strictly typed input (conversation context + current message)
* `output_model` - strictly typed output with success/clarification status

---

## 5) Tooling: A2A vs Local Tools vs MCP

### Local Pydantic AI Tools (internal actions)

**Purpose**: Execute side effects within this service

**Implemented as**: Pydantic AI Tool functions decorated with `@agent.tool`

**Examples**: 
* Query database
* Send email
* Store data
* Search documents
* Resolve user identities

**Key principle**: Agent automatically selects and orchestrates tools based on reasoning

```python
@agent.tool
async def query_data_tool(
    ctx: RunContext[Dependencies],
    query: str,
    filters: dict
) -> QueryResult:
    """Query data with filters."""
    return await ctx.deps.service.query(query, filters)
```

### A2A Protocol (assistant-to-assistant communication)

**Purpose**: Enable communication between different assistant services

**Use cases**:
1. **Outbound**: This assistant calls other specialized assistants
2. **Inbound**: External orchestrator/supervisor calls this assistant

#### Outbound A2A (assistant → other assistants)

Implemented as **Pydantic AI Tools** that use A2A client:

```python
@agent.tool
async def schedule_meeting_tool(
    ctx: RunContext[Dependencies],
    participants: list[str],
    duration_minutes: int
) -> ScheduleResult:
    """Schedule meeting via Scheduling Assistant."""
    
    # A2A call to another assistant
    response = await ctx.deps.a2a_client.call(
        assistant="scheduling",
        method="find_available_slots",
        params={
            "participants": participants,
            "duration_minutes": duration_minutes
        }
    )
    
    return ScheduleResult(**response)
```

#### Inbound A2A (orchestrator → assistant)

**Critical pattern**: Orchestrator may need multi-turn clarifications

**Implementation**: A2A handler accepts conversation context in payload and delegates to same agent used by chat API

```python
# A2A server method
@a2a_server.method("process_task")
async def handle_a2a_task(request: A2ATaskRequest) -> A2AResponse:
    """
    Process task from orchestrator with conversation support.
    Enables multi-turn clarifications.
    """
    
    # Transform A2A request to agent's native input format
    agent_request = ChatRequest(
        conversation_id=request.conversation_id or f"a2a_{request.task_id}",
        message=request.current_message,
        message_history=request.message_history or [],
        sender_email=request.orchestrator_context.get("email", "orchestrator@system")
    )
    
    # Reuse same agent logic (not a separate code path!)
    result = await agent.run(agent_request)
    
    # Return A2A response with status
    if result.needs_clarification:
        return A2AResponse(
            status="needs_clarification",
            question=result.clarification_question,
            conversation_id=result.conversation_id,
            options=result.clarification_options
        )
    else:
        return A2AResponse(
            status="completed",
            result=result.data,
            conversation_id=result.conversation_id
        )


# A2A request model (generic for all assistants)
class A2ATaskRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    
    task_id: StrictStr
    conversation_id: StrictStr | None = None  # Track multi-turn dialogue
    current_message: StrictStr
    message_history: list[Message] | None = None  # Previous turns
    orchestrator_context: dict  # Caller identity, permissions, etc.
```

**Multi-turn A2A flow**:
```
Turn 1:
Orchestrator → A2A("send report to John")
Assistant → A2A Response(status="needs_clarification", question="Which John?")

Turn 2:
Orchestrator → A2A("John Smith", conversation_id="conv_123")
Assistant → A2A Response(status="completed", result={...})
```

**Key principles**:
- A2A is the **transport**, conversation is the **content**
- Same agent handles both `/chat` API and A2A requests (no duplication)
- Conversation ID bridges multiple A2A calls
- Assistant stores conversation history (orchestrator just tracks conversation_id)

### MCP Server (external interoperability)

**Purpose**: Expose tools to external agents/systems outside the Lognos platform

**Implementation**: Thin wrappers around internal tools

```python
# MCP tool wrapper
@mcp_server.tool("query_data")
async def mcp_query_data(query: str, filters: dict) -> dict:
    """Expose query_data tool to external agents."""
    
    # Delegate to same service layer used by internal tools
    result = await service.query(query, filters)
    return result.model_dump()
```

### Protocol boundaries summary

| Scenario | Protocol | Implementation |
|----------|----------|----------------|
| Agent needs to perform action in this service | Local Tool | Pydantic AI Tool function |
| Agent needs capability from another assistant | A2A (outbound) | Pydantic AI Tool wrapping A2A client |
| Orchestrator needs to delegate task to this assistant | A2A (inbound) | A2A server method delegating to agent |
| External system needs to call this service | MCP | MCP server wrapping internal tools |
| User interacts with assistant | HTTP API | FastAPI endpoint delegating to agent |

**Internal execution flow**:
```
Agent → Local Tool → Service → Repository → DB
```

**Cross-assistant flow (outbound)**:
```
Agent → A2A Tool → A2A Client → Other Assistant Agent → Local Tool → Service
```

**Orchestrator flow (inbound)**:
```
Orchestrator → A2A → A2A Server → Agent (same as /chat) → Local Tools → Service
```

**External caller flow**:
```
External → MCP Server → MCP Tool → Service → Repository
```

### Anti-patterns (must avoid)

Agents must never:

* Call this service's FastAPI routes internally
* Call this service's MCP endpoints internally
* Call other assistants via HTTP (use A2A protocol)
* Implement separate logic for A2A vs HTTP API (reuse same agent)

Tools are defined following:
[https://ai.pydantic.dev/tools/](https://ai.pydantic.dev/tools/)

---

## 6) Data Access & Transactions

Primary approach:

* **Supabase Python Client** (`supabase-py`) for all database operations
* Repositories wrap Supabase client methods

Simple operations:

* Direct Supabase queries via repository methods

Multi-step or atomic workflows:

* Use **Supabase transactions** in service layer:

```python
async with supabase.transaction() as txn:
    result_one = await repo.action_one(txn, ...)
    result_two = await repo.action_two(txn, ...)
    return result_one, result_two
```

Repositories receive transaction context when needed, never manage transactions directly.

---

## 7) Environment Configuration

* Implement using `pydantic_settings`
* Fail fast on missing variables
* Prefix environment variables uniquely per assistant service
  Example:

  * `RISK_*`, `SCHED_*`, `EVM_*`, `COMM_*`, etc.

Local:

* `.env.example` tracked with descriptions
* `.env` ignored

Production:

* Secret providers (Azure Key Vault, etc.)

Never hard-code secrets.

---

## 8) Observability (Logfire)

Reference: [https://logfire.pydantic.dev/docs/](https://logfire.pydantic.dev/docs/)

Rules:

* No `print` usage
* Use spans around:

  * router entrypoints
  * service operations
  * repository calls
  * agent executions
  * MCP tool calls
* No sensitive data logging (tokens, PII, keys)

---

## 9) Code Quality & Testing Requirements

* Fully async execution path
* `ruff` for formatting & lint
* `mypy` for typing
* `pytest` with async fixtures

Blocking synchronous code must be wrapped:

```python
return await run_in_threadpool(fn, *args)
```

---

## 10) Versioning & Release Documentation

Versioning:

* Start each assistant at `0.1.0`
* Follow SemVer strictly

Changelog rules must follow:
[https://keepachangelog.com/en/1.1.0/](https://keepachangelog.com/en/1.1.0/)

Extended release notes per version:

```
docs/changes/YYYY-MM-DD-vX.Y.Z.md
```

Every change must include changelog updates.

Changelog & Extended Release Notes

Projects must maintain a human-readable changelog at the repository root:

CHANGELOG.md


Requirements

Follow Semantic Versioning (SemVer) for tags and entries.

Use Keep a Changelog style sections.

New releases are added at the top.

Keep the language user-facing and concise; deep technical details live in extended notes.

Every release entry must include links to extended notes (when present) and a compare link.

Standard sections

Added

Changed

Fixed

Removed (if applicable)

Breaking Changes (if applicable)

Migration Guide (if applicable)

Links

Extended notes (in docs/changes/…)

Git compare link (previous tag → current tag)

Extended notes location

Store detailed release documentation under:

docs/changes/YYYY-MM-DD-vX.Y.Z.md


Extended notes should include: schema/migration details, architecture decisions, diagrams, rollout/rollback steps, and any debugging guides.

Authoring guidance (Copilot must follow)

Update CHANGELOG.md with every release.

Create an extended notes file only when there are breaking changes, migrations, or non-obvious technical shifts.

Never rewrite history or remove past entries.

Do not include raw commit logs; summarize meaningful changes.

Templates (copy-paste)

CHANGELOG.md entry template:

## [0.1.0] - 2025-10-25
### Added
- …

### Changed
- …

### Fixed
- …

### Breaking Changes
- …

### Migration Guide
- …

### Links
- Extended notes: docs/changes/2025-10-25-v0.1.0.md
- Compare: <repo-url>/compare/v0.0.0...v0.1.0


docs/changes/YYYY-MM-DD-vX.Y.Z.md template:

# 2025-10-25 — v0.1.0

## Overview
Short paragraph describing what this release delivers.

## API Surface
- Endpoints added/changed/removed with brief notes.

## Models & Validation
- IO model changes, strictness updates, deprecations.

## Services & Data
- Transaction patterns, repository changes, schema/migrations.

## Agents & Tools
- Agent behaviors, internal Pydantic AI tools, A2A/MCP exposure.

## Observability
- New spans, fields, correlation IDs.

## Security
- Auth/authorization updates, secrets handling notes.

## Migration Steps
- Exact steps for operators (pre/post deploy, data backfills, flags).

## Rollback
- How to revert safely and what to verify.

## Known Issues / Next
- Caveats, follow-ups, planned deprecations.


Automation (optional)

If using Changesets or semantic-release:

Auto-draft the CHANGELOG entry from commits.

Ensure Copilot adds/edits Migration Guide and Extended Notes links as needed.

Human review is required before tagging a release.
---

## 11) CI/CD & Deployment

* PR: Build, lint, type-check, test
* Main merge: version bump, tag, docker build, deploy revision
* Each assistant deploys independently
* Health probe: `/api/v1/health`

---

## 12) Example Patterns

Strict IO:

```python
class AnalyzeInput(BaseModel):
    model_config = ConfigDict(strict=True)
    project_id: StrictStr
    content: StrictStr
```

Router → Service:

```python
@router.post("/analyze")
async def analyze(req: AnalyzeInput):
    return await AnalysisService().analyze(req)
```

Agent with Pydantic AI:

```python
output = await risk_agent.run(RiskInput(...))
```

---

## 13) Anti-patterns

Copilot must NEVER:

* Suggest frontend concepts
* Place DB calls in agents or routers
* Call this service’s own API internally
* Use MCP server endpoints internally
* Silence exceptions or rely on bare return dicts
* Invent undocumented features or schemas

---

## 14) Reference Documentation

* Pydantic AI: [https://ai.pydantic.dev/](https://ai.pydantic.dev/)
* Pydantic: [https://docs.pydantic.dev/latest/](https://docs.pydantic.dev/latest/)
* FastAPI: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
* MCP Protocol: [https://modelcontextprotocol.io/docs/getting-started/intro](https://modelcontextprotocol.io/docs/getting-started/intro)
* A2A Protocol: [https://a2a-protocol.org/latest/](https://a2a-protocol.org/latest/)
* Supabase Python Client: [https://supabase.com/docs/reference/python/introduction](https://supabase.com/docs/reference/python/introduction)

---

## 15) Defaults

If unsure:

* Use strict type safety everywhere
* Prefer internal tools over network calls
* Apply A2A only for cross-assistant interactions
* Instrument with Logfire spans
* Update changelog and documentation

---
