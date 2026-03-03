/**
 * Gantt Style Settings
 *
 * Centralized visual configuration for Gantt chart rendering.
 * All layout percentages, colors, sizes, and opacities live here.
 *
 * Currently scoped to baseline visualization settings.
 * Future iterations will migrate row, bar, milestone, summary,
 * and relationship arrow defaults here as well.
 */

export interface GanttBaselineStyle {
  /** Vertical offset of baseline bar within the row, as CSS % string */
  barTopOffset: string;
  /** Height of baseline bar within the row, as CSS % string */
  barHeight: string;
  /** Minimum width in px for very short baseline bars */
  barMinWidth: number;
  /** Background color (CSS) */
  barBg: string;
  /** Border color (CSS) */
  barBorderColor: string;
  /** Border style: 'dashed' | 'solid' | 'dotted' */
  barBorderStyle: string;
  /** Opacity (0-1) for the baseline bar */
  barOpacity: number;

  /** Milestone diamond size in px */
  milestoneSize: number;
  /** Vertical offset for the baseline milestone, as CSS % string */
  milestoneTopOffset: string;
  /** Milestone border color */
  milestoneBorderColor: string;
  /** Milestone fill (use 'transparent' for hollow) */
  milestoneBg: string;

  /** Legend swatch border color */
  legendBorderColor: string;
  /** Legend swatch background */
  legendBg: string;
}

export interface GanttStyleSettings {
  baseline: GanttBaselineStyle;
  // Future sections:
  // row: GanttRowStyle;
  // bar: GanttBarStyle;
  // milestone: GanttMilestoneStyle;
  // summary: GanttSummaryStyle;
  // relationships: GanttRelationshipStyle;
}

const ganttStyleSettings: Readonly<GanttStyleSettings> = Object.freeze({
  baseline: {
    barTopOffset: '60%',
    barHeight: '30%',
    barMinWidth: 8,
    barBg: 'rgba(55, 65, 81, 0.30)',
    barBorderColor: 'rgb(107, 114, 128)',
    barBorderStyle: 'dashed',
    barOpacity: 0.5,

    milestoneSize: 8,
    milestoneTopOffset: '65%',
    milestoneBorderColor: 'rgb(107, 114, 128)',
    milestoneBg: 'transparent',

    legendBorderColor: 'rgb(107, 114, 128)',
    legendBg: 'rgba(55, 65, 81, 0.30)',
  },
});

export default ganttStyleSettings;
