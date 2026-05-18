"""Database repository for querying Supabase."""

import logfire
from supabase import create_async_client, AsyncClient
from postgrest.exceptions import APIError

from sch_backend.config.settings import settings
from sch_backend.models.domain import Project


class DatabaseRepository:
    """Repository for database operations using supabase-py async client."""

    # def __init__(self):
    #     """Initialize repository with Supabase async client."""
    #     self.client: AsyncClient = create_async_client(
    #         str(settings.supabase_url),
    #         settings.supabase_service_role_key,
    #     )
    def __init__(self):
        """Initialize repository with Supabase async client."""
        self.client: AsyncClient | None = None
        self._schema_client: AsyncClient | None = None
        self._url = str(settings.SUPABASE_URL)
        self._key = settings.SUPABASE_SERVICE_ROLE_KEY

    async def _ensure_client(self):
        """Lazy initialization of async client."""
        if self.client is None:
            self.client = await create_async_client(self._url, self._key)
            self._schema_client = self.client.postgrest.schema("lognos_comm")

    @logfire.instrument("DatabaseRepository.query_information_schema")
    async def query_information_schema(self, schema: str) -> list[str]:
        """
        Query the information schema for table names.

        Args:
            schema: The database schema to query

        Returns:
            A list of table names

        Raises:
            APIError: If the query fails
        """
        await self._ensure_client()
        logfire.debug("Querying information schema for tables", schema=schema)
        try:
            # PostgREST query to information_schema.tables
            # We need to switch the schema for this specific query
            response = await (
                self.client.postgrest.schema("information_schema")
                .from_("tables")
                .select("table_name")
                .eq("table_schema", schema)
                .execute()
            )

            if not response.data:
                logfire.warn("No tables found in schema", schema=schema)
                return []

            # Extract table names from the response
            table_names = [item["table_name"] for item in response.data]
            logfire.info(
                "Found tables in schema",
                schema=schema,
                table_count=len(table_names),
            )
            return table_names

        except APIError as e:
            logfire.error(
                "Failed to query information schema",
                error=str(e),
                schema=schema,
            )
            raise

    @logfire.instrument("DatabaseRepository.rpc")
    async def rpc(self, function_name: str, params: dict) -> list[dict]:
        """
        Call a remote procedure (RPC) function.

        Args:
            function_name: The name of the RPC function to call
            params: The parameters to pass to the function

        Returns:
            The result of the RPC call

        Raises:
            APIError: If the RPC call fails
        """
        await self._ensure_client()
        logfire.debug(
            "Calling RPC function", function_name=function_name, params=params
        )
        try:
            response = await self.client.rpc(function_name, params).execute()

            if not response.data:
                logfire.warn("RPC returned no data", function_name=function_name)
                return []

            logfire.info(
                "RPC call successful",
                function_name=function_name,
                result_count=len(response.data)
                if isinstance(response.data, list)
                else 1,
            )
            return response.data if isinstance(response.data, list) else [response.data]

        except APIError as e:
            logfire.error(
                "Failed to call RPC",
                error=str(e),
                function_name=function_name,
            )
            raise

    @logfire.instrument("DatabaseRepository.get_project_by_id")
    async def get_project_by_id(self, project_id: str) -> Project | None:
        """
        Get project by ID.
        """
        await self._ensure_client()
        try:
            response = await (
                self._schema_client.from_("projects")
                .select("*")
                .eq("project_id", project_id)
                .execute()
            )
            if response.data:
                return Project(**response.data[0])
            return None
        except Exception as e:
            logfire.error(f"Failed to get project {project_id}: {e}")
            return None

    @logfire.instrument("DatabaseRepository.check_user_project_access")
    async def check_user_project_access(self, user_email: str, project_id: str) -> bool:
        """
        Check if user has access to project.
        """
        await self._ensure_client()
        try:
            response = await (
                self._schema_client.from_("user_project_access")
                .select("id")
                .eq("user_email", user_email)
                .eq("project_id", project_id)
                .execute()
            )
            return len(response.data) > 0
        except Exception as e:
            logfire.error(f"Failed to check access for {user_email} -> {project_id}: {e}")
            return False

    @logfire.instrument("DatabaseRepository.get_user_projects")
    async def get_user_projects(self, user_email: str) -> list[Project]:
        """
        Get all projects a user has access to.
        """
        await self._ensure_client()
        try:
            # 1. Get project IDs from access table
            access_response = await (
                self._schema_client.from_("user_project_access")
                .select("project_id")
                .eq("user_email", user_email)
                .execute()
            )
            
            if not access_response.data:
                return []
                
            project_ids = [row["project_id"] for row in access_response.data]
            
            # 2. Get project details
            projects_response = await (
                self._schema_client.from_("projects")
                .select("*")
                .in_("project_id", project_ids)
                .execute()
            )
            
            return [Project(**row) for row in projects_response.data]
            
        except Exception as e:
            logfire.error(f"Failed to get user projects for {user_email}: {e}")
            return []
