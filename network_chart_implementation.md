# Network Builder and Gantt Chart Implementation Plan

## 1. Executive Summary

This document outlines the implementation plan for adapting the copied `GanttChart` component to visualize P6 schedule activities and implementing a network builder using NetworkX for CPM (Critical Path Method) calculations.

**Key Deliverables:**
1. NetworkX-based schedule calculator (backend)
2. Adapted GanttChart component (frontend)
3. Agent tool integration for schedule visualization
4. Real-time Gantt updates via AG-UI streaming

**Primary Use Cases:**
- **(a)** Visualize existing schedules loaded from P6 database
- **(b)** Visualize preliminary modifications to schedules (agent working on in-memory DataFrame)
- **(c)** Visualize newly created schedules before saving to P6

**Core Concept:** The DataFrame serves as the **working state** for schedule manipulation. It can be loaded from P6, modified by the agent, or created from scratch - with the Gantt chart updating in real-time as changes occur.

---

## 2. Current State Analysis

### 2.1 GanttChart Component (`frontend/components/GanttChart.tsx`)

The original app uses the following data structure:

```typescript
export interface ScheduleItem {
  id: number;
  s_item_id: string;
  s_item: string;
  total_duration: number;
  start: string;
  finish: string;
  created_at: string;
  updated_at: string;
}
```

**Current Issues:**
- `ScheduleItem` type is NOT defined in this codebase (copied from another app)
- Component expects pre-calculated dates
- No integration with P6 database schema yet

### 2.2 P6 Database Schema (Relevant Tables)

#### TASK Table (Activities)
| Field | Description |
|-------|-------------|
| `TASK_ID` | Primary key |
| `TASK_CODE` | User-visible identifier |
| `TASK_NAME` | Activity description |
| `TARGET_DRTN_HR_CNT` | Planned duration (hours) |
| `REMAIN_DRTN_HR_CNT` | Remaining duration (hours) |
| `TARGET_START_DATE` | Planned start |
| `TARGET_END_DATE` | Planned finish |
| `EARLY_START_DATE` | Calculated early start |
| `EARLY_END_DATE` | Calculated early finish |
| `LATE_START_DATE` | Calculated late start |
| `LATE_END_DATE` | Calculated late finish |
| `TOTAL_FLOAT_HR_CNT` | Total float (hours) |
| `FREE_FLOAT_HR_CNT` | Free float (hours) |
| `STATUS_CODE` | TK_NotStart, TK_Active, TK_Complete |
| `CSTR_TYPE` / `CSTR_DATE` | Primary constraint |
| `CSTR_TYPE2` / `CSTR_DATE2` | Secondary constraint |

#### TASKPRED Table (Relationships/Dependencies)
| Field | Description |
|-------|-------------|
| `TASK_ID` | Successor activity |
| `PRED_TASK_ID` | Predecessor activity |
| `PRED_TYPE` | PR_FS, PR_SS, PR_FF, PR_SF |
| `LAG_HR_CNT` | Lag in hours (negative = lead) |

#### CALENDAR Table
| Field | Description |
|-------|-------------|
| `CLNDR_ID` | Calendar identifier |
| `CLNDR_DATA` | BLOB with work patterns |
| `DAY_HR_CNT` | Hours per day |
| `WEEK_HR_CNT` | Hours per week |

### 2.3 Existing Architecture

```
Repository Layer (p6_repository.py)
       ↓
Service Layer (scheduling_service.py)
       ↓
Agent Tools (p6_tools.py)
       ↓
Agent (scheduling_agent.py)
       ↓
AG-UI Stream → Frontend (GanttChart)
```

**Key Insight:** The agent is the primary consumer of the network calculator - no REST API endpoint is needed. Data flows through AG-UI streaming directly to the frontend.

---

## 3. Proposed Solution: NetworkX-based Schedule Calculator

### 3.1 Why NetworkX?

**Evaluation of NetworkX:**

| Criteria | Assessment |
|----------|------------|
| Graph representation | Excellent - native DiGraph for dependency networks |
| Algorithm support | Built-in topological sort, path algorithms |
| Performance | Good for schedules up to 50K activities |
| Python integration | Native, async-friendly with proper wrapping |
| Maintainability | Well-documented, widely used |

**Alternatives Considered:**

1. **Pure Python implementation**: More control but reinventing the wheel
2. **Microsoft Project Engine**: Proprietary, not embeddable
3. **Open-source PM libraries**: Limited Python options, most are unmaintained

**Recommendation**: Use NetworkX - it's the most practical choice for graph-based scheduling.

### 3.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Layer                              │
│  scheduling_agent.py + p6_tools.py                             │
│  (Tools: load_schedule, modify_activity, calculate_gantt)      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                              │
│  scheduling_service.py                                          │
│  + NEW: network_calculator.py                                   │
│  + NEW: schedule_state.py (in-memory DataFrame manager)         │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
┌───────────────────┐                    ┌─────────────────────┐
│    DataFrame      │                    │   NetworkX DiGraph  │
│  (Working State)  │ ───────────────▶   │   (Dependency Net)  │
│                   │                    │                     │
│ - task_id         │                    │ Nodes: activities   │
│ - duration_hours  │                    │ Edges: relationships│
│ - constraints     │                    │ + lag values        │
│ - calendar_id     │                    │                     │
└───────────────────┘                    └─────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │   CPM Calculation   │
                    │                     │
                    │ Forward Pass:       │
                    │   ES, EF dates      │
                    │                     │
                    │ Backward Pass:      │
                    │   LS, LF dates      │
                    │                     │
                    │ Float Calculation:  │
                    │   TF, FF            │
                    │                     │
                    │ Critical Path       │
                    └─────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │    AG-UI Stream     │
                    │                     │
                    │ ScheduleItem[] →    │
                    │ GanttChart Component│
                    │ (real-time updates) │
                    └─────────────────────┘
```

### 3.3 Working State Pattern (DataFrame as Session State)

The agent maintains an **in-memory DataFrame** per conversation that represents the current schedule state:

```
Use Case (a): Load from P6
─────────────────────────
P6 Database → Repository → DataFrame (working state) → NetworkX → Gantt

Use Case (b): Modify Existing
─────────────────────────────
User: "Move activity X to start after Y"
Agent → Modify DataFrame → Recalculate NetworkX → Stream updated Gantt

Use Case (c): Create New
────────────────────────
User: "Create a 3-month construction schedule"
Agent → Build DataFrame from scratch → Calculate NetworkX → Stream Gantt
User: "Looks good, save it"
Agent → Save DataFrame to P6 Database (using existing tools)
```

### 3.4 Data Flow with Real-Time Updates

```
1. LOAD/CREATE: Initialize DataFrame (working state)
   ├── From P6: Repository queries → DataFrame
   └── From scratch: Agent builds DataFrame based on user request

2. MODIFY (iterative, agent responds to user requests):
   ├── Agent updates DataFrame (add/remove/modify activities)
   ├── Recalculate via NetworkX
   └── Stream updated ScheduleItem[] to frontend

3. BUILD NETWORK: DataFrame → NetworkX DiGraph
   ├── Add activity nodes with attributes
   ├── Add relationship edges with lag
   └── Validate graph (no cycles)

4. CALCULATE: CPM Algorithm
   ├── Topological sort
   ├── Forward pass (ES, EF)
   ├── Apply constraints (Start On or After)
   ├── Backward pass (LS, LF)
   ├── Float calculation
   └── Critical path identification

5. STREAM: Calculated results → AG-UI → GanttChart
   └── Frontend receives ScheduleItem[] and re-renders

6. PERSIST (on user approval):
   └── Save DataFrame to P6 Database using existing tools
```

---

## 4. Detailed Component Specifications

### 4.1 New Backend Module: `network_calculator.py`

**Location:** `backend/services/network_calculator.py`

```python
# Proposed class structure (implementation pending approval)

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
import pandas as pd
import networkx as nx
from pydantic import BaseModel, ConfigDict

class RelationshipType(str, Enum):
    FS = "PR_FS"  # Finish-to-Start
    SS = "PR_SS"  # Start-to-Start
    FF = "PR_FF"  # Finish-to-Finish
    SF = "PR_SF"  # Start-to-Finish

class ConstraintType(str, Enum):
    """MVP: Focus on MSOA/SNET (Start On or After)"""
    ASAP = "CS_ASAP"      # As Soon As Possible (default)
    MSOA = "CS_MSOA"      # Must Start On or After (PRIMARY - MVP)
    SNET = "CS_SNET"      # Start No Earlier Than (same as MSOA)
    # Future: MEOB, MSO, MEO, SNLT, FNET, FNLT

@dataclass
class CalculatedActivity:
    """Result of CPM calculation for a single activity"""
    task_id: str
    task_code: str
    task_name: str
    duration_days: float
    early_start: date
    early_finish: date
    late_start: date
    late_finish: date
    total_float_days: float
    free_float_days: float
    is_critical: bool

class NetworkCalculator:
    """
    NetworkX-based CPM calculator for P6 schedules.
    
    Responsibilities:
    - Build dependency graph from activities and relationships
    - Perform forward and backward pass
    - Calculate float and identify critical path
    - Support calendars and constraints
    """
    
    def __init__(
        self,
        activities_df: pd.DataFrame,
        relationships_df: pd.DataFrame,
        calendar_hours_per_day: float = 8.0,
        project_start_date: date = None
    ):
        self.activities_df = activities_df
        self.relationships_df = relationships_df
        self.hours_per_day = calendar_hours_per_day
        self.project_start = project_start_date or date.today()
        self.graph: nx.DiGraph = None
        
    def build_network(self) -> nx.DiGraph:
        """Build NetworkX DiGraph from activities and relationships"""
        ...
        
    def validate_network(self) -> list[str]:
        """Check for cycles, disconnected nodes, missing predecessors"""
        ...
        
    def forward_pass(self) -> None:
        """Calculate Early Start (ES) and Early Finish (EF) dates"""
        ...
        
    def backward_pass(self) -> None:
        """Calculate Late Start (LS) and Late Finish (LF) dates"""
        ...
        
    def calculate_float(self) -> None:
        """Calculate Total Float (TF) and Free Float (FF)"""
        ...
        
    def identify_critical_path(self) -> list[str]:
        """Return list of critical activity IDs (TF = 0)"""
        ...
        
    def apply_constraints(self) -> None:
        """Apply activity constraints (MSO, MEO, SNET, etc.)"""
        ...
        
    def calculate(self) -> list[CalculatedActivity]:
        """Run full CPM calculation and return results"""
        self.build_network()
        errors = self.validate_network()
        if errors:
            raise ScheduleValidationError(errors)
        self.forward_pass()
        self.apply_constraints()
        self.backward_pass()
        self.calculate_float()
        return self._to_calculated_activities()
```

### 4.2 Calendar Support

**Option A: Simplified (Recommended for MVP)**
- Use default 8 hours/day, 5 days/week
- Convert all durations from hours to work days
- Skip complex exception handling

**Option B: Full Calendar Parsing**
- Parse `CLNDR_DATA` BLOB (XML format)
- Handle work exceptions, holidays
- Per-activity calendar assignment

**Recommendation:** Start with Option A, iterate to Option B based on user needs.

### 4.3 Constraint Handling (MVP: Start On or After)

| P6 Constraint | CPM Impact | MVP Status |
|---------------|------------|------------|
| CS_ASAP | Default behavior (earliest dates) | Supported |
| CS_MSOA / CS_SNET | ES >= constraint date | **Primary - Supported** |
| CS_MEOB / CS_FNLT | LF <= constraint date | Future |
| CS_MSO | ES = LS = constraint date | Future |
| CS_MEO | EF = LF = constraint date | Future |

### 4.4 Frontend Type Definition

**New file:** `frontend/types/schedule.ts`

```typescript
/**
 * Matches original app's ScheduleItem interface
 */
export interface ScheduleItem {
  id: number;              // Sequence number for display
  s_item_id: string;       // TASK_ID or TASK_CODE
  s_item: string;          // TASK_NAME
  total_duration: number;  // Duration in days
  start: string;           // ISO date string (early_start)
  finish: string;          // ISO date string (early_finish)
  created_at: string;      // Timestamp
  updated_at: string;      // Timestamp
}

/**
 * Extended schedule item with CPM data (for internal use)
 */
export interface ScheduleItemExtended extends ScheduleItem {
  is_critical?: boolean;    // On critical path
  total_float?: number;     // Float in days
  status?: 'not_started' | 'active' | 'complete';
  wbs_path?: string;        // WBS hierarchy for grouping
}

export interface GanttChartData {
  items: ScheduleItem[];
  project_start: string;
  project_finish: string;
  critical_path_length?: number;
  data_date?: string;
}
```

### 4.5 Agent Tools (No REST API Needed)

The agent directly calls the network calculator and streams results. **No separate REST endpoint is required** because:
1. The agent is the sole consumer of this functionality
2. Data flows through AG-UI streaming to the frontend
3. The chat interface is the user's interaction point

**New/Enhanced tools in:** `backend/tools/p6_tools.py`

```python
@agent.tool
async def load_schedule_to_workspace(
    ctx: RunContext[AgentDependencies],
    project_id: str
) -> WorkspaceLoadResult:
    """
    Load a P6 schedule into the working DataFrame.
    
    Use Case (a): Visualize existing schedules from P6.
    
    Returns: Summary of loaded activities and triggers Gantt display.
    """
    ...

@agent.tool
async def modify_activity_in_workspace(
    ctx: RunContext[AgentDependencies],
    task_id: str,
    duration_days: float | None = None,
    start_constraint: str | None = None,
    predecessor_id: str | None = None
) -> ModifyResult:
    """
    Modify an activity in the working DataFrame.
    
    Use Case (b): Preview modifications before saving to P6.
    
    Automatically recalculates network and streams updated Gantt.
    """
    ...

@agent.tool
async def add_activity_to_workspace(
    ctx: RunContext[AgentDependencies],
    task_code: str,
    task_name: str,
    duration_days: float,
    predecessor_id: str | None = None,
    start_constraint: str | None = None
) -> AddActivityResult:
    """
    Add a new activity to the working DataFrame.
    
    Use Case (c): Create new schedules incrementally.
    
    Automatically recalculates network and streams updated Gantt.
    """
    ...

@agent.tool
async def calculate_and_display_gantt(
    ctx: RunContext[AgentDependencies]
) -> GanttDisplayResult:
    """
    Recalculate CPM and stream Gantt chart to frontend.
    
    Called automatically after modifications, or manually
    when user wants to see current state.
    """
    ...

@agent.tool
async def save_workspace_to_p6(
    ctx: RunContext[AgentDependencies],
    project_id: str
) -> SaveResult:
    """
    Persist the working DataFrame to P6 database.
    
    Called when user approves the schedule after preview.
    Uses existing P6 write tools internally.
    """
    ...
```

### 4.6 Schedule State Manager

**New file:** `backend/services/schedule_state.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd

@dataclass
class ScheduleWorkspace:
    """
    In-memory working state for a schedule being edited.
    
    Maintains DataFrame + metadata per conversation session.
    """
    conversation_id: str
    project_id: str | None = None  # None if creating new schedule
    activities_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    relationships_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    is_modified: bool = False
    source: str = "new"  # "new" | "p6_loaded"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def mark_modified(self) -> None:
        self.is_modified = True
        self.updated_at = datetime.now()


class ScheduleStateManager:
    """
    Manages schedule workspaces per conversation.
    
    In production, could be backed by Redis for persistence
    across server restarts. For MVP, in-memory dict is sufficient.
    """
    
    def __init__(self):
        self._workspaces: dict[str, ScheduleWorkspace] = {}
    
    def get_or_create(self, conversation_id: str) -> ScheduleWorkspace:
        if conversation_id not in self._workspaces:
            self._workspaces[conversation_id] = ScheduleWorkspace(
                conversation_id=conversation_id
            )
        return self._workspaces[conversation_id]
    
    def load_from_p6(
        self, 
        conversation_id: str,
        project_id: str,
        activities_df: pd.DataFrame,
        relationships_df: pd.DataFrame
    ) -> ScheduleWorkspace:
        workspace = ScheduleWorkspace(
            conversation_id=conversation_id,
            project_id=project_id,
            activities_df=activities_df,
            relationships_df=relationships_df,
            source="p6_loaded"
        )
        self._workspaces[conversation_id] = workspace
        return workspace
    
    def clear(self, conversation_id: str) -> None:
        self._workspaces.pop(conversation_id, None)
```

---

## 5. Implementation Phases

### Phase 1: Core NetworkX Calculator (Backend)
- [ ] Create `network_calculator.py` with basic CPM
- [ ] Support FS relationships only (simplest case)
- [ ] Use default calendar (8h x 5d)
- [ ] Implement "Start On or After" constraint (MSOA/SNET)
- [ ] Unit tests with sample data (~100 activities)

### Phase 2: Schedule State Management
- [ ] Create `schedule_state.py` with ScheduleWorkspace
- [ ] Implement ScheduleStateManager for conversation-scoped state
- [ ] Load from P6 functionality
- [ ] Modify/add activity functionality

### Phase 3: Agent Tools & AG-UI Integration
- [ ] Implement `load_schedule_to_workspace` tool
- [ ] Implement `modify_activity_in_workspace` tool
- [ ] Implement `add_activity_to_workspace` tool
- [ ] Implement `calculate_and_display_gantt` tool
- [ ] Implement `save_workspace_to_p6` tool
- [ ] AG-UI streaming for Gantt data (artifact type)

### Phase 4: Frontend Integration
- [ ] Create `ScheduleItem` type definition
- [ ] Adapt `GanttChart.tsx` for P6 data structure
- [ ] Handle AG-UI stream updates for real-time rendering
- [ ] Add critical path highlighting (optional)

### Phase 5: Enhanced Relationships (Post-MVP)
- [ ] Add SS, FF, SF relationship support
- [ ] Implement lag/lead handling
- [ ] Add additional constraint types

---

## 6. Gantt Interactivity (Future Phase - NOT in MVP)

For reference, enabling direct Gantt manipulation would require:

| Feature | Complexity | Effort |
|---------|------------|--------|
| Drag to reschedule | Medium | 2-3 days |
| Edit duration in-place | Medium | 1-2 days |
| Add/remove relationships visually | High | 3-4 days |
| Undo/redo | High | 2-3 days |
| Visual dependency lines | Medium | 2 days |

**Total for interactivity: ~10-14 additional days**

For MVP, the Gantt is **read-only** - users interact via chat, agent updates the workspace, and Gantt re-renders automatically.

---

## 7. Testing Strategy

### Unit Tests
- NetworkX graph building
- CPM forward/backward pass
- Float calculation
- "Start On or After" constraint application

### Integration Tests
- End-to-end with P6 database (~100 activities)
- Agent tool execution
- AG-UI stream data format

### Sample Test Cases
1. Simple linear schedule (A → B → C)
2. Parallel paths with merge
3. Activity with "Start On or After" constraint
4. Incomplete network (missing predecessors - should warn)

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Circular dependencies | Calculation failure | Validate graph before CPM, clear error message |
| State loss on server restart | Lost work | Warn user to save; future: Redis persistence |
| AG-UI stream timing | Stale Gantt display | Debounce updates, ensure sequential delivery |

---

## 9. Open Questions - RESOLVED

| Question | Resolution |
|----------|------------|
| Calendar complexity | Simplified 8h/5d for MVP |
| Constraint priority | "Start On or After" (MSOA/SNET) |
| Gantt interactivity | Read-only for MVP; ~10-14 days for full interactivity |
| Data volume | ~100 activities (trivial for NetworkX) |
| Real-time updates | Key feature - AG-UI streaming after each modification |
| API endpoint needed? | No - agent is the consumer, data flows via AG-UI |

---

## 10. Dependencies

### Python Packages (to add to requirements.txt)
```
networkx>=3.0
pandas>=2.0
```

### No New Frontend Dependencies Required
- GanttChart already uses existing date-fns, etc.

---

## 11. Estimated Effort (Revised)

| Phase | Estimated Days |
|-------|----------------|
| Phase 1: Core Calculator | 2-3 days |
| Phase 2: State Management | 1-2 days |
| Phase 3: Agent Tools & AG-UI | 2-3 days |
| Phase 4: Frontend | 1-2 days |

**Total MVP (Phases 1-4):** 6-10 days

---

## 12. Approval Checklist

Before implementation, please confirm:

- [x] NetworkX is acceptable as the graph library
- [x] Simplified calendar approach is OK for MVP
- [x] "Start On or After" constraint is the priority
- [x] ~100 activities is sufficient scale for MVP
- [x] Read-only Gantt (no direct manipulation) is acceptable
- [x] Real-time updates via AG-UI streaming is the approach
- [x] No separate REST API endpoint needed
- [ ] Phase breakdown aligns with priorities
- [ ] Type definitions match expectations

---

*Document created: December 3, 2025*
*Author: GitHub Copilot*
*Status: REVISED - AWAITING FINAL APPROVAL*
