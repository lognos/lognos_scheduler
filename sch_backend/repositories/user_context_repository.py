"""Repository for user identity and project team context lookups in lognos_comm schema."""

from __future__ import annotations

import logfire
from supabase import Client

from sch_backend.models.domain import TeamMemberContext, UserContext


class UserContextRepository:
    """Read-only repository for user and team context data."""

    SCHEMA = "lognos_comm"
    USERS_TABLE = "users"
    USER_PROJECT_ACCESS_TABLE = "user_project_access"

    def __init__(self, supabase: Client):
        self.supabase = supabase

    @logfire.instrument("repo.get_user_context")
    async def get_user_context(self, email: str, project_id: str | None = None) -> UserContext:
        """Resolve user profile by email from lognos_comm.users."""
        result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.USERS_TABLE)
            .select(
                "user_email, full_name, first_name, role, app_role, department, reports_to, active"
            )
            .eq("user_email", email)
            .limit(1)
            .execute()
        )

        row = result.data[0] if result.data else None
        if not row:
            return UserContext(email=email, current_project_id=project_id)

        return UserContext(
            email=row.get("user_email") or email,
            full_name=row.get("full_name"),
            first_name=row.get("first_name"),
            role=row.get("role"),
            app_role=row.get("app_role"),
            department=row.get("department"),
            reports_to=row.get("reports_to"),
            active=bool(row.get("active", True)),
            current_project_id=project_id,
        )

    @logfire.instrument("repo.get_team_members_for_project")
    async def get_team_members_for_project(
        self,
        project_id: str,
        include_inactive: bool = False,
    ) -> list[TeamMemberContext]:
        """Resolve project team from user_project_access joined with users by email."""
        access_result = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.USER_PROJECT_ACCESS_TABLE)
            .select(
                "user_email, project_id, access_level, project_role, project_reports_to, can_own_risks, can_review_risks, project_purview"
            )
            .eq("project_id", project_id)
            .execute()
        )

        access_rows = access_result.data or []
        if not access_rows:
            return []

        emails = [row.get("user_email") for row in access_rows if row.get("user_email")]
        if not emails:
            return []

        users_query = (
            self.supabase
            .schema(self.SCHEMA)
            .table(self.USERS_TABLE)
            .select(
                "user_email, full_name, first_name, role, app_role, department, reports_to, active"
            )
            .in_("user_email", emails)
        )
        if not include_inactive:
            users_query = users_query.eq("active", True)

        users_result = users_query.execute()
        users_rows = users_result.data or []
        users_by_email = {row.get("user_email"): row for row in users_rows if row.get("user_email")}

        members: list[TeamMemberContext] = []
        for access_row in access_rows:
            email = access_row.get("user_email")
            if not email:
                continue

            user_row = users_by_email.get(email)
            if not user_row and not include_inactive:
                continue

            members.append(
                TeamMemberContext(
                    email=email,
                    full_name=(user_row or {}).get("full_name"),
                    first_name=(user_row or {}).get("first_name"),
                    role=(user_row or {}).get("role"),
                    app_role=(user_row or {}).get("app_role"),
                    department=(user_row or {}).get("department"),
                    reports_to=(user_row or {}).get("reports_to"),
                    active=bool((user_row or {}).get("active", include_inactive)),
                    project_id=access_row.get("project_id"),
                    access_level=access_row.get("access_level"),
                    project_role=access_row.get("project_role"),
                    project_reports_to=access_row.get("project_reports_to"),
                    can_own_risks=access_row.get("can_own_risks"),
                    can_review_risks=access_row.get("can_review_risks"),
                    project_purview=access_row.get("project_purview"),
                )
            )

        return members
