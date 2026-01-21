/**
 * RelationshipArrows Component
 *
 * Renders SVG overlay with dependency arrows between Gantt chart activities.
 * Supports all four relationship types (FS, SS, FF, SF) with visual distinction
 * for critical path relationships.
 */

import React, { useRef, useState, useEffect, useCallback } from 'react';
import { ScheduleRelationship } from '@/types/schedule';
import { PositionedItem, useRelationshipPaths, RelationshipPath } from './hooks';

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

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  relationship: ScheduleRelationship | null;
}

// Arrow marker dimensions
const ARROW_HEAD_WIDTH = 6;
const ARROW_HEAD_HEIGHT = 5;

// Relationship type labels
const REL_TYPE_LABELS: Record<string, string> = {
  FS: 'Finish-to-Start',
  SS: 'Start-to-Start',
  FF: 'Finish-to-Finish',
  SF: 'Start-to-Finish',
};

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
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    x: 0,
    y: 0,
    relationship: null,
  });

  // Measure container width from wrapper div
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const updateWidth = () => {
      const width = wrapper.getBoundingClientRect().width;
      if (width > 0) {
        setContainerWidth(width);
      }
    };

    // Initial measurement
    updateWidth();

    const observer = new ResizeObserver(() => {
      updateWidth();
    });

    observer.observe(wrapper);

    return () => observer.disconnect();
  }, []);

  const paths = useRelationshipPaths({
    items,
    relationships,
    rowHeight,
    showCriticalOnly,
    containerWidth,
  });

  const handleMouseEnter = useCallback((e: React.MouseEvent, pathData: RelationshipPath) => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    
    setTooltip({
      visible: true,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      relationship: pathData.relationship,
    });
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    
    setTooltip((prev) => ({
      ...prev,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    }));
  }, []);

  const handleMouseLeave = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false, relationship: null }));
  }, []);

  return (
    <div 
      ref={wrapperRef}
      className="absolute inset-0 pointer-events-none" 
      style={{ height: totalHeight }}
    >
      {containerWidth > 0 && paths.length > 0 && (
        <svg
          className="absolute inset-0 overflow-visible pointer-events-none"
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
            <g key={pathData.id} style={{ pointerEvents: 'auto' }}>
              {/* Invisible wider path for easier hover detection */}
              <path
                d={pathData.path}
                stroke="rgba(255,255,255,0.001)"
                strokeWidth={14}
                fill="none"
                className="cursor-pointer"
                onMouseEnter={(e) => handleMouseEnter(e, pathData)}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
              />
              {/* Visible arrow path */}
              <path
                d={pathData.path}
                stroke={pathData.color}
                strokeWidth={pathData.strokeWidth}
                fill="none"
                markerEnd={`url(#arrowhead-${pathData.relationship.is_critical ? 'critical' : 'normal'})`}
                className={`pointer-events-none ${
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
                  className={`pointer-events-none font-medium ${
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
      )}

      {/* Tooltip */}
      {tooltip.visible && tooltip.relationship && (
        <div
          className="absolute z-50 px-3 py-2 text-xs bg-dark-800 border border-dark-600 rounded-lg shadow-xl pointer-events-none"
          style={{
            left: tooltip.x + 12,
            top: tooltip.y - 10,
            transform: 'translateY(-100%)',
          }}
        >
          <div className="flex flex-col gap-1 text-gray-300 whitespace-nowrap">
            <div className="flex gap-2">
              <span className="text-gray-500">Predecessor:</span>
              <span className="font-medium text-white">{tooltip.relationship.pred_id}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-gray-500">Successor:</span>
              <span className="font-medium text-white">{tooltip.relationship.succ_id}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-gray-500">Type:</span>
              <span className="font-medium text-white">
                {tooltip.relationship.rel_type} ({REL_TYPE_LABELS[tooltip.relationship.rel_type]})
              </span>
            </div>
            {tooltip.relationship.lag_days !== 0 && (
              <div className="flex gap-2">
                <span className="text-gray-500">Lag:</span>
                <span className={`font-medium ${tooltip.relationship.lag_days > 0 ? 'text-amber-400' : 'text-blue-400'}`}>
                  {tooltip.relationship.lag_days > 0 ? '+' : ''}{tooltip.relationship.lag_days}d
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RelationshipArrows;
