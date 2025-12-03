import sqlite3
import uuid
import base64
import re
from html.parser import HTMLParser
from datetime import datetime
from typing import Optional
from backend.models.domain import P6Activity, P6Relationship


class _HTMLTextExtractor(HTMLParser):
    """Extracts plain text from HTML content."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
    
    def handle_data(self, data):
        text = data.strip()
        if text:
            self.text_parts.append(text)
    
    def get_text(self) -> str:
        return ' '.join(self.text_parts)


def extract_text_from_html(html_content: bytes | str | None) -> str | None:
    """Extract plain text from P6 notebook HTML content."""
    if not html_content:
        return None
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='replace')
    try:
        parser = _HTMLTextExtractor()
        parser.feed(html_content)
        result = parser.get_text()
        return result if result else None
    except Exception:
        return None

class P6Repository:
    def _generate_guid(self) -> str:
        """Generates a P6-compatible 22-character GUID."""
        return base64.b64encode(uuid.uuid4().bytes).decode('utf-8').rstrip('=')

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
            SELECT STATUS_CODE, PHYS_COMPLETE_PCT, ACT_START_DATE, ACT_END_DATE, TARGET_START_DATE, TARGET_END_DATE
            FROM TASK WHERE TASK_ID = ?
        """
        cursor.execute(sql, (task_id,))
        row = cursor.fetchone()
        if row:
            return {
                "status_code": row[0],
                "phys_complete_pct": row[1],
                "act_start_date": row[2],
                "act_end_date": row[3],
                "target_start_date": row[4],
                "target_end_date": row[5]
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
        task_guid = self._generate_guid()
        
        # Insert with defaults matching P6 schema requirements
        sql = """
            INSERT INTO TASK (
                TASK_ID, PROJ_ID, WBS_ID, CLNDR_ID, TASK_CODE, TASK_NAME, 
                STATUS_CODE, TASK_TYPE, DURATION_TYPE, 
                TARGET_DRTN_HR_CNT, REMAIN_DRTN_HR_CNT, PHYS_COMPLETE_PCT,
                CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER,
                GUID, COMPLETE_PCT_TYPE, PRIORITY_TYPE, EST_WT,
                REV_FDBK_FLAG, LOCK_PLAN_FLAG, AUTO_COMPUTE_ACT_FLAG,
                DRIVING_PATH_FLAG, CONTROL_UPDATES_FLAG, SCP_PCT_COMPLETE
            ) VALUES (
                ?, ?, ?, ?, ?, ?, 
                ?, ?, ?, 
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, 'CP_Drtn', 'PT_Top', 1.0,
                'N', 'N', 'N',
                'N', 'N', 0.0
            )
        """
        # Use provided values or defaults if missing in the object (though Pydantic model should handle most)
        status_code = task.status_code if task.status_code else 'TK_NotStart'
        task_type = task.task_type if task.task_type else 'TT_Task'
        duration_type = task.duration_type if task.duration_type else 'DT_FixedDUR2'
        
        cursor.execute(sql, (
            task_id, task.proj_id, task.wbs_id, task.clndr_id, task.task_code, task.task_name,
            status_code, task_type, duration_type,
            task.target_drtn_hr_cnt, task.remain_drtn_hr_cnt, task.phys_complete_pct,
            task.create_date, task.update_date, task.create_user, task.update_user,
            task_guid
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

    def get_relationship_id(self, conn: sqlite3.Connection, pred_id: int, succ_id: int) -> Optional[int]:
        cursor = conn.cursor()
        cursor.execute("SELECT TASK_PRED_ID FROM TASKPRED WHERE PRED_TASK_ID = ? AND TASK_ID = ?", (pred_id, succ_id))
        row = cursor.fetchone()
        return row[0] if row else None

    def delete_relationship(self, conn: sqlite3.Connection, task_pred_id: int) -> None:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM TASKPRED WHERE TASK_PRED_ID = ?", (task_pred_id,))

    def update_relationship(self, conn: sqlite3.Connection, task_pred_id: int, lag: Optional[float], rel_type: Optional[str]) -> None:
        cursor = conn.cursor()
        updates = ["UPDATE_DATE = ?"]
        params = [datetime.now()]
        
        if lag is not None:
            updates.append("LAG_HR_CNT = ?")
            params.append(lag)
            
        if rel_type:
            updates.append("PRED_TYPE = ?")
            params.append(rel_type)
            
        params.append(task_pred_id)
        
        sql = f"UPDATE TASKPRED SET {', '.join(updates)} WHERE TASK_PRED_ID = ?"
        cursor.execute(sql, params)

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

    def get_root_eps_wbs_id(self, conn: sqlite3.Connection) -> Optional[tuple[int, int]]:
        """
        Finds the WBS_ID and OBS_ID of the root EPS node.
        Assumes the root EPS is a PROJWBS entry where PROJ_NODE_FLAG='Y' and PARENT_WBS_ID is NULL.
        """
        cursor = conn.cursor()
        # Try to find a WBS that belongs to a project with PROJECT_FLAG='N' (EPS)
        sql = """
            SELECT w.WBS_ID, w.OBS_ID
            FROM PROJWBS w
            JOIN PROJECT p ON w.PROJ_ID = p.PROJ_ID
            WHERE p.PROJECT_FLAG = 'N' 
            ORDER BY w.WBS_ID ASC 
            LIMIT 1
        """
        cursor.execute(sql)
        row = cursor.fetchone()
        if row:
            return (row[0], row[1])
        return None

    def create_project(self, conn: sqlite3.Connection, short_name: str, long_name: str, planned_start: Optional[datetime] = None) -> tuple[int, int]:
        cursor = conn.cursor()
        
        # 1. IDs
        proj_id = self.get_next_key(conn, "PROJECT")
        wbs_id = self.get_next_key(conn, "PROJWBS")
        
        # Find Parent EPS and OBS
        eps_info = self.get_root_eps_wbs_id(conn)
        parent_wbs_id = None
        obs_id = None
        
        if eps_info:
            parent_wbs_id, obs_id = eps_info
            
        # Find Default Calendar
        cursor.execute("SELECT CLNDR_ID FROM CALENDAR WHERE DEFAULT_FLAG='Y' LIMIT 1")
        cal_row = cursor.fetchone()
        clndr_id = cal_row[0] if cal_row else None

        now = datetime.now()
        start_date = planned_start if planned_start else now
        
        # Generate GUIDs
        proj_guid = self._generate_guid()
        wbs_guid = self._generate_guid()

        # 2. Insert PROJECT
        # Added all default flags and settings observed from P6 manual creation
        # Added GUID and set ORIG_PROJ_ID to NULL (None)
        sql_proj = """
            INSERT INTO PROJECT (
                PROJ_ID, PROJ_SHORT_NAME, ORIG_PROJ_ID, 
                ADD_DATE, CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER,
                PLAN_START_DATE, PROJECT_FLAG, CLNDR_ID,
                FY_START_MONTH_NUM, RSRC_SELF_ADD_FLAG, ALLOW_COMPLETE_FLAG, 
                RSRC_MULTI_ASSIGN_FLAG, CHECKOUT_FLAG, STEP_COMPLETE_FLAG, 
                COST_QTY_RECALC_FLAG, BATCH_SUM_FLAG, NAME_SEP_CHAR, 
                DEF_COMPLETE_PCT_TYPE, TASK_CODE_BASE, TASK_CODE_STEP, 
                PRIORITY_NUM, WBS_MAX_SUM_LEVEL, STRGY_PRIORITY_NUM, 
                CRITICAL_DRTN_HR_CNT, DEF_COST_PER_QTY, DEF_DURATION_TYPE, 
                TASK_CODE_PREFIX, DEF_QTY_TYPE, DEF_RATE_TYPE, 
                ADD_ACT_REMAIN_FLAG, ACT_THIS_PER_LINK_FLAG, DEF_TASK_TYPE, 
                ACT_PCT_LINK_FLAG, CRITICAL_PATH_TYPE, TASK_CODE_PREFIX_FLAG, 
                DEF_ROLLUP_DATES_FLAG, USE_PROJECT_BASELINE_FLAG, 
                REM_TARGET_LINK_FLAG, RESET_PLANNED_FLAG, ALLOW_NEG_ACT_FLAG, 
                SUM_ASSIGN_LEVEL, FINTMPL_ID, GUID
            ) VALUES (
                ?, ?, ?, 
                ?, ?, ?, ?, ?,
                ?, 'Y', ?,
                1, 'Y', 'Y', 
                'Y', 'N', 'N', 
                'N', 'Y', '.', 
                'CP_Drtn', 1000, 10, 
                10, 2, 500, 
                0.0, 0.0, 'DT_FixedDUR2', 
                'A', 'QT_Hour', 'COST_PER_QTY', 
                'N', 'Y', 'TT_Task', 
                'Y', 'CT_TotFloat', 'Y', 
                'Y', 'Y', 
                'Y', 'N', 'N', 
                'SL_Taskrsrc', 1, ?
            )
        """
        cursor.execute(sql_proj, (
            proj_id, short_name, None, 
            now, now, now, "Agent", "Agent",
            start_date, clndr_id, proj_guid
        ))
        
        # 3. Insert Root WBS
        # Updated STATUS_CODE to 'WS_Open' and added defaults
        # Added GUID
        sql_wbs = """
            INSERT INTO PROJWBS (
                WBS_ID, PROJ_ID, WBS_SHORT_NAME, WBS_NAME, 
                PROJ_NODE_FLAG, STATUS_CODE, SEQ_NUM,
                CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER,
                PARENT_WBS_ID, OBS_ID,
                EST_WT, EV_USER_PCT, EV_ETC_USER_VALUE, 
                EV_COMPUTE_TYPE, EV_ETC_COMPUTE_TYPE, GUID
            ) VALUES (
                ?, ?, ?, ?, 'Y', 'WS_Open', 1, 
                ?, ?, ?, ?, 
                ?, ?,
                1.0, 6, 0.88, 
                'EC_Cmp_pct', 'EE_Rem_hr', ?
            )
        """
        cursor.execute(sql_wbs, (
            wbs_id, proj_id, short_name, long_name,
            now, now, "Agent", "Agent",
            parent_wbs_id, obs_id, wbs_guid
        ))
        
        return proj_id, wbs_id

    def ensure_embeddings_table(self, conn: sqlite3.Connection) -> None:
        """Ensures the TASK_EMBEDDINGS table exists."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS TASK_EMBEDDINGS (
                TASK_ID INTEGER PRIMARY KEY,
                PROJ_ID INTEGER NOT NULL,
                EMBEDDING_VECTOR BLOB NOT NULL,
                SOURCE_TEXT_HASH TEXT NOT NULL,
                LAST_UPDATED DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (TASK_ID) REFERENCES TASK(TASK_ID) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS IDX_TASK_EMBEDDINGS_PROJ ON TASK_EMBEDDINGS(PROJ_ID)")

    def upsert_task_embedding(self, conn: sqlite3.Connection, task_id: int, proj_id: int, embedding: bytes, source_hash: str) -> None:
        """Inserts or updates a task embedding."""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO TASK_EMBEDDINGS (TASK_ID, PROJ_ID, EMBEDDING_VECTOR, SOURCE_TEXT_HASH, LAST_UPDATED)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(TASK_ID) DO UPDATE SET
                EMBEDDING_VECTOR = excluded.EMBEDDING_VECTOR,
                SOURCE_TEXT_HASH = excluded.SOURCE_TEXT_HASH,
                LAST_UPDATED = excluded.LAST_UPDATED
        """, (task_id, proj_id, embedding, source_hash, datetime.now()))

    def get_project_embeddings(self, conn: sqlite3.Connection, proj_id: int) -> list[tuple[int, bytes]]:
        """Retrieves all embeddings for a project."""
        cursor = conn.cursor()
        cursor.execute("SELECT TASK_ID, EMBEDDING_VECTOR FROM TASK_EMBEDDINGS WHERE PROJ_ID = ?", (proj_id,))
        return cursor.fetchall()

    def list_projects(self, conn: sqlite3.Connection, include_eps: bool = False) -> list[dict]:
        """
        Lists all projects from the P6 database with summary information.
        
        Args:
            conn: Database connection
            include_eps: If True, include EPS hierarchy nodes. Default only actual projects.
            
        Returns:
            List of dictionaries with project information including description.
        """
        cursor = conn.cursor()
        
        # Filter: PROJECT_FLAG = 'Y' means it's an actual project, 'N' means EPS node
        # Note: In P6, the meaning is inverted from typical boolean logic
        project_filter = "" if include_eps else "AND p.PROJECT_FLAG = 'Y'"
        
        sql = f"""
            SELECT 
                p.PROJ_ID,
                p.PROJ_SHORT_NAME,
                pw.WBS_NAME as PROJECT_NAME,
                p.PLAN_START_DATE,
                p.PLAN_END_DATE,
                p.LAST_RECALC_DATE,
                p.ADD_DATE,
                (SELECT COUNT(*) FROM TASK t 
                 WHERE t.PROJ_ID = p.PROJ_ID 
                 AND t.DELETE_SESSION_ID IS NULL) as ACTIVITY_COUNT,
                wm.WBS_MEMO as DESCRIPTION_HTML
            FROM PROJECT p
            LEFT JOIN PROJWBS pw ON p.PROJ_ID = pw.PROJ_ID AND pw.PROJ_NODE_FLAG = 'Y'
            LEFT JOIN WBSMEMO wm ON pw.WBS_ID = wm.WBS_ID AND wm.MEMO_TYPE_ID = 33
            WHERE p.DELETE_SESSION_ID IS NULL
            {project_filter}
            ORDER BY p.PROJ_SHORT_NAME
        """
        
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        
        results = []
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            # Extract plain text from HTML description
            row_dict['DESCRIPTION'] = extract_text_from_html(row_dict.pop('DESCRIPTION_HTML', None))
            results.append(row_dict)
        
        return results

    def get_task_text_data(self, conn: sqlite3.Connection, proj_id: int) -> list[tuple[int, str, str, str, str]]:
        """
        Fetches Task ID, Code, Name, Memo content, and WBS Path for embedding generation.
        """
        cursor = conn.cursor()
        
        # Recursive CTE to build WBS Path (e.g., "Project > Phase 1 > Earthworks")
        # We start with the Project Root Node (PROJ_NODE_FLAG = 'Y')
        sql = """
            WITH RECURSIVE WBS_PATH(WBS_ID, PATH_NAME) AS (
                SELECT WBS_ID, WBS_NAME
                FROM PROJWBS
                WHERE PROJ_ID = ? AND PROJ_NODE_FLAG = 'Y'
                
                UNION ALL
                
                SELECT w.WBS_ID, wp.PATH_NAME || ' > ' || w.WBS_NAME
                FROM PROJWBS w
                JOIN WBS_PATH wp ON w.PARENT_WBS_ID = wp.WBS_ID
                WHERE w.PROJ_ID = ?
            )
            SELECT t.TASK_ID, t.TASK_CODE, t.TASK_NAME, 
                   COALESCE(tm.TASK_MEMO, '') as MEMO,
                   COALESCE(wp.PATH_NAME, '') as WBS_PATH
            FROM TASK t
            LEFT JOIN WBS_PATH wp ON t.WBS_ID = wp.WBS_ID
            LEFT JOIN TASKMEMO tm ON t.TASK_ID = tm.TASK_ID
            WHERE t.PROJ_ID = ?
        """
        try:
            cursor.execute(sql, (proj_id, proj_id, proj_id))
            return cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback if TASKMEMO doesn't exist or schema is different
            # Still try to get WBS Path without Memo
            sql_fallback = """
                WITH RECURSIVE WBS_PATH(WBS_ID, PATH_NAME) AS (
                    SELECT WBS_ID, WBS_NAME
                    FROM PROJWBS
                    WHERE PROJ_ID = ? AND PROJ_NODE_FLAG = 'Y'
                    UNION ALL
                    SELECT w.WBS_ID, wp.PATH_NAME || ' > ' || w.WBS_NAME
                    FROM PROJWBS w
                    JOIN WBS_PATH wp ON w.PARENT_WBS_ID = wp.WBS_ID
                    WHERE w.PROJ_ID = ?
                )
                SELECT t.TASK_ID, t.TASK_CODE, t.TASK_NAME, '', COALESCE(wp.PATH_NAME, '')
                FROM TASK t
                LEFT JOIN WBS_PATH wp ON t.WBS_ID = wp.WBS_ID
                WHERE t.PROJ_ID = ?
            """
            cursor.execute(sql_fallback, (proj_id, proj_id, proj_id))
            return cursor.fetchall()

    # ─────────────────────────────────────────────────────────────────────────────
    # Activity Code Methods
    # ─────────────────────────────────────────────────────────────────────────────

    def list_activity_codes(
        self, 
        conn: sqlite3.Connection, 
        include_project_codes: bool = False,
        proj_id: int | None = None
    ) -> list[dict]:
        """
        Lists activity code types and their values.
        
        Args:
            conn: Database connection
            include_project_codes: If True, include project-specific codes (requires proj_id)
            proj_id: Project ID for project-specific codes
            
        Returns:
            List of code types with their available values
        """
        cursor = conn.cursor()
        
        # Build scope filter
        if include_project_codes and proj_id:
            scope_filter = "(at.ACTV_CODE_TYPE_SCOPE = 'AS_Global' OR (at.ACTV_CODE_TYPE_SCOPE = 'AS_Project' AND at.PROJ_ID = ?))"
            params: list = [proj_id]
        else:
            scope_filter = "at.ACTV_CODE_TYPE_SCOPE = 'AS_Global'"
            params = []
        
        sql = f"""
            SELECT 
                at.ACTV_CODE_TYPE_ID,
                at.ACTV_CODE_TYPE,
                at.ACTV_CODE_TYPE_SCOPE,
                at.PROJ_ID as TYPE_PROJ_ID,
                at.SEQ_NUM as TYPE_SEQ,
                ac.ACTV_CODE_ID,
                ac.SHORT_NAME,
                ac.ACTV_CODE_NAME,
                ac.PARENT_ACTV_CODE_ID,
                ac.SEQ_NUM as CODE_SEQ
            FROM ACTVTYPE at
            LEFT JOIN ACTVCODE ac ON at.ACTV_CODE_TYPE_ID = ac.ACTV_CODE_TYPE_ID
            WHERE {scope_filter}
            ORDER BY at.SEQ_NUM, at.ACTV_CODE_TYPE, ac.SEQ_NUM, ac.SHORT_NAME
        """
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        # Group by code type
        types_map: dict[int, dict] = {}
        for row in rows:
            type_id = row[0]
            if type_id not in types_map:
                types_map[type_id] = {
                    'actv_code_type_id': type_id,
                    'actv_code_type': row[1],
                    'scope': row[2],
                    'proj_id': row[3],
                    'seq_num': row[4],
                    'values': []
                }
            # Add value if exists (LEFT JOIN may return NULL)
            if row[5] is not None:
                types_map[type_id]['values'].append({
                    'actv_code_id': row[5],
                    'short_name': row[6],
                    'actv_code_name': row[7],
                    'parent_actv_code_id': row[8],
                    'seq_num': row[9]
                })
        
        return list(types_map.values())

    def get_activity_code_type_by_name(
        self, 
        conn: sqlite3.Connection, 
        code_type_name: str,
        proj_id: int | None = None
    ) -> dict | None:
        """
        Gets an activity code type by its name.
        
        Args:
            conn: Database connection
            code_type_name: Name of the code type (e.g., 'PHASE')
            proj_id: Project ID for project-specific codes
            
        Returns:
            Code type info or None if not found
        """
        cursor = conn.cursor()
        
        # Try global first, then project-specific if proj_id provided
        sql = """
            SELECT ACTV_CODE_TYPE_ID, ACTV_CODE_TYPE, ACTV_CODE_TYPE_SCOPE, PROJ_ID
            FROM ACTVTYPE 
            WHERE ACTV_CODE_TYPE = ?
            AND (ACTV_CODE_TYPE_SCOPE = 'AS_Global' OR (ACTV_CODE_TYPE_SCOPE = 'AS_Project' AND PROJ_ID = ?))
            ORDER BY CASE WHEN ACTV_CODE_TYPE_SCOPE = 'AS_Global' THEN 0 ELSE 1 END
            LIMIT 1
        """
        cursor.execute(sql, (code_type_name, proj_id))
        row = cursor.fetchone()
        
        if row:
            return {
                'actv_code_type_id': row[0],
                'actv_code_type': row[1],
                'scope': row[2],
                'proj_id': row[3]
            }
        return None

    def get_activity_code_by_short_name(
        self, 
        conn: sqlite3.Connection, 
        code_type_id: int,
        short_name: str
    ) -> dict | None:
        """
        Gets an activity code value by its short name within a type.
        
        Args:
            conn: Database connection
            code_type_id: Activity code type ID
            short_name: Short name of the code value
            
        Returns:
            Code value info or None if not found
        """
        cursor = conn.cursor()
        
        sql = """
            SELECT ACTV_CODE_ID, SHORT_NAME, ACTV_CODE_NAME, PARENT_ACTV_CODE_ID
            FROM ACTVCODE 
            WHERE ACTV_CODE_TYPE_ID = ? AND SHORT_NAME = ?
        """
        cursor.execute(sql, (code_type_id, short_name))
        row = cursor.fetchone()
        
        if row:
            return {
                'actv_code_id': row[0],
                'short_name': row[1],
                'actv_code_name': row[2],
                'parent_actv_code_id': row[3]
            }
        return None

    def get_task_activity_codes(
        self, 
        conn: sqlite3.Connection, 
        task_id: int
    ) -> list[dict]:
        """
        Gets current activity code assignments for a task.
        
        Args:
            conn: Database connection
            task_id: Task ID
            
        Returns:
            List of current activity code assignments
        """
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                ta.ACTV_CODE_TYPE_ID,
                ta.ACTV_CODE_ID,
                at.ACTV_CODE_TYPE,
                ac.SHORT_NAME,
                ac.ACTV_CODE_NAME
            FROM TASKACTV ta
            JOIN ACTVTYPE at ON ta.ACTV_CODE_TYPE_ID = at.ACTV_CODE_TYPE_ID
            JOIN ACTVCODE ac ON ta.ACTV_CODE_ID = ac.ACTV_CODE_ID
            WHERE ta.TASK_ID = ?
            ORDER BY at.SEQ_NUM
        """
        cursor.execute(sql, (task_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'actv_code_type_id': row[0],
                'actv_code_id': row[1],
                'code_type_name': row[2],
                'short_name': row[3],
                'code_name': row[4]
            })
        return results

    def get_tasks_by_codes(
        self, 
        conn: sqlite3.Connection, 
        task_codes: list[str],
        proj_id: int
    ) -> list[dict]:
        """
        Gets task info by task codes.
        
        Args:
            conn: Database connection
            task_codes: List of task codes
            proj_id: Project ID
            
        Returns:
            List of task info dicts with task_id, task_code, task_name
        """
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(task_codes))
        sql = f"""
            SELECT TASK_ID, TASK_CODE, TASK_NAME
            FROM TASK
            WHERE TASK_CODE IN ({placeholders}) AND PROJ_ID = ?
            AND DELETE_SESSION_ID IS NULL
        """
        cursor.execute(sql, [*task_codes, proj_id])
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'task_id': row[0],
                'task_code': row[1],
                'task_name': row[2]
            })
        return results

    def get_tasks_by_wbs(
        self, 
        conn: sqlite3.Connection, 
        wbs_id: int,
        proj_id: int
    ) -> list[dict]:
        """
        Gets all tasks under a WBS (including nested WBS).
        
        Args:
            conn: Database connection
            wbs_id: WBS ID
            proj_id: Project ID
            
        Returns:
            List of task info dicts
        """
        cursor = conn.cursor()
        
        # Recursive CTE to get all WBS IDs under the given WBS
        sql = """
            WITH RECURSIVE WBS_TREE(WBS_ID) AS (
                SELECT WBS_ID FROM PROJWBS WHERE WBS_ID = ? AND PROJ_ID = ?
                UNION ALL
                SELECT w.WBS_ID FROM PROJWBS w
                JOIN WBS_TREE wt ON w.PARENT_WBS_ID = wt.WBS_ID
                WHERE w.PROJ_ID = ?
            )
            SELECT t.TASK_ID, t.TASK_CODE, t.TASK_NAME
            FROM TASK t
            WHERE t.WBS_ID IN (SELECT WBS_ID FROM WBS_TREE)
            AND t.DELETE_SESSION_ID IS NULL
            ORDER BY t.TASK_CODE
        """
        cursor.execute(sql, (wbs_id, proj_id, proj_id))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'task_id': row[0],
                'task_code': row[1],
                'task_name': row[2]
            })
        return results

    def assign_activity_code(
        self, 
        conn: sqlite3.Connection, 
        task_id: int,
        proj_id: int,
        actv_code_type_id: int,
        actv_code_id: int
    ) -> None:
        """
        Assigns an activity code to a task.
        Replaces existing code for the same type (UPSERT behavior).
        
        Args:
            conn: Database connection
            task_id: Task ID
            proj_id: Project ID
            actv_code_type_id: Activity code type ID
            actv_code_id: Activity code value ID
        """
        cursor = conn.cursor()
        now = datetime.now()
        
        # TASKACTV uses composite primary key (TASK_ID, ACTV_CODE_TYPE_ID)
        # Use INSERT OR REPLACE for upsert behavior
        sql = """
            INSERT OR REPLACE INTO TASKACTV (
                TASK_ID, PROJ_ID, ACTV_CODE_TYPE_ID, ACTV_CODE_ID,
                CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, (
            task_id, proj_id, actv_code_type_id, actv_code_id,
            now, now, "Agent", "Agent"
        ))

    def remove_activity_code(
        self, 
        conn: sqlite3.Connection, 
        task_id: int,
        actv_code_type_id: int
    ) -> bool:
        """
        Removes an activity code assignment from a task.
        
        Args:
            conn: Database connection
            task_id: Task ID
            actv_code_type_id: Activity code type ID
            
        Returns:
            True if a row was deleted, False if no matching assignment
        """
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM TASKACTV WHERE TASK_ID = ? AND ACTV_CODE_TYPE_ID = ?",
            (task_id, actv_code_type_id)
        )
        return cursor.rowcount > 0

    def check_activity_code_exists(
        self, 
        conn: sqlite3.Connection, 
        task_id: int,
        actv_code_type_id: int
    ) -> dict | None:
        """
        Checks if an activity code assignment exists for a task/type.
        
        Returns:
            Current assignment info or None
        """
        cursor = conn.cursor()
        
        sql = """
            SELECT ta.ACTV_CODE_ID, ac.SHORT_NAME, ac.ACTV_CODE_NAME
            FROM TASKACTV ta
            JOIN ACTVCODE ac ON ta.ACTV_CODE_ID = ac.ACTV_CODE_ID
            WHERE ta.TASK_ID = ? AND ta.ACTV_CODE_TYPE_ID = ?
        """
        cursor.execute(sql, (task_id, actv_code_type_id))
        row = cursor.fetchone()
        
        if row:
            return {
                'actv_code_id': row[0],
                'short_name': row[1],
                'code_name': row[2]
            }
        return None
