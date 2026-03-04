# What-If Analysis - Assessment & Implementation Proposal

## Date: 2026-03-04

---

## 1. Problem Statement

The user asked the agent to:
1. **Show the critical path** in the Gantt chart with its own data as baseline
2. **Run a what-if analysis** (e.g., delay an activity 3 weeks) and show the impact compared to the previous state as baseline

The agent partially succeeded: it calculated the critical path and displayed the Gantt chart, but **failed to set baseline data correctly** for comparison. On the second request ("use the critical path you are showing as its own baseline") the agent encountered a "technical issue" and fell back to manual text analysis instead of rendering the visual comparison.

---

## 2. Trace Analysis

### Trace 1: `019cb824f88afe9987ede11d311537fc` (First request)

**User message**: "I need you to run an exercise for me. Calculate the critical path and show it in the gantt chart. Include the same as baseline."

**Agent tool sequence**:
1. `list_schedule_versions_ms` - Found version v260129 (ID 21)
2. `load_schedule_ms` - Loaded schedule into workspace (13s, 50+ activities)
3. `calculate_gantt_ws` - Ran CPM and built Gantt payload

**Critical finding**: The agent called `calculate_gantt_ws` with:
```json
{
  "critical_only": true,
  "render_options": {
    "baseline_mode": "database_baseline"
  },
  "data_envelope": {
    "include_baselines": ["database_baseline"]
  }
}
```

The agent interpreted "include the same as baseline" as requesting the **database baseline** (a different version marked `is_baseline=true` in Supabase). This is incorrect - the user wanted to use the **current calculation results as its own baseline** for later comparison.

**Result**: Gantt displayed but with `baseline_mode: "database_baseline"` which may or may not have found a matching baseline version. The screenshot shows the Gantt rendered correctly with critical path activities, but baseline bars appear missing for most rows.

### Trace 2: `019cb826c9eda029010ab61ee6051091` (Second request)

**User message**: "I want the critical path you are showing to be shown as its own baseline - we'll do a what-if analysis based on that"

**Agent tool sequence**:
1. `list_schedule_versions_ms` - Re-listed versions
2. `load_schedule_ms` - Re-loaded schedule (unnecessary, already in workspace)
3. `calculate_gantt_ws` with `critical_only: true, baseline_mode: "own"` - Attempted own baseline
4. `get_project_constraints_ms` - Fetched constraints (trying to understand baseline)
5. `list_activities_ms` (x2) - Manually fetched all activities
6. `calculate_gantt_ws` with `critical_only: false` - Attempted full schedule
7. `list_activities_ms` - More manual fetching

**Critical finding**: The agent struggled because:
- The `calculate_gantt_ws` tool with `baseline_mode: "own"` checked for `baseline_start`/`baseline_finish` columns in the workspace DataFrame - these columns **do not exist** for MS Project schedules loaded via `load_schedule_ms`
- The workspace `load_from_ms()` method does NOT populate baseline columns
- The `schedule_activities` DB table has `baseline_start`/`baseline_finish` columns but they are not loaded into the workspace
- `has_own_baseline` evaluates to `false`, the agent sees no baseline available
- The agent then looped trying alternative approaches (manual listing, full schedule) spending 54 seconds total before giving up on visual comparison

---

## 3. Root Cause Analysis

### 3.1 Missing "Snapshot as Baseline" Capability

The core issue: **there is no mechanism to snapshot the current workspace state as a baseline for comparison**. The existing baseline modes are:

| Mode | Source | Status |
|------|--------|--------|
| `own` | `baseline_start`/`baseline_finish` from DB import | Only works if source DB has baseline columns populated |
| `previous_version` | Cross-version comparison from Supabase | Works for schedule_view_service, NOT for workspace tools |
| `database_baseline` | Version flagged `is_baseline=true` in Supabase | Works for schedule_view_service, NOT for workspace tools |

**The gap**: When the user says "use this as baseline", they mean: "freeze the current calculated dates (early_start, early_finish) as the reference point, then let me modify activities and recalculate to see the delta." No tool or mechanism exists for this.

### 3.2 Workspace Baseline Columns Not Loaded

`load_from_ms()` in `schedule_state.py` maps many columns but does NOT map `baseline_start`/`baseline_finish`/`baseline_duration_d` from `schedule_activities` into the workspace DataFrame. So even if the DB has baseline data, it is invisible to workspace tools.

### 3.3 calculate_gantt_ws Cannot Resolve Cross-Version Baselines

The `calculate_gantt_ws` tool builds its payload purely from in-memory workspace DataFrames. It does NOT call `schedule_view_service.build_view_payload()` which has full cross-version baseline resolution. The workspace tool has:
- `baseline_mode` parameter in `GanttRenderOptions`
- Reads workspace `baseline_start`/`baseline_finish` columns
- Reports `has_own_baseline: false` when those columns are empty
- **No path to resolve `previous_version` or `database_baseline`** from Supabase

### 3.4 Agent Confusion

The agent has no system prompt guidance on what-if workflows. It does not know:
- How to snapshot current state as baseline
- The correct tool sequence for what-if analysis
- That `modify_activity_ws` + `calculate_gantt_ws` is the intended what-if workflow

---

## 4. Proposed Solution

### Phase 1: Workspace Baseline Snapshot (Critical - enables what-if)

#### 4.1 New Tool: `snapshot_baseline_ws`

A new workspace tool that copies the current calculated dates into baseline columns:

```python
@logfire.instrument("snapshot_baseline_ws")
async def snapshot_baseline_ws(
    ctx: RunContext[AgentDeps],
    req: SnapshotBaselineWsRequest,
) -> str:
    """Snapshot the current workspace schedule as the baseline for what-if comparison.
    
    Copies the current calculated dates (early_start, early_finish, total_float_days)
    into baseline columns. After this, any modifications + recalculation will show 
    the delta via baseline ghost bars in the Gantt chart.
    
    Call this BEFORE making what-if changes. The baseline persists until:
    - A new snapshot is taken (overwrite)
    - The workspace is cleared
    - A new schedule is loaded
    
    Args:
        ctx: Runtime context with conversation_id in deps
        req: Optional label for the baseline
    
    Returns:
        Confirmation with activity count and baseline label
    """
```

**Implementation**: Copy columns from workspace DataFrame:
- `early_start` -> `baseline_start`
- `early_finish` -> `baseline_finish`
- `target_drtn_hr_cnt / 8.0` -> `baseline_duration_d`
- `total_float_days` -> `baseline_total_float`
- `is_critical` -> `baseline_is_critical`

Store snapshot metadata on the workspace:
```python
@dataclass 
class BaselineSnapshot:
    label: str
    taken_at: datetime
    project_start: date
    project_finish: date
    critical_path_length: float
    activity_count: int
```

#### 4.2 Update ScheduleWorkspace Dataclass

Add baseline snapshot tracking:

```python
@dataclass
class ScheduleWorkspace:
    # ... existing fields ...
    
    # Baseline snapshot for what-if comparison
    baseline_snapshot: Optional[BaselineSnapshot] = None
    
    def snapshot_as_baseline(self, label: str = "Baseline") -> BaselineSnapshot:
        """Copy current calculated dates into baseline columns."""
        if 'early_start' not in self.activities_df.columns:
            raise ValueError("No calculation results. Run calculate_gantt_ws first.")
        
        self.activities_df['baseline_start'] = self.activities_df['early_start']
        self.activities_df['baseline_finish'] = self.activities_df['early_finish']
        dur_hours = self.activities_df.get('target_drtn_hr_cnt', pd.Series(dtype=float))
        self.activities_df['baseline_duration_d'] = dur_hours / 8.0
        self.activities_df['baseline_total_float'] = self.activities_df.get(
            'total_float_days', pd.Series(dtype=float)
        )
        self.activities_df['baseline_is_critical'] = self.activities_df.get(
            'is_critical', pd.Series(dtype=bool)
        )
        
        snapshot = BaselineSnapshot(
            label=label,
            taken_at=datetime.now(),
            project_start=self.project_start,
            project_finish=self.project_finish,
            critical_path_length=...,  # From last calculation
            activity_count=len(self.activities_df),
        )
        self.baseline_snapshot = snapshot
        return snapshot
```

#### 4.3 Fix load_from_ms to Import Baseline Columns

In `schedule_state.py` `load_from_ms()`, add column mapping:

```python
column_mapping = {
    # ... existing mappings ...
    'baseline_start': 'baseline_start',
    'baseline_finish': 'baseline_finish', 
    'baseline_duration_d': 'baseline_duration_d',
}
```

And parse the date columns:
```python
for date_col in ['baseline_start', 'baseline_finish', ...]:
    if date_col in activities_df.columns:
        activities_df[date_col] = activities_df[date_col].apply(parse_date)
```

This fixes the `own` baseline mode for imported MS Project schedules that already have baseline data in Supabase.

### Phase 2: What-If Scenario Support

#### 4.4 New Tool: `get_whatif_comparison_ws`

After modifying activities and recalculating, this tool generates a structured comparison:

```python
@logfire.instrument("get_whatif_comparison_ws")
async def get_whatif_comparison_ws(
    ctx: RunContext[AgentDeps],
    req: WhatIfComparisonWsRequest,
) -> str:
    """Compare current workspace state against the stored baseline snapshot.
    
    Returns a summary of schedule impact: date shifts, float changes,
    critical path changes, and new/removed critical activities.
    
    Call AFTER: snapshot_baseline_ws -> modify_activity_ws -> calculate_gantt_ws
    """
```

**Output structure**:
```python
@dataclass
class WhatIfImpact:
    project_finish_delta_days: int          # +5 means 5 days later
    critical_path_length_delta: float       # Change in CP length
    activities_became_critical: list[str]   # Newly critical activities
    activities_left_critical: list[str]     # No longer critical
    most_impacted_activities: list[dict]    # Top N by date shift
    baseline_label: str
    scenario_label: str
```

#### 4.5 Update calculate_gantt_ws Response

When a baseline snapshot exists, the Gantt payload should:
1. Set `has_baseline: true` (baseline columns are populated)
2. Set `baseline_mode: "own"` 
3. Set `baseline_label` to the snapshot label (e.g., "Before delay")
4. Include the delta summary in a new `what_if_summary` field

The frontend already renders baseline ghost bars when `baseline_start`/`baseline_finish` are present on each item. No frontend changes needed for Phase 1.

### Phase 3: Prompt & Agent Guidance

#### 4.6 Add What-If Workflow to System Prompt

Add to `scheduler_general.xml.j2`:

```xml
<what_if_analysis>
    When the user requests what-if or impact analysis:
    
    1) Load the schedule into workspace (load_schedule_ms / load_schedule_ws)
    2) Calculate the initial state (calculate_gantt_ws)
    3) Snapshot as baseline (snapshot_baseline_ws) - REQUIRED before modifications
    4) Apply modifications (modify_activity_ws, add_relationship_ws, etc.)
    5) Recalculate (calculate_gantt_ws) - shows delta vs baseline automatically  
    6) Optionally compare (get_whatif_comparison_ws) for structured impact summary
    
    When user says "use this as baseline" or "compare against this":
    - Call snapshot_baseline_ws to freeze current state
    - Confirm baseline was captured
    - Wait for user to specify what-if changes
    
    The Gantt chart will automatically show ghost bars for the baseline dates
    after snapshot + recalculation.
</what_if_analysis>
```

#### 4.7 Add What-If Workflow to MSP-Specific Prompt

Add to `scheduler_msp.xml.j2`:

```xml
<what_if_workflow>
    For what-if on MSP schedules:
    - snapshot_baseline_ws captures calculated dates, not original MS dates
    - modify_activity_ws changes durations in hours (8h = 1 working day)
    - After recalculation, baseline bars in Gantt show the pre-modification state
    - Use get_whatif_comparison_ws to generate structured impact summary
</what_if_workflow>
```

---

## 5. Implementation Plan

### Phase 1 (Enables core what-if) - Priority HIGH

| Task | File | Effort |
|------|------|--------|
| Add `BaselineSnapshot` dataclass | `schedule_state.py` | S |
| Add `snapshot_as_baseline()` to workspace | `schedule_state.py` | S |
| Fix `load_from_ms` baseline column mapping | `schedule_state.py` | S |
| Create `SnapshotBaselineWsRequest` IO model | `models/io.py` | S |
| Implement `snapshot_baseline_ws` tool | `tools/workspace/mutations.py` | M |
| Register tool in agent tool list | `agents/scheduling_agent.py` | S |
| Update system prompts with what-if guidance | `prompt/*.xml.j2` | S |
| Verify `calculate_gantt_ws` reads baseline columns | `tools/workspace/mutations.py` | S (already works) |

### Phase 2 (Structured comparison) - Priority MEDIUM

| Task | File | Effort |
|------|------|--------|
| Create `WhatIfComparisonWsRequest` IO model | `models/io.py` | S |
| Implement `get_whatif_comparison_ws` tool | `tools/workspace/mutations.py` | M |
| Register comparison tool in agent | `agents/scheduling_agent.py` | S |

### Phase 3 (Enhanced visualization) - Priority LOW

| Task | File | Effort |
|------|------|--------|
| Frontend: what-if scenario label in Gantt header | `frontend/components/gantt/GanttPanel.tsx` | S |
| Frontend: impact summary overlay/tooltip | `frontend/components/gantt/GanttPanel.tsx` | M |
| Frontend: highlight newly-critical activities | `frontend/components/gantt/GanttPanel.tsx` | M |

---

## 6. Why Existing Baseline Modes Are Insufficient

| Existing Mode | Why It Does Not Work for What-If |
|---|---|
| `own` (DB baseline columns) | Only populated if the original schedule file contained baseline data. Many imported schedules have empty baseline columns. Even when present, these are the **original plan** baseline, not the "before my what-if change" baseline. |
| `previous_version` | Compares against a different uploaded version in Supabase. Not applicable to in-memory workspace modifications - the workspace is never saved as a version during what-if. |
| `database_baseline` | Compares against the version flagged `is_baseline=true`. Same problem as above - workspace modifications are in-memory only. |
| `calculate_gantt_ws` with `baseline_mode` param | The tool only reads `baseline_start`/`baseline_finish` from workspace DataFrame. It has NO code path to populate those columns from current calculations. |

The **fundamental gap** is: no mechanism turns **calculated** dates into **baseline** dates in the workspace. The `snapshot_baseline_ws` tool fills this gap.

---

## 7. Example User Flow (After Implementation)

```
User: "Show me the critical path for this project"
Agent: 
  1. load_schedule_ms(version_id=21)
  2. calculate_gantt_ws(critical_only=true, title="Critical Path")
  -> Gantt displayed with 17 critical activities

User: "Use this as baseline, we'll do a what-if"
Agent:
  3. snapshot_baseline_ws(label="Current Critical Path")
  -> "Baseline captured: 50 activities, project finish May 7 2026"

User: "What happens if 'Montaje de instrumentos' takes 3 weeks instead of 1 day?"
Agent:
  4. modify_activity_ws(task_id=1504, original_duration=120)  # 15 days * 8h
  5. calculate_gantt_ws(critical_only=false, title="What-If: Instruments +2wk")
  -> Gantt displayed with baseline ghost bars showing original dates
  -> New critical path visible, shifted dates highlighted
  
  6. get_whatif_comparison_ws()
  -> "Project finish shifted +8 days (May 7 -> May 15). 
      3 activities became critical. 
      Destileria float reduced from 6d to 0d."
```

---

## 8. Data Flow Diagram

```
[load_schedule_ms]
       |
       v
  Workspace DataFrame
  (activities_df with calculated columns)
       |
  [calculate_gantt_ws]  -->  Gantt Panel (no baseline bars)
       |
  [snapshot_baseline_ws]
       |  copies early_start -> baseline_start
       |  copies early_finish -> baseline_finish
       v
  Workspace DataFrame 
  (now has baseline_start, baseline_finish columns)
       |
  [modify_activity_ws]  -->  change duration / dates
       |
  [calculate_gantt_ws]  -->  recalculates early_start/early_finish
       |                     baseline_start/baseline_finish preserved
       v
  Gantt Panel
  (current bars + baseline ghost bars = visual delta)
```

---

## 9. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Agent may not call `snapshot_baseline_ws` before modifications | System prompt explicitly instructs the workflow order. Agent temperature is 0.3 (deterministic). |
| Multiple what-if iterations overwrite baseline | Tool can accept `overwrite=false` to warn if baseline exists. User can explicitly re-snapshot. |
| Workspace memory grows with baseline columns | ~3 extra float columns per activity row. Negligible for schedule sizes <5000 activities. |
| Frontend may not render baseline bars consistently | Already tested and working for `own` baseline mode in `schedule_view_service` path. Same data format. |
| NetworkCalculator recalculation may shift ALL dates | Expected behavior - this IS the what-if delta the user wants to see. |

---

## 10. Acceptance Criteria

1. User can say "use this as baseline" and agent calls `snapshot_baseline_ws`
2. After modification + recalculation, Gantt shows baseline ghost bars for pre-modification dates
3. `has_baseline` is `true` in the Gantt payload when baseline snapshot exists
4. MS Project schedules with existing DB baseline columns render baseline bars on first `calculate_gantt_ws` call
5. System prompt guides agent through correct what-if tool sequence
6. No changes to frontend required for Phase 1 (existing baseline rendering suffices)
