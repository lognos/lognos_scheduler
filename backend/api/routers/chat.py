from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.agents.scheduling_agent import scheduling_agent
from backend.tools.p6_tools import AgentDeps
from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService
from backend.models.io import AgentResponse
from backend.utils.safe_db import SafeP6Transaction

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    project_id: int = 1 # Default context if not provided, or could be part of message

@router.post("/chat", response_model=AgentResponse)
async def chat(req: ChatRequest):
    service = SchedulingService()
    vector_service = VectorService()
    
    # Optimization: Use Session-Level Transaction
    # We wrap the entire agent execution in a single SafeP6Transaction.
    # This means we copy the DB once, perform all tool calls on the temp copy,
    # and then swap it back once at the end.
    # This avoids O(N) file copies for N tool calls.
    try:
        with SafeP6Transaction() as conn:
            deps = AgentDeps(service=service, vector_service=vector_service, conn=conn)
            
            import logfire
            # Run the agent
            # Append context to the message
            full_message = f"Context: Project ID {req.project_id}\n\n{req.message}"
            
            with logfire.span("agent_run", message=req.message, project_id=req.project_id):
                result = await scheduling_agent.run(full_message, deps=deps)
                
                # Log the result for debugging
                logfire.info("Agent run completed", result_type=str(type(result)))

                # Log all messages (steps)
                if hasattr(result, 'all_messages'):
                    for i, msg in enumerate(result.all_messages()):
                        logfire.info(f"Step {i}: {type(msg).__name__}", content=str(msg))
                
                # Handle different Pydantic AI versions result structure
                response_data = getattr(result, 'data', getattr(result, 'output', None))
                if response_data is None:
                     # Fallback to response attribute if available, or string representation
                     response_data = getattr(result, 'response', str(result))
                
                logfire.info("Agent Output", output=str(response_data))

                # Extract tool calls for visibility (optional, Pydantic AI result has them)
                # For now just return the text response
                return AgentResponse(
                    response=str(response_data),
                    tool_calls=[] # We could extract these from result.usage() or similar if needed
                )
    except Exception as e:
        import logfire
        logfire.error("Error running agent", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
