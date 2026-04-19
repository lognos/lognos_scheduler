/**
 * Schedule Assistant Workspace layout types.
 *
 * These types live in a dedicated module so they can be shared between
 * `SAWorkspace`, `SAChatHeader`, and `SAGanttPanel` without circular imports.
 */

export type SAWorkspaceMode =
  | 'gantt-full-chat-floating'
  | 'gantt-main-chat-side'
  | 'chat-main-gantt-side';

/**
 * Internal-only effective mode used when no Gantt data is available yet.
 * Never user-selectable.
 */
export type SAEffectiveMode = SAWorkspaceMode | 'chat-only-virtual';

export type SADockedMode = 'gantt-main-chat-side' | 'chat-main-gantt-side';

export type SAGanttContainerVariant = 'full' | 'dockedRight' | 'dockedLeft';

export type SAShellMode = 'standalone' | 'embedded';

export interface FloatingChatGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SAWorkspaceLayoutState {
  mode: SAWorkspaceMode;
  floatingChat: FloatingChatGeometry;
  ganttSideWidth: number;
  splitRatio: number;
  lastDockedMode: SADockedMode;
}

/**
 * Actions exposed by both headers to mutate the workspace layout.
 * The workspace owns the implementations and passes them down.
 */
export interface SAWorkspaceLayoutActions {
  pinChatRight: () => void;
  unpinChatToFloating: () => void;
  makeGanttFull: () => void;
  makeSplit: () => void;
  swapSides: () => void;
}
