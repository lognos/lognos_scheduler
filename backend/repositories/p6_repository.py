import sqlite3
from datetime import datetime
from typing import Optional
from backend.models.domain import P6Activity, P6Relationship

class P6Repository:
    def get_next_key(self, conn: sqlite3.Connection, table_name: str) -> int:
        """
        Gets the next available primary key for a table from NEXTKEY.
        Updates the NEXTKEY table atomically.
        """
        cursor = conn.cursor()
        # Lock the row (SQLite doesn't support row locking like Oracle, but transaction isolation helps)
        # In SQLite, a write transaction locks the database.
        
        cursor.execute("SELECT KEY_SEQ_NUM FROM NEXTKEY WHERE KEY_NAME = ?", (table_name,))
        row = cursor.fetchone()
        
        if not row:
            # If key doesn't exist, initialize it (fallback, though P6 DB should have it)
            # Starting high to avoid conflicts if DB is messy
            next_key = 1000
            cursor.execute("INSERT INTO NEXTKEY (KEY_NAME, KEY_SEQ_NUM) VALUES (?, ?)", (table_name, next_key + 1))
        else:
            next_key = row[0]
            cursor.execute("UPDATE NEXTKEY SET KEY_SEQ_NUM = ? WHERE KEY_NAME = ?", (next_key + 1, table_name))
            
        return next_key

    def get_task_id_by_code(self, conn: sqlite3.Connection, task_code: str, proj_id: int) -> Optional[int]:
        cursor = conn.cursor()
        cursor.execute("SELECT TASK_ID FROM TASK WHERE TASK_CODE = ? AND PROJ_ID = ?", (task_code, proj_id))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_activity_details(self, conn: sqlite3.Connection, task_id: int) -> Optional[dict]:
        cursor = conn.cursor()
        sql = """
            SELECT STATUS_CODE, PHYS_COMPLETE_PCT, ACT_START_DATE, ACT_END_DATE 
            FROM TASK WHERE TASK_ID = ?
        """
        cursor.execute(sql, (task_id,))
        row = cursor.fetchone()
        if row:
            return {
                "status_code": row[0],
                "phys_complete_pct": row[1],
                "act_start_date": row[2],
                "act_end_date": row[3]
            }
        return None

    def update_activity_status(self, conn: sqlite3.Connection, task_id: int, 
                             status_code: str, 
                             phys_complete_pct: float,
                             act_start_date: Optional[datetime],
                             act_end_date: Optional[datetime]) -> None:
        cursor = conn.cursor()
        
        updates = [
            "STATUS_CODE = ?",
            "PHYS_COMPLETE_PCT = ?",
            "ACT_START_DATE = ?",
            "ACT_END_DATE = ?",
            "UPDATE_DATE = ?"
        ]
        params = [status_code, phys_complete_pct, act_start_date, act_end_date, datetime.now()]
        
        # If complete, remaining duration should be 0
        if status_code == "TK_Complete":
            updates.append("REMAIN_DRTN_HR_CNT = 0")
            
        params.append(task_id)
        
        sql = f"UPDATE TASK SET {', '.join(updates)} WHERE TASK_ID = ?"
        cursor.execute(sql, params)

    def create_task(self, conn: sqlite3.Connection, task: P6Activity) -> int:
        cursor = conn.cursor()
        
        # Get Next Key
        task_id = self.get_next_key(conn, "TASK")
        
        # Insert
        sql = """
            INSERT INTO TASK (
                TASK_ID, PROJ_ID, WBS_ID, CLNDR_ID, TASK_CODE, TASK_NAME, 
                STATUS_CODE, TASK_TYPE, DURATION_TYPE, 
                TARGET_DRTN_HR_CNT, REMAIN_DRTN_HR_CNT, PHYS_COMPLETE_PCT,
                CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, (
            task_id, task.proj_id, task.wbs_id, task.clndr_id, task.task_code, task.task_name,
            task.status_code, task.task_type, task.duration_type,
            task.target_drtn_hr_cnt, task.remain_drtn_hr_cnt, task.phys_complete_pct,
            task.create_date, task.update_date, task.create_user, task.update_user
        ))
        return task_id

    def create_relationship(self, conn: sqlite3.Connection, rel: P6Relationship) -> int:
        cursor = conn.cursor()
        
        rel_id = self.get_next_key(conn, "TASKPRED")
        
        sql = """
            INSERT INTO TASKPRED (
                TASK_PRED_ID, TASK_ID, PRED_TASK_ID, PROJ_ID, PRED_PROJ_ID,
                PRED_TYPE, LAG_HR_CNT, 
                CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        cursor.execute(sql, (
            rel_id, rel.task_id, rel.pred_task_id, rel.proj_id, rel.pred_proj_id,
            rel.pred_type, rel.lag_hr_cnt,
            now, now, "Agent", "Agent"
        ))
        return rel_id

    def update_task_progress(self, conn: sqlite3.Connection, task_id: int, 
                           phys_complete_pct: float, 
                           actual_start: Optional[datetime], 
                           actual_finish: Optional[datetime],
                           status_code: str) -> None:
        cursor = conn.cursor()
        
        updates = ["PHYS_COMPLETE_PCT = ?", "STATUS_CODE = ?", "UPDATE_DATE = ?"]
        params = [phys_complete_pct, status_code, datetime.now()]
        
        if actual_start:
            updates.append("ACT_START_DATE = ?")
            params.append(actual_start)
            
        if actual_finish:
            updates.append("ACT_END_DATE = ?")
            params.append(actual_finish)
            
        # If complete, remaining duration should be 0
        if status_code == "TK_Complete":
            updates.append("REMAIN_DRTN_HR_CNT = 0")
            
        params.append(task_id)
        
        sql = f"UPDATE TASK SET {', '.join(updates)} WHERE TASK_ID = ?"
        cursor.execute(sql, params)

    def check_wbs_exists(self, conn: sqlite3.Connection, wbs_id: int, proj_id: int) -> bool:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM PROJWBS WHERE WBS_ID = ? AND PROJ_ID = ?", (wbs_id, proj_id))
        return cursor.fetchone() is not None

    def check_project_exists(self, conn: sqlite3.Connection, proj_id: int) -> bool:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM PROJECT WHERE PROJ_ID = ?", (proj_id,))
        return cursor.fetchone() is not None
