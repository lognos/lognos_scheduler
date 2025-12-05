"""P6 database tools - queries and mutations for Primavera P6."""

from .queries import (
    get_activity_p6,
    search_activities_p6,
    list_projects_p6,
    list_activities_p6,
    list_activity_codes_p6,
    get_activity_codes_p6,
)
from .activities import (
    create_activity_p6,
    update_progress_p6,
    update_activity_status_p6,
)
from .relationships import (
    create_relationship_p6,
    update_relationship_p6,
    delete_relationship_p6,
)
from .projects import create_project_p6
from .activity_codes import (
    assign_activity_codes_p6,
    remove_activity_codes_p6,
    bulk_assign_activity_codes_p6,
)

# Categorized exports for agent registration
P6_QUERY_TOOLS = [
    get_activity_p6,
    search_activities_p6,
    list_projects_p6,
    list_activities_p6,
    list_activity_codes_p6,
    get_activity_codes_p6,
]

P6_MUTATION_TOOLS = [
    create_activity_p6,
    update_progress_p6,
    update_activity_status_p6,
    create_relationship_p6,
    update_relationship_p6,
    delete_relationship_p6,
    create_project_p6,
    assign_activity_codes_p6,
    remove_activity_codes_p6,
    bulk_assign_activity_codes_p6,
]

__all__ = [
    # Query tools
    "get_activity_p6",
    "search_activities_p6",
    "list_projects_p6",
    "list_activities_p6",
    "list_activity_codes_p6",
    "get_activity_codes_p6",
    # Mutation tools
    "create_activity_p6",
    "update_progress_p6",
    "update_activity_status_p6",
    "create_relationship_p6",
    "update_relationship_p6",
    "delete_relationship_p6",
    "create_project_p6",
    "assign_activity_codes_p6",
    "remove_activity_codes_p6",
    "bulk_assign_activity_codes_p6",
    # Tool lists
    "P6_QUERY_TOOLS",
    "P6_MUTATION_TOOLS",
]
