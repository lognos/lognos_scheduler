-- Migration: Add owner and scope_owner columns to schedule_activities
-- Date: 2025-01-XX
-- Purpose: Support activity ownership tracking in MS Project schedules

-- Add owner column (activity owner/responsible person)
ALTER TABLE schedule_activities 
ADD COLUMN IF NOT EXISTS owner TEXT;

-- Add scope_owner column (scope/discipline owner)
ALTER TABLE schedule_activities 
ADD COLUMN IF NOT EXISTS scope_owner TEXT;

-- Add comments for documentation
COMMENT ON COLUMN schedule_activities.owner IS 'Person responsible for the activity execution';
COMMENT ON COLUMN schedule_activities.scope_owner IS 'Person responsible for the scope/discipline this activity belongs to';

-- Create index for owner queries (optional, add if frequently queried)
CREATE INDEX IF NOT EXISTS idx_schedule_activities_owner 
ON schedule_activities(owner) 
WHERE owner IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_schedule_activities_scope_owner 
ON schedule_activities(scope_owner) 
WHERE scope_owner IS NOT NULL;
