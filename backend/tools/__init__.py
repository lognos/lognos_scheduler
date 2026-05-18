"""Tools package - all agent tools organized by target.

Tool naming convention:
- MS schedule tools: {action}_{entity}_ms
- Workspace tools: {action}_{entity}_ws

Import examples:
    from backend.tools.ms import list_activities_ms
    from backend.tools.workspace import calculate_gantt_ws
"""

# Re-export base dependencies
from backend.tools._base import AgentDeps

# Workspace tools (queries)
from backend.tools.workspace.queries import (
    get_workspace_status_ws,
    get_driving_path_ws,
)

# Workspace tools (mutations)
from backend.tools.workspace.mutations import (
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
    # What-if baseline tools
    snapshot_baseline_ws,
    get_whatif_comparison_ws,
)

# Context tools
from backend.tools.context import (
    get_team_data,
)

__all__ = [
    # Base
    "AgentDeps",
    
    # Workspace tools
    "get_workspace_status_ws",
    "get_driving_path_ws",
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
    # What-if baseline tools
    "snapshot_baseline_ws",
    "get_whatif_comparison_ws",
    
    # Context tools
    "get_team_data",
]
