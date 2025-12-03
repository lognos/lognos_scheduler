from pydantic_ai import Agent, UsageLimits
from pydantic_ai.settings import ModelSettings
from backend.prompt.loader import PromptLoader
from backend.tools.p6_tools import (
    create_activity_tool, 
    create_relationship_tool, 
    update_progress_tool, 
    get_activity_details_tool, 
    update_activity_status_tool, 
    create_project_tool,
    list_projects_tool,
    list_activities_tool,
    search_activity_tool, 
    index_project_tool,
    delete_relationship_tool,
    update_relationship_tool,
    list_activity_codes_tool,
    get_activity_current_codes_tool,
    assign_activity_codes_tool,
    remove_activity_codes_tool,
    bulk_assign_activity_codes_tool,
    # Gantt workspace tools
    load_schedule_to_workspace_tool,
    calculate_and_display_gantt_tool,
    modify_activity_in_workspace_tool,
    add_activity_to_workspace_tool,
    add_relationship_to_workspace_tool,
    hide_gantt_panel_tool,
    get_workspace_status_tool,
    AgentDeps
)
from backend.models.io import AgentOutput
from backend.config.settings import settings

# Usage limits to pass at runtime (prevents runaway loops)
SCHEDULING_USAGE_LIMITS = UsageLimits(
    request_limit=25,  # Maximum requests per run
    input_tokens_limit=50_000,  # Input token limit
    output_tokens_limit=8_000,  # Output token limit
)

# Define the Agent with structured output
scheduling_agent = Agent(
    settings.GOOGLE_DEFAULT_MODEL,
    deps_type=AgentDeps,
    output_type=AgentOutput,  # Structured output: SchedulingResponse | ClarificationRequest | ErrorResponse
    retries=5,  # Increased retries for Gemini empty response issues
    model_settings=ModelSettings(
        temperature=0.3,  # Lower temperature for more consistent responses
    ),
    system_prompt=PromptLoader.get_prompt("scheduler_system.xml.j2"),
    tools=[
        create_activity_tool, 
        create_relationship_tool, 
        update_progress_tool, 
        get_activity_details_tool, 
        update_activity_status_tool, 
        create_project_tool,
        list_projects_tool,
        list_activities_tool,
        search_activity_tool,
        index_project_tool,
        delete_relationship_tool,
        update_relationship_tool,
        list_activity_codes_tool,
        get_activity_current_codes_tool,
        assign_activity_codes_tool,
        remove_activity_codes_tool,
        bulk_assign_activity_codes_tool,
        # Gantt workspace tools
        load_schedule_to_workspace_tool,
        calculate_and_display_gantt_tool,
        modify_activity_in_workspace_tool,
        add_activity_to_workspace_tool,
        add_relationship_to_workspace_tool,
        hide_gantt_panel_tool,
        get_workspace_status_tool,
    ],
)
