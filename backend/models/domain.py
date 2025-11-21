from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class P6Activity(BaseModel):
    task_id: int
    proj_id: int
    wbs_id: int
    clndr_id: Optional[int]
    task_code: str
    task_name: str
    status_code: str
    task_type: str
    duration_type: str
    target_drtn_hr_cnt: float
    remain_drtn_hr_cnt: float
    phys_complete_pct: float
    create_date: datetime
    update_date: datetime
    create_user: str
    update_user: str

class P6Relationship(BaseModel):
    task_pred_id: int
    task_id: int
    pred_task_id: int
    proj_id: int
    pred_proj_id: int
    pred_type: str
    lag_hr_cnt: float
