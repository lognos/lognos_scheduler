# P6 Scheduling Agent - Development Plan

## 1. Project Overview
Development of a robust, production-ready agentic application to manage Primavera P6 schedules. The application will utilize a **Pydantic AI** agent to perform three core functions directly on the P6 SQLite database:
1.  **Create Activities**
2.  **Create Relationships**
3.  **Update Physical % Progress**

The system will be architected using **FastAPI** for the interface, **Pydantic v2** for strict data validation, and **Logfire** for observability.

## 2. Architecture & Tech Stack

### Technology Stack
*   **Language**: Python 3.11+
*   **Web Framework**: FastAPI
*   **Agent Framework**: Pydantic AI
*   **Data Validation**: Pydantic v2 (Strict Mode)
*   **Database**: SQLite (Direct P6 DB access)
*   **Observability**: Logfire
*   **Dependency Injection**: Pydantic AI `RunContext`

### Folder Structure
```
/backend/
├── agents/                 # Pydantic AI Agent definitions
│   └── scheduling_agent.py
├── api/                    # FastAPI application
│   ├── routers/            # API Endpoints
│   └── main.py             # App entrypoint
├── config/                 # Configuration & Settings
│   └── settings.py
├── models/                 # Pydantic Models
│   ├── domain.py           # Internal domain entities
│   └── io.py               # Input/Output DTOs (Strict)
├── repositories/           # Database Access Layer
│   └── p6_repository.py    # SQL operations for P6 tables
├── services/               # Business Logic Layer
│   └── scheduling_service.py
├── tools/                  # Agent Tools
│   └── p6_tools.py         # Tool definitions
└── utils/                  # Helpers
    └── db.py               # DB Connection management
```

## 3. Component Design

### 3.1. Data Models (`backend/models`)
Strict Pydantic models will ensure data integrity before it reaches the database.

*   **`io.py`**:
    *   `ActivityCreateRequest`: `task_code`, `task_name`, `wbs_id`, `proj_id`, `planned_duration`.
    *   `RelationshipCreateRequest`: `pred_task_code`, `succ_task_code`, `pred_type` (FS, SS, etc.), `lag`.
    *   `ProgressUpdateRequest`: `task_code`, `phys_complete_pct`, `actual_start` (optional), `actual_finish` (optional).
*   **`domain.py`**:
    *   `P6Activity`: Represents a row in `TASK` table.
    *   `P6Relationship`: Represents a row in `TASKPRED` table.

### 3.2. Repository Layer (`backend/repositories`)
**`P6Repository`**: Handles raw SQL interactions with the P6 SQLite database.
*   **Tables**: `TASK`, `TASKPRED`, `PROJWBS` (for validation).
*   **Methods**:
    *   `create_task(task: P6Activity) -> int`: Inserts into `TASK`.
    *   `create_relationship(pred_id: int, succ_id: int, type: str, lag: float) -> int`: Inserts into `TASKPRED`.
    *   `update_task_progress(task_id: int, pct: float, dates: dict) -> bool`: Updates `PHYS_COMPLETE_PCT`, `STATUS_CODE`, and dates in `TASK`.
    *   `get_task_id_by_code(code: str, proj_id: int) -> int`: Helper to resolve IDs.
    *   `get_next_key(table_name: str) -> int`: Handles P6 `NEXTKEY` logic for ID generation.

### 3.3. Service Layer (`backend/services`)
**`SchedulingService`**: Orchestrates logic and validation.
*   Validates that WBS and Projects exist.
*   Resolves `task_code` to `task_id`.
*   Ensures business rules (e.g., cannot link activity to itself).
*   Manages transactions (commit/rollback).

### 3.4. Agent Tools (`backend/tools`)
Pydantic AI tools decorated with `@agent.tool`. These will be injected with `SchedulingService` via context.
1.  **`create_activity_tool`**: "Creates a new activity in the schedule."
2.  **`create_relationship_tool`**: "Links two activities with a dependency."
3.  **`update_progress_tool`**: "Updates the physical percentage complete of an activity."

### 3.5. Agent (`backend/agents`)
**`scheduling_agent.py`**:
*   **System Prompt**: Defines the persona (Expert P6 Scheduler) and rules (e.g., "Always verify task codes exist before linking").
*   **Model**: Gemini 1.5 Pro (or configured LLM).
*   **Tools**: Registers the 3 tools defined above.

### 3.6. API (`backend/api`)
**FastAPI Router**:
*   `POST /api/v1/chat`: Accepts a user prompt (e.g., "Add activity A100 'Foundation' to WBS 123").
*   Invokes `scheduling_agent.run()`.
*   Returns the agent's natural language response and tool execution results.

### 3.7. Observability
*   **Logfire**: Instrumented in `main.py` to trace all agent executions, tool calls, and database queries.

## 4. Implementation Steps

1.  **Environment Setup**:
    *   Create virtual environment.
    *   Install `fastapi`, `pydantic-ai`, `logfire`, `uvicorn`, `pydantic-settings`.
2.  **Database Connection**:
    *   Implement `utils/db.py` to connect to the P6 SQLite file.
3.  **Repository Implementation**:
    *   Implement `P6Repository` with `NEXTKEY` handling (crucial for P6 integrity).
4.  **Service Layer**:
    *   Implement `SchedulingService` with logic to bridge Models and Repository.
5.  **Tool Definition**:
    *   Create `p6_tools.py` wrapping service methods.
6.  **Agent Configuration**:
    *   Setup `scheduling_agent` with system prompt and tools.
7.  **API Development**:
    *   Create FastAPI app and chat endpoint.
8.  **Testing**:
    *   Test with sample P6 database (copy of `p6.db`).

## 5. Key Considerations for P6
*   **ID Generation**: P6 uses a `NEXTKEY` table to manage primary keys. The repository **must** correctly increment and retrieve keys from this table to avoid corruption.
*   **Dates**: P6 stores dates as strings or timestamps. Strict format handling is required.
*   **Status Codes**: Updating progress requires managing `STATUS_CODE` (`TK_NotStart`, `TK_Active`, `TK_Complete`) alongside `% Complete`.
