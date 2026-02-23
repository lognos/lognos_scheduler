/**
 * GanttPanel Component
 *
 * Floating Gantt chart panel with filters, hierarchy support, and virtualization.
 * Uses shared hooks for timeline and bar position calculations.
 * Virtualized for performance with 500-1000+ activities.
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { format, parseISO } from 'date-fns';
import { X, Calendar, Filter, AlertTriangle, GitBranch } from 'lucide-react';
import { GanttChartData, GanttFilter } from '@/types/schedule';
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
}

/**
 * Floating Gantt chart panel that displays schedule data
 * streamed from the scheduling agent via AG-UI.
 */

type RelationshipMode = 'none' | 'critical' | 'all';

export const GanttPanel: React.FC<GanttPanelProps> = ({ data, onClose, width, onWidthChange }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  const [relationshipMode, setRelationshipMode] = useState<RelationshipMode>('critical');
  const dragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const columnDragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const [activityColumnWidth, setActivityColumnWidth] = useState<number>(192);

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

  // Cycle through modes: critical → all → none → critical
  const cycleRelationshipMode = () => {
    setRelationshipMode((prev) => {
      switch (prev) {
        case 'critical': return 'all';
        case 'all': return 'none';
        case 'none': return 'critical';
      }
    });
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

  // Build active filter description
  const filterDescription = useFilterDescription(data.filter_applied);

  // Virtualization for large datasets
  const rowVirtualizer = useVirtualizer({
    count: positionedItems.length,
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
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-blue-400" />
          <h2 className="text-lg font-light text-white">Schedule</h2>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">
            {data.filtered_activities} of {data.total_activities} activities
          </span>
          <button
            onClick={onClose}
            className="p-1 hover:bg-dark-700 rounded transition-colors"
            aria-label="Close panel"
          >
            <X className="h-5 w-5 text-gray-400 hover:text-white" />
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="px-4 py-2 bg-dark-800/30 border-b border-dark-700 text-xs text-gray-400 flex items-center justify-between">
        <div className="flex gap-4">
          <span>Start: {format(parseISO(data.project_start), 'MMM d, yyyy')}</span>
          <span>Finish: {format(parseISO(data.project_finish), 'MMM d, yyyy')}</span>
          <span>Critical Path: {data.critical_path_length.toFixed(1)} days</span>
        </div>
        {/* Relationships toggle */}
        {data.relationships && data.relationships.length > 0 && (
          <button
            onClick={cycleRelationshipMode}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors ${
              relationshipMode === 'all'
                ? 'bg-blue-600/20 text-blue-300'
                : relationshipMode === 'critical'
                  ? 'bg-red-600/20 text-red-300'
                  : 'hover:bg-dark-700 text-gray-500'
            }`}
            title={
              relationshipMode === 'all' 
                ? 'Showing all relationships' 
                : relationshipMode === 'critical'
                  ? 'Showing critical path only'
                  : 'Relationships hidden'
            }
          >
            <GitBranch className="h-3 w-3" />
            <span>
              {relationshipMode === 'all' ? 'All' : relationshipMode === 'critical' ? 'Critical' : 'None'}
            </span>
          </button>
        )}
      </div>

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
                      <HierarchicalRow
                        item={item}
                        showGrouping={!!data.grouping}
                        activityColumnWidth={activityColumnWidth}
                      />
                    </div>
                  );
                })}

                {/* Relationship arrows overlay - positioned over timeline area only */}
                {data.relationships && data.relationships.length > 0 && relationshipMode !== 'none' && (
                  <div 
                    className="absolute top-0 bottom-0"
                    style={{ 
                      left: `${activityColumnWidth}px`,
                      right: 0,
                    }}
                  >
                    <RelationshipArrows
                      items={positionedItems}
                      relationships={data.relationships}
                      rowHeight={36}
                      showCriticalOnly={relationshipMode === 'critical'}
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
  showGrouping: boolean;
  activityColumnWidth: number;
}

function HierarchicalRow({ item, showGrouping, activityColumnWidth }: HierarchicalRowProps) {
  const isSummary = item.is_summary === true;
  const indentLevel = (item.level || 2) - 1;
  const indentPx = indentLevel * 16;

  return (
    <div className={`flex items-center group h-full ${isSummary ? 'bg-dark-700/30' : ''}`}>
      {/* Activity label with indentation */}
      <div
        className="shrink-0 pr-2 flex items-center"
        style={{ width: `${activityColumnWidth}px`, paddingLeft: `${indentPx}px` }}
      >
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
        {/* Activity bar */}
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
