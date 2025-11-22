from backend.models.io import ActivityCreateRequest, RelationshipCreateRequest, ProgressUpdateRequest, ActivityDetailsRequest, ActivityStatusUpdateRequest, ProjectCreateRequest, RelationshipDeleteRequest, RelationshipUpdateRequest
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
