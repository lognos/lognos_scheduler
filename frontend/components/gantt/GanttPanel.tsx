/**
 * GanttPanel Component
 *
 * Floating Gantt chart panel with filters, hierarchy support, and virtualization.
 * Uses shared hooks for timeline and bar position calculations.
 * Virtualized for performance with 500-1000+ activities.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { format, isValid, parseISO, differenceInDays } from 'date-fns';
import { X, Calendar, AlertTriangle, GitBranch, ChevronRight, ChevronDown } from 'lucide-react';
import { GanttChartData, ScheduleViewKey, ScheduleViewMeta, ActivityUpdate, BaselineMode } from '@/types/schedule';
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
import ganttStyleSettings from './ganttStyleSettings';

interface GanttPanelProps {
  data: GanttChartData;
  onClose: () => void;
  width: number;
  onWidthChange: (width: number) => void;
  availableViews?: ScheduleViewMeta[];
  activeViewKey?: ScheduleViewKey;
  onSelectView?: (viewKey: ScheduleViewKey) => void;
  onBaselineModeChange?: (mode: BaselineMode) => void;
  isViewLoading?: boolean;
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

type OptionalColumnKey = 'start' | 'finish' | 'float' | 'progress';

interface OptionalColumnOption {
  key: OptionalColumnKey;
  label: string;
}

const OPTIONAL_COLUMN_OPTIONS: OptionalColumnOption[] = [
  { key: 'start', label: 'Start' },
  { key: 'finish', label: 'Finish' },
  { key: 'float', label: 'Float' },
  { key: 'progress', label: 'Complete (%)' },
];

function formatOptionalColumnValue(item: PositionedItem, column: OptionalColumnKey): string {
  switch (column) {
    case 'start':
      return formatProjectDate(item.start);
    case 'finish':
      return formatProjectDate(item.finish);
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

export const GanttPanel: React.FC<GanttPanelProps> = ({
  data,
  onClose,
  width,
  onWidthChange,
  availableViews = [],
  activeViewKey,
  onSelectView,
  onBaselineModeChange,
  isViewLoading = false,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const [showLinks, setShowLinks] = useState<boolean>(false);
  const [showBaseline, setShowBaseline] = useState<boolean>(true);
  const [baselineMode, setBaselineMode] = useState<BaselineMode>(data.baseline_mode || 'own');
  const [showUpdates, setShowUpdates] = useState<boolean>(true);
  const dragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const columnDragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const [activityColumnWidth, setActivityColumnWidth] = useState<number>(BASE_ACTIVITY_COLUMN_WIDTH);
  const [visibleColumns, setVisibleColumns] = useState<OptionalColumnKey[]>([]);
  const [collapsedSummaryKeys, setCollapsedSummaryKeys] = useState<Set<string>>(new Set());

  const activityColumnMinWidth = useMemo(
    () => BASE_ACTIVITY_COLUMN_WIDTH + (visibleColumns.length * OPTIONAL_COLUMN_WIDTH),
    [visibleColumns.length]
  );

  useEffect(() => {
    setActivityColumnWidth((previous) => Math.max(previous, activityColumnMinWidth));
  }, [activityColumnMinWidth]);

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

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const dragState = dragStateRef.current;

      if (dragState) {
        const delta = dragState.startX - event.clientX;
        onWidthChange(dragState.startWidth + delta);
      }

      const columnDragState = columnDragStateRef.current;
      if (columnDragState) {
        const minWidth = activityColumnMinWidth;
        const maxWidth = Math.max(minWidth, width - 320);
        const delta = event.clientX - columnDragState.startX;
        const nextWidth = columnDragState.startWidth + delta;
        setActivityColumnWidth(Math.min(Math.max(nextWidth, minWidth), maxWidth));
      }
    };

    const handleMouseUp = () => {
      dragStateRef.current = null;
      columnDragStateRef.current = null;
      document.body.style.removeProperty('user-select');
      document.body.style.removeProperty('cursor');
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.removeProperty('user-select');
      document.body.style.removeProperty('cursor');
    };
  }, [onWidthChange, width, activityColumnMinWidth]);

  const startResize = (event: React.MouseEvent<HTMLDivElement>) => {
    dragStateRef.current = {
      startX: event.clientX,
      startWidth: width,
    };

    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  };

  const startColumnResize = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();

    columnDragStateRef.current = {
      startX: event.clientX,
      startWidth: activityColumnWidth,
    };

    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  };

  // Use shared hooks
  const timeline = useTimeline({
    items: data.items,
    projectStart: data.project_start,
    projectEnd: data.project_finish,
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
  const relationships = data.relationships ?? [];
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
    estimateSize: () => ROW_HEIGHT_PX, // row height in px
    overscan: 10, // render 10 extra rows above/below viewport for smooth scrolling
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const scrollTop = parentRef.current?.scrollTop ?? 0;

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

  return (
    <div
      className="fixed top-20 right-8 bottom-30 bg-[#0d1117] border border-dark-700 rounded-xl shadow-2xl z-50 flex flex-col overflow-hidden"
      style={{ width: `${width}px` }}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-2 cursor-col-resize z-20"
        onMouseDown={startResize}
        aria-hidden="true"
      />
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-700 bg-[#0d1117] rounded-t-xl">
        <div className="flex items-center gap-4">
          <Calendar className="h-5 w-5 text-blue-400" />
          <h2 className="text-lg font-light text-white">Schedule</h2>
          <HeaderMeta items={headerMetaItems} />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onClose}
            className="p-1 hover:bg-dark-700 rounded transition-colors"
            aria-label="Close panel"
          >
            <X className="h-5 w-5 text-gray-400 hover:text-white" />
          </button>
        </div>
      </div>

      <div className="relative z-40 px-4 py-2 bg-[#0d1117] border-b border-dark-700 text-xs flex items-center justify-between gap-3">
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
              <button
                type="button"
                onClick={() => setShowLinks((previous) => !previous)}
                className={`h-[26px] w-[26px] rounded-full border flex items-center justify-center transition-colors ${
                  showLinks
                    ? 'border-blue-500 text-blue-300 bg-blue-500/10 hover:bg-blue-500/20'
                    : 'border-dark-600 text-gray-500 hover:bg-dark-700/60'
                }`}
                title={showLinks ? 'Hide links' : 'Show links'}
                aria-label={showLinks ? 'Hide links' : 'Show links'}
              >
                <GitBranch className="h-3.5 w-3.5" />
              </button>
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
                  {baselineMode === 'own' ? 'Baseline' : baselineMode === 'previous_version' ? 'Baseline (Prev)' : 'Baseline (DB)'}
                </button>

                <div className="absolute left-0 top-full mt-1 min-w-48 rounded-md border border-dark-600 bg-[#0d1117] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-50">
                  {([
                    { mode: 'own' as BaselineMode, label: 'Own Baseline', available: true },
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
                      } ${index === 0 ? 'rounded-t-md' : ''} ${index === 2 ? 'rounded-b-md' : ''}`}
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
          </div>
        </div>

      {/* Gantt chart content */}
      <div className="flex-1 flex flex-col overflow-hidden p-4">
        {positionedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <AlertTriangle className="h-8 w-8 mb-2" />
            <p>No activities match the current filter</p>
          </div>
        ) : (
          <div className="min-w-[500px] flex flex-col flex-1 overflow-hidden relative">
            <div
              className="absolute top-0 bottom-0 w-2 cursor-col-resize z-20"
              style={{ left: `${activityColumnWidth - 4}px` }}
              onMouseDown={startColumnResize}
              aria-label="Resize activity column"
              role="separator"
              aria-orientation="vertical"
            />
            {/* Timeline header - STICKY, not virtualized */}
            <div className="sticky top-0 z-10 bg-[#0d1117]">
              <TimelineHeader
                months={timeline.months}
                yearGroups={timeline.yearGroups}
                activityColumnWidth={activityColumnWidth}
                visibleColumns={visibleColumns}
              />
            </div>

            {/* Virtualized body - scrollable */}
            <div ref={parentRef} className="flex-1 overflow-auto">
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: '100%',
                  position: 'relative',
                }}
              >
                {stickySummaryItems.length > 0 && (
                  <div
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
                            visibleColumns={visibleColumns}
                            canCollapse={canCollapse}
                            isCollapsed={isCollapsed}
                            onToggleCollapse={() => toggleSummaryCollapse(summaryKey)}
                            showBaseline={showBaseline && !!data.has_baseline}
                            activityUpdates={showUpdates ? updatesMap.byActivity.get(item.s_item_id) : undefined}
                            baselineActivityUpdates={showUpdates ? baselineUpdatesMap.byActivity.get(item.s_item_id) : undefined}
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
                        visibleColumns={visibleColumns}
                        canCollapse={canCollapse}
                        isCollapsed={isCollapsed}
                        onToggleCollapse={() => toggleSummaryCollapse(summaryKey)}
                        showBaseline={showBaseline && !!data.has_baseline}
                        activityUpdates={showUpdates ? updatesMap.byActivity.get(item.s_item_id) : undefined}
                        baselineActivityUpdates={showUpdates ? baselineUpdatesMap.byActivity.get(item.s_item_id) : undefined}
                      />
                    </div>
                  );
                })}

                {/* Relationship arrows overlay - positioned over timeline area only */}
                {relationships.length > 0 && showLinks && (
                  <div 
                    className="absolute top-0 bottom-0"
                    style={{ 
                      left: `${activityColumnWidth}px`,
                      right: 0,
                    }}
                  >
                    <RelationshipArrows
                      items={visibleItems}
                      relationships={relationships}
                      rowHeight={ROW_HEIGHT_PX}
                      showCriticalOnly={false}
                      totalHeight={rowVirtualizer.getTotalSize()}
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
      />
    </div>
  );
};

// --- Sub-components ---

interface TimelineHeaderProps {
  months: TimelineMonth[];
  yearGroups: YearGroup[];
  activityColumnWidth: number;
  visibleColumns: OptionalColumnKey[];
}

interface HeaderMetaItem {
  label: string;
  value: string;
}

interface HeaderMetaProps {
  items: HeaderMetaItem[];
}

function HeaderMeta({ items }: HeaderMetaProps) {
  return (
    <div className="flex items-center gap-4 text-xs text-gray-400 flex-wrap">
      {items.map((item) => (
        <span key={item.label}>
          {item.label}: {item.value}
        </span>
      ))}
    </div>
  );
}

function TimelineHeader({ months, yearGroups, activityColumnWidth, visibleColumns }: TimelineHeaderProps) {
  const activityNameColumnWidth = Math.max(
    BASE_ACTIVITY_COLUMN_WIDTH,
    activityColumnWidth - (visibleColumns.length * OPTIONAL_COLUMN_WIDTH)
  );

  return (
    <div className="mb-4">
      {/* Year row */}
      <div className="flex">
        <div className="shrink-0" style={{ width: `${activityColumnWidth}px` }}></div>
        <div className="flex-1 flex text-xs text-gray-500">
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
      <div className="flex border-b border-dark-600 pb-2">
        <div className="shrink-0 flex items-center text-xs font-medium text-gray-400" style={{ width: `${activityColumnWidth}px` }}>
          <div className="truncate pr-2" style={{ width: `${activityNameColumnWidth}px` }}>
            Activity
          </div>
          {visibleColumns.map((columnKey) => {
            const label = OPTIONAL_COLUMN_OPTIONS.find((option) => option.key === columnKey)?.label ?? columnKey;
            return (
              <div
                key={columnKey}
                className="truncate px-2 text-right"
                style={{ width: `${OPTIONAL_COLUMN_WIDTH}px` }}
                title={label}
              >
                {label}
              </div>
            );
          })}
        </div>
        <div className="flex-1 flex text-xs text-gray-400">
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
  visibleColumns: OptionalColumnKey[];
  canCollapse: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  showBaseline: boolean;
  activityUpdates?: ActivityUpdate[];
  baselineActivityUpdates?: ActivityUpdate[];
}

function HierarchicalRow({
  item,
  activityColumnWidth,
  visibleColumns,
  canCollapse,
  isCollapsed,
  onToggleCollapse,
  showBaseline,
  activityUpdates,
  baselineActivityUpdates,
}: HierarchicalRowProps) {
  const isSummary = item.is_summary === true;
  const isMilestone = !isSummary && (item.working_days === 0 || item.calendar_days === 0);
  const indentLevel = (item.level || 2) - 1;
  const indentPx = indentLevel * 16;
  const bs = ganttStyleSettings.baseline;
  const us = ganttStyleSettings.updates;
  const bus = ganttStyleSettings.baselineUpdates;
  const hasBaseline = item.baselineStartPercentage !== undefined && item.baselineWidthPercentage !== undefined;
  const activityNameColumnWidth = Math.max(
    BASE_ACTIVITY_COLUMN_WIDTH,
    activityColumnWidth - (visibleColumns.length * OPTIONAL_COLUMN_WIDTH)
  );

  return (
    <div className={`flex items-center group h-full ${isSummary ? 'bg-[#0d1117]' : ''}`}>
      {/* Activity label with indentation */}
      <div className="shrink-0 pr-2 flex items-center" style={{ width: `${activityColumnWidth}px` }}>
        <div className="flex items-center min-w-0" style={{ width: `${activityNameColumnWidth}px`, paddingLeft: `${indentPx}px` }}>
          {isSummary ? (
            <button
              type="button"
              onClick={onToggleCollapse}
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
            className="shrink-0 px-2 text-xs text-gray-300 text-right truncate"
            style={{ width: `${OPTIONAL_COLUMN_WIDTH}px` }}
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
}

function Legend({ grouping, hasRelationships, hasBaseline, showBaseline, baselineMode, baselineLabel, hasUpdates, showUpdates, hasBaselineUpdates }: LegendProps) {
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
              <span>{baselineMode === 'previous_version' ? `vs. Previous${baselineLabel ? ` (${baselineLabel})` : ''}` : baselineMode === 'database_baseline' ? `vs. DB Baseline${baselineLabel ? ` (${baselineLabel})` : ''}` : 'Baseline'}</span>
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
      </div>
      {grouping && <div className="mt-1 text-gray-500">Grouped by: {grouping}</div>}
    </div>
  );
}

// --- Hooks ---
