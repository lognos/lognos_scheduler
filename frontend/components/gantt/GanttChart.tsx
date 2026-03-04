/**
 * GanttChart Component
 *
 * Standalone Gantt chart optimized for reports and printing.
 * Uses shared hooks for timeline and bar position calculations.
 */

import React from 'react';
import { format, parseISO, differenceInDays } from 'date-fns';
import { Calendar } from 'lucide-react';
import { ScheduleItem, ScheduleRelationship, ActivityUpdate } from '@/types';
import { useTimeline, useBarPositions, useActivityUpdates, PositionedItem, TimelineMonth, YearGroup } from './hooks';
import { RelationshipArrows } from './RelationshipArrows';
import ganttStyleSettings from './ganttStyleSettings';

interface GanttChartProps {
  data: ScheduleItem[];
  /** Optional relationships for dependency arrows */
  relationships?: ScheduleRelationship[];
  /** Optional activity updates for indicator display */
  activityUpdates?: ActivityUpdate[];
  loading?: boolean;
  /** Show only critical path relationships (default: true) */
  showCriticalOnly?: boolean;
}

const ROW_HEIGHT = 44; // Height of each row in pixels (including spacing)

const GanttChart: React.FC<GanttChartProps> = ({
  data,
  relationships,
  activityUpdates,
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
  const updatesMap = useActivityUpdates(activityUpdates);

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
            <GanttRow
              key={item.s_item_id}
              item={item}
              colorIndex={index}
              activityUpdates={updatesMap.byActivity.get(item.s_item_id)}
            />
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
  activityUpdates?: ActivityUpdate[];
}

function GanttRow({ item, colorIndex, activityUpdates }: GanttRowProps) {
  const barColor = getBarColor(colorIndex);
  const isMilestone = item.working_days === 0 || item.calendar_days === 0;
  const bs = ganttStyleSettings.baseline;
  const us = ganttStyleSettings.updates;
  const hasBaseline = item.baselineStartPercentage !== undefined && item.baselineWidthPercentage !== undefined;

  const tooltipText = buildReportTooltip(item);

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
            title={tooltipText}
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
            title={tooltipText}
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

        {/* Baseline bar (ghost) - always visible in report view */}
        {hasBaseline && !isMilestone && (
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
        {item.baselineStartPercentage !== undefined && isMilestone && (
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

        {/* Update indicator - always visible in report view */}
        {activityUpdates && activityUpdates.length > 0 && (
          <div
            className="absolute flex items-center"
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
              className="rounded-full flex items-center justify-center"
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
              title={activityUpdates
                .map((u) => `[${u.update_type.toUpperCase()}] ${u.details}`)
                .join('\n')}
            >
              !
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function buildReportTooltip(item: PositionedItem): string {
  let tooltip = `${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Working Days: ${item.working_days}d
Calendar Days: ${item.calendar_days}d
Total Float: ${item.total_float}d`;

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

function getBarColor(index: number): string {
  const colors = ['#3B82F6'];
  return colors[index % colors.length];
}

export default GanttChart;
