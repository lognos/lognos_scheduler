-- Additive RPC for indexed semantic search over MS schedule activities.
-- This migration is prepared for deployment but is not applied by cleanup tooling.

create or replace function lognos_schedule.match_schedule_activities(
    query_embedding vector(1536),
    target_version_id bigint,
    match_threshold double precision default 0.2,
    match_count integer default 10,
    wbs_prefix text default null,
    owner_filter text default null,
    scope_owner_filter text default null
)
returns table (
    id text,
    schedule_version_id text,
    ms_uid text,
    wbs text,
    name text,
    name_verbose text,
    owner text,
    scope_owner text,
    similarity double precision
)
language sql
stable
as $$
    select
        a.id::text,
        a.schedule_version_id::text,
        a.ms_uid::text,
        a.wbs::text,
        a.name::text,
        a.name_verbose::text,
        a.owner::text,
        a.scope_owner::text,
        1 - (a.embedding <=> query_embedding) as similarity
    from lognos_schedule.schedule_activities a
    where a.schedule_version_id = target_version_id
      and a.embedding is not null
      and 1 - (a.embedding <=> query_embedding) >= match_threshold
      and (wbs_prefix is null or a.wbs like wbs_prefix || '%')
      and (owner_filter is null or a.owner = owner_filter)
      and (scope_owner_filter is null or a.scope_owner = scope_owner_filter)
    order by a.embedding <=> query_embedding
    limit least(greatest(match_count, 1), 50);
$$;