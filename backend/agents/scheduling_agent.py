from pydantic_ai import Agent
from backend.tools.p6_tools import create_activity_tool, create_relationship_tool, update_progress_tool, get_activity_details_tool, update_activity_status_tool, AgentDeps
from backend.config.settings import settings

# Define the Agent
scheduling_agent = Agent(
    settings.GOOGLE_DEFAULT_MODEL,
    deps_type=AgentDeps,
    system_prompt=(
        "You are an expert Primavera P6 Scheduler Agent. "
        "You have direct access to modify the P6 database to help users manage their schedules. "
        "You can create activities, link them with relationships, and update their progress. "
        "Always verify that the user provides necessary details (Project ID, WBS ID, Activity Codes). "
        "If details are missing, ask the user for clarification. "
        "When creating relationships, ensure you understand the predecessor and successor. "
        "When updating activity status, ALWAYS check the current status first using 'get_activity_details_tool'. "
        "Enforce P6 business rules: 'In Progress' requires Actual Start; 'Completed' requires Actual Start and Actual Finish. "
        "Be concise and professional."
    ),
    tools=[create_activity_tool, create_relationship_tool, update_progress_tool, get_activity_details_tool, update_activity_status_tool],
)
