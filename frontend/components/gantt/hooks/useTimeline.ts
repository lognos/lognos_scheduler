/**
 * useTimeline Hook
 *
 * Generates timeline months and year groups for Gantt header rendering.
 * Consolidates duplicated logic from GanttChart.tsx and GanttPanel.tsx.
 */

import { useMemo } from 'react';
import {
  startOfMonth,
  addMonths,
  differenceInDays,
  format,
  parseISO,
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
 *
 * @param options - Timeline configuration
 * @returns Timeline data including months, year groups, total days, and start date
 */
export function useTimeline({
  items,
  projectStart,
  projectEnd,
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
      const itemStarts = items.map((item) => parseISO(item.start));
      const itemEnds = items.map((item) => parseISO(item.finish));

      // Include baseline dates so the timeline expands to fit them
      const baselineStarts = items
        .filter((item) => item.baseline_start)
        .map((item) => parseISO(item.baseline_start!));
      const baselineEnds = items
        .filter((item) => item.baseline_finish)
        .map((item) => parseISO(item.baseline_finish!));

      const allStarts = [...itemStarts, ...baselineStarts];
      const allEnds = [...itemEnds, ...baselineEnds];

      const dataStart = projectStart
        ? typeof projectStart === 'string'
          ? parseISO(projectStart)
          : projectStart
        : new Date(Math.min(...allStarts.map((d) => d.getTime())));

      const dataEnd = projectEnd
        ? typeof projectEnd === 'string'
          ? parseISO(projectEnd)
          : projectEnd
        : new Date(Math.max(...allEnds.map((d) => d.getTime())));

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
