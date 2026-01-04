# Tool Architecture Transition Completion Proposal

**Status:** Proposal  
**Date:** 2026-01-04  
**Relates to:** [tool-architecture-proposal.md](tool-architecture-proposal.md)

---

## Executive Summary

This proposal completes the tool architecture transition outlined in the original proposal. The modular structure (`p6/`, `workspace/`, `indexing/`) is already in place, but several gaps remain for production readiness:

1. Legacy `p6_tools.py` still exists alongside new structure
2. Workspace tools use individual parameters instead of Pydantic models
3. Missing workspace tools (`delete_*_ws`)
4. No idempotency guards on create operations
5. No standardized tool creation process

---

## 1. Parameter Standardization: Pydantic Request Models

### Current State Gap

| Tool Type | Parameter Style | Example |
|-----------|-----------------|---------|
| P6 tools | ✅ Pydantic request models | `create_activity_p6(ctx, req: ActivityCreateRequest)` |
| Workspace tools | ❌ Individual parameters | `add_activity_ws(ctx, task_code: str, task_name: str, ...)` |

### Why Pydantic Models Are Better

1. **Validation at the edge**: Invalid data fails immediately with clear errors
2. **Self-documenting**: Field descriptions appear in tool schemas
3. **Refactoring safety**: Adding/removing fields is centralized
4. **Consistent serialization**: LLMs receive identical schema patterns
5. **Testability**: Request objects are easier to construct in tests

### Standard Pattern

```python
# backend/models/io.py - Request model definition
class AddActivityWsRequest(BaseModel):
    """Request to add an activity to the workspace."""
    model_config = ConfigDict(strict=True)
    
    task_code: StrictStr = Field(
        ..., 
        description="Unique activity code for the new activity"
    )
    task_name: StrictStr = Field(
        ..., 
        description="Name of the new activity"
    )
    original_duration_hours: int = Field(
        ..., 
        ge=1,
        description="Duration in hours (e.g., 40 for 5 days)"
    )
    wbs_id: int | None = Field(
        default=None,
        description="Optional WBS ID to assign the activity to"
    )
    target_start_date: str | None = Field(
        default=None,
        description="Target start date in ISO format (YYYY-MM-DD)",
        pattern=r"^\d{4}-\d{2}-\d{2}$"  # Validates format
    )
    activity_codes: dict[str, str] | None = Field(
        default=None,
        description="Optional dict mapping code type to value for grouping"
    )

# backend/tools/workspace/mutations.py - Tool function
@logfire.instrument("add_activity_ws")
async def add_activity_ws(
    ctx: RunContext[AgentDeps], 
    req: AddActivityWsRequest
) -> str:
    """Add a new activity to the schedule workspace..."""
    # Implementation uses req.task_code, req.task_name, etc.
```

### Request Models to Create

> [!IMPORTANT]
> Request models already exist in `io.py` for workspace tools but are **not used**. These should be refactored to match the naming convention and then applied:

| Tool | New Request Model | Notes |
|------|-------------------|-------|
| `load_schedule_ws` | `LoadScheduleWsRequest` | Currently uses `proj_id: int` only |
| `calculate_gantt_ws` | `CalculateGanttWsRequest` | Rename from `CalculateAndDisplayGanttRequest` |
| `modify_activity_ws` | `ModifyActivityWsRequest` | Rename from `ModifyActivityInWorkspaceRequest` |
| `add_activity_ws` | `AddActivityWsRequest` | Rename from `AddActivityToWorkspaceRequest` |
| `add_relationship_ws` | `AddRelationshipWsRequest` | Rename from `AddRelationshipToWorkspaceRequest` |
| `modify_relationship_ws` | `ModifyRelationshipWsRequest` | **NEW** - create |
| `create_schedule_ws` | `CreateScheduleWsRequest` | **NEW** - create |
| `delete_activity_ws` | `DeleteActivityWsRequest` | **NEW** - create with new tool |
| `delete_relationship_ws` | `DeleteRelationshipWsRequest` | **NEW** - create with new tool |
| `assign_activity_codes_ws` | `AssignActivityCodesWsRequest` | **NEW** - create |
| `remove_activity_codes_ws` | `RemoveActivityCodesWsRequest` | **NEW** - create |

---

## 2. Missing Workspace Tools

### Required for Parity

| Tool | Purpose | Priority |
|------|---------|----------|
| `delete_relationship_ws` | Remove a relationship from workspace | **HIGH** |
| `delete_activity_ws` | Remove an activity from workspace | **HIGH** |
| `commit_workspace_to_p6` | Save workspace changes to P6 (Phase 3) | Medium |

### Implementation Template

```python
@logfire.instrument("delete_relationship_ws")
async def delete_relationship_ws(
    ctx: RunContext[AgentDeps],
    req: DeleteRelationshipWsRequest
) -> str:
    """Delete a relationship from the workspace.
    
    Use this tool to remove a dependency between activities in the workspace.
    This is a temporary change - it does not affect the P6 database.
    """
    workspace = schedule_state_manager.get(ctx.deps.conversation_id)
    if not workspace:
        return "No schedule workspace active. Use load_schedule_ws first."
    
    # Find and remove the relationship
    mask = (
        (workspace.relationships_df['pred_task_id'] == req.predecessor_task_id) &
        (workspace.relationships_df['task_id'] == req.successor_task_id)
    )
    
    if not mask.any():
        return f"No relationship found from {req.predecessor_task_id} to {req.successor_task_id}."
    
    workspace.relationships_df = workspace.relationships_df[~mask]
    workspace.is_modified = True
    
    return f"Deleted relationship: {req.predecessor_task_id} -> {req.successor_task_id}"
```

---

## 3. Idempotency Guards

### Problem

Create operations can duplicate data if called twice with the same parameters.

### Solution Pattern

```python
@logfire.instrument("create_activity_p6")
async def create_activity_p6(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """Create a new activity in the P6 database (permanent)."""
    try:
        # Idempotency check: does activity already exist?
        existing = ctx.deps.service.get_activity_by_code(
            req.task_code, 
            req.proj_id, 
            conn=ctx.deps.conn
        )
        if existing:
            return f"Activity '{req.task_code}' already exists (task_id={existing['task_id']}). No action taken."
        
        task_id = ctx.deps.service.create_activity(req, conn=ctx.deps.conn)
        ctx.deps.mark_modified()
        return f"Created activity '{req.task_code}' with ID {task_id}."
    except Exception as e:
        logfire.error("Error in create_activity_p6", error=str(e))
        return f"Error creating activity: {str(e)}"
```

### Tools Requiring Idempotency

| Tool | Check Method |
|------|--------------|
| `create_activity_p6` | Check if `task_code` exists in project |
| `create_relationship_p6` | Check if link between pred/succ exists |
| `create_project_p6` | Check if `project_short_name` exists |
| `add_activity_ws` | Already implemented ✓ |
| `add_relationship_ws` | Already implemented ✓ |

---

## 4. Legacy File Deprecation

### Current State

- `backend/tools/p6_tools.py` (1453 lines) contains all original tools
- New modular structure in `p6/`, `workspace/`, `indexing/` directories
- Some tools are duplicated or have inconsistent implementations

### Migration Steps

1. **Audit**: Compare each function in `p6_tools.py` with modular equivalents
2. **Mark deprecated**: Add deprecation warnings to legacy functions
3. **Update imports**: Ensure all agents import from new locations
4. **Remove**: Delete `p6_tools.py` after validation period

### Files to Update

```python
# backend/agents/scheduling_agent.py - BEFORE
from backend.tools.p6_tools import (
    create_activity_tool,
    update_relationship_tool,
    # ...
)

# backend/agents/scheduling_agent.py - AFTER
from backend.tools import (
    create_activity_p6,
    update_relationship_p6,
    # Or use category lists:
)
from backend.tools.p6 import P6_MUTATION_TOOLS, P6_QUERY_TOOLS
from backend.tools.workspace import WS_MUTATION_TOOLS, WS_QUERY_TOOLS
```

---

## 5. Production Readiness Enhancements

### 5.1 Structured Error Responses

Instead of returning error strings, use structured error models:

```python
class ToolErrorResponse(BaseModel):
    """Standardized error response for tool failures."""
    success: Literal[False] = False
    error_code: str  # e.g., "NOT_FOUND", "VALIDATION_ERROR", "DUPLICATE"
    message: str
    suggestion: str | None = None
    retry_hint: str | None = None  # For ModelRetry scenarios
```

### 5.2 Rate Limiting Metadata

Add execution timing for monitoring:

```python
@logfire.instrument("create_activity_p6", extract_args=True)
async def create_activity_p6(...):
    start = time.perf_counter()
    # ... implementation
    elapsed = time.perf_counter() - start
    logfire.info("Tool completed", elapsed_ms=elapsed*1000)
```

### 5.3 Transaction Boundaries

Ensure atomic operations for multi-step tools:

```python
# For tools that modify multiple tables
async def bulk_assign_activity_codes_p6(...):
    with ctx.deps.conn.transaction():  # Rollback on any failure
        for task_code in req.task_codes:
            ctx.deps.service.assign_code(...)
```

### 5.4 Health Check Tool

Add a diagnostic tool for debugging:

```python
@logfire.instrument("health_check")
async def health_check(ctx: RunContext[AgentDeps]) -> dict:
    """Check system health - database connection, vector service, workspace."""
    return {
        "database": "connected" if ctx.deps.conn else "disconnected",
        "vector_service": "available" if ctx.deps.vector_service else "unavailable",
        "workspace": schedule_state_manager.get(ctx.deps.conversation_id) is not None,
        "tools_version": TOOLS_VERSION,
    }
```

### 5.5 Version Tracking

```python
# backend/tools/__init__.py
TOOLS_VERSION = "2.1.0"  # Semantic versioning

# Include in agent registration for debugging
scheduling_agent = Agent(
    ...,
    metadata={"tools_version": TOOLS_VERSION}
)
```

---

## 6. Agent Tool Creation Guide

This section provides step-by-step guidance for creating new tools that conform to the architecture standards.

### Step 1: Determine Tool Target

| Question | If YES → | If NO → |
|----------|----------|---------|
| Does this persist data to P6 database? | `_p6` suffix, put in `backend/tools/p6/` | Continue |
| Does this modify in-memory workspace? | `_ws` suffix, put in `backend/tools/workspace/` | Continue |
| Is this for vector/search indexing? | No suffix, put in `backend/tools/indexing/` | Evaluate if new category needed |

### Step 2: Define Request Model

Create a Pydantic model in `backend/models/io.py`:

```python
class MyNewToolRequest(BaseModel):
    """Request for my_new_tool operation."""
    model_config = ConfigDict(strict=True)
    
    # Required fields: use ... (Ellipsis) as default
    required_field: StrictStr = Field(
        ...,
        description="Clear description for LLM. Include examples if helpful."
    )
    
    # Optional fields: provide explicit default
    optional_field: int | None = Field(
        default=None,
        ge=0,  # Add constraints where applicable
        description="Optional field with validation"
    )
```

**Checklist for Request Models:**
- [ ] `model_config = ConfigDict(strict=True)` for type safety
- [ ] Every field has a `description` (this appears in LLM tool schema)
- [ ] Use `StrictStr` for string fields that should not accept numbers
- [ ] Add validators (`ge`, `le`, `pattern`) where applicable
- [ ] Use `field_validator` for complex date parsing

### Step 3: Implement Tool Function

```python
# backend/tools/{category}/{module}.py

from pydantic_ai import RunContext, ModelRetry
import logfire
from backend.tools._base import AgentDeps
from backend.models.io import MyNewToolRequest


@logfire.instrument("my_new_tool_p6")  # Match function name
async def my_new_tool_p6(
    ctx: RunContext[AgentDeps], 
    req: MyNewToolRequest
) -> str:
    """[One-line summary of what this tool does].
    
    [When to use this tool - help LLM understand context]
    
    Note: This updates the P6 database permanently.  # Or "temporary workspace"
    
    Args:
        ctx: Runtime context with dependencies.
        req: Request containing [describe key fields].
    
    Returns:
        [What the success message contains]
    
    Raises:
        ModelRetry: If [condition that LLM can recover from].
    """
    try:
        # 1. Validate preconditions
        if not some_condition:
            return "Error: [actionable message with suggestion]"
        
        # 2. Idempotency check (for create operations)
        existing = check_if_exists(req.some_id)
        if existing:
            return f"Already exists: {existing}. No action taken."
        
        # 3. Perform operation via service layer
        result = ctx.deps.service.do_operation(req, conn=ctx.deps.conn)
        
        # 4. Mark transaction modified (P6 tools only)
        ctx.deps.mark_modified()
        
        # 5. Return minimal, informative response
        return f"Success: {result}. Next step: [suggest follow-up]"
        
    except ValueError as e:
        # Recoverable - suggest how LLM can fix
        raise ModelRetry(f"Failed: {e}. Try [specific action].")
        
    except Exception as e:
        logfire.error(f"Error in my_new_tool_p6", error=str(e))
        return f"Error: {str(e)}"
```

### Step 4: Register Tool

```python
# backend/tools/{category}/__init__.py

from .mymodule import my_new_tool_p6

# Add to appropriate list
P6_MUTATION_TOOLS = [
    ...,
    my_new_tool_p6,  # Add here
]

# Export in __all__
__all__ = [
    ...,
    "my_new_tool_p6",
]
```

```python
# backend/tools/__init__.py

from backend.tools.{category} import my_new_tool_p6

__all__ = [
    ...,
    "my_new_tool_p6",
]
```

### Step 5: Update System Prompt

Add to the appropriate category in `scheduler_system.xml.j2`:

```xml
<category name="P6_MUTATION_TOOLS">
    ...
    - my_new_tool_p6: [One-line description matching docstring]
</category>
```

### Step 6: Write Tests

```python
# tests/tools/test_my_new_tool.py

import pytest
from backend.models.io import MyNewToolRequest
from backend.tools.p6 import my_new_tool_p6


class TestMyNewTool:
    @pytest.fixture
    def valid_request(self):
        return MyNewToolRequest(
            required_field="test_value",
            optional_field=42
        )
    
    async def test_success_case(self, mock_ctx, valid_request):
        result = await my_new_tool_p6(mock_ctx, valid_request)
        assert "Success" in result
    
    async def test_idempotency(self, mock_ctx, valid_request):
        # First call creates
        await my_new_tool_p6(mock_ctx, valid_request)
        # Second call should detect duplicate
        result = await my_new_tool_p6(mock_ctx, valid_request)
        assert "Already exists" in result
    
    def test_request_validation(self):
        with pytest.raises(ValidationError):
            MyNewToolRequest(required_field=123)  # Wrong type
```

### Checklist Summary

**Before creating a new tool:**
- [ ] Tool name follows `{action}_{entity}_{target}` pattern
- [ ] Request model created with proper validation and descriptions
- [ ] Docstring explains when/why LLM should use this tool
- [ ] Idempotency check for create operations
- [ ] `ctx.deps.mark_modified()` called for P6 mutations
- [ ] Minimal, actionable return messages
- [ ] `ModelRetry` for recoverable errors with suggestions
- [ ] Tool registered in category `__init__.py` and main `__init__.py`
- [ ] System prompt updated with tool description
- [ ] Unit tests written

---

## 7. Implementation Phases

### Phase 1: Parameter Standardization (Low Risk)
1. Rename existing request models in `io.py` to new convention
2. Create missing request models
3. Update workspace tools to use request models
4. Test all tools still function

### Phase 2: Missing Tools & Idempotency (Medium Risk)
1. Implement `delete_relationship_ws`
2. Implement `delete_activity_ws`
3. Add idempotency checks to P6 create tools
4. Add unit tests for new tools

### Phase 3: Legacy Removal & Production Hardening (Medium Risk)
1. Audit and remove `p6_tools.py`
2. Add structured error responses
3. Add health check tool
4. Add version tracking
5. Update all import statements

---

## 8. Verification Plan

### Automated Tests

```bash
# Run all tool tests
pytest tests/tools/ -v

# Run with coverage
pytest tests/tools/ --cov=backend/tools --cov-report=html
```

### Manual Verification

1. **Load schedule test**: Load a project and verify Gantt displays
2. **Create in workspace test**: Add activity + relationship, verify CPM runs
3. **P6 mutation test**: Create activity in P6, verify database updated
4. **Idempotency test**: Call create twice, verify no duplicate

---

## Decision Points

- [ ] Confirm Pydantic model naming convention (`*WsRequest` vs `*WorkspaceRequest`)
- [ ] Confirm structured error response adoption scope
- [ ] Determine `commit_workspace_to_p6` implementation timeline (Phase 3)
- [ ] Identify additional production-readiness requirements

---

## Next Steps

1. [ ] Review and approve this proposal
2. [ ] Create/rename request models in `io.py`
3. [ ] Refactor workspace tools to use request models
4. [ ] Implement missing `delete_*_ws` tools
5. [ ] Add idempotency to P6 create tools
6. [ ] Deprecate and remove `p6_tools.py`
7. [ ] Update system prompt
8. [ ] Write tests
