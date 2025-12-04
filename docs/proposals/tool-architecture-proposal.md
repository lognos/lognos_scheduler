# Tool Architecture Proposal: Database vs Workspace Separation

## Executive Summary

The current tool architecture mixes P6 database operations with in-memory workspace operations, leading to confusion for the LLM agent and incorrect tool selection. This proposal establishes a clear separation between **persistent database tools** and **ephemeral workspace tools**, with consistent naming conventions and organized module structure.

---

## Current State Analysis

### Existing Tools (25 total)

| Tool Name | Target | Category |
|-----------|--------|----------|
| `create_activity_tool` | P6 Database | Activity CRUD |
| `create_relationship_tool` | P6 Database | Relationship CRUD |
| `delete_relationship_tool` | P6 Database | Relationship CRUD |
| `update_relationship_tool` | P6 Database | Relationship CRUD |
| `update_progress_tool` | P6 Database | Activity CRUD |
| `update_activity_status_tool` | P6 Database | Activity CRUD |
| `get_activity_details_tool` | P6 Database | Query |
| `search_activity_tool` | P6 Database + Vector | Query |
| `index_project_tool` | Vector DB | Indexing |
| `create_project_tool` | P6 Database | Project CRUD |
| `list_projects_tool` | P6 Database | Query |
| `list_activities_tool` | P6 Database | Query |
| `list_activity_codes_tool` | P6 Database | Query |
| `get_activity_current_codes_tool` | P6 Database | Query |
| `assign_activity_codes_tool` | P6 Database | Activity Codes |
| `remove_activity_codes_tool` | P6 Database | Activity Codes |
| `bulk_assign_activity_codes_tool` | P6 Database | Activity Codes |
| `load_schedule_to_workspace_tool` | Workspace | Workspace |
| `calculate_and_display_gantt_tool` | Workspace | Workspace |
| `hide_gantt_panel_tool` | Workspace | Workspace UI |
| `get_workspace_status_tool` | Workspace | Workspace |
| `modify_activity_in_workspace_tool` | Workspace | Workspace |
| `add_activity_to_workspace_tool` | Workspace | Workspace |
| `add_relationship_to_workspace_tool` | Workspace | Workspace |
| `modify_relationship_in_workspace_tool` | Workspace | Workspace |

### Problems Identified

1. **Naming Inconsistency**: Database tools don't indicate they affect persistent storage
2. **LLM Confusion**: Agent uses `update_relationship_tool` (database) when it should use `modify_relationship_in_workspace_tool` (workspace)
3. **No Clear Grouping**: Tools are declared in a single list without logical organization
4. **Missing Parallel Operations**: No workspace equivalents for some database operations (e.g., delete)

---

## Proposed Architecture

### 1. Naming Convention

#### Pattern: `{action}_{entity}_{target}_tool`

- **action**: `create`, `update`, `delete`, `get`, `list`, `search`, `load`, `calculate`
- **entity**: `activity`, `relationship`, `project`, `activity_codes`, `schedule`, `gantt`
- **target**: `p6` (database) or `ws` (workspace)

#### Renamed Tools

| Current Name | Proposed Name | Rationale |
|-------------|---------------|-----------|
| `create_activity_tool` | `create_activity_p6` | Explicit database target |
| `create_relationship_tool` | `create_relationship_p6` | Explicit database target |
| `update_relationship_tool` | `update_relationship_p6` | Explicit database target |
| `delete_relationship_tool` | `delete_relationship_p6` | Explicit database target |
| `update_progress_tool` | `update_progress_p6` | Explicit database target |
| `update_activity_status_tool` | `update_activity_status_p6` | Explicit database target |
| `add_activity_to_workspace_tool` | `create_activity_ws` | Consistent with P6 naming |
| `add_relationship_to_workspace_tool` | `create_relationship_ws` | Consistent with P6 naming |
| `modify_activity_in_workspace_tool` | `update_activity_ws` | Consistent with P6 naming |
| `modify_relationship_in_workspace_tool` | `update_relationship_ws` | Consistent with P6 naming |
| `load_schedule_to_workspace_tool` | `load_schedule_ws` | Shorter, clear target |
| `calculate_and_display_gantt_tool` | `calculate_gantt_ws` | Shorter, clear target |
| `get_workspace_status_tool` | `get_status_ws` | Shorter, clear target |
| `hide_gantt_panel_tool` | `hide_gantt_ws` | Shorter, clear target |

#### Query Tools (read-only, but target-specific)

| Current Name | Proposed Name | Rationale |
|-------------|---------------|-----------|
| `get_activity_details_tool` | `get_activity_p6` | Read from P6 database |
| `search_activity_tool` | `search_activities_p6` | Search P6 via vector |
| `list_projects_tool` | `list_projects_p6` | Read from P6 database |
| `list_activities_tool` | `list_activities_p6` | Read from P6 database |
| `list_activity_codes_tool` | `list_activity_codes_p6` | Read from P6 database |
| `get_activity_current_codes_tool` | `get_activity_codes_p6` | Read from P6 database |

**Future workspace query tools:**

| Future Tool | Purpose |
|-------------|---------|
| `get_activity_ws` | Get activity details from workspace DataFrame |
| `search_activities_ws` | Search workspace activities (in-memory filter) |
| `list_activities_ws` | List all activities in workspace |
| `list_relationships_ws` | List all relationships in workspace |
| `get_critical_path_ws` | Get critical path activities from workspace |
| `get_float_analysis_ws` | Get float/slack analysis from workspace |

**Rationale for explicit targets on queries:**

1. **Consistency**: All tools follow same `{action}_{entity}_{target}` pattern
2. **Future-proofing**: Easy to add `_ws` equivalents when needed
3. **Clear expectations**: LLM knows exactly where data comes from
4. **Different results**: P6 query returns persisted data; WS query returns in-memory state (may include unsaved changes)

---

### 2. Module Structure

```
backend/tools/
├── __init__.py              # Re-exports all tools + category lists
├── _base.py                 # AgentDeps, common utilities
├── p6/
│   ├── __init__.py          # Exports P6_TOOLS (queries + mutations)
│   ├── queries.py           # get_activity_p6, search_activities_p6, list_*_p6
│   ├── activities.py        # create_activity_p6, update_progress_p6, update_activity_status_p6
│   ├── relationships.py     # create_relationship_p6, update_relationship_p6, delete_relationship_p6
│   ├── projects.py          # create_project_p6
│   └── activity_codes.py    # assign_activity_codes_p6, remove_activity_codes_p6, bulk_assign_activity_codes_p6
├── workspace/
│   ├── __init__.py          # Exports WORKSPACE_TOOLS (queries + mutations)
│   ├── queries.py           # get_activity_ws, list_activities_ws, get_critical_path_ws, etc.
│   ├── schedule.py          # load_schedule_ws, get_status_ws
│   ├── activities.py        # create_activity_ws, update_activity_ws, delete_activity_ws
│   ├── relationships.py     # create_relationship_ws, update_relationship_ws, delete_relationship_ws
│   └── gantt.py             # calculate_gantt_ws, hide_gantt_ws
└── indexing/
    ├── __init__.py          # Exports INDEXING_TOOLS list
    └── vector.py            # index_project
```

---

### 3. Tool Registration with Categories

```python
# backend/agents/scheduling_agent.py

from backend.tools.p6 import P6_QUERY_TOOLS, P6_MUTATION_TOOLS
from backend.tools.workspace import WS_QUERY_TOOLS, WS_MUTATION_TOOLS
from backend.tools.indexing import INDEXING_TOOLS

scheduling_agent = Agent(
    settings.GOOGLE_DEFAULT_MODEL,
    deps_type=AgentDeps,
    output_type=AgentOutput,
    system_prompt=PromptLoader.get_prompt("scheduler_system.xml.j2"),
    tools=[
        *P6_QUERY_TOOLS,      # Read from P6 database
        *P6_MUTATION_TOOLS,   # Write to P6 database (permanent)
        *WS_QUERY_TOOLS,      # Read from workspace (in-memory)
        *WS_MUTATION_TOOLS,   # Write to workspace (temporary)
        *INDEXING_TOOLS,      # Vector indexing operations
    ],
)
```

Each module exports categorized lists:

```python
# backend/tools/p6/__init__.py

from .queries import (
    get_activity_p6,
    search_activities_p6,
    list_projects_p6,
    list_activities_p6,
    list_activity_codes_p6,
    get_activity_codes_p6,
)
from .activities import create_activity_p6, update_progress_p6, update_activity_status_p6
from .relationships import create_relationship_p6, update_relationship_p6, delete_relationship_p6
from .projects import create_project_p6
from .activity_codes import assign_activity_codes_p6, remove_activity_codes_p6, bulk_assign_activity_codes_p6

P6_QUERY_TOOLS = [
    get_activity_p6,
    search_activities_p6,
    list_projects_p6,
    list_activities_p6,
    list_activity_codes_p6,
    get_activity_codes_p6,
]

P6_MUTATION_TOOLS = [
    create_activity_p6,
    update_progress_p6,
    update_activity_status_p6,
    create_relationship_p6,
    update_relationship_p6,
    delete_relationship_p6,
    create_project_p6,
    assign_activity_codes_p6,
    remove_activity_codes_p6,
    bulk_assign_activity_codes_p6,
]
```

```python
# backend/tools/workspace/__init__.py

from .queries import (
    get_activity_ws,
    list_activities_ws,
    list_relationships_ws,
    get_critical_path_ws,
    get_float_analysis_ws,
)
from .schedule import load_schedule_ws, get_status_ws
from .activities import create_activity_ws, update_activity_ws, delete_activity_ws
from .relationships import create_relationship_ws, update_relationship_ws, delete_relationship_ws
from .gantt import calculate_gantt_ws, hide_gantt_ws

WS_QUERY_TOOLS = [
    get_status_ws,
    get_activity_ws,
    list_activities_ws,
    list_relationships_ws,
    get_critical_path_ws,
    get_float_analysis_ws,
]

WS_MUTATION_TOOLS = [
    load_schedule_ws,
    create_activity_ws,
    update_activity_ws,
    delete_activity_ws,
    create_relationship_ws,
    update_relationship_ws,
    delete_relationship_ws,
    calculate_gantt_ws,
    hide_gantt_ws,
]
```

---

### 4. System Prompt Organization

```xml
<system_instructions>
    <role>
        You are an expert Primavera P6 Scheduler Agent with two operating modes:
        - P6 Mode: Permanent changes to the P6 database
        - Workspace Mode: Temporary in-memory schedule manipulation for preview/analysis
    </role>

    <tool_categories>
        <category name="P6_QUERY_TOOLS" description="Read-only operations on P6 database">
            - get_activity_p6: Get details of a specific activity from P6
            - search_activities_p6: Search activities by natural language (vector search)
            - list_projects_p6: List all projects in P6
            - list_activities_p6: List activities in a project from P6
            - list_activity_codes_p6: List available activity code types from P6
            - get_activity_codes_p6: Get codes assigned to an activity from P6
        </category>
        
        <category name="WS_QUERY_TOOLS" description="Read-only operations on workspace (in-memory)">
            - get_activity_ws: Get activity details from workspace
            - list_activities_ws: List all activities in workspace
            - list_relationships_ws: List all relationships in workspace
            - get_critical_path_ws: Get critical path from last calculation
            - get_float_analysis_ws: Get float/slack analysis
            - get_status_ws: Check workspace status and summary
        </category>
        
        <category name="P6_DATABASE_TOOLS" description="Permanent changes to P6 database">
            - create_activity_p6: Create activity in P6 (permanent)
            - create_relationship_p6: Create relationship in P6 (permanent)
            - update_relationship_p6: Modify relationship in P6 (permanent)
            - delete_relationship_p6: Remove relationship from P6 (permanent)
            - update_progress_p6: Update activity progress in P6 (permanent)
            - update_activity_status_p6: Update activity status in P6 (permanent)
            - create_project_p6: Create new project in P6 (permanent)
            - assign_activity_codes_p6: Assign codes in P6 (permanent)
            - remove_activity_codes_p6: Remove codes in P6 (permanent)
            - bulk_assign_activity_codes_p6: Bulk assign codes in P6 (permanent)
        </category>
        
        <category name="WORKSPACE_TOOLS" description="Temporary in-memory operations for preview">
            - load_schedule_ws: Load P6 schedule into workspace memory
            - create_activity_ws: Create activity in workspace (temporary)
            - update_activity_ws: Modify activity in workspace (temporary)
            - delete_activity_ws: Remove activity from workspace (temporary)
            - create_relationship_ws: Create relationship in workspace (temporary)
            - update_relationship_ws: Modify relationship in workspace (temporary)
            - delete_relationship_ws: Remove relationship from workspace (temporary)
            - calculate_gantt_ws: Run CPM and display Gantt chart
            - hide_gantt_ws: Hide Gantt panel
        </category>
        
        <category name="INDEXING_TOOLS" description="Vector search indexing">
            - index_project: Index project activities for semantic search
        </category>
    </tool_categories>

    <tool_selection_rules>
        <rule priority="1">
            When user asks to PREVIEW, VISUALIZE, ANALYZE, or CREATE A DRAFT schedule:
            → Use WORKSPACE_TOOLS (create_activity_ws, create_relationship_ws, etc.)
            → Changes are temporary and won't affect P6
        </rule>
        
        <rule priority="2">
            When user asks to SAVE, COMMIT, UPDATE P6, or make PERMANENT changes:
            → Use P6_DATABASE_TOOLS (create_activity_p6, create_relationship_p6, etc.)
            → Changes are permanent in the P6 database
        </rule>
        
        <rule priority="3">
            When modifying entities that were created in workspace:
            → ALWAYS use workspace tools (update_activity_ws, update_relationship_ws)
            → P6 tools will fail because entities don't exist in database yet
        </rule>
        
        <rule priority="4">
            When displaying a Gantt chart or running CPM calculations:
            → First load schedule with load_schedule_ws
            → Make modifications with workspace tools
            → Display with calculate_gantt_ws
        </rule>
        
        <rule priority="5">
            For querying CURRENT WORKSPACE STATE (after modifications):
            → Use WS_QUERY_TOOLS (list_activities_ws, get_critical_path_ws)
            → These show in-memory state including unsaved changes
        </rule>
        
        <rule priority="6">
            For querying PERSISTED P6 DATA:
            → Use P6_QUERY_TOOLS (list_activities_p6, search_activities_p6)
            → These show only committed data in P6 database
        </rule>
    </tool_selection_rules>
    
    <workflow_examples>
        <example name="Preview new schedule">
            1. load_schedule_ws (load existing P6 data)
            2. create_activity_ws (add draft activities)
            3. create_relationship_ws (link activities)
            4. calculate_gantt_ws (visualize)
            5. [User reviews]
            6. If approved → commit_workspace_to_p6 (future tool)
        </example>
        
        <example name="Modify workspace activities">
            1. User: "change the relationships to SS"
            2. update_relationship_ws (NOT update_relationship_p6!)
            3. calculate_gantt_ws (re-visualize)
        </example>
        
        <example name="Permanent P6 change">
            1. User: "add this activity to P6 project 1011"
            2. create_activity_p6 (permanent)
            3. User: "link it to existing activity"
            4. create_relationship_p6 (permanent)
        </example>
    </workflow_examples>
</system_instructions>
```

---

### 5. Missing Tools to Add

For workspace parity with P6 database operations:

| P6 Tool | Workspace Equivalent | Status |
|---------|---------------------|--------|
| `create_activity_p6` | `create_activity_ws` | Exists |
| `create_relationship_p6` | `create_relationship_ws` | Exists |
| `update_relationship_p6` | `update_relationship_ws` | Exists |
| `delete_relationship_p6` | `delete_relationship_ws` | **MISSING** |
| `update_progress_p6` | N/A (use update_activity_ws) | N/A |
| `update_activity_status_p6` | `update_activity_ws` | Exists (partial) |

**New tools needed:**
1. `delete_relationship_ws` - Remove a relationship from workspace
2. `delete_activity_ws` - Remove an activity from workspace
3. `commit_workspace_to_p6` - Save workspace changes to P6 database (future)

---

### 6. Implementation Phases

#### Phase 1: Rename and Reorganize (Low Risk)
1. Create new module structure
2. Add alias imports for backward compatibility
3. Update system prompt with clear categories
4. Test with existing workflows

#### Phase 2: Add Missing Tools (Medium Risk)
1. Implement `delete_relationship_ws`
2. Implement `delete_activity_ws`
3. Update tests

#### Phase 3: Commit Workflow (Higher Risk)
1. Implement `commit_workspace_to_p6`
2. Add validation before commit
3. Add rollback capability

---

### 7. Backward Compatibility

During transition, maintain aliases:

```python
# backend/tools/__init__.py

# Legacy aliases (deprecated, will be removed in v2.0)
create_activity_tool = create_activity_p6
create_relationship_tool = create_relationship_p6
update_relationship_tool = update_relationship_p6
add_activity_to_workspace_tool = create_activity_ws
add_relationship_to_workspace_tool = create_relationship_ws
modify_relationship_in_workspace_tool = update_relationship_ws
# ... etc
```

---

## Benefits

1. **Clear Mental Model**: Developers and LLM understand which tools affect what
2. **Reduced Errors**: LLM less likely to use wrong tool for the context
3. **Better Organization**: Related tools grouped together
4. **Easier Testing**: Test database tools separately from workspace tools
5. **Future Extensibility**: Easy to add new tool categories (e.g., export tools)

---

## Decision Points

1. **Naming suffix**: `_p6` vs `_db` vs `_persist`?
   - Recommendation: `_p6` (specific to Primavera P6)

2. **Workspace suffix**: `_ws` vs `_workspace` vs `_mem`?
   - Recommendation: `_ws` (short, clear)

3. **Query tools suffix**: `_p6`/`_ws` vs none?
   - Recommendation: Include `_p6`/`_ws` suffix for consistency and future-proofing
   - Rationale: Workspace queries return in-memory state (may differ from P6)

4. **Tool suffix**: Keep `_tool` or drop it?
   - Recommendation: Drop `_tool` suffix (cleaner, Pydantic AI doesn't require it)

---

## Next Steps

1. [ ] Review and approve naming convention
2. [ ] Create module structure
3. [ ] Migrate tools with aliases
4. [ ] Update system prompt
5. [ ] Add missing workspace tools
6. [ ] Test with real workflows
7. [ ] Remove legacy aliases after deprecation period
