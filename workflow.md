# P6 Assistant Workflow Documentation

This document illustrates how the P6 Assistant processes a complex user request involving multiple steps and how it ensures database integrity during write operations.

## Scenario
**User Request:** "Create two activities, earthworks (30 days duration) and foundations of a generator (21 days duration), with a FS relationship and a lag of 2 days."

## 1. System Architecture Workflow (Session-Level Transaction)
This diagram shows the flow of control from the user's request through the Agent, Tools, Service, and Repository layers. 
**Optimization:** The entire agent execution is wrapped in a single `SafeP6Transaction`. This means the database is copied once at the start of the request, all agent operations (multiple tool calls) are performed on the temporary copy, and the file is swapped back only once at the end of the request.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI Router
    participant SafeDB as SafeP6Transaction
    participant Agent as Pydantic AI Agent
    participant Tools as P6 Tools
    participant Service as Scheduling Service
    participant Repo as P6 Repository

    User->>API: POST /chat <br/>"Create Earthworks & Foundations..."
    
    %% Start Session Transaction
    Note over API: Start Session-Level Transaction
    API->>SafeDB: Enter Context (Copy LiveDB -> TempDB)
    activate SafeDB
    SafeDB-->>API: Yield Connection(TempDB)
    
    API->>Agent: agent.run(user_prompt, deps={conn: TempDB})
    
    Note over Agent: LLM analyzes request & plans steps

    %% Step 1: Create Activity 1
    Agent->>Tools: create_activity_tool(Earthworks, 30d)
    Tools->>Service: create_activity(conn=TempDB)
    Service->>Repo: create_task(TempDB, ...)
    Repo-->>Service: Returns Task ID (e.g., 1001)
    Service-->>Tools: Returns ID
    Tools-->>Agent: "Created Earthworks (ID: 1001)"

    %% Step 2: Create Activity 2
    Agent->>Tools: create_activity_tool(Foundations, 21d)
    Tools->>Service: create_activity(conn=TempDB)
    Service->>Repo: create_task(TempDB, ...)
    Repo-->>Service: Returns Task ID (e.g., 1002)
    Service-->>Tools: Returns ID
    Tools-->>Agent: "Created Foundations (ID: 1002)"

    %% Step 3: Create Relationship
    Agent->>Tools: create_relationship_tool(1001 -> 1002, FS, Lag=2d)
    Tools->>Service: create_relationship(conn=TempDB, ...)
    Service->>Repo: create_relationship(TempDB, ...)
    Repo-->>Service: Returns Rel ID
    Service-->>Tools: Returns Success
    Tools-->>Agent: "Linked 1001 -> 1002"

    Agent-->>API: Final Response Summary
    
    %% End Session Transaction
    Note over API: Commit & Swap
    API->>SafeDB: Exit Context (Integrity Check -> Swap Files)
    deactivate SafeDB
    
    API-->>User: "Successfully created activities and linked them."
```

## 2. Safe Database Transaction Workflow
This diagram details the **Copy-Modify-Check-Replace** safety mechanism. In the optimized workflow, this entire sequence happens once per **Request** (Session), rather than once per individual write operation.

```mermaid
sequenceDiagram
    participant API as FastAPI Router
    participant SafeDB as SafeP6Transaction
    participant FS as File System
    participant LiveDB as Live DB (PPMDBSQLite.db)
    participant TempDB as Temp DB (Copy)

    Note over API: Request Started

    API->>SafeDB: Enter Context
    activate SafeDB
    
    %% 1. Copy
    SafeDB->>FS: Copy LiveDB -> TempDB
    activate TempDB
    Note right of FS: Snapshot taken
    
    %% 2. Modify (Multiple Operations)
    SafeDB->>API: Yield Connection(TempDB)
    API->>TempDB: Operation 1 (INSERT)
    API->>TempDB: Operation 2 (INSERT)
    API->>TempDB: Operation 3 (UPDATE)
    
    %% 3. Check
    API->>SafeDB: Exit Context
    SafeDB->>TempDB: PRAGMA integrity_check
    TempDB-->>SafeDB: Result: OK
    
    alt Integrity Check Passed
        %% 4. Backup & Replace
        SafeDB->>FS: Move LiveDB -> superseded/LiveDB_timestamp
        Note right of FS: Backup created
        SafeDB->>FS: Move TempDB -> LiveDB
        Note right of FS: Atomic Replacement
        SafeDB-->>API: Success
    else Integrity Check Failed
        SafeDB->>FS: Delete TempDB
        SafeDB-->>API: Raise Error (LiveDB untouched)
    end
    
    deactivate TempDB
    deactivate SafeDB
```

### Performance Note
By lifting the transaction scope to the Session (Request) level, we reduce the I/O overhead from $O(N)$ copies (where N is the number of tool calls) to $O(1)$ copy per request. This significantly improves performance for complex multi-step instructions while maintaining the same level of safety against corruption.
