from backend.models.io import ActivityCreateRequest, RelationshipCreateRequest, ProgressUpdateRequest, ActivityDetailsRequest, ActivityStatusUpdateRequest
from backend.models.domain import P6Activity, P6Relationship
from backend.utils.db import get_db_connection
from backend.utils.safe_db import SafeP6Transaction
from backend.repositories.p6_repository import P6Repository
from datetime import datetime

class SchedulingService:
    def __init__(self):
        self.repo = P6Repository()

    def get_activity_details(self, req: ActivityDetailsRequest) -> dict:
        # Read operations can still use the direct connection for speed, 
        # as they don't risk corruption.
        with get_db_connection() as conn:
            task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
            if not task_id:
                raise ValueError(f"Activity {req.task_code} not found")
            
            details = self.repo.get_activity_details(conn, task_id)
            if not details:
                raise ValueError(f"Details for activity {req.task_code} not found")
            return details

    def update_activity_status(self, req: ActivityStatusUpdateRequest) -> str:
        # Write operations use SafeP6Transaction
        with SafeP6Transaction() as conn:
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
            conn.commit()
            return f"Updated {req.task_code} to {req.new_status}"

    def create_activity(self, req: ActivityCreateRequest) -> int:
        with SafeP6Transaction() as conn:
            # Check if WBS exists
            if not self.repo.check_wbs_exists(conn, req.wbs_id, req.proj_id):
                raise ValueError(f"WBS {req.wbs_id} does not exist in Project {req.proj_id}")

            # Map request to domain model
            # Defaulting some P6 fields
            now = datetime.now()
            task = P6Activity(
                proj_id=req.proj_id,
                wbs_id=req.wbs_id,
                clndr_id=req.clndr_id or 1, # Default calendar if not provided
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

    def create_relationship(self, req: RelationshipCreateRequest) -> int:
        with SafeP6Transaction() as conn:
            # Get Task IDs
            pred_id = self.repo.get_task_id_by_code(conn, req.pred_task_code, req.proj_id)
            succ_id = self.repo.get_task_id_by_code(conn, req.succ_task_code, req.proj_id)
            
            if not pred_id:
                raise ValueError(f"Predecessor {req.pred_task_code} not found")
            if not succ_id:
                raise ValueError(f"Successor {req.succ_task_code} not found")
                
            rel = P6Relationship(
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

    def update_progress(self, req: ProgressUpdateRequest) -> str:
        with SafeP6Transaction() as conn:
            task_id = self.repo.get_task_id_by_code(conn, req.task_code, req.proj_id)
            if not task_id:
                raise ValueError(f"Activity {req.task_code} not found")
                
            # Determine status based on inputs
            status_code = "TK_Active"
            if req.phys_complete_pct == 100:
                status_code = "TK_Complete"
            elif req.phys_complete_pct == 0 and not req.actual_start:
                status_code = "TK_NotStart"
                
            self.repo.update_task_progress(
                conn, 
                task_id, 
                req.phys_complete_pct, 
                req.actual_start, 
                req.actual_finish,
                status_code
            )
            conn.commit()
            return f"Updated progress for {req.task_code}"
