# Project Creation Tool Implementation Proposal

## 1. Objective
Implement a new tool `create_project_tool` that allows the Agent to create new projects in the P6 database. This involves creating the project record and its corresponding root WBS element.

## 2. Schema Analysis
To create a valid project in P6, we must populate two tables:
1.  **`PROJECT`**: Contains project-level settings (ID, Short Name, etc.).
2.  **`PROJWBS`**: Contains the Work Breakdown Structure. Every project must have a root WBS node where `PROJ_NODE_FLAG = 'Y'`.

### Key Fields
*   **`PROJECT` Table**:
    *   `PROJ_ID` (PK): Generated via `NEXTKEY`.
    *   `PROJ_SHORT_NAME`: Unique identifier (e.g., 'PROJ-001').
    *   `PROJ_NAME`: *Note: P6 often stores the project name in the root WBS node, but let's verify if `PROJECT` has a name field or if it relies on `PROJWBS`.* (Based on schema review, `PROJECT` has `PROJ_SHORT_NAME` but `PROJWBS` has `WBS_NAME` and `WBS_SHORT_NAME`. The root WBS usually carries the project name).
    *   `ORIG_PROJ_ID`: Usually same as `PROJ_ID` for new projects.
    *   `ADD_DATE`: Creation date.
    *   `STATUS_CODE`: e.g., 'TK_Active'.

*   **`PROJWBS` Table**:
    *   `WBS_ID` (PK): Generated via `NEXTKEY`.
    *   `PROJ_ID`: FK to `PROJECT`.
    *   `WBS_SHORT_NAME`: Same as `PROJ_SHORT_NAME` for root.
    *   `WBS_NAME`: The full name of the project.
    *   `PROJ_NODE_FLAG`: Must be `'Y'` for the root node.
    *   `STATUS_CODE`: 'TK_Active'.
    *   `SEQ_NUM`: 1.

## 3. Implementation Plan

### 3.1 Models (`backend/models/io.py` & `domain.py`)
**IO Model:**
```python
class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    project_short_name: StrictStr
    project_name: StrictStr
    planned_start_date: datetime | None = None
```

### 3.2 Repository (`backend/repositories/p6_repository.py`)
Add `create_project` method:
1.  Get `PROJ_ID` from `NEXTKEY`.
2.  Get `WBS_ID` from `NEXTKEY`.
3.  Insert into `PROJECT`.
4.  Insert into `PROJWBS` (Root Node).

### 3.3 Service (`backend/services/scheduling_service.py`)
Add `create_project` method:
*   Accept `ProjectCreateRequest`.
*   Use `SafeP6Transaction` (or passed `conn`).
*   Call Repo to create project.
*   Return `project_id`.

### 3.4 Tool (`backend/tools/p6_tools.py`)
Add `create_project_tool`:
*   Expose to Agent.
*   Logfire instrumentation.

## 4. Draft Code

### Repository
```python
def create_project(self, conn: sqlite3.Connection, short_name: str, long_name: str) -> int:
    cursor = conn.cursor()
    
    # 1. IDs
    proj_id = self.get_next_key(conn, "PROJECT")
    wbs_id = self.get_next_key(conn, "PROJWBS")
    
    now = datetime.now()
    
    # 2. Insert PROJECT
    sql_proj = """
        INSERT INTO PROJECT (
            PROJ_ID, PROJ_SHORT_NAME, ORIG_PROJ_ID, 
            ADD_DATE, CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor.execute(sql_proj, (
        proj_id, short_name, proj_id, 
        now, now, now, "Agent", "Agent"
    ))
    
    # 3. Insert Root WBS
    sql_wbs = """
        INSERT INTO PROJWBS (
            WBS_ID, PROJ_ID, WBS_SHORT_NAME, WBS_NAME, 
            PROJ_NODE_FLAG, STATUS_CODE, SEQ_NUM,
            CREATE_DATE, UPDATE_DATE, CREATE_USER, UPDATE_USER
        ) VALUES (?, ?, ?, ?, 'Y', 'TK_Active', 1, ?, ?, ?, ?)
    """
    cursor.execute(sql_wbs, (
        wbs_id, proj_id, short_name, long_name,
        now, now, "Agent", "Agent"
    ))
    
    return proj_id
```

### Service
```python
def create_project(self, req: ProjectCreateRequest, conn=None) -> int:
    if conn:
        return self.repo.create_project(conn, req.project_short_name, req.project_name)
        
    with SafeP6Transaction() as safe_conn:
        proj_id = self.repo.create_project(safe_conn, req.project_short_name, req.project_name)
        safe_conn.commit()
        return proj_id
```

## 6. Implementation Status (Updated)
**Status**: Implemented and Verified.

**Key Adjustments Made During Implementation:**
1.  **GUIDs**: Added generation of 22-char Base64 GUIDs for both `PROJECT` and `PROJWBS` tables. This is mandatory for P6 visibility.
2.  **Defaults**: Populated numerous default flags (e.g., `PROJECT_FLAG='Y'`, `ALLOW_COMPLETE_FLAG='Y'`, `SC_OPEN` status) to match P6 native behavior.
3.  **Hierarchy**: Logic added to find the Root EPS (Enterprise Project Structure) to correctly parent the new project's WBS, ensuring it appears in the project tree.
4.  **Calendar**: Logic added to fetch and assign the default Global Calendar (`DEFAULT_FLAG='Y'`) to the new project.

The tool is now fully functional and creates projects that are immediately visible and editable in P6.
