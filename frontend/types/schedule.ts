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
  /** Physical percent complete (0-100), when available */
  percent_complete?: number;

  // Baseline fields (MS Project schedules)
  /** Baseline start date (ISO format), null if no baseline set */
  baseline_start?: string | null;
  /** Baseline finish date (ISO format), null if no baseline set */
  baseline_finish?: string | null;
  /** Baseline duration in working days, null if no baseline set */
  baseline_duration_d?: number | null;

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
  /** P6-style critical definition used by the backend view */
  critical_definition?: 'total_float' | 'longest_path' | 'free_float_path';
  /** Total-float threshold, in days, when critical_definition is total_float */
  float_threshold_d?: number | null;
  /** Multiple-float-path number when a float path view is selected */
  float_path?: number | null;
  /** Multiple-float-path calculation method */
  float_path_method?: 'total_float' | 'free_float' | null;
  /** Selected end target for longest-path / float-path views */
  path_target?: 'project_finish' | string | null;
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
 * Baseline comparison mode
 * - own: Current version's embedded baseline (default)
 * - previous_version: Start/finish dates from the previous schedule version
 * - database_baseline: Start/finish dates from the version flagged is_baseline=true
 * - what_if: Filter-scoped baseline derived from visible activities (what-if analysis)
 */
export type BaselineMode = 'own' | 'previous_version' | 'database_baseline' | 'what_if';

/**
 * A user-reported activity update (delay, completion, start)
 */
export interface ActivityUpdate {
  /** Unique log identifier */
  log_id: string;
  /** Activity code (ms_uid as string) — matches ScheduleItem.s_item_id */
  s_item_id: string;
  /** Update type: delay, completion, start */
  update_type: 'delay' | 'completion' | 'start';
  /** Free-text description of the update */
  details: string;
  /** Structured value (date, duration text, etc.) */
  reported_value?: string | null;
  /** Email of the reporter */
  reported_by: string;
  /** ISO timestamp of when the update was reported */
  reported_at: string;
  /** Whether the update has been incorporated into the schedule */
  processed: boolean;
}

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

export interface GanttCapabilities {
  links: {
    available: boolean;
    render_enabled: boolean;
  };
  updates: {
    available: boolean;
    render_enabled: boolean;
  };
  baseline_modes: {
    available: BaselineMode[];
    selected: BaselineMode;
  };
  columns: {
    available: string[];
    selected: string[];
  };
  what_if: {
    supported: boolean;
    active_scenario_id: string | null;
    overlay_available: boolean;
  };
}

export interface GanttDataEnvelope {
  activities: ScheduleItem[];
  relationships: Array<{
    id: string;
    pred_id: string;
    succ_id: string;
    rel_type: RelationshipType;
    lag_days: number;
  }>;
  baselines: {
    own: { activities: Array<{ id: number; s_item_id: string; start: string | null; finish: string | null; duration_d: number | null }> };
    previous_version: { activities: Array<{ id: number; s_item_id: string; start: string | null; finish: string | null; duration_d: number | null }> };
    database_baseline: { activities: Array<{ id: number; s_item_id: string; start: string | null; finish: string | null; duration_d: number | null }> };
  };
  updates: ActivityUpdate[];
}

export interface GanttDisplay {
  filter_applied: GanttFilter;
  visible_activity_ids: number[];
  visible_relationship_ids: string[];
  project_start: string;
  project_finish: string;
  critical_path_length: number;
  total_activities: number;
  filtered_activities: number;
  preserve_order?: boolean;
}

/**
 * Complete Gantt chart data streamed from the agent
 */
export interface GanttChartData {
  /** Payload schema version for compatibility handling */
  schema_version?: string;
  /** Optional custom view metadata */
  view?: {
    id?: string | null;
    title?: string;
    grouping?: string | null;
    source?: {
      project_id?: number | null;
      schedule_version_id?: number | null;
      scenario_id?: string | null;
    };
  };
  /** Explicit capability matrix (v2 payload) */
  capabilities?: GanttCapabilities;
  /** Full data envelope independent of display filters (v2 payload) */
  data_envelope?: GanttDataEnvelope;
  /** Display projection for currently visible subset (v2 payload) */
  display?: GanttDisplay;

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
  /** Whether baseline data is available for this schedule version */
  has_baseline?: boolean;

  /** Active baseline comparison mode */
  baseline_mode?: BaselineMode;

  /** Label describing what the baseline represents (e.g. version name) */
  baseline_label?: string | null;

  /** Which baseline modes are available for this project */
  available_baseline_modes?: {
    own: boolean;
    previous_version: boolean;
    database_baseline: boolean;
    what_if?: boolean;
  };

  /** User-reported activity updates for indicator display */
  activity_updates?: ActivityUpdate[];

  /** Update logs from the selected baseline version (cross-version mode only) */
  baseline_activity_updates?: ActivityUpdate[];
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

export type PredefinedScheduleViewKey =
  | 'critical_path'
  | 'total_float_critical'
  | 'near_critical'
  | 'float_path_1'
  | 'lookahead_4w'
  | 'full_schedule'
  | 'updates';
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
