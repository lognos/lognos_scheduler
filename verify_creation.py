import sqlite3
import os
from backend.config.settings import settings

def verify_project():
    db_path = settings.P6_DB_LOC
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Checking database at: {db_path}")
    
    # Get latest project
    cursor.execute("SELECT PROJ_ID, PROJ_SHORT_NAME, PLAN_START_DATE FROM PROJECT ORDER BY PROJ_ID DESC LIMIT 1")
    proj = cursor.fetchone()
    if not proj:
        print("No projects found.")
        return
        
    proj_id = proj[0]
    print(f"Latest Project: ID={proj_id}, Name={proj[1]}, Start={proj[2]}")
    
    # Get Activities
    cursor.execute("SELECT TASK_CODE, TASK_NAME, TARGET_DRTN_HR_CNT FROM TASK WHERE PROJ_ID = ?", (proj_id,))
    tasks = cursor.fetchall()
    print("\nActivities:")
    for t in tasks:
        print(f"- {t[0]}: {t[1]} ({t[2]} hrs)")
        
    # Get Relationships
    cursor.execute("""
        SELECT p.TASK_CODE, s.TASK_CODE, tp.PRED_TYPE, tp.LAG_HR_CNT
        FROM TASKPRED tp
        JOIN TASK p ON tp.PRED_TASK_ID = p.TASK_ID
        JOIN TASK s ON tp.TASK_ID = s.TASK_ID
        WHERE tp.PROJ_ID = ?
    """, (proj_id,))
    
    rels = cursor.fetchall()
    print("\nRelationships:")
    for r in rels:
        print(f"- {r[0]} -> {r[1]} ({r[2]}, Lag: {r[3]})")
        
    conn.close()

if __name__ == "__main__":
    verify_project()
