# MS Project CPM Calculation Fix - Implementation Instructions

> **Date**: 2026-02-27
> **Priority**: CRITICAL - Client delivery required
> **Repo**: `lognos/lognos_scheduler`, branch `master`
> **Workspace**: `/Users/facu/LOGNOS/01_APPS/ASSIST/P6_ASSIST`

---

## 0. How to Use This Document

**This is not a proposal or a plan. This is a set of implementation instructions you must execute.**

You are an implementing agent. Your task is to read this document top-to-bottom, understand the root causes, then implement the fixes described in each phase — in order, one phase at a time. Do not skip phases or reorder them.

**Rules:**
1. **Follow the phased implementation order** (Section 8). Each phase builds on the previous one.
2. **Before starting any phase**, read the relevant source files referenced in the root causes and the file map (Section 5) to confirm the current state matches what is described here.
3. **After completing each phase**, validate your changes against the stored MS Project dates using the validation protocol (Section 10).
4. **Maintain the change registry** (Section 9). Log every file you modify, what you changed, and the validation result. This is mandatory — not optional.
5. **Do not break P6 schedules.** The CPM engine serves both P6 and MS Project. Every change must be backward-compatible. Run P6 regression checks (Phoenix Tower, P6 ID: 1011) after each phase.
6. **Commit after each completed phase** with a clear commit message referencing the phase number and root cause IDs addressed.

---

## 1. Problem Statement

The MS Project Gantt display shows **completely wrong dates**. The NetworkX CPM engine produces different results than MS Project's calculations. You must fix the CPM engine so it produces dates matching MS Project, using the pre-calculated dates in the database as **ground truth** for validation.

We need CPM to work correctly because the agent modifies schedules (add/remove activities, change durations, modify relationships) and must recalculate after changes.

---

## 2. Root Causes (Verified by Code Audit)

These are the specific bugs causing date mismatches:

### RC-1: Project start defaults to `date.today()` instead of actual project start
- **Location**: `backend/services/schedule_state.py` → `load_from_ms()` (line 487)
- `ScheduleWorkspace` is created with `project_start = None`
- `NetworkCalculator.__init__` (line 131): `self.project_start = project_start_date or date.today()`
- The MS Project start date is available in Supabase (`project_constraints` table or `MIN(start)` from activities) but never passed to the workspace

### RC-2: Only FS relationships supported - SS/FF/SF treated as FS
- **Location**: `backend/services/network_calculator.py` → `build_network()` (line 196)
- Non-FS relationships logged as warning but **processed as FS**
- MS Project commonly uses all four relationship types

### RC-3: Calendar is hardcoded (8h/day, Mon-Fri, no holidays)
- **Location**: `backend/services/network_calculator.py` → `_days_to_work_date()` (line 143)
- MS Project calendar data is loaded by `load_schedule_ms` but **never passed** to `NetworkCalculator`
- Calendar exceptions (holidays) from `calendar_exceptions` table are ignored

### RC-4: MS constraint types not mapped
- **Location**: `backend/services/schedule_state.py` → `load_from_ms()` (line 430)
- `constraint_type` and `constraint_date` columns exist in `schedule_activities` but are **not in the `column_mapping`** dict
- `NetworkCalculator` expects P6-style constraint strings (`CS_MSOA`, `CS_SNET`) but MS uses different constraint type IDs (reference: `constraint_types` table in Supabase)

### RC-5: Activity status always defaults to `not_started`
- **Location**: `backend/services/network_calculator.py` → `build_network()` (line 203)
- Expects P6 `status_code` column (`TK_NotStart`/`TK_Active`/`TK_Complete`)
- MS schedules have no `status_code` - status should be derived from `percent_complete`

### RC-6: Backward pass lag handling is simplified
- **Location**: `backend/services/network_calculator.py` → `backward_pass()` (line 328)
- Comment says "Simplified for FS" - lag is not applied to LF calculation

---

## 3. Current Implementation Status

### What Works
- [x] 9 MS-specific tools registered with agent (`backend/agents/scheduling_agent.py` lines 65-79, 223-235)
- [x] MS data loads from Supabase into workspace format (`load_from_ms`)
- [x] Relationships loaded and mapped (pred_id/succ_id using Supabase PKs)
- [x] WBS hierarchy display (`_build_ms_project_hierarchy` in mutations.py lines 26-150)
- [x] `preserve_order: true` flag prevents frontend re-sorting (mutations.py line 547)
- [x] Relationship arrows rendered on Gantt (`RelationshipArrows.tsx`)
- [x] GanttPanel supports virtualization with `@tanstack/react-virtual` (500+ activities)
- [x] Version management (create subversion, promote with diff)
- [x] Frontend hierarchy rendering with indentation and summary styling (`GanttPanel.tsx` line 371)

### What Does NOT Work
- [ ] CPM produces wrong dates (all root causes above)
- [ ] MS Project stored dates discarded after CPM recalculation
- [ ] No validation comparing calculated vs stored dates
- [ ] Calendar exceptions not used in CPM
- [ ] SS/FF/SF relationship types not calculated correctly
- [ ] MS constraint types not applied
- [ ] `remain_drtn_hr_cnt` not adjusted for `percent_complete`

---

## 4. Database Access

**Supabase Project ID**: `kxwradnyjqobvdheklsn`

Use MCP tools:
```
mcp_supabase_execute_sql with project_id: kxwradnyjqobvdheklsn
```

### Key Queries

```sql
-- Get MS project and current version
SELECT sv.id as version_id, sv.version_number, mp.project_id, mp.name
FROM schedule_versions sv
JOIN ms_projects mp ON mp.id = sv.ms_project_id
WHERE mp.project_id = 'BIO4-01-0002' AND sv.is_current = true;

-- Schema of schedule_activities
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'schedule_activities'
ORDER BY ordinal_position;

-- Sample activities with MS Project dates (these are ground truth)
SELECT ms_uid, name, wbs, is_summary, start, finish, duration_d,
       constraint_type, constraint_date, percent_complete
FROM schedule_activities
WHERE version_id = <VERSION_ID> AND is_summary = false
ORDER BY wbs LIMIT 20;

-- Relationships - check all types present
SELECT rel_type, COUNT(*) FROM schedule_links
WHERE schedule_version_id = <VERSION_ID>
GROUP BY rel_type;

-- Sample relationships with names
SELECT sl.id, sl.pred_id, sl.succ_id, sl.rel_type, sl.lag_d,
       pred.ms_uid as pred_uid, pred.name as pred_name,
       succ.ms_uid as succ_uid, succ.name as succ_name
FROM schedule_links sl
JOIN schedule_activities pred ON pred.id = sl.pred_id
JOIN schedule_activities succ ON succ.id = sl.succ_id
WHERE sl.schedule_version_id = <VERSION_ID>
LIMIT 20;

-- Project constraints (contains project start date, scheduling direction)
SELECT * FROM project_constraints
WHERE schedule_version_id = <VERSION_ID>;

-- Calendar and exceptions (holidays, non-working days)
SELECT * FROM project_calendars
WHERE schedule_version_id = <VERSION_ID>;

SELECT ce.* FROM calendar_exceptions ce
JOIN project_calendars pc ON pc.id = ce.calendar_id
WHERE pc.schedule_version_id = <VERSION_ID>;

-- Constraint type reference data (maps integer IDs to meanings)
SELECT * FROM constraint_types;
```

---

## 5. File Map

### Backend - Core (must modify)

| File | Lines | Key Functions | Root Cause |
|------|-------|--------------|------------|
| `backend/services/network_calculator.py` | 561 | `__init__()`, `build_network()`, `forward_pass()`, `backward_pass()`, `_days_to_work_date()`, `_work_days_between()` | RC-2, RC-3, RC-5, RC-6 |
| `backend/services/schedule_state.py` | 516 | `load_from_ms()` (L394-512), `ScheduleWorkspace` dataclass (L33-65) | RC-1, RC-4 |
| `backend/tools/workspace/mutations.py` | 1558 | `calculate_gantt_ws()` (L226-588), `_build_ms_project_hierarchy()` (L26-150) | Needs validation step |

### Backend - MS Tools (read for context, likely minor changes)

| File | Lines | Content |
|------|-------|---------|
| `backend/tools/ms/queries.py` | 490 | 6 query tools (list_versions, overview, list_activities, get_activity, constraints, calendar) |
| `backend/tools/ms/workspace.py` | 99 | `load_schedule_ms` - loads full schedule into workspace |
| `backend/tools/ms/versions.py` | 143 | `create_schedule_subversion_ms`, `promote_subversion_ms` |
| `backend/repositories/ms_schedule_repository.py` | 539 | All CRUD: versions, activities, relationships, calendar, constraints |
| `backend/models/io.py` | 670 | MS request models at lines 580-670 (9 models with `ConfigDict(strict=True)`) |

### Backend - Agent & Other

| File | Relevance |
|------|-----------|
| `backend/agents/scheduling_agent.py` | All 9 MS tools registered (L65-79, L223-235). No changes unless new tools added |
| `backend/models/domain.py` | Domain models. May need updates if new data structures added |

### Frontend (likely no changes for date fix)

| File | Lines | Status |
|------|-------|--------|
| `frontend/components/gantt/GanttPanel.tsx` | 539 | Working. `preserve_order` sort mode, hierarchy rendering, virtualization |
| `frontend/components/gantt/GanttChart.tsx` | 221 | Standalone/report chart. No hierarchy (minor gap) |
| `frontend/components/gantt/RelationshipArrows.tsx` | - | Dependency arrows. Working |
| `frontend/types/schedule.ts` | 139 | Type defs. Working |

---

## 6. Data Flow Diagram

### Current (Broken)
```
Supabase
  schedule_activities.start/finish  ← CORRECT dates from MS Project
  schedule_activities.duration_d
  schedule_links.pred_id/succ_id/rel_type/lag_d
    │
    ▼
load_from_ms()  [schedule_state.py L394]
  target_start_date/target_end_date  (original dates stored but unused later)
  target_drtn_hr_cnt = duration_d * 8
  relationships_df mapped (pred_type prefixed with PR_)
  workspace.project_start = None  ← BUG: never set
  constraint_type/constraint_date = NOT MAPPED  ← BUG
    │
    ▼
calculate_gantt_ws()  [mutations.py L226]
    │
    ▼
NetworkCalculator(project_start_date=None → defaults to date.today())  ← WRONG
  build_network():  SS/FF/SF → treated as FS  ← WRONG
  forward_pass():   hardcoded Mon-Fri, no holidays  ← WRONG
  backward_pass():  simplified lag  ← WRONG
    │
    ▼
early_start/early_finish  (CALCULATED — overwrites correct MS dates)
    │
    ▼
_build_ms_project_hierarchy() → GanttPanel  (displays wrong dates)
```

### Target (Fixed)
```
Supabase
  schedule_activities.start/finish  ← ground truth
  schedule_activities.duration_d/constraint_type/constraint_date
  schedule_links (all rel_types)
  project_constraints (project start date, scheduling direction)
  project_calendars + calendar_exceptions
    │
    ▼
load_from_ms()
  Map constraint_type → engine format (query constraint_types table)
  Map constraint_date
  Set workspace.project_start from project_constraints or MIN(start)
  Preserve original_start/original_finish for validation
  Derive status from percent_complete
  Adjust remain_drtn_hr_cnt = target * (1 - pct/100)
  Attach calendar exceptions to workspace
    │
    ▼
NetworkCalculator(project_start=actual, calendar_exceptions=[...])
  build_network(): Store actual rel_type on edges (FS/SS/FF/SF)
  forward_pass(): Handle all 4 types, use calendar, apply constraints
  backward_pass(): Handle all 4 types, proper lag
    │
    ▼
early_start/early_finish  (should match MS Project ± 1 day)
    │
    ▼
validate_against_stored_dates() → log discrepancies
    │
    ▼
_build_ms_project_hierarchy() → GanttPanel  (correct dates)
```

---

## 7. Column Mapping Reference

### schedule_activities (Supabase) → Workspace DataFrame

| Supabase Column | Currently Mapped To | Status |
|-----------------|-------------------|--------|
| `id` | `task_id` | OK |
| `name` | `task_name` | OK |
| `ms_uid` | `task_code` | OK |
| `start` | `target_start_date` | OK but unused by CPM |
| `finish` | `target_end_date` | OK but unused by CPM |
| `percent_complete` | `phys_complete_pct` | OK but no status derived |
| `total_float_d` | `total_float_days` | OK but overwritten by CPM |
| `actual_start` | `act_start_date` | OK |
| `actual_finish` | `act_end_date` | OK |
| `duration_d` | `target_drtn_hr_cnt` (×8) | OK |
| `duration_d` | `remain_drtn_hr_cnt` (×8) | BUG: not adjusted for pct |
| `wbs` | `wbs_path` | OK |
| `is_summary` | (carried through) | OK |
| `is_milestone` | (carried through) | OK |
| `constraint_type` | **NOT MAPPED** | MISSING |
| `constraint_date` | **NOT MAPPED** | MISSING |
| `owner` | (carried through) | OK |
| `scope_owner` | (carried through) | OK |
| `baseline_*` | (not mapped) | Not needed for CPM |

### schedule_links (Supabase) → Workspace relationships_df

| Supabase Column | Currently Mapped To | Status |
|-----------------|-------------------|--------|
| `id` | `task_pred_id` | OK |
| `succ_id` | `task_id` | OK |
| `pred_id` | `pred_task_id` | OK |
| `rel_type` | `pred_type` (prefixed `PR_`) | OK mapping, but engine ignores non-FS |
| `lag_d` | `lag_hr_cnt` (×8) | OK mapping, but backward pass simplified |

---

## 8. Implementation Plan (Phased)

### Phase 1: Fix Project Start Date (30 min) — Fixes RC-1
1. In `load_schedule_ms` (`backend/tools/ms/workspace.py`), query `project_constraints` for the project start date
2. Pass it to `schedule_state_manager.load_from_ms()`
3. In `load_from_ms()`, set `workspace.project_start` from the constraint or `MIN(start)` of non-summary activities
4. **Validate**: Project start in Gantt header should match MS Project

### Phase 2: Preserve & Validate Stored Dates (1 hour)
1. In `load_from_ms()`, keep `start`/`finish` as `original_start`/`original_finish` columns
2. In `calculate_gantt_ws()`, after CPM runs, add validation method
3. New method `validate_against_ms_dates()` on `NetworkCalculator` or workspace: compare `early_start` vs `original_start` per task, log discrepancies
4. **Validate**: Logs show per-activity comparison

### Phase 3: Support All Relationship Types (2-3 hours) — Fixes RC-2
1. In `build_network()`, store actual relationship type on NetworkX edge attributes
2. In `forward_pass()`, implement ES/EF calculation for each type:
   - FS: ES(succ) = EF(pred) + lag
   - SS: ES(succ) = ES(pred) + lag
   - FF: EF(succ) = EF(pred) + lag → ES(succ) = EF(succ) - duration
   - SF: EF(succ) = ES(pred) + lag → ES(succ) = EF(succ) - duration
3. In `backward_pass()`, implement corresponding LF/LS for each type — Fixes RC-6
4. **Validate**: Find SS/FF/SF relationships in data, compare dates

### Phase 4: Calendar Support (2-3 hours) — Fixes RC-3
1. Add `calendar_exceptions: list[date]` param to `NetworkCalculator.__init__()`
2. In `load_from_ms()`, load calendar exceptions and attach to workspace
3. Pass through in `calculate_gantt_ws()` when creating `NetworkCalculator`
4. Update `_days_to_work_date()` and `_work_days_between()` to skip exception dates
5. **Validate**: Find activity spanning a holiday, verify date accounts for it

### Phase 5: Constraint Type Mapping (1-2 hours) — Fixes RC-4
1. Query `constraint_types` table to understand the integer → meaning mapping
2. In `load_from_ms()`, map `constraint_type` integer IDs to engine-compatible values
3. Map `constraint_date` column into workspace
4. Ensure `forward_pass()` applies constraints (it already has MSOA/SNET logic)
5. **Validate**: Find constrained activity, verify date matches MS Project

### Phase 6: Status & Remaining Duration (30 min) — Fixes RC-5
1. In `load_from_ms()`, derive `status_code`:
   - `percent_complete == 0` → `TK_NotStart`
   - `percent_complete == 100` → `TK_Complete`
   - else → `TK_Active`
2. Adjust `remain_drtn_hr_cnt = target_drtn_hr_cnt * (1 - percent_complete/100)`
3. **Validate**: Completed activities use actual dates, in-progress use partial duration

---

## 9. Change Registry Template

**CRITICAL INSTRUCTION**: Maintain this registry throughout implementation. Create a file `docs/changes/ms_cpm_fix_registry.md` and update it after **every** modification. Each entry must include:

```markdown
### [STATUS] Change ID: <sequential number>

**File**: `<relative path>`
**Function/Class/Model**: `<name>`
**Change Type**: NEW | MODIFIED | DELETED
**Phase**: <1-6>
**Root Cause**: <RC-1 through RC-6 or N/A>

**Description**: <what was changed and why>

**Lines Before**: <line range in original file>
**Lines After**: <line range after modification>

**Dependencies**: <other Change IDs this depends on>
**Dependents**: <other Change IDs that depend on this>

**Validation**:
- [ ] Unit test: <test name or "N/A">
- [ ] Integration test: <describe>
- [ ] Date comparison: <X of Y activities match within 1 day>

**Notes**: <any caveats, follow-ups, or decisions made>
```

### Pre-populated Registry (fill in as you go)

| ID | Phase | File | Function/Model | Type | RC | Status |
|----|-------|------|----------------|------|----|--------|
| 1 | 1 | `schedule_state.py` | `load_from_ms()` | MOD | RC-1 | [ ] |
| 2 | 1 | `schedule_state.py` | `ScheduleWorkspace` | MOD | RC-1 | [ ] |
| 3 | 1 | `ms/workspace.py` | `load_schedule_ms()` | MOD | RC-1 | [ ] |
| 4 | 2 | `schedule_state.py` | `load_from_ms()` | MOD | - | [ ] |
| 5 | 2 | `mutations.py` | `calculate_gantt_ws()` | MOD | - | [ ] |
| 6 | 2 | `network_calculator.py` | `validate_against_ms_dates()` | NEW | - | [ ] |
| 7 | 3 | `network_calculator.py` | `build_network()` | MOD | RC-2 | [ ] |
| 8 | 3 | `network_calculator.py` | `forward_pass()` | MOD | RC-2 | [ ] |
| 9 | 3 | `network_calculator.py` | `backward_pass()` | MOD | RC-2,6 | [ ] |
| 10 | 4 | `network_calculator.py` | `__init__()` | MOD | RC-3 | [ ] |
| 11 | 4 | `network_calculator.py` | `_days_to_work_date()` | MOD | RC-3 | [ ] |
| 12 | 4 | `network_calculator.py` | `_work_days_between()` | MOD | RC-3 | [ ] |
| 13 | 4 | `schedule_state.py` | `load_from_ms()` | MOD | RC-3 | [ ] |
| 14 | 4 | `mutations.py` | `calculate_gantt_ws()` | MOD | RC-3 | [ ] |
| 15 | 5 | `schedule_state.py` | `load_from_ms()` | MOD | RC-4 | [ ] |
| 16 | 5 | `ms_schedule_repository.py` | (query constraint_types) | MOD? | RC-4 | [ ] |
| 17 | 6 | `schedule_state.py` | `load_from_ms()` | MOD | RC-5 | [ ] |

---

## 10. Validation Protocol

After each phase, run this validation:

```sql
-- Get 5 sample non-summary activities with their MS dates
SELECT ms_uid, name, start as ms_start, finish as ms_finish, duration_d
FROM schedule_activities
WHERE version_id = <VERSION_ID> AND is_summary = false
ORDER BY wbs LIMIT 5;
```

Compare with Gantt display. Acceptable: +/- 1 calendar day.

### Test Scenarios
1. **Basic FS chain**: 3 activities connected by FS relationships
2. **SS relationship**: Find an SS link, verify both start same day + lag
3. **FF relationship**: Find an FF link, verify both finish same day + lag
4. **Holiday**: Activity spanning a calendar exception date
5. **Constraint**: Activity with Must Start On / Start No Earlier Than
6. **Completed activity**: 100% complete, verify actual dates used
7. **Summary rollup**: Summary bar spans match child date ranges
8. **Regression**: P6 Phoenix Tower schedule still calculates correctly

---

## 11. Running the Application

```bash
cd /Users/facu/LOGNOS/01_APPS/ASSIST/P6_ASSIST

# Backend
make backend

# Frontend (separate terminal)
make p6   # or:  cd frontend && npm run dev
```

**Test URL**: http://localhost:3000

**Test flow**: Select BIO4-01-0002 project → "load the ms project schedule" → "show me the gantt"

### Logs & Debugging
```
mcp_logfire_arbitrary_query with age: 10
```
Check for: `Built MS Project hierarchy`, `calculate_gantt_ws`, errors.

---

## 12. Test Data

- **MS Project**: BIO4-01-0002 (`project_id` in `ms_projects` table)
- **647 activities** (146 summaries, 501 details), max WBS depth 7
- **P6 regression test**: Phoenix Tower Construction (P6 ID: 1011)
- Do NOT break P6 schedule calculations

---

## 13. Success Criteria

1. CPM dates match MS Project stored dates within 1-day tolerance for >95% of activities
2. Project start/finish matches MS Project
3. All 4 relationship types (FS/SS/FF/SF) produce correct dates
4. Calendar exceptions (holidays) affect date calculations
5. MS constraints applied correctly
6. Validation log shows per-activity comparison results
7. P6 schedules still work (regression test)
8. Change registry fully populated with line numbers and validation status
