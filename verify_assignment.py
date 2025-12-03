#!/usr/bin/env python3
"""Verify activity code assignment"""

import sqlite3
from backend.config.settings import settings

def main():
    conn = sqlite3.connect(settings.P6_DB_LOC)
    cursor = conn.cursor()
    
    proj_id = 1011
    task_codes = ['A2010', 'A2040']
    
    # Find DISCIPLINE code type
    cursor.execute("""
        SELECT ACTV_CODE_TYPE_ID, ACTV_CODE_TYPE, ACTV_CODE_TYPE_SCOPE
        FROM ACTVTYPE
        WHERE ACTV_CODE_TYPE = 'DISCIPLINE'
    """)
    code_type = cursor.fetchone()
    print(f"Code type: {code_type}")
    
    if not code_type:
        print("DISCIPLINE code type not found!")
        conn.close()
        return
    
    actv_code_type_id = code_type[0]
    
    # Find CIV code
    cursor.execute("""
        SELECT ACTV_CODE_ID, SHORT_NAME, ACTV_CODE_NAME
        FROM ACTVCODE
        WHERE ACTV_CODE_TYPE_ID = ? AND SHORT_NAME = 'CIV'
    """, (actv_code_type_id,))
    civ_code = cursor.fetchone()
    print(f"CIV code: {civ_code}")
    
    # Find tasks
    placeholders = ','.join(['?'] * len(task_codes))
    cursor.execute(f"""
        SELECT TASK_ID, TASK_CODE, TASK_NAME
        FROM TASK
        WHERE TASK_CODE IN ({placeholders}) AND PROJ_ID = ?
    """, [*task_codes, proj_id])
    tasks = cursor.fetchall()
    print(f"Tasks: {tasks}")
    
    # Check TASKACTV for these tasks
    for task in tasks:
        task_id = task[0]
        cursor.execute("""
            SELECT ta.ACTV_CODE_TYPE_ID, at.ACTV_CODE_TYPE, 
                   ta.ACTV_CODE_ID, ac.SHORT_NAME, ac.ACTV_CODE_NAME
            FROM TASKACTV ta
            JOIN ACTVTYPE at ON ta.ACTV_CODE_TYPE_ID = at.ACTV_CODE_TYPE_ID
            JOIN ACTVCODE ac ON ta.ACTV_CODE_ID = ac.ACTV_CODE_ID
            WHERE ta.TASK_ID = ?
        """, (task_id,))
        codes = cursor.fetchall()
        print(f"\nTask {task[1]} ({task_id}) has codes:")
        for code in codes:
            print(f"  - {code[1]}: {code[3]} ({code[4]})")
        
        if not codes:
            print("  (no codes assigned)")
    
    conn.close()

if __name__ == "__main__":
    main()
