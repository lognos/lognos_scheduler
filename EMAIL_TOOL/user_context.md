# User Context and Team Data Proposal

Date: 2026-03-04

## Objective

Ensure the scheduling agent is user-aware by default and can fetch full project team details (emails, roles, access context) on demand.

## Implemented Design

### 1) Logged-in user context in runtime by default

- Source of truth: `lognos_comm.users`
- Runtime resolution:
  - The chat router resolves request user context from `sender_email` for every turn.
  - If the user is not found, the fallback context still includes the request email.
- Data loaded into context:
  - `email`
  - `full_name`
  - `first_name`
  - `role`
  - `app_role`
  - `department`
  - `reports_to`
  - `active`
  - `current_project_id`
- Injection points:
  - Added to `AgentDeps` as `user_context`.
  - Included in the request context text sent to the agent each turn.

### 2) Team lookup tool (`get_team_data`) registered for the agent

- Tool name: `get_team_data`
- Purpose:
  - Retrieve project team members and their relevant data when the agent needs complete team context.
- Source tables:
  - `lognos_comm.user_project_access`
  - `lognos_comm.users`
- Lookup strategy:
  - First get project memberships from `user_project_access` by `project_id`.
  - Then enrich members with profile attributes from `users` using `user_email`.
- Return payload includes:
  - `project_id`
  - `requested_by` (current user context)
  - `member_count`
  - `team_members[]` with identity, role, app role, access level, project role, reporting lines, and project permissions fields.
- Default project behavior:
  - If no explicit `project_id` is provided to the tool, it uses the current request context project ID.

## Architecture Alignment

- Router handles request context resolution and dependency wiring.
- Repository encapsulates all Supabase data access (`UserContextRepository`).
- Tool only orchestrates runtime logic and delegates reads to repository.
- No direct DB access from the agent.

## Files Added

- `backend/repositories/user_context_repository.py`
- `backend/tools/context/__init__.py`
- `backend/tools/context/user_context.py`

## Files Updated

- `backend/models/domain.py`
- `backend/tools/_base.py`
- `backend/tools/__init__.py`
- `backend/agents/scheduling_agent.py`
- `backend/api/routers/chat.py`
- `backend/prompt/scheduler_general.xml.j2`

## Notes

- The implementation explicitly uses `lognos_comm.users` as requested.
- `get_team_data` is always available in `COMMON_TOOLS` so the scheduling agent can resolve project team context.
