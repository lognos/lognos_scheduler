"""Pydantic AI tools for Phase 1."""

from backend.tools.database_tools import (
    list_communications_tool,
    get_communications_by_project_tool,
    get_communications_by_date_range_tool,
    get_communications_by_project_and_date_tool,
    search_communications_semantic_tool,
)
from backend.tools.email_tools import (
    send_email_tool,
    check_email_service_health_tool,
)
from backend.tools.risk_tools import (
    extract_risks_from_memory_tool,
    find_similar_risks_tool,
    create_risk_assessment_tool,
    get_project_risks_tool,
    propose_reviewers_tool,
    extract_review_feedback_tool,
    generate_revision_tool,
    link_related_risks_tool,
    get_related_risks_tool,
)

__all__ = [
    # Database tools
    "list_communications_tool",
    "get_communications_by_project_tool",
    "get_communications_by_date_range_tool",
    "get_communications_by_project_and_date_tool",
    "search_communications_semantic_tool",
    # Email tools
    "send_email_tool",
    "check_email_service_health_tool",
    # Risk tools
    "extract_risks_from_memory_tool",
    "find_similar_risks_tool",
    "create_risk_assessment_tool",
    "get_project_risks_tool",
    "propose_reviewers_tool",
    "extract_review_feedback_tool",
    "generate_revision_tool",
    "link_related_risks_tool",
    "get_related_risks_tool",
]
