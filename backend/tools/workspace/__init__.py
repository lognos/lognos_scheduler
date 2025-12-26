"""Workspace tools package - tools for operating on the in-memory schedule workspace.

These tools operate on the workspace DataFrame loaded from P6 but not yet persisted.
Use these for what-if analysis, schedule calculations, and visualization.

All tool names follow the convention: {action}_{entity}_ws
"""

from backend.tools.workspace.queries import (
    get_workspace_status_ws,
)
from backend.tools.workspace.mutations import (
    load_schedule_ws,
    create_schedule_ws,
    clear_schedule_ws,
    calculate_gantt_ws,
    modify_activity_ws,
    add_activity_ws,
    add_relationship_ws,
    modify_relationship_ws,
    hide_gantt_ws,
)

__all__ = [
    # Queries
    "get_workspace_status_ws",
    # Mutations - Workspace lifecycle
    "load_schedule_ws",
    "create_schedule_ws",
    "clear_schedule_ws",
    # Mutations - Schedule operations
    "calculate_gantt_ws",
    "modify_activity_ws",
    "add_activity_ws",
    "add_relationship_ws",
    "modify_relationship_ws",
    "hide_gantt_ws",
]
