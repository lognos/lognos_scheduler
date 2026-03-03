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

export interface GanttUpdateIndicatorStyle {
  /** Indicator circle diameter in px */
  size: number;
  /** Background color for the indicator circle */
  bg: string;
  /** Text color for the "!" symbol */
  textColor: string;
  /** Font size for the "!" symbol */
  fontSize: string;
  /** Font weight for the "!" */
  fontWeight: string;
  /** Horizontal offset from the end of the bar, in px */
  offsetRight: number;

  /** Tooltip max width */
  tooltipMaxWidth: number;

  /** Type badge colors: bg, text for each update_type */
  typeBadge: {
    delay: { bg: string; text: string };
    completion: { bg: string; text: string };
    start: { bg: string; text: string };
  };

  /** Legend swatch color */
  legendBg: string;
  legendTextColor: string;
}

export interface GanttStyleSettings {
  baseline: GanttBaselineStyle;
  updates: GanttUpdateIndicatorStyle;
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
  updates: {
    size: 16,
    bg: 'rgb(217, 119, 6)',
    textColor: 'rgb(255, 255, 255)',
    fontSize: '10px',
    fontWeight: '700',
    offsetRight: -20,

    tooltipMaxWidth: 320,

    typeBadge: {
      delay: { bg: 'rgba(239, 68, 68, 0.15)', text: 'rgb(248, 113, 113)' },
      completion: { bg: 'rgba(16, 185, 129, 0.15)', text: 'rgb(52, 211, 153)' },
      start: { bg: 'rgba(59, 130, 246, 0.15)', text: 'rgb(96, 165, 250)' },
    },

    legendBg: 'rgb(217, 119, 6)',
    legendTextColor: 'rgb(255, 255, 255)',
  },
});

export default ganttStyleSettings;
