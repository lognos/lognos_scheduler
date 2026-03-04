from typing import Any

import logfire
from pydantic_ai import RunContext


@logfire.instrument("tool.check_email_service_health")
async def check_email_service_health_tool(ctx: RunContext[Any]) -> dict:
    email_service = getattr(ctx.deps, "email_service", None)
    if email_service is None:
        return {
            "status": "disabled",
            "message": "Email service dependency is not configured",
        }

    health_status = await email_service.check_health()
    return health_status.model_dump()
