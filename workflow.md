# P6 Assistant Workflow Documentation

This document illustrates how the P6 Assistant processes a complex user request involving multiple steps and how it ensures database integrity during write operations.

## Scenario
**User Request:** "Create two activities, earthworks (30 days duration) and foundations of a generator (21 days duration), with a FS relationship and a lag of 2 days."

## 1. System Architecture Workflow
This diagram shows the flow of control from the user's request through the Agent, Tools, Service, and Repository layers.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI Router
    participant Agent as Pydantic AI Agent
    participant Tools as P6 Tools
    participant Service as Scheduling Service
    participant Repo as P6 Repository

    User->>API: POST /chat <br/>"Create Earthworks & Foundations..."
    API->>Agent: agent.run(user_prompt)
    
    Note over Agent: LLM analyzes request & plans steps:<br/>1. Create Earthworks<br/>2. Create Foundations<br/>3. Link them

    %% Step 1: Create Activity 1
    Agent->>Tools: create_activity_tool(Earthworks, 30d)
    Tools->>Service: create_activity(...)
    Service->>Repo: create_task(...)
    Repo-->>Service: Returns Task ID (e.g., 1001)
    Service-->>Tools: Returns ID
    Tools-->>Agent: "Created Earthworks (ID: 1001)"

    %% Step 2: Create Activity 2
    Agent->>Tools: create_activity_tool(Foundations, 21d)
    Tools->>Service: create_activity(...)
    Service->>Repo: create_task(...)
    Repo-->>Service: Returns Task ID (e.g., 1002)
    Service-->>Tools: Returns ID
    Tools-->>Agent: "Created Foundations (ID: 1002)"

    %% Step 3: Create Relationship
    Note over Agent: Uses IDs from previous steps
    Agent->>Tools: create_relationship_tool(1001 -> 1002, FS, Lag=2d)
    Tools->>Service: create_relationship(...)
    Service->>Repo: create_relationship(...)
    Repo-->>Service: Returns Rel ID
    Service-->>Tools: Returns Success
    Tools-->>Agent: "Linked 1001 -> 1002"

    Agent-->>API: Final Response Summary
    API-->>User: "Successfully created activities and linked them."
```

## 2. Safe Database Transaction Workflow
This diagram details the **Copy-Modify-Check-Replace** safety mechanism that occurs *inside* the `Scheduling Service` whenever a write operation (like `create_activity` or `create_relationship`) is performed. This ensures the live P6 database is never corrupted by concurrent access or script errors.

```mermaid
sequenceDiagram
    participant Service as Scheduling Service
    participant SafeDB as SafeP6Transaction
    participant FS as File System
    participant LiveDB as Live DB (PPMDBSQLite.db)
    participant TempDB as Temp DB (Copy)

    Note over Service: Triggered by any Write Operation

    Service->>SafeDB: Enter Context (with SafeP6Transaction)
    activate SafeDB
    
    %% 1. Copy
    SafeDB->>FS: Copy LiveDB -> TempDB
    activate TempDB
    Note right of FS: Snapshot taken
    
    %% 2. Modify
    SafeDB->>Service: Yield Connection(TempDB)
    Service->>TempDB: INSERT / UPDATE SQL
    Service->>TempDB: COMMIT
    
    %% 3. Check
    Service->>SafeDB: Exit Context
    SafeDB->>TempDB: PRAGMA integrity_check
    TempDB-->>SafeDB: Result: OK
    
    alt Integrity Check Passed
        %% 4. Backup & Replace
        SafeDB->>FS: Move LiveDB -> superseded/LiveDB_timestamp
        Note right of FS: Backup created
        SafeDB->>FS: Move TempDB -> LiveDB
        Note right of FS: Atomic Replacement
        SafeDB-->>Service: Success
    else Integrity Check Failed
        SafeDB->>FS: Delete TempDB
        SafeDB-->>Service: Raise Error (LiveDB untouched)
    end
    
    deactivate TempDB
    deactivate SafeDB
```
