# MS Project Schedule Display - Critical Bug Analysis & Resolution Prompt

## Context for Agent

You are picking up a critical bug in the Lognos Scheduling Assistant application. The MS Project schedule display feature was recently implemented but has fundamental issues with date calculations and rendering.

**Deadline**: End of today - client needs a functional MS Project schedule viewer.

**Repository**: `lognos/lognos_scheduler` on branch `master`
**Workspace**: `/Users/facu/LOGNOS/01_APPS/ASSIST/P6_ASSIST`

---

## Problem Statement

When displaying MS Project schedules, the application shows **completely wrong dates**:

| Issue | MS Project Shows | App Shows |
|-------|------------------|-----------|
| Project Start | Fri 3/7/25 (March 7, 2025) | Jan 12, 2026 |
| Activity Dates | Calculated by MS Project | Recalculated incorrectly |
| Duration/Float | From MS Project | Recalculated incorrectly |

**Important**: We DO need the NetworkX CPM engine to work for MS Project schedules because the agent will modify schedules and recalculate. The MS Project pre-calculated dates serve as **ground truth to validate our CPM implementation**.

---

## The Real Problem

The NetworkX CPM calculation engine produces different results than MS Project's calculations. This could be due to:

1. **Missing/incorrect relationship data** - Are predecessor/successor links imported correctly?
2. **Calendar differences** - MS Project uses specific calendars; are we handling them?
3. **Lag/Lead handling** - Are relationship lags being applied correctly?
4. **Constraint handling** - MS Project has constraints (Must Start On, etc.) that affect dates
5. **Data mapping issues** - Are we loading the right columns into the calculation engine?

The MS Project database has **both**:
- Pre-calculated dates (from MS Project) - the correct answers
- Relationship/dependency data - inputs for our CPM engine

We need to **debug why our CPM produces different results** than MS Project.

---

## Architecture Background

### Why CPM Calculation is Required

The application needs to:
1. **Display schedules** - Show activities with correct dates
2. **Modify schedules** - Agent can add/remove activities, change durations, modify relationships
3. **Recalculate after changes** - CPM engine must produce correct dates after modifications

MS Project's pre-calculated dates are **validation data** - we compare our CPM results against them to verify our engine is correct.

### P6 vs MS Project - Data Structure Difference

**P6 Schedules (existing, working)**:
- Imported from XML with raw activity definitions
- Relationships/links define dependencies
- Application calculates CPM to derive Early Start/Early Finish dates
- NetworkX engine performs forward/backward pass calculations

**MS Project Schedules (needs debugging)**:
- Stored in Supabase `schedule_activities` table
- Has **both** raw data (durations, relationships) AND calculated dates
- We should calculate CPM and **compare** with stored dates
- If they match → engine works correctly
- If they don't → we need to fix the engine or data mapping

### Key Files

1. **`backend/tools/workspace/mutations.py`**
   - `calculate_gantt_ws()` - Main function that calculates and streams Gantt data
   - `_build_ms_project_hierarchy()` - Builds hierarchical items for MS Project (recently added)
   - Currently calls `workspace.calculate_network()` for ALL schedules (P6 and MS)

2. **`backend/services/schedule_state.py`**
   - `ScheduleWorkspace` class manages in-memory schedule data
   - `load_from_ms()` - Loads MS Project data from Supabase
   - `calculate_network()` - Runs NetworkX CPM (should NOT be called for MS Project)

3. **`backend/services/network_calculator.py`**
   - NetworkX-based CPM implementation
   - Designed for P6 data structure
   - Calculates early_start, early_finish, late_start, late_finish, float

4. **`backend/repositories/p6_schedule_repository.py`**
   - Contains MS Project query methods (despite the name)
   - `get_schedule_activities_ms()` - Fetches activities from Supabase

5. **`backend/tools/p6/ms_schedule_tools.py`**
   - MS Project specific tools
   - `load_schedule_ms`, `get_schedule_overview_ms`, etc.

---

## Database Reference

**Supabase Project ID**: `kxwradnyjqobvdheklsn`

Use MCP tools to query:
```
mcp_supabase_execute_sql with project_id: kxwradnyjqobvdheklsn
```

### Key Tables

**`ms_projects`** - MS Project metadata
```sql
SELECT * FROM ms_projects WHERE project_id = 'BIO4-01-0002';
```

**`schedule_versions`** - Version history
```sql
SELECT * FROM schedule_versions WHERE ms_project_id = (
  SELECT id FROM ms_projects WHERE project_id = 'BIO4-01-0002'
);
```

**`schedule_activities`** - Activities with dates
```sql
SELECT 
  ms_uid,
  name,
  wbs,
  is_summary,
  start_date,
  finish_date,
  duration_d,
  percent_complete
FROM schedule_activities 
WHERE version_id = '<version_id>'
ORDER BY wbs
LIMIT 20;
```

Check what date columns exist:
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'schedule_activities'
AND column_name LIKE '%date%' OR column_name LIKE '%start%' OR column_name LIKE '%finish%';
```

---

## Proposed Solution Direction

### Debugging Approach (Required First)

1. **Query MS Project dates from database** - Get the "correct" dates
2. **Run CPM calculation** - Get our calculated dates  
3. **Compare side by side** - Identify discrepancies
4. **Trace the differences** - Find root cause

### Investigation Queries

```sql
-- Get activities with MS Project dates vs what we might be missing
SELECT 
  ms_uid,
  name,
  wbs,
  duration_d,
  start_date as ms_start,
  finish_date as ms_finish,
  -- Check for constraint columns
  constraint_type,
  constraint_date
FROM schedule_activities 
WHERE version_id = '<version_id>'
AND is_summary = false
ORDER BY wbs
LIMIT 20;

-- Get relationships/dependencies
SELECT 
  sa.name as activity_name,
  sa.ms_uid,
  -- Look for predecessor columns
  sa.predecessors
FROM schedule_activities sa
WHERE version_id = '<version_id>'
LIMIT 20;

-- Check what relationship data exists
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'schedule_activities'
AND (column_name LIKE '%pred%' OR column_name LIKE '%succ%' OR column_name LIKE '%link%' OR column_name LIKE '%relation%');
```

### Potential Fixes Based on Root Cause

**If relationships missing/incorrect:**
- Import MS Project predecessor/successor data
- Map to NetworkX graph correctly

**If calendar not handled:**
- Implement MS Project calendar support
- Use working days vs calendar days correctly

**If constraints not handled:**
- Parse constraint_type and constraint_date
- Apply constraints in CPM calculation

**If data mapping wrong:**
- Verify duration units (days vs hours)
- Check date format parsing
- Validate start date anchor

### Temporary Workaround (If CPM fix takes too long)

As a **short-term solution** for today's demo, if fixing CPM is complex:

1. Add a flag to use MS Project stored dates directly for display
2. Disable modification features temporarily
3. Document that recalculation is WIP

```python
# In calculate_gantt_ws()
if is_ms_schedule and not req.force_recalculate:
    # Use stored dates for display (temporary)
    result = workspace.get_stored_ms_dates()
else:
    # Full CPM calculation (for modifications or P6)
    result = workspace.calculate_network()
```

### Long-term Fix (Required)

1. Fix CPM engine to match MS Project calculations
2. Add validation step that compares calculated vs stored dates
3. Log discrepancies for debugging
4. Eventually, calculated dates should match stored dates

---

## Specific Code Changes to Investigate

### 1. Check what date columns exist in database

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'schedule_activities'
ORDER BY ordinal_position;
```

### 2. In `schedule_state.py` - `load_from_ms()`

Check how data is loaded:
- Are `start_date` and `finish_date` being loaded?
- Are relationships/predecessors being loaded?
- Is duration being loaded correctly (days vs hours)?

### 3. In `network_calculator.py` - CPM Implementation

Verify the algorithm:
- How is project start date determined?
- How are durations used (working days vs calendar days)?
- How are relationships processed?
- Are lags handled?

### 4. Compare Input Data

Log what goes INTO the CPM calculation:
- Activity durations
- Relationships (pred/succ)
- Project start date

### 5. Add Validation Step

After calculation, compare results:
```python
def validate_calculation(calculated_df, stored_dates_df):
    """Compare CPM results with MS Project dates."""
    discrepancies = []
    for task_id in calculated_df['task_id']:
        calc_start = calculated_df[calculated_df['task_id'] == task_id]['early_start']
        stored_start = stored_dates_df[stored_dates_df['task_id'] == task_id]['start_date']
        if calc_start != stored_start:
            discrepancies.append({
                'task_id': task_id,
                'calculated': calc_start,
                'expected': stored_start,
                'diff_days': (calc_start - stored_start).days
            })
    return discrepancies
```

---

## Verification Steps

After fix, verify:

1. **CPM calculation matches MS Project dates**
   - Run validation comparison
   - Discrepancies should be < 1 day (calendar rounding)

2. **Project dates match MS Project export**
   - Query: `SELECT MIN(start_date), MAX(finish_date) FROM schedule_activities WHERE version_id = ?`
   - Compare with calculated project_start and project_finish

3. **Activity dates match**
   - Pick 5 activities from different levels
   - Compare calculated vs stored dates

4. **Modification works**
   - Change an activity duration
   - Verify recalculation produces reasonable results

5. **Hierarchy displays correctly**
   - Summary tasks show correct spans
   - Children nested under parents
   - WBS order preserved

6. **No regressions on P6**
   - Test P6 schedule still works with CPM calculations

---

## Test Data

**MS Project Schedule**: BIO4-01-0002
- Version: v260101
- Project ID in Supabase: Query `ms_projects` table
- Has 647 activities (146 summaries, 501 details)
- Max WBS depth: 7 levels

**P6 Schedule for regression test**: Phoenix Tower Construction (P6 ID: 1011)

---

## Running the Application

```bash
cd /Users/facu/LOGNOS/01_APPS/ASSIST/P6_ASSIST

# Backend
make backend

# Frontend (separate terminal)
cd frontend && npm run dev
```

**Test URL**: http://localhost:3000

**Test prompt**: "show me the bio4-01-0002 project schedule" → "it's a ms project schedule of the project with project id BIO4-001-0002"

---

## Logs & Debugging

Use Logfire MCP tool:
```
mcp_logfire_arbitrary_query with age: 10
```

Check for:
- `Built MS Project hierarchy` spans
- `calculate_gantt_ws` execution
- Any calculation/date transformation logs

---

## Success Criteria

1. ✅ CPM calculation produces dates matching MS Project (within 1 day tolerance)
2. ✅ Project start/finish matches MS Project export
3. ✅ Activity dates match MS Project export  
4. ✅ Can modify schedule and recalculate correctly
5. ✅ Hierarchy (summary/detail) displays correctly
6. ✅ P6 schedules continue to work (CPM calculation)
7. ✅ No JSON serialization errors
8. ✅ Gantt renders without frontend errors

---

## Key Question to Answer

**Why does our NetworkX CPM produce different dates than MS Project?**

Possible answers:
- Relationships not loaded/mapped correctly
- Calendar/working days not handled
- Constraints not applied
- Duration units mismatch
- Project start anchor wrong
- Lag/lead not processed

Find the root cause, fix it, and validate with MS Project's pre-calculated dates.

---

## Priority

**CRITICAL** - Client delivery today. 

**Recommended approach**:
1. First, implement temporary workaround using stored dates for display (30 min)
2. Then, debug CPM calculation to find root cause (2-3 hours)
3. Fix CPM to match MS Project results
4. Remove workaround, use calculated dates

This gives client a working demo while we fix the underlying calculation.
