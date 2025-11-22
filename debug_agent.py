import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from backend.agents.scheduling_agent import scheduling_agent
from backend.tools.p6_tools import AgentDeps
from backend.services.scheduling_service import SchedulingService
from backend.services.vector_service import VectorService
from backend.utils.safe_db import SafeP6Transaction
import logfire

# Configure logfire to print to console
logfire.configure(send_to_logfire=False)

async def main():
    service = SchedulingService()
    vector_service = VectorService()
    
    message = "Create a project 'Energy project' starting on Jan 1st 2026. It has five activities with these durations: Engineering (8 months), Procurement (12 months), Construction (8 months), Commissioning (6 months), and Handover (3 months). Link them all with start-start relationships with a lag equal to half the duration of the predecessor. Please make reasonable assumptions for any missing information (e.g. Project Short Name, WBS structure, Activity Codes) and proceed with the creation."
    
    print(f"Running agent with message: {message}")
    
    try:
        with SafeP6Transaction() as conn:
            deps = AgentDeps(service=service, vector_service=vector_service, conn=conn)
            
            # Mocking the context project ID as 1 (default)
            full_message = f"Context: Project ID 1\n\n{message}"
            
            result = await scheduling_agent.run(full_message, deps=deps)
            
            print("\nAgent Result:")
            # Handle different Pydantic AI versions result structure
            response_data = getattr(result, 'data', getattr(result, 'output', None))
            if response_data is None:
                    # Fallback to response attribute if available, or string representation
                    response_data = getattr(result, 'response', str(result))
            print(response_data)
            
    except Exception as e:
        print(f"\nError running agent: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
