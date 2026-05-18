"""
Repository for MS Project schedules stored in Supabase.
"""
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
from datetime import datetime, date, timedelta
from hashlib import sha1
import json
import logfire
from supabase import Client

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class MSScheduleRepository:
    """Repository for MS Project schedules stored in Supabase.
    
    Handles all CRUD operations for schedule_versions, schedule_activities,
    schedule_links, project_calendars, calendar_exceptions, and project_constraints.
    
    All tables live in the lognos_schedule schema.
    """
    
    supabase: Client
    SCHEMA: str = "lognos_schedule"
    
    def _table(self, name: str):
        """Return a PostgREST query builder scoped to lognos_schedule."""
        return self.supabase.schema(self.SCHEMA).table(name)
    
    # =========================================================================
    # Version Operations
    # =========================================================================
    
    @logfire.instrument("ms_repo.list_versions")
    async def list_versions(
        self,
        project_name: str,
        include_temp: bool = True
    ) -> list[dict]:
        """List all schedule versions for a project.
        
        Args:
            project_name: Project name (e.g., 'BIO4-01-0002')
            include_temp: Include temporary/draft versions
            
        Returns:
            List of version records ordered by version_number desc
        """
        query = self._table('schedule_versions') \
            .select('*') \
            .eq('project_name', project_name) \
            .order('version_number', desc=True)
        
        return query.execute().data or []
    
    @logfire.instrument("ms_repo.get_version")
    async def get_version(self, version_id: int) -> Optional[dict]:
        """Get version by ID."""
        try:
            result = self._table('schedule_versions') \
                .select('*') \
                .eq('id', version_id) \
                .single() \
                .execute()
            return result.data
        except Exception:
            return None
    
    @logfire.instrument("ms_repo.get_current_version")
    async def get_current_version(self, project_name: str) -> Optional[dict]:
        """Get the current active version for a project."""
        try:
            result = self._table('schedule_versions') \
                .select('*') \
                .eq('project_name', project_name) \
                .eq('is_current', True) \
                .single() \
                .execute()
            return result.data
        except Exception:
            return None

    @logfire.instrument("ms_repo.get_previous_version")
    async def get_previous_version(
        self, project_name: str, current_version_number: int,
    ) -> Optional[dict]:
        """Get the version immediately before the current one by version_number."""
        result = self._table('schedule_versions') \
            .select('*') \
            .eq('project_name', project_name) \
            .lt('version_number', current_version_number) \
            .order('version_number', desc=True) \
            .limit(1) \
            .execute()
        return result.data[0] if result.data else None

    @logfire.instrument("ms_repo.get_baseline_version")
    async def get_baseline_version(self, project_name: str) -> Optional[dict]:
        """Get the version flagged as baseline for a project."""
        try:
            result = self._table('schedule_versions') \
                .select('*') \
                .eq('project_name', project_name) \
                .eq('is_baseline', True) \
                .single() \
                .execute()
            return result.data
        except Exception:
            return None

    # =========================================================================
    # Activity Operations
    # =========================================================================
    
    @logfire.instrument("ms_repo.get_activities_lookahead")
    async def get_activities_lookahead(
        self,
        version_id: int,
        reference_date: date,
        weeks_back: int = 1,
        weeks_forward: int = 2,
        include_summary: bool = False
    ) -> list[dict]:
        """Get activities within a lookahead window.
        
        Args:
            version_id: Schedule version ID
            reference_date: Center date for the window
            weeks_back: Weeks to look back from reference
            weeks_forward: Weeks to look forward from reference
            include_summary: Include summary activities
            
        Returns:
            Activities that overlap with the date window
        """
        start_date = reference_date - timedelta(weeks=weeks_back)
        end_date = reference_date + timedelta(weeks=weeks_forward)
        
        query = self._table('schedule_activities') \
            .select('*') \
            .eq('schedule_version_id', version_id) \
            .gte('finish', start_date.isoformat()) \
            .lte('start', end_date.isoformat())
        
        if not include_summary:
            query = query.eq('is_summary', False)
        
        return query.order('start').execute().data or []
    
    @logfire.instrument("ms_repo.get_activities_by_version")
    async def get_activities_by_version(
        self,
        version_id: int,
        limit: int = 500,
        offset: int = 0,
        wbs_prefix: Optional[str] = None,
        critical_only: bool = False,
        owner: Optional[str] = None,
        scope_owner: Optional[str] = None,
        include_summary: bool = True
    ) -> list[dict]:
        """Get activities for a version with pagination and filters.
        
        Args:
            version_id: Schedule version ID
            limit: Max activities to return
            offset: Pagination offset
            wbs_prefix: Filter by WBS prefix (e.g., '1.3')
            critical_only: Only critical path activities (total_float_d = 0)
            owner: Filter by activity owner
            scope_owner: Filter by scope owner
            include_summary: Include summary activities
            
        Returns:
            List of activity records
        """
        query = self._table('schedule_activities') \
            .select('*') \
            .eq('schedule_version_id', version_id)
        
        if wbs_prefix:
            query = query.like('wbs', f'{wbs_prefix}%')
        
        if critical_only:
            query = query.eq('total_float_d', 0)
        
        if owner:
            query = query.eq('owner', owner)
        
        if scope_owner:
            query = query.eq('scope_owner', scope_owner)
        
        if not include_summary:
            query = query.eq('is_summary', False)
        
        return query.order('wbs').range(offset, offset + limit - 1).execute().data or []
    
    @logfire.instrument("ms_repo.get_activity_by_id")
    async def get_activity_by_id(self, activity_id: int) -> Optional[dict]:
        """Get a single activity by internal ID."""
        try:
            result = self._table('schedule_activities') \
                .select('*') \
                .eq('id', activity_id) \
                .single() \
                .execute()
            return result.data
        except Exception:
            return None
    
    @logfire.instrument("ms_repo.get_update_logs_by_version")
    async def get_update_logs_by_version(self, version_id: int) -> list[dict]:
        """Fetch schedule update logs for a version.

        Returns rows from ``schedule_update_logs`` ordered by most recent first.
        """
        result = (
            self._table("schedule_update_logs")
            .select(
                "log_id, activity_id, update_type, details, reported_value, "
                "reported_by, reported_at, processed"
            )
            .eq("schedule_version_id", version_id)
            .order("reported_at", desc=True)
            .execute()
        )
        return result.data or []

    @logfire.instrument("ms_repo.get_activity_by_ms_uid")
    async def get_activity_by_ms_uid(
        self, 
        version_id: int, 
        ms_uid: int
    ) -> Optional[dict]:
        """Get a single activity by MS Project UID within a version."""
        try:
            result = self._table('schedule_activities') \
                .select('*') \
                .eq('schedule_version_id', version_id) \
                .eq('ms_uid', ms_uid) \
                .single() \
                .execute()
            return result.data
        except Exception:
            return None

    @logfire.instrument("ms_repo.search_activities_semantic")
    async def search_activities_semantic(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        version_id: int,
        limit: int = 10,
        match_threshold: float = 0.2,
        wbs_prefix: Optional[str] = None,
        owner: Optional[str] = None,
        scope_owner: Optional[str] = None,
    ) -> list[dict]:
        """Search activities using the MS schedule embedding vector.

        The primary path calls the additive Supabase RPC defined in migration 003.
        If that RPC has not been deployed yet, this falls back to a bounded text
        search so the tool can still return useful results during local cleanup.
        """
        params = {
            "query_embedding": query_embedding,
            "target_version_id": version_id,
            "match_threshold": match_threshold,
            "match_count": limit,
            "wbs_prefix": wbs_prefix,
            "owner_filter": owner,
            "scope_owner_filter": scope_owner,
        }

        try:
            result = (
                self.supabase
                .schema(self.SCHEMA)
                .rpc("match_schedule_activities", params)
                .execute()
            )
            return result.data or []
        except Exception as error:
            logfire.warning(
                "Semantic search RPC unavailable; using text fallback",
                error=str(error),
                version_id=version_id,
            )
            return await self._search_activities_text_fallback(
                query_text=query_text,
                version_id=version_id,
                limit=limit,
                wbs_prefix=wbs_prefix,
                owner=owner,
                scope_owner=scope_owner,
            )

    async def _search_activities_text_fallback(
        self,
        *,
        query_text: str,
        version_id: int,
        limit: int,
        wbs_prefix: Optional[str] = None,
        owner: Optional[str] = None,
        scope_owner: Optional[str] = None,
    ) -> list[dict]:
        """Bounded text fallback for local/dev environments without the RPC."""
        query = self._table('schedule_activities') \
            .select(
                'id, schedule_version_id, ms_uid, name, name_verbose, wbs, start, finish, '
                'duration_d, total_float_d, percent_complete, is_milestone, is_summary, '
                'owner, scope_owner, notes'
            ) \
            .eq('schedule_version_id', version_id) \
            .limit(1000)

        if wbs_prefix:
            query = query.like('wbs', f'{wbs_prefix}%')
        if owner:
            query = query.eq('owner', owner)
        if scope_owner:
            query = query.eq('scope_owner', scope_owner)

        rows = query.execute().data or []
        terms = [term for term in query_text.lower().split() if term]

        scored: list[dict] = []
        for row in rows:
            haystack = " ".join(
                str(row.get(field) or "")
                for field in ('name', 'name_verbose', 'wbs', 'owner', 'scope_owner', 'notes')
            ).lower()
            score = sum(1 for term in terms if term in haystack)
            if score <= 0:
                continue
            row = dict(row)
            row['similarity'] = score / max(len(terms), 1)
            scored.append(row)

        scored.sort(key=lambda row: row.get('similarity', 0), reverse=True)
        return scored[:limit]
    
    # =========================================================================
    # Relationship Operations
    # =========================================================================
    
    @logfire.instrument("ms_repo.get_relationships_by_version")
    async def get_relationships_by_version(
        self,
        version_id: int
    ) -> list[dict]:
        """Get all relationships for a version with predecessor/successor details."""
        return self._table('schedule_links') \
            .select('*, pred:schedule_activities!pred_id(name, ms_uid, wbs), succ:schedule_activities!succ_id(name, ms_uid, wbs)') \
            .eq('schedule_version_id', version_id) \
            .execute().data or []

    @logfire.instrument("ms_repo.get_relationship_cache_signature")
    async def get_relationship_cache_signature(self, version_id: int) -> dict:
        """Return a deterministic signature for relationship snapshot invalidation."""
        rows = self._table('schedule_links') \
            .select('id,pred_id,succ_id,rel_type,lag_d') \
            .eq('schedule_version_id', version_id) \
            .order('id') \
            .execute().data or []

        normalized = [
            {
                "id": int(row["id"]),
                "pred_id": int(row["pred_id"]),
                "succ_id": int(row["succ_id"]),
                "rel_type": str(row.get("rel_type") or "FS"),
                "lag_d": int(row.get("lag_d") or 0),
            }
            for row in rows
            if row.get("id") is not None
            and row.get("pred_id") is not None
            and row.get("succ_id") is not None
        ]
        checksum = sha1(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        return {
            "relationship_count": len(normalized),
            "max_relationship_id": max((row["id"] for row in normalized), default=0),
            "relationship_checksum": checksum,
        }
    
    @logfire.instrument("ms_repo.get_relationships_for_activity")
    async def get_relationships_for_activity(
        self,
        activity_id: int
    ) -> dict:
        """Get predecessors and successors for a specific activity."""
        preds = self._table('schedule_links') \
            .select('*, pred:schedule_activities!pred_id(name, ms_uid, wbs)') \
            .eq('succ_id', activity_id) \
            .execute().data or []
        
        succs = self._table('schedule_links') \
            .select('*, succ:schedule_activities!succ_id(name, ms_uid, wbs)') \
            .eq('pred_id', activity_id) \
            .execute().data or []
        
        return {
            'predecessors': preds,
            'successors': succs
        }
    
    # =========================================================================
    # Calendar & Constraint Operations
    # =========================================================================
    
    @logfire.instrument("ms_repo.get_calendar")
    async def get_calendar(self, version_id: int) -> dict:
        """Get calendar info including exceptions for a version."""
        calendar = self._table('project_calendars') \
            .select('*') \
            .eq('schedule_version_id', version_id) \
            .execute().data
        
        if not calendar:
            return {'calendar': None, 'exceptions': []}
        
        cal = calendar[0]
        exceptions = self._table('calendar_exceptions') \
            .select('*') \
            .eq('calendar_id', cal['id']) \
            .order('exception_date') \
            .execute().data or []
        
        return {'calendar': cal, 'exceptions': exceptions}
    
    @logfire.instrument("ms_repo.get_project_constraints")
    async def get_project_constraints(self, version_id: int) -> Optional[dict]:
        """Get project constraints for a version (dates, status date, direction)."""
        result = self._table('project_constraints') \
            .select('*') \
            .eq('schedule_version_id', version_id) \
            .execute().data
        
        if not result:
            return None
        
        constraints = result[0]
        constraints['scheduling_direction'] = 'forward' if constraints.get('schedule_from_start') else 'backward'
        return constraints
    
    @logfire.instrument("ms_repo.get_constraint_types")
    async def get_constraint_types(self) -> list[dict]:
        """Get all constraint type definitions."""
        return self._table('constraint_types') \
            .select('*') \
            .order('id') \
            .execute().data or []
    
    # =========================================================================
    # Version Management (Create/Promote)
    # =========================================================================
    
    @logfire.instrument("ms_repo.create_subversion")
    async def create_subversion(
        self,
        base_version_id: int,
        version_name: Optional[str],
        description: str,
        activities_df: "pd.DataFrame",
        relationships_df: "pd.DataFrame"
    ) -> int:
        """Create a new temporary subversion from workspace data.
        
        Args:
            base_version_id: Version this is based on
            version_name: Name for new version (auto-generated if None)
            description: Description of changes
            activities_df: DataFrame with activity data
            relationships_df: DataFrame with relationship data
            
        Returns:
            New version ID
        """
        # Get base version metadata
        base = self._table('schedule_versions') \
            .select('project_name, version_number') \
            .eq('id', base_version_id) \
            .single().execute().data
        
        # Generate version name if not provided
        now = datetime.now()
        if not version_name:
            version_name = f"draft-{now.strftime('%y%m%d')}-{now.strftime('%H%M')}"
        
        # Generate version number from timestamp
        new_version_number = int(now.strftime('%y%m%d%H%M'))
        
        # Create new version record
        new_version = self._table('schedule_versions').insert({
            'project_name': base['project_name'],
            'version_name': version_name,
            'version_number': new_version_number,
            'is_baseline': False,
            'is_current': False,
            'description': description,
            'uploaded_by': 'workspace_save'
        }).execute().data[0]
        
        new_version_id = new_version['id']
        
        # Prepare activities for batch insert
        activities_records = []
        for _, row in activities_df.iterrows():
            record = {
                'schedule_version_id': new_version_id,
                'ms_uid': row.get('ms_uid') or row.get('task_code'),
                'name': row.get('task_name') or row.get('name'),
                'name_verbose': row.get('name_verbose'),
                'wbs': row.get('wbs'),
                'start': row.get('target_start_date') or row.get('start'),
                'finish': row.get('target_end_date') or row.get('finish'),
                'percent_complete': row.get('phys_complete_pct') or row.get('percent_complete', 0),
                'is_milestone': row.get('is_milestone', False),
                'is_summary': row.get('is_summary', False),
                'actual_start': row.get('act_start_date') or row.get('actual_start'),
                'actual_finish': row.get('act_end_date') or row.get('actual_finish'),
                'constraint_type': row.get('constraint_type'),
                'constraint_date': row.get('constraint_date'),
                'owner': row.get('owner'),
                'scope_owner': row.get('scope_owner'),
                'notes': row.get('notes'),
            }
            
            # Handle duration conversion (hours to days if needed)
            if 'target_drtn_hr_cnt' in row and row.get('target_drtn_hr_cnt'):
                record['duration_d'] = row['target_drtn_hr_cnt'] / 8
            elif 'duration_d' in row:
                record['duration_d'] = row.get('duration_d')
            
            # Handle float
            if 'total_float_days' in row:
                record['total_float_d'] = row.get('total_float_days')
            elif 'total_float_d' in row:
                record['total_float_d'] = row.get('total_float_d')
            
            activities_records.append(record)
        
        # Batch insert activities
        if activities_records:
            self._table('schedule_activities').insert(activities_records).execute()
        
        # Get inserted activity IDs for relationship mapping
        inserted = self._table('schedule_activities') \
            .select('id, ms_uid') \
            .eq('schedule_version_id', new_version_id) \
            .execute().data or []
        
        uid_to_id = {a['ms_uid']: a['id'] for a in inserted}
        
        # Prepare relationships
        rel_records = []
        for _, row in relationships_df.iterrows():
            pred_uid = row.get('pred_ms_uid') or row.get('pred_task_code')
            succ_uid = row.get('succ_ms_uid') or row.get('succ_task_code')
            
            if pred_uid in uid_to_id and succ_uid in uid_to_id:
                rel_type = row.get('pred_type', 'FS')
                if rel_type.startswith('PR_'):
                    rel_type = rel_type[3:]  # Remove PR_ prefix
                
                lag = row.get('lag_hr_cnt', 0)
                if lag:
                    lag = int(lag / 8)  # Convert hours to days
                else:
                    lag = row.get('lag_d', 0)
                
                rel_records.append({
                    'schedule_version_id': new_version_id,
                    'pred_id': uid_to_id[pred_uid],
                    'succ_id': uid_to_id[succ_uid],
                    'rel_type': rel_type,
                    'lag_d': lag,
                })
        
        if rel_records:
            self._table('schedule_links').insert(rel_records).execute()
        
        logfire.info(
            "Created subversion",
            version_id=new_version_id,
            version_name=version_name,
            activities_count=len(activities_records),
            relationships_count=len(rel_records)
        )
        
        return new_version_id
    
    @logfire.instrument("ms_repo.promote_to_current")
    async def promote_to_current(
        self, 
        version_id: int,
        expected_current_version_id: Optional[int] = None
    ) -> dict:
        """Set a version as current with optimistic locking.
        
        Args:
            version_id: Version to promote
            expected_current_version_id: Expected current version (for optimistic lock)
            
        Returns:
            Dict with success status and diff summary
            
        Raises:
            ValueError: If optimistic lock fails (current changed)
        """
        # Get version info
        version = self._table('schedule_versions') \
            .select('project_name') \
            .eq('id', version_id) \
            .single().execute().data
        
        project_name = version['project_name']
        
        # Check optimistic lock
        current = self._table('schedule_versions') \
            .select('id') \
            .eq('project_name', project_name) \
            .eq('is_current', True) \
            .execute().data
        
        if expected_current_version_id and current:
            if current[0]['id'] != expected_current_version_id:
                raise ValueError(
                    f"Optimistic lock failed: current version changed from "
                    f"{expected_current_version_id} to {current[0]['id']}. "
                    f"Please reload and retry."
                )
        
        old_current_id = current[0]['id'] if current else None
        
        # Generate diff before promoting
        diff = None
        if old_current_id:
            diff = await self._generate_version_diff(old_current_id, version_id)
        
        # Unset all current flags for this project
        self._table('schedule_versions') \
            .update({'is_current': False}) \
            .eq('project_name', project_name) \
            .execute()
        
        # Set new current
        self._table('schedule_versions') \
            .update({'is_current': True}) \
            .eq('id', version_id) \
            .execute()
        
        logfire.info(
            "Promoted version to current",
            version_id=version_id,
            previous_current_id=old_current_id
        )
        
        return {
            'success': True,
            'promoted_version_id': version_id,
            'previous_current_id': old_current_id,
            'diff': diff
        }
    
    async def _generate_version_diff(
        self, 
        old_version_id: int, 
        new_version_id: int
    ) -> dict:
        """Generate diff summary between two versions."""
        old_activities = self._table('schedule_activities') \
            .select('ms_uid, name, start, finish, duration_d, percent_complete') \
            .eq('schedule_version_id', old_version_id) \
            .eq('is_summary', False) \
            .execute().data or []
        
        new_activities = self._table('schedule_activities') \
            .select('ms_uid, name, start, finish, duration_d, percent_complete') \
            .eq('schedule_version_id', new_version_id) \
            .eq('is_summary', False) \
            .execute().data or []
        
        old_by_uid = {a['ms_uid']: a for a in old_activities}
        new_by_uid = {a['ms_uid']: a for a in new_activities}
        
        added = [new_by_uid[uid] for uid in set(new_by_uid) - set(old_by_uid)]
        removed = [old_by_uid[uid] for uid in set(old_by_uid) - set(new_by_uid)]
        
        modified = []
        for uid in set(old_by_uid) & set(new_by_uid):
            old = old_by_uid[uid]
            new = new_by_uid[uid]
            changes = {}
            
            for field in ['start', 'finish', 'duration_d', 'percent_complete']:
                if old.get(field) != new.get(field):
                    changes[field] = {'old': old.get(field), 'new': new.get(field)}
            
            if changes:
                modified.append({
                    'ms_uid': uid,
                    'name': new['name'],
                    'changes': changes
                })
        
        return {
            'added_count': len(added),
            'removed_count': len(removed),
            'modified_count': len(modified),
            'added': added[:10],
            'removed': removed[:10],
            'modified': modified[:20]
        }
