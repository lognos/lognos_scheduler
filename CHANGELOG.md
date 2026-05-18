# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Added optional Duration display in the Gantt column selector.
- Added dependency tooltip activity navigation and draggable timeline scale adjustment in the Gantt panel.
- Added double-click on the Gantt timeline header to reset the timeline scale so the project fits the available viewport width.
- Added two months of leading and trailing padding to the Gantt timeline so months continue beyond the project window without overflowing the viewport.
- Added a resizable floating chat overlay for the Schedule Assistant workspace.
- Added schedule view modes for longest-path critical path, total-float critical, near-critical, and Float Path 1 analysis.
- Added config-aware schedule view snapshot invalidation so cached views rebuild when critical-path semantics change.
- Added MS activity semantic search backed by Supabase schedule activity embeddings and a prepared RPC migration.

### Changed

- Simplified the Schedule Assistant workspace so the Gantt fills the canvas while chat remains floating above it.
- Changed the Gantt table to auto-size its initial columns from schedule content instead of fixed percentages.
- Changed the system Critical Path view to use longest-path semantics instead of only filtering activities with total float less than or equal to zero.
- Changed the Gantt activity columns to stay frozen at the left while only the timeline section scrolls horizontally when the timeline extends beyond the viewport.
- Changed the stacking order so the frozen Gantt columns paint above relationship arrows during horizontal scroll instead of being covered by them.
- Changed the Gantt relationship arrows overlay to clip its SVG to the timeline area so arrow paths can no longer bleed leftward into the frozen activity columns when scrolled.
- Changed the Gantt relationship arrows overlay to dynamically clip its leftmost region equal to the current horizontal scroll offset so arrows can never paint behind the sticky activity columns once the body has been scrolled right.
- Changed the backend runtime to a Lognos Scheduling Agent MS/workspace-only service while preserving workspace CPM, Gantt visualization, what-if, and email/team context behavior.
- Changed scheduling agent construction to support the project's Pydantic AI dependency range and report optional Logfire instrumentation incompatibility without blocking app startup.
- Pinned `pydantic-ai` to the version verified with the scheduling agent constructor and usage-limit APIs.

### Removed

- Removed Primavera P6 SQLite runtime paths, P6 API routes, P6 agent/tools, P6 repositories/services, and old P6 docs/scripts/data from the production cleanup branch.

### Fixed

- Fixed Gantt relationship arrows incorrectly overlapping milestone diamonds and showing inconsistent leading gaps by computing milestone endpoint bounds from the diamond's visual half-width instead of the clamped widthPercentage, so arrows now leave and enter milestones with the same 6 px gap used for regular activity bars.
- Fixed the Gantt timeline drag-to-scale running away past the viewport and snapping back when shrunk by measuring the viewport from the scroll container instead of the printable wrapper, preventing a width feedback loop with the scaled canvas.
- Fixed the Gantt timeline drag scaling so it stays anchored at the cursor (zoom-to-cursor) and reduced drag sensitivity so small drags produce small scale changes instead of pushing content off-screen.
- Fixed the Gantt timeline drag that kept scaling after the user released the mouse by mounting the global mousemove/mouseup listeners once and routing the latest layout values through a ref instead of recreating the listeners on every render.
- Fixed the Schedule Assistant workspace flex chain so the Gantt panel cannot grow past the viewport when the timeline is scaled, by adding `min-w-0` to the workspace mode wrappers; the body now correctly shows a horizontal scrollbar and the header stays clipped to the panel width.
- Hardened Gantt drag release by also listening on pointerup/pointercancel/blur in the capture phase so the timeline scale and column resizes always stop when the cursor is released, even if the release lands outside the window or is consumed by a child element.
