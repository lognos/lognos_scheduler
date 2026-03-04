# Scheduling Agent Workflow Assessment

Date: 2026-03-04  
Scope: Current scheduling-agent flow, source-selection behavior, and optimization proposal for mixed P6/MS projects.  
Reference trace: `019cb7868ab13f57c45938f96d698f0e`

## 1) Current Workflow (As Implemented)

### Entry and context resolution
- `POST /api/v1/chat` initializes conversation context in `backend/api/routers/chat.py`.
- The router only resolves `p6_proj_id` through `P6ScheduleRepository.resolve_p6_proj_id(...)`.
- It emits reasoning text:
  - `Using P6 project {id}` when mapping exists.
  - `No P6 schedule linked` when mapping does not exist.
- There is no equivalent upfront source-resolution step for MS schedule context.

### Agent/tool behavior
- Agent is configured with both P6 and MS tools (`backend/agents/scheduling_agent.py`).
- Source choice is delegated to model reasoning and prompt interpretation (not deterministic router/service routing).
- User context currently injects `Lognos Project: <project_id>` plus optional `P6 Project ID: <id>`.
- Because MS tools require `project_name`, the model infers that `project_id` can be passed to MS tools.

### Persistence context
- `lognos_comm.p6_schedules` already contains a `schedule_type` column, but this describes P6 schedule flavor (`current`, `draft`, etc.), not source-family (`p6` vs `ms`).
- `lognos_comm.schedule_conversations` stores `project_id` and optional `p6_schedule_id`, but no source discriminator.
- `lognos_schedule.schedule_versions` contains MS schedule data by `project_name`, no source discriminator (MS-only dataset).

## 2) Observed Runtime Behavior (Trace Analysis)

For trace `019cb7868ab13f57c45938f96d698f0e`:

- Conversation context had:
  - `project_id = BIO4-24101`
  - `p6_schedule_id = null`
- Router span metadata confirms:
  - `p6_proj_id = null`
- Agent still used MS tools and executed:
  - `list_schedule_versions_ms(project_name='BIO4-24101')`
  - `load_schedule_ms(project_name='BIO4-24101', version_id=21)`
  - `calculate_gantt_ws(...)`

### Failure details
1. Tool-level failure occurred in `calculate_gantt_ws`:
   - Error: `'str' object has no attribute 'isoformat'`
   - Logged at `backend/tools/workspace/mutations.py`.
2. Agent run then exceeded output token limits:
   - `UsageLimitExceeded: output_tokens=64099 > 32000`
   - Prompt/input tokens were also very high (`73496`) with very large reasoning tokens.
3. Router surfaced final error and discarded transaction changes.

## 3) Why "No P6 schedule linked" is misleading

The message is technically correct for P6 mapping but semantically misleading for users working on MS-backed projects.

Current behavior implies this chain:
- Router checks only P6 linkage.
- Missing P6 linkage emits warning-like message.
- Agent may still succeed with MS tools.

Net effect:
- UX noise at the start of many valid MS requests.
- Ambiguous mental model of which data source is active.

## 4) Data Model Gap

A single canonical, per-project source discriminator is missing.

What exists today:
- P6 mapping (`lognos_comm.p6_schedules`) for some projects.
- MS versions (`lognos_schedule.schedule_versions`) for some projects.

What is missing:
- A deterministic `schedule_type` (source-family) for project routing at runtime.

## 5) Recommended Schema Addition (in `lognos_schedule`)

Create a registry table in `lognos_schedule` with an explicit source discriminator.

### Proposed table
`lognos_schedule.project_schedule_registry`

Suggested fields:
- `project_id text primary key`
- `schedule_type text not null check (schedule_type in ('p6','ms'))`
- `ms_project_name text null`
- `default_ms_version_id integer null`
- `p6_schedule_id uuid null`
- `updated_at timestamptz not null default now()`
- `metadata jsonb not null default '{}'::jsonb`

Suggested constraints:
- If `schedule_type='ms'`, require `ms_project_name`.
- If `schedule_type='p6'`, require `p6_schedule_id`.
- Optional FK:
  - `default_ms_version_id -> lognos_schedule.schedule_versions(id)`
  - `p6_schedule_id -> lognos_comm.p6_schedules(id)`

Rationale:
- Keeps routing metadata centralized and explicit.
- Lives in `lognos_schedule` as requested.
- Supports future hybrid/dual-source policy via metadata if needed.

## 6) Simplified Runtime Flow (Target)

1. On chat start, resolve registry by `project_id`.
2. Branch by `schedule_type`:
   - `ms`: preload MS context message and suppress P6-link warning.
   - `p6`: resolve P6 schedule and include `p6_proj_id` context.
3. Persist resolved `schedule_type` into conversation metadata for continuity.
4. Emit one clear initialization message:
   - `Using MS schedule source (BIO4-24101, current version v260129)`
   - or `Using P6 schedule source (proj_id 1011)`

## 7) Additional Findings Affecting This Use Case

- `calculate_gantt_ws` can fail when baseline fields are strings and code assumes datetime (`isoformat()` calls). This is an independent bug that amplifies token/cost failures because the model keeps reasoning after tool errors.
- Prompt + tool-return footprint remains large for visualization scenarios, increasing the risk of output-token overflow.

## 8) Priority Implementation Plan

### Phase 1 (Low risk)
- Add `project_schedule_registry` table and seed values for active projects.
- Add repository for registry lookup.
- Update chat router initialization to resolve source before building context.
- Replace `No P6 schedule linked` with source-aware message.

### Phase 2 (Stability)
- Harden `calculate_gantt_ws` date serialization to handle string/datetime safely.
- Add guardrails for tool-error short-circuiting to reduce runaway reasoning after failures.

### Phase 3 (Performance)
- Reduce prompt verbosity for non-P6 operations.
- Limit or summarize oversized tool returns before they re-enter model context.

## 9) Acceptance Criteria

- For MS projects, initialization never shows `No P6 schedule linked`.
- Agent receives deterministic source context (`schedule_type`) before first tool call.
- Visualization request in the reference scenario executes without source ambiguity.
- Token overrun incidence is reduced for gantt-heavy prompts.

## 10) Concrete Evidence Snapshot

- `lognos_comm.p6_schedules`: only one active row (`project_id='SOUT-01-0002'`).
- `lognos_schedule.schedule_versions`: contains versions for `BIO4-24101` including current `id=21`.
- Trace confirms mixed behavior: no P6 mapping + successful MS tool path + gantt serialization error + token overflow.

## 11) Revised Temporary Plan (No DB redesign yet)

### Objective
Introduce a temporary explicit request argument `project_type` hardcoded to `"msp"` and constrain the agent runtime to MSP + Workspace tooling only.

### Why this temporary plan
- It removes source ambiguity immediately without waiting for schema migration.
- It prevents misleading startup messaging (`No P6 schedule linked`) for MSP projects.
- It reduces prompt/tool confusion and avoids unnecessary P6 tool calls.

### Proposed request contract (temporary)
- Add `project_type` to chat request model.
- Allowed values: `"msp" | "p6"` (or temporary literal default while rollout is active).
- For this temporary phase, backend behavior is effectively hardcoded to `"msp"`.

Suggested temporary behavior:
- If `project_type == "msp"`:
  - Skip P6 resolution path and skip P6 startup reasoning messages.
  - Build MSP-focused context (`Lognos Project`, inferred/selected MS version context).
  - Execute MSP-scoped agent (or MSP-scoped toolset).

## 12) Are any P6 tools required for MSP/Workspace operation?

Short answer: **No**.

Detailed assessment:
- MSP schedule load path is fully implemented via:
  - `list_schedule_versions_ms`
  - `load_schedule_ms`
  - `schedule_state_manager.load_from_ms(...)`
- Workspace operations (`calculate_gantt_ws`, `modify_activity_ws`, relationship edits, etc.) operate on in-memory DataFrames and do not require P6 tools.
- `index_project` is P6-only (vector indexing of P6 project activities) and not needed for MSP workflows.
- `load_schedule_ws` is P6-loader and not needed for MSP workflows.

Conclusion: MSP mode can run correctly with **zero** P6 tools registered.

## 13) Recommended MSP-only tool allowlist (temporary)

### Keep (MS tools)
- `list_schedule_versions_ms`
- `get_schedule_overview_ms`
- `list_activities_ms`
- `get_activity_ms`
- `get_project_constraints_ms`
- `get_calendar_ms`
- `load_schedule_ms`
- `create_schedule_subversion_ms`
- `promote_subversion_ms`

### Keep (Workspace tools)
- `get_workspace_status_ws`
- `clear_schedule_ws`
- `calculate_gantt_ws`
- `modify_activity_ws`
- `add_activity_ws`
- `add_relationship_ws`
- `modify_relationship_ws`
- `delete_relationship_ws`
- `delete_activity_ws`
- `hide_gantt_ws`
- `assign_activity_codes_ws`
- `bulk_assign_activity_codes_ws`
- `remove_activity_codes_ws`
- `get_activity_codes_ws`

### Remove/disable for MSP mode
- All `_p6` tools
- `index_project`
- `load_schedule_ws` (P6 loader)
- `create_schedule_ws` (optional: can be disabled temporarily if MSP-first UX should always start from loaded MSP versions)

## 14) Prompt policy changes required for temporary MSP mode

Current system prompt is P6-centric and explicitly encourages P6 tools. Even with MSP data available, this increases the chance of incorrect tool selection.

Temporary prompt policy for MSP mode should:
- Define the agent as MSP schedule assistant (not Primavera-only).
- Remove P6 business rules and P6 tool guidance.
- Explicitly instruct first-step flow:
  1. resolve/list versions for project,
  2. load MSP version to workspace,
  3. perform analysis/visualization via `_ws` tools.
- Forbid P6 tool usage in MSP mode.

## 15) Practical rollout recommendation (no implementation yet)

1. Add `project_type` argument to chat request model and set temporary default to `"msp"`.
2. Add MSP-mode branching in chat router initialization (skip P6 schedule linking message).
3. Use MSP-only toolset for agent runs when `project_type="msp"`.
4. Switch to MSP-oriented prompt for that mode.
5. Keep prior long-term plan (`project_schedule_registry`) for durable source routing once temporary mode is validated.

## 16) Risks and mitigations for temporary mode

- Risk: Existing P6 conversations lose capabilities if forced globally to MSP.
  - Mitigation: Keep optional `project_type="p6"` path available internally, even if UI sends `"msp"` for now.
- Risk: Tool-call failures in `calculate_gantt_ws` still possible from date serialization edge cases.
  - Mitigation: Prioritize the known `isoformat()` string/date hardening in a follow-up patch.
- Risk: Token pressure remains high on large visualization requests.
  - Mitigation: enforce concise response instructions and tool-result summarization in MSP prompt.

## 17) Prompt Strategy Proposal (General + Specific)

Your proposal is the right approach and aligns well with the temporary MSP-first plan.

### Recommended composition model
- `general` prompt: shared rules that always apply (response format, clarification behavior, safety/validation constraints, workspace interaction principles, concise output policy).
- `msp` prompt: MSP domain rules, MS tool selection policy, version-loading flow, and MSP-specific terminology.
- `p6` prompt: P6 domain rules, P6 business constraints, and P6-specific tool usage.

Runtime composition:
- `project_type = "msp"` → `general + msp`
- `project_type = "p6"` → `general + p6`

### Why this is better than one large prompt
- Reduces conflicting instructions (current prompt mixes P6-first guidance into MSP requests).
- Improves determinism in tool selection by exposing only relevant domain instructions.
- Lowers token overhead by avoiding unused domain blocks.
- Makes governance easier: shared behavior evolves once in `general`; domain logic evolves independently.

### Suggested prompt boundaries

`general` should contain only cross-domain behavior:
- Structured output contract (`SchedulingResponse`, `ClarificationRequest`, `ErrorResponse`).
- How to ask clarifications when key identifiers are missing.
- Workspace/Gantt behavior that is source-agnostic.
- Response brevity policy and anti-runaway guidance.
- Universal decision order (understand intent → select tool family → execute minimal calls → summarize).

`msp` should contain only MSP-specific behavior:
- First action sequence: list/select version → `load_schedule_ms` → workspace analysis.
- MSP tool allowlist and explicit prohibition of `_p6` and `index_project` in MSP mode.
- MSP naming conventions (`project_name`, `version_id`, current/baseline handling).

`p6` should contain only P6-specific behavior:
- P6 DB mutation/query rules and status constraints.
- P6 tool allowlist and P6 identifier conventions (`proj_id`, task code semantics).
- Any vector-search/indexing guidance (`index_project`) only for P6 mode.

### Temporary mode (current workstream)
- Since `project_type` is hardcoded to `"msp"`, the system should always compose `general + msp`.
- Keep `general + p6` path implemented but inactive behind `project_type="p6"` for later re-enable.

### Implementation-oriented guidance (proposal only, no code yet)
- Store prompts as three files:
  - `prompt/scheduler_general.xml.j2`
  - `prompt/scheduler_msp.xml.j2`
  - `prompt/scheduler_p6.xml.j2`
- Compose at agent-build time (or per-request in router if needed) using a deterministic combiner in prompt loader.
- Add a simple validation check to fail startup if any required prompt segment is missing.

### Acceptance criteria for prompt architecture
- In MSP mode, no P6 instruction text appears in the effective system prompt.
- MSP requests never trigger P6 tool calls.
- Token footprint of system prompt is lower than current monolithic prompt.
- Switching to P6 mode changes only prompt/tool profile, not response contract.
