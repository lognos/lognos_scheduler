from backend.models.io import (
    ActivityCreateRequest, 
    RelationshipCreateRequest, 
    ProgressUpdateRequest, 
    ActivityDetailsRequest, 
    ActivityStatusUpdateRequest, 
    ProjectCreateRequest, 
    RelationshipDeleteRequest, 
    RelationshipUpdateRequest, 
    ListProjectsRequest,
    ListActivityCodesRequest,
    AssignActivityCodeRequest,
    RemoveActivityCodeRequest,
    BulkAssignActivityCodeRequest,
    GetActivityCurrentCodesRequest,
)
from backend.models.domain import P6Activity, P6Relationship
from backend.utils.db import get_db_connection
from backend.utils.safe_db import SafeP6Transaction
from backend.repositories.p6_repository import P6Repository
from datetime import datetime

class SchedulingService:
    def __init__(self):
        self.repo = P6Repository()

    def delete_relationship(self, req: RelationshipDeleteRequest, conn=None) -> str:
        if conn:
            return self._delete_relationship_impl(conn, req)
        with SafeP6Transaction() as safe_conn:
            result = self._delete_relationship_impl(safe_conn, req)
            safe_conn.commit()
            return result

    def _delete_relationship_impl(self, conn, req: RelationshipDeleteRequest) -> str:
        pred_id = self.repo.get_task_id_by_code(conn, req.pred_task_code, req.proj_id)
        succ_id = self.repo.get_task_id_by_code(conn, req.succ_task_code, req.proj_id)
        
        if not pred_id:
            raise ValueError(f"Predecessor {req.pred_task_code} not found")
        if not succ_id:
            raise ValueError(f"Successor {req.succ_task_code} not found")
            
        rel_id = self.repo.get_relationship_id(conn, pred_id, succ_id)
        if not rel_id:
            raise ValueError(f"Relationship {req.pred_task_code} -> {req.succ_task_code} does not exist")
            
        self.repo.delete_relationship(conn, rel_id)
        conn.commit()
        return f"Deleted relationship {req.pred_task_code} -> {req.succ_task_code}"

    def update_relationship(self, req: RelationshipUpdateRequest, conn=None) -> str:
        if conn:
            return self._update_relationship_impl(conn, req)
        with SafeP6Transaction() as safe_conn:
            result = self._update_relationship_impl(safe_conn, req)
            safe_conn.commit()
            return result

    def _update_relationship_impl(self, conn, req: RelationshipUpdateRequest) -> str:
        pred_id = self.repo.get_task_id_by_code(conn, req.pred_task_code, req.proj_id)
        succ_id = self.repo.get_task_id_by_code(conn, req.succ_task_code, req.proj_id)
        
        if not pred_id:
            raise ValueError(f"Predecessor {req.pred_task_code} not found")
        if not succ_id:
            raise ValueError(f"Successor {req.succ_task_code} not found")
            
        rel_id = self.repo.get_relationship_id(conn, pred_id, succ_id)
        if not rel_id:
            raise ValueError(f"Relationship {req.pred_task_code} -> {req.succ_task_code} does not exist")
            
        self.repo.update_relationship(conn, rel_id, req.new_lag, req.new_type)
        conn.commit()
        return f"Updated relationship {req.pred_task_code} -> {req.succ_task_code}"

    def get_activity_details(self, req: ActivityDetailsRequest, conn=None) -> dict:
        # If a connection is provided (e.g. from a transaction), use it to ensure we see uncommitted changes.
        if conn:
            return self._get_activity_details_impl(conn, req)

        # Otherwise, use a direct connection for speed (read-only safe)
        with get_db_connection() as direct_conn:
            return self._get_activity_details_impl(direct_conn, req)

    def _get_activity_details_impl(self, conn, req: ActivityDetailsRequest) -> dict:
        task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
        if not task_id:
            raise ValueError(f"Activity {req.task_code} not found")
        
        details = self.repo.get_activity_details(conn, task_id)
        if not details:
            raise ValueError(f"Details for activity {req.task_code} not found")
        return details

    def update_activity_status(self, req: ActivityStatusUpdateRequest, conn=None) -> str:
        if conn:
            return self._update_activity_status_impl(conn, req)
        
        # Write operations use SafeP6Transaction
        with SafeP6Transaction() as safe_conn:
            result = self._update_activity_status_impl(safe_conn, req)
            safe_conn.commit()
            return result

    def _update_activity_status_impl(self, conn, req: ActivityStatusUpdateRequest) -> str:
        task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
        if not task_id:
            raise ValueError(f"Activity {req.task_code} not found")

        # Logic Flow
        status_code = ""
        phys_complete_pct = 0.0
        act_start = None
        act_end = None

        if req.new_status == "In Progress":
            if not req.actual_start_date:
                raise ValueError("Actual Start Date is required for 'In Progress' status")
            status_code = "TK_Active"
            act_start = req.actual_start_date
            act_end = None
            if req.phys_complete_pct is None:
                current = self.repo.get_activity_details(conn, task_id)
                phys_complete_pct = current['phys_complete_pct']
            else:
                phys_complete_pct = req.phys_complete_pct
            
        elif req.new_status == "Completed":
            if not req.actual_start_date:
                    # Try to get from DB if already started
                    current = self.repo.get_activity_details(conn, task_id)
                    if current['act_start_date']:
                        act_start = current['act_start_date']
                    else:
                        raise ValueError("Actual Start Date is required (or must be already set) for 'Completed' status")
            else:
                act_start = req.actual_start_date

            if not req.actual_finish_date:
                raise ValueError("Actual Finish Date is required for 'Completed' status")
            
            status_code = "TK_Complete"
            act_end = req.actual_finish_date
            phys_complete_pct = 100.0

        elif req.new_status == "Not Started":
            status_code = "TK_NotStart"
            act_start = None
            act_end = None
            phys_complete_pct = 0.0

        self.repo.update_activity_status(conn, task_id, status_code, phys_complete_pct, act_start, act_end)
        # We commit here to ensure the connection sees the changes, 
        # but the file swap only happens when SafeP6Transaction exits.
        conn.commit()
        return f"Updated {req.task_code} to {req.new_status}"

    def create_activity(self, req: ActivityCreateRequest, conn=None) -> int:
        if conn:
            return self._create_activity_impl(conn, req)
            
        with SafeP6Transaction() as safe_conn:
            result = self._create_activity_impl(safe_conn, req)
            safe_conn.commit()
            return result

    def _create_activity_impl(self, conn, req: ActivityCreateRequest) -> int:
        # Check if WBS exists
        if not self.repo.check_wbs_exists(conn, req.wbs_id, req.proj_id):
            raise ValueError(f"WBS {req.wbs_id} does not exist in Project {req.proj_id}")

        # Fetch default calendar from Project if not provided
        clndr_id = req.clndr_id
        if not clndr_id:
            clndr_id = 1 # Fallback
            cursor = conn.cursor()
            cursor.execute("SELECT CLNDR_ID FROM PROJECT WHERE PROJ_ID = ?", (req.proj_id,))
            row = cursor.fetchone()
            if row and row[0]:
                clndr_id = row[0]

        # Map request to domain model
        # Defaulting some P6 fields
        now = datetime.now()
        task = P6Activity(
            task_id=0, # Dummy ID, will be generated by repo
            proj_id=req.proj_id,
            wbs_id=req.wbs_id,
            clndr_id=clndr_id, 
            task_code=req.task_code,
            task_name=req.task_name,
            status_code="TK_NotStart",
            task_type="TT_Task",
            duration_type="DT_FixDrtn",
            target_drtn_hr_cnt=float(req.planned_duration),
            remain_drtn_hr_cnt=float(req.planned_duration),
            phys_complete_pct=0.0,
            create_date=now,
            update_date=now,
            create_user="Agent",
            update_user="Agent"
        )
        
        task_id = self.repo.create_task(conn, task)
        conn.commit()
        return task_id

    def create_relationship(self, req: RelationshipCreateRequest, conn=None) -> int:
        if conn:
            return self._create_relationship_impl(conn, req)
            
        with SafeP6Transaction() as safe_conn:
            result = self._create_relationship_impl(safe_conn, req)
            safe_conn.commit()
            return result

    def create_project(self, req: ProjectCreateRequest, conn=None) -> tuple[int, int]:
        if conn:
            return self.repo.create_project(conn, req.project_short_name, req.project_name, req.planned_start_date)
            
        with SafeP6Transaction() as safe_conn:
            proj_id, wbs_id = self.repo.create_project(safe_conn, req.project_short_name, req.project_name, req.planned_start_date)
            safe_conn.commit()
            return proj_id, wbs_id

    def _create_relationship_impl(self, conn, req: RelationshipCreateRequest) -> int:
        # Get Task IDs
        pred_id = self.repo.get_task_id_by_code(conn, req.pred_task_code, req.proj_id)
        succ_id = self.repo.get_task_id_by_code(conn, req.succ_task_code, req.proj_id)
        
        if not pred_id:
            raise ValueError(f"Predecessor {req.pred_task_code} not found")
        if not succ_id:
            raise ValueError(f"Successor {req.succ_task_code} not found")
            
        rel = P6Relationship(
            task_pred_id=0, # Dummy ID
            task_id=succ_id,
            pred_task_id=pred_id,
            proj_id=req.proj_id,
            pred_proj_id=req.proj_id, # Assuming same project for now
            pred_type=req.pred_type,
            lag_hr_cnt=float(req.lag)
        )
        
        rel_id = self.repo.create_relationship(conn, rel)
        conn.commit()
        return rel_id

    def update_progress(self, req: ProgressUpdateRequest, conn=None) -> str:
        if conn:
            return self._update_progress_impl(conn, req)
            
        with SafeP6Transaction() as safe_conn:
            result = self._update_progress_impl(safe_conn, req)
            safe_conn.commit()
            return result

    def _update_progress_impl(self, conn, req: ProgressUpdateRequest) -> str:
        task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
        if not task_id:
            raise ValueError(f"Activity {req.task_code} not found")
            
        # Determine status based on inputs
        status_code = "TK_Active"
        if req.phys_complete_pct == 100:
            status_code = "TK_Complete"
        elif req.phys_complete_pct == 0 and not req.actual_start:
            status_code = "TK_NotStart"
            
        # Validation: If status is Active or Complete, Actual Start is required.
        # If not provided in request, check if it exists in DB.
        actual_start = req.actual_start
        if status_code in ["TK_Active", "TK_Complete"] and not actual_start:
            current = self.repo.get_activity_details(conn, task_id)
            if current and current['act_start_date']:
                # Already started, keep existing date (repo handles None by not updating)
                pass 
            else:
                # Not started yet, and no date provided. Default to NOW or raise error?
                # P6 requires a date. Let's default to today if missing, but ideally agent should ask.
                # For now, let's default to today to avoid invalid state, but log it.
                actual_start = datetime.now()
        
        self.repo.update_task_progress(
            conn, 
            task_id, 
            req.phys_complete_pct, 
            actual_start, 
            req.actual_finish,
            status_code
        )
        conn.commit()
        return f"Updated progress for {req.task_code}"

    def list_projects(self, req: ListProjectsRequest, conn=None) -> list[dict]:
        """Lists all projects with summary information including descriptions."""
        if conn:
            return self._list_projects_impl(conn, req)
        
        # Read-only operation, use direct connection
        with get_db_connection() as direct_conn:
            return self._list_projects_impl(direct_conn, req)
    
    def _list_projects_impl(self, conn, req: ListProjectsRequest) -> list[dict]:
        """Implementation for list_projects."""
        projects = self.repo.list_projects(conn, include_eps=req.include_eps_nodes)
        
        # Format dates as ISO strings for readability
        for proj in projects:
            for date_field in ['PLAN_START_DATE', 'PLAN_END_DATE', 'LAST_RECALC_DATE', 'ADD_DATE']:
                if proj.get(date_field):
                    # Parse and format if it's a string, otherwise format datetime
                    val = proj[date_field]
                    if isinstance(val, str):
                        # Already a string, try to parse and reformat for consistency
                        try:
                            dt = datetime.fromisoformat(val.replace(' ', 'T'))
                            proj[date_field] = dt.strftime('%Y-%m-%d')
                        except ValueError:
                            pass  # Keep original if parsing fails
                    else:
                        proj[date_field] = val.strftime('%Y-%m-%d') if val else None
        
        return projects

    # ─────────────────────────────────────────────────────────────────────────────
    # Activity Code Methods
    # ─────────────────────────────────────────────────────────────────────────────

    def list_activity_codes(self, req: ListActivityCodesRequest, conn=None) -> list[dict]:
        """Lists available activity code types and their values."""
        if conn:
            return self._list_activity_codes_impl(conn, req)
        
        with get_db_connection() as direct_conn:
            return self._list_activity_codes_impl(direct_conn, req)
    
    def _list_activity_codes_impl(self, conn, req: ListActivityCodesRequest) -> list[dict]:
        """Implementation for list_activity_codes."""
        if req.include_project_codes and not req.proj_id:
            raise ValueError("proj_id is required when include_project_codes=True")
        
        return self.repo.list_activity_codes(
            conn, 
            include_project_codes=req.include_project_codes,
            proj_id=req.proj_id
        )

    def get_activity_current_codes(
        self, 
        req: GetActivityCurrentCodesRequest, 
        conn=None
    ) -> dict[str, list[dict]]:
        """
        Gets current activity code assignments for multiple activities.
        
        Returns:
            Dict mapping task_code -> list of current assignments
        """
        if conn:
            return self._get_activity_current_codes_impl(conn, req)
        
        with get_db_connection() as direct_conn:
            return self._get_activity_current_codes_impl(direct_conn, req)
    
    def _get_activity_current_codes_impl(
        self, 
        conn, 
        req: GetActivityCurrentCodesRequest
    ) -> dict[str, list[dict]]:
        """Implementation for get_activity_current_codes."""
        # Get task IDs for the codes
        tasks = self.repo.get_tasks_by_codes(conn, req.task_codes, req.proj_id)
        
        # Build mapping
        result: dict[str, list[dict]] = {}
        for task in tasks:
            codes = self.repo.get_task_activity_codes(conn, task['task_id'])
            result[task['task_code']] = codes
        
        # Include not-found tasks with empty list
        for task_code in req.task_codes:
            if task_code not in result:
                result[task_code] = []  # Task not found or no codes
        
        return result

    def assign_activity_codes(
        self, 
        req: AssignActivityCodeRequest, 
        conn=None
    ) -> dict:
        """
        Assigns activity codes to a single activity.
        
        Returns:
            Dict with result info including any replaced codes
        """
        if conn:
            return self._assign_activity_codes_impl(conn, req)
        
        with SafeP6Transaction() as safe_conn:
            result = self._assign_activity_codes_impl(safe_conn, req)
            safe_conn.commit()
            return result
    
    def _assign_activity_codes_impl(self, conn, req: AssignActivityCodeRequest) -> dict:
        """Implementation for assign_activity_codes."""
        # Get task ID
        task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
        if not task_id:
            raise ValueError(f"Activity '{req.task_code}' not found in project {req.proj_id}")
        
        assigned = []
        replaced = []
        errors = []
        
        for code_type_name, code_value in req.code_assignments.items():
            # Resolve code type
            code_type = self.repo.get_activity_code_type_by_name(
                conn, 
                code_type_name,
                req.proj_id
            )
            if not code_type:
                errors.append(f"Code type '{code_type_name}' not found")
                continue
            
            # Resolve code value
            code_value_record = self.repo.get_activity_code_by_short_name(
                conn,
                code_type['actv_code_type_id'],
                code_value
            )
            if not code_value_record:
                errors.append(
                    f"Code value '{code_value}' not found in type '{code_type_name}'"
                )
                continue
            
            # Check for existing assignment
            existing = self.repo.check_activity_code_exists(
                conn,
                task_id,
                code_type['actv_code_type_id']
            )
            
            if existing and not req.replace_existing:
                errors.append(
                    f"Activity already has code '{existing['short_name']}' for type "
                    f"'{code_type_name}'. Set replace_existing=True to replace."
                )
                continue
            
            if existing:
                replaced.append({
                    'code_type': code_type_name,
                    'old_value': existing['short_name'],
                    'new_value': code_value
                })
            
            # Assign the code
            self.repo.assign_activity_code(
                conn,
                task_id,
                req.proj_id,
                code_type['actv_code_type_id'],
                code_value_record['actv_code_id']
            )
            assigned.append({
                'code_type': code_type_name,
                'code_value': code_value
            })
        
        conn.commit()
        
        return {
            'task_code': req.task_code,
            'assigned': assigned,
            'replaced': replaced,
            'errors': errors
        }

    def remove_activity_codes(
        self, 
        req: RemoveActivityCodeRequest, 
        conn=None
    ) -> dict:
        """
        Removes activity code assignments from an activity.
        
        Returns:
            Dict with result info
        """
        if conn:
            return self._remove_activity_codes_impl(conn, req)
        
        with SafeP6Transaction() as safe_conn:
            result = self._remove_activity_codes_impl(safe_conn, req)
            safe_conn.commit()
            return result
    
    def _remove_activity_codes_impl(self, conn, req: RemoveActivityCodeRequest) -> dict:
        """Implementation for remove_activity_codes."""
        # Get task ID
        task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
        if not task_id:
            raise ValueError(f"Activity '{req.task_code}' not found in project {req.proj_id}")
        
        removed = []
        not_found = []
        
        for code_type_name in req.code_type_names:
            # Resolve code type
            code_type = self.repo.get_activity_code_type_by_name(
                conn, 
                code_type_name,
                req.proj_id
            )
            if not code_type:
                not_found.append(f"Code type '{code_type_name}' not found")
                continue
            
            # Check current assignment
            existing = self.repo.check_activity_code_exists(
                conn,
                task_id,
                code_type['actv_code_type_id']
            )
            
            if not existing:
                not_found.append(f"No '{code_type_name}' code assigned to activity")
                continue
            
            # Remove the code
            self.repo.remove_activity_code(
                conn,
                task_id,
                code_type['actv_code_type_id']
            )
            removed.append({
                'code_type': code_type_name,
                'removed_value': existing['short_name']
            })
        
        conn.commit()
        
        return {
            'task_code': req.task_code,
            'removed': removed,
            'not_found': not_found
        }

    def bulk_assign_activity_codes(
        self, 
        req: BulkAssignActivityCodeRequest, 
        conn=None
    ) -> dict:
        """
        Assigns activity codes to multiple activities.
        
        Returns:
            Dict with result info for each activity
        """
        if conn:
            return self._bulk_assign_activity_codes_impl(conn, req)
        
        with SafeP6Transaction() as safe_conn:
            result = self._bulk_assign_activity_codes_impl(safe_conn, req)
            safe_conn.commit()
            return result
    
    def _bulk_assign_activity_codes_impl(
        self, 
        conn, 
        req: BulkAssignActivityCodeRequest
    ) -> dict:
        """Implementation for bulk_assign_activity_codes."""
        # Validate input - must have either task_codes or wbs_id, not both
        if req.task_codes and req.wbs_id:
            raise ValueError("Provide either task_codes OR wbs_id, not both")
        if not req.task_codes and not req.wbs_id:
            raise ValueError("Must provide either task_codes or wbs_id")
        
        # Get target tasks
        if req.task_codes:
            tasks = self.repo.get_tasks_by_codes(conn, req.task_codes, req.proj_id)
            if not tasks:
                raise ValueError("No matching activities found for the provided task codes")
        else:
            tasks = self.repo.get_tasks_by_wbs(conn, req.wbs_id, req.proj_id)
            if not tasks:
                raise ValueError(f"No activities found under WBS {req.wbs_id}")
        
        # Pre-resolve code types and values (do once for efficiency)
        resolved_codes = []
        resolution_errors = []
        
        for code_type_name, code_value in req.code_assignments.items():
            code_type = self.repo.get_activity_code_type_by_name(
                conn, 
                code_type_name,
                req.proj_id
            )
            if not code_type:
                resolution_errors.append(f"Code type '{code_type_name}' not found")
                continue
            
            code_value_record = self.repo.get_activity_code_by_short_name(
                conn,
                code_type['actv_code_type_id'],
                code_value
            )
            if not code_value_record:
                resolution_errors.append(
                    f"Code value '{code_value}' not found in type '{code_type_name}'"
                )
                continue
            
            resolved_codes.append({
                'code_type_name': code_type_name,
                'code_type_id': code_type['actv_code_type_id'],
                'code_value': code_value,
                'code_id': code_value_record['actv_code_id']
            })
        
        if resolution_errors:
            # Return early with errors if any codes couldn't be resolved
            return {
                'success': False,
                'resolution_errors': resolution_errors,
                'task_results': []
            }
        
        # Apply to each task
        task_results = []
        
        for task in tasks:
            task_result = {
                'task_code': task['task_code'],
                'task_name': task['task_name'],
                'assigned': [],
                'replaced': []
            }
            
            for code in resolved_codes:
                # Check for existing assignment
                existing = self.repo.check_activity_code_exists(
                    conn,
                    task['task_id'],
                    code['code_type_id']
                )
                
                if existing and not req.replace_existing:
                    # Skip this task/code combo
                    continue
                
                if existing:
                    task_result['replaced'].append({
                        'code_type': code['code_type_name'],
                        'old_value': existing['short_name'],
                        'new_value': code['code_value']
                    })
                
                # Assign the code
                self.repo.assign_activity_code(
                    conn,
                    task['task_id'],
                    req.proj_id,
                    code['code_type_id'],
                    code['code_id']
                )
                task_result['assigned'].append({
                    'code_type': code['code_type_name'],
                    'code_value': code['code_value']
                })
            
            task_results.append(task_result)
        
        conn.commit()
        
        return {
            'success': True,
            'total_tasks': len(tasks),
            'task_results': task_results
        }
