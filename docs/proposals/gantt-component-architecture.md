# Gantt Component Architecture Proposal

**Date:** January 19, 2026  
**Status:** Revised  
**Author:** Engineering Team  
**Revision:** v2 — Scaled back from previous proposed approach

---

## Executive Summary

This proposal outlines a **pragmatic refactoring** of the existing Gantt chart components (`GanttChart.tsx`, `GanttPanel.tsx`) to eliminate code duplication, improve maintainability, and **support datasets of 500-1000 activities** with acceptable performance.

### Why This Refactor Now?

1. **Immediate need**: We're onboarding a project with 500-1000 activities — the current implementation will not perform acceptably at this scale
2. **Technical debt**: ~120 lines of duplicated logic across two components makes changes error-prone
3. **Testability**: Calculation logic embedded in components cannot be unit tested in isolation

### What Changed from the Original Proposal?

The **previous proposed approach** envisioned a fully headless, composable component system with 15+ files, separate theme contexts, render props, and a complete abstraction layer. After review, that approach was deemed **over-architected for current usage** — the Gantt components are used in exactly 2 places with no immediate plans for additional consumers.

This revised proposal focuses on:
- **Extracting shared hooks** for timeline and positioning calculations
- **Adding virtualization** for large dataset performance  
- **Preserving existing patterns** (Tailwind styling, component structure)

---

## Current State Analysis

### Existing Components

| Component | Lines | Purpose |
|-----------|-------|---------|
| `GanttChart.tsx` | 242 | Standalone Gantt for reports/printing |
| `GanttPanel.tsx` | 366 | Floating panel with filters and hierarchy |
| `types/schedule.ts` | 122 | Type definitions |

### Problems Identified

1. **Code Duplication** (Primary focus of this refactor)
   - Timeline generation logic is duplicated in both components (~40 lines each)
   - Bar positioning calculation is duplicated (~30 lines each)
   - Year/month header rendering is duplicated (~50 lines each)

2. **Tight Coupling** (Acceptable for current scope)
   - Styling uses Tailwind classes consistently — this is fine
   - Layout is embedded but both variants need different layouts anyway

3. **Limited Extensibility** (Deferred — no current requirement)
   - ~~Cannot add features without modifying core components~~
   - ~~No plugin or slot system for customization~~
   - Features like dependency arrows can be added incrementally

4. **Performance Concerns** (Critical for target datasets)
   - Target datasets are **500-1000 activities** — virtualization is required
   - Without virtualization: 3,000-5,000+ DOM nodes, slow scrolling, janky re-renders
   - Existing `useMemo` usage helps but doesn't solve the DOM volume problem

---

## Previous Proposed Approach (Revised)

The original proposal suggested a 15+ file architecture:

```
frontend/components/gantt/           # PREVIOUS - TOO COMPLEX
├── hooks/ (5 files)
├── context/ (2 files)  
├── core/ (9 files)
├── ui/ (5 files)
├── composed/ (3 files)
└── themes/ (3 files)
```

**Why this was revised:**
- Only 2 consumers (`ChatLayout.tsx` → `GanttPanel`, report page → `GanttChart`)
- Headless component pattern adds abstraction cost without clear benefit
- Parallel theme token system conflicts with existing Tailwind approach
- No concrete third use case to justify the abstraction

---

## Revised Architecture

### Directory Structure

We propose a **flat, minimal structure** that groups Gantt-related code without over-abstracting:

```
frontend/components/gantt/
├── index.ts                        # Public API exports
├── types.ts                        # Shared Gantt types (extends schedule.ts)
│
├── hooks/
│   ├── index.ts                    # Hook exports
│   ├── useTimeline.ts              # Timeline month/year generation
│   ├── useBarPositions.ts          # Calculate bar left/width percentages
│   └── useVirtualizedRows.ts       # Row virtualization for large datasets
│
├── GanttChart.tsx                  # Refactored standalone (uses hooks)
└── GanttPanel.tsx                  # Refactored panel (uses hooks, virtualized)
```

**Total: 7 files** (down from 27+ in original proposal)

**Why this structure:**
- **`hooks/` folder**: Isolates reusable calculation logic that can be unit tested independently
- **Components stay at root level**: No deep nesting — easy to find and modify
- **Single `types.ts`**: Avoids type fragmentation across multiple files
- **No `context/`, `core/`, `ui/` folders**: These added indirection without value for 2 consumers

---

## Design Principles (Revised)

### 1. Extract Hooks, Keep Components Simple

**What:** Move duplicated calculation logic (timeline generation, bar positioning) into shared hooks. Leave rendering logic in each component.

**Why:** 
- The two components (`GanttChart`, `GanttPanel`) have **identical calculation logic** but **different rendering needs** (print layout vs. interactive panel)
- Extracting calculations into hooks eliminates the ~120 lines of duplication
- Each component retains control over its specific layout, styling, and interactions
- Hooks can be unit tested without rendering components

```tsx
// Both components use the same hooks for calculations
const timeline = useTimeline({ items, projectStart, projectEnd });
const positions = useBarPositions({ items, timeline });

// But each component handles its own rendering/layout differently
// GanttChart: optimized for print, static
// GanttPanel: interactive, virtualized, hierarchical
```

### 2. Preserve Tailwind Styling

**What:** Continue using Tailwind classes for all styling. No separate theme token system.

**Why:**
- The entire frontend uses Tailwind — introducing a parallel system creates cognitive overhead
- Theme tokens require runtime style computation; Tailwind classes are statically compiled
- Print styling already works via Tailwind's `print:` variants (`print:bg-white`, `print:text-black`)
- If we need theming later (e.g., white-label), CSS variables in Tailwind config is the idiomatic approach

```typescript
// PREVIOUS - Creates two competing styling paradigms
const theme = {
  barColors: { critical: '#ef4444' },
  rowHeight: 32,
};
<div style={{ backgroundColor: theme.barColors.critical }}>
```

```tsx
// REVISED - Consistent with rest of codebase
<div className={`${isCritical ? 'bg-red-500' : 'bg-blue-500'} rounded`}>
```

### 3. Keep ScheduleItem Type

**What:** Work directly with the existing `ScheduleItem` type from `types/schedule.ts`. No new "normalized" type.

**Why:**
- The backend already returns well-structured data in `ScheduleItem` format
- A transformation layer (`transformScheduleItemsToTasks()`) adds CPU cost on every render
- For 1000 activities, transformation creates 1000 new objects per render cycle
- Hooks can handle ISO string → Date parsing internally and memoize the results

```typescript
// PREVIOUS - Requires transformation layer
interface GanttTask {
  start: Date;  // Backend sends string
  end: Date;
}
// + transformScheduleItemsToTasks() on every render = 1000 object allocations
```

```typescript
// REVISED - No transformation needed
// Hooks accept ScheduleItem[] directly, parse dates internally with memoization
```

### 4. Virtualization for Large Datasets

**What:** Render only the visible rows (+ small buffer) instead of all 500-1000 rows.

**Why this is critical:**
- **DOM node explosion**: Each row has ~5 elements (label container, label text, ID text, bar container, bar). 1000 activities = 5000+ DOM nodes.
- **Browser limits**: Beyond ~2000 DOM nodes, scroll performance degrades noticeably. Beyond 5000, it becomes unusable.
- **Re-render cost**: React must diff all 5000 nodes on any state change (hover, selection)
- **Memory**: Each DOM node consumes memory; virtualization keeps it constant regardless of dataset size

**How virtualization solves this:**
- Only ~30-50 rows are in the DOM at any time (visible viewport + overscan buffer)
- As user scrolls, rows are recycled — removed from top, added to bottom (or vice versa)
- Total DOM nodes stay constant: ~150-250 instead of 5000+

```tsx
// Using @tanstack/react-virtual for row virtualization
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualizedGanttBody({ items, parentRef }) {
  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28, // row height in px
    overscan: 10, // render 10 extra rows above/below viewport for smooth scrolling
  });

  return (
    <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative' }}>
      {rowVirtualizer.getVirtualItems().map((virtualRow) => (
        <GanttRow 
          key={items[virtualRow.index].id}
          item={items[virtualRow.index]}
          style={{
            position: 'absolute',
            top: virtualRow.start,
            height: virtualRow.size,
          }}
        />
      ))}
    </div>
  );
}
```

**Why `@tanstack/react-virtual` over alternatives:**

| Library | Size | Notes |
|---------|------|-------|
| `@tanstack/react-virtual` | ~3KB | ✅ Lightweight, active, supports dynamic heights |
| `react-window` | ~6KB | Good but less actively maintained |
| `react-virtuoso` | ~15KB | Feature-rich but heavier than needed |
| Custom implementation | 0KB | Risk of bugs, maintenance burden |

---

## Library Status Assessment

This section provides a current status evaluation of the libraries recommended in this proposal, ensuring production readiness and long-term maintainability.

### @tanstack/react-virtual (Recommended for virtualization)

| Metric | Value | Assessment |
|--------|-------|------------|
| **Version** | 3.13.18 | Stable, mature |
| **Last Publish** | 12 days ago (Jan 2026) | ✅ Actively maintained |
| **Weekly Downloads** | 7.4M | ✅ Extremely high adoption |
| **GitHub Stars** | 6.6k | ✅ Strong community |
| **Open Issues** | 86 | Reasonable for popularity |
| **Contributors** | 130 | Active contributor base |
| **Used By** | 357k+ repositories | ✅ Battle-tested at scale |
| **License** | MIT | ✅ No restrictions |
| **TypeScript** | Built-in declarations | ✅ First-class support |
| **Bundle Size** | ~3KB (gzipped) | ✅ Minimal footprint |

**Verdict: APPROVED** — Part of the TanStack ecosystem (same maintainers as TanStack Query, TanStack Table, TanStack Router). Very active development with 273 releases. The library is framework-agnostic with dedicated React bindings.

**Risk factors:** None identified. The TanStack ecosystem is one of the most reliable in the React community.

---

### react-window (Alternative — NOT recommended)

| Metric | Value | Assessment |
|--------|-------|------------|
| **Version** | 2.2.5 | Recently updated (v2 released) |
| **Last Publish** | 8 days ago (Jan 2026) | ✅ Active again |
| **Weekly Downloads** | 4.1M | ✅ High adoption |
| **Open Issues** | 1 | ⚠️ Low, but historically had maintenance gaps |
| **Collaborators** | 1 (bvaughn) | ⚠️ Single maintainer |
| **License** | MIT | ✅ No restrictions |
| **Bundle Size** | ~6KB | Slightly larger than TanStack |

**Verdict: ACCEPTABLE but NOT PREFERRED** — After a long maintenance gap, v2.0 was released with significant updates. However, single-maintainer projects carry bus-factor risk. The library is solid but TanStack Virtual has stronger ecosystem support.

**Note:** react-window v2 was recently published (8 days ago), showing renewed maintenance. Worth monitoring.

---

### react-virtuoso (Alternative — NOT recommended)

| Metric | Value | Assessment |
|--------|-------|------------|
| **Version** | 4.18.1 | Stable |
| **Last Publish** | 21 days ago | ✅ Active |
| **Weekly Downloads** | 1.5M | Good adoption |
| **Bundle Size** | ~15KB (240 kB unpacked) | ⚠️ 5x larger than TanStack |
| **Features** | Very rich (groups, tables, grids) | More than we need |
| **License** | MIT | ✅ No restrictions |

**Verdict: OVER-ENGINEERED for our use case** — Excellent library with automatic height measurement and rich features. However, 5x the bundle size and features we won't use. Better suited for complex table/grid scenarios.

---

### date-fns (Already in use — no change)

| Metric | Value | Assessment |
|--------|-------|------------|
| **Version** | 4.1.0 | Stable |
| **Last Publish** | ~1 year ago | ⚠️ Stable but slow release cadence |
| **Weekly Downloads** | 39.7M | ✅ Industry standard |
| **Used By** | 23,828+ dependents | ✅ Extremely battle-tested |
| **License** | MIT | ✅ No restrictions |
| **TypeScript** | Built-in declarations | ✅ First-class support |

**Verdict: CONTINUE USING** — Already in the codebase, industry standard for date manipulation. The 1-year gap since last publish is normal for mature, stable libraries. Version 4.0 added first-class timezone support.

**Note:** No changes needed — the current implementation already uses date-fns functions (`parseISO`, `format`, `differenceInDays`, `addMonths`, `startOfMonth`).

---

### Summary

| Library | Status | Action |
|---------|--------|--------|
| `@tanstack/react-virtual` | ✅ Excellent | **Add as new dependency** |
| `react-window` | ⚠️ Acceptable | Not recommended (single maintainer) |
| `react-virtuoso` | ⚠️ Overkill | Not recommended (bundle size) |
| `date-fns` | ✅ Excellent | **Already in use — no change** |

**Dependency Impact:**
- New dependencies: 1 (`@tanstack/react-virtual`)
- Bundle size increase: ~3KB gzipped
- No breaking changes to existing dependencies

### Sticky Header Pattern for Virtualized Scrolling

When virtualizing rows, the timeline header must remain **fixed** while the body scrolls. This is critical for usability — users need month/year context while scrolling through activities.

**Implementation pattern:**

```tsx
// GanttPanel.tsx - Virtualized layout structure
function GanttPanelContent({ positionedItems, timeline, parentRef }) {
  const rowVirtualizer = useVirtualizer({
    count: positionedItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
    overscan: 10,
  });

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Timeline header - STICKY, not virtualized */}
      <div className="sticky top-0 z-10 bg-dark-800">
        <TimelineHeader 
          months={timeline.months} 
          yearGroups={timeline.yearGroups} 
        />
      </div>

      {/* Virtualized body - scrollable */}
      <div ref={parentRef} className="flex-1 overflow-auto">
        {/* Spacer div maintains scroll height */}
        <div
          style={{
            height: `${rowVirtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const item = positionedItems[virtualRow.index];
            return (
              <div
                key={item.id}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <HierarchicalRow item={item} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
```

**Key implementation details:**

1. **Sticky header**: `sticky top-0 z-10` keeps the timeline header fixed at the top of the scroll container
2. **Background color**: Header needs `bg-dark-800` to prevent content showing through while scrolling
3. **Spacer div**: The outer div with `getTotalSize()` height maintains correct scrollbar proportions
4. **Transform for positioning**: Using `transform: translateY()` is more performant than `top` for frequently changing positions
5. **Overscan**: 10 rows above/below viewport ensures smooth scrolling without visible pop-in

---

## Type Definitions (Minimal)

The **previous proposed approach** defined extensive new types (`GanttTask`, `GanttConfig`, `GanttTheme`, `TaskDependency`). This revision uses minimal additions to the existing type system.

### New Types (hooks/types.ts)

```typescript
// types.ts — Extends existing schedule.ts types

import { ScheduleItem } from '@/types/schedule';

/**
 * Sorting modes for activity display order.
 * Exported from useBarPositions but defined here for type safety.
 */
export type SortMode = 
  | 'preserve'      // Keep backend order (MS Project hierarchy)
  | 'start-date'    // Sort by start date (simple P6 display)
  | 'grouped';      // Group-aware: group name → summaries first → start date

/**
 * Calculated timeline for header rendering
 */
export interface TimelineData {
  months: TimelineMonth[];
  totalDays: number;
  startDate: Date;
  yearGroups: YearGroup[];
}

export interface TimelineMonth {
  date: Date;
  label: string;      // "Jan 2026"
  shortLabel: string; // "Jan"
}

export interface YearGroup {
  year: string;
  monthCount: number;
}

/**
 * Calculated bar position
 */
export interface BarPosition {
  startPercentage: number;
  widthPercentage: number;
}

/**
 * Item with calculated position (returned by useBarPositions)
 */
export interface PositionedItem extends ScheduleItem {
  startPercentage: number;
  widthPercentage: number;
  duration: number;
}
```

**Note:** We intentionally avoid:
- A new `GanttTask` type requiring transformation
- A `GanttTheme` type (using Tailwind instead)
- A `GanttConfig` type (each component has its own props)

---

## Hook Implementations

Each hook extracts specific duplicated logic from the existing components. The implementations below are derived directly from the current `useMemo` blocks in `GanttChart.tsx` and `GanttPanel.tsx`.

### useTimeline

**What it does:** Generates the timeline structure (months, year groups, total days) used to render the Gantt header.

**Why extract it:**
- This exact logic exists in both `GanttChart.tsx` (lines 42-68) and `GanttPanel.tsx` (lines 17-48)
- Both components need the same calculation: "given a set of activities, determine the month columns to display"
- Extracting it means bug fixes and improvements happen in one place

**Current duplication being eliminated:**

```typescript
// GanttChart.tsx - generateTimeline useMemo (~40 lines)
// GanttPanel.tsx - timeline useMemo (~40 lines)
// ↓ Consolidated into ↓
// useTimeline.ts (~60 lines, single source of truth)
```

```typescript
// hooks/useTimeline.ts
import { useMemo } from 'react';
import { 
  startOfMonth, 
  addMonths, 
  differenceInDays, 
  format,
  parseISO 
} from 'date-fns';
import { ScheduleItem } from '@/types/schedule';
import { TimelineData, TimelineMonth, YearGroup } from './types';

interface UseTimelineOptions {
  /** Schedule items (uses start/finish ISO strings) */
  items: ScheduleItem[];
  /** Override project start (ISO string or Date) */
  projectStart?: string | Date;
  /** Override project end (ISO string or Date) */
  projectEnd?: string | Date;
}

/**
 * Generates timeline months and year groups for Gantt header rendering.
 * Consolidates duplicated logic from GanttChart.tsx and GanttPanel.tsx.
 */
export function useTimeline({ 
  items, 
  projectStart, 
  projectEnd 
}: UseTimelineOptions): TimelineData {
  return useMemo(() => {
    if (!items || items.length === 0) {
      return {
        months: [],
        totalDays: 0,
        startDate: new Date(),
        yearGroups: [],
      };
    }

    try {
      // Determine date range from items or explicit overrides
      const itemStarts = items.map(item => parseISO(item.start));
      const itemEnds = items.map(item => parseISO(item.finish));
      
      const dataStart = projectStart 
        ? (typeof projectStart === 'string' ? parseISO(projectStart) : projectStart)
        : new Date(Math.min(...itemStarts.map(d => d.getTime())));
      const dataEnd = projectEnd
        ? (typeof projectEnd === 'string' ? parseISO(projectEnd) : projectEnd)
        : new Date(Math.max(...itemEnds.map(d => d.getTime())));

      const timelineStart = startOfMonth(dataStart);
      const timelineEnd = addMonths(startOfMonth(dataEnd), 1);

      // Generate months
      const months: TimelineMonth[] = [];
      let current = new Date(timelineStart);
      
      while (current < timelineEnd) {
        months.push({
          date: new Date(current),
          label: format(current, 'MMM yyyy'),
          shortLabel: format(current, 'MMM'),
        });
        current = addMonths(current, 1);
      }

      // Group by year for header row
      const yearGroups: YearGroup[] = [];
      let currentYear = '';
      let monthCount = 0;

      months.forEach((month) => {
        const year = format(month.date, 'yyyy');
        if (year !== currentYear) {
          if (currentYear) {
            yearGroups.push({ year: currentYear, monthCount });
          }
          currentYear = year;
          monthCount = 1;
        } else {
          monthCount++;
        }
      });
      if (currentYear) {
        yearGroups.push({ year: currentYear, monthCount });
      }

      const totalDays = differenceInDays(timelineEnd, timelineStart) || 1;

      return { months, totalDays, startDate: timelineStart, yearGroups };
    } catch (error) {
      console.error('Error generating timeline:', error);
      return { months: [], totalDays: 0, startDate: new Date(), yearGroups: [] };
    }
  }, [items, projectStart, projectEnd]);
}
```

### useBarPositions

**What it does:** Calculates the horizontal position (left %) and width (%) for each activity bar based on the timeline.

**Why extract it:**
- This calculation exists in both components: `GanttChart.tsx` (lines 70-95) and `GanttPanel.tsx` (lines 50-108)
- The math is identical: `(daysFromStart / totalDays) * 100` for position, `(duration / totalDays) * 100` for width
- `GanttPanel` has additional sorting/grouping logic that we preserve via the `preserveOrder` option

**Additional responsibility — sorting:**
- For P6 schedules: Sort by start date (default behavior)
- For MS Project schedules: Preserve backend order to maintain WBS hierarchy (`preserveOrder: true`)

```typescript
// hooks/useBarPositions.ts
import { useMemo } from 'react';
import { differenceInDays, parseISO } from 'date-fns';
import { ScheduleItem } from '@/types/schedule';
import { PositionedItem } from './types';

/**
 * Sorting modes for activity display order
 */
export type SortMode = 
  | 'preserve'      // Keep backend order (MS Project hierarchy)
  | 'start-date'    // Sort by start date (simple P6 display)
  | 'grouped';      // Group-aware: group name → summaries first → start date

interface UseBarPositionsOptions {
  items: ScheduleItem[];
  timelineStartDate: Date;
  totalDays: number;
  /** 
   * Sorting mode for activities:
   * - 'preserve': Keep backend order (MS Project with WBS hierarchy)
   * - 'start-date': Simple sort by start date (default)
   * - 'grouped': Group-aware sorting for P6 grouped displays
   */
  sortMode?: SortMode;
}

/**
 * Calculates bar positions as percentages for each schedule item.
 * Consolidates duplicated logic from GanttChart.tsx and GanttPanel.tsx.
 */
export function useBarPositions({
  items,
  timelineStartDate,
  totalDays,
  sortMode = 'start-date',
}: UseBarPositionsOptions): PositionedItem[] {
  return useMemo(() => {
    if (!items || items.length === 0 || totalDays === 0) {
      return [];
    }

    // Apply sorting based on mode
    const sortedItems = sortItems(items, sortMode);

    return sortedItems.map((item) => {
      try {
        const startDate = parseISO(item.start);
        const finishDate = parseISO(item.finish);

        const daysFromStart = differenceInDays(startDate, timelineStartDate);
        const duration = differenceInDays(finishDate, startDate) + 1;

        const startPercentage = (daysFromStart / totalDays) * 100;
        const widthPercentage = (duration / totalDays) * 100;

        return {
          ...item,
          startPercentage: Math.max(0, startPercentage),
          widthPercentage: Math.max(1, widthPercentage),
          duration,
        };
      } catch {
        return null;
      }
    }).filter(Boolean) as PositionedItem[];
  }, [items, timelineStartDate, totalDays, sortMode]);
}

/**
 * Sorting logic extracted for clarity and testability.
 * Handles the three sorting modes required by different use cases.
 */
function sortItems(items: ScheduleItem[], mode: SortMode): ScheduleItem[] {
  if (mode === 'preserve') {
    // MS Project: backend already sorted by WBS hierarchy
    return [...items];
  }

  if (mode === 'start-date') {
    // Simple chronological sort
    return [...items].sort((a, b) => 
      new Date(a.start).getTime() - new Date(b.start).getTime()
    );
  }

  // 'grouped' mode: P6 with activity code grouping
  return [...items].sort((a, b) => {
    // 1. Sort by group_name (nulls/undefined last)
    const groupA = a.group_name ?? '';
    const groupB = b.group_name ?? '';
    if (groupA !== groupB) {
      return groupA.localeCompare(groupB);
    }

    // 2. Within same group, summaries come first
    const summaryA = a.is_summary ? 0 : 1;
    const summaryB = b.is_summary ? 0 : 1;
    if (summaryA !== summaryB) {
      return summaryA - summaryB;
    }

    // 3. Within same group and type, sort by start date
    return new Date(a.start).getTime() - new Date(b.start).getTime();
  });
}
```

---

## Refactored Components

The component refactoring is intentionally minimal — we're replacing internal `useMemo` blocks with hook calls while preserving all existing rendering logic, Tailwind classes, and print styles.

### GanttChart.tsx (After)

**Changes:**
- Replace `generateTimeline` useMemo → `useTimeline` hook
- Replace `processedData` useMemo → `useBarPositions` hook
- **No changes to JSX, Tailwind classes, or print styles**

```tsx
// components/gantt/GanttChart.tsx
import React from 'react';
import { format, parseISO } from 'date-fns';
import { Calendar } from 'lucide-react';
import { ScheduleItem } from '@/types';
import { useTimeline } from './hooks/useTimeline';
import { useBarPositions } from './hooks/useBarPositions';

interface GanttChartProps {
  data: ScheduleItem[];
  loading?: boolean;
}

const GanttChart: React.FC<GanttChartProps> = ({ data, loading }) => {
  // Use shared hooks instead of duplicated useMemo blocks
  const timeline = useTimeline({ items: data });
  const positionedItems = useBarPositions({
    items: data,
    timelineStartDate: timeline.startDate,
    totalDays: timeline.totalDays,
  });

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (!data || data.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700 
                    print:bg-white print:border print:border-gray-300">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-blue-400 print:text-black" />
          <h3 className="text-xl font-light text-white print:text-black">
            Project L1 schedule
          </h3>
        </div>
        <div className="text-sm text-gray-400 print:text-black">
          {data.length} schedule item{data.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Timeline Header - uses hook data */}
      <TimelineHeader 
        months={timeline.months} 
        yearGroups={timeline.yearGroups} 
      />

      {/* Gantt Bars - uses hook data */}
      <div className="space-y-3">
        {positionedItems.map((item, index) => (
          <GanttRow key={item.id} item={item} colorIndex={index} />
        ))}
      </div>
    </div>
  );
};

// Extracted sub-components (same file, not exported)
function TimelineHeader({ months, yearGroups }) { /* ... */ }
function GanttRow({ item, colorIndex }) { /* ... */ }
function LoadingSkeleton() { /* ... */ }
function EmptyState() { /* ... */ }

export default GanttChart;
```

### GanttPanel.tsx (After)

**Changes:**
- Replace `timeline` useMemo → `useTimeline` hook
- Replace `processedItems` useMemo → `useBarPositions` hook  
- **Add virtualization** for 500-1000 activity performance
- **Preserve**: hierarchy rendering, filter display, legend, all panel-specific logic

```tsx
// components/gantt/GanttPanel.tsx  
import React from 'react';
import { X, Calendar, Filter, AlertTriangle } from 'lucide-react';
import { GanttChartData } from '@/types/schedule';
import { useTimeline } from './hooks/useTimeline';
import { useBarPositions } from './hooks/useBarPositions';

interface GanttPanelProps {
  data: GanttChartData;
  onClose: () => void;
}

export const GanttPanel: React.FC<GanttPanelProps> = ({ data, onClose }) => {
  // Use shared hooks
  const timeline = useTimeline({ 
    items: data.items,
    projectStart: data.project_start,
    projectEnd: data.project_finish,
  });
  
  // Determine sort mode based on data characteristics
  const sortMode = data.preserve_order 
    ? 'preserve'           // MS Project: keep WBS hierarchy
    : data.grouping 
      ? 'grouped'          // P6 with grouping: group-aware sort
      : 'start-date';      // P6 ungrouped: simple chronological
  
  const positionedItems = useBarPositions({
    items: data.items,
    timelineStartDate: timeline.startDate,
    totalDays: timeline.totalDays,
    sortMode,
  });

  // Panel-specific: filter description (unchanged)
  const filterDescription = useFilterDescription(data.filter_applied);

  return (
    <div className="fixed top-20 right-8 bottom-30 w-[900px] bg-[#0d1117] ...">
      {/* Panel header, stats bar, filter indicator - unchanged */}
      
      {/* Gantt content - now uses hook data */}
      <div className="flex-1 overflow-auto p-4">
        <TimelineHeader months={timeline.months} yearGroups={timeline.yearGroups} />
        
        <div className="space-y-1">
          {positionedItems.map((item) => (
            <HierarchicalRow key={item.id} item={item} />
          ))}
        </div>
      </div>
      
      {/* Legend - unchanged */}
    </div>
  );
};

// Panel-specific sub-components
function HierarchicalRow({ item }) {
  const indentPx = ((item.level || 2) - 1) * 16;
  // ... hierarchy-aware rendering with summary bars
}
```

---

## What Was Removed from Previous Proposal

The following elements from the **previous proposed approach** are **not included** in this revision:

| Removed | Reason |
|---------|--------|
| `GanttContext` / `GanttProvider` | No shared state needed between 2 independent components |
| `ThemeContext` / theme tokens | Tailwind handles styling consistently |
| `GanttBar`, `GanttRow`, `GanttTimeline` as separate files | Sub-components stay in their parent files |
| `SimpleGantt`, `PanelGantt`, `PrintableGantt` composed variants | Keep existing component structure |
| `useGanttZoom`, `useGanttScroll`, `useGanttSelection` hooks | No current requirement for these features |
| `GanttMilestone`, `GanttSummaryBar`, `GanttDependencyArrow` | Future features, add incrementally when needed |
| `GanttTooltip`, `GanttLegend`, `GanttZoomControls`, `GanttGridLines` UI components | Existing inline implementations are sufficient |
| `transformScheduleItemsToTasks()` utility | Work directly with `ScheduleItem` type |
| Render props pattern | Over-engineering for current needs |

---

## Migration Plan (Revised)

The migration is designed to be **incremental and low-risk**. Each phase produces working code that can be merged independently.

### Phase 1: Extract Hooks + Virtualization (2-3 days)

**Goal:** Create the shared infrastructure without touching existing components yet.

1. Create `frontend/components/gantt/hooks/useTimeline.ts`
2. Create `frontend/components/gantt/hooks/useBarPositions.ts`  
3. Create `frontend/components/gantt/hooks/useVirtualizedRows.ts`
4. Create `frontend/components/gantt/hooks/types.ts`
5. Create `frontend/components/gantt/hooks/index.ts`
6. Install `@tanstack/react-virtual` dependency
7. Write unit tests for hooks (can test without components)

**Risk level:** Low — no existing code is modified.

### Phase 2: Refactor GanttChart (1 day)

**Goal:** Migrate the simpler component first as a proof of concept.

1. Replace `generateTimeline` useMemo with `useTimeline` hook
2. Replace `processedData` useMemo with `useBarPositions` hook
3. Verify print styling still works (`print:` classes preserved)
4. Run visual regression tests

**Risk level:** Low — `GanttChart` is simpler (no hierarchy, no virtualization needed for reports).

### Phase 3: Refactor GanttPanel with Virtualization (2 days)

**Goal:** Migrate the complex component and add virtualization for large datasets.

1. Replace `timeline` useMemo with `useTimeline` hook
2. Replace `processedItems` useMemo with `useBarPositions` hook (with `sortMode`)
3. **Add virtualized scrolling** using `useVirtualizedRows` hook
4. Implement fixed timeline header with scrollable virtualized body (see sticky header pattern above)
5. Verify hierarchy/grouping still works (`preserve_order`, `level`, `is_summary`)
6. Performance test with 500+ activities
7. **Visual regression testing** (see below)

**Risk level:** Medium — virtualization changes the DOM structure. Requires careful testing.

**Visual Regression Testing Requirements:**

Virtualization fundamentally changes the DOM structure (from N rows to ~30-50 visible rows). This can introduce subtle visual bugs:

| Test Case | What to Verify |
|-----------|----------------|
| **Scroll alignment** | Bars align correctly with timeline columns during scroll |
| **Header stickiness** | Timeline header stays fixed, doesn't jump or flicker |
| **Row transitions** | No visible "pop-in" of rows at scroll edges |
| **Hierarchy indentation** | Summary/child indentation preserved after virtualization |
| **Bar tooltips** | Hover tooltips appear correctly on virtualized rows |
| **Legend visibility** | Footer legend remains visible (not affected by scroll) |

**Recommended approach:**
- Use Playwright or Cypress for screenshot comparison tests
- Test with datasets of 50, 200, 500, and 1000 activities
- Capture screenshots at: top of list, middle (scrolled), bottom
- Compare before/after virtualization for pixel differences

### Phase 4: Cleanup (0.5 day)

**Goal:** Finalize the file organization.

1. Move refactored components to `components/gantt/` directory
2. Update imports in `ChatLayout.tsx`
3. Delete old component files
4. Update `index.ts` exports

**Risk level:** Low — just file moves and import updates.

---

**Total: ~6 days** (down from 4 weeks in previous proposal)

**Note**: Virtualization adds ~2 days but is required for 500-1000 activity datasets.

---

## Testing Strategy

**Why test hooks separately?**
- Hooks contain pure calculation logic — easy to unit test with mock data
- Component tests are slower and more brittle
- We can achieve high coverage with fast hook tests + selective component integration tests

```typescript
// __tests__/hooks/useTimeline.test.ts
import { renderHook } from '@testing-library/react';
import { useTimeline } from '../hooks/useTimeline';

describe('useTimeline', () => {
  it('generates correct month units for date range', () => {
    const items = [
      { id: 1, start: '2024-01-15', finish: '2024-03-20', /* ... */ },
    ];
    const { result } = renderHook(() => useTimeline({ items }));
    
    expect(result.current.months).toHaveLength(3); // Jan, Feb, Mar
    expect(result.current.yearGroups).toEqual([{ year: '2024', monthCount: 3 }]);
  });

  it('handles empty items array', () => {
    const { result } = renderHook(() => useTimeline({ items: [] }));
    expect(result.current.months).toHaveLength(0);
    expect(result.current.totalDays).toBe(0);
  });

  it('respects projectStart/projectEnd overrides', () => {
    const items = [{ id: 1, start: '2024-02-15', finish: '2024-02-20' }];
    const { result } = renderHook(() => useTimeline({ 
      items,
      projectStart: '2024-01-01',
      projectEnd: '2024-04-30',
    }));
    
    expect(result.current.months).toHaveLength(4); // Jan, Feb, Mar, Apr
  });
});

// __tests__/hooks/useBarPositions.test.ts
import { renderHook } from '@testing-library/react';
import { useBarPositions } from '../hooks/useBarPositions';

describe('useBarPositions', () => {
  it('calculates correct percentages', () => {
    const items = [
      { id: 1, start: '2024-01-01', finish: '2024-01-10', /* ... */ },
    ];
    const { result } = renderHook(() => useBarPositions({
      items,
      timelineStartDate: new Date('2024-01-01'),
      totalDays: 31,
    }));
    
    expect(result.current[0].startPercentage).toBe(0);
    expect(result.current[0].widthPercentage).toBeCloseTo(32.26, 1); // 10/31 * 100
  });

  it('preserves order when sortMode is "preserve"', () => {
    const items = [
      { id: 1, start: '2024-01-15', finish: '2024-01-20' },
      { id: 2, start: '2024-01-01', finish: '2024-01-05' },
    ];
    const { result } = renderHook(() => useBarPositions({
      items,
      timelineStartDate: new Date('2024-01-01'),
      totalDays: 31,
      sortMode: 'preserve',
    }));
    
    // Should maintain original order (id 1 first, then id 2)
    expect(result.current[0].id).toBe(1);
    expect(result.current[1].id).toBe(2);
  });

  it('sorts by start date when sortMode is "start-date"', () => {
    const items = [
      { id: 1, start: '2024-01-15', finish: '2024-01-20' },
      { id: 2, start: '2024-01-01', finish: '2024-01-05' },
    ];
    const { result } = renderHook(() => useBarPositions({
      items,
      timelineStartDate: new Date('2024-01-01'),
      totalDays: 31,
      sortMode: 'start-date',
    }));
    
    // Should sort chronologically (id 2 first, then id 1)
    expect(result.current[0].id).toBe(2);
    expect(result.current[1].id).toBe(1);
  });

  it('sorts with group-awareness when sortMode is "grouped"', () => {
    const items = [
      { id: 1, start: '2024-01-15', finish: '2024-01-20', group_name: 'Phase B', is_summary: false },
      { id: 2, start: '2024-01-01', finish: '2024-01-05', group_name: 'Phase A', is_summary: false },
      { id: 3, start: '2024-01-01', finish: '2024-01-31', group_name: 'Phase A', is_summary: true },
    ];
    const { result } = renderHook(() => useBarPositions({
      items,
      timelineStartDate: new Date('2024-01-01'),
      totalDays: 31,
      sortMode: 'grouped',
    }));
    
    // Should sort: Phase A summary (id 3), Phase A item (id 2), Phase B item (id 1)
    expect(result.current[0].id).toBe(3); // Phase A summary first
    expect(result.current[1].id).toBe(2); // Phase A item
    expect(result.current[2].id).toBe(1); // Phase B item
  });
});
```

---

## Benefits Summary (Revised)

| Benefit | Impact |
|---------|--------|
| **Performance** | Virtualization enables 500-1000 activities without UI lag |
| **DRY Code** | ~80 lines of duplicated logic extracted to hooks |
| **Testable** | Hooks can be unit tested in isolation (faster CI, better coverage) |
| **Low Risk** | Minimal changes to component structure — refactor, not rewrite |
| **Quick Win** | ~6 days vs 4 weeks in previous proposal |
| **Incremental** | Hook foundation enables future enhancements without rewrites |

---

## Future Enhancements (Deferred)

The following features from the **previous proposed approach** are explicitly deferred until there's a concrete requirement. Each has a clear trigger that would justify the implementation effort:

| Feature | Trigger to Implement |
|---------|---------------------|
| Headless component system | Third consumer of Gantt components |
| Theme token system | Need for white-label or customer theming |
| `useGanttZoom` hook | User feedback requesting zoom controls |
| `useGanttScroll` hook | Performance issues with wide timelines |
| Dependency arrows | Feature request for relationship visualization |
| ~~Virtualization~~ | ~~Datasets exceeding 200 activities~~ **MOVED TO PHASE 1** |
| Drag-to-edit | Interactive scheduling feature request |

---

## File Comparison

### Before (Current)
```
components/
├── GanttChart.tsx       (242 lines)  ← Contains duplicated timeline/positioning logic
├── GanttPanel.tsx       (366 lines)  ← Contains same logic + hierarchy handling
types/
└── schedule.ts          (122 lines)

Total: 730 lines, 2 components, ~80 lines duplicated
Problems: Duplication, no virtualization, untestable calculations
```

### After (Revised Proposal)
```
components/gantt/
├── index.ts             (~10 lines)   ← Clean public API
├── hooks/
│   ├── index.ts         (~5 lines)
│   ├── types.ts         (~40 lines)   ← Minimal new types
│   ├── useTimeline.ts   (~60 lines)   ← Extracted, testable
│   ├── useBarPositions.ts (~50 lines) ← Extracted, testable
│   └── useVirtualizedRows.ts (~40 lines) ← NEW: enables large datasets
├── GanttChart.tsx       (~180 lines)  ← Simplified, uses hooks
└── GanttPanel.tsx       (~320 lines)  ← Uses hooks + virtualized

Total: ~705 lines, 2 components + 3 hooks
Improvements: No duplication, virtualized, testable hooks
```
│   ├── useBarPositions.ts (~50 lines)
│   └── useVirtualizedRows.ts (~40 lines)
├── GanttChart.tsx       (~180 lines, refactored)
└── GanttPanel.tsx       (~320 lines, refactored + virtualized)

Total: ~705 lines, 2 components + 3 hooks + virtualization
```

**Note**: Slight line increase due to virtualization, but critical for 500-1000 activity performance.

### Previous Proposed Approach (Not Implemented)
```
components/gantt/        # TOO COMPLEX FOR CURRENT NEEDS
├── 27+ files
├── ~1,320 lines
└── 15+ components

Rejected: Over-architecture for 2 consumers, added complexity without proportional benefit
```

---

## Conclusion

This revised proposal takes a **pragmatic, needs-driven approach**:

1. **Extract hooks** to eliminate duplicated timeline and positioning logic (~80 lines of duplication removed)
2. **Add virtualization** to support the immediate requirement of 500-1000 activity datasets
3. **Preserve existing patterns** — Tailwind styling, component structure, print support all remain unchanged

The **previous proposed approach** with headless components, theme tokens, and render props was architecturally elegant but inappropriate for the current context:
- Only 2 consumers of Gantt components
- No white-label or theming requirements  
- No third-party integration needs

**What we gain:**
- Performance for large datasets (virtualization)
- Maintainability (DRY hooks)
- Testability (isolated calculation logic)

**What we avoid:**
- Over-abstraction (no headless component system)
- Parallel styling paradigms (no theme tokens)
- Unnecessary transformation layers (work with existing types)

The hook foundation established here provides a natural extension point if future requirements justify additional abstraction.
