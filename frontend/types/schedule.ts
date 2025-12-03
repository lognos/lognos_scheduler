/**
 * Schedule and Gantt Chart Types
 * 
 * Types for the NetworkX-based CPM schedule visualization
 * streamed via AG-UI from the scheduling agent.
 */

/**
 * A single activity/task in the Gantt chart
 */
export interface ScheduleItem {
  /** Internal database task ID */
  id: number;
  /** Activity code (e.g., "A1010") */
  s_item_id: string;
  /** Activity name/description */
  s_item: string;
  /** Total float in work days */
  total_duration: number;
  /** Early start date (ISO format) */
  start: string;
  /** Early finish date (ISO format) */
  finish: string;
  /** Whether this activity is on the critical path */
  is_critical: boolean;
  /** WBS path (e.g., "Project/Phase1/Civil") */
  wbs_path: string;
  /** Activity status: not_started, in_progress, completed */
  status: 'not_started' | 'in_progress' | 'completed';
}

/**
 * Filter configuration applied to the Gantt display
 */
export interface GanttFilter {
  /** WBS path filter */
  wbs_path?: string;
  /** Show only critical path activities */
  critical_only?: boolean;
  /** Activity code filters: { "Phase": ["Phase 1"], "Discipline": ["Civil"] } */
  activity_codes?: Record<string, string[]>;
  /** Status filter */
  status?: string[];
  /** Text search term */
  search_term?: string;
}

/**
 * Available activity codes for filtering
 * Maps code type name to array of available values
 */
export interface AvailableActivityCodes {
  [codeTypeName: string]: string[];
}

/**
 * Complete Gantt chart data streamed from the agent
 */
export interface GanttChartData {
  /** List of activities to display */
  items: ScheduleItem[];
  /** Project start date (ISO format) */
  project_start: string;
  /** Project finish date (ISO format) */
  project_finish: string;
  /** Length of critical path in work days */
  critical_path_length: number;
  /** Currently applied filters */
  filter_applied: GanttFilter;
  /** Total activities in workspace (before filtering) */
  total_activities: number;
  /** Number of activities after filtering */
  filtered_activities: number;
  /** Available activity codes for filter UI */
  available_activity_codes: AvailableActivityCodes;
}

/**
 * Gantt panel event streamed via AG-UI
 */
export interface GanttPanelEvent {
  type: 'gantt_panel';
  action: 'show' | 'hide';
  data?: GanttChartData;
}

/**
 * Gantt panel state for the UI
 */
export interface GanttPanelState {
  /** Whether the panel is visible */
  isVisible: boolean;
  /** Current Gantt data (when visible) */
  data: GanttChartData | null;
  /** Loading state */
  isLoading: boolean;
}
