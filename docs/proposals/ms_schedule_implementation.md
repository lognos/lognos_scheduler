# MS Project Schedule Implementation Proposal

## Executive Summary

This proposal introduces support for Microsoft Project XML schedules stored in Supabase as an additional data source for the scheduling agent. The agent will gain the capability to:

1. **Read and display** schedule segments (e.g., "3-week lookahead" view)
2. **Modify schedules** in the workspace with visualization
3. **Save to temporary subversions** for review with optimistic locking
4. **Promote temporary versions** to "current" after validation (with diff visualization)

This mirrors the existing P6 workflow but targets Supabase-stored MS Project schedules using tools with the `_ms` suffix.

---

## Current Architecture Overview

### Existing Data Sources

| Source | Storage | Tools Suffix | Use Case |
|--------|---------|--------------|----------|
| P6 Database | SQLite (local) | `_p6` | Oracle Primavera P6 schedules |
| Workspace | In-memory (pandas) | `_ws` | Temporary edits, CPM calculation, Gantt visualization |

### Supabase MS Project Schema (Existing)

Tables discovered in `public` schema (project_id: `kxwradnyjqobvdheklsn`):

```
schedule_versions      - Version metadata (is_current, is_baseline, status_date)
schedule_activities    - Activity data (ms_uid, name, wbs, start, finish, duration_d, etc.)
schedule_links         - Relationships (pred_id, succ_id, rel_type, lag_d)
project_calendars      - Calendar definitions (working days/hours per version)
calendar_exceptions    - Non-working days, holidays, special hours
```

#### `schedule_versions` Key Fields
- `id`: Version identifier
- `project_name`: Schedule project name (e.g., "BIO4-01-0002")
- `version_name`: Version label (e.g., "v260101")
- `version_number`: Numeric version (e.g., 260101)
- `is_baseline`: Boolean - baseline snapshot
- `is_current`: Boolean - currently active version
- `status_date`: Status date for progress reporting
- `description`: Version notes
- `main_critical_path`: JSONB - cached critical path

#### `schedule_activities` Key Fields (Current)
- `id`: Internal ID (bigint)
- `ms_uid`: MS Project UID (integer) - original identifier
- `schedule_version_id`: FK to schedule_versions
- `name`: Activity name
- `name_verbose`: Full hierarchical name (WBS path + name)
- `wbs`: WBS code string
- `start` / `finish`: Planned dates
- `actual_start` / `actual_finish`: Actual dates
- `baseline_start` / `baseline_finish`: Baseline dates
- `baseline_duration_d`: Baseline duration
- `duration_d`: Duration in days
- `percent_complete`: Progress (0-100)
- `total_float_d`: Total float in days
- `is_milestone`: Boolean
- `is_summary`: Boolean
- `constraint_type` / `constraint_date`: Constraints
- `deadline_date`: Deadline constraint
- `calendar_id`: FK to project_calendars
- `cost`: Activity cost
- `notes`: Activity notes
- `embedding`: Vector for semantic search

#### `schedule_activities` New Fields (To Add)
- `scope_owner`: Text - Scope owner assignment
- `owner`: Text - Activity owner/responsible party

#### `schedule_links` Key Fields
- `id`: Link ID
- `pred_id` / `succ_id`: FK to schedule_activities.id
- `rel_type`: FS, SS, FF, SF
- `lag_d`: Lag in days
- `schedule_version_id`: FK to schedule_versions

#### `project_calendars` Key Fields
- `id`: Calendar ID
- `schedule_version_id`: FK to schedule_versions
- `calendar_name`: Calendar name (e.g., "Lunes - Sabado (6 días)")
- `is_base_calendar`: Boolean
- `working_days_per_week`: Integer (5, 6, 7)
- `working_hours_per_day`: Numeric (8.0, 9.0, etc.)

#### `calendar_exceptions` Key Fields
- `id`: Exception ID
- `calendar_id`: FK to project_calendars
- `exception_date`: Date of exception
- `is_working_day`: Boolean (false = holiday)
- `working_hours`: Override hours for the day
- `exception_type`: Text (holiday, reduced hours, etc.)

#### `constraint_types` (Lookup Table)
| ID | Name | Description |
|----|------|-------------|
| 0 | ASAP | As Soon As Possible |
| 1 | ALAP | As Late As Possible |
| 2 | MSO | Must Start On |
| 3 | MFO | Must Finish On |
| 4 | SNET | Start No Earlier Than |
| 5 | SNLT | Start No Later Than |
| 6 | FNET | Finish No Earlier Than |
| 7 | FNLT | Finish No Later Than |

#### `project_constraints` Key Fields
- `id`: Constraint ID
- `schedule_version_id`: FK to schedule_versions
- `project_start_date`: Project start constraint (timestamptz)
- `project_finish_date`: Project finish date (timestamptz)
- `status_date`: Data date / status date for scheduling (timestamptz)
- `schedule_from_start`: Boolean (true = forward scheduling)
- `created_at`: Record creation timestamp

---

## Proposed Architecture

### New Data Flow

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    SCHEDULING AGENT                      │
                    └─────────────────────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    ▼                         ▼                         ▼
            ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
            │   P6 Tools   │        │  MS Tools    │        │   WS Tools   │
            │    (_p6)     │        │    (_ms)     │        │    (_ws)     │
            └──────────────┘        └──────────────┘        └──────────────┘
                    │                         │                         │
                    ▼                         ▼                         ▼
            ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
            │   SQLite     │        │   Supabase   │        │   In-Memory  │
            │  (P6 DB)     │        │   (Postgres) │        │   (Pandas)   │
            └──────────────┘        └──────────────┘        └──────────────┘
```

### Tool Naming Convention

Following the existing pattern: `{action}_{entity}_{source}`

| Suffix | Target | Storage |
|--------|--------|---------|
| `_p6` | P6 Database | SQLite (local) |
| `_ms` | MS Project | Supabase (PostgreSQL) |
| `_ws` | Workspace | In-memory (pandas) |

---

## Proposed Tools

### Phase 1: Query Tools (Read-Only)

| Tool Name | Description |
|-----------|-------------|
| `list_schedule_versions_ms` | List all schedule versions for a project (baseline, current, temp) |
| `get_schedule_overview_ms` | Get 3-week lookahead (last week + next 2 weeks) with summary stats |
| `list_activities_ms` | List activities with filters (WBS, date range, status, critical, owner) |
| `get_activity_ms` | Get single activity details by ID or ms_uid |
| `search_activities_ms` | Semantic search using embeddings |
| `list_relationships_ms` | List relationships for activities |
| `get_critical_path_ms` | Get cached critical path from version metadata |
| `get_calendar_ms` | Get calendar info including exceptions for a version |
| `get_project_constraints_ms` | Get project constraints (start/finish dates, status date, scheduling direction) |

### Phase 2: Workspace Integration

| Tool Name | Description |
|-----------|-------------|
| `load_schedule_ms` | Load MS schedule version into workspace for editing |

This reuses existing workspace tools (`modify_activity_ws`, `add_relationship_ws`, `calculate_gantt_ws`) since the workspace is source-agnostic once loaded.

### Phase 3: Persistence Tools (Write)

| Tool Name | Description |
|-----------|-------------|
| `create_schedule_subversion_ms` | Save workspace to new temporary subversion |
| `promote_subversion_ms` | Set temporary version as `is_current = true` (with diff) |
| `update_activity_ms` | Direct update to MS activity in Supabase |
| `create_activity_ms` | Add new activity to MS schedule |
| `create_relationship_ms` | Add new relationship |
| `delete_activity_ms` | Remove activity |
| `delete_relationship_ms` | Remove relationship |

---

## Version Naming Convention

Subversions follow a consistent naming pattern:

| Pattern | Example | Use Case |
|---------|---------|----------|
| `v{YYMMDD}` | `v260111` | Official version from XML import |
| `draft-{YYMMDD}-{HHMM}` | `draft-260111-1430` | Auto-generated workspace save |
| `draft-{description}` | `draft-delay-analysis` | User-specified description |
| `temp-{user}-{YYMMDD}` | `temp-facu-260111` | User-specific temporary |

**Rules:**
- Official versions: `v` prefix + date code
- Draft/temp versions: `draft-` or `temp-` prefix
- Never overwrite existing version names (append timestamp if needed)

---

## Implementation Details

### 1. Database Migration: Add New Columns

```sql
-- Migration: add_owner_fields_to_schedule_activities
ALTER TABLE schedule_activities 
ADD COLUMN IF NOT EXISTS scope_owner TEXT,
ADD COLUMN IF NOT EXISTS owner TEXT;

-- Index for filtering by owner
CREATE INDEX IF NOT EXISTS idx_schedule_activities_owner 
ON schedule_activities(owner) WHERE owner IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_schedule_activities_scope_owner 
ON schedule_activities(scope_owner) WHERE scope_owner IS NOT NULL;
```

### 2. New Repository: `ms_schedule_repository.py`

```python
# backend/repositories/ms_schedule_repository.py

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, date, timedelta
from supabase import Client

@dataclass
class MSScheduleRepository:
    """Repository for MS Project schedules stored in Supabase."""
    
    supabase: Client
    
    async def list_versions(
        self,
        project_name: str,
        include_temp: bool = True
    ) -> list[dict]:
        """List all schedule versions for a project."""
        query = self.supabase.table('schedule_versions') \
            .select('*') \
            .eq('project_name', project_name) \
            .order('version_number', desc=True)
        
        return query.execute().data
    
    async def get_version(self, version_id: int) -> Optional[dict]:
        """Get version by ID."""
        result = self.supabase.table('schedule_versions') \
            .select('*') \
            .eq('id', version_id) \
            .single() \
            .execute()
        return result.data
    
    async def get_current_version(self, project_name: str) -> Optional[dict]:
        """Get the current active version."""
        result = self.supabase.table('schedule_versions') \
            .select('*') \
            .eq('project_name', project_name) \
            .eq('is_current', True) \
            .single() \
            .execute()
        
        return result.data
    
    async def get_activities_lookahead(
        self,
        version_id: int,
        reference_date: date,
        weeks_back: int = 1,
        weeks_forward: int = 2,
        include_summary: bool = False
    ) -> list[dict]:
        """Get activities within a lookahead window."""
        start_date = reference_date - timedelta(weeks=weeks_back)
        end_date = reference_date + timedelta(weeks=weeks_forward)
        
        query = self.supabase.table('schedule_activities') \
            .select('*') \
            .eq('schedule_version_id', version_id) \
            .gte('start', start_date.isoformat()) \
            .lte('finish', end_date.isoformat())
        
        if not include_summary:
            query = query.eq('is_summary', False)
        
        return query.order('start').execute().data
    
    async def get_activities_by_version(
        self,
        version_id: int,
        limit: int = 500,
        offset: int = 0,
        wbs_prefix: Optional[str] = None,
        critical_only: bool = False,
        owner: Optional[str] = None,
        scope_owner: Optional[str] = None
    ) -> list[dict]:
        """Get all activities for a version with pagination and filters."""
        query = self.supabase.table('schedule_activities') \
            .select('*') \
            .eq('schedule_version_id', version_id)
        
        if wbs_prefix:
            query = query.like('wbs', f'{wbs_prefix}%')
        
        if critical_only:
            query = query.eq('total_float_d', 0)
        
        if owner:
            query = query.eq('owner', owner)
        
        if scope_owner:
            query = query.eq('scope_owner', scope_owner)
        
        return query.order('wbs').range(offset, offset + limit - 1).execute().data
    
    async def get_relationships_by_version(
        self,
        version_id: int
    ) -> list[dict]:
        """Get all relationships for a version."""
        return self.supabase.table('schedule_links') \
            .select('*, pred:schedule_activities!pred_id(name, ms_uid, wbs), succ:schedule_activities!succ_id(name, ms_uid, wbs)') \
            .eq('schedule_version_id', version_id) \
            .execute().data
    
    async def get_calendar(self, version_id: int) -> dict:
        """Get calendar info including exceptions for a version."""
        calendar = self.supabase.table('project_calendars') \
            .select('*') \
            .eq('schedule_version_id', version_id) \
            .execute().data
        
        if not calendar:
            return {'calendar': None, 'exceptions': []}
        
        cal = calendar[0]
        exceptions = self.supabase.table('calendar_exceptions') \
            .select('*') \
            .eq('calendar_id', cal['id']) \
            .order('exception_date') \
            .execute().data
        
        return {'calendar': cal, 'exceptions': exceptions}
    
    async def get_project_constraints(self, version_id: int) -> Optional[dict]:
        """Get project constraints for a version (dates, status date, direction)."""
        result = self.supabase.table('project_constraints') \
            .select('*') \
            .eq('schedule_version_id', version_id) \
            .execute().data
        
        if not result:
            return None
        
        constraints = result[0]
        # Enrich with constraint type names
        constraints['scheduling_direction'] = 'forward' if constraints.get('schedule_from_start') else 'backward'
        return constraints
    
    async def get_constraint_types(self) -> list[dict]:
        """Get all constraint type definitions."""
        return self.supabase.table('constraint_types') \
            .select('*') \
            .order('id') \
            .execute().data
    
    async def create_subversion(
        self,
        base_version_id: int,
        version_name: str,
        description: str,
        activities_df: 'pd.DataFrame',
        relationships_df: 'pd.DataFrame'
    ) -> int:
        """Create a new temporary subversion from workspace data.
        
        Uses optimistic locking: checks base_version hasn't changed.
        """
        # Get base version metadata
        base = self.supabase.table('schedule_versions') \
            .select('project_name, version_number') \
            .eq('id', base_version_id) \
            .single().execute().data
        
        # Generate version number from timestamp
        new_version_number = int(datetime.now().strftime('%y%m%d%H%M'))
        
        # Create new version record
        new_version = self.supabase.table('schedule_versions').insert({
            'project_name': base['project_name'],
            'version_name': version_name,
            'version_number': new_version_number,
            'is_baseline': False,
            'is_current': False,  # Temporary until promoted
            'description': description,
            'uploaded_by': 'workspace_save'
        }).execute().data[0]
        
        new_version_id = new_version['id']
        
        # Prepare activities for batch insert
        activities_records = []
        for _, row in activities_df.iterrows():
            activities_records.append({
                'schedule_version_id': new_version_id,
                'ms_uid': row.get('ms_uid') or row.get('task_code'),
                'name': row['task_name'],
                'name_verbose': row.get('name_verbose'),
                'wbs': row.get('wbs'),
                'start': row.get('target_start_date'),
                'finish': row.get('target_end_date'),
                'duration_d': row.get('target_drtn_hr_cnt', 0) / 8 if row.get('target_drtn_hr_cnt') else None,
                'percent_complete': row.get('phys_complete_pct', 0),
                'total_float_d': row.get('total_float_days'),
                'is_milestone': row.get('is_milestone', False),
                'is_summary': row.get('is_summary', False),
                'actual_start': row.get('act_start_date'),
                'actual_finish': row.get('act_end_date'),
                'constraint_type': row.get('constraint_type'),
                'constraint_date': row.get('constraint_date'),
                'owner': row.get('owner'),
                'scope_owner': row.get('scope_owner'),
                'notes': row.get('notes'),
            })
        
        # Batch insert activities
        if activities_records:
            self.supabase.table('schedule_activities').insert(activities_records).execute()
        
        # Get inserted activity IDs for relationship mapping
        inserted = self.supabase.table('schedule_activities') \
            .select('id, ms_uid') \
            .eq('schedule_version_id', new_version_id) \
            .execute().data
        
        uid_to_id = {a['ms_uid']: a['id'] for a in inserted}
        
        # Prepare relationships
        rel_records = []
        for _, row in relationships_df.iterrows():
            pred_uid = row.get('pred_ms_uid') or row.get('pred_task_code')
            succ_uid = row.get('succ_ms_uid') or row.get('succ_task_code')
            
            if pred_uid in uid_to_id and succ_uid in uid_to_id:
                rel_records.append({
                    'schedule_version_id': new_version_id,
                    'pred_id': uid_to_id[pred_uid],
                    'succ_id': uid_to_id[succ_uid],
                    'rel_type': row.get('pred_type', 'FS').replace('PR_', ''),
                    'lag_d': int(row.get('lag_hr_cnt', 0) / 8) if row.get('lag_hr_cnt') else 0,
                })
        
        if rel_records:
            self.supabase.table('schedule_links').insert(rel_records).execute()
        
        return new_version_id
    
    async def promote_to_current(
        self, 
        version_id: int,
        expected_current_version_id: Optional[int] = None
    ) -> dict:
        """Set a version as current with optimistic locking.
        
        Args:
            version_id: Version to promote
            expected_current_version_id: Expected current version (for optimistic lock)
        
        Returns:
            Dict with success status and diff summary
        
        Raises:
            ValueError: If optimistic lock fails (current changed)
        """
        # Get version info
        version = self.supabase.table('schedule_versions') \
            .select('project_name') \
            .eq('id', version_id) \
            .single().execute().data
        
        project_name = version['project_name']
        
        # Check optimistic lock
        current = self.supabase.table('schedule_versions') \
            .select('id') \
            .eq('project_name', project_name) \
            .eq('is_current', True) \
            .execute().data
        
        if expected_current_version_id and current:
            if current[0]['id'] != expected_current_version_id:
                raise ValueError(
                    f"Optimistic lock failed: current version changed from "
                    f"{expected_current_version_id} to {current[0]['id']}. "
                    f"Please reload and retry."
                )
        
        old_current_id = current[0]['id'] if current else None
        
        # Generate diff before promoting
        diff = await self._generate_version_diff(old_current_id, version_id) if old_current_id else None
        
        # Unset all current flags for this project
        self.supabase.table('schedule_versions') \
            .update({'is_current': False}) \
            .eq('project_name', project_name) \
            .execute()
        
        # Set new current
        self.supabase.table('schedule_versions') \
            .update({'is_current': True}) \
            .eq('id', version_id) \
            .execute()
        
        return {
            'success': True,
            'promoted_version_id': version_id,
            'previous_current_id': old_current_id,
            'diff': diff
        }
    
    async def _generate_version_diff(
        self, 
        old_version_id: int, 
        new_version_id: int
    ) -> dict:
        """Generate diff summary between two versions."""
        old_activities = self.supabase.table('schedule_activities') \
            .select('ms_uid, name, start, finish, duration_d, percent_complete') \
            .eq('schedule_version_id', old_version_id) \
            .eq('is_summary', False) \
            .execute().data
        
        new_activities = self.supabase.table('schedule_activities') \
            .select('ms_uid, name, start, finish, duration_d, percent_complete') \
            .eq('schedule_version_id', new_version_id) \
            .eq('is_summary', False) \
            .execute().data
        
        old_by_uid = {a['ms_uid']: a for a in old_activities}
        new_by_uid = {a['ms_uid']: a for a in new_activities}
        
        added = [new_by_uid[uid] for uid in set(new_by_uid) - set(old_by_uid)]
        removed = [old_by_uid[uid] for uid in set(old_by_uid) - set(new_by_uid)]
        
        modified = []
        for uid in set(old_by_uid) & set(new_by_uid):
            old = old_by_uid[uid]
            new = new_by_uid[uid]
            changes = {}
            
            for field in ['start', 'finish', 'duration_d', 'percent_complete']:
                if old.get(field) != new.get(field):
                    changes[field] = {'old': old.get(field), 'new': new.get(field)}
            
            if changes:
                modified.append({
                    'ms_uid': uid,
                    'name': new['name'],
                    'changes': changes
                })
        
        return {
            'added_count': len(added),
            'removed_count': len(removed),
            'modified_count': len(modified),
            'added': added[:10],  # Limit for display
            'removed': removed[:10],
            'modified': modified[:20]
        }
```

### 2. New Tools Module: `backend/tools/ms/`

```
backend/tools/ms/
    __init__.py
    queries.py      # list_schedule_versions_ms, get_schedule_overview_ms, etc.
    activities.py   # update_activity_ms, create_activity_ms
    relationships.py # create_relationship_ms, delete_relationship_ms
    versions.py     # create_schedule_subversion_ms, promote_subversion_ms
```

### 3. Request Models: `backend/models/io.py` (additions)

```python
# MS Schedule Request Models

class ListScheduleVersionsMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    project_name: str = Field(..., description="Project name (e.g., 'BIO4-01-0002')")
    include_temp: bool = Field(default=True, description="Include temporary subversions")

class GetScheduleOverviewMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    project_name: str = Field(..., description="Project name")
    version_id: Optional[int] = Field(None, description="Specific version ID (default: current)")
    reference_date: Optional[str] = Field(None, description="Reference date for lookahead (default: today)")
    weeks_back: int = Field(default=1, description="Weeks to look back")
    weeks_forward: int = Field(default=2, description="Weeks to look forward")

class ListActivitiesMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    version_id: int = Field(..., description="Schedule version ID")
    wbs_prefix: Optional[str] = Field(None, description="Filter by WBS prefix (e.g., '1.3')")
    date_start: Optional[str] = Field(None, description="Filter activities starting on/after this date")
    date_end: Optional[str] = Field(None, description="Filter activities finishing on/before this date")
    critical_only: bool = Field(default=False, description="Only critical path activities")
    status: Optional[Literal["not_started", "in_progress", "complete"]] = Field(None)
    owner: Optional[str] = Field(None, description="Filter by activity owner")
    scope_owner: Optional[str] = Field(None, description="Filter by scope owner")
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

class LoadScheduleMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    project_name: str = Field(..., description="Project name")
    version_id: Optional[int] = Field(None, description="Version to load (default: current)")

class CreateSubversionMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    version_name: Optional[str] = Field(None, description="Name for subversion (auto-generated if not provided)")
    description: str = Field(..., description="Description of changes made")

class PromoteSubversionMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    version_id: int = Field(..., description="Version ID to promote to current")
    expected_current_version_id: Optional[int] = Field(None, description="Expected current version for optimistic locking")

class UpdateActivityMsRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    activity_id: int = Field(..., description="Activity ID (internal)")
    start: Optional[str] = Field(None, description="New start date")
    finish: Optional[str] = Field(None, description="New finish date")
    duration_d: Optional[float] = Field(None, description="New duration in days")
    percent_complete: Optional[float] = Field(None, ge=0, le=100)
    actual_start: Optional[str] = Field(None)
    actual_finish: Optional[str] = Field(None)
    owner: Optional[str] = Field(None, description="Activity owner")
    scope_owner: Optional[str] = Field(None, description="Scope owner")
```
```

### 4. AgentDeps Extension

```python
# backend/tools/_base.py (modified)

@dataclass
class AgentDeps:
    """Dependencies for the scheduling agent."""
    
    # Existing P6 dependencies
    service: SchedulingService
    vector_service: Optional[VectorService] = None
    conn: Optional[object] = None  # SQLite connection for P6
    transaction: Optional["SafeP6Transaction"] = None
    
    # New MS Schedule dependencies
    ms_repository: Optional["MSScheduleRepository"] = None
    supabase_client: Optional["Client"] = None
    
    # Workspace (source-agnostic)
    gantt_event_queue: Optional[list] = None
    conversation_id: Optional[str] = None
    
    def mark_modified(self):
        """Mark the transaction as modified."""
        if self.transaction:
            self.transaction.mark_modified()
```

### 5. Schedule State Extension

The workspace (`ScheduleWorkspace`) needs to track the source:

```python
# backend/services/schedule_state.py (additions)

@dataclass
class ScheduleWorkspace:
    # ... existing fields ...
    
    # Source tracking
    source: str = "new"  # "new" | "p6_loaded" | "ms_loaded"
    source_version_id: Optional[int] = None  # For MS schedules
    source_project_name: Optional[str] = None  # For MS schedules
```

### 6. Workspace Loading from MS

New method in `schedule_state_manager`:

```python
def load_from_ms(
    self,
    conversation_id: str,
    project_name: str,
    version_id: int,
    activities: list[dict],
    relationships: list[dict],
    calendar_info: dict
) -> ScheduleWorkspace:
    """Load MS Project schedule into workspace."""
    
    # Convert to DataFrames with P6-compatible column names
    activities_df = pd.DataFrame(activities)
    activities_df = activities_df.rename(columns={
        'id': 'task_id',
        'name': 'task_name',
        'ms_uid': 'task_code',  # Use ms_uid as task identifier
        'start': 'target_start_date',
        'finish': 'target_end_date',
        'duration_d': 'target_drtn_hr_cnt',  # Convert days to hours
        'percent_complete': 'phys_complete_pct',
        'total_float_d': 'total_float_days',
        'actual_start': 'act_start_date',
        'actual_finish': 'act_end_date',
    })
    
    # Adjust duration from days to hours (8 hrs/day)
    if 'target_drtn_hr_cnt' in activities_df.columns:
        activities_df['target_drtn_hr_cnt'] = activities_df['target_drtn_hr_cnt'] * 8
    
    relationships_df = pd.DataFrame(relationships)
    relationships_df = relationships_df.rename(columns={
        'pred_id': 'pred_task_id',
        'succ_id': 'succ_task_id',
        'rel_type': 'pred_type',
        'lag_d': 'lag_hr_cnt'
    })
    
    # Convert lag from days to hours
    if 'lag_hr_cnt' in relationships_df.columns:
        relationships_df['lag_hr_cnt'] = relationships_df['lag_hr_cnt'] * 8
    
    workspace = ScheduleWorkspace(
        conversation_id=conversation_id,
        project_name=project_name,
        source="ms_loaded",
        source_version_id=version_id,
        source_project_name=project_name,
        activities_df=activities_df,
        relationships_df=relationships_df
    )
    
    self._workspaces[conversation_id] = workspace
    return workspace
```

---

## Tool Implementation Examples

### `get_schedule_overview_ms`

```python
@logfire.instrument("get_schedule_overview_ms")
async def get_schedule_overview_ms(
    ctx: RunContext[AgentDeps],
    req: GetScheduleOverviewMsRequest
) -> str:
    """Get 3-week lookahead schedule overview from MS Project (Supabase).
    
    Shows activities from last week through next 2 weeks, grouped by status.
    Use this tool to quickly understand current schedule state.
    
    Args:
        ctx: Runtime context with ms_repository
        req: Request with project_name, optional version_id and date range
    
    Returns:
        Formatted overview with activity counts, critical activities, and lookahead.
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available."
    
    try:
        # Get version (current if not specified)
        if req.version_id:
            version = await ctx.deps.ms_repository.get_version(req.version_id)
        else:
            version = await ctx.deps.ms_repository.get_current_version(req.project_name)
        
        if not version:
            return f"No schedule found for project '{req.project_name}'"
        
        # Parse reference date
        ref_date = date.fromisoformat(req.reference_date) if req.reference_date else date.today()
        
        # Get lookahead activities
        activities = await ctx.deps.ms_repository.get_activities_lookahead(
            version_id=version['id'],
            reference_date=ref_date,
            weeks_back=req.weeks_back,
            weeks_forward=req.weeks_forward
        )
        
        # Build response
        lines = [
            f"Schedule Overview: {req.project_name}",
            f"Version: {version['version_name']} {'(CURRENT)' if version['is_current'] else '(TEMP)'}",
            f"Reference Date: {ref_date.isoformat()}",
            f"Window: {req.weeks_back} week(s) back, {req.weeks_forward} week(s) forward",
            "",
            f"Activities in window: {len(activities)}",
        ]
        
        # Group by status
        not_started = [a for a in activities if (a.get('percent_complete') or 0) == 0 and not a.get('actual_start')]
        in_progress = [a for a in activities if a.get('actual_start') and (a.get('percent_complete') or 0) < 100]
        complete = [a for a in activities if (a.get('percent_complete') or 0) >= 100]
        
        lines.append(f"  - Not Started: {len(not_started)}")
        lines.append(f"  - In Progress: {len(in_progress)}")
        lines.append(f"  - Complete: {len(complete)}")
        
        # Critical activities
        critical = [a for a in activities if (a.get('total_float_d') or 0) == 0 and not a.get('is_summary')]
        if critical:
            lines.append("")
            lines.append(f"Critical Activities ({len(critical)}):")
            for act in critical[:10]:  # Limit to 10
                lines.append(f"  - {act['wbs']}: {act['name'][:50]} ({act['start'][:10]} - {act['finish'][:10]})")
        
        return "\n".join(lines)
        
    except Exception as e:
        logfire.error("Error in get_schedule_overview_ms", error=str(e))
        return f"Error: {str(e)}"
```

### `load_schedule_ms`

```python
@logfire.instrument("load_schedule_ms")
async def load_schedule_ms(
    ctx: RunContext[AgentDeps],
    req: LoadScheduleMsRequest
) -> str:
    """Load MS Project schedule from Supabase into workspace for editing.
    
    Creates an in-memory copy that can be modified and visualized without
    affecting the database. Use workspace tools (_ws) to make changes.
    
    Args:
        ctx: Runtime context with ms_repository and conversation_id
        req: Request with project_name and optional version_id
    
    Returns:
        Summary of loaded schedule
    """
    if not ctx.deps.ms_repository:
        return "MS Schedule repository not available."
    
    conversation_id = ctx.deps.conversation_id
    if not conversation_id:
        return "Error: No conversation_id available."
    
    try:
        # Get version
        if req.version_id:
            version = await ctx.deps.ms_repository.get_version(req.version_id)
        else:
            version = await ctx.deps.ms_repository.get_current_version(req.project_name)
        
        if not version:
            return f"No schedule found for project '{req.project_name}'"
        
        # Load all activities and relationships
        activities = await ctx.deps.ms_repository.get_activities_by_version(
            version_id=version['id'],
            limit=5000  # Full schedule
        )
        relationships = await ctx.deps.ms_repository.get_relationships_by_version(
            version_id=version['id']
        )
        
        # Load calendar info
        calendar_info = await ctx.deps.ms_repository.get_calendar(version['id'])
        
        # Load into workspace
        workspace = schedule_state_manager.load_from_ms(
            conversation_id=conversation_id,
            project_name=req.project_name,
            version_id=version['id'],
            activities=activities,
            relationships=relationships,
            calendar_info=calendar_info
        )
        
        calendar_name = calendar_info['calendar']['calendar_name'] if calendar_info.get('calendar') else 'Default'
        return f"Loaded '{req.project_name}' v{version['version_name']}: {len(activities)} activities, calendar: {calendar_name}. Use calculate_gantt_ws to visualize."
        
    except Exception as e:
        logfire.error("Error in load_schedule_ms", error=str(e))
        return f"Error: {str(e)}"
```

---

## Agent System Prompt Updates

Add guidance to `scheduler_system.xml.j2`:

```xml
<ms_schedule_tools>
    <description>
        MS Project schedules are stored in Supabase (not the P6 database).
        Use _ms tools to query and modify these schedules.
    </description>
    
    <workflow>
        1. Use list_schedule_versions_ms to see available versions
        2. Use get_schedule_overview_ms for 3-week lookahead view
        3. Use load_schedule_ms to load into workspace for editing
        4. Make changes with workspace tools (_ws)
        5. Save changes with create_schedule_subversion_ms
        6. After validation, promote with promote_subversion_ms
    </workflow>
    
    <version_states>
        - is_current=true: Active production version
        - is_baseline=true: Approved baseline (read-only reference)
        - is_current=false, is_baseline=false: Temporary/draft subversion
    </version_states>
</ms_schedule_tools>
```

---

## Implementation Phases

### Phase 1: Read-Only (1-2 days)

1. Create `MSScheduleRepository` with query methods
2. Implement `list_schedule_versions_ms`
3. Implement `get_schedule_overview_ms` (3-week lookahead)
4. Implement `list_activities_ms` with filters
5. Implement `search_activities_ms` (vector search)
6. Update `AgentDeps` with MS dependencies
7. Register tools in agent

**Deliverables:**
- Agent can list MS schedule versions
- Agent can show 3-week lookahead
- Agent can filter/search activities

### Phase 2: Workspace Integration (1 day)

1. Implement `load_schedule_ms`
2. Add `load_from_ms` to `ScheduleWorkspace`
3. Track source in workspace (`ms_loaded`)
4. Verify existing `_ws` tools work with MS-loaded data

**Deliverables:**
- Agent can load MS schedule to workspace
- All workspace tools work (modify, Gantt, etc.)

### Phase 3: Persistence (2-3 days)

1. Implement `create_schedule_subversion_ms`
2. Implement `promote_subversion_ms`
3. Implement direct modification tools (`update_activity_ms`, etc.)
4. Add validation logic for version promotion

**Deliverables:**
- Agent can save workspace to temporary subversion
- Agent can promote subversion to current
- Agent can make direct database edits

### Phase 4: Polish & Testing (1-2 days)

1. System prompt updates
2. Error handling refinement
3. Integration tests
4. Documentation

---

## Design Decisions (Resolved)

| Question | Decision |
|----------|----------|
| **Version Naming** | Auto-generated: `draft-{YYMMDD}-{HHMM}` or user-specified |
| **Concurrent Edits** | Optimistic locking via `expected_current_version_id` |
| **Baseline Protection** | Allow subversions from any version (including baselines) |
| **Calendar Handling** | Use existing `project_calendars` and `calendar_exceptions` tables |
| **Custom Fields** | Add `scope_owner` and `owner` columns to activities |
| **DCMA Integration** | Not included - no automatic trigger |
| **Diff Visualization** | Yes - show diff summary on promotion |

---

## Files to Create/Modify

### New Files
- `backend/repositories/ms_schedule_repository.py`
- `backend/tools/ms/__init__.py`
- `backend/tools/ms/queries.py`
- `backend/tools/ms/activities.py`
- `backend/tools/ms/relationships.py`
- `backend/tools/ms/versions.py`

### Modified Files
- `backend/tools/__init__.py` - Export MS tools
- `backend/tools/_base.py` - Add MS dependencies to AgentDeps
- `backend/models/io.py` - Add MS request models
- `backend/services/schedule_state.py` - Add `load_from_ms` method
- `backend/agents/scheduling_agent.py` - Register MS tools
- `backend/prompt/scheduler_system.xml.j2` - Add MS guidance
- `backend/api/dependencies.py` - Initialize MS repository

---

## Acceptance Criteria

- [ ] Agent correctly identifies when user is working with MS schedule vs P6
- [ ] 3-week lookahead shows correct activities with status breakdown
- [ ] Workspace loads MS schedule and Gantt displays correctly
- [ ] Changes in workspace can be saved to subversion with auto-generated name
- [ ] Subversion can be promoted to current with optimistic locking
- [ ] Optimistic lock failure returns clear error message
- [ ] Diff summary is generated and returned on version promotion
- [ ] Owner and scope_owner fields can be filtered and updated
- [ ] Calendar data is loaded from existing `project_calendars` table
- [ ] All tool docstrings are clear for LLM understanding
- [ ] Errors are handled gracefully with helpful messages
