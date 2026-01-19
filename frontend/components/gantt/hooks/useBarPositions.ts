/**
 * useBarPositions Hook
 *
 * Calculates bar positions as percentages for each schedule item.
 * Consolidates duplicated logic from GanttChart.tsx and GanttPanel.tsx.
 */

import { useMemo } from 'react';
import { differenceInDays, parseISO } from 'date-fns';
import { ScheduleItem } from '@/types/schedule';
import { PositionedItem, SortMode } from './types';

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
 *
 * @param options - Bar positioning configuration
 * @returns Array of items with calculated position percentages
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

    return sortedItems
      .map((item) => {
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
      })
      .filter(Boolean) as PositionedItem[];
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
    return [...items].sort(
      (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
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
