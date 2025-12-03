from pydantic_ai import RunContext
import logfire
from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService
from backend.models.io import ActivityCreateRequest, RelationshipCreateRequest, ProgressUpdateRequest, ActivityDetailsRequest, ActivityStatusUpdateRequest, ProjectCreateRequest, SearchActivityRequest, IndexProjectRequest, RelationshipDeleteRequest, RelationshipUpdateRequest, ListProjectsRequest

# We define the dependencies class
class AgentDeps:
    def __init__(self, service: SchedulingService, vector_service: VectorService = None, conn=None):
        self.service = service
        self.vector_service = vector_service
        self.conn = conn

@logfire.instrument("delete_relationship_tool")
async def delete_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipDeleteRequest) -> str:
    """
    Deletes an existing relationship between two activities.
    """
    try:
        return ctx.deps.service.delete_relationship(req, conn=ctx.deps.conn)
    except Exception as e:
        logfire.error("Error in delete_relationship_tool", error=str(e))
        return f"Error deleting relationship: {str(e)}"

@logfire.instrument("update_relationship_tool")
async def update_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipUpdateRequest) -> str:
    """
    Updates an existing relationship (Lag or Type).
    """
    try:
        return ctx.deps.service.update_relationship(req, conn=ctx.deps.conn)
    except Exception as e:
        logfire.error("Error in update_relationship_tool", error=str(e))
        return f"Error updating relationship: {str(e)}"

@logfire.instrument("search_activity_tool")
async def search_activity_tool(ctx: RunContext[AgentDeps], req: SearchActivityRequest) -> str:
    """
    Searches for activities using natural language description.
    Returns a list of matching activities with their IDs and similarity scores.
    """
    if not ctx.deps.vector_service:
        return "Vector search service is not available."
    
    try:
        results = ctx.deps.vector_service.search_activities(req.query, req.proj_id, threshold=0.5, conn=ctx.deps.conn)
        if not results:
            return "No matching activities found."
        
        # Format results for the agent
        response = "Found matching activities:\n"
        for task_id, score in results:
            # We need to fetch details to show the user (Code, Name)
            # The vector service returns task_id.
            # We can use the repo to get details.
            # Since we are in the tool, we can access the repo via service.
            details = ctx.deps.service.repo.get_activity_details(ctx.deps.conn, task_id)
            # Wait, get_activity_details takes task_id but returns dict with status etc.
            # We need Code and Name.
            # Let's add a method to repo or just query here?
            # Better to add a method to repo or use existing one if it returns what we need.
            # get_activity_details returns status, pct, dates. Not Code/Name.
            # But we have task_id.
            # Let's fetch Code and Name directly or add a helper.
            # For now, I'll just show the ID if I can't easily get the name without modifying repo again.
            # Actually, I should modify repo to get basic info by ID.
            # Or I can use `get_task_text_data` logic but for single ID.
            
            # Let's do a quick query here using the connection, or better, add a helper in service/repo.
            # I'll add a helper in SchedulingService to get activity info by ID.
            # But I can't modify service in this tool call easily.
            # I'll use a direct SQL query here for now as a pragmatic solution, 
            # or better, rely on the fact that the agent can look up details if needed.
            # But the user wants to know WHICH activity it is.
            
            # Let's use the connection to get the code and name.
            cursor = ctx.deps.conn.cursor()
            cursor.execute("SELECT TASK_CODE, TASK_NAME FROM TASK WHERE TASK_ID = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                response += f"- {row[0]}: {row[1]} (Score: {score:.2f})\n"
            else:
                response += f"- ID {task_id} (Score: {score:.2f})\n"
                
        return response
    except Exception as e:
        logfire.error("Error in search_activity_tool", error=str(e))
        return f"Error searching activities: {str(e)}"

@logfire.instrument("index_project_tool")
async def index_project_tool(ctx: RunContext[AgentDeps], req: IndexProjectRequest) -> str:
    """
    Indexes a project for vector search. Generates embeddings for all activities.
    """
    if not ctx.deps.vector_service:
        return "Vector search service is not available."

    try:
        ctx.deps.vector_service.index_project(req.proj_id, conn=ctx.deps.conn)
        return f"Successfully indexed project {req.proj_id}."
    except Exception as e:
        logfire.error("Error in index_project_tool", error=str(e))
        return f"Error indexing project: {str(e)}"

@logfire.instrument("get_activity_details_tool")
async def get_activity_details_tool(ctx: RunContext[AgentDeps], req: ActivityDetailsRequest) -> dict | str:
    """
    Retrieves current details (status, dates, % complete) for an activity.
    Returns: status_code, phys_complete_pct, act_start_date, act_end_date, target_start_date (Planned Start), target_end_date (Planned Finish).
    """
    try:
        return ctx.deps.service.get_activity_details(req, conn=ctx.deps.conn)
    except Exception as e:
        logfire.error("Error in get_activity_details_tool", error=str(e))
        return f"Error retrieving details: {str(e)}"

@logfire.instrument("update_activity_status_tool")
async def update_activity_status_tool(ctx: RunContext[AgentDeps], req: ActivityStatusUpdateRequest) -> str:
    """
    Updates the status of an activity (Not Started, In Progress, Completed) with strict validation.
    """
    try:
        return ctx.deps.service.update_activity_status(req, conn=ctx.deps.conn)
    except Exception as e:
        logfire.error("Error in update_activity_status_tool", error=str(e))
        return f"Error updating status: {str(e)}"

@logfire.instrument("create_activity_tool")
async def create_activity_tool(ctx: RunContext[AgentDeps], req: ActivityCreateRequest) -> str:
    """
    Creates a new activity in the P6 schedule.
    """
    try:
        task_id = ctx.deps.service.create_activity(req, conn=ctx.deps.conn)
        return f"Successfully created activity {req.task_code} with ID {task_id}."
    except Exception as e:
        logfire.error("Error in create_activity_tool", error=str(e))
        return f"Error creating activity: {str(e)}"

@logfire.instrument("create_relationship_tool")
async def create_relationship_tool(ctx: RunContext[AgentDeps], req: RelationshipCreateRequest) -> str:
    """
    Creates a relationship between two activities.
    """
    try:
        rel_id = ctx.deps.service.create_relationship(req, conn=ctx.deps.conn)
        return f"Successfully linked {req.pred_task_code} -> {req.succ_task_code} ({req.pred_type})."
    except Exception as e:
        logfire.error("Error in create_relationship_tool", error=str(e))
        return f"Error creating relationship: {str(e)}"

@logfire.instrument("update_progress_tool")
async def update_progress_tool(ctx: RunContext[AgentDeps], req: ProgressUpdateRequest) -> str:
    """
    Updates the physical % complete of an activity.
    """
    try:
        result = ctx.deps.service.update_progress(req, conn=ctx.deps.conn)
        return result
    except Exception as e:
        logfire.error("Error in update_progress_tool", error=str(e))
        return f"Error updating progress: {str(e)}"

@logfire.instrument("create_project_tool")
async def create_project_tool(ctx: RunContext[AgentDeps], req: ProjectCreateRequest) -> str:
    """
    Creates a new project in the P6 database.
    """
    try:
        proj_id, wbs_id = ctx.deps.service.create_project(req, conn=ctx.deps.conn)
        return f"Successfully created project '{req.project_short_name}' with ID {proj_id}. Root WBS ID is {wbs_id}."
    except Exception as e:
        logfire.error("Error in create_project_tool", error=str(e))
        return f"Error creating project: {str(e)}"

@logfire.instrument("list_projects_tool")
async def list_projects_tool(ctx: RunContext[AgentDeps], req: ListProjectsRequest) -> str:
    """
    Lists all projects in the P6 database with their key information.
    Returns a formatted table of projects with ID, name, dates, activity count, and description.
    """
    try:
        projects = ctx.deps.service.list_projects(req, conn=ctx.deps.conn)
        
        if not projects:
            return "No projects found in the database."
        
        # Build formatted table output
        lines = ["Available Projects:", ""]
        
        # Table header
        header = f"{'PROJ_ID':<10} {'Short Name':<15} {'Project Name':<35} {'Plan Start':<12} {'Plan End':<12} {'Activities':<10} {'Description'}"
        lines.append(header)
        lines.append("-" * 130)
        
        for proj in projects:
            proj_id = proj.get('PROJ_ID', '-')
            short_name = proj.get('PROJ_SHORT_NAME', '-') or '-'
            project_name = proj.get('PROJECT_NAME', '-') or '-'
            plan_start = proj.get('PLAN_START_DATE', '-') or '-'
            plan_end = proj.get('PLAN_END_DATE', '-') or '-'
            activity_count = proj.get('ACTIVITY_COUNT', 0) or 0
            description = proj.get('DESCRIPTION') or '-'
            
            # Truncate long fields
            if len(project_name) > 33:
                project_name = project_name[:30] + '...'
            if len(short_name) > 13:
                short_name = short_name[:10] + '...'
            if len(description) > 50:
                description = description[:47] + '...'
            
            row = f"{proj_id:<10} {short_name:<15} {project_name:<35} {plan_start:<12} {plan_end:<12} {activity_count:<10} {description}"
            lines.append(row)
        
        lines.append("")
        lines.append(f"Total: {len(projects)} project(s)")
        
        return "\n".join(lines)
    except Exception as e:
        logfire.error("Error in list_projects_tool", error=str(e))
        return f"Error listing projects: {str(e)}"
