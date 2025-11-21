# Lessons Learned: P6 Agent Development

## 1. P6 Database Schema Quirks
*   **GUIDs are Mandatory**: P6 relies heavily on 22-character Base64 GUIDs (stored in `GUID` columns) for internal linking and visibility. Inserting records with just integer IDs (`TASK_ID`, `PROJ_ID`) is insufficient; the records may exist in the DB but be invisible in the UI or cause crashes.
    *   *Solution*: Always generate and insert a GUID for `PROJECT`, `PROJWBS`, `TASK`, `RSRC`, etc.
*   **Default Flags Matter**: P6 tables have many "Flag" columns (e.g., `PROJ_NODE_FLAG`, `ALLOW_COMPLETE_FLAG`, `STATUS_CODE`). Leaving these null or using incorrect defaults often leads to "zombie" records.
    *   *Solution*: Reverse-engineer defaults by inspecting a manually created record in P6 before implementing the `INSERT` logic.
*   **Project Visibility**: A project is only visible if it has a corresponding Root WBS node (`PROJWBS` table) with `PROJ_NODE_FLAG = 'Y'`.

## 2. Agent & Tool Architecture
*   **Model/Service Alignment**: Ensure Pydantic models in `io.py` exactly match the fields expected by `scheduling_service.py`.
    *   *Incident*: `ActivityCreateRequest` lacked `clndr_id`, but the service tried to access it, causing a crash.
    *   *Fix*: Added the field to the model.
*   **Tool Clarity**: The Agent can get confused between similar concepts like `task_id` (internal integer PK) and `task_code` (user-facing string ID).
    *   *Solution*: Be explicit in system prompts and tool docstrings. "Use `task_code` for inputs, never `task_id`."

## 3. Performance & Safety (Local SQLite)
*   **Session-Level Transactions**: For a local file-based DB like SQLite (which P6 locks exclusively), copying the entire DB file for *every* tool call is too slow (O(N)).
    *   *Solution*: We implemented a "Session-Level Transaction" pattern. The API wraps the entire Agent execution in a single `SafeP6Transaction`. The Agent passes this connection to all tools, allowing multiple operations on a single temp copy before committing once at the end. This is O(1) and essential for multi-step tasks.

## 4. Future Recommendations
*   **Vector Search**: To make the agent more user-friendly, implement the proposed Vector Search (see `activity_vectorsearch.md`). This will allow users to refer to activities by description ("Update Earthworks") rather than memorizing codes ("A1000").
*   **Validation**: Continue to expand the `P6Repository` checks (e.g., `check_wbs_exists`) to fail fast with clear errors before attempting DB writes.
