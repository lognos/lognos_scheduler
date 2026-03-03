/**
 * GanttChart Component
 *
 * Standalone Gantt chart optimized for reports and printing.
 * Uses shared hooks for timeline and bar position calculations.
 */

import React from 'react';
import { format, parseISO } from 'date-fns';
import { Calendar } from 'lucide-react';
import { ScheduleItem, ScheduleRelationship } from '@/types';
import { useTimeline, useBarPositions, PositionedItem, TimelineMonth, YearGroup } from './hooks';
import { RelationshipArrows } from './RelationshipArrows';

interface GanttChartProps {
  data: ScheduleItem[];
  /** Optional relationships for dependency arrows */
  relationships?: ScheduleRelationship[];
  loading?: boolean;
  /** Show only critical path relationships (default: true) */
  showCriticalOnly?: boolean;
}

const ROW_HEIGHT = 44; // Height of each row in pixels (including spacing)

const GanttChart: React.FC<GanttChartProps> = ({
  data,
  relationships,
  loading,
  showCriticalOnly = true,
}) => {
  // Use shared hooks instead of duplicated useMemo blocks
  const timeline = useTimeline({ items: data });
  const positionedItems = useBarPositions({
    items: data,
    timelineStartDate: timeline.startDate,
    totalDays: timeline.totalDays,
    sortMode: 'start-date',
  });

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (!data || data.length === 0) {
    return <EmptyState />;
  }

  const totalHeight = positionedItems.length * ROW_HEIGHT;

  return (
    <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700 print:bg-white print:border print:border-gray-300 print:rounded-none print:page-break-inside-avoid chart-color-preserve">
      <div className="flex items-center justify-between mb-6 print:mb-4">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-blue-400 print:text-black" />
          <h3 className="text-xl font-light text-white print:text-black print:font-helvetica">
            Project L1 schedule
          </h3>
        </div>
        <div className="text-sm text-gray-400 print:text-black">
          {data.length} schedule item{data.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Timeline Header */}
      <TimelineHeader months={timeline.months} yearGroups={timeline.yearGroups} />

      {/* Gantt Bars with Relationships */}
      <div className="relative" style={{ minHeight: totalHeight }}>
        <div className="space-y-3">
          {positionedItems.map((item, index) => (
            <GanttRow key={item.s_item_id} item={item} colorIndex={index} />
          ))}
        </div>

        {/* Relationship arrows overlay */}
        {relationships && relationships.length > 0 && (
          <RelationshipArrows
            items={positionedItems}
            relationships={relationships}
            rowHeight={ROW_HEIGHT}
            showCriticalOnly={showCriticalOnly}
            totalHeight={totalHeight}
          />
        )}
      </div>
    </div>
  );
};

// --- Sub-components ---

function LoadingSkeleton() {
  return (
    <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700">
      <div className="flex items-center gap-2 mb-4">
        <Calendar className="h-5 w-5 text-blue-400" />
        <h3 className="text-xl font-light text-white">Project Schedule</h3>
      </div>
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bg-dark-800/50 backdrop-blur-sm rounded-xl p-6 border border-dark-700">
      <div className="flex items-center gap-2 mb-4">
        <Calendar className="h-5 w-5 text-blue-400" />
        <h3 className="text-xl font-light text-white">Project Schedule</h3>
      </div>
      <div className="flex items-center justify-center h-64 text-gray-400">
        No schedule data available
      </div>
    </div>
  );
}

interface TimelineHeaderProps {
  months: TimelineMonth[];
  yearGroups: YearGroup[];
}

function TimelineHeader({ months, yearGroups }: TimelineHeaderProps) {
  return (
    <div className="mb-4">
      {/* Year row */}
      <div className="flex">
        <div className="w-80"></div>
        <div className="flex-1 flex text-xs text-gray-500 print:text-black">
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
      <div className="flex border-b border-dark-600 print:border-gray-300 pb-2">
        <div className="w-80 text-xs font-medium text-gray-400 print:text-black">
          Activity
        </div>
        <div className="flex-1 flex text-xs text-gray-400 print:text-black">
          {months.map((month, index) => (
            <div
              key={index}
              className="flex-1 text-center border-r border-dark-600 print:border-gray-300 last:border-r-0"
            >
              {month.shortLabel}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface GanttRowProps {
  item: PositionedItem;
  colorIndex: number;
}

function GanttRow({ item, colorIndex }: GanttRowProps) {
  const barColor = getBarColor(colorIndex);
  const isMilestone = item.working_days === 0 || item.calendar_days === 0;

  return (
    <div className="flex items-center group">
      {/* Task Label */}
      <div className="w-80 pr-4">
        <div className="text-xs font-medium text-white print:text-black truncate">
          {item.s_item}
        </div>
        <div className="text-xs text-gray-500 print:text-black">{item.s_item_id}</div>
      </div>

      {/* Timeline Bar Container */}
      <div className="flex-1 relative h-8 rounded">
        {isMilestone ? (
          <div
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rotate-45 transition-all duration-200 group-hover:opacity-80 shadow-lg"
            style={{
              left: `${item.startPercentage}%`,
              width: '14px',
              height: '14px',
              backgroundColor: barColor,
            }}
            title={`${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Working Days: ${item.working_days}d
Calendar Days: ${item.calendar_days}d
Total Float: ${item.total_float}d`}
          />
        ) : (
          <div
            className="absolute top-1 bottom-1 rounded transition-all duration-200 group-hover:opacity-80 flex items-center justify-center text-xs font-medium shadow-lg gantt-bar"
            style={{
              left: `${item.startPercentage}%`,
              width: `${item.widthPercentage}%`,
              backgroundColor: barColor,
              minWidth: '20px',
              color: 'white',
            }}
            title={`${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Working Days: ${item.working_days}d
Calendar Days: ${item.calendar_days}d
Total Float: ${item.total_float}d`}
          >
            {item.widthPercentage > 12 ? (
              <span className="truncate px-1 gantt-duration-text" style={{ color: 'inherit' }}>
                {item.working_days}d / {item.calendar_days}d
              </span>
            ) : item.widthPercentage > 6 ? (
              <span className="truncate px-1 gantt-duration-text" style={{ color: 'inherit' }}>
                {item.calendar_days}d
              </span>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function getBarColor(index: number): string {
  const colors = ['#3B82F6'];
  return colors[index % colors.length];
}

export default GanttChart;
