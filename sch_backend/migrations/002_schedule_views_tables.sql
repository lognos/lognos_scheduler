-- Migration: Create persisted schedule view definitions and snapshots
-- Schema: lognos_schedule

CREATE TABLE IF NOT EXISTS lognos_schedule.schedule_view_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id TEXT NOT NULL,
    schedule_version_id BIGINT NOT NULL,
    view_key TEXT NOT NULL,
    view_name TEXT NOT NULL,
    view_type TEXT NOT NULL CHECK (view_type IN ('system', 'user')),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, schedule_version_id, view_key)
);

CREATE INDEX IF NOT EXISTS idx_schedule_view_definitions_project_version
    ON lognos_schedule.schedule_view_definitions(project_id, schedule_version_id);

CREATE INDEX IF NOT EXISTS idx_schedule_view_definitions_default
    ON lognos_schedule.schedule_view_definitions(project_id, is_default)
    WHERE is_default = TRUE;

CREATE TABLE IF NOT EXISTS lognos_schedule.schedule_view_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    view_definition_id UUID NOT NULL REFERENCES lognos_schedule.schedule_view_definitions(id) ON DELETE CASCADE,
    schedule_version_id BIGINT NOT NULL,
    payload JSONB NOT NULL,
    checksum TEXT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (view_definition_id, schedule_version_id)
);

CREATE INDEX IF NOT EXISTS idx_schedule_view_snapshots_view_computed
    ON lognos_schedule.schedule_view_snapshots(view_definition_id, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_schedule_view_snapshots_version
    ON lognos_schedule.schedule_view_snapshots(schedule_version_id);
