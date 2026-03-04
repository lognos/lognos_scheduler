# Custom View Data Architecture Proposal

## Goal

Define a future-proof data architecture for custom Gantt views where the UI can always render supported capabilities (links, baseline modes, optional columns, updates, and future what-if overlays) regardless of display filters. Scope is limited to data contracts, payload shape, and backend assembly behavior for custom views.

## Problem Summary

Trace analysis identified a contract mismatch between conversational intent and tool execution:

- Trace `019cb7482a6f1e117e72595dc604424c` shows `calculate_gantt_ws` invoked with only `title` and `group_by`.
- No baseline mode or capability selection was passed at invocation time.
- Backend spans confirm relationships and baseline fields existed in source data (`get_relationships_by_version` and activity baseline fields were available).

This means the issue is not missing source data. The issue is that the custom-view path does not explicitly encode capability intent and data guarantees in its request/response contract.

## Current State

### Workspace Gantt path (`calculate_gantt_ws`)

- Runs CPM and updates workspace.
- Applies filters before building visible `items`.
- Includes relationships only when both endpoints are in filtered activity set.
- Returns a payload optimized for current rendering, not for explicit capability guarantees.

### Persisted view path (`ScheduleViewService`)

- Already models baseline modes and baseline availability metadata.
- Assembles richer payload semantics for system views.
- Better aligned with deterministic UI capabilities than workspace custom-view path.

### Gap

Two similar paths produce Gantt payloads with different capability semantics. Custom views need a single authoritative data contract that decouples:

- Data envelope completeness (what is available)
- Display subset intent (what is currently shown)

## Design Principles

1. Data superset, display subset
   - Always assemble a complete data envelope for the active view context.
   - Apply display filters as a derived projection, not as a destructive data reduction.

2. Explicit capabilities
   - Payload must state what can be rendered now (`links`, `baseline_modes`, `updates`, `columns`, `what_if`).
   - UI should not infer capability from missing arrays/fields.

3. Stable identifiers and lineage
   - Activities and links must carry stable IDs to support scenario diffing and overlays.

4. One contract across paths
   - Workspace custom views and persisted schedule views should share the same payload schema and capability semantics.

5. Backward compatibility first
   - Introduce additive fields and a schema version marker.

## Proposed Data Contract

### Request model (custom view compute)

Add explicit capability and rendering intent to custom-view requests.

```json
{
  "view_id": "optional-uuid-or-key",
  "title": "BIO4 custom view",
  "group_by": "wbs",
  "display_filter": {
    "critical_only": false,
    "wbs_path": "BIO4.ENG",
    "status": ["in_progress"],
    "activity_codes": {"PHASE": ["ENG"]},
    "date_start": "2025-01-01",
    "date_end": "2025-03-31",
    "search_term": "steel"
  },
  "render_options": {
    "columns": ["start", "finish", "total_float", "percent_complete"],
    "show_links": true,
    "show_updates": true,
    "baseline_mode": "own"
  },
  "data_envelope": {
    "include_links": true,
    "include_updates": true,
    "include_baselines": ["own", "previous_version", "database_baseline"],
    "include_optional_fields": ["percent_complete", "free_float_days"],
    "include_hierarchy": true
  }
}
```

### Response model (custom view payload)

```json
{
  "schema_version": "gantt.custom.v2",
  "view": {
    "id": "uuid-or-key",
    "title": "BIO4 custom view",
    "grouping": "WBS",
    "source": {
      "project_id": "BIO4-24101",
      "schedule_version_id": 123,
      "scenario_id": null,
      "generated_at": "2026-01-12T10:30:00Z"
    }
  },
  "capabilities": {
    "links": {"available": true, "render_enabled": true},
    "updates": {"available": true, "render_enabled": true},
    "baseline_modes": {
      "available": ["own", "previous_version", "database_baseline"],
      "selected": "own"
    },
    "columns": {
      "available": ["start", "finish", "total_float", "percent_complete"],
      "selected": ["start", "finish", "total_float", "percent_complete"]
    },
    "what_if": {
      "supported": true,
      "active_scenario_id": null,
      "overlay_available": false
    }
  },
  "data_envelope": {
    "activities": [],
    "relationships": [],
    "baselines": {
      "own": {"activities": []},
      "previous_version": {"activities": []},
      "database_baseline": {"activities": []}
    },
    "updates": []
  },
  "display": {
    "filter_applied": {},
    "visible_activity_ids": [],
    "visible_relationship_ids": [],
    "project_start": "2026-01-01",
    "project_finish": "2026-08-30",
    "critical_path_length": 180,
    "total_activities": 1200,
    "filtered_activities": 178,
    "preserve_order": true
  }
}
```

## Key Behavioral Rules

1. Relationships are envelope data, not only view-local artifacts
   - `data_envelope.relationships` includes all relationships for the selected version/scenario (or a documented bounded subset).
   - `display.visible_relationship_ids` decides which links are currently drawn.

2. Baseline data is capability-scoped
   - Baseline availability is reported independently from current `display_filter`.
   - If a baseline mode is unavailable, API returns explicit reason metadata.

3. Optional columns are separately negotiated
   - Column availability and selected columns are explicit.
   - Missing optional values are represented as null, not dropped fields.

4. Display filter never mutates envelope guarantees
   - Applying `critical_only` or date windows changes only `display.visible_*` projections.

5. Deterministic render toggles
   - `show_links`, `show_updates`, and `baseline_mode` are render options; payload always contains enough data to honor them when capability says available.

## What-if Readiness (Data Scope Only)

To support future what-if without reworking contracts:

- Add `scenario_id` and `parent_scenario_id` lineage metadata to view source.
- Keep stable IDs for activities/relationships across baseline/current/scenario variants where possible.
- Represent scenario deltas in additive structures:
  - `what_if.added_activities`
  - `what_if.updated_activities`
  - `what_if.removed_activity_ids`
  - `what_if.added_relationships`
  - `what_if.updated_relationships`
  - `what_if.removed_relationship_ids`
- Keep baseline maps keyed by mode so scenario-vs-baseline overlays remain deterministic.

This enables side-by-side or overlay rendering later without changing core payload shape.

## Implementation Plan

### Phase 1: Contract introduction (non-breaking)

- Add new request/response models for custom-view compute in `backend/models/io.py`.
- Keep current fields, add `schema_version`, `capabilities`, `data_envelope`, and `display` blocks.
- Default behavior should mirror current UX when new fields are omitted.

### Phase 2: Workspace path alignment

- Refactor `calculate_gantt_ws` assembly to produce:
  - Full envelope (activities, relationships, baseline maps, updates)
  - Display projections (`visible_activity_ids`, `visible_relationship_ids`)
- Preserve existing `gantt_panel` event consumption in frontend.

### Phase 3: Shared builder across services

- Introduce a shared payload builder used by:
  - `calculate_gantt_ws` custom views
  - `ScheduleViewService.build_view_payload`
- Remove divergent capability semantics between paths.

### Phase 4: What-if metadata scaffolding

- Add scenario lineage fields and empty delta blocks.
- No UI changes required in this phase.

## Validation Checklist

1. Capability consistency
   - If `capabilities.links.available=true`, toggling links never fails due to missing data arrays.

2. Baseline consistency
   - Selected baseline mode is always reflected in capability metadata and render result.

3. Filter invariance
   - Toggling filters changes display projections but does not remove envelope capabilities.

4. Cross-path parity
   - Workspace custom view and persisted system view payloads validate against the same schema version.

5. Future compatibility
   - Payload accepts scenario metadata and delta blocks without breaking existing frontend parsing.

## Risks and Mitigations

- Increased payload size
  - Mitigation: keep envelope complete but optionally bounded by server limits and include truncation metadata.

- Transitional complexity while two formats coexist
  - Mitigation: schema version marker and adapter layer in frontend parser.

- Performance regressions on large schedules
  - Mitigation: cache envelope by `(project_id, schedule_version_id, scenario_id)` and recompute only display projections per filter.

## Recommendation

Adopt the v2 custom-view contract with explicit `capabilities + data_envelope + display` separation, and make it the shared contract for both workspace and persisted schedule-view paths. This resolves current mismatch issues (agent claims vs rendered capability), keeps custom views deterministic under filters, and provides a stable base for future what-if visualization without another contract rewrite.
