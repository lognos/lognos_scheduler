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