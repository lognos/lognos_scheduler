# Baseline Visualization in Gantt Panel

**Date:** March 3, 2026
**Status:** Draft
**Author:** Engineering Team

---

## 1. Objective

Add baseline bar visualization to the Gantt panel for MS Project schedules, enabling users to compare current schedule dates against baseline dates directly in the UI. This is a core scheduling feature that gives immediate visual feedback on schedule slippage.

---

## 2. Current State

### 2.1 Database (schema: `lognos_schedule`)

**`schedule_activities`** already stores baseline fields per activity row:

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `baseline_start` | `timestamptz` | YES | Baseline start date |
| `baseline_finish` | `timestamptz` | YES | Baseline finish date |
| `baseline_duration_d` | `numeric` | YES | Baseline duration in days |

**`schedule_versions`** has a `is_baseline` boolean flag to identify which version is the project baseline.

Data availability (verified in DB):
- Baseline data is stored **inline** on each activity row of the current version (not as a separate version join). The MS Project XML import populates `baseline_start`/`baseline_finish` directly from the `<Baseline>` element of each task.
- Coverage is high: on the current version (v260129) of example project BIO4-24101, 641 of 663 activities (96.7%) have `baseline_start` and `baseline_finish` populated.
- Activities added after the baseline was set (22 of 663) have `NULL` baseline fields, which is correct behavior.
- A separate version row with `is_baseline = true` also exists, containing the full baseline snapshot (714 activities, 100% baseline coverage).

### 2.2 Backend

**`MSScheduleRepository`** (`backend/repositories/ms_schedule_repository.py`):
- Queries `schedule_activities` with `SELECT *`, so `baseline_start`, `baseline_finish`, and `baseline_duration_d` are already returned in every activity dict.
- No additional repository changes needed to fetch the data.

**`ScheduleViewService.build_view_payload()`** (`backend/services/schedule_view_service.py`):
- Parses each activity into a `parsed` dict but **does not** extract `baseline_start`, `baseline_finish`, or `baseline_duration_d`.
- The `items_payload` dict sent to the frontend contains no baseline fields.
- This is the primary backend gap.

**Agent tools** (`backend/tools/ms/queries.py`):
- The `get_activity_detail` tool already reads and displays baseline info in text form for agent conversations.
- No tool changes are needed for the visualization feature.

### 2.3 Frontend Types

**`ScheduleItem`** (`frontend/types/schedule.ts`):
- Does **not** include `baseline_start`, `baseline_finish`, or `baseline_duration_d` fields.
- No baseline-related properties exist anywhere in the type system.

**`PositionedItem`** (`frontend/components/gantt/hooks/types.ts`):
- Extends `ScheduleItem` with `startPercentage`, `widthPercentage`, `duration` for bar positioning.
- No baseline position fields exist.

### 2.4 Frontend Gantt Rendering

**`GanttPanel.tsx`** (775 lines, primary interactive Gantt):
- `HierarchicalRow` renders a single bar per activity (current dates).
- Supports milestone diamonds, summary bars, status coloring, critical path highlighting.
- No baseline bar or ghost bar rendering exists.
- Legend component has no baseline entry.
- Tooltip (`getBarTooltip`) shows current dates only.

**`GanttChart.tsx`** (240 lines, standalone report Gantt):
- Simpler version, same pattern: single bar per activity, no baseline support.
- Should also receive baseline support for consistency.

**`useBarPositions.ts`** hook:
- Calculates `startPercentage` and `widthPercentage` from `start`/`finish` dates.
- Does not compute any baseline positions.

### 2.5 Summary of Gaps

| Layer | Gap | Effort |
|-------|-----|--------|
| Database | None - baseline columns exist and are populated | - |
| Repository | None - `SELECT *` already returns baseline fields | - |
| Service | `build_view_payload()` does not include baseline fields in item payloads | Small |
| Types (TS) | `ScheduleItem` missing baseline fields | Small |
| Hooks | `useBarPositions` does not compute baseline bar positions | Small |
| GanttPanel | No baseline bar rendering in `HierarchicalRow` | Medium |
| GanttChart | No baseline bar rendering in `GanttRow` | Small |
| Legend | No baseline legend entry | Small |
| Tooltip | No baseline dates in tooltip | Small |
| Style Settings | No centralized style settings for Gantt visuals | Medium |

---

## 3. Proposed Implementation

### 3.1 Backend: Include Baseline Fields in Payload

**File:** `backend/services/schedule_view_service.py`

In `build_view_payload()`, within the activity parsing loop, extract baseline dates:

```python
# In the parsed[] construction loop:
parsed.append({
    ...existing fields...,
    "baseline_start_dt": self._normalize_datetime(a.get("baseline_start")),
    "baseline_finish_dt": self._normalize_datetime(a.get("baseline_finish")),
    "baseline_duration_d": float(a.get("baseline_duration_d") or 0) if a.get("baseline_duration_d") is not None else None,
})
```

In the `items_payload` construction:

```python
# Add to item_payload dict:
bl_start_dt = item.get("baseline_start_dt")
bl_finish_dt = item.get("baseline_finish_dt")

item_payload = {
    ...existing fields...,
    "baseline_start": bl_start_dt.date().isoformat() if bl_start_dt else None,
    "baseline_finish": bl_finish_dt.date().isoformat() if bl_finish_dt else None,
    "baseline_duration_d": item.get("baseline_duration_d"),
}
```

Also include a top-level flag in the payload indicating whether baseline data is available:

```python
has_baseline = any(
    item.get("baseline_start_dt") is not None
    for item in filtered_items
    if not item["is_summary"]
)

return {
    ...existing return dict...,
    "has_baseline": has_baseline,
}
```

### 3.2 Frontend Types: Add Baseline Fields

**File:** `frontend/types/schedule.ts`

Add to `ScheduleItem`:

```typescript
export interface ScheduleItem {
  ...existing fields...

  /** Baseline start date (ISO format), null if no baseline set */
  baseline_start?: string | null;
  /** Baseline finish date (ISO format), null if no baseline set */
  baseline_finish?: string | null;
  /** Baseline duration in working days, null if no baseline set */
  baseline_duration_d?: number | null;
}
```

Add to `GanttChartData`:

```typescript
export interface GanttChartData {
  ...existing fields...

  /** Whether baseline data is available for this schedule version */
  has_baseline?: boolean;
}
```

### 3.3 Frontend Hooks: Compute Baseline Bar Positions

**File:** `frontend/components/gantt/hooks/types.ts`

Add baseline position fields to `PositionedItem`:

```typescript
export interface PositionedItem extends ScheduleItem {
  ...existing fields...

  /** Baseline bar start as percentage (0-100), undefined if no baseline */
  baselineStartPercentage?: number;
  /** Baseline bar width as percentage, undefined if no baseline */
  baselineWidthPercentage?: number;
}
```

**File:** `frontend/components/gantt/hooks/useBarPositions.ts`

In the mapping function, compute baseline positions alongside current positions:

```typescript
// After computing startPercentage and widthPercentage:
let baselineStartPercentage: number | undefined;
let baselineWidthPercentage: number | undefined;

if (item.baseline_start && item.baseline_finish) {
  const blStart = parseISO(item.baseline_start);
  const blFinish = parseISO(item.baseline_finish);
  const blDaysFromStart = differenceInDays(blStart, timelineStartDate);
  const blDuration = differenceInDays(blFinish, blStart) + 1;
  baselineStartPercentage = Math.max(0, (blDaysFromStart / totalDays) * 100);
  baselineWidthPercentage = Math.max(1, (blDuration / totalDays) * 100);
}

return {
  ...item,
  startPercentage,
  widthPercentage,
  duration,
  baselineStartPercentage,
  baselineWidthPercentage,
};
```

### 3.4 Gantt Style Settings

**New file:** `frontend/components/gantt/ganttStyleSettings.ts`

Introduce a centralized **style settings object** that parametrizes all visual properties of the Gantt chart. For this implementation, populate it with baseline-related settings only. Future work will migrate existing hardcoded visual constants (bar colors, row height, milestone size, etc.) into this same structure.

Design principles:
- **Single source of truth** for any visual constant used by Gantt components and hooks.
- **Flat-ish structure** grouped by concern (baseline, row, bar, milestone, etc.).
- **Default export** of a frozen settings object; components import and read from it.
- **No runtime mutation** - settings are compile-time constants (future: could be overridden via user preferences or theme context).

```typescript
/**
 * Gantt Style Settings
 *
 * Centralized visual configuration for Gantt chart rendering.
 * All layout percentages, colors, sizes, and opacities live here.
 *
 * Currently scoped to baseline visualization settings.
 * Future iterations will migrate row, bar, milestone, summary,
 * and relationship arrow defaults here as well.
 */

export interface GanttBaselineStyle {
  /** Vertical offset of baseline bar within the row, as CSS % string */
  barTopOffset: string;
  /** Height of baseline bar within the row, as CSS % string */
  barHeight: string;
  /** Minimum width in px for very short baseline bars */
  barMinWidth: number;
  /** Background color (Tailwind or CSS) */
  barBg: string;
  /** Border color (Tailwind or CSS) */
  barBorderColor: string;
  /** Border style: 'dashed' | 'solid' | 'dotted' */
  barBorderStyle: string;
  /** Opacity (0-1) for the baseline bar */
  barOpacity: number;

  /** Milestone diamond size in px */
  milestoneSize: number;
  /** Vertical offset for the baseline milestone, as CSS % string */
  milestoneTopOffset: string;
  /** Milestone border color */
  milestoneBorderColor: string;
  /** Milestone fill (use 'transparent' for hollow) */
  milestoneBg: string;

  /** Legend swatch border color */
  legendBorderColor: string;
  /** Legend swatch background */
  legendBg: string;
}

export interface GanttStyleSettings {
  baseline: GanttBaselineStyle;
  // Future sections:
  // row: GanttRowStyle;
  // bar: GanttBarStyle;
  // milestone: GanttMilestoneStyle;
  // summary: GanttSummaryStyle;
  // relationships: GanttRelationshipStyle;
}

const ganttStyleSettings: Readonly<GanttStyleSettings> = Object.freeze({
  baseline: {
    barTopOffset: '60%',
    barHeight: '30%',
    barMinWidth: 8,
    barBg: 'rgba(55, 65, 81, 0.30)',       // gray-700/30
    barBorderColor: 'rgb(107, 114, 128)',   // gray-500
    barBorderStyle: 'dashed',
    barOpacity: 0.5,

    milestoneSize: 8,
    milestoneTopOffset: '65%',
    milestoneBorderColor: 'rgb(107, 114, 128)',
    milestoneBg: 'transparent',

    legendBorderColor: 'rgb(107, 114, 128)',
    legendBg: 'rgba(55, 65, 81, 0.30)',
  },
});

export default ganttStyleSettings;
```

All Gantt components (`GanttPanel.tsx`, `GanttChart.tsx`) and sub-components (`HierarchicalRow`, `GanttRow`, `Legend`) import this settings object instead of having hardcoded color/layout values.

### 3.5 Frontend Rendering: Baseline Bars in GanttPanel

**File:** `frontend/components/gantt/GanttPanel.tsx`

#### 3.5.1 HierarchicalRow - Baseline Ghost Bar

Render a semi-transparent baseline bar **below** the current schedule bar. Visual properties are read from `ganttStyleSettings.baseline`:

```
Visual layout per row (h-7 container):
  ┌─────────────────────────────────────────────┐
  │   [====== current bar ======]                │  top: 1px, height ~45%
  │      [--- baseline ghost bar ---]            │  top: 60%, height: 30%  (from settings)
  └─────────────────────────────────────────────────┘
```

For milestones, render the baseline as a smaller, hollow diamond offset below.

For summary bars, render the baseline as a thin line below the summary bar.

Implementation approach in `HierarchicalRow`:

```tsx
import ganttStyleSettings from './ganttStyleSettings';

const bs = ganttStyleSettings.baseline;

{/* Baseline bar (ghost) - rendered BEHIND current bar */}
{showBaseline && item.baselineStartPercentage !== undefined && item.baselineWidthPercentage !== undefined && !isMilestone && (
  <div
    className="absolute rounded"
    style={{
      left: `${item.baselineStartPercentage}%`,
      width: `${item.baselineWidthPercentage}%`,
      top: bs.barTopOffset,
      height: bs.barHeight,
      minWidth: `${bs.barMinWidth}px`,
      backgroundColor: bs.barBg,
      borderWidth: '1px',
      borderStyle: bs.barBorderStyle,
      borderColor: bs.barBorderColor,
      opacity: bs.barOpacity,
    }}
    title={`Baseline: ${format(parseISO(item.baseline_start!), 'MMM dd, yyyy')} - ${format(parseISO(item.baseline_finish!), 'MMM dd, yyyy')}`}
  />
)}

{/* Baseline milestone (hollow diamond) */}
{showBaseline && item.baselineStartPercentage !== undefined && isMilestone && (
  <div
    className="absolute -translate-x-1/2 -translate-y-1/2 rotate-45"
    style={{
      left: `${item.baselineStartPercentage}%`,
      top: bs.milestoneTopOffset,
      width: `${bs.milestoneSize}px`,
      height: `${bs.milestoneSize}px`,
      borderWidth: '1px',
      borderStyle: bs.barBorderStyle,
      borderColor: bs.milestoneBorderColor,
      backgroundColor: bs.milestoneBg,
    }}
    title={`Baseline: ${format(parseISO(item.baseline_start!), 'MMM dd, yyyy')}`}
  />
)}
```

#### 3.5.2 Toggle Control

Add a baseline visibility toggle in the toolbar row (alongside the existing links toggle):

```tsx
{data.has_baseline && (
  <button
    type="button"
    onClick={() => setShowBaseline((prev) => !prev)}
    className={`h-[26px] px-2 rounded-full border flex items-center gap-1 text-xs transition-colors ${
      showBaseline
        ? 'border-gray-400 text-gray-200 bg-gray-500/10 hover:bg-gray-500/20'
        : 'border-dark-600 text-gray-500 hover:bg-dark-700/60'
    }`}
    title={showBaseline ? 'Hide baseline' : 'Show baseline'}
  >
    Baseline
  </button>
)}
```

#### 3.5.3 Legend Entry

Add to the `Legend` component, using settings for the swatch:

```tsx
import ganttStyleSettings from './ganttStyleSettings';

const bs = ganttStyleSettings.baseline;

{hasBaseline && showBaseline && (
  <div className="flex items-center gap-1">
    <div
      className="w-3 h-3 rounded"
      style={{
        backgroundColor: bs.legendBg,
        borderWidth: '1px',
        borderStyle: bs.barBorderStyle,
        borderColor: bs.legendBorderColor,
      }}
    />
    <span>Baseline</span>
  </div>
)}
```

#### 3.5.4 Enhanced Tooltip

Update `getBarTooltip()` to include baseline comparison when available:

```typescript
function getBarTooltip(item: PositionedItem, isSummary: boolean): string {
  // ...existing tooltip content...

  // Append baseline section if available
  if (item.baseline_start && item.baseline_finish) {
    const blStart = format(parseISO(item.baseline_start), 'MMM dd, yyyy');
    const blFinish = format(parseISO(item.baseline_finish), 'MMM dd, yyyy');

    const currentFinish = parseISO(item.finish);
    const baselineFinish = parseISO(item.baseline_finish);
    const slipDays = differenceInDays(currentFinish, baselineFinish);

    tooltip += `\nBaseline: ${blStart} - ${blFinish}`;
    if (slipDays !== 0) {
      tooltip += `\nSlippage: ${slipDays > 0 ? '+' : ''}${slipDays} days`;
    }
  }

  return tooltip;
}
```

### 3.6 Frontend Rendering: Baseline in GanttChart (Report View)

**File:** `frontend/components/gantt/GanttChart.tsx`

Apply the same pattern in `GanttRow` but simplified (no toggle; baseline always shown if present since it's a static report). All visual values read from `ganttStyleSettings.baseline`.

### 3.7 Timeline Expansion

**File:** `frontend/components/gantt/hooks/useTimeline.ts`

The `useTimeline` hook computes the timeline date range from `project_start`/`project_finish` and activity dates. If baseline bars extend earlier or later than the current schedule, the timeline must expand to include them.

In `useTimeline`, extend the min/max date calculation:

```typescript
// When computing date range, also consider baseline dates
for (const item of items) {
  if (item.baseline_start) {
    const blStart = parseISO(item.baseline_start);
    if (blStart < minDate) minDate = blStart;
  }
  if (item.baseline_finish) {
    const blFinish = parseISO(item.baseline_finish);
    if (blFinish > maxDate) maxDate = blFinish;
  }
}
```

---

## 4. Implementation Plan

| Step | Layer | Files | Description |
|------|-------|-------|-------------|
| 1 | Backend | `schedule_view_service.py` | Add baseline fields to `build_view_payload()` item construction and top-level `has_baseline` flag |
| 2 | Frontend Types | `types/schedule.ts`, `hooks/types.ts` | Add `baseline_start`, `baseline_finish`, `baseline_duration_d` to `ScheduleItem`; add `baselineStartPercentage`, `baselineWidthPercentage` to `PositionedItem`; add `has_baseline` to `GanttChartData` |
| 3 | Frontend Settings | `gantt/ganttStyleSettings.ts` | Create centralized style settings with baseline section |
| 4 | Frontend Hook | `hooks/useBarPositions.ts` | Compute baseline bar positions alongside current positions |
| 5 | Frontend Hook | `hooks/useTimeline.ts` | Extend timeline date range to account for baseline dates |
| 6 | Frontend UI | `GanttPanel.tsx` | Add baseline ghost bars in `HierarchicalRow` (reading from settings), toggle button, legend entry, enhanced tooltip |
| 7 | Frontend UI | `GanttChart.tsx` | Add baseline ghost bars in `GanttRow` (reading from settings), legend entry, enhanced tooltip |

Steps 1-2 can be done first and verified independently (baseline data appears in API response). Step 3 is prerequisite for steps 6-7. Steps 4-5 are independent hook work.

---

## 5. Visual Design

### 5.1 Bar Layout

All layout values below are the **defaults** defined in `ganttStyleSettings.baseline`. They can be adjusted in a single place without touching component code.

```
Activity Row (36px height):
┌────────────────────────────────────────────────────────┐
│                                                        │
│       ┌══════════ Current Bar ══════════┐              │  ← top: 2px, h: ~45%
│       │  12d / 18d                      │              │
│       └═════════════════════════════════┘              │
│          ┌╌╌╌╌╌╌╌╌╌ Baseline ╌╌╌╌╌╌╌╌╌┐             │  ← top: 60%, h: 30%  (settings.barTopOffset / barHeight)
│          └╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘             │
└────────────────────────────────────────────────────────┘

Milestone Row:
┌────────────────────────────────────────────────────────┐
│                ◆  Current (solid, 12px)                │
│                 ◇  Baseline (hollow/dashed, 8px)       │  ← settings.milestoneSize / milestoneTopOffset
└────────────────────────────────────────────────────────┘
```

### 5.2 Default Values (from `ganttStyleSettings.baseline`)

| Property | Default | Description |
|----------|---------|-------------|
| `barTopOffset` | `'60%'` | Vertical position of baseline bar within row |
| `barHeight` | `'30%'` | Height of baseline bar within row |
| `barMinWidth` | `8` | Minimum pixel width for short bars |
| `barBg` | `rgba(55,65,81,0.30)` | gray-700 at 30% opacity |
| `barBorderColor` | `rgb(107,114,128)` | gray-500 |
| `barBorderStyle` | `'dashed'` | Dashed border for contrast |
| `barOpacity` | `0.5` | Overall bar opacity |
| `milestoneSize` | `8` | Diamond size in px |
| `milestoneTopOffset` | `'65%'` | Vertical position of baseline diamond |
| `milestoneBorderColor` | `rgb(107,114,128)` | gray-500 |
| `milestoneBg` | `'transparent'` | Hollow diamond |
| `legendBorderColor` | `rgb(107,114,128)` | Legend swatch border |
| `legendBg` | `rgba(55,65,81,0.30)` | Legend swatch fill |

The muted gray ensures baselines are visible but clearly secondary to the current schedule bars. Using `dashed` border provides an unmistakable visual distinction.

### 5.3 Style Settings: Future Expansion

The `GanttStyleSettings` interface is designed to grow. Planned sections for future iterations:

```typescript
export interface GanttStyleSettings {
  baseline: GanttBaselineStyle;      // ← this proposal
  // row: GanttRowStyle;             // rowHeight, padding, hover bg
  // bar: GanttBarStyle;             // status colors, border-radius, min-width
  // milestone: GanttMilestoneStyle; // size, colors
  // summary: GanttSummaryStyle;     // bar color, text color, font-weight
  // relationships: GanttRelStyle;   // arrow colors, stroke widths, marker sizes
  // timeline: GanttTimelineStyle;   // header colors, grid line colors
}
```

Migrating existing hardcoded Tailwind classes into this structure is not in scope for this proposal, but the pattern established here makes it straightforward.

### 5.4 Slippage Indicators (Future Enhancement)

A future iteration could color-code baseline offset:
- Green tint if current finish is earlier than baseline (ahead of schedule)
- Red tint if current finish is later than baseline (behind schedule)

This is out of scope for the initial implementation but the data model supports it. Slippage colors would be added to `GanttBaselineStyle` (e.g., `slipAheadColor`, `slipBehindColor`).

---

## 6. Edge Cases

| Case | Handling |
|------|----------|
| Activity has no baseline (`baseline_start` / `baseline_finish` are NULL) | No baseline bar rendered; current bar renders normally |
| Baseline dates identical to current dates | Baseline bar rendered directly under current bar (visually overlapping); tooltip shows "Slippage: 0 days" |
| Baseline extends beyond timeline range | `useTimeline` expands range to include baseline dates |
| Summary activity with baseline | Render thin baseline bar below summary bar |
| Milestone with baseline | Render smaller hollow diamond below current milestone |
| Toggle off | Baseline bars hidden; row heights unchanged |
| No activities have baseline data (`has_baseline: false`) | Toggle button hidden |

---

## 7. Scope Exclusions

The following are **not** in scope for this implementation:

- **Version-to-version comparison** (comparing two full schedule versions side by side): this requires cross-version activity matching logic.
- **Baseline version selector** (choosing which baseline to compare against): the inline `baseline_*` fields represent the primary baseline (Baseline 0 in MS Project terms).
- **Slippage color coding** on bars: deferred to future iteration.
- **Non-MS schedule formats**: This proposal covers MS Project schedules only.
- **Progress overlay** (percent complete shading on bars): orthogonal feature, can be combined later.
- **Earned Value calculations**: uses baseline data but is a separate analytics feature.

---

## 8. Verification

After implementation, verify with any MS Project schedule that has baseline data:

1. Open any project with `has_baseline: true` in the Gantt panel.
2. Confirm baseline ghost bars appear below current bars.
3. Confirm milestones show hollow baseline diamonds.
4. Confirm tooltip shows baseline dates and slippage.
5. Confirm toggle hides/shows baseline bars.
6. Confirm legend shows baseline entry when toggle is on.
7. Confirm activities without baseline data render normally (no ghost bar).
8. Confirm timeline range expands if baseline dates exceed current range.
