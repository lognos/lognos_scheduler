"""Indexing operations - tools for vector index management."""

import logfire
from pydantic_ai import RunContext, ModelRetry
from backend.tools._base import AgentDeps
from backend.models.io import IndexProjectRequest


@logfire.instrument("index_project")
async def index_project(ctx: RunContext[AgentDeps], req: IndexProjectRequest) -> str:
    """Index a P6 project for vector-based activity search.
    
    Use this tool to enable natural language search on a project's activities.
    Generates embeddings for all activities in the project. Should be called
    before search_activities_p6 if searches return no results.
    
    Args:
        ctx: Runtime context with dependencies (service, vector_service, connection).
        req: Request containing the proj_id to index.
    
    Returns:
        Success message confirming indexing is complete.
    
    Raises:
        ModelRetry: If vector service unavailable (system configuration issue).
    """
    if not ctx.deps.vector_service:
        raise ModelRetry("Vector search service is not available. Activity search by description is disabled.")

    try:
        ctx.deps.vector_service.index_project(req.proj_id, conn=ctx.deps.conn)
        return f"Successfully indexed project {req.proj_id}. You can now search for activities by description."
    except Exception as e:
        logfire.error("Error in index_project", error=str(e))
        return f"Error indexing project: {str(e)}"
