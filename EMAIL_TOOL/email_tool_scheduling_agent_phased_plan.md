# Email Capability Proposal for Scheduling Agent

**Date:** March 4, 2026  
**Status:** Draft  
**Owner:** Scheduling Assistant Team

---

## 1) Objective

Enable the scheduling agent to safely and reliably handle outbound and inbound email workflows in phases:

1. Phase 1: draft/send schedule emails (no attachments)
2. Phase 2: include schedule artifacts as attachments
3. Phase 3: read, classify, and respond to inbound emails

The plan prioritizes minimal risk to current scheduling flows and strict alignment with existing agent architecture.

---

## 2) Current State Assessment

### 2.1 What already exists

A full email stack was copied into `EMAIL_TOOL/backend` with:

- tools for send/search/draft/modify/send-draft/attachments
- service and repository layers
- Microsoft Graph integration
- attachment processor for PDF, DOCX, XLSX

### 2.2 Key integration blockers found

1. **Import namespace collision**
   - Copied files import from `backend.*`.
   - In this repository, `backend.*` resolves to the main scheduling backend, not `EMAIL_TOOL/backend`.
   - Result: email models/settings in copied stack are not directly import-safe in current runtime.

2. **Settings mismatch**
   - Copied email stack expects lowercase fields (`tenant_id`, `client_id`, `bio4_lognos_user_id`, etc.).
   - Main backend settings currently expose mostly uppercase names and different model assumptions.

3. **Missing runtime dependencies in root requirements**
   - Current `requirements.txt` lacks required packages for the copied stack (`msgraph-sdk`, `azure-identity`, `markdown`, `bleach`, `google-genai`, `openpyxl`, `python-docx`).

4. **Dependency injection gap in agent deps**
   - `AgentDeps` currently has scheduling/vector/MS schedule dependencies only.
   - Email services are not present, so email tools cannot run in the current agent runtime.

5. **Toolset scope exceeds Phase 1 requirement**
   - Existing stack includes read/respond and attachment processing from the start.
   - For safe rollout, this should be gated and activated phase-by-phase.

6. **Code quality issue discovered**
   - In attachment processor, one logging call uses `lcf.error` instead of `logfire.error`.

### 2.3 Database implications

- The scheduling conversation store exists in schema `lognos_comm` (`schedule_conversations`, `schedule_chat_messages`).
- No dedicated scheduling email outbox/ingestion tables were found in `lognos_comm`.
- A legacy `public.email_send_log` exists but appears outside the scheduling schema and should not be reused blindly.

---

## 3) Proposed Architecture

### 3.1 Target boundary (aligned with current backend patterns)

- Router -> Service -> Repository
- Agent uses tools only
- Email tools call local email service/repository (no internal HTTP calls)
- Outbound and inbound email events are persisted via repository layer for traceability

### 3.2 Packaging decision

Refactor copied stack into first-class scheduling package namespace:

- `backend/email_tools/models/...`
- `backend/email_tools/repositories/...`
- `backend/email_tools/services/...`
- `backend/email_tools/tools/...`

Avoid dual `backend` roots and avoid importing from `EMAIL_TOOL/backend` at runtime.

### 3.3 Feature flags

Add explicit feature flags:

- `ENABLE_EMAIL_PHASE1_SEND`
- `ENABLE_EMAIL_PHASE2_ATTACHMENTS`
- `ENABLE_EMAIL_PHASE3_INBOUND`

Tools should no-op with clear error/status when a later phase is disabled.

---

## 4) Phase Plan

## Phase 0 (Foundation Hardening - required before Phase 1)

### Scope

- Normalize namespace/package layout under main backend.
- Introduce email config in main settings.
- Add missing dependencies.
- Wire `AgentDeps` with optional email dependencies.
- Add basic health check and smoke test path.

### Deliverables

- Import-safe email package under main backend.
- Settings contract for Graph credentials and mailbox IDs.
- Agent dependency injection wired in chat router.
- Feature flags scaffolded.

### Exit criteria

- Scheduling agent starts with email dependencies enabled.
- `check_email_service_health_tool` returns operational when credentials are valid.

---

## Phase 1 (Requested first milestone: draft/send emails, no attachments)

### Scope

Enable only:

- create draft email
- modify draft
- list drafts
- send draft
- direct send email (plain/HTML)

Disable:

- attachment retrieval/processing
- inbox search/read/respond

### Functional behavior

- Agent can compose schedule update emails from conversation context.
- Agent can send only after explicit user confirmation in same conversation turn (guardrail).
- Email metadata stored in scheduling schema for audit:
  - conversation_id
  - sender/recipient
  - subject
  - status
  - message/draft IDs
  - timestamp
  - error details

### Data model additions (new tables in `lognos_comm`)

- `schedule_email_outbox`
- `schedule_email_audit`

### Deliverables

- Phase 1 tool registry exposed to scheduling agent.
- Prompt updates to teach when to draft vs send.
- Audit persistence + Logfire spans.

### Exit criteria

- User can ask: “Draft an update email for schedule X to Y@company.com” and receive draft details.
- User can ask: “Send it” and tool sends successfully.
- All send attempts are traceable in DB + logs.

---

## Phase 2 (Attachments)

### Scope

Add controlled attachment support for schedule artifacts:

- generated gantt export (if available)
- structured schedule summary (CSV/JSON/PDF when available)
- optional user-requested files from project assets

### Functional behavior

- Attachments validated by MIME type and size limits.
- Hard cap on single attachment and total email payload.
- Attachment metadata persisted in outbox/audit records.

### Deliverables

- Enable `get_email_attachments_tool` plus outbound attachment wiring.
- Fix attachment processor defects and harden file handling.
- Add policies for allowed file types and max size in settings.

### Exit criteria

- User can request schedule email with attachment and tool sends successfully when file exists.
- Unsafe or oversized attachments are rejected with clear user-facing reason.

---

## Phase 3 (Read and respond to emails)

### Scope

Enable inbound mailbox workflows:

- search/read inbox messages
- draft responses linked to original thread
- send response drafts
- optionally classify intent (schedule question, status request, change request)

### Functional behavior

- Use explicit mailbox scope and folder filters.
- Keep human-in-the-loop default for sending responses.
- Persist thread linkage:
  - inbound message_id
  - conversation_id
  - generated draft_id
  - response status

### Data model additions

- `schedule_email_inbox_index` (ingestion state and dedupe)
- `schedule_email_thread_links` (conversation/message correlation)

### Deliverables

- Enable `search_emails_tool` and `draft_email_response_tool`.
- Add inbound polling/sync job or on-demand read path.
- Add idempotency controls to prevent duplicate response drafts.

### Exit criteria

- Agent can find relevant inbound messages and prepare draft replies.
- Agent sends reply only after user confirmation.
- Full thread traceability across inbox -> draft -> sent.

---

## 5) Cross-Cutting Requirements

- Strict Pydantic models for all IO and tool contracts.
- Logfire spans in tool/service/repository boundaries.
- No direct DB access from routers or tools.
- Feature-flagged rollout by phase.
- Regression tests for existing scheduling tools must pass.

---

## 6) Suggested Execution Sequence

1. Phase 0 hardening branch
2. Phase 1 MVP release (draft/send, no attachments)
3. Stabilization window with telemetry review
4. Phase 2 attachments release
5. Phase 3 inbound read/respond release

---

## 7) Risks and Mitigations

1. **Credential/config drift**
   - Mitigation: startup validation + health endpoint + explicit env docs.

2. **Accidental emails**
   - Mitigation: confirmation gate before send; optional allowlist in non-prod.

3. **Attachment security and cost**
   - Mitigation: MIME/size restrictions, explicit truncation/summarization rules.

4. **Thread mismatch for replies**
   - Mitigation: persist message/thread IDs and enforce idempotency keys.

5. **Scope creep from copied tools**
   - Mitigation: expose only phase-approved tools in agent registry.

---

## 8) Acceptance Checklist by Phase

### Phase 1

- [ ] Agent can draft schedule email from user request
- [ ] Agent can modify draft
- [ ] Agent can send draft after explicit confirmation
- [ ] Attachments are not available
- [ ] All sends are logged in `lognos_comm`

### Phase 2

- [ ] Agent can attach approved schedule artifacts
- [ ] Size/type validation enforced
- [ ] Attachment metadata logged

### Phase 3

- [ ] Agent can search inbox with filters
- [ ] Agent can draft contextual replies
- [ ] Agent sends replies only after confirmation
- [ ] Thread linkage persisted and queryable
