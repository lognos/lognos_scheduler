"""Tools package - all agent tools organized by target.

Tool naming convention:
- P6 database tools: {action}_{entity}_p6
- Workspace tools: {action}_{entity}_ws
- Indexing tools: {action}_{entity}

Import examples:
    from backend.tools import get_activity_p6, load_schedule_ws
    from backend.tools.p6 import create_activity_p6
    from backend.tools.workspace import calculate_gantt_ws
"""

# Re-export base dependencies
from backend.tools._base import AgentDeps

# P6 Database tools (queries)
from backend.tools.p6.queries import (
    get_activity_p6,
    search_activities_p6,
    list_projects_p6,
    list_activities_p6,
    list_activity_codes_p6,
    get_activity_codes_p6,
)

# P6 Database tools (activities)
from backend.tools.p6.activities import (
    create_activity_p6,
    update_activity_status_p6,
    update_progress_p6,
)

# P6 Database tools (relationships)
from backend.tools.p6.relationships import (
    create_relationship_p6,
    update_relationship_p6,
    delete_relationship_p6,
)

# P6 Database tools (projects)
from backend.tools.p6.projects import (
    create_project_p6,
)

# P6 Database tools (activity codes)
from backend.tools.p6.activity_codes import (
    assign_activity_codes_p6,
    remove_activity_codes_p6,
    bulk_assign_activity_codes_p6,
)

# Workspace tools (queries)
from backend.tools.workspace.queries import (
    get_workspace_status_ws,
)

# Workspace tools (mutations)
from backend.tools.workspace.mutations import (
    load_schedule_ws,
    create_schedule_ws,
    clear_schedule_ws,
    calculate_gantt_ws,
    modify_activity_ws,
    add_activity_ws,
    add_relationship_ws,
    modify_relationship_ws,
    delete_relationship_ws,
    delete_activity_ws,
    hide_gantt_ws,
    # Activity code tools
    assign_activity_codes_ws,
    bulk_assign_activity_codes_ws,
    remove_activity_codes_ws,
    get_activity_codes_ws,
)

# Indexing tools
from backend.tools.indexing.operations import (
    index_project,
)

# Context tools
from backend.tools.context import (
    get_team_data,
)

__all__ = [
    # Base
    "AgentDeps",
    
    # P6 Query tools
    "get_activity_p6",
    "search_activities_p6",
    "list_projects_p6",
    "list_activities_p6",
    "list_activity_codes_p6",
    "get_activity_codes_p6",
    
    # P6 Activity tools
    "create_activity_p6",
    "update_activity_status_p6",
    "update_progress_p6",
    
    # P6 Relationship tools
    "create_relationship_p6",
    "update_relationship_p6",
    "delete_relationship_p6",
    
    # P6 Project tools
    "create_project_p6",
    
    # P6 Activity code tools
    "assign_activity_codes_p6",
    "remove_activity_codes_p6",
    "bulk_assign_activity_codes_p6",
    
    # Workspace tools
    "get_workspace_status_ws",
    "load_schedule_ws",
    "create_schedule_ws",
    "clear_schedule_ws",
    "calculate_gantt_ws",
    "modify_activity_ws",
    "add_activity_ws",
    "add_relationship_ws",
    "modify_relationship_ws",
    "delete_relationship_ws",
    "delete_activity_ws",
    "hide_gantt_ws",
    # Workspace activity code tools
    "assign_activity_codes_ws",
    "bulk_assign_activity_codes_ws",
    "remove_activity_codes_ws",
    "get_activity_codes_ws",
    
    # Indexing tools
    "index_project",

    # Context tools
    "get_team_data",
]
