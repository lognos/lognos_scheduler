import React, { useMemo } from 'react';
import { format, parseISO, differenceInDays, addMonths, startOfMonth } from 'date-fns';
import { X, Calendar, Filter, AlertTriangle } from 'lucide-react';
import { GanttChartData, ScheduleItem } from '@/types/schedule';

interface GanttPanelProps {
    data: GanttChartData;
    onClose: () => void;
}

/**
 * Floating Gantt chart panel that displays schedule data
 * streamed from the scheduling agent via AG-UI.
 */
export const GanttPanel: React.FC<GanttPanelProps> = ({ data, onClose }) => {
    // Generate timeline months from project dates
    const timeline = useMemo(() => {
        if (!data.items || data.items.length === 0) {
            return { months: [], totalDays: 0, startDate: new Date() };
        }

        try {
            const projectStart = parseISO(data.project_start);
            const projectEnd = parseISO(data.project_finish);

            // Start from the beginning of the start month
            const timelineStart = startOfMonth(projectStart);
            // End at the end of the end month
            const timelineEnd = addMonths(startOfMonth(projectEnd), 1);

            const months: { date: Date; label: string; shortLabel: string }[] = [];
            let currentDate = new Date(timelineStart);

            while (currentDate < timelineEnd) {
                months.push({
                    date: new Date(currentDate),
                    label: format(currentDate, 'MMM yyyy'),
                    shortLabel: format(currentDate, 'MMM'),
                });
                currentDate = addMonths(currentDate, 1);
            }

            const totalDays = differenceInDays(timelineEnd, timelineStart);
            return { months, totalDays, startDate: timelineStart };
        } catch (error) {
            console.error('Error generating timeline:', error);
            return { months: [], totalDays: 0, startDate: new Date() };
        }
    }, [data.project_start, data.project_finish, data.items]);

    // Process items for display with calculated positions
    const processedItems = useMemo(() => {
        if (!data.items || data.items.length === 0 || timeline.totalDays === 0) {
            return [];
        }

        return data.items
            .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
            .map((item) => {
                try {
                    const startDate = parseISO(item.start);
                    const finishDate = parseISO(item.finish);

                    const daysFromStart = differenceInDays(startDate, timeline.startDate);
                    const duration = differenceInDays(finishDate, startDate) + 1;

                    const startPercentage = (daysFromStart / timeline.totalDays) * 100;
                    const widthPercentage = (duration / timeline.totalDays) * 100;

                    return {
                        ...item,
                        startPercentage: Math.max(0, startPercentage),
                        widthPercentage: Math.max(1, widthPercentage),
                        duration,
                    };
                } catch {
                    return null;
                }
            })
            .filter(Boolean) as (ScheduleItem & {
                startPercentage: number;
                widthPercentage: number;
                duration: number;
            })[];
    }, [data.items, timeline]);

    // Build active filter description
    const filterDescription = useMemo(() => {
        const parts: string[] = [];
        const f = data.filter_applied;

        if (f.activity_codes) {
            Object.entries(f.activity_codes).forEach(([type, values]) => {
                parts.push(`${type}: ${values.join(', ')}`);
            });
        }
        if (f.wbs_path) parts.push(`WBS: ${f.wbs_path}`);
        if (f.critical_only) parts.push('Critical Path Only');
        if (f.status && f.status.length > 0) parts.push(`Status: ${f.status.join(', ')}`);
        if (f.search_term) parts.push(`Search: "${f.search_term}"`);

        return parts.length > 0 ? parts.join(' | ') : null;
    }, [data.filter_applied]);

    return (
        <div className="fixed top-20 right-8 bottom-30 w-[900px] bg-[#0d1117] border border-dark-700 rounded-xl shadow-2xl z-50 flex flex-col overflow-hidden">
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
            </div>

            {/* Filter indicator */}
            {filterDescription && (
                <div className="px-4 py-2 bg-blue-900/20 border-b border-dark-700 text-xs text-blue-300 flex items-center gap-2">
                    <Filter className="h-3 w-3" />
                    <span>{filterDescription}</span>
                </div>
            )}

            {/* Gantt chart content */}
            <div className="flex-1 overflow-auto p-4">
                {processedItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-400">
                        <AlertTriangle className="h-8 w-8 mb-2" />
                        <p>No activities match the current filter</p>
                    </div>
                ) : (
                    <div className="min-w-[500px]">
                        {/* Timeline header */}
                        <div className="mb-4">
                            {/* Year row */}
                            <div className="flex">
                                <div className="w-48 shrink-0"></div>
                                <div className="flex-1 flex text-xs text-gray-500">
                                    {(() => {
                                        const yearGroups: { year: string; monthCount: number }[] = [];
                                        let currentYear = '';
                                        let monthCount = 0;

                                        timeline.months.forEach((month) => {
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

                                        return yearGroups.map((group, index) => (
                                            <div
                                                key={index}
                                                className="text-center font-medium"
                                                style={{ flex: group.monthCount }}
                                            >
                                                {group.year}
                                            </div>
                                        ));
                                    })()}
                                </div>
                            </div>
                            {/* Month row */}
                            <div className="flex border-b border-dark-600 pb-2">
                                <div className="w-48 shrink-0 text-xs font-medium text-gray-400">Activity</div>
                                <div className="flex-1 flex text-xs text-gray-400">
                                    {timeline.months.map((month, index) => (
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

                        {/* Activity rows */}
                        <div className="space-y-1">
                            {processedItems.map((item) => {
                                const isSummary = item.is_summary === true;
                                const indentLevel = (item.level || 2) - 1;
                                const indentPx = indentLevel * 16;
                                
                                return (
                                    <div 
                                        key={item.id} 
                                        className={`flex items-center group ${isSummary ? 'bg-dark-700/30' : ''}`}
                                    >
                                        {/* Activity label with indentation */}
                                        <div 
                                            className="w-48 shrink-0 pr-2 flex items-center"
                                            style={{ paddingLeft: `${indentPx}px` }}
                                        >
                                            {isSummary && (
                                                <span className="text-xs text-yellow-500 mr-1" title={`${item.children_count} activities`}>
                                                    [{item.children_count}]
                                                </span>
                                            )}
                                            <div className="flex-1 min-w-0">
                                                <div 
                                                    className={`text-xs truncate ${
                                                        isSummary 
                                                            ? 'font-semibold text-yellow-400' 
                                                            : 'font-medium text-white'
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
                                                className={`absolute top-1 bottom-1 rounded transition-all duration-200 group-hover:opacity-80 flex items-center justify-center text-xs font-medium shadow-lg ${
                                                    isSummary
                                                        ? 'bg-yellow-600/80 border border-yellow-500'
                                                        : item.is_critical
                                                        ? 'bg-red-500'
                                                        : item.status === 'completed'
                                                        ? 'bg-green-600'
                                                        : item.status === 'in_progress'
                                                        ? 'bg-blue-500'
                                                        : 'bg-gray-600'
                                                }`}
                                                style={{
                                                    left: `${item.startPercentage}%`,
                                                    width: `${item.widthPercentage}%`,
                                                    minWidth: '16px',
                                                }}
                                                title={isSummary 
                                                    ? `${item.s_item} (Summary)
${item.children_count} activities
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Calendar Span: ${item.calendar_days}d
${item.is_critical ? '(Contains Critical Path)' : ''}`
                                                    : `${item.s_item}
Start: ${format(parseISO(item.start), 'MMM dd, yyyy')}
End: ${format(parseISO(item.finish), 'MMM dd, yyyy')}
Working Days: ${item.working_days}d
Calendar Days: ${item.calendar_days}d
Total Float: ${item.total_float.toFixed(1)} days
${item.is_critical ? '(Critical Path)' : ''}`}
                                            >
                                                {item.widthPercentage > 12 ? (
                                                    <span className="truncate px-1 text-white text-[10px]">
                                                        {isSummary 
                                                            ? `${item.calendar_days}d` 
                                                            : `${item.working_days}d / ${item.calendar_days}d`
                                                        }
                                                    </span>
                                                ) : item.widthPercentage > 6 ? (
                                                    <span className="truncate px-1 text-white text-[10px]">
                                                        {item.calendar_days}d
                                                    </span>
                                                ) : null}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            {/* Legend */}
            <div className="px-4 py-2 border-t border-dark-700 bg-dark-800/30 text-xs rounded-b-xl">
                <div className="flex items-center gap-4 text-gray-400">
                    {data.grouping && (
                        <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-yellow-600 border border-yellow-500"></div>
                            <span>Summary</span>
                        </div>
                    )}
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-red-500"></div>
                        <span>Critical</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-blue-500"></div>
                        <span>In Progress</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-green-600"></div>
                        <span>Completed</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-gray-600"></div>
                        <span>Not Started</span>
                    </div>
                </div>
                {data.grouping && (
                    <div className="mt-1 text-gray-500">
                        Grouped by: {data.grouping}
                    </div>
                )}
            </div>
        </div>
    );
};
