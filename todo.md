# TODO

## Persistence Strategy (Schedule Assistant + UI)

- [ ] Define a comprehensive persistence matrix for frontend state:
  - [ ] Gantt panel width
  - [ ] Gantt activity-name column width
  - [ ] Gantt relationship mode (`critical` / `all` / `none`)
  - [ ] Gantt filter state (when applicable)
  - [ ] Active project selection
  - [ ] Last opened conversation/context relevant to scheduling
- [ ] Decide persistence scope per item:
  - [ ] Session-only vs cross-session
  - [ ] Per-user vs global browser
  - [ ] Per-project vs global
- [ ] Define storage mechanism per scope:
  - [ ] `localStorage` for low-risk UI preferences
  - [ ] Backend profile/preferences table for cross-device persistence
- [ ] Standardize persistence keys/naming conventions and versioning for migrations.
- [ ] Implement a reusable persistence utility/hook (read, validate, write, fallback defaults).
- [ ] Apply persistence comprehensively across selected UI states (not one-off).
- [ ] Add guardrails for invalid or stale saved values (clamping, schema checks).
- [ ] Validate behavior with manual QA checklist and add tests where appropriate.
