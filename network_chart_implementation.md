# Network Builder and Gantt Chart Implementation Plan

## 1. Executive Summary

This document outlines the implementation plan for adapting the copied `GanttChart` component to visualize P6 schedule activities and implementing a network builder using NetworkX for CPM (Critical Path Method) calculations.

**Key Deliverables:**
1. NetworkX-based schedule calculator (backend)
2. Adapted GanttChart component (frontend) with floating panel UI
3. Agent tool integration for schedule visualization
4. Real-time Gantt updates via AG-UI streaming
5. Filtering capabilities for partial schedule views

**Primary Use Cases:**
- **(a)** Visualize existing schedules loaded from P6 database
- **(b)** Visualize preliminary modifications to schedules (agent working on in-memory DataFrame)
- **(c)** Visualize newly created schedules before saving to P6

**Core Concept:** The DataFrame serves as the **working state** for schedule manipulation. It can be loaded from P6, modified by the agent, or created from scratch - with the Gantt chart updating in real-time as changes occur.

---

## 2. Current State Analysis

### 2.1 GanttChart Component (`frontend/components/GanttChart.tsx`)

**UI Requirement:** The GanttChart should appear as a **floating panel on the right side** of the chat interface, triggered only when schedule visualization is needed. The chat area should resize/shift left to accommodate the Gantt panel.

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

#### Activity Codes System (PRIMARY Filter Mechanism)

Activity Codes are the **primary mechanism** for filtering schedule views. Each activity can have multiple codes assigned (one per code type).

**P6 Tables:**

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `ACTVTYPE` | Code type definitions | `ACTV_CODE_TYPE_ID`, `ACTV_CODE_TYPE` (name), `ACTV_CODE_TYPE_SCOPE` |
| `ACTVCODE` | Code values (hierarchical) | `ACTV_CODE_ID`, `ACTV_CODE_TYPE_ID`, `PARENT_ACTV_CODE_ID`, `ACTV_CODE_NAME` |
| `TASKACTV` | Task-to-code assignments | `TASK_ID`, `ACTV_CODE_TYPE_ID`, `ACTV_CODE_ID` |

**Example Structure:**
```
Code Type: "Phase"
├── Design
├── Construction
│   ├── Civil (child)
│   ├── Mechanical (child)
│   └── Electrical (child)
└── Commissioning

Code Type: "Area"
├── Building A
├── Building B
└── Site Work
```

**Assignment Rule:** Each activity can have **ONE code value per code type**. An activity might have:
- Phase = "Construction" (specifically "Civil")
- Area = "Building A"
- Responsibility = "Contractor ABC"

**SQL to Load Activity Codes for a Project:**
```sql
SELECT 
    ta.TASK_ID,
    ct.ACTV_CODE_TYPE as code_type_name,
    cv.ACTV_CODE_NAME as code_value_name
FROM TASKACTV ta
JOIN ACTVTYPE ct ON ta.ACTV_CODE_TYPE_ID = ct.ACTV_CODE_TYPE_ID
JOIN ACTVCODE cv ON ta.ACTV_CODE_ID = cv.ACTV_CODE_ID
JOIN TASK t ON ta.TASK_ID = t.TASK_ID
WHERE t.PROJ_ID = :project_id
```

**SQL to Get Available Code Types and Values:**
```sql
-- Get all code types (project-level + global)
SELECT 
    ct.ACTV_CODE_TYPE_ID,
    ct.ACTV_CODE_TYPE as code_type_name,
    cv.ACTV_CODE_NAME as code_value_name
FROM ACTVTYPE ct
JOIN ACTVCODE cv ON ct.ACTV_CODE_TYPE_ID = cv.ACTV_CODE_TYPE_ID
WHERE ct.PROJ_ID = :project_id OR ct.PROJ_ID IS NULL
ORDER BY ct.SEQ_NUM, cv.SEQ_NUM
```

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
AG-UI Stream → Frontend (GanttChart floating panel)
```

**Key Insights:**
1. The agent is the primary consumer of the network calculator - no REST API endpoint is needed
2. Data flows through AG-UI streaming directly to the frontend
3. The agent controls when the Gantt panel is shown/hidden via stream events
4. The agent can filter data before streaming (partial views)

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
                              │
                              ▼
                    ┌─────────────────────┐
                    │   Frontend Layout   │
                    │                     │
                    │ ┌───────┬─────────┐ │
                    │ │ Chat  │ Gantt   │ │
                    │ │ (left)│ (right) │ │
                    │ │       │ floating│ │
                    │ └───────┴─────────┘ │
                    │                     │
                    │ Panel visibility    │
                    │ controlled by agent │
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

5. FILTER (optional): Apply view filters
   ├── By Activity Codes (PRIMARY - Phase, Area, Responsibility, etc.)
   ├── By WBS path (show specific branch)
   ├── By date range (activities in window)
   ├── By critical path only
   ├── By activity status
   └── By search term (name/code match)

6. STREAM: Filtered results → AG-UI → GanttChart
   ├── Include panel visibility command (show/hide)
   └── Frontend receives ScheduleItem[] and re-renders

7. PERSIST (on user approval):
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
  filter_applied?: GanttFilter;  // Indicates what filter is active
  total_activities?: number;     // Total before filtering
  
  // Available Activity Code types and values for filter UI
  // Populated on initial load from P6 ACTVTYPE/ACTVCODE tables
  available_activity_codes?: Record<string, string[]>;
}

/**
 * Filter options for partial schedule views
 * 
 * Activity Codes are the PRIMARY filter mechanism.
 * Each activity can have multiple codes (one per code type).
 * P6 Structure: ACTVTYPE (types) → ACTVCODE (values) → TASKACTV (assignments)
 */
export interface GanttFilter {
  wbs_path?: string;           // Show activities under this WBS
  date_start?: string;         // Activities starting on or after
  date_end?: string;           // Activities finishing on or before
  critical_only?: boolean;     // Only critical path activities
  status?: ('not_started' | 'active' | 'complete')[];
  search_term?: string;        // Match in task_code or task_name
  
  // Activity Code filters (PRIMARY filtering mechanism)
  // Key = Code Type name (e.g., "Phase", "Area", "Responsibility")
  // Value = Array of Code Values to include (e.g., ["Construction", "Commissioning"])
  // Activities must match ALL specified code types (AND logic between types)
  // Within a code type, activities matching ANY value are included (OR logic within type)
  activity_codes?: Record<string, string[]>;
}

/**
 * AG-UI event to control Gantt panel visibility
 */
export interface GanttPanelEvent {
  type: 'gantt_panel';
  action: 'show' | 'hide' | 'update';
  data?: GanttChartData;
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
    ctx: RunContext[AgentDependencies],
    filter_wbs: str | None = None,
    filter_date_start: str | None = None,
    filter_date_end: str | None = None,
    filter_critical_only: bool = False,
    filter_status: list[str] | None = None,
    filter_search: str | None = None,
    filter_activity_codes: dict[str, list[str]] | None = None
) -> GanttDisplayResult:
    """
    Recalculate CPM and stream Gantt chart to frontend.
    
    Called automatically after modifications, or manually
    when user wants to see current state.
    
    Filtering options allow partial views:
    - filter_wbs: Show only activities under this WBS path
    - filter_date_start/end: Show activities in date range
    - filter_critical_only: Show only critical path
    - filter_status: Filter by status (not_started, active, complete)
    - filter_search: Match task code or name
    - filter_activity_codes: PRIMARY filter - dict of code_type → code_values
      Example: {"Phase": ["Construction"], "Area": ["Building A", "Building B"]}
      Logic: AND between types, OR within a type
    
    Sends 'gantt_panel' event with action='show' to display panel.
    """
    ...

@agent.tool
async def hide_gantt_panel(
    ctx: RunContext[AgentDependencies]
) -> None:
    """
    Hide the Gantt panel from the UI.
    
    Called when user is done reviewing the schedule or
    switches to a different topic.
    
    Sends 'gantt_panel' event with action='hide'.
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
    
    Activity Codes are loaded from P6 tables:
    - ACTVTYPE: Code type definitions (Phase, Area, Responsibility, etc.)
    - ACTVCODE: Code values (hierarchical, e.g., Construction → Civil)
    - TASKACTV: Code assignments to tasks (one value per code type per task)
    """
    conversation_id: str
    project_id: str | None = None  # None if creating new schedule
    activities_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    relationships_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    
    # Activity Code data (loaded from P6)
    # activity_codes_df: task_id → code_type_name → code_value_name
    # Flattened view of TASKACTV joined with ACTVTYPE and ACTVCODE
    activity_codes_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Available code types and their values for UI filter options
    code_types_with_values: dict[str, list[str]] = field(default_factory=dict)
    
    is_modified: bool = False
    source: str = "new"  # "new" | "p6_loaded"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def mark_modified(self) -> None:
        self.is_modified = True
        self.updated_at = datetime.now()
    
    def filter_activities(
        self,
        wbs_path: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        critical_only: bool = False,
        status: list[str] | None = None,
        search_term: str | None = None,
        activity_codes: dict[str, list[str]] | None = None
    ) -> pd.DataFrame:
        """
        Return filtered view of activities DataFrame.
        
        Does not modify the underlying data - returns a filtered copy.
        
        Activity Code filtering (PRIMARY mechanism):
        - activity_codes is a dict: code_type_name → list of code_value_names
        - Example: {"Phase": ["Construction"], "Area": ["Building A", "Building B"]}
        - Logic: AND between code types, OR within a code type
        - Above example: Phase=Construction AND (Area=Building A OR Area=Building B)
        """
        df = self.activities_df.copy()
        
        # Activity Code filter (PRIMARY - filter first for efficiency)
        if activity_codes and not self.activity_codes_df.empty:
            # Build set of task_ids that match the Activity Code criteria
            matching_task_ids = None
            
            for code_type, code_values in activity_codes.items():
                # Find tasks that have any of the specified values for this code type
                type_matches = self.activity_codes_df[
                    (self.activity_codes_df['code_type_name'] == code_type) &
                    (self.activity_codes_df['code_value_name'].isin(code_values))
                ]['task_id'].unique()
                
                if matching_task_ids is None:
                    matching_task_ids = set(type_matches)
                else:
                    # AND logic: intersect with previous code type matches
                    matching_task_ids = matching_task_ids & set(type_matches)
            
            if matching_task_ids is not None:
                df = df[df['task_id'].isin(matching_task_ids)]
        
        if wbs_path:
            df = df[df['wbs_path'].str.startswith(wbs_path)]
        
        if date_start:
            df = df[df['early_start'] >= date_start]
        
        if date_end:
            df = df[df['early_finish'] <= date_end]
        
        if critical_only:
            df = df[df['is_critical'] == True]
        
        if status:
            df = df[df['status'].isin(status)]
        
        if search_term:
            mask = (
                df['task_code'].str.contains(search_term, case=False, na=False) |
                df['task_name'].str.contains(search_term, case=False, na=False)
            )
            df = df[mask]
        
        return df


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
        relationships_df: pd.DataFrame,
        activity_codes_df: pd.DataFrame | None = None,
        code_types_with_values: dict[str, list[str]] | None = None
    ) -> ScheduleWorkspace:
        """
        Load schedule data from P6 including Activity Codes.
        
        activity_codes_df expected columns:
        - task_id: int
        - code_type_name: str (e.g., "Phase", "Area")
        - code_value_name: str (e.g., "Construction", "Building A")
        
        code_types_with_values: dict of available code types and their values
        - Used by frontend to populate filter dropdowns
        - Example: {"Phase": ["Design", "Construction", "Closeout"],
                   "Area": ["Building A", "Building B"]}
        """
        workspace = ScheduleWorkspace(
            conversation_id=conversation_id,
            project_id=project_id,
            activities_df=activities_df,
            relationships_df=relationships_df,
            activity_codes_df=activity_codes_df if activity_codes_df is not None else pd.DataFrame(),
            code_types_with_values=code_types_with_values or {},
            source="p6_loaded"
        )
        self._workspaces[conversation_id] = workspace
        return workspace
    
    def clear(self, conversation_id: str) -> None:
        self._workspaces.pop(conversation_id, None)
```

---

## 5. UI Layout: Floating Gantt Panel

### 5.1 Layout Behavior

```
┌──────────────────────────────────────────────────────────────────────┐
│                           Header                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  DEFAULT STATE (no Gantt):                                           │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                                                                │  │
│  │                        Chat Area                               │  │
│  │                      (full width)                              │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  WITH GANTT PANEL (triggered by agent):                              │
│  ┌─────────────────────────┬──────────────────────────────────────┐  │
│  │                         │                                      │  │
│  │      Chat Area          │         Gantt Panel                  │  │
│  │    (resized left)       │     (floating right)                 │  │
│  │                         │                                      │  │
│  │                         │  ┌──────────────────────────────┐   │  │
│  │                         │  │ [x] Close  Filter: WBS/A     │   │  │
│  │                         │  ├──────────────────────────────┤   │  │
│  │                         │  │                              │   │  │
│  │                         │  │      Gantt Chart             │   │  │
│  │                         │  │                              │   │  │
│  │                         │  │  ████████░░░░ Activity A     │   │  │
│  │                         │  │       ████████ Activity B    │   │  │
│  │                         │  │            ██████ Activity C │   │  │
│  │                         │  │                              │   │  │
│  │                         │  └──────────────────────────────┘   │  │
│  │                         │                                      │  │
│  └─────────────────────────┴──────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 Panel Visibility States

| State | Trigger | Chat Width | Gantt Width |
|-------|---------|------------|-------------|
| Hidden | Default / `hide_gantt_panel` | 100% | 0 |
| Visible | `calculate_and_display_gantt` | ~50-60% | ~40-50% |

### 5.3 AG-UI Events for Panel Control

```typescript
// Event types streamed from agent to frontend

// Show panel with data
{
  type: 'gantt_panel',
  action: 'show',
  data: {
    items: ScheduleItem[],
    project_start: '2025-01-01',
    project_finish: '2025-06-30',
    filter_applied: { wbs_path: 'WBS/A' },
    total_activities: 100  // 100 total, showing filtered subset
  }
}

// Update panel data (panel already visible)
{
  type: 'gantt_panel',
  action: 'update',
  data: { ... }
}

// Hide panel
{
  type: 'gantt_panel',
  action: 'hide'
}
```

### 5.4 Frontend Component Structure

```
ChatLayout.tsx (modified)
├── ChatArea (resizable based on ganttVisible state)
│   └── MessageList, InputArea, etc.
│
└── GanttPanel (conditional render)
    ├── PanelHeader
    │   ├── Close button (triggers hide)
    │   └── Filter indicator (shows active filter)
    │
    └── GanttChart (existing component, adapted)
        └── Receives ScheduleItem[] from AG-UI stream
```

### 5.5 State Management (Frontend)

```typescript
// In ChatLayout or context provider

interface GanttPanelState {
  visible: boolean;
  data: GanttChartData | null;
  filterApplied: GanttFilter | null;
}

// AG-UI stream handler
const handleGanttEvent = (event: GanttPanelEvent) => {
  switch (event.action) {
    case 'show':
      setGanttState({
        visible: true,
        data: event.data,
        filterApplied: event.data?.filter_applied || null
      });
      break;
    case 'update':
      setGanttState(prev => ({
        ...prev,
        data: event.data,
        filterApplied: event.data?.filter_applied || null
      }));
      break;
    case 'hide':
      setGanttState({ visible: false, data: null, filterApplied: null });
      break;
  }
};
```

---

## 6. Implementation Phases

### Phase 1: Core NetworkX Calculator (Backend)
- [ ] Create `network_calculator.py` with basic CPM
- [ ] Support FS relationships only (simplest case)
- [ ] Use default calendar (8h x 5d)
- [ ] Implement "Start On or After" constraint (MSOA/SNET)
- [ ] Unit tests with sample data (~100 activities)

### Phase 2: Schedule State Management
- [ ] Create `schedule_state.py` with ScheduleWorkspace
- [ ] Implement ScheduleStateManager for conversation-scoped state
- [ ] Implement `filter_activities()` method for partial views
- [ ] Load from P6 functionality
- [ ] Modify/add activity functionality

### Phase 3: Agent Tools & AG-UI Integration
- [ ] Implement `load_schedule_to_workspace` tool
- [ ] Implement `modify_activity_in_workspace` tool
- [ ] Implement `add_activity_to_workspace` tool
- [ ] Implement `calculate_and_display_gantt` tool with filtering params
- [ ] Implement `hide_gantt_panel` tool
- [ ] Implement `save_workspace_to_p6` tool
- [ ] AG-UI streaming for Gantt data (`gantt_panel` event type)

### Phase 4: Frontend Integration
- [ ] Create `ScheduleItem` type definition
- [ ] Adapt `GanttChart.tsx` for P6 data structure
- [ ] Create floating panel layout (chat left, Gantt right)
- [ ] Handle `gantt_panel` events (show/hide/update)
- [ ] Implement responsive layout transition (chat resize)
- [ ] Handle AG-UI stream updates for real-time rendering
- [ ] Display filter indicator when partial view is active
- [ ] Add critical path highlighting (optional)

### Phase 5: Enhanced Relationships (Post-MVP)
- [ ] Add SS, FF, SF relationship support
- [ ] Implement lag/lead handling
- [ ] Add additional constraint types

---

## 7. Gantt Interactivity (Future Phase - NOT in MVP)

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

## 8. Testing Strategy

### Unit Tests
- NetworkX graph building
- CPM forward/backward pass
- Float calculation
- "Start On or After" constraint application
- DataFrame filtering methods

### Integration Tests
- End-to-end with P6 database (~100 activities)
- Agent tool execution
- AG-UI stream data format
- Panel show/hide events

### Sample Test Cases
1. Simple linear schedule (A → B → C)
2. Parallel paths with merge
3. Activity with "Start On or After" constraint
4. Incomplete network (missing predecessors - should warn)
5. Filter by WBS path (show subset)
6. Filter by critical path only
7. Filter by search term
8. Panel visibility toggle
9. Filter by single Activity Code type (Phase = Construction)
10. Filter by multiple Activity Code types (Phase = Construction AND Area = Building A)
11. Filter by Activity Code with multiple values (Area = Building A OR Building B)
12. Load Activity Codes from P6 (TASKACTV join)

### Example User Interactions
```
User: "Show me the schedule for Project X"
Agent: [loads from P6] → [calculates] → [streams gantt_panel show]
       Panel appears on right, chat resizes
       (includes available_activity_codes for filter dropdowns)

User: "Just show me the foundation work"
Agent: [filters by WBS 'Foundation'] → [streams gantt_panel update]
       Panel updates with filtered view, shows "Filter: WBS/Foundation"

User: "Show me all Construction phase activities in Building A"
Agent: [filters by activity_codes: {Phase: ["Construction"], Area: ["Building A"]}]
       → [streams gantt_panel update]
       Panel shows filtered view: "Filter: Phase=Construction, Area=Building A"

User: "Include Building B as well"
Agent: [filters by activity_codes: {Phase: ["Construction"], Area: ["Building A", "Building B"]}]
       → [streams gantt_panel update]
       Panel shows expanded view: "Filter: Phase=Construction, Area=Building A or Building B"

User: "What's on the critical path?"
Agent: [filters critical_only=true] → [streams gantt_panel update]
       Panel shows only critical activities

User: "Add a new activity after A1020"
Agent: [modifies DataFrame] → [recalculates] → [streams gantt_panel update]
       Panel updates with new activity shown

User: "Thanks, I'm done reviewing"
Agent: [streams gantt_panel hide]
       Panel closes, chat expands to full width
```

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Circular dependencies | Calculation failure | Validate graph before CPM, clear error message |
| State loss on server restart | Lost work | Warn user to save; future: Redis persistence |
| AG-UI stream timing | Stale Gantt display | Debounce updates, ensure sequential delivery |

---

## 10. Open Questions - RESOLVED

| Question | Resolution |
|----------|------------|
| Calendar complexity | Simplified 8h/5d for MVP |
| Constraint priority | "Start On or After" (MSOA/SNET) |
| Gantt interactivity | Read-only for MVP; ~10-14 days for full interactivity |
| Data volume | ~100 activities (trivial for NetworkX) |
| Real-time updates | Key feature - AG-UI streaming after each modification |
| API endpoint needed? | No - agent is the consumer, data flows via AG-UI |
| UI layout | Floating panel on right, chat resizes left |
| Partial views | Filtering by WBS, date, critical path, status, search |

---

## 11. Dependencies

### Python Packages (to add to requirements.txt)
```
networkx>=3.0
pandas>=2.0
```

### No New Frontend Dependencies Required
- GanttChart already uses existing date-fns, etc.

---

## 12. Estimated Effort (Revised)

| Phase | Estimated Days |
|-------|----------------|
| Phase 1: Core Calculator | 2-3 days |
| Phase 2: State Management + Filtering | 1-2 days |
| Phase 3: Agent Tools & AG-UI | 2-3 days |
| Phase 4: Frontend (incl. panel layout) | 2-3 days |

**Total MVP (Phases 1-4):** 7-11 days

---

## 13. Approval Checklist

Before implementation, please confirm:

- [x] NetworkX is acceptable as the graph library
- [x] Simplified calendar approach is OK for MVP
- [x] "Start On or After" constraint is the priority
- [x] ~100 activities is sufficient scale for MVP
- [x] Read-only Gantt (no direct manipulation) is acceptable
- [x] Real-time updates via AG-UI streaming is the approach
- [x] No separate REST API endpoint needed
- [x] Floating panel UI (right side, chat resizes)
- [x] Filtering/partial view capability included
- [x] Activity Codes as PRIMARY filter mechanism
- [ ] Phase breakdown aligns with priorities
- [ ] Type definitions match expectations

---

*Document created: December 3, 2025*
*Author: GitHub Copilot*
*Status: REVISED (v3) - Activity Code filtering added - AWAITING FINAL APPROVAL*
