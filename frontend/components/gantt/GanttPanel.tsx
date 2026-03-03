/**
 * GanttPanel Component
 *
 * Floating Gantt chart panel with filters, hierarchy support, and virtualization.
 * Uses shared hooks for timeline and bar position calculations.
 * Virtualized for performance with 500-1000+ activities.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { format, isValid, parseISO } from 'date-fns';
import { X, Calendar, Filter, AlertTriangle, GitBranch, ChevronRight, ChevronDown } from 'lucide-react';
import { GanttChartData, GanttFilter, ScheduleViewKey, ScheduleViewMeta } from '@/types/schedule';
import {
  useTimeline,
  useBarPositions,
  PositionedItem,
  TimelineMonth,
  YearGroup,
  SortMode,
} from './hooks';
import { RelationshipArrows } from './RelationshipArrows';

interface GanttPanelProps {
  data: GanttChartData;
  onClose: () => void;
  width: number;
  onWidthChange: (width: number) => void;
  availableViews?: ScheduleViewMeta[];
  activeViewKey?: ScheduleViewKey;
  onSelectView?: (viewKey: ScheduleViewKey) => void;
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

export const GanttPanel: React.FC<GanttPanelProps> = ({
  data,
  onClose,
  width,
  onWidthChange,
  availableViews = [],
  activeViewKey,
  onSelectView,
  isViewLoading = false,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const [showLinks, setShowLinks] = useState<boolean>(true);
  const dragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const columnDragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const [activityColumnWidth, setActivityColumnWidth] = useState<number>(192);
  const [collapsedSummaryKeys, setCollapsedSummaryKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const dragState = dragStateRef.current;

      if (dragState) {
        const delta = dragState.startX - event.clientX;
        onWidthChange(dragState.startWidth + delta);
      }

      const columnDragState = columnDragStateRef.current;
      if (columnDragState) {
        const minWidth = 140;
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
  }, [onWidthChange]);

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

  const collapseLevel2Summaries = () => {
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

    setCollapsedSummaryKeys(level2Keys);
  };

  const expandAllSummaries = () => {
    setCollapsedSummaryKeys(new Set());
  };

  const hasCollapsibleSummaries = collapsibleSummaryKeys.size > 0;
  const hasCollapsedSummaries = collapsedSummaryKeys.size > 0;
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

  // Build active filter description
  const filterDescription = useFilterDescription(data.filter_applied);

  // Virtualization for large datasets
  const rowVirtualizer = useVirtualizer({
    count: visibleItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 36, // row height in px
    overscan: 10, // render 10 extra rows above/below viewport for smooth scrolling
  });

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
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-700 bg-dark-800/50 rounded-t-xl">
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

      {(availableViews.length > 0 || isViewLoading || hasCollapsibleSummaries) && (
        <div className="px-4 py-2 bg-dark-800/20 border-b border-dark-700 text-xs flex items-center justify-between gap-3">
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

                <div className="absolute left-0 top-full mt-1 min-w-40 rounded-md border border-dark-600 bg-[#111827] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-30">
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
                        {view.view_name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
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

                <div className="absolute right-0 top-full mt-1 w-36 rounded-md border border-dark-600 bg-[#111827] shadow-lg opacity-0 invisible translate-y-1 transition-all duration-150 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 z-30">
                  <button
                    type="button"
                    onClick={collapseAllSummaries}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-dark-700/70 rounded-t-md disabled:text-gray-600 disabled:hover:bg-transparent"
                    disabled={collapsedSummaryKeys.size === collapsibleSummaryKeys.size}
                  >
                    Collapse all
                  </button>
                  <button
                    type="button"
                    onClick={collapseLevel2Summaries}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-dark-700/70 disabled:text-gray-600 disabled:hover:bg-transparent"
                    disabled={!hasLevel2CollapsibleSummaries}
                  >
                    Level 2
                  </button>
                  <button
                    type="button"
                    onClick={expandAllSummaries}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-dark-700/70 rounded-b-md disabled:text-gray-600 disabled:hover:bg-transparent"
                    disabled={!hasCollapsedSummaries}
                  >
                    Expand all
                  </button>
                </div>
              </div>
            )}

            {data.relationships && data.relationships.length > 0 && (
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

            {isViewLoading && <span className="text-gray-500">Loading view...</span>}
          </div>
        </div>
      )}

      {/* Filter indicator */}
      {filterDescription && (
        <div className="px-4 py-2 bg-blue-900/20 border-b border-dark-700 text-xs text-blue-300 flex items-center gap-2">
          <Filter className="h-3 w-3" />
          <span>{filterDescription}</span>
        </div>
      )}

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
                {/* Activity rows */}
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
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
                        canCollapse={canCollapse}
                        isCollapsed={isCollapsed}
                        onToggleCollapse={() => toggleSummaryCollapse(summaryKey)}
                      />
                    </div>
                  );
                })}

                {/* Relationship arrows overlay - positioned over timeline area only */}
                {data.relationships && data.relationships.length > 0 && showLinks && (
                  <div 
                    className="absolute top-0 bottom-0"
                    style={{ 
                      left: `${activityColumnWidth}px`,
                      right: 0,
                    }}
                  >
                    <RelationshipArrows
                      items={visibleItems}
                      relationships={data.relationships}
                      rowHeight={36}
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
        hasRelationships={!!data.relationships && data.relationships.length > 0}
      />
    </div>
  );
};

// --- Sub-components ---

interface TimelineHeaderProps {
  months: TimelineMonth[];
  yearGroups: YearGroup[];
  activityColumnWidth: number;
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

function TimelineHeader({ months, yearGroups, activityColumnWidth }: TimelineHeaderProps) {
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
        <div
          className="shrink-0 text-xs font-medium text-gray-400"
          style={{ width: `${activityColumnWidth}px` }}
        >
          Activity
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
  canCollapse: boolean;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

function HierarchicalRow({
  item,
  activityColumnWidth,
  canCollapse,
  isCollapsed,
  onToggleCollapse,
}: HierarchicalRowProps) {
  const isSummary = item.is_summary === true;
  const isMilestone = !isSummary && (item.working_days === 0 || item.calendar_days === 0);
  const indentLevel = (item.level || 2) - 1;
  const indentPx = indentLevel * 16;

  return (
    <div className={`flex items-center group h-full ${isSummary ? 'bg-dark-700/30' : ''}`}>
      {/* Activity label with indentation */}
      <div
        className="shrink-0 pr-2 flex items-center"
        style={{ width: `${activityColumnWidth}px`, paddingLeft: `${indentPx}px` }}
      >
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
        {isSummary && (
          <span
            className="text-xs text-yellow-500 mr-1"
            title={`${item.children_count} activities`}
          >
            [{item.children_count}]
          </span>
        )}
        <div className="flex-1 min-w-0">
          <div
            className={`text-xs truncate ${
              isSummary ? 'font-semibold text-yellow-400' : 'font-medium text-white'
            }`}
            title={item.s_item}
          >
            {item.s_item}
          </div>
          <div className="text-xs text-gray-500">{item.s_item_id}</div>
        </div>
      </div>

      {/* Timeline bar container */}
      <div className="flex-1 relative h-7 rounded bg-dark-800/30">
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
  if (isSummary) {
    return `${item.s_item} (Summary)
${item.children_count} activities
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Calendar Span: ${item.calendar_days}d
${item.is_critical ? '(Contains Critical Path)' : ''}`;
  }

  return `${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Working Days: ${item.working_days}d
Calendar Days: ${item.calendar_days}d
Total Float: ${item.total_float.toFixed(1)} days
${item.is_critical ? '(Critical Path)' : ''}`;
}

interface LegendProps {
  grouping?: string | null;
  hasRelationships?: boolean;
}

function Legend({ grouping, hasRelationships }: LegendProps) {
  return (
    <div className="px-4 py-2 border-t border-dark-700 bg-dark-800/30 text-xs rounded-b-xl">
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
      </div>
      {grouping && <div className="mt-1 text-gray-500">Grouped by: {grouping}</div>}
    </div>
  );
}

// --- Hooks ---

function useFilterDescription(filter: GanttFilter): string | null {
  return useMemo(() => {
    const parts: string[] = [];

    if (filter.activity_codes) {
      Object.entries(filter.activity_codes).forEach(([type, values]) => {
        parts.push(`${type}: ${values.join(', ')}`);
      });
    }
    if (filter.wbs_path) parts.push(`WBS: ${filter.wbs_path}`);
    if (filter.critical_only) parts.push('Critical Path Only');
    if (filter.status && filter.status.length > 0) {
      parts.push(`Status: ${filter.status.join(', ')}`);
    }
    if (filter.search_term) parts.push(`Search: "${filter.search_term}"`);

    return parts.length > 0 ? parts.join(' | ') : null;
  }, [filter]);
}
