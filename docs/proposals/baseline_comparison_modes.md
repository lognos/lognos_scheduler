# Baseline Comparison Modes

**Date:** March 3, 2026
**Status:** Draft
**Author:** Engineering Team
**Depends on:** Baseline visualization (implemented)

---

## 1. Objective

Transform the "Baseline" button from a simple on/off toggle into a dropdown with three comparison modes. This lets users compare the current schedule against different reference points:

| Mode | Label | Ghost bars show | Source |
|------|-------|-----------------|--------|
| Own Baseline | Own Baseline | `baseline_start` / `baseline_finish` from the current version's activities | Current `schedule_activities` columns |
| Previous Version | Previous Version | `start` / `finish` from the immediately preceding schedule version | Cross-version query by `ms_uid` |
| Database Baseline | Database Baseline | `start` / `finish` from the version flagged `is_baseline = true` | Cross-version query by `ms_uid` |

**Default:** Own Baseline (current behavior).

---

## 2. Current State

### 2.1 Database

**`schedule_versions`** for BIO4-24101:

| id | version_name | version_number | is_current | is_baseline | data_date |
|----|--------------|----------------|------------|-------------|-----------|
| 21 | v260129 | 260129 | true | false | - |
| 20 | v260101 | 260101 | false | false | 2026-01-10 |
| 15 | v250912 | 250912 | false | false | 2025-09-12 |
| 0 | baseline | 250710 | false | **true** | 2025-07-09 |
| 10 | v250710 | 250710 | false | false | 2025-07-12 |

**`schedule_activities`** columns relevant to each mode:

- **Own Baseline**: `baseline_start`, `baseline_finish`, `baseline_duration_d` (columns on each activity row)
- **Previous Version / Database Baseline**: `start`, `finish`, `duration_d` from a *different* version's activities, matched by `ms_uid`

### 2.2 Backend

`build_view_payload()` currently reads `baseline_start` and `baseline_finish` from the current version's activities and maps them to `baseline_start` / `baseline_finish` in the payload items. There is no mechanism to fetch dates from a different version.

### 2.3 Frontend

- `ScheduleItem` has `baseline_start`, `baseline_finish`, `baseline_duration_d`
- `GanttChartData` has `has_baseline: boolean`
- `useBarPositions` computes `baselineStartPercentage` / `baselineWidthPercentage`
- GanttPanel has a simple "Baseline" toggle button
- The ghost bars and slippage tooltip consume the above fields

### 2.4 Gaps

| Layer | Gap |
|-------|-----|
| Backend | No method to fetch activities from a different version for comparison |
| Backend | No way to resolve "previous version" or "database baseline version" |
| Backend | `build_view_payload` hardcodes own-baseline columns |
| API | No parameter to request a specific baseline mode |
| Frontend types | No baseline mode concept |
| GanttPanel | No dropdown on the Baseline button |

---

## 3. Proposed Implementation

### 3.1 Data Model: Baseline Modes

```
BaselineMode = "own" | "previous_version" | "database_baseline"
```

- **`own`** (default): Use `baseline_start` / `baseline_finish` from the current activity (existing behavior, zero extra queries)
- **`previous_version`**: Resolve the version with the next-lower `version_number` for the same `project_name`. Fetch its activities, match by `ms_uid`, and use their `start` / `finish` as baseline dates
- **`database_baseline`**: Resolve the version where `is_baseline = true` for the same `project_name`. Same cross-version matching by `ms_uid`

### 3.2 Backend: Version Resolution Helpers

**File:** `backend/repositories/ms_schedule_repository.py`

```python
async def get_previous_version(
    self, project_name: str, current_version_number: int
) -> Optional[dict]:
    """Get the version immediately before the current one."""
    result = (
        self._table("schedule_versions")
        .select("*")
        .eq("project_name", project_name)
        .lt("version_number", current_version_number)
        .order("version_number", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None

async def get_baseline_version(self, project_name: str) -> Optional[dict]:
    """Get the version flagged as baseline."""
    try:
        result = (
            self._table("schedule_versions")
            .select("*")
            .eq("project_name", project_name)
            .eq("is_baseline", True)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        return None
```

### 3.3 Backend: Cross-Version Baseline Overlay

**File:** `backend/services/schedule_view_service.py`

Add a method that fetches activities from a reference version and returns a `ms_uid -> (start, finish, duration_d)` lookup:

```python
async def _build_cross_version_baseline(
    self, reference_version_id: int
) -> dict[str, tuple[Optional[datetime], Optional[datetime], Optional[float]]]:
    """Build a ms_uid -> (start_dt, finish_dt, duration_d) map from a reference version."""
    ref_activities = await self.ms_repository.get_activities_by_version(
        version_id=reference_version_id,
        limit=5000,
        include_summary=True,
    )
    lookup: dict[str, tuple] = {}
    for a in ref_activities:
        ms_uid = a.get("ms_uid")
        if ms_uid is None:
            continue
        key = str(ms_uid)
        start_dt = self._normalize_datetime(a.get("start"))
        finish_dt = self._normalize_datetime(a.get("finish"))
        dur = float(a.get("duration_d") or 0) if a.get("duration_d") is not None else None
        lookup[key] = (start_dt, finish_dt, dur)
    return lookup
```

In `build_view_payload()`, after parsing current activities:

```python
baseline_mode = config.get("baseline_mode", "own")

if baseline_mode == "own":
    # Current behavior: use baseline_start/baseline_finish from current activities
    pass  # Already populated in parsed loop
elif baseline_mode in ("previous_version", "database_baseline"):
    # Resolve the reference version
    current_version = await self.ms_repository.get_version(schedule_version_id)
    ref_version = None
    if baseline_mode == "previous_version" and current_version:
        ref_version = await self.ms_repository.get_previous_version(
            current_version["project_name"],
            current_version["version_number"],
        )
    elif baseline_mode == "database_baseline" and current_version:
        ref_version = await self.ms_repository.get_baseline_version(
            current_version["project_name"],
        )

    if ref_version:
        cross_baseline = await self._build_cross_version_baseline(ref_version["id"])
        # Override baseline dates in parsed items
        for item in parsed:
            ref = cross_baseline.get(item["s_item_id"])
            if ref:
                item["baseline_start_dt"] = ref[0]
                item["baseline_finish_dt"] = ref[1]
                item["baseline_duration_d"] = ref[2]
            else:
                # Activity doesn't exist in reference version
                item["baseline_start_dt"] = None
                item["baseline_finish_dt"] = None
                item["baseline_duration_d"] = None
    else:
        # Reference version not found; clear all baseline
        for item in parsed:
            item["baseline_start_dt"] = None
            item["baseline_finish_dt"] = None
            item["baseline_duration_d"] = None
```

This reuses the exact same downstream code (items_payload, `has_baseline`, `useBarPositions`, ghost bars, slippage tooltip) without any changes. The only difference is _where_ the baseline dates come from.

### 3.4 Backend: Baseline Mode in Snapshot Config

The `config` dict for each view already supports arbitrary keys. The baseline mode will be passed separately from the view key (it applies to any view — Critical Path, Full, 4-Week, Updates).

**Approach:** The baseline mode is a **query parameter** on the API, not part of the view definition config. The service computes the payload with the requested mode, but snapshots always store the `own` baseline (default). Non-own modes trigger a fresh computation.

### 3.5 API: Baseline Mode Parameter

**File:** `backend/api/routers/schedule_views.py`

Add `baseline_mode` query parameter to both endpoints:

```python
@router.get("/preload", response_model=ScheduleViewsPreloadResponse)
async def preload_schedule_views(
    lognos_project_id: str = Header(..., alias="Lognos-ProjectID"),
    baseline_mode: str = "own",
):
    result = await service.preload(
        project_id=lognos_project_id,
        baseline_mode=baseline_mode,
    )
    ...

@router.get("/{view_key}", response_model=ScheduleViewResponse)
async def get_schedule_view(
    view_key: str,
    lognos_project_id: str = Header(..., alias="Lognos-ProjectID"),
    baseline_mode: str = "own",
):
    result = await service.get_view(
        project_id=lognos_project_id,
        view_key=view_key,
        baseline_mode=baseline_mode,
    )
    ...
```

For non-own modes, the service skips snapshot lookup and always calls `build_view_payload` with the mode in config.

### 3.6 Frontend: Types

**File:** `frontend/types/schedule.ts`

```typescript
/** Baseline comparison mode */
export type BaselineMode = 'own' | 'previous_version' | 'database_baseline';
```

Add to `GanttChartData`:

```typescript
export interface GanttChartData {
  ...existing fields...

  /** Active baseline mode */
  baseline_mode?: BaselineMode;

  /** Label describing what the baseline represents (for tooltip/legend) */
  baseline_label?: string;
}
```

### 3.7 Frontend: Baseline Button Dropdown

**File:** `frontend/components/gantt/GanttPanel.tsx`

Replace the simple "Baseline" toggle button with a button + dropdown (same pattern as the "Collapse" dropdown):

```
Before (current):
  [ Baseline ]  ← simple on/off toggle

After (proposed):
  [ Baseline v ]  ← click toggles on/off; hover opens mode selector

  Dropdown:
  ┌─────────────────────┐
  │ ● Own Baseline      │  ← current behavior, default
  │ ○ Previous Version  │  ← compare against version N-1
  │ ○ Database Baseline │  ← compare against is_baseline version
  └─────────────────────┘
```

**State changes:**

```typescript
const [showBaseline, setShowBaseline] = useState<boolean>(true);
const [baselineMode, setBaselineMode] = useState<BaselineMode>('own');
```

When the user selects a different mode:
1. Set `baselineMode` to the new value
2. Set `showBaseline` to `true` (auto-enable)
3. Trigger a re-fetch of the current view with `?baseline_mode=<mode>`

The re-fetch flow depends on how the GanttPanel receives its data. Looking at the existing view-switching pattern (`onSelectView`), the same callback pattern can be extended:

```typescript
interface GanttPanelProps {
  ...existing props...

  /** Callback to request data with a different baseline mode */
  onBaselineModeChange?: (mode: BaselineMode) => void;
}
```

The parent component handles the re-fetch (calls the API with the `baseline_mode` query parameter) and passes updated `data` back to the panel.

### 3.8 Frontend: Legend & Tooltip Updates

The legend currently shows "Baseline". With modes, it should show a more descriptive label:

| Mode | Legend text | Tooltip prefix |
|------|-----------|----------------|
| own | Baseline | Baseline: |
| previous_version | vs. Previous (v260101) | Previous (v260101): |
| database_baseline | vs. Baseline (v250710) | DB Baseline (v250710): |

`GanttChartData.baseline_label` (set by the backend) provides the version-specific label (e.g., "v260101") so the frontend doesn't need to know version details.

---

## 4. Caching Strategy

| Mode | Cached? | Rationale |
|------|---------|-----------|
| own | Yes (snapshot) | Default, stable between imports |
| previous_version | No (fresh compute) | Depends on which version is "previous" — changes after each import |
| database_baseline | Could cache | The baseline version rarely changes, but fresh compute is simpler for V1 |

For V1, only `own` mode uses cached snapshots. Non-own modes bypass the snapshot entirely and always call `build_view_payload()`. This keeps the implementation simple while avoiding stale comparisons.

---

## 5. Implementation Plan

| Step | Layer | Files | Description |
|------|-------|-------|-------------|
| 1 | Repository | `ms_schedule_repository.py` | Add `get_previous_version()`, `get_baseline_version()` |
| 2 | Service | `schedule_view_service.py` | Add `_build_cross_version_baseline()`, integrate baseline_mode into `build_view_payload()`, pass through `preload()`/`get_view()` |
| 3 | API | `schedule_views.py` | Add `baseline_mode` query parameter to both endpoints |
| 4 | Types | `types/schedule.ts` | Add `BaselineMode` type, `baseline_mode` and `baseline_label` to `GanttChartData` |
| 5 | GanttPanel | `GanttPanel.tsx` | Convert Baseline button to dropdown with mode selection, add `onBaselineModeChange` prop |
| 6 | Parent wiring | Component that hosts GanttPanel | Pass `onBaselineModeChange` callback that re-fetches with new mode |
| 7 | Legend/Tooltip | `GanttPanel.tsx`, `GanttChart.tsx` | Use `baseline_label` in legend and tooltip text |

Steps 1-3 are backend. Steps 4-7 are frontend. The backend changes are self-contained and testable independently.

---

## 6. Data Flow

```
User selects "Previous Version" from dropdown
  → GanttPanel calls onBaselineModeChange("previous_version")
  → Parent re-fetches: GET /schedule-views/{view_key}?baseline_mode=previous_version
  → API passes baseline_mode to service
  → Service resolves version N-1 (id=20) for BIO4-24101
  → Service fetches activities from version 20
  → Builds ms_uid → (start, finish) lookup
  → Overlays onto current version's parsed items as baseline_start_dt/baseline_finish_dt
  → Returns payload with has_baseline=true, baseline_mode="previous_version", 
    baseline_label="v260101"
  → Frontend renders ghost bars using the same useBarPositions hook
  → Legend shows "vs. Previous (v260101)"
  → Slippage tooltip shows difference against version 20's dates
```

---

## 7. Edge Cases

| Case | Handling |
|------|----------|
| No previous version exists | `get_previous_version` returns None → `has_baseline = false`, ghost bars hidden, dropdown option grayed out |
| No database baseline exists | `get_baseline_version` returns None → same as above |
| Activity exists in current but not in reference | `baseline_start = null`, no ghost bar for that activity |
| Activity exists in reference but not in current | Ignored (only current activities are rendered) |
| Summary activity baseline | Summaries in the reference version are matched by `ms_uid` like leaf activities |
| Current version IS the baseline | "Database Baseline" would compare against itself → same dates, zero slippage (harmless but pointless; could gray out the option) |
| Current version is the first version | "Previous Version" unavailable → option grayed out |

---

## 8. UX Details

### 8.1 Dropdown Behavior

- **Click** the "Baseline" button text: toggles visibility (on/off), preserving the current mode
- **Hover** over the button: opens the mode dropdown
- The dropdown appears below the button, same style as the Collapse dropdown
- Selected mode has a filled radio indicator; others have empty circles
- When a mode is selected and data loads, baseline turns on automatically

### 8.2 Loading State

When switching modes, show a subtle loading indicator on the Baseline button (e.g., opacity pulse or small spinner) since a new API call is needed. The rest of the Gantt remains interactive.

### 8.3 Button Label

The button text changes based on mode to provide context:

| Mode | Button label |
|------|-------------|
| own | Baseline |
| previous_version | Baseline (Prev) |
| database_baseline | Baseline (DB) |

### 8.4 Availability Indicators

The backend can include metadata in the preload response to let the frontend know which modes are available:

```typescript
export interface GanttChartData {
  ...existing...
  
  /** Available baseline modes for this project (populated on preload) */
  available_baseline_modes?: {
    own: boolean;           // always true if has_baseline
    previous_version: boolean;  // true if a previous version exists
    database_baseline: boolean; // true if a version with is_baseline=true exists
  };
}
```

This lets the frontend gray out unavailable options without making an API call to discover it.

---

## 9. Scope Exclusions

- **Arbitrary version comparison** (pick any version from a list): deferred to future. The three modes cover the most common comparison needs
- **Side-by-side dual Gantt**: Out of scope; this proposal overlays ghost bars on the same chart
- **Baseline mode persistence**: The mode resets to "own" on panel close/reopen. User preference persistence is deferred
- **GanttChart (report view)**: Always uses own baseline. Mode selection is only in GanttPanel

---

## 10. Verification

1. Open BIO4-24101 Gantt panel (current = version 21)
2. Confirm "Own Baseline" shows the existing baseline ghost bars (current behavior)
3. Switch to "Previous Version" → ghost bars show version 20's dates for matching activities
4. Verify slippage tooltip shows difference between v21 and v20 dates
5. Switch to "Database Baseline" → ghost bars show version 0 (baseline) dates
6. Verify activities not present in v0 have no ghost bar
7. Toggle baseline off → ghost bars disappear regardless of mode
8. Toggle back on → ghost bars reappear with the last selected mode
9. Switch to a view with few activities (Critical Path) → baseline mode still works
10. Verify "Previous Version" is unavailable if viewing the oldest version
