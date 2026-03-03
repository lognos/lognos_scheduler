/**
 * Gantt Hook Types
 *
 * Minimal type additions for the extracted hooks.
 * Extends existing schedule.ts types without transformation layers.
 */

import { ScheduleItem, ScheduleRelationship, RelationshipType } from '@/types/schedule';

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
  /** Baseline bar start as percentage (0-100), undefined if no baseline */
  baselineStartPercentage?: number;
  /** Baseline bar width as percentage, undefined if no baseline */
  baselineWidthPercentage?: number;
}

/**
 * Anchor point coordinates for relationship arrow endpoints
 */
export interface AnchorPoint {
  /** X coordinate as percentage (0-100) */
  x: number;
  /** Y coordinate in pixels (row center) */
  y: number;
}

/**
 * Calculated SVG path data for rendering a relationship arrow
 */
export interface RelationshipPath {
  /** Unique identifier for React key */
  id: string;
  /** SVG path 'd' attribute */
  path: string;
  /** Original relationship data */
  relationship: ScheduleRelationship;
  /** Path stroke color (hex) */
  color: string;
  /** Stroke width in pixels */
  strokeWidth: number;
  /** Lag label text (e.g., "+2d", "-1d") */
  lagLabel: string | null;
  /** Position for lag label */
  lagLabelPosition: { x: number; y: number } | null;
}

// Re-export for convenience
export type { RelationshipType, ScheduleRelationship };
