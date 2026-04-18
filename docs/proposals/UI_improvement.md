# Schedule Workspace UI Improvement Proposal (v2)

## Summary

Introduce a flexible Schedule Assistant workspace that lets the user pin or unpin chat and Gantt independently, while preparing the page to be embedded into a host application that already ships a similar chat UI.

The proposal:

- adds three concrete layout modes with a clear default
- moves pin and unpin controls into the existing chat and Gantt headers
- renames only the orchestration components that gain schedule-specific behavior, to avoid name collisions when embedded
- introduces an explicit `embedded` vs `standalone` mode so host-provided shell elements (sidebar, project selector, user context) are not duplicated

This is a focused refactor of `frontend/components/ChatLayout.tsx`, `frontend/components/ChatWithHistory.tsx`, `frontend/components/ChatHeader.tsx`, `frontend/components/gantt/GanttPanel.tsx`, plus their import sites. No new layout framework is introduced.

## Requirements Recap

From the user request:

- Default mode: Gantt pinned full size, chat unpinned and floating.
- Mode 2: Gantt pinned (about 80% width), chat pinned right (about 20%).
- Mode 3: Chat pinned, Gantt pinned right (current layout).
- Pin and unpin icons live in the chat and Gantt headers.
- Reuse and modify existing components; create new components only if strictly needed.
- This page will be embedded into another app that uses similar chat components, so renaming is required to avoid conflicts.
- Some host-app components may be reused (chat header, bubbles, history) and the schedule workspace must not assume local ownership of those primitives forever.

Modes 4 and 5 are intentionally left as future work. The state model must be open-ended enough to add them without rework.

## Current State (verified in code)

- `frontend/app/page.tsx` renders `ChatWithHistory`.
- `frontend/components/ChatWithHistory.tsx` owns AG-UI streaming, conversation history, and renders `ChatLayout`.
- `frontend/components/ChatLayout.tsx` renders the sidebar, the chat header, the messages, the input area, and conditionally the Gantt panel.
- `frontend/components/ChatLayout.tsx` hardcodes `pl-16` to leave room for the standalone `Sidebar`.
- `frontend/components/ChatHeader.tsx` renders the project selector plus history and new-conversation actions.
- `frontend/components/gantt/GanttPanel.tsx` is a `fixed top-20 right-8 bottom-30` floating panel with internal width state and an `X` close action.
- `frontend/components/gantt/index.ts` re-exports `GanttPanel`.
- The current layout is effectively Mode 3 (chat-main, Gantt right-docked).

Embedding implications discovered:

- `Sidebar` and `ProjectSelector` are standalone-only. The host app already provides equivalent navigation and selection.
- `useUser` and the auth provider are also likely host-owned.
- The class `pl-16` and `right-8` style positioning will conflict with a host shell.
- File-level names like `ChatLayout`, `ChatHeader`, `ChatWithHistory` are highly likely to collide with the host app.
- `ConversationHistoryPanel` is also generic enough to collide; it should be namespaced when embedded but does not need to be modified for layout behavior.

## Naming Strategy

To avoid collisions in the host app, the orchestration components are renamed with the `SA` prefix (matching the existing sidebar nav label "SA" for Schedule Assistant). This is a single, consistent prefix across the new workspace shell.

Renames:

- `ChatLayout.tsx` -> `SAWorkspace.tsx`
- `ChatWithHistory.tsx` -> `SAWorkspaceWithHistory.tsx`
- `ChatHeader.tsx` -> `SAChatHeader.tsx`
- `gantt/GanttPanel.tsx` -> `gantt/SAGanttPanel.tsx`

Components left untouched (presentational, low collision risk inside an `sa/` import path):

- `MessageBubble.tsx`
- `ThinkingIndicator.tsx`
- `InputArea.tsx`
- `ConversationHistoryPanel.tsx`

These remain reusable. When embedded, the host app may swap them out via composition (see "Embed Mode" below). The host app's chat bubble and history are expected to be acceptable replacements.

`Sidebar.tsx`, `ProjectSelector.tsx`, `LognosLogo.tsx`, `Portal.tsx`, `ReviewBadge.tsx`, `ConversationSkeleton.tsx`, and `providers/` stay as-is. They are either standalone-only or already neutral.

Import sites that must be updated in the rename pass:

- `frontend/app/page.tsx` (renders `ChatWithHistory`)
- `frontend/components/ChatWithHistory.tsx` (imports `ChatLayout`)
- `frontend/components/ChatLayout.tsx` (imports `ChatHeader`, `GanttPanel`)
- `frontend/components/gantt/index.ts` (re-exports `GanttPanel`)
- Any test or storybook files that import these symbols

The `gantt/index.ts` barrel should re-export the new name (`SAGanttPanel`) and drop the old `GanttPanel` export to prevent dual ownership.

## Embed Mode vs Standalone Mode

A single explicit prop drives host vs standalone behavior, so the workspace stays one component instead of two parallel trees.

```ts
type SAWorkspaceShellMode = 'standalone' | 'embedded';
```

Behavior matrix:

| Concern | standalone | embedded |
|---|---|---|
| Renders `Sidebar` | yes | no |
| Reserves left padding (`pl-16`) | yes | no (host owns layout) |
| Renders `ProjectSelector` in header | yes | optional via prop, default no |
| Owns user context fetching | yes (via `useUser`) | accepts user prop or context override |
| Mounts conversation history panel | yes | optional, can be host-owned |
| Persists layout in localStorage | yes (namespaced key) | yes (namespaced key, separate per host) |
| Z-index of floating chat | local stacking context | bounded to host container |

The mode default is `standalone`. The host opts into `embedded` explicitly when mounting `SAWorkspaceWithHistory`.

Persistence keys must be namespaced to avoid collisions:

- `lognos.sa.workspace.layoutMode`
- `lognos.sa.workspace.floatingChat`
- `lognos.sa.workspace.splitRatio`
- `lognos.sa.workspace.ganttWidth`

In `embedded` mode the host can pass a `persistenceNamespace` prop so multiple embeddings do not stomp on each other.

## Layout Modes

Three modes ship in the first iteration. Modes 4 and 5 are reserved.

### Mode A — `gantt-full-chat-floating` (default)

- Gantt fills the available workspace area inside the schedule shell.
- Chat is rendered as a floating, draggable panel above the Gantt.
- The chat header shows a "pin chat right" action.
- The Gantt header does not show a "close" action in this mode (closing the Gantt would empty the workspace). Instead the Gantt header shows pin-mode actions.

### Mode B — `gantt-main-chat-side`

- Gantt occupies roughly 80% of the content width, chat occupies roughly 20% on the right.
- The split is resizable via the divider.
- Chat header shows "unpin to floating" and "swap sides" actions.
- Gantt header shows "make full" and "swap sides" actions.

### Mode C — `chat-main-gantt-side`

- Chat occupies the main area on the left, Gantt is pinned right.
- This matches the current visible layout and existing Gantt resize logic.
- Chat header shows "unpin to floating" and "swap sides" actions.
- Gantt header shows "make full" and "swap sides" actions.

### Empty schedule fallback

When no Gantt data is available, the effective mode falls back to a chat-only render regardless of the stored layout mode. The stored mode is preserved and re-applied as soon as Gantt data arrives. This avoids ever rendering a "Gantt full" canvas with no Gantt.

```ts
const effectiveMode: SAWorkspaceMode =
  ganttPanel?.data ? layoutMode : 'chat-only-virtual';
```

`chat-only-virtual` is internal and is not user-selectable.

## Header Interaction Model

Pin and unpin lives in the chat and Gantt headers. The control set is concrete, not loose, and reuses lucide icons already used in the project (`lucide-react`).

Suggested icons:

- `Pin` and `PinOff` for chat pin/unpin
- `Maximize2` for "make Gantt full"
- `Columns2` for split mode (Mode B)
- `PanelRight` / `PanelLeft` for swap sides
- Existing `X` only for actions that truly close the panel; in embed mode the X may be hidden because the host owns visibility

### Chat header (`SAChatHeader`)

Visible actions, depending on `layoutMode`:

- Mode A: `Pin` (pin chat right -> Mode B)
- Mode B: `PinOff` (unpin to floating -> Mode A), `PanelLeft` (swap to Mode C)
- Mode C: `PinOff` (unpin to floating -> Mode A), `PanelRight` (swap to Mode B)

History and new-conversation actions remain unchanged.

In `embedded` mode the project selector is hidden by default and the host is expected to provide the equivalent.

### Gantt header (`SAGanttPanel`)

Visible actions, depending on `layoutMode`:

- Mode A: `Columns2` (switch to split -> Mode B)
- Mode B: `Maximize2` (make Gantt full -> Mode A), `PanelLeft` (swap to Mode C)
- Mode C: `Maximize2` (make Gantt full -> Mode A), `PanelRight` (swap to Mode B)

The legacy `X` close action moves to a single behavior: hide the Gantt entirely. It is only shown when a meaningful empty state exists for the workspace (chat-only). In Mode A it is hidden because closing would leave an empty canvas.

All controls reuse the same pill-style button look already used inside the Gantt header (`px-2.5 py-1 rounded-full border ...`), to avoid introducing a second visual language.

## State Model

Single explicit mode value. No combinations of independent booleans.

```ts
export type SAWorkspaceMode =
  | 'gantt-full-chat-floating'
  | 'gantt-main-chat-side'
  | 'chat-main-gantt-side';

export interface FloatingChatGeometry {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SAWorkspaceLayoutState {
  mode: SAWorkspaceMode;
  floatingChat: FloatingChatGeometry;
  ganttSideWidth: number;     // used in Mode B and Mode C
  splitRatio: number;         // used in Mode B; chat-side fraction
  lastDockedMode: 'gantt-main-chat-side' | 'chat-main-gantt-side';
}
```

`lastDockedMode` lets the chat unpin (-> Mode A) and re-pin to the user's last docked layout.

State lives in `SAWorkspace` (formerly `ChatLayout`). It is hydrated from localStorage on mount when persistence is enabled, with safe fallbacks if no entry exists or the stored shape is invalid.

## File-by-file Plan

### `ChatLayout.tsx` -> `SAWorkspace.tsx`

Responsibilities:

- own `SAWorkspaceLayoutState`
- compute `effectiveMode`
- render `Sidebar` only when `shellMode === 'standalone'`
- conditionally apply the `pl-16` sidebar offset only in `standalone`
- render chat as a floating panel or as a docked column depending on `effectiveMode`
- render the Gantt panel in `full`, `dockedRight`, or `dockedLeft` container variant depending on `effectiveMode`
- pass header actions to `SAChatHeader` and `SAGanttPanel`

The current `ganttWidth` state is renamed to `ganttSideWidth` and reused for both Mode B and Mode C. The current `handleGanttWidthChange` clamping logic stays.

The current double-render of `InputArea` (welcome state vs footer) is preserved inside the floating chat shell as well.

### `ChatWithHistory.tsx` -> `SAWorkspaceWithHistory.tsx`

Stays the orchestrator for AG-UI streaming and history. Renamed only.

Adds two optional props for embed scenarios:

- `shellMode?: 'standalone' | 'embedded'` (default `'standalone'`)
- `persistenceNamespace?: string` (default `'lognos.sa.workspace'`)

The hardcoded `http://localhost:8500` URL is acknowledged as embed-incompatible but is out of scope here. A follow-up note: replace it with a configurable base URL when wiring the embed integration.

### `ChatHeader.tsx` -> `SAChatHeader.tsx`

Adds props:

- `layoutMode: SAWorkspaceMode`
- `onPinChatRight: () => void`
- `onUnpinChatToFloating: () => void`
- `onSwapSides: () => void`
- `showProjectSelector?: boolean` (default `true`)

Existing `onHistoryToggle` and `onNewConversation` are preserved.

The project selector is rendered only when `showProjectSelector` is true. In `embedded` mode the workspace passes `showProjectSelector={false}` by default.

### `gantt/GanttPanel.tsx` -> `gantt/SAGanttPanel.tsx`

Adds a container variant prop:

```ts
type SAGanttContainerVariant = 'full' | 'dockedRight' | 'dockedLeft';
```

Container behavior:

- `full`: fills its parent, no `fixed` positioning, no rounded outer shell, no own width prop required
- `dockedRight`: keeps the current `fixed top-20 right-8 bottom-30` shell and `width` resize handle
- `dockedLeft`: same as `dockedRight`, mirrored

Adds props:

- `layoutMode: SAWorkspaceMode`
- `onMakeFull: () => void`
- `onMakeSplit: () => void`
- `onSwapSides: () => void`

Internal behavior preserved:

- `useTimeline`, `useBarPositions`, `RelationshipArrows`
- column resize, sticky summaries, virtualization
- the `data-gantt-panel-root` and `data-gantt-printable` attributes used by `services/printService.ts` are preserved exactly so print continues to work
- baseline mode, view selector, and update toggles stay where they are

The legacy `onClose` prop is preserved but only wired to a visible `X` when `effectiveMode !== 'gantt-full-chat-floating'`. In Mode A the close action is hidden.

## Floating Chat Shell

The floating chat is a JSX section inside `SAWorkspace`, not a new component, on first pass. If the JSX exceeds roughly 80 lines or starts duplicating logic, extract it into `frontend/components/SAFloatingChat.tsx` in a follow-up. This is the only "create only if strictly needed" candidate.

Behavior:

- positioned `absolute` inside the workspace container, not `fixed`, so it stays bounded inside the embedded host
- drag from a header strip; reuses the same pointer-event pattern already used for Gantt resize in `SAGanttPanel`
- min and max size clamped to the workspace bounds
- initial position derived from the workspace size (e.g. top-right corner with margin)
- no external drag library

The floating chat reuses the same `MessageBubble`, `ThinkingIndicator`, and `InputArea` components, so message rendering stays identical to the docked modes.

## Gantt Container CSS Strategy

Concrete plan instead of "make it conditional":

- `full`: outer wrapper is `relative w-full h-full` inside `SAWorkspace`'s flex layout; remove `fixed`, `top-20`, `right-8`, `bottom-30`, and the `width` prop usage in this variant
- `dockedRight`: keep current `fixed top-20 right-8 bottom-30` and current `width` resize handle (preserves current visual exactly for Mode C)
- `dockedLeft`: same as `dockedRight` with `right-8` swapped for `left-8` and the resize handle on the right edge of the panel

The print path is unaffected because `data-gantt-panel-root` and the print stylesheet selectors remain on the same outer div.

## Persistence

LocalStorage with namespaced keys, hydrated on mount, written on change. Hydration is wrapped in a guard that:

- ignores invalid JSON
- ignores stored modes that are not in the current `SAWorkspaceMode` union
- clamps stored geometry to current viewport bounds

In embed mode, the namespace prefix is taken from `persistenceNamespace`.

## Embedded Integration Contract

When the host app embeds this workspace, the integration shape is:

```tsx
<SAWorkspaceWithHistory
  shellMode="embedded"
  persistenceNamespace="hostapp.sa"
  // optional overrides; otherwise uses local defaults
  // userOverride={hostUser}
/>
```

Inside `embedded` mode:

- no `Sidebar`
- no `pl-16`
- no `ProjectSelector` (host owns project context)
- floating chat is bounded by the host container
- Gantt panel switches `dockedRight` / `dockedLeft` from `fixed` to `absolute` so it stays inside the host pane (small adjustment to the variant CSS noted above; both variants must use `absolute` positioning when `shellMode === 'embedded'`)

Out of scope but flagged:

- Host-provided `MessageBubble` / `ConversationHistoryPanel` swap. To enable a full swap later, `SAWorkspace` would accept render-prop-style overrides, e.g. `renderMessage`, `renderHistory`. This is not implemented in v2 to keep the rename minimal, but the proposal notes it as the natural follow-up if the host insists on its own bubbles.

## Phased Implementation Plan

### Phase 1 — Mechanical rename (no behavior change)

- Rename the four orchestration files and update all import sites.
- Update `gantt/index.ts` barrel export.
- Verify the app still renders identically (still Mode C-equivalent visually).
- Ship.

Risk: low. This is a refactor and should pass typecheck cleanly.

### Phase 2 — Embed mode and headers wiring

- Add `shellMode`, `persistenceNamespace`, and `showProjectSelector` props.
- Wire conditional `Sidebar`, `pl-16`, and `ProjectSelector`.
- Add the layout mode union and stub state in `SAWorkspace`.
- Add the new header action props (still no-ops if not yet wired).

Risk: low. Standalone behavior is preserved by defaults.

### Phase 3 — Mode A (default Gantt-full + floating chat)

- Add `full` container variant in `SAGanttPanel`.
- Add the floating chat JSX inside `SAWorkspace`.
- Add drag and clamp logic (reusing the Gantt resize pattern).
- Add chat header `Pin` action and Gantt header `Columns2` action.
- Hide the Gantt `X` close action in Mode A.
- Make Mode A the default for new sessions when Gantt data is present.

Risk: medium. Drag and z-index behavior need testing with the conversation history panel and any modal dialogs.

### Phase 4 — Modes B and C with swap

- Add `dockedLeft` container variant in `SAGanttPanel` (mirror of `dockedRight`).
- Add resizable split divider for Mode B.
- Add the swap-sides action in both headers.
- Persist `lastDockedMode` for unpin restore.

Risk: medium. The split divider is the most novel piece; it should reuse the Gantt resize pointer pattern.

### Phase 5 — Persistence and polish

- Namespaced localStorage hydration and writes.
- Bounds clamping on viewport resize.
- Optional `renderMessage` / `renderHistory` slots if the host integration requires it.

Risk: low.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Rename misses an import site and breaks the build | Single grep sweep before commit; the project compiles in CI |
| Embedding still leaks standalone styling | `shellMode` gate and removal of `fixed` positioning in embed |
| Gantt print behavior changes | Preserve `data-gantt-panel-root` and `data-gantt-printable` exactly; print service untouched |
| Floating chat overlaps `ConversationHistoryPanel` | Workspace owns z-index ordering; history panel stays on top |
| Mode A with no Gantt data is empty | `effectiveMode` fallback to chat-only when `ganttPanel.data` is null |
| Persistence collides with host app keys | Namespaced keys, host can override prefix |
| Two visual languages for header controls | Reuse the existing pill-button style from `SAGanttPanel` for all new actions |
| GanttPanel `onClose` ambiguity | Hidden in Mode A; only shown when chat-only state is meaningful |

## Out of Scope (explicit)

- Backend changes
- AG-UI protocol changes
- Replacing `useUser` or auth provider for embedded mode
- Replacing the hardcoded `http://localhost:8500` URL in `ChatWithHistory.tsx` (flagged for follow-up)
- Modes 4 and 5
- Mobile-specific layouts (the new modes target desktop; mobile falls back to chat-only)

## Deliverables

- Renamed components: `SAWorkspace.tsx`, `SAWorkspaceWithHistory.tsx`, `SAChatHeader.tsx`, `SAGanttPanel.tsx`
- Updated imports in `frontend/app/page.tsx` and `frontend/components/gantt/index.ts`
- New `SAWorkspaceLayoutState` and `SAWorkspaceMode` types (colocated in `SAWorkspace.tsx` initially; promote to `frontend/types/` if reused)
- New `SAGanttContainerVariant` plumbing in `SAGanttPanel.tsx`
- Pin / unpin / swap / make-full controls in both headers, using the existing pill-button style
- Floating chat shell inside `SAWorkspace`
- Namespaced localStorage persistence
- `shellMode` and `persistenceNamespace` props on `SAWorkspaceWithHistory`
# Schedule Workspace UI Improvement Proposal

## Summary

This proposal introduces a scheduling-specific workspace layout that supports pin and unpin behavior between chat and Gantt, while also preparing the page to be embedded into another application that already contains similar chat components.

The design goal is to keep generic chat primitives reusable, but move the new schedule-aware layout behavior into renamed, schedule-scoped components so the embedded integration does not create naming collisions or two competing ownership models.

## Goals

- Support multiple layout modes without creating a separate UI stack.
- Keep the Gantt and chat headers as the places where pin and unpin actions live.
- Reuse existing components where possible and create new ones only when strictly necessary.
- Avoid naming conflicts when this page is embedded into another application that already has its own chat shell.
- Preserve the current scheduling behavior, AG-UI message flow, Gantt interactions, and history integration.

## Current Constraints

The current implementation is centered around these components:

- `frontend/components/ChatLayout.tsx`
- `frontend/components/ChatWithHistory.tsx`
- `frontend/components/ChatHeader.tsx`
- `frontend/components/gantt/GanttPanel.tsx`

Today, the layout relationship is effectively fixed:

- Chat owns the main area.
- Gantt renders as a floating right panel.
- Gantt width is resizable.
- Chat has no equivalent pin, unpin, or floating state.

This is workable for the current app, but it becomes too rigid for the requested layout flexibility and too generic for an embedded scenario where another app already owns similarly named chat components.

## Proposed Architecture

### 1. Separate shared chat primitives from schedule-specific workspace orchestration

The proposal does not introduce a new generic chat framework. Instead, it draws a clear boundary:

- Shared chat primitives remain simple and swappable.
- Schedule workspace orchestration becomes an explicit scheduling concern.

Shared or reusable pieces include:

- message bubbles
- conversation history panel
- input area
- generic chat actions where appropriate

Schedule-specific pieces include:

- layout mode selection
- chat and Gantt pin and unpin behavior
- floating chat behavior
- split-pane widths and docking rules
- scheduling-specific header actions and shell composition

This makes it practical to embed the schedule page in the other app while reusing some of that app's existing chat UI without forcing the schedule workspace to inherit the other app's layout assumptions.

### 2. Rename the scheduling-specific components

The components that should be renamed are the ones that will diverge from generic chat behavior.

Recommended renames:

- `ChatLayout.tsx` -> `ScheduleWorkspace.tsx`
- `ChatWithHistory.tsx` -> `ScheduleWorkspaceWithHistory.tsx`
- `ChatHeader.tsx` -> `ScheduleChatHeader.tsx`
- `gantt/GanttPanel.tsx` -> `gantt/ScheduleGanttPanel.tsx`

These names make the ownership explicit:

- the workspace is schedule-specific
- the header is no longer a generic chat header
- the Gantt panel is the schedule workspace variant, not a universally reusable Gantt shell

Components that can remain generic unless later requirements force a split:

- `MessageBubble.tsx`
- `ThinkingIndicator.tsx`
- `InputArea.tsx`
- `ConversationHistoryPanel.tsx`

This keeps the rename scope intentionally narrow.

### 3. Centralize layout state in the schedule workspace container

The renamed workspace container should remain the source of truth for layout state.

That container should own:

- active layout mode
- Gantt docked width
- split ratio for docked dual-pane modes
- floating chat size
- floating chat position
- the last docked layout mode for restoring state after unpin

This state should not live in the shared chat pieces, because those pieces should remain reusable and unaware of schedule workspace composition.

## Layout Modes

The first implementation should support three real modes and leave room for future presets.

### Mode 1: Gantt pinned full, chat floating

Default mode.

Behavior:

- Gantt occupies the full available content area.
- Chat appears as a floating panel above the Gantt.
- The user can move the chat panel.
- The chat header exposes an action to pin chat to the right.
- The Gantt header exposes an action to switch to split mode if needed later.

This mode best matches the requested default and makes the Gantt the primary visual workspace.

### Mode 2: Gantt pinned left, chat pinned right

Behavior:

- Gantt uses roughly 80% of the content width.
- Chat is pinned on the right using roughly 20%.
- The split should be resizable after initialization.
- Chat and Gantt remain visible at the same time.

This is the most balanced dual-pane workspace when the user wants both views visible without overlap.

### Mode 3: Chat pinned left, Gantt pinned right

Behavior:

- Chat remains the primary panel.
- Gantt stays pinned on the right.
- This is the closest to the current layout.

This mode preserves the familiar interaction model and reduces rollout risk.

### Future Modes

The internal layout model should be extensible so modes 4 and 5 can be added without rewriting layout state.

No visible placeholders are needed yet. The code should support extension, but the UI should only expose modes that actually exist.

## Header Interaction Model

The key interaction rule is that pin and unpin controls live in the relevant headers.

### Schedule chat header

The schedule chat header should expose layout actions in addition to the existing history and new conversation actions.

Expected actions:

- pin chat right
- unpin chat to floating mode
- optionally switch to chat-primary mode if not already active

The exact visible icon set depends on the current mode.

Examples:

- In floating mode, show a pin action.
- In docked-right mode, show an unpin action.
- In chat-primary mode, show the alternative pin target if useful.

### Schedule Gantt header

The Gantt header should expose layout actions next to the existing close action.

Expected actions:

- pin Gantt full
- pin Gantt right
- optionally switch to split mode

The close action should keep its current meaning of hiding the Gantt entirely. Pin and unpin actions control layout, not visibility.

## Component Reuse Strategy

### Keep and reuse

These pieces should remain largely reusable as-is:

- `frontend/components/MessageBubble.tsx`
- `frontend/components/ThinkingIndicator.tsx`
- `frontend/components/InputArea.tsx`
- `frontend/components/ConversationHistoryPanel.tsx`

These are mostly presentational or narrowly scoped and do not need schedule ownership.

### Rename and adapt

These should become schedule-scoped:

- `frontend/components/ChatLayout.tsx`
- `frontend/components/ChatWithHistory.tsx`
- `frontend/components/ChatHeader.tsx`
- `frontend/components/gantt/GanttPanel.tsx`

These files currently own composition or are about to gain schedule-specific behavior.

### Create new components only if strictly needed

The preferred first pass is to avoid introducing a large set of new files.

Recommended approach:

- Rename the existing orchestration components.
- Keep rendering logic in the renamed workspace container.
- Extract a dedicated floating chat shell only if the JSX becomes too hard to maintain.

That means the first implementation should try to avoid creating separate components such as `FloatingChatPanel`, `DockedChatPanel`, or `WorkspaceLayoutManager` unless the refactor proves they are necessary.

## Detailed File-Level Proposal

### `frontend/components/ChatLayout.tsx` -> `frontend/components/ScheduleWorkspace.tsx`

This becomes the primary owner of the new architecture.

Responsibilities:

- own layout mode state
- own docked and floating geometry state
- render chat in docked or floating form depending on mode
- render the Gantt panel in full, right-docked, or split form depending on mode
- pass pin and unpin actions into both headers

This is the correct place for the orchestration because it already composes the chat region and the Gantt region.

### `frontend/components/ChatWithHistory.tsx` -> `frontend/components/ScheduleWorkspaceWithHistory.tsx`

This wrapper should keep handling conversation history and AG-UI integration.

Responsibilities remain mostly the same:

- load conversations
- toggle history panel
- pass schedule and conversation props into the workspace

The rename is mostly about namespacing and embedded clarity.

### `frontend/components/ChatHeader.tsx` -> `frontend/components/ScheduleChatHeader.tsx`

This should stay a focused header, but it will gain schedule workspace actions.

Suggested new props:

- current layout mode
- callbacks for chat pin and unpin actions
- optional flags for whether Gantt is visible

The project selector can remain in this header if that continues to match the schedule workspace UX.

### `frontend/components/gantt/GanttPanel.tsx` -> `frontend/components/gantt/ScheduleGanttPanel.tsx`

This should remain the interactive schedule chart shell, but its root container should no longer assume only one rendering mode.

Suggested additions:

- root container mode: full, docked-right, or floating-ready
- layout action callbacks
- header actions for pin and unpin

Important implementation detail:

The current resize logic for the panel width should be preserved and reused for the docked-right case rather than rewritten.

## State Model

The workspace should use a single explicit layout mode rather than several loosely related booleans.

Suggested model:

```ts
type ScheduleWorkspaceMode =
  | 'gantt-full-chat-floating'
  | 'gantt-main-chat-side'
  | 'chat-main-gantt-side';

interface FloatingChatState {
  x: number;
  y: number;
  width: number;
  height: number;
}
```

Additional local state:

- `ganttWidth`
- `chatSideWidth`
- `floatingChatState`
- `lastDockedMode`

This approach scales better than tracking combinations like `isChatFloating`, `isGanttPinned`, and `isSplitLayout` independently.

## Interaction and Behavior Details

### Floating chat movement

Use the same low-level pointer handling pattern already used for Gantt panel resizing.

Recommended behavior:

- dragging starts from the chat header
- movement is bounded to the visible workspace area
- no external drag library is introduced

This keeps the implementation consistent with current interaction code and avoids unnecessary dependencies.

### Gantt sizing

Preserve the existing Gantt width resize behavior for the right-docked mode.

For the full-Gantt mode:

- the panel should stop behaving like a fixed floating overlay
- it should instead fill the available workspace area inside the schedule shell

### Chat sizing in docked mode

For the split mode, initialize chat at roughly 20% width, but keep the split adjustable.

This should be treated as a workspace split concern, not as an internal chat component concern.

### History panel compatibility

The conversation history behavior can remain unchanged.

The history panel should continue to be owned by the wrapper around the workspace, since it is orthogonal to Gantt layout mode.

## Embedded App Compatibility

This proposal specifically prepares the schedule page for embedding into another app with a similar chat UI.

### Why renaming matters

If the page is embedded into an app that already has components named `ChatLayout`, `ChatHeader`, or similar generic names, the schedule implementation becomes hard to reason about and easy to import incorrectly.

Renaming the schedule-specific shells solves this in two ways:

- it avoids import collisions and ambiguous ownership
- it makes it clear which components are reusable chat primitives and which are schedule workspace infrastructure

### Swappable primitives strategy

The embedded integration should be able to reuse the host app's generic chat components where that is beneficial.

That means the schedule workspace should depend on simple interfaces and composition rather than assume that all chat pieces are owned locally forever.

Practical interpretation:

- keep bubbles and history generic if possible
- keep workspace orchestration schedule-specific
- avoid tying generic primitives to Gantt logic

## Phased Implementation Plan

### Phase 1: Namespacing and low-risk layout foundation

- rename the schedule-specific container and header files
- update imports throughout the frontend
- introduce the new layout mode type in the renamed workspace component
- preserve the current visible behavior while the rename lands cleanly

Outcome:

- embedding-safe naming
- no behavior regression yet

### Phase 2: Default Gantt-full plus floating chat

- render Gantt as the primary workspace canvas
- render chat as a floating panel
- add drag behavior to the floating chat shell
- add header pin and unpin controls

Outcome:

- requested default experience becomes real

### Phase 3: Docked split modes

- add Gantt-left plus chat-right split mode
- keep chat-left plus Gantt-right mode as a supported preset
- make widths adjustable

Outcome:

- all three requested layout modes are supported

### Phase 4: Persistence and polish

- persist last selected layout mode locally
- persist floating chat position if it remains within bounds
- refine mobile and narrow-width fallbacks

Outcome:

- improved usability across sessions

## Risks and Mitigations

### Risk: workspace JSX becomes too complex

Mitigation:

- keep the first implementation in the renamed workspace container
- extract a small shell component only if readability actually degrades

### Risk: floating chat interferes with existing overlays

Mitigation:

- keep z-index ownership inside the workspace container
- test with the conversation history panel open

### Risk: Gantt print behavior is affected by layout changes

Mitigation:

- keep the Gantt printable root and print service contract unchanged
- only change outer container behavior in a controlled way

### Risk: embedding into the host app still causes conceptual overlap

Mitigation:

- keep schedule-specific names for all orchestration components
- keep shared chat primitives generic and replaceable

## Recommendation

Proceed with a schedule-scoped workspace refactor, not a generic chat rewrite.

The most pragmatic implementation is:

- rename the orchestration components to schedule-specific names
- keep layout state in the renamed workspace container
- add pin and unpin controls to the existing chat and Gantt headers
- reuse the current Gantt panel internals and resize logic
- keep generic chat primitives reusable and minimally modified

This meets the requested UX goals, avoids unnecessary new components, and prepares the page for embedding into another app without creating naming or ownership conflicts.

## Proposed Deliverables

- renamed schedule-specific workspace components
- explicit workspace layout mode model
- header pin and unpin controls for chat and Gantt
- default Gantt-full plus floating chat mode
- split docked modes for dual-pane use
- embedded-safe naming and reuse boundaries