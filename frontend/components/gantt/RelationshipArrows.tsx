/**
 * RelationshipArrows Component
 *
 * Renders SVG overlay with dependency arrows between Gantt chart activities.
 * Supports all four relationship types (FS, SS, FF, SF) with visual distinction
 * for critical path relationships.
 */

import React, { useRef, useState, useEffect } from 'react';
import { ScheduleRelationship } from '@/types/schedule';
import { PositionedItem, useRelationshipPaths } from './hooks';

interface RelationshipArrowsProps {
  /** Positioned activity items with calculated percentages */
  items: PositionedItem[];
  /** Relationships to render */
  relationships: ScheduleRelationship[];
  /** Row height in pixels (must match Gantt row height) */
  rowHeight: number;
  /** Whether to show only critical path relationships (default: true) */
  showCriticalOnly?: boolean;
  /** Total height of the container in pixels */
  totalHeight: number;
}

// Arrow marker dimensions
const ARROW_HEAD_WIDTH = 6;
const ARROW_HEAD_HEIGHT = 5;

/**
 * RelationshipArrows renders an SVG overlay with dependency arrows.
 *
 * The component uses absolute positioning to overlay the Gantt timeline area.
 * Arrows are rendered as SVG paths with arrow head markers.
 */
export function RelationshipArrows({
  items,
  relationships,
  rowHeight,
  showCriticalOnly = true,
  totalHeight,
}: RelationshipArrowsProps) {
  const containerRef = useRef<SVGSVGElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  // Measure container width
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });

    observer.observe(containerRef.current);
    // Initial measurement
    setContainerWidth(containerRef.current.getBoundingClientRect().width);

    return () => observer.disconnect();
  }, []);

  const paths = useRelationshipPaths({
    items,
    relationships,
    rowHeight,
    showCriticalOnly,
    containerWidth,
  });

  if (paths.length === 0 || containerWidth === 0) {
    return (
      <svg
        ref={containerRef}
        className="absolute inset-0 pointer-events-none"
        style={{ width: '100%', height: totalHeight }}
      />
    );
  }

  return (
    <svg
      ref={containerRef}
      className="absolute inset-0 pointer-events-none overflow-visible"
      style={{
        width: '100%',
        height: totalHeight,
        zIndex: 10,
      }}
      aria-hidden="true"
    >
      <defs>
        {/* Critical path arrow marker (red) */}
        <marker
          id="arrowhead-critical"
          markerWidth={ARROW_HEAD_WIDTH}
          markerHeight={ARROW_HEAD_HEIGHT}
          refX={ARROW_HEAD_WIDTH - 1}
          refY={ARROW_HEAD_HEIGHT / 2}
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <polygon
            points={`0 0, ${ARROW_HEAD_WIDTH} ${ARROW_HEAD_HEIGHT / 2}, 0 ${ARROW_HEAD_HEIGHT}`}
            fill="#EF4444"
            className="print:fill-black"
          />
        </marker>

        {/* Normal (non-critical) arrow marker (gray) */}
        <marker
          id="arrowhead-normal"
          markerWidth={ARROW_HEAD_WIDTH}
          markerHeight={ARROW_HEAD_HEIGHT}
          refX={ARROW_HEAD_WIDTH - 1}
          refY={ARROW_HEAD_HEIGHT / 2}
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <polygon
            points={`0 0, ${ARROW_HEAD_WIDTH} ${ARROW_HEAD_HEIGHT / 2}, 0 ${ARROW_HEAD_HEIGHT}`}
            fill="#6B7280"
            className="print:fill-gray-600"
          />
        </marker>
      </defs>

      {/* Relationship arrow paths */}
      {paths.map((pathData) => (
        <g key={pathData.id}>
          {/* Arrow path */}
          <path
            d={pathData.path}
            stroke={pathData.color}
            strokeWidth={pathData.strokeWidth}
            fill="none"
            markerEnd={`url(#arrowhead-${pathData.relationship.is_critical ? 'critical' : 'normal'})`}
            className={`${
              pathData.relationship.is_critical
                ? 'print:stroke-black'
                : 'print:stroke-gray-600'
            }`}
            style={{
              strokeLinecap: 'round',
              strokeLinejoin: 'round',
            }}
          />

          {/* Lag label */}
          {pathData.lagLabel && pathData.lagLabelPosition && (
            <text
              x={pathData.lagLabelPosition.x}
              y={pathData.lagLabelPosition.y}
              textAnchor="middle"
              fontSize="9"
              className={`font-medium ${
                pathData.relationship.is_critical
                  ? 'fill-red-500 print:fill-black'
                  : 'fill-gray-500 print:fill-gray-600'
              }`}
              style={{
                paintOrder: 'stroke',
                stroke: 'rgba(13, 17, 23, 0.8)',
                strokeWidth: 2,
                strokeLinejoin: 'round',
              }}
            >
              {pathData.lagLabel}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

export default RelationshipArrows;
