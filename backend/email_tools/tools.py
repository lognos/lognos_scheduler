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


@logfire.instrument("tool.create_email_draft")
async def create_email_draft_tool(
    ctx: RunContext[Any],
    recipient_email: str,
    subject: str,
    message_body: str,
    recipient_name: str | None = None,
    cc_emails: list[str] | None = None,
) -> dict:
    email_service = getattr(ctx.deps, "email_service", None)
    if email_service is None:
        return {"success": False, "message": "Email service dependency is not configured"}

    result = await email_service.create_draft(
        recipient_email=recipient_email,
        subject=subject,
        message_body=message_body,
        recipient_name=recipient_name,
        cc_emails=cc_emails,
    )
    return result.model_dump(mode="json")


@logfire.instrument("tool.list_email_drafts")
async def list_email_drafts_tool(ctx: RunContext[Any], limit: int = 10) -> dict:
    email_service = getattr(ctx.deps, "email_service", None)
    if email_service is None:
        return {"success": False, "message": "Email service dependency is not configured", "count": 0, "drafts": []}

    try:
        normalized_limit = max(1, min(limit, 50))
        drafts = await email_service.list_drafts(limit=normalized_limit)
        return {
            "success": True,
            "count": len(drafts),
            "drafts": [draft.model_dump(mode="json") for draft in drafts],
        }
    except Exception as error:
        return {
            "success": False,
            "message": "Failed to list drafts",
            "error": str(error),
            "count": 0,
            "drafts": [],
        }


@logfire.instrument("tool.modify_email_draft")
async def modify_email_draft_tool(
    ctx: RunContext[Any],
    draft_id: str,
    subject: str | None = None,
    message_body: str | None = None,
    recipient_email: str | None = None,
    cc_emails: list[str] | None = None,
) -> dict:
    email_service = getattr(ctx.deps, "email_service", None)
    if email_service is None:
        return {"success": False, "message": "Email service dependency is not configured"}

    if not any([subject is not None, message_body is not None, recipient_email is not None, cc_emails is not None]):
        return {
            "success": False,
            "draft_id": draft_id,
            "message": "No updates provided. Set at least one field to modify.",
        }

    result = await email_service.modify_draft(
        draft_id=draft_id,
        subject=subject,
        message_body=message_body,
        recipient_email=recipient_email,
        cc_emails=cc_emails,
    )
    return result.model_dump(mode="json")


@logfire.instrument("tool.send_email_draft")
async def send_email_draft_tool(
    ctx: RunContext[Any],
    draft_id: str,
    confirm_send: bool,
) -> dict:
    email_service = getattr(ctx.deps, "email_service", None)
    if email_service is None:
        return {"success": False, "message": "Email service dependency is not configured"}

    if not confirm_send:
        return {
            "success": False,
            "draft_id": draft_id,
            "message": "Send blocked. Set confirm_send=true only when the user explicitly confirms sending.",
        }

    result = await email_service.send_draft(draft_id=draft_id)
    return result.model_dump(mode="json")


@logfire.instrument("tool.send_email")
async def send_email_tool(
    ctx: RunContext[Any],
    recipient_email: str,
    subject: str,
    message_body: str,
    confirm_send: bool,
    recipient_name: str | None = None,
    cc_emails: list[str] | None = None,
) -> dict:
    email_service = getattr(ctx.deps, "email_service", None)
    if email_service is None:
        return {"success": False, "message": "Email service dependency is not configured"}

    if not confirm_send:
        return {
            "success": False,
            "message": "Send blocked. Set confirm_send=true only when the user explicitly confirms sending.",
            "to": [recipient_email],
            "subject": subject,
        }

    result = await email_service.send_email(
        recipient_email=recipient_email,
        subject=subject,
        message_body=message_body,
        recipient_name=recipient_name,
        cc_emails=cc_emails,
    )
    return result.model_dump(mode="json")
