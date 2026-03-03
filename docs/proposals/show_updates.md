# Activity Update Indicators in Gantt Panel

**Date:** March 3, 2026
**Status:** Draft
**Author:** Engineering Team

---

## 1. Objective

Display user-reported schedule updates (delays, completions, actual starts) as amber indicator icons directly on the Gantt chart, next to the affected activity bars. Each indicator shows a rich tooltip on hover with the update details, reporter, and date. A future "Show Impact" button in the tooltip will trigger downstream path analysis — the tooltip layout is designed to accommodate it from day one.

---

## 2. Current State

### 2.1 Database (schema: `lognos_schedule`)

**`schedule_update_logs`** stores user-reported updates per activity:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `log_id` | `uuid` | NO | Primary key (auto-generated) |
| `project_id` | `text` | NO | Project identifier (e.g., `BIO4-24101`) |
| `schedule_version_id` | `bigint` | NO | FK to `schedule_versions.id` |
| `activity_id` | `bigint` | NO | FK to `schedule_activities.id` (PK, not `ms_uid`) |
| `update_type` | `text` | NO | One of: `delay`, `completion`, `start` |
| `details` | `text` | NO | Free-text description of the update |
| `reported_value` | `text` | YES | Structured value (date, duration, etc.) |
| `reported_by` | `text` | NO | Email of the reporter |
| `reported_at` | `timestamptz` | NO | When the update was reported |
| `processed` | `boolean` | NO | Whether the update has been processed (default: `false`) |
| `processed_at` | `timestamptz` | YES | When processed |
| `processed_by` | `text` | YES | Who processed it |
| `processing_notes` | `text` | YES | Notes from processing |
| `created_at` | `timestamptz` | NO | Row creation timestamp |
| `updated_at` | `timestamptz` | NO | Row update timestamp |

There is also a `queued_activity_updates` table used by the agent for queued/staged changes. This proposal focuses on `schedule_update_logs` only, as it represents confirmed user-reported updates.

**Existing data** (BIO4-24101):
- 8 update logs across versions 20 and 21
- Update types: `delay` (4), `completion` (3), `start` (1)
- One activity (`Escalera Nivel 1`) has multiple updates (start + delay)
- All updates are currently `processed: true`
- Updates reference `activity_id` (PK), which maps to `ms_uid` via the `schedule_activities` table

**Key relationships:**
- `schedule_update_logs.activity_id` = `schedule_activities.id` (database PK)
- `schedule_activities.ms_uid` is used as `s_item_id` in the Gantt payload (stringified)
- Updates are scoped to a `schedule_version_id`, but may reference activities from older versions whose `ms_uid` persists across versions

### 2.2 Backend

**No existing code** reads from `schedule_update_logs`. The table is only written to by the scheduling agent during conversations. A new repository method and service integration are needed.

**`ScheduleViewService.build_view_payload()`** currently builds `items_payload` and `relationships_payload`. Update indicators need to be added as a third payload section: `activity_updates`.

### 2.3 Frontend

No update-related types or rendering exist in the Gantt components. The feature is entirely new on the frontend side.

### 2.4 Summary of Gaps

| Layer | Gap | Effort |
|-------|-----|--------|
| Database | None - table exists with data | - |
| Repository | No method to fetch update logs by version | Small |
| Service | `build_view_payload()` does not include update data | Small |
| Types (TS) | No `ActivityUpdate` type or update fields on `GanttChartData` | Small |
| GanttPanel | No indicator rendering, no tooltip | Medium |
| GanttChart | No indicator rendering | Small |
| Style Settings | No update indicator settings in `ganttStyleSettings` | Small |

---

## 3. Proposed Implementation

### 3.1 Backend: Repository Method

**File:** `backend/repositories/ms_schedule_repository.py`

Add a method to fetch update logs for a given schedule version, joining to resolve `ms_uid`:

```python
async def get_update_logs_by_version(
    self, version_id: int
) -> list[dict]:
    """Fetch schedule update logs for a version, with ms_uid for frontend mapping."""
    result = (
        self.client.schema(SCHEMA)
        .from_("schedule_update_logs")
        .select(
            "log_id, activity_id, update_type, details, reported_value, "
            "reported_by, reported_at, processed"
        )
        .eq("schedule_version_id", version_id)
        .order("reported_at", desc=True)
        .execute()
    )
    return result.data or []
```

### 3.2 Backend: Service Integration

**File:** `backend/services/schedule_view_service.py`

In `build_view_payload()`, after building `items_payload`, fetch update logs and map them to `s_item_id` (ms_uid):

```python
# Fetch update logs for this version
update_logs = await self.ms_repository.get_update_logs_by_version(schedule_version_id)

# Map activity_id (PK) -> s_item_id (ms_uid) using activity_by_id
activity_updates_payload = []
for log in update_logs:
    activity = activity_by_id.get(log["activity_id"])
    if not activity:
        continue
    ms_uid = str(activity.get("ms_uid") or log["activity_id"])
    # Only include if the activity is in the filtered set
    if int(log["activity_id"]) not in filtered_id_set:
        continue
    activity_updates_payload.append({
        "log_id": log["log_id"],
        "s_item_id": ms_uid,
        "update_type": log["update_type"],
        "details": log["details"],
        "reported_value": log.get("reported_value"),
        "reported_by": log["reported_by"],
        "reported_at": log["reported_at"],
        "processed": log["processed"],
    })
```

Add to the return dict:

```python
return {
    ...existing fields...,
    "activity_updates": activity_updates_payload,
}
```

### 3.3 Frontend Types

**File:** `frontend/types/schedule.ts`

Add new types:

```typescript
/**
 * A user-reported activity update (delay, completion, start)
 */
export interface ActivityUpdate {
  /** Unique log identifier */
  log_id: string;
  /** Activity code (ms_uid as string) — matches ScheduleItem.s_item_id */
  s_item_id: string;
  /** Update type: delay, completion, start */
  update_type: 'delay' | 'completion' | 'start';
  /** Free-text description of the update */
  details: string;
  /** Structured value (date, duration text, etc.) */
  reported_value?: string | null;
  /** Email of the reporter */
  reported_by: string;
  /** ISO timestamp of when the update was reported */
  reported_at: string;
  /** Whether the update has been incorporated into the schedule */
  processed: boolean;
}
```

Add to `GanttChartData`:

```typescript
export interface GanttChartData {
  ...existing fields...

  /** User-reported activity updates for indicator display */
  activity_updates?: ActivityUpdate[];
}
```

### 3.4 Frontend Hook: Update Lookup Map

**File:** `frontend/components/gantt/hooks/useActivityUpdates.ts` (new)

Create a hook that builds a lookup map from `s_item_id` to its updates array, so rendering components can check in O(1) whether an activity has updates:

```typescript
/**
 * useActivityUpdates Hook
 *
 * Builds a lookup map from activity s_item_id to its update logs.
 * Returns the map and a boolean indicating whether any updates exist.
 */

import { useMemo } from 'react';
import { ActivityUpdate } from '@/types/schedule';

export interface ActivityUpdatesMap {
  /** Map from s_item_id to array of updates (most recent first) */
  byActivity: Map<string, ActivityUpdate[]>;
  /** Whether any updates exist */
  hasUpdates: boolean;
}

export function useActivityUpdates(
  updates?: ActivityUpdate[]
): ActivityUpdatesMap {
  return useMemo(() => {
    if (!updates || updates.length === 0) {
      return { byActivity: new Map(), hasUpdates: false };
    }

    const byActivity = new Map<string, ActivityUpdate[]>();
    for (const update of updates) {
      const existing = byActivity.get(update.s_item_id);
      if (existing) {
        existing.push(update);
      } else {
        byActivity.set(update.s_item_id, [update]);
      }
    }

    return { byActivity, hasUpdates: true };
  }, [updates]);
}
```

Export from `frontend/components/gantt/hooks/index.ts`.

### 3.5 Gantt Style Settings

**File:** `frontend/components/gantt/ganttStyleSettings.ts`

Add an `updates` section alongside the existing `baseline` section:

```typescript
export interface GanttUpdateIndicatorStyle {
  /** Indicator circle diameter in px */
  size: number;
  /** Background color for the indicator circle */
  bg: string;
  /** Text color for the "!" symbol */
  textColor: string;
  /** Font size for the "!" symbol */
  fontSize: string;
  /** Font weight for the "!" */
  fontWeight: string;
  /** Horizontal offset from the end of the bar, in px */
  offsetRight: number;

  /** Tooltip max width */
  tooltipMaxWidth: number;

  /** Type badge colors: bg, text for each update_type */
  typeBadge: {
    delay: { bg: string; text: string };
    completion: { bg: string; text: string };
    start: { bg: string; text: string };
  };

  /** Legend swatch color */
  legendBg: string;
  legendTextColor: string;
}

export interface GanttStyleSettings {
  baseline: GanttBaselineStyle;
  updates: GanttUpdateIndicatorStyle;
}
```

Default values:

```typescript
const ganttStyleSettings: Readonly<GanttStyleSettings> = Object.freeze({
  baseline: { ...existing... },
  updates: {
    size: 16,
    bg: 'rgb(217, 119, 6)',          // amber-600
    textColor: 'rgb(255, 255, 255)', // white
    fontSize: '10px',
    fontWeight: '700',
    offsetRight: -20,

    tooltipMaxWidth: 320,

    typeBadge: {
      delay: { bg: 'rgba(239, 68, 68, 0.15)', text: 'rgb(248, 113, 113)' },       // red
      completion: { bg: 'rgba(16, 185, 129, 0.15)', text: 'rgb(52, 211, 153)' },   // emerald
      start: { bg: 'rgba(59, 130, 246, 0.15)', text: 'rgb(96, 165, 250)' },        // blue
    },

    legendBg: 'rgb(217, 119, 6)',
    legendTextColor: 'rgb(255, 255, 255)',
  },
});
```

### 3.6 Frontend Rendering: Update Indicator in GanttPanel

**File:** `frontend/components/gantt/GanttPanel.tsx`

#### 3.6.1 Indicator Icon

Render an amber circular `(!)` indicator to the right of the activity bar when that activity has one or more updates. The indicator is positioned **after** the bar end, offset by `ganttStyleSettings.updates.offsetRight`:

```
Activity Row:
┌────────────────────────────────────────────────────┐
│  [====== current bar ======] (!)                   │
│     [--- baseline ghost ---]                       │
└────────────────────────────────────────────────────────┘
                                ^
                           amber circle with "!"
```

For milestones, the indicator is placed to the right of the diamond.

Implementation in `HierarchicalRow`:

```tsx
const us = ganttStyleSettings.updates;

{/* Update indicator */}
{activityUpdates && activityUpdates.length > 0 && (
  <div className="group/update absolute" style={{
    left: `${item.startPercentage + item.widthPercentage}%`,
    top: '50%',
    transform: 'translateY(-50%)',
    marginLeft: `${us.offsetRight < 0 ? 4 : us.offsetRight}px`,
  }}>
    {/* Amber circle */}
    <div
      className="rounded-full flex items-center justify-center cursor-default"
      style={{
        width: `${us.size}px`,
        height: `${us.size}px`,
        backgroundColor: us.bg,
        color: us.textColor,
        fontSize: us.fontSize,
        fontWeight: us.fontWeight,
      }}
    >
      !
    </div>

    {/* Hover tooltip */}
    <UpdateTooltip updates={activityUpdates} />
  </div>
)}
```

#### 3.6.2 Tooltip Component

A custom hover tooltip rendered as an absolutely-positioned div appearing on hover of the indicator. This is a sub-component rather than a native `title` attribute because:
- Multiple updates need structured layout (list)
- Type badges need color coding
- The "Show Impact" button needs to be a clickable element

```
┌─────────────────────────────────────────┐
│  2 Updates                              │
│─────────────────────────────────────────│
│  DELAY                        Feb 18    │
│  Columna AS16 fuera de especi...        │
│  Reported by: sliboa@bio4.com.ar        │
│  [Show Impact]  (disabled/mock)         │
│─────────────────────────────────────────│
│  START                        Jan 15    │
│  La actividad comenzó el 13/01...       │
│  Reported by: sliboa@bio4.com.ar        │
│  [Show Impact]  (disabled/mock)         │
└─────────────────────────────────────────┘
```

**Tooltip design principles:**
- **Positioned above or below** the indicator depending on available space (prefer above)
- **Max width** from settings (`tooltipMaxWidth: 320px`)
- **Max height**: `320px` with overflow scroll for activities with many updates
- **Details text**: Truncated to 3 lines with `line-clamp-3`
- **Type badge**: Colored pill per `update_type` (delay=red, completion=green, start=blue)
- **Date**: Formatted as `MMM dd` (short) in the header, full date in expanded view
- **Reporter**: Email displayed below details
- **Show Impact button**: Present but disabled (grayed out with "Coming soon" tooltip). This button will eventually trigger downstream path impact analysis

```tsx
interface UpdateTooltipProps {
  updates: ActivityUpdate[];
}

function UpdateTooltip({ updates }: UpdateTooltipProps) {
  const us = ganttStyleSettings.updates;

  return (
    <div
      className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 opacity-0 invisible
                 group-hover/update:opacity-100 group-hover/update:visible
                 transition-all duration-150 z-50 pointer-events-none
                 group-hover/update:pointer-events-auto"
      style={{ width: `${us.tooltipMaxWidth}px` }}
    >
      <div className="bg-[#1a1f2e] border border-dark-600 rounded-lg shadow-xl p-3 text-xs">
        {/* Header */}
        <div className="text-gray-300 font-medium mb-2">
          {updates.length} Update{updates.length !== 1 ? 's' : ''}
        </div>

        {/* Update entries */}
        <div className="space-y-2 max-h-[240px] overflow-y-auto">
          {updates.map((update) => (
            <div key={update.log_id} className="border-t border-dark-600 pt-2">
              {/* Type badge + date */}
              <div className="flex items-center justify-between mb-1">
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
                  style={{
                    backgroundColor: us.typeBadge[update.update_type].bg,
                    color: us.typeBadge[update.update_type].text,
                  }}
                >
                  {update.update_type}
                </span>
                <span className="text-gray-500">
                  {format(parseISO(update.reported_at), 'MMM dd, yyyy')}
                </span>
              </div>

              {/* Details */}
              <p className="text-gray-300 line-clamp-3 mb-1">
                {update.details}
              </p>

              {/* Reported value (if present) */}
              {update.reported_value && (
                <p className="text-gray-400 text-[10px] mb-1">
                  Value: {update.reported_value}
                </p>
              )}

              {/* Reporter */}
              <p className="text-gray-500 text-[10px]">
                {update.reported_by}
              </p>

              {/* Show Impact button (mock/disabled) */}
              <button
                type="button"
                disabled
                className="mt-1.5 px-2 py-0.5 rounded border border-dark-500 text-[10px]
                           text-gray-500 cursor-not-allowed opacity-50"
                title="Coming soon: Analyze downstream impact of this update"
              >
                Show Impact
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

#### 3.6.3 Toggle Control

Add an "Updates" toggle in the toolbar row (alongside baseline and links toggles):

```tsx
{updatesMap.hasUpdates && (
  <button
    type="button"
    onClick={() => setShowUpdates((prev) => !prev)}
    className={`h-[26px] px-2 rounded-full border flex items-center gap-1 text-xs transition-colors ${
      showUpdates
        ? 'border-amber-500 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20'
        : 'border-dark-600 text-gray-500 hover:bg-dark-700/60'
    }`}
    title={showUpdates ? 'Hide updates' : 'Show updates'}
  >
    Updates
  </button>
)}
```

#### 3.6.4 Legend Entry

Add to the Legend component:

```tsx
{hasUpdates && showUpdates && (
  <div className="flex items-center gap-1">
    <div
      className="w-3 h-3 rounded-full flex items-center justify-center text-[8px] font-bold"
      style={{
        backgroundColor: us.legendBg,
        color: us.legendTextColor,
      }}
    >
      !
    </div>
    <span>Update</span>
  </div>
)}
```

#### 3.6.5 Data Flow in HierarchicalRow

Pass the updates map to `HierarchicalRow` so it can look up updates per activity:

```tsx
// In GanttPanel component body:
const updatesMap = useActivityUpdates(data.activity_updates);

// In HierarchicalRow render:
const activityUpdates = showUpdates
  ? updatesMap.byActivity.get(item.s_item_id)
  : undefined;
```

### 3.7 Frontend Rendering: Update Indicator in GanttChart

**File:** `frontend/components/gantt/GanttChart.tsx`

Apply the same indicator pattern in `GanttRow`, simplified (always visible, no toggle). The tooltip uses the same `UpdateTooltip` component (extract to a shared file if needed).

### 3.8 Snapshot Staleness

**File:** `backend/services/schedule_view_service.py`

Since update logs can be added at any time (outside of schedule imports), the cached snapshot payload could become stale when a new update is logged. Two approaches:

**Option A (recommended for now):** Include `activity_updates` outside the cached snapshot. Fetch them fresh in `preload()` and `get_view()` and merge into the payload before returning. This avoids snapshot invalidation for every new update.

```python
# In preload() and get_view(), after fetching snapshot:
payload = dict(snapshot.get("payload") or {})
update_logs = await self.ms_repository.get_update_logs_by_version(schedule_version_id)
payload["activity_updates"] = self._build_updates_payload(
    update_logs, activity_by_id={}, filtered_id_set=set()
)
```

However, `activity_by_id` and `filtered_id_set` are not available outside `build_view_payload()`. A simpler approach: always include updates in `build_view_payload()` (they are re-fetched each time), and in `preload()`/`get_view()`, fetch updates separately and inject them:

```python
# In preload(), after getting default_payload:
if default_payload:
    update_logs = await self.ms_repository.get_update_logs_by_version(schedule_version_id)
    default_payload = dict(default_payload)
    default_payload["activity_updates"] = self._map_update_logs(
        update_logs, schedule_version_id
    )
```

**Option B (future):** Add a `last_update_at` column check that compares the latest `schedule_update_logs.reported_at` against `snapshot.computed_at`, refreshing if updates are newer.

For this implementation, **Option A** is simplest and ensures updates are always fresh without complex cache invalidation.

---

## 4. Implementation Plan

| Step | Layer | Files | Description |
|------|-------|-------|-------------|
| 1 | Repository | `ms_schedule_repository.py` | Add `get_update_logs_by_version()` method |
| 2 | Service | `schedule_view_service.py` | Integrate update logs into `build_view_payload()` return, and fresh-fetch in `preload()` / `get_view()` |
| 3 | Types | `types/schedule.ts` | Add `ActivityUpdate` interface and `activity_updates` to `GanttChartData` |
| 4 | Style Settings | `ganttStyleSettings.ts` | Add `updates` section with indicator and tooltip styles |
| 5 | Hook | `hooks/useActivityUpdates.ts` | New hook for update lookup map |
| 6 | Hook | `hooks/index.ts` | Export new hook |
| 7 | GanttPanel | `GanttPanel.tsx` | Add indicator icon, `UpdateTooltip` sub-component, toggle, legend, wire up `useActivityUpdates` |
| 8 | GanttChart | `GanttChart.tsx` | Add indicator icon and tooltip (always visible) |

Steps 1-3 form the backend+types layer and can be verified independently. Steps 4-6 are frontend infrastructure. Steps 7-8 are the rendering layer.

---

## 5. Visual Design

### 5.1 Indicator Layout

```
Activity Row (36px height):
┌──────────────────────────────────────────────────┐
│                                                  │
│   [====== current bar ======] (!)                │
│      [--- baseline ghost ---]                    │
│                                                  │
└──────────────────────────────────────────────────┘
                                 ^
                            amber circle
                            16px diameter
                            white "!" centered
```

For activities with multiple updates, a single indicator is shown with a count badge (e.g., the tooltip header reads "2 Updates").

### 5.2 Indicator Defaults (from `ganttStyleSettings.updates`)

| Property | Default | Description |
|----------|---------|-------------|
| `size` | `16` | Circle diameter in px |
| `bg` | `rgb(217,119,6)` | Amber-600 background |
| `textColor` | `rgb(255,255,255)` | White text |
| `fontSize` | `'10px'` | Font size for "!" |
| `fontWeight` | `'700'` | Bold |
| `offsetRight` | `-20` | Gap from bar end |
| `tooltipMaxWidth` | `320` | Max tooltip width in px |

### 5.3 Tooltip Layout

```
┌──────────────────────────────────────────────┐
│  2 Updates                                    │
│──────────────────────────────────────────────│
│  DELAY                           Feb 18, 2026│
│  Columna AS16 fuera de especifica-            │
│  cion o mal perforada, viga corta...          │
│  Value: Rework required in field              │
│  sliboa@bio4.com.ar                           │
│  [ Show Impact ]  (disabled)                  │
│──────────────────────────────────────────────│
│  START                           Jan 15, 2026│
│  La actividad comenzo el 13/01/20-            │
│  26 con relevamientos de las patas...         │
│  Value: 2026-01-13                            │
│  sliboa@bio4.com.ar                           │
│  [ Show Impact ]  (disabled)                  │
└──────────────────────────────────────────────┘
```

### 5.4 Type Badge Colors

| Type | Badge BG | Badge Text | Semantics |
|------|----------|------------|-----------|
| `delay` | `rgba(239,68,68,0.15)` | `rgb(248,113,113)` | Red — problem/delay |
| `completion` | `rgba(16,185,129,0.15)` | `rgb(52,211,153)` | Green — done |
| `start` | `rgba(59,130,246,0.15)` | `rgb(96,165,250)` | Blue — started |

### 5.5 "Show Impact" Button — Future Design

The disabled button in the tooltip is a placeholder for a future feature that will:

1. Send the update context (activity, update_type, details) to the scheduling agent
2. The agent runs a downstream path analysis (which successors are affected, by how much)
3. Results are rendered as highlighted paths on the Gantt (affected activities glow, arrows thicken)
4. A summary card shows total impact (delay propagation, new critical path, etc.)

The button is included now so that:
- The tooltip layout already accounts for it (no re-design needed later)
- Users see it as "Coming soon", building awareness
- The click handler stub is ready for wiring

When enabled, the button text will change to "Show Impact" (active) and trigger an agent tool call.

---

## 6. Edge Cases

| Case | Handling |
|------|----------|
| Activity has no updates | No indicator rendered |
| Activity has multiple updates | Single indicator; tooltip lists all updates (most recent first) |
| Update references activity not in current filtered view | Update excluded from payload (filtered by `filtered_id_set`) |
| Update from older version references activity still in current version | Include if `activity_id` matches (PK is stable across version imports of the same activity) |
| Summary activity has update | Indicator shown on summary bar (updates can reference summary-level activities) |
| Milestone has update | Indicator positioned to the right of the diamond |
| Toggle off | Indicators hidden; tooltips inaccessible |
| No updates exist (`activity_updates` is empty or absent) | Toggle button hidden |
| Very long details text | `line-clamp-3` in tooltip, full text accessible via future detail view |
| Updates fetched fresh vs cached | Updates are injected fresh on every `preload()`/`get_view()` call (not part of snapshot cache) |

---

## 7. Cross-Version Update Visibility

Updates are stored against a specific `schedule_version_id`. When a new version is imported:

- Updates from the previous version will **not** appear on the new version by default (they target different `schedule_version_id`)
- This is correct behavior: once a new version is imported, old updates are historical
- Future enhancement: allow "carrying forward" unprocessed updates to new versions based on `ms_uid` matching

For now, only updates matching the **current** `schedule_version_id` are shown.

---

## 8. Scope Exclusions

- **Show Impact analysis**: Deferred to future implementation. Only the disabled button placeholder is included.
- **Update creation from Gantt**: Users report updates via the chat agent, not from the Gantt UI.
- **Update editing/deletion**: Out of scope; managed via agent conversations or admin tools.
- **Notification for new updates**: Real-time push of new updates to the Gantt is deferred.
- **`queued_activity_updates` table**: This table is for staged agent-generated updates and is not shown on the Gantt.
- **P6 schedule updates**: This proposal covers MS Project schedules only (consistent with the existing data model).

---

## 9. Verification

After implementation, verify with project BIO4-24101 (which has 8 update logs):

1. Open the project Gantt panel and confirm the "Updates" toggle appears.
2. Confirm amber `(!)` indicators appear next to activities that have updates.
3. Hover over an indicator and confirm the tooltip shows update details, type badge, reporter, and date.
4. Confirm the "Show Impact" button is visible but disabled.
5. Confirm activities without updates show no indicator.
6. Confirm the legend shows the "Update" entry when toggle is on.
7. Switch views (critical_path, full_schedule) and confirm indicators appear correctly in each.
8. Toggle updates off and confirm indicators disappear.
9. Verify activity "Escalera Nivel 1" (ms_uid 1511) shows 2 updates (start + delay) in its tooltip (note: these are from version 20, so they will only show when viewing version 20's data).
10. Verify activity "Nivel 1" (ms_uid 1510) shows 1 update (delay from version 21) in the current view.
