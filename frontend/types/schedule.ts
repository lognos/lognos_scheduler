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
  /** Internal database task ID (negative for synthetic summary items) */
  id: number;
  /** Activity code (e.g., "A1010") or group code for summaries */
  s_item_id: string;
  /** Activity name/description or group name */
  s_item: string;
  /** Duration in working days (planned hours / 8) */
  working_days: number;
  /** Duration in calendar days (finish - start + 1, includes weekends) */
  calendar_days: number;
  /** Total float in work days */
  total_float: number;
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

  // Hierarchy fields for grouped display
  /** Display level: 1 = summary/group, 2 = detail activity */
  level?: number;
  /** Whether this is a summary bar spanning child activities */
  is_summary?: boolean;
  /** Parent summary item ID (for level 2 items) */
  parent_id?: string | null;
  /** Number of child activities (for summary items) */
  children_count?: number;
  /** Group name this item belongs to */
  group_name?: string | null;
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
  /** Start date filter (ISO format: YYYY-MM-DD) */
  date_start?: string;
  /** End date filter (ISO format: YYYY-MM-DD) */
  date_end?: string;
}

/**
 * Available activity codes for filtering
 * Maps code type name to array of available values
 */
export interface AvailableActivityCodes {
  [codeTypeName: string]: string[];
}

/**
 * Relationship types for schedule dependencies
 */
export type RelationshipType = 'FS' | 'SS' | 'FF' | 'SF';

/**
 * Relationship between two activities for Gantt visualization
 */
export interface ScheduleRelationship {
  /** Predecessor activity code (s_item_id) */
  pred_id: string;
  /** Successor activity code (s_item_id) */
  succ_id: string;
  /** Relationship type: FS (Finish-to-Start), SS (Start-to-Start), FF (Finish-to-Finish), SF (Start-to-Finish) */
  rel_type: RelationshipType;
  /** Lag in days (positive = delay, negative = lead) */
  lag_days: number;
  /** Whether this relationship is on the critical path */
  is_critical?: boolean;
}

/**
 * Complete Gantt chart data streamed from the agent
 */
export interface GanttChartData {
  /** List of activities to display */
  items: ScheduleItem[];
  /** Relationships between activities for dependency arrows */
  relationships?: ScheduleRelationship[];
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
  /** Current grouping applied (e.g., "Phase", "WBS", null) */
  grouping?: string | null;
  /** If true, items are pre-sorted (MS Project hierarchy) - don't re-sort on frontend */
  preserve_order?: boolean;
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

export type PredefinedScheduleViewKey = 'critical_path' | 'lookahead_4w' | 'full_schedule';
export type ScheduleViewKey = PredefinedScheduleViewKey | 'custom';

export interface ScheduleViewMeta {
  view_key: ScheduleViewKey;
  view_name: string;
  view_type: string;
  is_default: boolean;
  computed_at?: string | null;
}

export interface ScheduleViewsPreloadResponse {
  project_id: string;
  schedule_version_id: number;
  default_view_key: PredefinedScheduleViewKey;
  views: ScheduleViewMeta[];
  payload: GanttChartData;
}

export interface ScheduleViewResponse {
  project_id: string;
  schedule_version_id: number;
  view_key: PredefinedScheduleViewKey;
  view_name: string;
  computed_at?: string | null;
  payload: GanttChartData;
}
