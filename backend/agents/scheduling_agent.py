from pydantic_ai import Agent, UsageLimits
from pydantic_ai.settings import ModelSettings
from backend.prompt.loader import PromptLoader
from backend.tools import (
    # Base
    AgentDeps,
    
    # P6 Query tools
    get_activity_p6,
    search_activities_p6,
    list_projects_p6,
    list_activities_p6,
    list_activity_codes_p6,
    get_activity_codes_p6,
    
    # P6 Activity tools
    create_activity_p6,
    update_activity_status_p6,
    update_progress_p6,
    
    # P6 Relationship tools
    create_relationship_p6,
    update_relationship_p6,
    delete_relationship_p6,
    
    # P6 Project tools
    create_project_p6,
    
    # P6 Activity code tools
    assign_activity_codes_p6,
    remove_activity_codes_p6,
    bulk_assign_activity_codes_p6,
    
    # Workspace tools
    get_workspace_status_ws,
    load_schedule_ws,
    calculate_gantt_ws,
    modify_activity_ws,
    add_activity_ws,
    add_relationship_ws,
    modify_relationship_ws,
    hide_gantt_ws,
    
    # Indexing tools
    index_project,
)
from backend.models.io import AgentOutput
from backend.config.settings import settings

# Usage limits to pass at runtime (prevents runaway loops)
SCHEDULING_USAGE_LIMITS = UsageLimits(
    request_limit=25,  # Maximum requests per run
    input_tokens_limit=100_000,  # Input token limit (Gemini 2.5 Flash supports 1M)
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
        # P6 Query tools
        get_activity_p6,
        search_activities_p6,
        list_projects_p6,
        list_activities_p6,
        list_activity_codes_p6,
        get_activity_codes_p6,
        
        # P6 Activity tools
        create_activity_p6,
        update_activity_status_p6,
        update_progress_p6,
        
        # P6 Relationship tools
        create_relationship_p6,
        update_relationship_p6,
        delete_relationship_p6,
        
        # P6 Project tools
        create_project_p6,
        
        # P6 Activity code tools
        assign_activity_codes_p6,
        remove_activity_codes_p6,
        bulk_assign_activity_codes_p6,
        
        # Workspace tools
        get_workspace_status_ws,
        load_schedule_ws,
        calculate_gantt_ws,
        modify_activity_ws,
        add_activity_ws,
        add_relationship_ws,
        modify_relationship_ws,
        hide_gantt_ws,
        
        # Indexing tools
        index_project,
    ],
)
