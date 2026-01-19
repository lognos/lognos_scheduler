/**
 * useRelationshipPaths Hook
 *
 * Calculates SVG path data for relationship arrows between activities.
 * Handles all four relationship types (FS, SS, FF, SF) with proper routing.
 * 
 * Arrow entry/exit rules:
 * - FS: Exit right of pred → Enter left of succ (arrow points →)
 * - SS: Exit left of pred → Enter left of succ (arrow points →)
 * - FF: Exit right of pred → Enter right of succ (arrow points ←)
 * - SF: Exit left of pred → Enter right of succ (arrow points ←)
 * 
 * When there's insufficient space, paths route around (inverse-S pattern).
 */

import { useMemo } from 'react';
import { ScheduleRelationship, RelationshipType } from '@/types/schedule';
import { PositionedItem, RelationshipPath, AnchorPoint } from './types';

interface UseRelationshipPathsOptions {
  /** Positioned activity items with calculated percentages */
  items: PositionedItem[];
  /** Relationships to render */
  relationships: ScheduleRelationship[];
  /** Row height in pixels */
  rowHeight: number;
  /** Whether to show only critical path relationships */
  showCriticalOnly?: boolean;
  /** Container width in pixels (for percentage to pixel conversion) */
  containerWidth: number;
}

// Visual constants
const HORIZONTAL_OFFSET = 6; // Pixels offset from bar edge for arrow tip
const CORNER_RADIUS = 4; // Match activity bar border-radius
const MIN_HORIZONTAL_SPACE = 20; // Minimum space needed for direct routing
const ROUTE_AROUND_GAP = 12; // Gap when routing around bars

// Colors
const CRITICAL_COLOR = '#EF4444'; // red-500
const NORMAL_COLOR = '#6B7280'; // gray-500
const CRITICAL_STROKE_WIDTH = 1.5;
const NORMAL_STROKE_WIDTH = 1;

/**
 * Calculates SVG path data for relationship arrows.
 */
export function useRelationshipPaths({
  items,
  relationships,
  rowHeight,
  showCriticalOnly = false,
  containerWidth,
}: UseRelationshipPathsOptions): RelationshipPath[] {
  return useMemo(() => {
    if (!items || items.length === 0 || !relationships || relationships.length === 0 || containerWidth === 0) {
      return [];
    }

    // Build lookup map: s_item_id → (row index, item)
    const itemMap = new Map<string, { item: PositionedItem; rowIndex: number }>();
    items.forEach((item, index) => {
      itemMap.set(item.s_item_id, { item, rowIndex: index });
    });

    // Filter and calculate paths
    return relationships
      .filter((rel) => !showCriticalOnly || rel.is_critical)
      .map((rel) => calculatePath(rel, itemMap, rowHeight, containerWidth))
      .filter((path): path is RelationshipPath => path !== null);
  }, [items, relationships, rowHeight, showCriticalOnly, containerWidth]);
}

interface BarBounds {
  left: number;
  right: number;
  centerY: number;
  rowIndex: number;
}

/**
 * Calculate the SVG path for a single relationship.
 */
function calculatePath(
  rel: ScheduleRelationship,
  itemMap: Map<string, { item: PositionedItem; rowIndex: number }>,
  rowHeight: number,
  containerWidth: number
): RelationshipPath | null {
  const pred = itemMap.get(rel.pred_id);
  const succ = itemMap.get(rel.succ_id);

  if (!pred || !succ) return null;

  // Calculate bar bounds in pixels
  const predBounds: BarBounds = {
    left: (pred.item.startPercentage / 100) * containerWidth,
    right: ((pred.item.startPercentage + pred.item.widthPercentage) / 100) * containerWidth,
    centerY: pred.rowIndex * rowHeight + rowHeight / 2,
    rowIndex: pred.rowIndex,
  };

  const succBounds: BarBounds = {
    left: (succ.item.startPercentage / 100) * containerWidth,
    right: ((succ.item.startPercentage + succ.item.widthPercentage) / 100) * containerWidth,
    centerY: succ.rowIndex * rowHeight + rowHeight / 2,
    rowIndex: succ.rowIndex,
  };

  // Generate path based on relationship type
  const path = generatePathForRelType(rel.rel_type, predBounds, succBounds, rowHeight);

  // Calculate lag label position
  const lagLabel = formatLagLabel(rel.lag_days);
  const predAnchor = getExitPoint(rel.rel_type, predBounds);
  const succAnchor = getEntryPoint(rel.rel_type, succBounds);
  const lagLabelPosition = lagLabel ? calculateLagLabelPosition(predAnchor, succAnchor) : null;

  return {
    id: `${rel.pred_id}-${rel.succ_id}-${rel.rel_type}`,
    path,
    relationship: rel,
    color: rel.is_critical ? CRITICAL_COLOR : NORMAL_COLOR,
    strokeWidth: rel.is_critical ? CRITICAL_STROKE_WIDTH : NORMAL_STROKE_WIDTH,
    lagLabel,
    lagLabelPosition,
  };
}

/**
 * Get exit point from predecessor based on relationship type.
 */
function getExitPoint(relType: RelationshipType, bounds: BarBounds): AnchorPoint {
  switch (relType) {
    case 'FS':
    case 'FF':
      return { x: bounds.right + HORIZONTAL_OFFSET, y: bounds.centerY }; // Exit right
    case 'SS':
    case 'SF':
      return { x: bounds.left - HORIZONTAL_OFFSET, y: bounds.centerY }; // Exit left
  }
}

/**
 * Get entry point to successor based on relationship type.
 */
function getEntryPoint(relType: RelationshipType, bounds: BarBounds): AnchorPoint {
  switch (relType) {
    case 'FS':
    case 'SS':
      return { x: bounds.left - HORIZONTAL_OFFSET, y: bounds.centerY }; // Enter left (arrow →)
    case 'FF':
    case 'SF':
      return { x: bounds.right + HORIZONTAL_OFFSET, y: bounds.centerY }; // Enter right (arrow ←)
  }
}

/**
 * Generate path based on relationship type with proper routing.
 */
function generatePathForRelType(
  relType: RelationshipType,
  pred: BarBounds,
  succ: BarBounds,
  rowHeight: number
): string {
  const r = CORNER_RADIUS;
  const goingDown = succ.rowIndex > pred.rowIndex;
  const verticalDir = goingDown ? 1 : -1;

  switch (relType) {
    case 'FS':
      return generateFSPath(pred, succ, r, goingDown, verticalDir, rowHeight);
    case 'SS':
      return generateSSPath(pred, succ, r, goingDown, verticalDir, rowHeight);
    case 'FF':
      return generateFFPath(pred, succ, r, goingDown, verticalDir, rowHeight);
    case 'SF':
      return generateSFPath(pred, succ, r, goingDown, verticalDir, rowHeight);
  }
}

/**
 * FS: Exit right → Enter left (arrow points →)
 * Direct Z-path if space allows, otherwise inverse-S routing below/above.
 */
function generateFSPath(
  pred: BarBounds,
  succ: BarBounds,
  r: number,
  goingDown: boolean,
  verticalDir: number,
  rowHeight: number
): string {
  const exitX = pred.right + HORIZONTAL_OFFSET;
  const entryX = succ.left - HORIZONTAL_OFFSET;
  const exitY = pred.centerY;
  const entryY = succ.centerY;

  // Check if there's enough horizontal space for direct routing
  const hasSpace = entryX - exitX >= MIN_HORIZONTAL_SPACE;

  if (hasSpace) {
    // Direct Z-path: exit → horizontal → down → horizontal → enter
    const midX = (exitX + entryX) / 2;
    return buildPath([
      `M ${exitX} ${exitY}`,
      `L ${midX - r} ${exitY}`,
      `Q ${midX} ${exitY} ${midX} ${exitY + r * verticalDir}`,
      `L ${midX} ${entryY - r * verticalDir}`,
      `Q ${midX} ${entryY} ${midX + r} ${entryY}`,
      `L ${entryX} ${entryY}`,
    ]);
  } else {
    // Inverse-S: route around to the left side to enter from left
    // Path: exit right → drop halfway → go left past succ.left → drop to entry Y → enter
    const midY = exitY + (rowHeight / 2 + 4) * verticalDir; // Halfway point between rows
    const routeX = Math.min(pred.left, succ.left) - ROUTE_AROUND_GAP; // Left of both bars
    
    return buildPath([
      `M ${exitX} ${exitY}`,
      // Go right a bit then curve down
      `L ${exitX + r} ${exitY}`,
      `Q ${exitX + r * 2} ${exitY} ${exitX + r * 2} ${exitY + r * verticalDir}`,
      // Drop to midY
      `L ${exitX + r * 2} ${midY - r * verticalDir}`,
      // Curve left
      `Q ${exitX + r * 2} ${midY} ${exitX + r} ${midY}`,
      // Go left to routeX
      `L ${routeX + r} ${midY}`,
      // Curve down
      `Q ${routeX} ${midY} ${routeX} ${midY + r * verticalDir}`,
      // Drop to entryY
      `L ${routeX} ${entryY - r * verticalDir}`,
      // Curve right toward entry
      `Q ${routeX} ${entryY} ${routeX + r} ${entryY}`,
      // Final horizontal to entry
      `L ${entryX} ${entryY}`,
    ]);
  }
}

/**
 * SS: Exit left → Enter left (arrow points →)
 * Route down on left side of both bars.
 */
function generateSSPath(
  pred: BarBounds,
  succ: BarBounds,
  r: number,
  goingDown: boolean,
  verticalDir: number,
  rowHeight: number
): string {
  const exitX = pred.left - HORIZONTAL_OFFSET;
  const entryX = succ.left - HORIZONTAL_OFFSET;
  const exitY = pred.centerY;
  const entryY = succ.centerY;

  // Route on the left side of both bars
  const leftMost = Math.min(exitX, entryX) - ROUTE_AROUND_GAP;

  return buildPath([
    `M ${exitX} ${exitY}`,
    `L ${leftMost + r} ${exitY}`,
    `Q ${leftMost} ${exitY} ${leftMost} ${exitY + r * verticalDir}`,
    `L ${leftMost} ${entryY - r * verticalDir}`,
    `Q ${leftMost} ${entryY} ${leftMost + r} ${entryY}`,
    `L ${entryX} ${entryY}`,
  ]);
}

/**
 * FF: Exit right → Enter right (arrow points ←)
 * Route down on right side of both bars.
 */
function generateFFPath(
  pred: BarBounds,
  succ: BarBounds,
  r: number,
  goingDown: boolean,
  verticalDir: number,
  rowHeight: number
): string {
  const exitX = pred.right + HORIZONTAL_OFFSET;
  const entryX = succ.right + HORIZONTAL_OFFSET;
  const exitY = pred.centerY;
  const entryY = succ.centerY;

  // Route on the right side of both bars
  const rightMost = Math.max(exitX, entryX) + ROUTE_AROUND_GAP;

  return buildPath([
    `M ${exitX} ${exitY}`,
    `L ${rightMost - r} ${exitY}`,
    `Q ${rightMost} ${exitY} ${rightMost} ${exitY + r * verticalDir}`,
    `L ${rightMost} ${entryY - r * verticalDir}`,
    `Q ${rightMost} ${entryY} ${rightMost - r} ${entryY}`,
    `L ${entryX} ${entryY}`,
  ]);
}

/**
 * SF: Exit left → Enter right (arrow points ←)
 * Direct path if space allows, otherwise inverse-S routing to the right.
 */
function generateSFPath(
  pred: BarBounds,
  succ: BarBounds,
  r: number,
  goingDown: boolean,
  verticalDir: number,
  rowHeight: number
): string {
  const exitX = pred.left - HORIZONTAL_OFFSET;
  const entryX = succ.right + HORIZONTAL_OFFSET;
  const exitY = pred.centerY;
  const entryY = succ.centerY;

  // Check if there's enough horizontal space (exit is left of entry)
  const hasSpace = exitX - entryX >= MIN_HORIZONTAL_SPACE;

  if (hasSpace) {
    // Direct path: exit left → down → enter right
    const midX = (exitX + entryX) / 2;
    return buildPath([
      `M ${exitX} ${exitY}`,
      `L ${midX + r} ${exitY}`,
      `Q ${midX} ${exitY} ${midX} ${exitY + r * verticalDir}`,
      `L ${midX} ${entryY - r * verticalDir}`,
      `Q ${midX} ${entryY} ${midX - r} ${entryY}`,
      `L ${entryX} ${entryY}`,
    ]);
  } else {
    // Inverse-S: route around to the right side to enter from right
    // Path: exit left → drop halfway → go right past succ.right → drop to entry Y → enter
    const midY = exitY + (rowHeight / 2 + 4) * verticalDir; // Halfway point between rows
    const routeX = Math.max(pred.right, succ.right) + ROUTE_AROUND_GAP; // Right of both bars
    
    return buildPath([
      `M ${exitX} ${exitY}`,
      // Go left a bit then curve down
      `L ${exitX - r} ${exitY}`,
      `Q ${exitX - r * 2} ${exitY} ${exitX - r * 2} ${exitY + r * verticalDir}`,
      // Drop to midY
      `L ${exitX - r * 2} ${midY - r * verticalDir}`,
      // Curve right
      `Q ${exitX - r * 2} ${midY} ${exitX - r} ${midY}`,
      // Go right to routeX
      `L ${routeX - r} ${midY}`,
      // Curve down
      `Q ${routeX} ${midY} ${routeX} ${midY + r * verticalDir}`,
      // Drop to entryY
      `L ${routeX} ${entryY - r * verticalDir}`,
      // Curve left toward entry
      `Q ${routeX} ${entryY} ${routeX - r} ${entryY}`,
      // Final horizontal to entry
      `L ${entryX} ${entryY}`,
    ]);
  }
}

/**
 * Build SVG path string from segments.
 */
function buildPath(segments: string[]): string {
  return segments.join(' ');
}

/**
 * Format lag value as a label string.
 */
function formatLagLabel(lagDays: number): string | null {
  if (!lagDays || lagDays === 0) return null;

  const sign = lagDays > 0 ? '+' : '';
  const value = Math.abs(lagDays);
  const formatted = Number.isInteger(value) ? value.toString() : value.toFixed(1);

  return `${sign}${formatted}d`;
}

/**
 * Calculate position for the lag label (midpoint of path).
 */
function calculateLagLabelPosition(
  from: AnchorPoint,
  to: AnchorPoint
): { x: number; y: number } {
  return {
    x: (from.x + to.x) / 2,
    y: (from.y + to.y) / 2 - 6,
  };
}
