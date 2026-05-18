from inspect import signature

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
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
    
    # Workspace tools
    get_workspace_status_ws,
    get_driving_path_ws,
    create_schedule_ws,
    clear_schedule_ws,
    calculate_gantt_ws,
    modify_activity_ws,
    add_activity_ws,
    add_relationship_ws,
    modify_relationship_ws,
    delete_relationship_ws,
    delete_activity_ws,
    hide_gantt_ws,
    
    # Workspace activity code tools
    assign_activity_codes_ws,
    bulk_assign_activity_codes_ws,
    remove_activity_codes_ws,
    get_activity_codes_ws,
    
    # What-if baseline tools
    snapshot_baseline_ws,
    get_whatif_comparison_ws,
    
    # Context tools
    get_team_data,
)
from backend.tools.ms import (
    # MS Query tools
    list_schedule_versions_ms,
    get_schedule_overview_ms,
    list_activities_ms,
    search_activities_ms,
    get_activity_ms,
    get_project_constraints_ms,
    get_calendar_ms,
    
    # MS Workspace tools
    load_schedule_ms,
    
    # MS Version tools
    create_schedule_subversion_ms,
    promote_subversion_ms,
)
from backend.email_tools import (
    check_email_service_health_tool,
    create_email_draft_tool,
    list_email_drafts_tool,
    modify_email_draft_tool,
    send_email_draft_tool,
    send_email_tool,
)
from backend.models.io import AgentOutput
from backend.config.settings import settings

# Usage limits to pass at runtime (prevents runaway loops)
SCHEDULING_USAGE_LIMITS = UsageLimits(
    request_limit=30,  # Maximum requests per run (increased for complex schedules)
    request_tokens_limit=500_000,  # Input token limit (Gemini 2.5 Flash supports 1M)
    response_tokens_limit=32_000,  # Output token limit (increased as safety net)
)


def filter_tool_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Remove tool calls and returns from historical messages to reduce token usage.
    
    This processor filters out ToolCallPart and ToolReturnPart from PAST conversation
    turns, keeping only user prompts, system prompts, and final text responses.
    
    The current turn's tool calls are preserved because they're part of the active
    agent run and are needed for the agentic loop to work correctly.
    
    Additionally, detects repeated identical tool calls in the current run and
    injects a stop signal to prevent infinite loops.
    
    This is critical because:
    1. Tool returns (e.g., list_activities_ms) can be thousands of tokens
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

    # ---- Loop guard: detect repeated identical tool calls in current run ----
    # Count (tool_name, args_str) occurrences across current-run ModelResponse messages
    MAX_IDENTICAL_CALLS = 2
    call_counts: dict[tuple[str, str], int] = {}
    for msg in filtered:
        if not (hasattr(msg, 'run_id') and msg.run_id == current_run_id):
            continue
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    key = (part.tool_name, part.args_as_json_str())
                    call_counts[key] = call_counts.get(key, 0) + 1

    # If any tool was called > MAX_IDENTICAL_CALLS with identical args, inject a
    # warning into the latest ToolReturnPart(s) for that tool so the model sees
    # "STOP: you already called this tool N times with the same arguments"
    repeated_tools = {k for k, v in call_counts.items() if v > MAX_IDENTICAL_CALLS}
    if repeated_tools:
        # Walk filtered in reverse to find the latest ToolReturnPart for
        # each repeated tool and prepend a stop warning to its content
        patched_return_keys: set[tuple[str, str]] = set()
        for i in range(len(filtered) - 1, -1, -1):
            msg = filtered[i]
            if not isinstance(msg, ModelRequest):
                continue
            if not (hasattr(msg, 'run_id') and msg.run_id == current_run_id):
                continue
            new_parts = []
            for part in msg.parts:
                if (
                    isinstance(part, ToolReturnPart)
                    and hasattr(part, 'tool_name')
                ):
                    # Identify which call this return belongs to by
                    # matching tool_name against repeated set
                    for rk in repeated_tools:
                        if rk[0] == part.tool_name and rk not in patched_return_keys:
                            # Inject stop signal
                            warning = (
                                f"STOP REPEATING: You have called {part.tool_name} "
                                f"{call_counts[rk]} times with identical arguments and "
                                "received the same result each time. This tool cannot "
                                "fulfill this request differently. You MUST now respond "
                                "to the user with the information you have, or explain "
                                "that this operation is not currently supported. Do NOT "
                                "call this tool again with the same arguments."
                            )
                            original = part.model_response_str() if hasattr(part, 'model_response_str') else str(part.content if hasattr(part, 'content') else '')
                            patched = ToolReturnPart(
                                tool_name=part.tool_name,
                                content=f"{warning}\n\nOriginal result: {original}",
                                tool_call_id=part.tool_call_id if hasattr(part, 'tool_call_id') else None,
                            )
                            new_parts.append(patched)
                            patched_return_keys.add(rk)
                            break
                    else:
                        new_parts.append(part)
                else:
                    new_parts.append(part)
            if new_parts != list(msg.parts):
                filtered[i] = ModelRequest(
                    parts=new_parts,
                    instructions=msg.instructions,
                    run_id=msg.run_id,
                )
    
    return filtered

def _build_agent(system_prompt: str, tools: list) -> Agent:
    agent_kwargs = dict(
        deps_type=AgentDeps,
        retries=5,
        model_settings=ModelSettings(
            temperature=0.3,
        ),
        system_prompt=system_prompt,
        tools=tools,
    )
    agent_parameters = signature(Agent).parameters
    if "output_type" in agent_parameters:
        agent_kwargs["output_type"] = AgentOutput
    else:
        agent_kwargs["result_type"] = AgentOutput
    if "history_processors" in agent_parameters:
        agent_kwargs["history_processors"] = [filter_tool_history]

    return Agent(settings.GOOGLE_DEFAULT_MODEL, **agent_kwargs)


WORKSPACE_TOOLS = [
    get_workspace_status_ws,
    get_driving_path_ws,
    create_schedule_ws,
    clear_schedule_ws,
    calculate_gantt_ws,
    modify_activity_ws,
    add_activity_ws,
    add_relationship_ws,
    modify_relationship_ws,
    delete_relationship_ws,
    delete_activity_ws,
    hide_gantt_ws,
    assign_activity_codes_ws,
    bulk_assign_activity_codes_ws,
    remove_activity_codes_ws,
    get_activity_codes_ws,
    # What-if baseline tools
    snapshot_baseline_ws,
    get_whatif_comparison_ws,
]


MSP_TOOLS = [
    list_schedule_versions_ms,
    get_schedule_overview_ms,
    list_activities_ms,
    search_activities_ms,
    get_activity_ms,
    get_project_constraints_ms,
    get_calendar_ms,
    load_schedule_ms,
    create_schedule_subversion_ms,
    promote_subversion_ms,
]


COMMON_TOOLS = [
    get_team_data,
    check_email_service_health_tool,
]

if settings.EMAIL_ENABLED and settings.ENABLE_EMAIL_PHASE1_SEND:
    COMMON_TOOLS.extend(
        [
            create_email_draft_tool,
            list_email_drafts_tool,
            modify_email_draft_tool,
            send_email_draft_tool,
            send_email_tool,
        ]
    )


_MSP_SYSTEM_PROMPT = PromptLoader.compose_prompts([
    "scheduler_general.xml.j2",
    "scheduler_msp.xml.j2",
])

_msp_scheduling_agent = _build_agent(
    system_prompt=_MSP_SYSTEM_PROMPT,
    tools=MSP_TOOLS + WORKSPACE_TOOLS + COMMON_TOOLS,
)


def get_scheduling_agent(project_type: str = "msp") -> Agent:
    """Return the MS/workspace scheduling agent."""
    if project_type.lower() == "p6":
        raise ValueError("P6 schedules are no longer supported by this MS-only service.")
    return _msp_scheduling_agent


# Backward compatibility alias (defaults to MSP)
scheduling_agent = _msp_scheduling_agent
