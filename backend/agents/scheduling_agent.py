from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
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
    create_schedule_ws,
    clear_schedule_ws,
    calculate_gantt_ws,
    modify_activity_ws,
    add_activity_ws,
    add_relationship_ws,
    modify_relationship_ws,
    hide_gantt_ws,
    
    # Workspace activity code tools
    assign_activity_codes_ws,
    bulk_assign_activity_codes_ws,
    remove_activity_codes_ws,
    get_activity_codes_ws,
    
    # Indexing tools
    index_project,
)
from backend.tools.ms import (
    # MS Query tools
    list_schedule_versions_ms,
    get_schedule_overview_ms,
    list_activities_ms,
    get_activity_ms,
    get_project_constraints_ms,
    get_calendar_ms,
    
    # MS Workspace tools
    load_schedule_ms,
    
    # MS Version tools
    create_schedule_subversion_ms,
    promote_subversion_ms,
)
from backend.models.io import AgentOutput
from backend.config.settings import settings

# Usage limits to pass at runtime (prevents runaway loops)
SCHEDULING_USAGE_LIMITS = UsageLimits(
    request_limit=30,  # Maximum requests per run (increased for complex schedules)
    input_tokens_limit=500_000,  # Input token limit (Gemini 2.5 Flash supports 1M)
    output_tokens_limit=32_000,  # Output token limit (increased as safety net)
)


def filter_tool_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Remove tool calls and returns from historical messages to reduce token usage.
    
    This processor filters out ToolCallPart and ToolReturnPart from PAST conversation
    turns, keeping only user prompts, system prompts, and final text responses.
    
    The current turn's tool calls are preserved because they're part of the active
    agent run and are needed for the agentic loop to work correctly.
    
    This is critical because:
    1. Tool returns (e.g., list_activities_p6) can be thousands of tokens
    2. Each conversation turn accumulates more tool results
    3. Without filtering, input context can grow to 100k+ tokens
    4. Large contexts cause Gemini to generate extremely verbose responses (65k+ tokens)
    """
    if not messages:
        return messages
    
    filtered: list[ModelMessage] = []
    
    # Get the run_id of the current (most recent) turn to preserve it
    current_run_id = None
    for msg in reversed(messages):
        if hasattr(msg, 'run_id') and msg.run_id:
            current_run_id = msg.run_id
            break
    
    for msg in messages:
        # Preserve current turn messages completely (needed for agentic loop)
        if hasattr(msg, 'run_id') and msg.run_id == current_run_id:
            filtered.append(msg)
            continue
        
        # For historical messages, filter out tool-related parts
        if isinstance(msg, ModelRequest):
            # Keep only SystemPromptPart and UserPromptPart
            filtered_parts = [
                part for part in msg.parts
                if isinstance(part, (SystemPromptPart, UserPromptPart))
            ]
            if filtered_parts:
                # Create a new ModelRequest with only the filtered parts
                # Note: ModelRequest doesn't have timestamp field
                new_msg = ModelRequest(
                    parts=filtered_parts,
                    instructions=msg.instructions,
                    run_id=msg.run_id,
                )
                filtered.append(new_msg)
                
        elif isinstance(msg, ModelResponse):
            # Keep only TextPart responses (final answers, not tool calls)
            filtered_parts = [
                part for part in msg.parts
                if isinstance(part, TextPart)
            ]
            if filtered_parts:
                # Create a new ModelResponse with only the filtered parts
                new_msg = ModelResponse(
                    parts=filtered_parts,
                    model_name=msg.model_name,
                    timestamp=msg.timestamp,
                    run_id=msg.run_id,
                )
                filtered.append(new_msg)
        else:
            # Keep any other message types as-is
            filtered.append(msg)
    
    return filtered

# Define the Agent with structured output
scheduling_agent = Agent(
    settings.GOOGLE_DEFAULT_MODEL,
    deps_type=AgentDeps,
    output_type=AgentOutput,  # Structured output: SchedulingResponse | ClarificationRequest | ErrorResponse
    retries=5,  # Increased retries for Gemini empty response issues
    model_settings=ModelSettings(
        temperature=0.3,  # Lower temperature for more consistent responses
    ),
    history_processors=[filter_tool_history],  # Filter tool calls from history to reduce tokens
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
        create_schedule_ws,
        clear_schedule_ws,
        calculate_gantt_ws,
        modify_activity_ws,
        add_activity_ws,
        add_relationship_ws,
        modify_relationship_ws,
        hide_gantt_ws,
        
        # Workspace activity code tools
        assign_activity_codes_ws,
        bulk_assign_activity_codes_ws,
        remove_activity_codes_ws,
        get_activity_codes_ws,
        
        # Indexing tools
        index_project,
        
        # MS Project (Supabase) Query tools
        list_schedule_versions_ms,
        get_schedule_overview_ms,
        list_activities_ms,
        get_activity_ms,
        get_project_constraints_ms,
        get_calendar_ms,
        
        # MS Project Workspace tools
        load_schedule_ms,
        
        # MS Project Version tools
        create_schedule_subversion_ms,
        promote_subversion_ms,
    ],
)
