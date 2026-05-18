"""User and team context tools."""

from __future__ import annotations

from pydantic_ai import RunContext
import logfire

from sch_backend.tools._base import AgentDeps


@logfire.instrument("get_team_data")
async def get_team_data(
    ctx: RunContext[AgentDeps],
    project_id: str | None = None,
    include_inactive: bool = False,
) -> dict:
    """Get team members involved in a project from lognos_comm.users + user_project_access.

    Use this tool when you need full team information such as emails, roles,
    access levels, reporting lines, and project roles before drafting communications
    or assigning responsibilities.

    Args:
        ctx: Runtime context with user_context and user_context_repository.
        project_id: Optional explicit Lognos project ID. Defaults to current user context project.
        include_inactive: Include inactive users if true.

    Returns:
        Dictionary with current_user and team_members for the resolved project.
    """
    user_context = ctx.deps.user_context
    user_repo = ctx.deps.user_context_repository

    if not user_repo:
        return {
            "success": False,
            "error": "User context repository is not available in runtime dependencies.",
        }

    resolved_project_id = project_id or (user_context.current_project_id if user_context else None)
    if not resolved_project_id:
        return {
            "success": False,
            "error": "Project ID is required. Provide project_id or ensure request context has a current project.",
        }

    members = await user_repo.get_team_members_for_project(
        project_id=resolved_project_id,
        include_inactive=include_inactive,
    )

    return {
        "success": True,
        "project_id": resolved_project_id,
        "requested_by": user_context.model_dump() if user_context else None,
        "member_count": len(members),
        "team_members": [member.model_dump() for member in members],
    }
