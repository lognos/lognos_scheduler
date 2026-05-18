# Cleanup Proposal: MS-Only Scheduling App

Date: 2026-05-18
Branch: cleanup/ms-only-production-prep

## Current Request

Create a branch that prepares this repository for a production-ready, MS-only scheduling application by removing backend code related to Primavera P6 database interactions, P6 tools, and related runtime paths. Preserve the scheduling work, workspace editing/visualization behavior, Supabase-backed MS Project schedule support, email/team context work, and the frontend.

This document started as a proposal and now also records the implemented cleanup state on this branch.

## My Interpretation

The target app should become an MS Project and workspace scheduling assistant, not a dual P6/MSP assistant. In practice, that means the backend should stop importing, configuring, constructing, exposing, or executing P6-specific database code. The MS scheduling path should remain first-class and production-oriented.

I interpret "workspace/ms only" as:

- Keep the in-memory workspace tools and schedule state used for editing, Gantt payloads, what-if comparisons, and frontend streaming events.
- Keep MS Project tools that read/write Supabase schedule data in the `lognos_schedule` schema.
- Keep frontend schedule visualization and chat behavior, with the chat request continuing to use `project_type: "msp"` or eventually dropping `project_type` entirely.
- Remove P6 as a selectable or reachable runtime mode.
- Remove P6 SQLite/database transaction assumptions from normal chat execution.

## Supabase MS Schema Review

I used the Supabase MCP project `kxwradnyjqobvdheklsn` to inspect schema `lognos_schedule`. The MS-side data model to preserve includes:

- Schedule versions: `schedule_versions`
- Schedule activities: `schedule_activities`
- Schedule relationships: `schedule_links`
- Calendars and exceptions: `project_calendars`, `calendar_exceptions`
- Project constraints and constraint reference data: `project_constraints`, `constraint_types`
- Schedule update flow: `queued_activity_updates`, `schedule_update_logs`
- Schedule view cache: `schedule_view_definitions`, `schedule_view_snapshots`
- Classification/reference tables: `schedule_classification_rules`, `project_phases`, `feature_flags`, `schedule_cp`

The code already has a focused MS repository surface around this schema in `backend/repositories/ms_schedule_repository.py`, plus view caching in `backend/repositories/schedule_view_repository.py` and `backend/services/schedule_view_service.py`.

## What Should Be Preserved

Backend areas to preserve:

- `backend/tools/ms/` MS schedule query, load, subversion, and promotion tools.
- `backend/repositories/ms_schedule_repository.py` for `lognos_schedule` access.
- `backend/repositories/schedule_view_repository.py` and `backend/services/schedule_view_service.py`.
- `backend/services/schedule_state.py`, `backend/services/gantt_payload_builder.py`, `backend/services/network_calculator.py`, and workspace mutation/query tools under `backend/tools/workspace/`.
- Network calculation and CPM/critical-path capabilities are key production features for MS/workspace schedules and must be preserved. P6-specific naming/comments inside this area should be renamed, not removed, when the underlying logic is generic schedule network logic.
- Semantic activity search should be preserved by replacing the P6 SQLite vector service with an MS/Supabase implementation against `lognos_schedule.schedule_activities.embedding`.
- `backend/api/routers/chat.py`, after simplifying it to MS-only dependencies and removing P6 branching.
- Conversation, project, user context, email tools, Supabase client, Logfire instrumentation, and health endpoints.
- `backend/prompt/scheduler_general.xml.j2` and `backend/prompt/scheduler_msp.xml.j2` as the active agent prompt stack.
- The frontend app, especially the Gantt view and chat stream, with only label/comment/API cleanup where P6 assumptions leak through.

Frontend areas to preserve:

- Chat streaming to `/api/v1/chat`.
- Schedule view fetching from `/api/v1/schedule-views`.
- Gantt rendering, relationship drawing, hierarchy preservation, update/baseline rendering, and schedule controls.
- Existing project selection and `Lognos-ProjectID` header behavior.

## What I Propose To Remove

Backend P6 runtime code:

- P6 SQLite configuration in `backend/config/settings.py`, especially `P6_DB_LOC` and P6 app naming.
- SQLite helpers and safe P6 file transaction code in `backend/utils/db.py` and `backend/utils/safe_db.py`.
- P6 repositories: `backend/repositories/p6_repository.py` and `backend/repositories/p6_schedule_repository.py`.
- P6 route: `backend/api/routers/p6_schedules.py`, plus its registration in `backend/api/main.py` and router exports.
- P6 tools: `backend/tools/p6/`, `backend/tools/p6_tools.py`, and P6 re-exports from `backend/tools/__init__.py`.
- P6 indexing/vector code: `backend/tools/indexing/operations.py` and `backend/services/vector_service.py`, after adding the MS/Supabase semantic search replacement.
- P6-only business service: `backend/services/scheduling_service.py`, unless any workspace code still depends on a neutral subset after inspection.
- P6 agent variant in `backend/agents/scheduling_agent.py`: P6 imports, `P6_TOOLS`, `_P6_SYSTEM_PROMPT`, `_p6_scheduling_agent`, and `get_scheduling_agent(project_type="p6")` branching.
- P6 prompt files and legacy prompt text: `backend/prompt/scheduler_p6.xml.j2` and P6 references in `backend/prompt/scheduler_system.xml.j2` if the file is no longer used.
- P6 domain and IO models that are not used by MS/workspace features.

Chat/API simplification:

- Remove `p6_schedule_id` from active chat request handling and conversation creation metadata. Old conversations can be deleted later.
- Keep the `project_type` field for compatibility, but make the backend MS-only. Treat missing/`msp` values as MS scheduling and reject or ignore P6 values with a clear compatibility message.
- Remove `P6ScheduleRepository`, P6 `SchedulingService`, old P6 `VectorService`, and `SafeP6Transaction` construction from both streaming and sync chat paths.
- If transaction terminology is still useful after cleanup, refactor the retained helper/name to `SafeScheduleTransaction`. It must be MS/workspace-neutral and must not keep P6 SQLite file-copy semantics unless a generic schedule workflow truly needs that behavior.
- Make `AgentDeps` MS/workspace-neutral. Remove P6-required fields or make them optional only where a remaining MS/workspace tool still needs them.

Docs/scripts cleanup candidates:

- P6-only root docs such as `scheduling_tools.md`, `lessons_learned.md`, `project_tool.md`, and old P6 investigation notes should be deleted.
- Root verification scripts such as `check_embeddings.py`, `verify_assignment.py`, and `verify_creation.py` appear P6/SQLite-specific and should be removed from a production MS-only branch.
- `preliminary/` contains P6 schema exploration scripts and should be reviewed as non-production artifact cleanup.

## Proposed Implementation Sequence

1. Establish a safety baseline.
   - Run backend tests and frontend checks before deleting anything.
   - Record current failures separately from cleanup failures.

2. Remove reachable P6 API surface.
   - Unregister `/api/v1/p6-schedules`.
   - Remove P6 schedule models and repository imports from router registration.
   - Keep `/api/v1/chat`, `/api/v1/projects`, `/api/v1/conversations`, `/api/v1/schedule-views`, and `/api/v1/health`.

3. Convert agent construction to MS-only.
   - Build one scheduling agent using `scheduler_general.xml.j2` and `scheduler_msp.xml.j2`.
   - Keep MS tools, workspace tools, context tools, and enabled email tools.
   - Remove P6 tools and P6 prompt loading.

4. Simplify chat dependencies.
   - Stop creating P6 transactions for MSP chat runs.
   - Pass `MSScheduleRepository`, Supabase client, conversation ID, user context, email service, and the Gantt event queue.
   - Remove P6 project resolution and P6-specific SSE reasoning messages.
   - Keep `project_type` in the request model for compatibility, while removing P6 routing behavior.

5. Add the MS semantic search replacement.
   - Add an MS/Supabase semantic search repository method over `lognos_schedule.schedule_activities.embedding`.
   - Add an agent tool such as `search_activities_ms` for fuzzy natural-language activity lookup.
   - Preserve or add embedding generation during MS schedule ingestion/upload so activity rows have useful vectors.
   - Use exact MS tools for deterministic filters and semantic search for ambiguous activity discovery.

6. Make transaction and dependency naming neutral.
   - Refactor `SafeP6Transaction` references away from chat execution.
   - Rename any retained generic transaction helper to `SafeScheduleTransaction`.
   - Make `AgentDeps` independent from P6 services, P6 repositories, P6 SQLite connections, and P6 transaction objects.

7. Delete P6 backend modules after imports are clean.
   - Delete P6 repositories, P6 tools, P6 SQLite utils, P6 vector/indexing service, and P6-only service code.
   - Remove P6 request/domain models that no remaining code imports.
   - Carefully preserve MS and workspace request models in `backend/models/io.py`.
   - Update settings and environment examples to remove P6 SQLite configuration.

8. Clean frontend/backend naming and stale P6 assumptions.
   - Keep behavior intact, especially the Gantt chart.
   - Rename comments, constants, display labels, endpoint descriptions, service names, prompts, and app titles that say P6 when they now describe generic Lognos/MS schedule behavior.
   - Keep `project_type: "msp"` during transition, then optionally remove it once the backend no longer needs it.
   - Track `.next`/standalone output if it is part of the production artifact or currently tracked. Regenerate or update retained `.next` artifacts so required production files do not carry stale P6 naming.

9. Clean docs and production artifacts.
   - Delete P6 historical docs and exploration scripts.
   - Update README/backend docs to describe the MS-only app and `lognos_schedule` schema.
   - Update CHANGELOG only when implementation is made, not for this proposal-only branch unless you want proposal docs tracked as a change.

10. Verify.
   - Run backend tests.
   - Run frontend lint/build checks.
   - Start backend and frontend locally.
   - Smoke test chat with an MS project context and schedule-view loading.
   - Search for remaining reachable P6 imports and endpoint registrations.
   - Search source and retained production artifacts for stale P6/Primavera naming.

## Important Risks And Handling Decisions

- `SafeP6Transaction`: refactor out of chat execution. If a neutral transaction abstraction is still useful, rename it to `SafeScheduleTransaction`; do not preserve P6 SQLite assumptions by accident.
- `AgentDeps`: make it MS/workspace-neutral before deleting P6 services, so remaining tools depend only on repositories/services they actually use.
- `backend/models/io.py`: carefully split or prune P6 models while preserving all workspace and MS request models.
- Frontend/backend P6 labels: rename retained behavior to generic Lognos/MS schedule language rather than deleting behavior.
- `.next` artifacts: track which generated/standalone files are production-relevant or tracked by git; regenerate or update retained artifacts so they match the renamed app.
- `network_calculator.py`: preserve the capability. Rename P6-specific comments/types to generic schedule-network language if appropriate, but keep CPM/network calculation for MS/workspace schedules.

## Decisions Captured

- Delete old P6 docs and exploration scripts rather than archiving them.
- Keep `project_type` in the chat API for compatibility, while making the backend MS-only.
- Remove P6 schedule IDs and P6 conversation metadata from the active app. Old conversations can be deleted later.
- Rename the app to "Lognos Scheduling Agent".
- Include the MS semantic search replacement in this cleanup branch.
- Preserve network calculation and CPM/critical-path functionality for MS/workspace schedules.

## Semantic Vector Search Plan

The existing P6 vector search should not be preserved as-is because it indexes local SQLite P6 `TASK` data through `backend/services/vector_service.py` and `backend/tools/indexing/operations.py`. That path is P6-specific and belongs in the cleanup removal set.

The MS database already has vector-search support to build on: `lognos_schedule.schedule_activities.embedding` has an HNSW cosine index named `schedule_activities_embedding_idx`. The refactored app will keep semantic activity search, but implement it as an MS/Supabase capability.

Database impact: no destructive database changes or table redesign should be needed for the cleanup. The existing vector column and index are already present. For production-grade Supabase access, this branch may prepare an additive RPC migration such as `lognos_schedule.match_schedule_activities(...)`; applying that migration to the live Supabase project should be treated as a separate deployment decision. Existing activity rows with missing embeddings should be handled by an embedding backfill or importer fix, not by a schema rewrite.

Recommended refactor:

- Add an MS semantic search repository method against `lognos_schedule.schedule_activities.embedding`, filtered by `schedule_version_id`, project, WBS, owner, status, or date as needed.
- Add or keep an embedding generation step during schedule upload/import so each activity embedding reflects useful text such as WBS, name, verbose name, notes, owner/scope owner, milestone/summary status, and classification metadata.
- Add an agent tool such as `search_activities_ms` for natural-language activity lookup.
- Use deterministic tools like `list_activities_ms` for exact filters, and semantic search for fuzzy requests such as "find the concrete curing activity", email/status-update matching, ambiguous activity names, and activity discovery by description.

## Current Status

- Branch created and active: `cleanup/ms-only-production-prep`.
- Proposal document created: `cleanup_proposal.md`.
- P6 backend runtime paths, SQLite utilities, P6 tools, P6 repositories/services, P6 prompts, and old P6 docs/scripts/data have been removed from the branch.
- Root application folders have been renamed to `sch_backend` and `sch_frontend`; launch commands and Python imports use the new names.
- Chat and agent construction are MS/workspace-only; `project_type` is kept for compatibility and `p6` is rejected with a clear message.
- MS semantic activity search was added with a Supabase repository method, a `search_activities_ms` agent tool, an embedding service, and a prepared additive RPC migration at `sch_backend/migrations/003_schedule_activity_semantic_search.sql`.
- `network_calculator.py` and workspace CPM/Gantt/what-if behavior were preserved.
- Backend tests pass with `PYTHONPATH="$PWD" ... -m pytest`.
- Backend import smoke check passes with `GEMINI_API_KEY=dummy` and reports a visible warning if Logfire's optional Pydantic AI instrumentation is incompatible with the installed Pydantic AI version.
- Frontend production build passes. Frontend lint still has unrelated pre-existing errors in components outside the Gantt files changed in this cleanup.
- The Supabase RPC migration has not been applied to the live project; applying it remains a separate approval/deployment step.
