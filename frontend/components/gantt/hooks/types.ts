/**
 * Gantt Hook Types
 *
 * Minimal type additions for the extracted hooks.
 * Extends existing schedule.ts types without transformation layers.
 */

import { ScheduleItem } from '@/types/schedule';

/**
 * Sorting modes for activity display order.
 */
export type SortMode =
  | 'preserve' // Keep backend order (MS Project hierarchy)
  | 'start-date' // Sort by start date (simple P6 display)
  | 'grouped'; // Group-aware: group name → summaries first → start date

/**
 * A single month in the timeline header
 */
export interface TimelineMonth {
  date: Date;
  label: string; // "Jan 2026"
  shortLabel: string; // "Jan"
}

/**
 * A year grouping for the year header row
 */
export interface YearGroup {
  year: string;
  monthCount: number;
}

/**
 * Calculated timeline data for header rendering
 */
export interface TimelineData {
  months: TimelineMonth[];
  totalDays: number;
  startDate: Date;
  yearGroups: YearGroup[];
}

/**
 * Schedule item with calculated bar position
 */
export interface PositionedItem extends ScheduleItem {
  startPercentage: number;
  widthPercentage: number;
  duration: number;
}
