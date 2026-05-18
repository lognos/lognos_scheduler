/**
 * SAGanttPanel Component (Schedule Assistant)
 *
 * Gantt chart panel with filters, hierarchy support, and virtualization.
 * Renders in three container variants driven by the workspace layout mode:
 *   - 'full'        : fills its parent (Mode A: gantt-full-chat-floating)
 *   - 'dockedRight' : fixed/absolute right-side panel (Mode C: chat-main-gantt-side)
 *   - 'dockedLeft'  : fixed/absolute left-side panel (Mode B: gantt-main-chat-side)
 *
 * Uses shared hooks for timeline and bar position calculations.
 * Virtualized for performance with 500-1000+ activities.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { format, isValid, parseISO, differenceInDays } from 'date-fns';
import { X, AlertTriangle, GitBranch, ChevronRight, ChevronDown, Printer, Maximize2, Columns2, PanelLeft, PanelRight } from 'lucide-react';
import { GanttChartData, ScheduleViewKey, ScheduleViewMeta, ActivityUpdate, BaselineMode } from '@/types/schedule';
import {
  SAWorkspaceMode,
  SAGanttContainerVariant,
  SAShellMode,
  SAWorkspaceLayoutActions,
} from '@/types/workspace';
import {
  useTimeline,
  useBarPositions,
  useActivityUpdates,
  PositionedItem,
  TimelineMonth,
  YearGroup,
  SortMode,
} from './hooks';
import { RelationshipArrows } from './RelationshipArrows';
import { executePrint } from '@/services/printService';
import ganttStyleSettings from './ganttStyleSettings';

interface SAGanttPanelProps {
  data: GanttChartData;
  onClose: () => void;
  width: number;
  onWidthChange: (width: number) => void;
  availableViews?: ScheduleViewMeta[];
  activeViewKey?: ScheduleViewKey;
  onSelectView?: (viewKey: ScheduleViewKey) => void;
  onBaselineModeChange?: (mode: BaselineMode) => void;
  isViewLoading?: boolean;
  /** Container variant driven by the workspace layout mode. */
  variant?: SAGanttContainerVariant;
  /** Workspace shell mode; in 'embedded' the docked variants use absolute (host-bound) positioning. */
  shellMode?: SAShellMode;
  /** Active workspace layout mode; drives which header layout actions are visible. */
  layoutMode?: SAWorkspaceMode;
  /** Layout mutation actions provided by the workspace. When omitted, layout buttons are hidden. */
  layoutActions?: SAWorkspaceLayoutActions;
}

/**
 * Floating Gantt chart panel that displays schedule data
 * streamed from the scheduling agent via AG-UI.
 */

function getSummaryKey(item: PositionedItem): string {
  return `${item.s_item_id}:${item.id}`;
}

function formatProjectDate(value?: string): string {
  if (!value) {
    return '—';
  }

  const parsed = parseISO(value);
  if (!isValid(parsed)) {
    return '—';
  }

  return format(parsed, 'MMM d, yyyy');
}

const ROW_HEIGHT_PX = 36;
const BASE_ACTIVITY_COLUMN_WIDTH = 192;
const OPTIONAL_COLUMN_WIDTH = 108;
const MIN_COLUMN_WIDTH = 60;
const MAX_ACTIVITY_COLUMN_WIDTH = 640;
const MAX_OPTIONAL_COLUMN_WIDTH = 180;
const HEADER_TEXT_FONT = '500 12px Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const ROW_TEXT_FONT = '500 12px Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const SUMMARY_TEXT_FONT = '600 12px Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const ACTIVITY_CELL_CHROME_WIDTH = 44;
const OPTIONAL_CELL_HORIZONTAL_PADDING = 20;
const MIN_TIMELINE_SCALE = 0.5;
const MAX_TIMELINE_SCALE = 6;
const TIMELINE_SCALE_DRAG_PX = 600;
const MIN_TIMELINE_WIDTH = 240;
const TIMELINE_PAD_MONTHS = 2;

type OptionalColumnKey = 'start' | 'finish' | 'duration' | 'float' | 'progress';
type ResizableColumnKey = 'name' | OptionalColumnKey;

/**
 * Visibility mode for relationship arrows.
 *  - 'none'     : hide all arrows
 *  - 'selected' : only arrows touching the currently selected activity
 *  - 'critical' : only critical-path arrows
 *  - 'all'      : every arrow whose endpoints are currently rendered (default)
 *
 * In every mode, arrows whose pred/succ are hidden by a collapsed summary are
 * already filtered out by `useRelationshipPaths` (endpoints absent from `items`).
 */
type LinksMode = 'none' | 'selected' | 'critical' | 'all';

const LINKS_MODE_OPTIONS: ReadonlyArray<{ key: LinksMode; label: string; title: string }> = [
  { key: 'none', label: 'None', title: 'Hide all relationship arrows' },
  { key: 'selected', label: 'Selected', title: 'Show arrows touching the selected activity (click a bar to select)' },
  { key: 'critical', label: 'Critical', title: 'Show only critical-path arrows' },
  { key: 'all', label: 'All', title: 'Show all arrows for currently visible activities' },
];

interface OptionalColumnOption {
  key: OptionalColumnKey;
  label: string;
}

const OPTIONAL_COLUMN_OPTIONS: OptionalColumnOption[] = [
  { key: 'start', label: 'Start' },
  { key: 'finish', label: 'Finish' },
  { key: 'duration', label: 'Duration' },
  { key: 'float', label: 'Float' },
  { key: 'progress', label: 'Complete (%)' },
];

const DEFAULT_VISIBLE_COLUMNS: OptionalColumnKey[] = ['start', 'finish', 'duration', 'float', 'progress'];

const OPTIONAL_COLUMN_MIN_WIDTHS: Record<OptionalColumnKey, number> = {
  start: 104,
  finish: 104,
  duration: 84,
  float: 76,
  progress: 96,
};

let textMeasureContext: CanvasRenderingContext2D | null = null;

function measureTextWidth(text: string, font: string): number {
  if (typeof document === 'undefined') {
    return text.length * 7;
  }

  if (!textMeasureContext) {
    textMeasureContext = document.createElement('canvas').getContext('2d');
  }

  if (!textMeasureContext) {
    return text.length * 7;
  }

  textMeasureContext.font = font;
  return textMeasureContext.measureText(text).width;
}

function getOptionalColumnLabel(column: OptionalColumnKey): string {
  return OPTIONAL_COLUMN_OPTIONS.find((option) => option.key === column)?.label ?? column;
}

type OptionalColumnValueItem = Pick<PositionedItem, 'start' | 'finish' | 'working_days' | 'total_float' | 'is_summary' | 'percent_complete' | 'status'>;

function formatOptionalColumnValue(item: OptionalColumnValueItem, column: OptionalColumnKey): string {
  switch (column) {
    case 'start':
      return formatProjectDate(item.start);
    case 'finish':
      return formatProjectDate(item.finish);
    case 'duration':
      return `${item.working_days.toFixed(1)}d`;
    case 'float':
      return `${item.total_float.toFixed(1)}d`;
    case 'progress': {
      if (item.is_summary) {
        return '—';
      }

      if (typeof item.percent_complete === 'number' && Number.isFinite(item.percent_complete)) {
        return `${Math.round(item.percent_complete)}%`;
      }

      if (item.status === 'completed') {
        return '100%';
      }

      if (item.status === 'not_started') {
        return '0%';
      }

      return '—';
    }
    default:
      return '—';
  }
}

function calculateInitialColumnWidths(items: GanttChartData['items']): {
  name: number;
  optional: Record<OptionalColumnKey, number>;
} {
  const activityHeaderWidth = measureTextWidth('Activity', HEADER_TEXT_FONT) + OPTIONAL_CELL_HORIZONTAL_PADDING;
  const nameContentWidth = items.reduce((maxWidth, item) => {
    const indentPx = ((item.level || 2) - 1) * 16;
    const itemFont = item.is_summary ? SUMMARY_TEXT_FONT : ROW_TEXT_FONT;
    const labelWidth = measureTextWidth(item.s_item, itemFont);
    const idWidth = measureTextWidth(String(item.s_item_id), ROW_TEXT_FONT);
    return Math.max(maxWidth, indentPx + ACTIVITY_CELL_CHROME_WIDTH + Math.max(labelWidth, idWidth));
  }, activityHeaderWidth);

  const optional = OPTIONAL_COLUMN_OPTIONS.reduce((widths, option) => {
    const headerWidth = measureTextWidth(option.label, HEADER_TEXT_FONT) + OPTIONAL_CELL_HORIZONTAL_PADDING;
    const contentWidth = items.reduce((maxWidth, item) => {
      const value = formatOptionalColumnValue(item, option.key);
      return Math.max(maxWidth, measureTextWidth(value, ROW_TEXT_FONT) + OPTIONAL_CELL_HORIZONTAL_PADDING);
    }, headerWidth);

    widths[option.key] = Math.ceil(Math.min(
      Math.max(OPTIONAL_COLUMN_MIN_WIDTHS[option.key], contentWidth),
      MAX_OPTIONAL_COLUMN_WIDTH,
    ));
    return widths;
  }, {} as Record<OptionalColumnKey, number>);

  return {
    name: Math.ceil(Math.min(Math.max(BASE_ACTIVITY_COLUMN_WIDTH, nameContentWidth), MAX_ACTIVITY_COLUMN_WIDTH)),
    optional,
  };
}

interface SummaryContextMeta {
  ancestorSummaryIndicesByIndex: number[][];
  summaryEndIndexByIndex: Map<number, number>;
}

function buildSummaryContextMeta(items: PositionedItem[]): SummaryContextMeta {
  const ancestorSummaryIndicesByIndex: number[][] = Array.from({ length: items.length }, () => []);
  const summaryEndIndexByIndex = new Map<number, number>();
  const summaryStack: Array<{ index: number; level: number }> = [];

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    const level = item.level ?? (item.is_summary ? 1 : 2);

    while (summaryStack.length > 0 && level <= summaryStack[summaryStack.length - 1].level) {
      const completedSummary = summaryStack.pop();
      if (completedSummary) {
        summaryEndIndexByIndex.set(completedSummary.index, index - 1);
      }
    }

    ancestorSummaryIndicesByIndex[index] = summaryStack.map((entry) => entry.index);

    if (item.is_summary) {
      summaryStack.push({ index, level });
    }
  }

  while (summaryStack.length > 0) {
    const completedSummary = summaryStack.pop();
    if (completedSummary) {
      summaryEndIndexByIndex.set(completedSummary.index, items.length - 1);
    }
  }

  return {
    ancestorSummaryIndicesByIndex,
    summaryEndIndexByIndex,
  };
}

function areSetsEqual(first: Set<string>, second: Set<string>): boolean {
  if (first.size !== second.size) {
    return false;
  }

  for (const value of first) {
    if (!second.has(value)) {
      return false;
    }
  }

  return true;
}

function clampTimelineScale(value: number): number {
  return Math.min(MAX_TIMELINE_SCALE, Math.max(MIN_TIMELINE_SCALE, value));
}

export const SAGanttPanel: React.FC<SAGanttPanelProps> = ({
  data,
  onClose,
  width,
  onWidthChange,
  variant = 'dockedRight',
  shellMode = 'standalone',
  layoutMode,
  layoutActions,
  availableViews = [],
  activeViewKey,
  onSelectView,
  onBaselineModeChange,
  isViewLoading = false,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const printableRef = useRef<HTMLDivElement>(null);
  const headerScrollRef = useRef<HTMLDivElement>(null);
  const [linksMode, setLinksMode] = useState<LinksMode>(
    () => (data.capabilities?.links?.render_enabled === false ? 'none' : 'all')
  );
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [showBaseline, setShowBaseline] = useState<boolean>(true);
  const [baselineMode, setBaselineMode] = useState<BaselineMode>(data.baseline_mode || 'own');

  // Sync linksMode when backend sends new data with render_enabled hint.
  // Only forces 'none' when the backend explicitly disables; otherwise preserves user choice.
  useEffect(() => {
    const backendHint = data.capabilities?.links?.render_enabled;
    if (backendHint === false) {
      setLinksMode('none');
    } else if (backendHint === true) {
      setLinksMode((prev) => (prev === 'none' ? 'all' : prev));
    }
  }, [data]);
  const [showUpdates, setShowUpdates] = useState<boolean>(true);
  const dragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const columnDragStateRef = useRef<{ column: ResizableColumnKey; startX: number; startWidth: number } | null>(null);
  const timelineScaleDragStateRef = useRef<{
    startX: number;
    startScale: number;
    anchorContentX: number;
    anchorFraction: number;
  } | null>(null);
  const [nameColumnWidth, setNameColumnWidth] = useState<number>(BASE_ACTIVITY_COLUMN_WIDTH);
  const [printableWidth, setPrintableWidth] = useState(0);
  const [timelineScale, setTimelineScale] = useState(1);
  const [optionalColumnWidths, setOptionalColumnWidths] = useState<Record<OptionalColumnKey, number>>({
    start: OPTIONAL_COLUMN_WIDTH,
    finish: OPTIONAL_COLUMN_WIDTH,
    duration: OPTIONAL_COLUMN_WIDTH,
    float: OPTIONAL_COLUMN_WIDTH,
    progress: OPTIONAL_COLUMN_WIDTH,
  });
  const [visibleColumns, setVisibleColumns] = useState<OptionalColumnKey[]>(DEFAULT_VISIBLE_COLUMNS);
  const [collapsedSummaryKeys, setCollapsedSummaryKeys] = useState<Set<string>>(new Set());
  const [isPrinting, setIsPrinting] = useState(false);
  const printButtonRef = useRef<HTMLButtonElement>(null);
  const columnAutoSizeKey = useMemo(() => {
    const source = data.view?.source;
    return [
      source?.project_id ?? 'project',
      source?.schedule_version_id ?? 'version',
      data.view?.id ?? data.view?.title ?? 'view',
      data.items.length,
      data.project_start,
      data.project_finish,
    ].join(':');
  }, [
    data.items.length,
    data.project_finish,
    data.project_start,
    data.view?.id,
    data.view?.source,
    data.view?.title,
  ]);

  const autoSizedColumnKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (autoSizedColumnKeyRef.current === columnAutoSizeKey) return;
    if (data.items.length === 0) return;

    const initialWidths = calculateInitialColumnWidths(data.items);
    setNameColumnWidth(initialWidths.name);
    setOptionalColumnWidths(initialWidths.optional);
    autoSizedColumnKeyRef.current = columnAutoSizeKey;
  }, [columnAutoSizeKey, data.items]);

  const activityColumnWidth = useMemo(
    () => nameColumnWidth + visibleColumns.reduce((sum, key) => sum + optionalColumnWidths[key], 0),
    [nameColumnWidth, visibleColumns, optionalColumnWidths]
  );

  const [scrollViewportEl, setScrollViewportEl] = useState<HTMLDivElement | null>(null);
  const attachScrollViewport = useCallback((el: HTMLDivElement | null) => {
    parentRef.current = el;
    setScrollViewportEl(el);
  }, []);

  useEffect(() => {
    if (!scrollViewportEl) {
      // Fallback to printable container only when the scroll viewport isn't mounted yet
      // (e.g. empty-state render). Measuring the printable container here is safe because
      // it has no scaled child while the empty state is shown.
      const printable = printableRef.current;
      if (!printable) return;

      const updatePrintableWidth = () => {
        const nextWidth = Math.round(printable.getBoundingClientRect().width);
        setPrintableWidth((previous) => (previous === nextWidth ? previous : nextWidth));
      };

      updatePrintableWidth();
      const observer = new ResizeObserver(updatePrintableWidth);
      observer.observe(printable);

      return () => observer.disconnect();
    }

    // Measure the actual scroll viewport (its clientWidth is independent of the scaled
    // inner canvas, so it cannot feed back into the timeline-scale calculation).
    const updateViewportWidth = () => {
      const nextWidth = Math.round(scrollViewportEl.clientWidth);
      setPrintableWidth((previous) => (previous === nextWidth ? previous : nextWidth));
    };

    updateViewportWidth();
    const observer = new ResizeObserver(updateViewportWidth);
    observer.observe(scrollViewportEl);

    return () => observer.disconnect();
  }, [scrollViewportEl]);

  const timelineViewportWidth = useMemo(
    () => Math.max(MIN_TIMELINE_WIDTH, (printableWidth || width || 0) - activityColumnWidth),
    [activityColumnWidth, printableWidth, width]
  );

  const timelineContentWidth = useMemo(
    () => Math.max(MIN_TIMELINE_WIDTH, timelineViewportWidth * timelineScale),
    [timelineScale, timelineViewportWidth]
  );

  const ganttContentWidth = activityColumnWidth + timelineContentWidth;

  const toggleVisibleColumn = (column: OptionalColumnKey) => {
    setVisibleColumns((previous) => {
      if (previous.includes(column)) {
        return previous.filter((current) => current !== column);
      }

      const ordered = OPTIONAL_COLUMN_OPTIONS
        .map((option) => option.key)
        .filter((key) => previous.includes(key) || key === column);

      return ordered;
    });
  };

  // Keep latest values reachable from the global mouse listeners without
  // re-creating those listeners on every render. Re-creating them caused a
  // race where a mouseup fired between cleanup and re-add was lost, leaving
  // the drag "stuck" so subsequent mouse moves kept scaling the timeline.
  const dragValuesRef = useRef({
    width,
    onWidthChange,
    activityColumnWidth,
    timelineViewportWidth,
  });
  useEffect(() => {
    dragValuesRef.current = { width, onWidthChange, activityColumnWidth, timelineViewportWidth };
  }, [activityColumnWidth, onWidthChange, timelineViewportWidth, width]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const dragState = dragStateRef.current;

      if (dragState) {
        const delta = dragState.startX - event.clientX;
        dragValuesRef.current.onWidthChange(dragState.startWidth + delta);
      }

      const columnDragState = columnDragStateRef.current;
      if (columnDragState) {
        const delta = event.clientX - columnDragState.startX;
        const nextWidth = Math.max(MIN_COLUMN_WIDTH, columnDragState.startWidth + delta);
        if (columnDragState.column === 'name') {
          setNameColumnWidth(nextWidth);
        } else {
          const key = columnDragState.column;
          setOptionalColumnWidths((prev) => ({ ...prev, [key]: nextWidth }));
        }
      }

      const timelineScaleDragState = timelineScaleDragStateRef.current;
      if (timelineScaleDragState) {
        const delta = event.clientX - timelineScaleDragState.startX;
        const nextScale = clampTimelineScale(
          timelineScaleDragState.startScale + (delta / TIMELINE_SCALE_DRAG_PX)
        );
        setTimelineScale(nextScale);

        // Zoom-at-cursor: keep the time point that was under the cursor at drag start
        // visually stationary so the user always sees what they are zooming into.
        const scrollEl = parentRef.current;
        if (scrollEl) {
          const { activityColumnWidth: ac, timelineViewportWidth: tv } = dragValuesRef.current;
          const newContentX = ac + timelineScaleDragState.anchorFraction * (tv * nextScale);
          scrollEl.scrollLeft = Math.max(0, Math.round(newContentX - timelineScaleDragState.anchorContentX));
        }
      }
    };

    const handleMouseUp = () => {
      dragStateRef.current = null;
      columnDragStateRef.current = null;
      timelineScaleDragStateRef.current = null;
      document.body.style.removeProperty('user-select');
      document.body.style.removeProperty('cursor');
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp, true); // capture phase: catch release before any child stops it
    // Defensive: mouseup outside the window (e.g. user releases on browser
    // chrome) does not fire on window. Listen on blur to clear stuck drags.
    const handleBlur = () => handleMouseUp();
    window.addEventListener('blur', handleBlur);
    // Pointer events fire even when the cursor leaves the window if it was
    // captured. Listening on them gives us a second, more reliable release.
    const handlePointerUp = () => handleMouseUp();
    window.addEventListener('pointerup', handlePointerUp, true);
    window.addEventListener('pointercancel', handlePointerUp, true);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp, true);
      window.removeEventListener('blur', handleBlur);
      window.removeEventListener('pointerup', handlePointerUp, true);
      window.removeEventListener('pointercancel', handlePointerUp, true);
      document.body.style.removeProperty('user-select');
      document.body.style.removeProperty('cursor');
    };
  }, []);

  const startResize = (event: React.MouseEvent<HTMLDivElement>) => {
    dragStateRef.current = {
      startX: event.clientX,
      startWidth: width,
    };

    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  };

  const startTimelineScaleDrag = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();

    // Capture the cursor position relative to the timeline content so we can
    // keep the same time point under the cursor while scaling.
    const scrollEl = parentRef.current;
    const scrollLeft = scrollEl?.scrollLeft ?? 0;
    const scrollRect = scrollEl?.getBoundingClientRect();
    const anchorContentX = scrollRect
      ? Math.max(0, event.clientX - scrollRect.left)
      : 0;
    const currentTimelineWidth = Math.max(MIN_TIMELINE_WIDTH, timelineViewportWidth * timelineScale);
    const timelineOffsetWithinContent = scrollLeft + anchorContentX - activityColumnWidth;
    const anchorFraction = currentTimelineWidth > 0
      ? Math.min(1, Math.max(0, timelineOffsetWithinContent / currentTimelineWidth))
      : 0;

    timelineScaleDragStateRef.current = {
      startX: event.clientX,
      startScale: timelineScale,
      anchorContentX,
      anchorFraction,
    };

    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ew-resize';
  }, [activityColumnWidth, timelineScale, timelineViewportWidth]);

  const startColumnResize = (column: ResizableColumnKey) => (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const startWidth = column === 'name' ? nameColumnWidth : optionalColumnWidths[column];
    columnDragStateRef.current = {
      column,
      startX: event.clientX,
      startWidth,
    };

    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  };

  // Boundary x-positions for per-column resize handles (cumulative from left).
  // The last boundary equals activityColumnWidth (section/timeline divider).
  const columnBoundaries = useMemo(() => {
    const boundaries: Array<{ key: ResizableColumnKey; x: number }> = [];
    let x = nameColumnWidth;
    boundaries.push({ key: 'name', x });
    for (const key of visibleColumns) {
      x += optionalColumnWidths[key];
      boundaries.push({ key, x });
    }
    return boundaries;
  }, [nameColumnWidth, visibleColumns, optionalColumnWidths]);

  // Use shared hooks
  const timeline = useTimeline({
    items: data.items,
    projectStart: data.project_start,
    projectEnd: data.project_finish,
    padMonths: TIMELINE_PAD_MONTHS,
  });

  // Determine sort mode based on data characteristics
  const sortMode: SortMode = data.preserve_order
    ? 'preserve' // MS Project: keep WBS hierarchy
    : data.grouping
      ? 'grouped' // P6 with grouping: group-aware sort
      : 'start-date'; // P6 ungrouped: simple chronological

  const positionedItems = useBarPositions({
    items: data.items,
    timelineStartDate: timeline.startDate,
    totalDays: timeline.totalDays,
    sortMode,
  });

  const updatesMap = useActivityUpdates(data.activity_updates);
  const baselineUpdatesMap = useActivityUpdates(data.baseline_activity_updates);

  const fitTimelineToProject = useCallback(() => {
    if (timeline.totalDays <= 0) return;
    // Fit the entire (padded) timeline content to the viewport width.
    // That makes the project bars occupy the visual screen width with a small
    // padding margin on each side, instead of extending well past the viewport.
    setTimelineScale(1);
    requestAnimationFrame(() => {
      const scrollEl = parentRef.current;
      if (!scrollEl) return;
      scrollEl.scrollLeft = 0;
    });
  }, [timeline.totalDays]);

  const collapsibleSummaryKeys = useMemo(() => {
    const keys = new Set<string>();

    for (let index = 0; index < positionedItems.length; index += 1) {
      const current = positionedItems[index];
      if (!current.is_summary) {
        continue;
      }

      const currentLevel = current.level ?? 1;
      const next = positionedItems[index + 1];
      if (next && (next.level ?? 2) > currentLevel) {
        keys.add(getSummaryKey(current));
      }
    }

    return keys;
  }, [positionedItems]);

  useEffect(() => {
    setCollapsedSummaryKeys((previous) => {
      const next = new Set([...previous].filter((key) => collapsibleSummaryKeys.has(key)));
      return next.size === previous.size ? previous : next;
    });
  }, [collapsibleSummaryKeys]);

  const toggleSummaryCollapse = (summaryKey: string) => {
    setCollapsedSummaryKeys((previous) => {
      const next = new Set(previous);
      if (next.has(summaryKey)) {
        next.delete(summaryKey);
      } else {
        next.add(summaryKey);
      }
      return next;
    });
  };

  const collapseAllSummaries = () => {
    setCollapsedSummaryKeys(new Set(collapsibleSummaryKeys));
  };

  const level2CollapsibleSummaryKeys = useMemo(() => {
    const level2Keys = new Set<string>();

    for (const item of positionedItems) {
      if (!item.is_summary) {
        continue;
      }

      const level = item.level ?? 1;
      if (level === 2 && collapsibleSummaryKeys.has(getSummaryKey(item))) {
        level2Keys.add(getSummaryKey(item));
      }
    }

    return level2Keys;
  }, [positionedItems, collapsibleSummaryKeys]);

  const collapseLevel2Summaries = () => {
    setCollapsedSummaryKeys(new Set(level2CollapsibleSummaryKeys));
  };

  const expandAllSummaries = () => {
    setCollapsedSummaryKeys(new Set());
  };

  const hasCollapsibleSummaries = collapsibleSummaryKeys.size > 0;
  const hasCollapsedSummaries = collapsedSummaryKeys.size > 0;
  const isCollapseAllState = hasCollapsibleSummaries && collapsedSummaryKeys.size === collapsibleSummaryKeys.size;
  const isLevel2State = level2CollapsibleSummaryKeys.size > 0 && areSetsEqual(collapsedSummaryKeys, level2CollapsibleSummaryKeys);
  const isExpandAllState = collapsedSummaryKeys.size === 0;
  const relationships = useMemo(() => data.relationships ?? [], [data.relationships]);

  // Filter relationships by current display mode.
  // The hook still drops paths whose endpoints aren't in `visibleItems` (collapsed branches),
  // so this only narrows the candidate set for performance and clarity.
  const displayRelationships = useMemo(() => {
    if (linksMode === 'none' || relationships.length === 0) return [];
    if (linksMode === 'critical') return relationships.filter((r) => r.is_critical);
    if (linksMode === 'selected') {
      if (!selectedItemId) return [];
      return relationships.filter(
        (r) => String(r.pred_id) === selectedItemId || String(r.succ_id) === selectedItemId,
      );
    }
    return relationships;
  }, [linksMode, relationships, selectedItemId]);

  const activeView = activeViewKey
    ? availableViews.find((view) => view.view_key === activeViewKey)
    : null;

  const hasLevel2CollapsibleSummaries = useMemo(
    () => positionedItems.some(
      (item) => item.is_summary && (item.level ?? 1) === 2 && collapsibleSummaryKeys.has(getSummaryKey(item))
    ),
    [positionedItems, collapsibleSummaryKeys]
  );

  const visibleItems = useMemo(() => {
    const items: PositionedItem[] = [];
    const collapsedLevels: number[] = [];

    for (const item of positionedItems) {
      const level = item.level ?? (item.is_summary ? 1 : 2);

      while (collapsedLevels.length > 0 && level <= collapsedLevels[collapsedLevels.length - 1]) {
        collapsedLevels.pop();
      }

      const isHiddenByParent = collapsedLevels.length > 0;
      if (!isHiddenByParent) {
        items.push(item);
      }

      if (item.is_summary && collapsedSummaryKeys.has(getSummaryKey(item))) {
        collapsedLevels.push(level);
      }
    }

    return items;
  }, [positionedItems, collapsedSummaryKeys]);

  const handlePrint = useCallback(() => {
    // Set isPrinting = true so the virtualizer renders ALL rows.
    // The useEffect below will call executePrint once rows are rendered.
    setIsPrinting(true);
  }, []);

  // When isPrinting becomes true and the virtualizer has rendered all rows,
  // execute the native print flow, then reset.
  useEffect(() => {
    if (!isPrinting) return;

    // Wait two frames for the virtualizer to expand and render all rows
    let cancelled = false;
    const run = async () => {
      await new Promise((r) => requestAnimationFrame(r));
      await new Promise((r) => requestAnimationFrame(r));
      // Extra settle for large DOM expansion
      await new Promise((r) => setTimeout(r, 150));
      if (cancelled) return;

      const projectId = data.view?.source?.project_id;
      const versionId = data.view?.source?.schedule_version_id;
      const projectLabel = projectId ? `Project ${projectId}` : (data.view?.title ?? 'Schedule');
      const versionLabel = versionId ? `v${versionId}` : undefined;

      try {
        await executePrint({
          projectName: projectLabel,
          versionLabel,
          viewName: activeView?.view_name,
          itemCount: visibleItems.length,
          projectStart: data.project_start,
          projectFinish: data.project_finish,
          grouping: data.grouping,
        });
      } finally {
        setIsPrinting(false);
      }
    };

    run();
    return () => { cancelled = true; };
  }, [isPrinting, data, activeView, visibleItems.length]);

  const headerMetaItems = useMemo(
    () => [
      { label: 'Start', value: formatProjectDate(data.project_start) },
      { label: 'Finish', value: formatProjectDate(data.project_finish) },
      { label: 'Critical Path', value: `${data.critical_path_length.toFixed(1)} days` },
      { label: 'Visible', value: `${visibleItems.length}` },
      { label: 'Filtered', value: `${data.filtered_activities}` },
      { label: 'Total', value: `${data.total_activities}` },
    ],
    [
      data.project_start,
      data.project_finish,
      data.critical_path_length,
      data.filtered_activities,
      data.total_activities,
      visibleItems.length,
    ]
  );

  // Virtualization for large datasets
  const rowVirtualizer = useVirtualizer({
    count: visibleItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_PX,
    overscan: isPrinting ? visibleItems.length : 10,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const scrollTop = parentRef.current?.scrollTop ?? 0;

  const syncHeaderScroll = useCallback((scrollLeft: number) => {
    if (headerScrollRef.current) {
      headerScrollRef.current.scrollLeft = scrollLeft;
    }
  }, []);

  // Track horizontal scroll so we can clip the relationship arrows overlay to
  // the area not covered by the sticky activity columns. Without this clipping,
  // overlay paths drawn at container-x coordinates near `activityColumnWidth`
  // end up painting behind the sticky columns once the body is scrolled right,
  // because the overlay's container coords stay fixed while its screen-space
  // position slides under the pinned columns.
  const [bodyScrollLeft, setBodyScrollLeft] = useState(0);

  const handleBodyScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const left = event.currentTarget.scrollLeft;
    syncHeaderScroll(left);
    setBodyScrollLeft(left);
  }, [syncHeaderScroll]);

  useEffect(() => {
    syncHeaderScroll(parentRef.current?.scrollLeft ?? 0);
  }, [ganttContentWidth, syncHeaderScroll]);

  const navigateToActivity = useCallback((sItemId: string) => {
    const targetIndex = visibleItems.findIndex((item) => String(item.s_item_id) === String(sItemId));
    if (targetIndex < 0) {
      return;
    }

    setSelectedItemId(String(sItemId));
    rowVirtualizer.scrollToIndex(targetIndex, { align: 'center' });
  }, [visibleItems, rowVirtualizer]);

  // Viewport-aware relationship culling: only keep arrows whose predecessor OR
  // successor is currently rendered (within the virtualizer window + buffer).
  // Without this, long-vertical arrows from off-screen rows still cut through
  // the visible area because their SVG paths are computed for every visibleItem.
  const VIEWPORT_REL_BUFFER_ROWS = 8;
  const viewportItemIds = useMemo(() => {
    if (isPrinting || virtualRows.length === 0) {
      // When printing (or no virtual rows yet), allow all visibleItems.
      return null;
    }
    const firstIdx = Math.max(0, virtualRows[0].index - VIEWPORT_REL_BUFFER_ROWS);
    const lastIdx = Math.min(
      visibleItems.length - 1,
      virtualRows[virtualRows.length - 1].index + VIEWPORT_REL_BUFFER_ROWS,
    );
    const ids = new Set<string>();
    for (let i = firstIdx; i <= lastIdx; i += 1) {
      const item = visibleItems[i];
      if (item) ids.add(String(item.s_item_id));
    }
    return ids;
  }, [virtualRows, visibleItems, isPrinting]);

  const viewportRelationships = useMemo(() => {
    if (!viewportItemIds || displayRelationships.length === 0) return displayRelationships;
    return displayRelationships.filter(
      (r) => viewportItemIds.has(String(r.pred_id)) || viewportItemIds.has(String(r.succ_id)),
    );
  }, [displayRelationships, viewportItemIds]);

  const summaryContextMeta = useMemo(() => buildSummaryContextMeta(visibleItems), [visibleItems]);

  const stickySummaryIndices = useMemo(() => {
    if (visibleItems.length === 0) {
      return [];
    }
    const stickyAncestors: number[] = [];

    for (let slot = 0; slot < visibleItems.length; slot += 1) {
      const probeY = scrollTop + (slot * ROW_HEIGHT_PX);
      const probeIndex = Math.min(Math.floor(probeY / ROW_HEIGHT_PX), visibleItems.length - 1);
      const probeItem = visibleItems[probeIndex];
      const probeAncestors = summaryContextMeta.ancestorSummaryIndicesByIndex[probeIndex] ?? [];
      const probePath = probeItem?.is_summary ? [...probeAncestors, probeIndex] : probeAncestors;

      if (probePath.length <= slot) {
        break;
      }

      const summaryIndex = probePath[slot];
      const endIndex = summaryContextMeta.summaryEndIndexByIndex.get(summaryIndex);
      if (endIndex === undefined || probeIndex > endIndex) {
        break;
      }

      const summaryTop = summaryIndex * ROW_HEIGHT_PX;
      const freezeThreshold = scrollTop + (slot * ROW_HEIGHT_PX);

      if (summaryTop < freezeThreshold) {
        stickyAncestors.push(summaryIndex);
      } else {
        break;
      }
    }

    return stickyAncestors;
  }, [visibleItems, summaryContextMeta, scrollTop]);

  const stickySummaryItems = useMemo(
    () => stickySummaryIndices.map((summaryIndex) => visibleItems[summaryIndex]).filter(Boolean),
    [stickySummaryIndices, visibleItems]
  );

  const stickyStackHeight = stickySummaryItems.length * ROW_HEIGHT_PX;

  // Container variant -> outer className/style.
  // - 'full'        : fills its parent (workspace canvas)
  // - 'dockedRight' : right-docked panel (standalone=fixed; embedded=absolute, host-bound)
  // - 'dockedLeft'  : left-docked panel (mirror of dockedRight)
  const positioningClass = shellMode === 'embedded' ? 'absolute' : 'fixed';
  const containerClass =
    variant === 'full'
      ? 'relative w-full flex-1 min-h-0 bg-[#0d1117] z-10 flex flex-col overflow-hidden'
      : variant === 'dockedLeft'
        ? `${positioningClass} top-20 left-8 bottom-30 bg-[#0d1117] border border-dark-700 rounded-xl shadow-2xl z-50 flex flex-col overflow-hidden`
        : `${positioningClass} top-20 right-8 bottom-30 bg-[#0d1117] border border-dark-700 rounded-xl shadow-2xl z-50 flex flex-col overflow-hidden`;
  const containerStyle = variant === 'full' ? undefined : { width: `${width}px` };

  // Width-resize handle position depends on which side the panel is docked to.
  // 'dockedRight' resizes from its left edge (existing behavior).
  // 'dockedLeft'  resizes from its right edge.
  // 'full'        has no width handle.
  const showWidthHandle = variant !== 'full';
  const widthHandleClass =
    variant === 'dockedLeft'
      ? 'absolute right-0 top-0 bottom-0 w-2 cursor-col-resize z-20'
      : 'absolute left-0 top-0 bottom-0 w-2 cursor-col-resize z-20';

  // Hide the X close action in 'gantt-full-chat-floating' (Mode A): closing
  // would leave an empty workspace canvas. In other modes the X keeps its
  // existing behavior of hiding the Gantt panel entirely.
  const showCloseButton = layoutMode !== 'gantt-full-chat-floating';

  // Layout action availability per current mode.
  const showMakeFull = !!layoutActions && layoutMode !== 'gantt-full-chat-floating';
  const showMakeSplit = !!layoutActions && layoutMode === 'gantt-full-chat-floating';
  const showSwapLeft = !!layoutActions && layoutMode === 'gantt-main-chat-side';
  const showSwapRight = !!layoutActions && layoutMode === 'chat-main-gantt-side';

  return (
    <div
      data-gantt-panel-root
      className={containerClass}
      style={containerStyle}
    >
      {showWidthHandle && (
        <div
          className={widthHandleClass}
          onMouseDown={startResize}
          aria-hidden="true"
        />
      )}

      <div data-gantt-no-print className="relative z-40 px-4 py-2 bg-[#0d1117] border-b border-dark-700 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {availableViews.length > 0 && (
              <div className="relative group">
                <button
                  type="button"
                  className={`px-2.5 py-1 rounded-full border transition-colors border-dark-600 text-gray-300 hover:bg-dark-700/60 ${isViewLoading ? 'opacity-70 cursor-not-allowed' : ''}`}
                  title="View options"
                  disabled={isViewLoading}
                >
                  {activeView ? activeView.view_name : 'View'}
                </button>

                <div className="absolute left-0 top-full mt-1 min-w-40 rounded-md border border-dark-600 bg-[#0d1117] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-50">
                  {availableViews.map((view, index) => {
                    const isActive = activeViewKey === view.view_key;
                    return (
                      <button
                        key={view.view_key}
                        type="button"
                        onClick={() => onSelectView?.(view.view_key)}
                        disabled={isViewLoading}
                        className={`w-full text-left px-3 py-2 text-xs transition-colors disabled:text-gray-600 disabled:hover:bg-transparent ${
                          isActive
                            ? 'text-blue-300 bg-blue-500/10'
                            : 'text-gray-200 hover:bg-dark-700/70'
                        } ${index === 0 ? 'rounded-t-md' : ''} ${index === availableViews.length - 1 ? 'rounded-b-md' : ''}`}
                      >
                          <span className="mr-2">{isActive ? '●' : '○'}</span>
                        {view.view_name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="relative group">
              <button
                type="button"
                className="px-2.5 py-1 rounded-full border transition-colors border-dark-600 text-gray-300 hover:bg-dark-700/60"
                title="Visible columns"
              >
                Show
              </button>

              <div className="absolute left-0 top-full mt-1 min-w-44 rounded-md border border-dark-600 bg-[#0d1117] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-50">
                {OPTIONAL_COLUMN_OPTIONS.map((column, index) => {
                  const isActive = visibleColumns.includes(column.key);
                  return (
                    <button
                      key={column.key}
                      type="button"
                      onClick={() => toggleVisibleColumn(column.key)}
                      className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                        isActive
                          ? 'text-blue-300 bg-blue-500/10'
                          : 'text-gray-200 hover:bg-dark-700/70'
                      } ${index === 0 ? 'rounded-t-md' : ''} ${index === OPTIONAL_COLUMN_OPTIONS.length - 1 ? 'rounded-b-md' : ''}`}
                    >
                      <span className="mr-2">{isActive ? '●' : '○'}</span>
                      {column.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {hasCollapsibleSummaries && (
              <div className="relative group">
                <button
                  type="button"
                  className="px-2.5 py-1 rounded-full border transition-colors border-dark-600 text-gray-300 hover:bg-dark-700/60"
                  title="Collapse options"
                >
                  Collapse
                </button>

                <div className="absolute right-0 top-full mt-1 w-36 rounded-md border border-dark-600 bg-[#0d1117] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-50">
                  <button
                    type="button"
                    onClick={collapseAllSummaries}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-dark-700/70 rounded-t-md disabled:text-gray-600 disabled:hover:bg-transparent"
                    disabled={collapsedSummaryKeys.size === collapsibleSummaryKeys.size}
                  >
                    <span className="mr-2">{isCollapseAllState ? '●' : '○'}</span>
                    Collapse all
                  </button>
                  <button
                    type="button"
                    onClick={collapseLevel2Summaries}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-dark-700/70 disabled:text-gray-600 disabled:hover:bg-transparent"
                    disabled={!hasLevel2CollapsibleSummaries}
                  >
                    <span className="mr-2">{isLevel2State ? '●' : '○'}</span>
                    Level 2
                  </button>
                  <button
                    type="button"
                    onClick={expandAllSummaries}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-dark-700/70 rounded-b-md disabled:text-gray-600 disabled:hover:bg-transparent"
                    disabled={!hasCollapsedSummaries}
                  >
                    <span className="mr-2">{isExpandAllState ? '●' : '○'}</span>
                    Expand all
                  </button>
                </div>
              </div>
            )}

            {relationships.length > 0 && (
              <div className="relative group">
                <button
                  type="button"
                  onClick={() => setLinksMode((previous) => (previous === 'none' ? 'all' : 'none'))}
                  className={`h-[26px] px-2 rounded-full border flex items-center gap-1 text-xs transition-colors ${
                    linksMode !== 'none'
                      ? 'border-blue-500 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20'
                      : 'border-dark-600 text-gray-500 hover:bg-dark-700/60'
                  }`}
                  title={linksMode !== 'none' ? 'Hide links' : 'Show links'}
                  aria-label={linksMode !== 'none' ? 'Hide links' : 'Show links'}
                >
                  <GitBranch className="h-3.5 w-3.5" />
                  <span>
                    {linksMode === 'none'
                      ? 'Links'
                      : linksMode === 'selected'
                        ? 'Links (Selected)'
                        : linksMode === 'critical'
                          ? 'Links (Critical)'
                          : 'Links (All)'}
                  </span>
                </button>

                <div className="absolute left-0 top-full mt-1 min-w-44 rounded-md border border-dark-600 bg-[#0d1117] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-50">
                  {LINKS_MODE_OPTIONS.map((opt, index) => {
                    const disabled = opt.key === 'selected' && selectedItemId === null;
                    return (
                      <button
                        key={opt.key}
                        type="button"
                        disabled={disabled}
                        onClick={() => setLinksMode(opt.key)}
                        title={opt.title}
                        className={`w-full text-left px-3 py-2 text-xs transition-colors disabled:text-gray-600 disabled:cursor-not-allowed disabled:hover:bg-transparent ${
                          linksMode === opt.key
                            ? 'text-blue-300 bg-blue-500/10'
                            : 'text-gray-200 hover:bg-dark-700/70'
                        } ${index === 0 ? 'rounded-t-md' : ''} ${index === LINKS_MODE_OPTIONS.length - 1 ? 'rounded-b-md' : ''}`}
                      >
                        <span className="mr-2">{linksMode === opt.key ? '●' : '○'}</span>
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {data.has_baseline && (
              <div className="relative group">
                <button
                  type="button"
                  onClick={() => setShowBaseline((previous) => !previous)}
                  className={`h-[26px] px-2 rounded-full border flex items-center gap-1 text-xs transition-colors ${
                    showBaseline
                      ? 'border-blue-500 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20'
                      : 'border-dark-600 text-gray-500 hover:bg-dark-700/60'
                  }`}
                  title={showBaseline ? 'Hide baseline' : 'Show baseline'}
                >
                  {baselineMode === 'what_if' ? 'Baseline (What-If)' : baselineMode === 'own' ? 'Baseline' : baselineMode === 'previous_version' ? 'Baseline (Prev)' : 'Baseline (DB)'}
                </button>

                <div className="absolute left-0 top-full mt-1 min-w-48 rounded-md border border-dark-600 bg-[#0d1117] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-50">
                  {([
                    { mode: 'what_if' as BaselineMode, label: 'What-If Baseline', available: data.available_baseline_modes?.what_if ?? false },
                    { mode: 'own' as BaselineMode, label: 'Own Baseline', available: data.available_baseline_modes?.own ?? true },
                    { mode: 'previous_version' as BaselineMode, label: `Previous Version${data.baseline_mode === 'previous_version' && data.baseline_label ? ` (${data.baseline_label})` : ''}`, available: data.available_baseline_modes?.previous_version ?? false },
                    { mode: 'database_baseline' as BaselineMode, label: `Database Baseline${data.baseline_mode === 'database_baseline' && data.baseline_label ? ` (${data.baseline_label})` : ''}`, available: data.available_baseline_modes?.database_baseline ?? false },
                  ]).map((opt, index) => (
                    <button
                      key={opt.mode}
                      type="button"
                      disabled={!opt.available || isViewLoading}
                      onClick={() => {
                        if (opt.mode !== baselineMode) {
                          setBaselineMode(opt.mode);
                          setShowBaseline(true);
                          onBaselineModeChange?.(opt.mode);
                        }
                      }}
                      className={`w-full text-left px-3 py-2 text-xs transition-colors disabled:text-gray-600 disabled:cursor-not-allowed disabled:hover:bg-transparent ${
                        baselineMode === opt.mode
                          ? 'text-blue-300 bg-blue-500/10'
                          : 'text-gray-200 hover:bg-dark-700/70'
                      } ${index === 0 ? 'rounded-t-md' : ''} ${index === 3 ? 'rounded-b-md' : ''}`}
                    >
                      <span className="mr-2">{baselineMode === opt.mode ? '●' : '○'}</span>
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {updatesMap.hasUpdates && (
              <button
                type="button"
                onClick={() => setShowUpdates((previous) => !previous)}
                className={`h-[26px] px-2 rounded-full border flex items-center gap-1 text-xs transition-colors ${
                  showUpdates
                    ? 'border-blue-500 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20'
                    : 'border-dark-600 text-gray-500 hover:bg-dark-700/60'
                }`}
                title={showUpdates ? 'Hide updates' : 'Show updates'}
              >
                Updates
              </button>
            )}

            {isViewLoading && <span className="text-gray-500">Loading view...</span>}

            {/* Print, layout, and close controls. */}
            <div className="flex items-center gap-1 ml-1 pl-2 border-l border-dark-700">
              <button
                ref={printButtonRef}
                type="button"
                onClick={handlePrint}
                disabled={visibleItems.length === 0 || isViewLoading}
                className={`p-1 rounded transition-colors ${
                  visibleItems.length === 0 || isViewLoading
                    ? 'opacity-30 cursor-not-allowed text-gray-400'
                    : 'text-gray-400 hover:text-white hover:bg-dark-700'
                }`}
                title="Print schedule"
                aria-label="Print schedule"
              >
                <Printer className="h-4 w-4" />
              </button>
              {showMakeFull && (
                <button
                  type="button"
                  onClick={layoutActions!.makeGanttFull}
                  className="p-1 text-gray-400 hover:text-white hover:bg-dark-700 rounded transition-colors"
                  title="Make Gantt full (chat floats)"
                  aria-label="Make Gantt full"
                >
                  <Maximize2 className="h-4 w-4" />
                </button>
              )}
              {showMakeSplit && (
                <button
                  type="button"
                  onClick={layoutActions!.makeSplit}
                  className="p-1 text-gray-400 hover:text-white hover:bg-dark-700 rounded transition-colors"
                  title="Pin chat to side (split view)"
                  aria-label="Pin chat to side"
                >
                  <Columns2 className="h-4 w-4" />
                </button>
              )}
              {showSwapLeft && (
                <button
                  type="button"
                  onClick={layoutActions!.swapSides}
                  className="p-1 text-gray-400 hover:text-white hover:bg-dark-700 rounded transition-colors"
                  title="Move Gantt to right"
                  aria-label="Move Gantt to right"
                >
                  <PanelLeft className="h-4 w-4" />
                </button>
              )}
              {showSwapRight && (
                <button
                  type="button"
                  onClick={layoutActions!.swapSides}
                  className="p-1 text-gray-400 hover:text-white hover:bg-dark-700 rounded transition-colors"
                  title="Move Gantt to left"
                  aria-label="Move Gantt to left"
                >
                  <PanelRight className="h-4 w-4" />
                </button>
              )}
              {showCloseButton && (
                <button
                  onClick={onClose}
                  className="p-1 hover:bg-dark-700 rounded transition-colors"
                  aria-label="Close panel"
                >
                  <X className="h-4 w-4 text-gray-400 hover:text-white" />
                </button>
              )}
            </div>
          </div>
        </div>

      {/* Gantt chart content */}
      <div className="flex-1 flex flex-col overflow-hidden p-4 min-w-0">
        {positionedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <AlertTriangle className="h-8 w-8 mb-2" />
            <p>No activities match the current filter</p>
          </div>
        ) : (
          <div ref={printableRef} data-gantt-printable className="min-w-0 flex flex-col flex-1 overflow-hidden relative">
            {columnBoundaries.map((boundary) => (
              <div
                key={`resize-${boundary.key}`}
                data-gantt-no-print
                className="absolute top-0 bottom-0 w-2 cursor-col-resize z-20 hover:bg-blue-500/20 transition-colors"
                style={{ left: `${boundary.x - 4}px` }}
                onMouseDown={startColumnResize(boundary.key)}
                aria-label={
                  boundary.key === 'name'
                    ? 'Resize activity name column'
                    : `Resize ${boundary.key} column`
                }
                role="separator"
                aria-orientation="vertical"
              />
            ))}
            {/* Timeline header - STICKY, not virtualized */}
            <div ref={headerScrollRef} className="sticky top-0 z-10 bg-[#0d1117] overflow-hidden">
              <TimelineHeader
                months={timeline.months}
                yearGroups={timeline.yearGroups}
                activityColumnWidth={activityColumnWidth}
                nameColumnWidth={nameColumnWidth}
                visibleColumns={visibleColumns}
                optionalColumnWidths={optionalColumnWidths}
                timelineContentWidth={timelineContentWidth}
                ganttContentWidth={ganttContentWidth}
                timelineScale={timelineScale}
                onTimelineScaleMouseDown={startTimelineScaleDrag}
                onTimelineDoubleClick={fitTimelineToProject}
              />
            </div>

            {/* Virtualized body - scrollable */}
            <div ref={attachScrollViewport} className="flex-1 overflow-auto min-w-0" onScroll={handleBodyScroll}>
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: `${ganttContentWidth}px`,
                  position: 'relative',
                }}
              >
                {stickySummaryItems.length > 0 && (
                  <div
                    data-gantt-no-print
                    className="sticky top-0 z-30"
                    style={{ height: `${stickyStackHeight}px` }}
                  >
                    {stickySummaryItems.map((item, index) => {
                      const summaryKey = getSummaryKey(item);
                      const canCollapse = item.is_summary === true && collapsibleSummaryKeys.has(summaryKey);
                      const isCollapsed = canCollapse && collapsedSummaryKeys.has(summaryKey);

                      return (
                        <div
                          key={`sticky-${item.id}-${index}`}
                          className="absolute left-0 right-0"
                          style={{
                            top: `${index * ROW_HEIGHT_PX}px`,
                            height: `${ROW_HEIGHT_PX}px`,
                          }}
                        >
                          <HierarchicalRow
                            item={item}
                            activityColumnWidth={activityColumnWidth}
                            nameColumnWidth={nameColumnWidth}
                            visibleColumns={visibleColumns}
                            optionalColumnWidths={optionalColumnWidths}
                            canCollapse={canCollapse}
                            isCollapsed={isCollapsed}
                            onToggleCollapse={() => toggleSummaryCollapse(summaryKey)}
                            showBaseline={showBaseline && !!data.has_baseline}
                            activityUpdates={showUpdates ? updatesMap.byActivity.get(item.s_item_id) : undefined}
                            baselineActivityUpdates={showUpdates ? baselineUpdatesMap.byActivity.get(item.s_item_id) : undefined}
                            isSelected={selectedItemId === String(item.s_item_id)}
                            onSelect={(id) => setSelectedItemId((prev) => (prev === id ? null : id))}
                          />
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Activity rows */}
                {virtualRows.map((virtualRow) => {
                  const item = visibleItems[virtualRow.index];
                  const summaryKey = getSummaryKey(item);
                  const canCollapse = item.is_summary === true && collapsibleSummaryKeys.has(summaryKey);
                  const isCollapsed = canCollapse && collapsedSummaryKeys.has(summaryKey);

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
                      <HierarchicalRow
                        item={item}
                        activityColumnWidth={activityColumnWidth}
                        nameColumnWidth={nameColumnWidth}
                        visibleColumns={visibleColumns}
                        optionalColumnWidths={optionalColumnWidths}
                        canCollapse={canCollapse}
                        isCollapsed={isCollapsed}
                        onToggleCollapse={() => toggleSummaryCollapse(summaryKey)}
                        showBaseline={showBaseline && !!data.has_baseline}
                        activityUpdates={showUpdates ? updatesMap.byActivity.get(item.s_item_id) : undefined}
                        baselineActivityUpdates={showUpdates ? baselineUpdatesMap.byActivity.get(item.s_item_id) : undefined}
                        isSelected={selectedItemId === String(item.s_item_id)}
                        onSelect={(id) => setSelectedItemId((prev) => (prev === id ? null : id))}
                      />
                    </div>
                  );
                })}

                {/* Relationship arrows overlay - positioned over timeline area only */}
                {viewportRelationships.length > 0 && (
                  <div 
                    className="absolute top-0 bottom-0 overflow-hidden"
                    style={{ 
                      left: `${activityColumnWidth}px`,
                      width: `${timelineContentWidth}px`,
                      // Clip the leftmost portion equal to the current scroll
                      // offset so the overlay never paints in the screen-space
                      // region occupied by the sticky activity columns.
                      clipPath: `inset(0 0 0 ${Math.max(0, Math.min(timelineContentWidth, bodyScrollLeft))}px)`,
                      zIndex: 2,
                    }}
                  >
                    <RelationshipArrows
                      items={visibleItems}
                      relationships={viewportRelationships}
                      rowHeight={ROW_HEIGHT_PX}
                      showCriticalOnly={false}
                      totalHeight={rowVirtualizer.getTotalSize()}
                      onNavigateToActivity={navigateToActivity}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <Legend
        grouping={data.grouping}
        hasRelationships={relationships.length > 0}
        hasBaseline={!!data.has_baseline}
        showBaseline={showBaseline}
        baselineMode={baselineMode}
        baselineLabel={data.baseline_label}
        hasUpdates={updatesMap.hasUpdates}
        showUpdates={showUpdates}
        hasBaselineUpdates={baselineUpdatesMap.hasUpdates}
        statsItems={headerMetaItems}
      />
    </div>
  );
};

// --- Sub-components ---

interface TimelineHeaderProps {
  months: TimelineMonth[];
  yearGroups: YearGroup[];
  activityColumnWidth: number;
  nameColumnWidth: number;
  visibleColumns: OptionalColumnKey[];
  optionalColumnWidths: Record<OptionalColumnKey, number>;
  timelineContentWidth: number;
  ganttContentWidth: number;
  timelineScale: number;
  onTimelineScaleMouseDown: (event: React.MouseEvent<HTMLDivElement>) => void;
  onTimelineDoubleClick: () => void;
}

interface HeaderMetaItem {
  label: string;
  value: string;
}

function TimelineHeader({
  months,
  yearGroups,
  activityColumnWidth,
  nameColumnWidth,
  visibleColumns,
  optionalColumnWidths,
  timelineContentWidth,
  ganttContentWidth,
  timelineScale,
  onTimelineScaleMouseDown,
  onTimelineDoubleClick,
}: TimelineHeaderProps) {
  const dragTitle = `Drag horizontally to resize timeline (${Math.round(timelineScale * 100)}%) — double-click to fit project`;

  return (
    <div className="mb-4" style={{ width: `${ganttContentWidth}px` }}>
      {/* Year row */}
      <div className="flex" style={{ width: `${ganttContentWidth}px` }}>
        <div
          className="shrink-0 bg-[#0d1117]"
          style={{
            width: `${activityColumnWidth}px`,
            position: 'sticky',
            left: 0,
            zIndex: 20,
          }}
        ></div>
        <div
          className="shrink-0 flex cursor-ew-resize select-none text-xs text-gray-500"
          style={{ width: `${timelineContentWidth}px` }}
          onMouseDown={onTimelineScaleMouseDown}
          onDoubleClick={onTimelineDoubleClick}
          title={dragTitle}
        >
          {yearGroups.map((group, index) => (
            <div
              key={index}
              className="text-center font-medium"
              style={{ flex: group.monthCount }}
            >
              {group.year}
            </div>
          ))}
        </div>
      </div>
      {/* Month row */}
      <div className="flex border-b border-dark-600 pb-2" style={{ width: `${ganttContentWidth}px` }}>
        <div
          className="shrink-0 flex items-center text-xs font-medium text-gray-400 bg-[#0d1117]"
          style={{
            width: `${activityColumnWidth}px`,
            position: 'sticky',
            left: 0,
            zIndex: 20,
          }}
        >
          <div className="truncate px-2 text-center" style={{ width: `${nameColumnWidth}px` }}>
            Activity
          </div>
          {visibleColumns.map((columnKey) => {
            const label = getOptionalColumnLabel(columnKey);
            return (
              <div
                key={columnKey}
                className="truncate px-2 text-center"
                style={{ width: `${optionalColumnWidths[columnKey]}px` }}
                title={label}
              >
                {label}
              </div>
            );
          })}
        </div>
        <div
          className="shrink-0 flex cursor-ew-resize select-none text-xs text-gray-400"
          style={{ width: `${timelineContentWidth}px` }}
          onMouseDown={onTimelineScaleMouseDown}
          onDoubleClick={onTimelineDoubleClick}
          title={dragTitle}
        >
          {months.map((month, index) => (
            <div
              key={index}
              className="flex-1 text-center border-r border-dark-700 last:border-r-0"
            >
              {month.shortLabel}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface HierarchicalRowProps {
  item: PositionedItem;
  activityColumnWidth: number;
  nameColumnWidth: number;
  visibleColumns: OptionalColumnKey[];
  optionalColumnWidths: Record<OptionalColumnKey, number>;
  canCollapse: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  showBaseline: boolean;
  activityUpdates?: ActivityUpdate[];
  baselineActivityUpdates?: ActivityUpdate[];
  /** Whether this row is the currently selected activity (for 'selected' link mode). */
  isSelected?: boolean;
  /** Click handler invoked with the row's s_item_id (toggles selection). */
  onSelect?: (sItemId: string) => void;
}

function HierarchicalRow({
  item,
  activityColumnWidth,
  nameColumnWidth,
  visibleColumns,
  optionalColumnWidths,
  canCollapse,
  isCollapsed,
  onToggleCollapse,
  showBaseline,
  activityUpdates,
  baselineActivityUpdates,
  isSelected = false,
  onSelect,
}: HierarchicalRowProps) {
  const isSummary = item.is_summary === true;
  const isMilestone = !isSummary && (item.working_days === 0 || item.calendar_days === 0);
  const indentLevel = (item.level || 2) - 1;
  const indentPx = indentLevel * 16;
  const bs = ganttStyleSettings.baseline;
  const us = ganttStyleSettings.updates;
  const bus = ganttStyleSettings.baselineUpdates;
  const hasBaseline = item.baselineStartPercentage !== undefined && item.baselineWidthPercentage !== undefined;

  return (
    <div
      className={`flex items-center group h-full ${isSummary ? 'bg-[#0d1117]' : ''} ${
        isSelected ? 'ring-1 ring-inset ring-blue-400/70 bg-blue-500/10' : ''
      } ${onSelect ? 'cursor-pointer' : ''}`}
      onClick={onSelect ? () => onSelect(String(item.s_item_id)) : undefined}
    >
      {/* Activity label with indentation */}
      <div
        className={`shrink-0 pr-2 flex items-center ${
          isSelected ? 'bg-[#11203a]' : 'bg-[#0d1117]'
        }`}
        style={{
          width: `${activityColumnWidth}px`,
          position: 'sticky',
          left: 0,
          zIndex: 15,
        }}
      >
        <div className="flex items-center min-w-0" style={{ width: `${nameColumnWidth}px`, paddingLeft: `${indentPx}px` }}>
          {isSummary ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleCollapse();
              }}
              disabled={!canCollapse}
              className={`mr-1 h-4 w-4 flex items-center justify-center rounded transition-colors ${
                canCollapse ? 'text-gray-300 hover:bg-dark-700 hover:text-white' : 'text-gray-600'
              }`}
              aria-label={isCollapsed ? 'Expand summary' : 'Collapse summary'}
              title={isCollapsed ? 'Expand' : 'Collapse'}
            >
              {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          ) : (
            <span className="mr-1 h-4 w-4 shrink-0" aria-hidden="true"></span>
          )}
          <div className="flex-1 min-w-0">
            <div
              className={`text-xs truncate ${
                isSummary ? 'font-semibold text-white' : 'font-medium text-white'
              }`}
              title={item.s_item}
            >
              {item.s_item}
            </div>
            <div className={`text-xs ${isSummary ? 'text-white/80' : 'text-gray-500'}`}>{item.s_item_id}</div>
          </div>
        </div>

        {visibleColumns.map((columnKey) => (
          <div
            key={`${item.id}-${columnKey}`}
            className="shrink-0 px-2 text-xs text-gray-300 text-center truncate"
            style={{ width: `${optionalColumnWidths[columnKey]}px` }}
            title={formatOptionalColumnValue(item, columnKey)}
          >
            {formatOptionalColumnValue(item, columnKey)}
          </div>
        ))}
      </div>

      {/* Timeline bar container */}
      <div className="flex-1 relative h-7 rounded bg-transparent">
        {isMilestone ? (
          <div
            className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rotate-45 transition-all duration-200 group-hover:opacity-80 shadow-lg ${getBarClasses(
              item
            )}`}
            style={{
              left: `${item.startPercentage}%`,
              width: '12px',
              height: '12px',
            }}
            title={getBarTooltip(item, isSummary)}
          />
        ) : (
          <div
            className={`absolute top-1 bottom-1 rounded transition-all duration-200 group-hover:opacity-80 flex items-center justify-center text-xs font-medium shadow-lg ${getBarClasses(
              item
            )}`}
            style={{
              left: `${item.startPercentage}%`,
              width: `${item.widthPercentage}%`,
              minWidth: '16px',
            }}
            title={getBarTooltip(item, isSummary)}
          >
            {item.widthPercentage > 12 ? (
              <span className="truncate px-1 text-white text-[10px]">
                {isSummary ? `${item.calendar_days}d` : `${item.working_days}d / ${item.calendar_days}d`}
              </span>
            ) : item.widthPercentage > 6 ? (
              <span className="truncate px-1 text-white text-[10px]">{item.calendar_days}d</span>
            ) : null}
          </div>
        )}

        {/* Baseline bar (ghost) */}
        {showBaseline && hasBaseline && !isMilestone && (
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

        {/* Update indicator */}
        {activityUpdates && activityUpdates.length > 0 && (
          <div
            className="group/update absolute"
            style={{
              left: isMilestone
                ? `${item.startPercentage}%`
                : `${item.startPercentage + item.widthPercentage}%`,
              top: '50%',
              transform: 'translateY(-50%)',
              marginLeft: '4px',
            }}
          >
            <div
              className="rounded-full flex items-center justify-center cursor-default"
              style={{
                width: `${us.size}px`,
                height: `${us.size}px`,
                backgroundColor: us.bg,
                borderWidth: us.borderWidth,
                borderStyle: 'solid',
                borderColor: us.borderColor,
                color: us.textColor,
                fontSize: us.fontSize,
                fontWeight: us.fontWeight,
              }}
            >
              !
            </div>
            <UpdateTooltip updates={activityUpdates} />
          </div>
        )}

        {/* Baseline update indicator (light gray) */}
        {baselineActivityUpdates && baselineActivityUpdates.length > 0 && (
          <div
            className="group/blupdate absolute"
            style={{
              left: isMilestone
                ? `${item.startPercentage}%`
                : `${item.startPercentage + item.widthPercentage}%`,
              top: '50%',
              transform: 'translateY(-50%)',
              marginLeft: activityUpdates && activityUpdates.length > 0
                ? `${4 + us.size + 2}px`
                : '4px',
            }}
          >
            <div
              className="rounded-full flex items-center justify-center cursor-default"
              style={{
                width: `${bus.size}px`,
                height: `${bus.size}px`,
                backgroundColor: bus.bg,
                borderWidth: bus.borderWidth,
                borderStyle: 'solid',
                borderColor: bus.borderColor,
                color: bus.textColor,
                fontSize: bus.fontSize,
                fontWeight: bus.fontWeight,
              }}
            >
              !
            </div>
            <UpdateTooltip updates={baselineActivityUpdates} label="Baseline" />
          </div>
        )}
      </div>
    </div>
  );
}

interface UpdateTooltipProps {
  updates: ActivityUpdate[];
  /** Optional label prefix, e.g. "Baseline" for baseline version updates */
  label?: string;
}

function UpdateTooltip({ updates, label }: UpdateTooltipProps) {
  const us = ganttStyleSettings.updates;

  // Tailwind JIT requires full static class strings — dynamic interpolation won't work.
  const hoverClasses = label
    ? 'group-hover/blupdate:opacity-100 group-hover/blupdate:visible group-hover/blupdate:pointer-events-auto'
    : 'group-hover/update:opacity-100 group-hover/update:visible group-hover/update:pointer-events-auto';

  return (
    <div
      className={`absolute left-1/2 -translate-x-1/2 bottom-full mb-2 opacity-0 invisible
                 transition-all duration-150 z-50 pointer-events-none
                 ${hoverClasses}`}
      style={{ width: `${us.tooltipMaxWidth}px` }}
    >
      <div className="bg-[#1a1f2e] border border-dark-600 rounded-lg shadow-xl p-3 text-xs">
        <div className="text-gray-300 font-medium mb-2">
          {label ? `${label}: ` : ''}{updates.length} Update{updates.length !== 1 ? 's' : ''}
        </div>

        <div className="space-y-2 max-h-[240px] overflow-y-auto">
          {updates.map((update) => (
            <div key={update.log_id} className="border-t border-dark-600 pt-2">
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

              <p className="text-gray-300 line-clamp-3 mb-1">
                {update.details}
              </p>

              {update.reported_value && (
                <p className="text-gray-400 text-[10px] mb-1">
                  Value: {update.reported_value}
                </p>
              )}

              <p className="text-gray-500 text-[10px]">
                {update.reported_by}
              </p>

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

function getBarClasses(item: PositionedItem): string {
  if (item.is_summary) {
    return 'bg-yellow-900/55 border border-yellow-700/70';
  }
  if (item.is_critical) {
    return 'bg-red-900/70 border border-red-700/70';
  }
  if (item.status === 'completed') {
    return 'bg-emerald-900/65 border border-emerald-700/70';
  }
  if (item.status === 'in_progress') {
    return 'bg-blue-900/65 border border-blue-700/70';
  }
  return 'bg-slate-800/75 border border-slate-600/70';
}

function getBarTooltip(item: PositionedItem, isSummary: boolean): string {
  let tooltip: string;

  if (isSummary) {
    tooltip = `${item.s_item} (Summary)
${item.children_count} activities
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Calendar Span: ${item.calendar_days}d
${item.is_critical ? '(Contains Critical Path)' : ''}`;
  } else {
    tooltip = `${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Working Days: ${item.working_days}d
Calendar Days: ${item.calendar_days}d
Total Float: ${item.total_float.toFixed(1)} days
${item.is_critical ? '(Critical Path)' : ''}`;
  }

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

interface LegendProps {
  grouping?: string | null;
  hasRelationships?: boolean;
  hasBaseline?: boolean;
  showBaseline?: boolean;
  baselineMode?: BaselineMode;
  baselineLabel?: string | null;
  hasUpdates?: boolean;
  showUpdates?: boolean;
  hasBaselineUpdates?: boolean;
  statsItems?: HeaderMetaItem[];
}

function Legend({ grouping, hasRelationships, hasBaseline, showBaseline, baselineMode, baselineLabel, hasUpdates, showUpdates, hasBaselineUpdates, statsItems }: LegendProps) {
  const bs = ganttStyleSettings.baseline;
  const us = ganttStyleSettings.updates;
  const bus = ganttStyleSettings.baselineUpdates;

  return (
    <div className="px-4 py-2 border-t border-dark-700 bg-[#0d1117] text-xs rounded-b-xl">
      <div className="flex items-center gap-4 text-gray-400 flex-wrap">
        {grouping && (
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded bg-yellow-900/55 border border-yellow-700/70"></div>
            <span>Summary</span>
          </div>
        )}
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-red-900/70 border border-red-700/70"></div>
          <span>Critical</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-blue-900/65 border border-blue-700/70"></div>
          <span>In Progress</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-emerald-900/65 border border-emerald-700/70"></div>
          <span>Completed</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-slate-800/75 border border-slate-600/70"></div>
          <span>Not Started</span>
        </div>
        {hasRelationships && (
          <>
            <div className="w-px h-3 bg-dark-600 mx-1"></div>
            <div className="flex items-center gap-1">
              <svg className="w-4 h-3" viewBox="0 0 16 12">
                <line x1="0" y1="6" x2="12" y2="6" stroke="#EF4444" strokeWidth="2" />
                <polygon points="12,3 16,6 12,9" fill="#EF4444" />
              </svg>
              <span>Critical Link</span>
            </div>
            <div className="flex items-center gap-1">
              <svg className="w-4 h-3" viewBox="0 0 16 12">
                <line x1="0" y1="6" x2="12" y2="6" stroke="#6B7280" strokeWidth="1.5" />
                <polygon points="12,3 16,6 12,9" fill="#6B7280" />
              </svg>
              <span>Link</span>
            </div>
          </>
        )}
        {hasBaseline && showBaseline && (
          <>
            <div className="w-px h-3 bg-dark-600 mx-1"></div>
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
              <span>{baselineMode === 'what_if' ? 'vs. What-If Baseline (Visible Scope)' : baselineMode === 'previous_version' ? `vs. Previous${baselineLabel ? ` (${baselineLabel})` : ''}` : baselineMode === 'database_baseline' ? `vs. DB Baseline${baselineLabel ? ` (${baselineLabel})` : ''}` : 'Baseline'}</span>
            </div>
          </>
        )}
        {hasUpdates && showUpdates && (
          <>
            <div className="w-px h-3 bg-dark-600 mx-1"></div>
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
          </>
        )}
        {hasBaselineUpdates && showUpdates && (
          <>
            <div className="w-px h-3 bg-dark-600 mx-1"></div>
            <div className="flex items-center gap-1">
              <div
                className="w-3 h-3 rounded-full flex items-center justify-center text-[8px] font-bold"
                style={{
                  backgroundColor: bus.legendBg,
                  color: bus.legendTextColor,
                }}
              >
                !
              </div>
              <span>Baseline Update</span>
            </div>
          </>
        )}
        {/* Stats: pushed to the right */}
        {statsItems && statsItems.length > 0 && (
          <>
            <div className="flex-1" />
            <div className="flex items-center gap-3 text-gray-400 flex-wrap">
              {statsItems.map((item) => (
                <span key={item.label} className="whitespace-nowrap">
                  <span className="text-gray-500">{item.label}:</span>{' '}
                  <span className="text-gray-300">{item.value}</span>
                </span>
              ))}
            </div>
          </>
        )}
      </div>
      {grouping && <div className="mt-1 text-gray-500">Grouped by: {grouping}</div>}
    </div>
  );
}

// --- Hooks ---
