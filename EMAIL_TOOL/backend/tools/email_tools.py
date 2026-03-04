"""Email tools for Pydantic AI agent."""

import logfire
from typing import Any
from pydantic_ai import RunContext

from backend.models.domain import EmailRecipient, EmailMessage
from backend.config.settings import settings
from backend.utils.formatting import convert_markdown_to_html
from backend.utils.email_templates import apply_email_template
from typing import Literal


@logfire.instrument("tool.send_email")
async def send_email_tool(
    ctx: RunContext[Any],
    recipient_email: str,
    subject: str,
    message_body: str,
    recipient_name: str | None = None,
    sender_context: str | None = None,
) -> dict:
    """
    Send an email to a recipient.

    CRITICAL: Email signatures must identify the AGENT, not the requesting user.

    The message_body you provide should end with an appropriate agent signature:
    - Spanish: "Atentamente,\nAgent de Riesgos LOGNOS"
    - English: "Best regards,\nLOGNOS Risk Agent"

    NEVER include user names in the signature (e.g., "John Smith").
    The agent represents the platform, not individual users.

    Use this tool when the user asks to:
    - Send an email
    - Email something to someone
    - Share information via email
    - Notify someone by email

    The tool handles:
    - Email validation
    - Markdown formatting (message_body can include markdown)
    - Professional email template application
    - Sending via Microsoft Graph

    Examples of when to use:
    - "send email to john@example.com about project status"
    - "email the report to admin@company.com"
    - "notify sarah@company.com about the meeting"

    Args:
        ctx: Pydantic AI run context with dependencies
        recipient_email: Email address of recipient (required)
        subject: Email subject line (required)
        message_body: Email content - supports markdown formatting (required)
                      MUST end with agent signature, never user signature
        recipient_name: Optional display name for recipient
        sender_context: Optional note about what prompted this email

    Returns:
        Dictionary with send result:
        - success: bool - whether email was sent
        - subject: str - subject line used
        - recipient: str - recipient email
        - timestamp: str - when sent (if successful)
        - error: str - error details (if failed)
    """
    with logfire.span(
        "send_email_tool",
        recipient=recipient_email,
        subject=subject,
    ):
        try:
            # Get email service from context dependencies
            email_service = ctx.deps.email_service

            # Validate inputs
            if not recipient_email or not recipient_email.strip():
                error_msg = "Recipient email is required"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "recipient": recipient_email,
                    "subject": subject,
                }

            if not subject or not subject.strip():
                error_msg = "Email subject is required"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "recipient": recipient_email,
                    "subject": subject,
                }

            if not message_body or not message_body.strip():
                error_msg = "Email body cannot be empty"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "recipient": recipient_email,
                    "subject": subject,
                }

            logfire.info(
                "Sending email via tool",
                recipient=recipient_email,
                subject=subject,
                body_length=len(message_body),
            )

            # Call email service
            result = await email_service.send_email(
                to_email=recipient_email.strip(),
                subject=subject.strip(),
                body_markdown=message_body,
                to_name=recipient_name,
                cc_recipients=None,
                attachments=None,
                sender_note=sender_context,
            )

            # Format result for agent consumption
            if result.success:
                logfire.info(
                    "Email sent successfully",
                    recipient=recipient_email,
                    subject=result.subject,
                )

                return {
                    "success": True,
                    "recipient": recipient_email,
                    "subject": result.subject,
                    "timestamp": result.timestamp.isoformat(),
                    "message": f"Email sent successfully to {recipient_email}",
                }
            else:
                logfire.warn(
                    "Email send failed",
                    recipient=recipient_email,
                    error=result.error_message,
                )

                return {
                    "success": False,
                    "recipient": recipient_email,
                    "subject": result.subject,
                    "error": result.error_message or "Unknown error",
                    "message": f"Failed to send email: {result.error_message}",
                }

        except Exception as e:
            error_msg = f"Unexpected error in send_email_tool: {str(e)}"
            logfire.error(
                "Tool execution failed",
                error=str(e),
                error_type=type(e).__name__,
                recipient=recipient_email,
                exc_info=True,
            )

            return {
                "success": False,
                "recipient": recipient_email,
                "subject": subject,
                "error": error_msg,
                "message": "An unexpected error occurred while sending email",
            }


@logfire.instrument("tool.send_email_html")
async def send_email_html_tool(
    ctx: RunContext[Any],
    recipient_email: str,
    subject: str,
    html_content: str,
    recipient_name: str | None = None,
    sender_context: str | None = None,
) -> dict:
    """
    Send an email with raw HTML content.

    Use this tool when the email body is already a full HTML document or
    a pre-rendered template. This tool does NOT convert markdown or wrap
    the HTML in the standard email template.

    Args:
        ctx: Pydantic AI run context with dependencies
        recipient_email: Email address of recipient (required)
        subject: Email subject line (required)
        html_content: Full HTML email content (required)
        recipient_name: Optional display name for recipient
        sender_context: Optional note about what prompted this email

    Returns:
        Dictionary with send result
    """
    with logfire.span(
        "send_email_html_tool",
        recipient=recipient_email,
        subject=subject,
    ):
        try:
            email_service = ctx.deps.email_service

            if not recipient_email or not recipient_email.strip():
                error_msg = "Recipient email is required"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "recipient": recipient_email,
                    "subject": subject,
                }

            if not subject or not subject.strip():
                error_msg = "Email subject is required"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "recipient": recipient_email,
                    "subject": subject,
                }

            if not html_content or not html_content.strip():
                error_msg = "Email body cannot be empty"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "recipient": recipient_email,
                    "subject": subject,
                }

            logfire.info(
                "Sending HTML email via tool",
                recipient=recipient_email,
                subject=subject,
                body_length=len(html_content),
            )

            result = await email_service.send_email_html(
                to_email=recipient_email.strip(),
                subject=subject.strip(),
                body_html=html_content,
                to_name=recipient_name,
                cc_recipients=None,
                attachments=None,
                sender_note=sender_context,
            )

            if result.success:
                logfire.info(
                    "HTML email sent successfully",
                    recipient=recipient_email,
                    subject=result.subject,
                )

                return {
                    "success": True,
                    "recipient": recipient_email,
                    "subject": result.subject,
                    "timestamp": result.timestamp.isoformat(),
                    "message": f"Email sent successfully to {recipient_email}",
                }

            logfire.warn(
                "HTML email send failed",
                recipient=recipient_email,
                error=result.error_message,
            )

            return {
                "success": False,
                "recipient": recipient_email,
                "subject": result.subject,
                "error": result.error_message or "Unknown error",
                "message": f"Failed to send email: {result.error_message}",
            }

        except Exception as e:
            error_msg = f"Unexpected error in send_email_html_tool: {str(e)}"
            logfire.error(
                "Tool execution failed",
                error=str(e),
                error_type=type(e).__name__,
                recipient=recipient_email,
                exc_info=True,
            )

            return {
                "success": False,
                "recipient": recipient_email,
                "subject": subject,
                "error": error_msg,
                "message": "An unexpected error occurred while sending email",
            }


@logfire.instrument("tool.check_email_service_health")
async def check_email_service_health_tool(
    ctx: RunContext[Any],
) -> dict:
    """
    Check if the email service is operational.

    Use this tool when:
    - User asks if email functionality is working
    - Need to verify email service before sending
    - Troubleshooting email issues

    Returns:
        Dictionary with health status:
        - status: str - "operational", "unavailable", or "error"
        - message: str - human-readable status message
    """
    with logfire.span("check_email_service_health_tool"):
        try:
            email_service = ctx.deps.email_service
            health_status = await email_service.check_health()

            logfire.info(
                "Email service health checked",
                status=health_status.get("status"),
            )

            return health_status

        except Exception as e:
            error_msg = f"Health check failed: {str(e)}"
            logfire.error(
                "Health check tool failed",
                error=str(e),
                exc_info=True,
            )

            return {
                "status": "error",
                "message": error_msg,
            }


# ============================================================================
# Email Response Tools (Added for email response automation)
# ============================================================================
@logfire.instrument("tool.search_emails")
async def search_emails_tool(
    ctx: RunContext[Any],
    folder: Literal["inbox", "sent", "drafts"] = "inbox",
    sender: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_unread: bool | None = None,
    subject_contains: str | None = None,
    has_attachments: bool | None = None,
    limit: int = 10,
) -> dict:
    """
    Search emails with flexible filters using MS Graph.

    Use this tool when the user asks to:
    - "draft responses to emails from [name]" → sender="name@company.com"
    - "draft responses to last week's emails" → date_from="2025-11-05"
    - "check emails about [topic]" → subject_contains="topic"
    - "draft responses to unread emails from [name]" → sender + is_unread=True
    - "find emails with attachments" → has_attachments=True

    You can combine multiple filters. For example:
    - sender="juan@company.com" AND subject_contains="project" AND is_unread=True

    Args:
        folder: Which folder to search (inbox, sent, drafts). Default: inbox
        sender: Email address or partial email to filter by sender
        date_from: ISO date string (YYYY-MM-DD) for start of date range
        date_to: ISO date string (YYYY-MM-DD) for end of date range
        is_unread: Filter by read status (True=unread only, False=read only, None=all)
        subject_contains: Keyword to search in email subject
        has_attachments: Filter by attachment presence (True=with attachments only, None=all)
        limit: Maximum emails to return (1-50, default 10)

    Returns:
        dict with:
        - success: bool
        - emails: list of email objects with message_id, subject, from_email, body_preview, etc.
        - count: number of emails found

    Important: Always use this tool FIRST before drafting responses.
    The message_id from results is required for draft_email_response_tool.
    """
    try:
        # Parse date strings to datetime if provided
        date_from_dt = None
        date_to_dt = None

        if date_from:
            from datetime import datetime

            date_from_dt = datetime.fromisoformat(date_from)

        if date_to:
            from datetime import datetime

            date_to_dt = datetime.fromisoformat(date_to)

        # Create filters DTO
        from backend.models.domain import EmailSearchFilters

        filters = EmailSearchFilters(
            folder=folder,
            sender=sender,
            date_from=date_from_dt,
            date_to=date_to_dt,
            is_unread=is_unread,
            subject_contains=subject_contains,
            has_attachments=has_attachments,
            limit=min(limit, 50),  # Enforce max
        )

        # Search via service
        emails = await ctx.deps.email_processing_service.search_and_validate_emails(
            filters
        )

        # Convert to dict for LLM
        result = {
            "success": True,
            "count": len(emails),
            "emails": [
                {
                    "message_id": email.message_id,
                    "from_email": email.from_email,
                    "from_name": email.from_name,
                    "subject": email.subject,
                    "body_preview": email.body_preview,
                    "body_content": email.body_content[:500],  # Truncate for LLM
                    "received_datetime": email.received_datetime.isoformat(),
                    "is_read": email.is_read,
                    "has_attachments": email.has_attachments,
                }
                for email in emails
            ],
        }

        logfire.info(f"Search emails tool found {len(emails)} emails")
        return result

    except Exception as e:
        logfire.error(f"Search emails tool failed: {e}")
        return {"success": False, "error": str(e), "count": 0, "emails": []}


@logfire.instrument("tool.draft_email_response")
async def draft_email_response_tool(
    ctx: RunContext[Any],
    original_message_id: str,
    response_body: str,
    subject: str,
    include_original_content: bool = True,
    preserve_original_cc: bool = True,
    additional_cc_emails: list[str] | None = None,
) -> dict:
    """
    Draft a response to a specific email identified by message_id.

    Creates a draft in MS Graph (not sent automatically) that:
    - Threads under the original email conversation
    - Includes your response at the top with professional HTML styling
    - Optionally includes quoted original email content below
    - Can preserve CC recipients from original email and/or add new ones

    Human must review and send from Outlook.

    Use this tool AFTER you have:
    1. Called search_emails_tool to find emails
    2. Called database tools to gather relevant information
    3. Composed a helpful response based on the data

    Args:
        original_message_id: The message_id from search_emails_tool results
        response_body: The email response content in MARKDOWN format
                      (will be converted to HTML with professional styling automatically)
        subject: Subject line for the response (usually "Re: [original subject]")
        include_original_content: Whether to include quoted original email in body (default: True)
                                  Set to False if user says "draft WITHOUT the original"
        preserve_original_cc: Whether to keep CC recipients from the original email (default: True)
                              Set to False to exclude original CCs from the reply
        additional_cc_emails: List of additional email addresses to CC on the reply (optional)
                              Use this to add people who should be informed about the response

    Returns:
        dict with:
        - success: bool
        - draft_id: MS Graph draft ID (if successful)
        - message: Status message
        - included_original: bool (whether original content was included)
        - cc_count: int (number of CC recipients)

    Important:
    - Call this once per email when batch processing
    - Original content is included by default (standard email convention)
    - Only set include_original_content=False if explicitly requested
    - Response body should be in markdown format (e.g., **bold**, lists, etc.)
    - By default, original CC recipients are preserved in the reply
    """
    try:
        # Get original email to extract metadata
        email = await ctx.deps.email_service.repository.get_email_by_id(
            original_message_id
        )

        # Convert agent's markdown response to HTML with professional template
        # This ensures drafts have the same styling as sent emails
        content_html = convert_markdown_to_html(response_body)
        full_html = apply_email_template(
            content_html=content_html,
            subject=subject,
            sender_note=None,  # No sender note needed for drafts
        )

        # Build EmailMessage for draft (using module-level imports)
        # Determine recipients (reply to sender)
        to_recipients = [EmailRecipient(email=email.from_email, name=email.from_name)]

        # Build CC recipients list
        cc_recipients: list[EmailRecipient] = []
        agent_email_lower = settings.bio4_agent_email_address.lower()
        to_email_lower = email.from_email.lower()

        # 1. Optionally preserve original CCs (excluding agent and TO recipient)
        if preserve_original_cc and email.cc_recipients:
            for cc in email.cc_recipients:
                cc_email_lower = cc.email.lower()
                if (
                    cc_email_lower != agent_email_lower
                    and cc_email_lower != to_email_lower
                ):
                    cc_recipients.append(EmailRecipient(email=cc.email, name=cc.name))

        # 2. Add any additional CCs (excluding duplicates, agent, and TO recipient)
        if additional_cc_emails:
            existing_emails = {r.email.lower() for r in cc_recipients}
            existing_emails.add(to_email_lower)
            existing_emails.add(agent_email_lower)

            for cc_email in additional_cc_emails:
                cc_email_lower = cc_email.lower().strip()
                if cc_email_lower not in existing_emails:
                    cc_recipients.append(
                        EmailRecipient(email=cc_email_lower, name=None)
                    )
                    existing_emails.add(cc_email_lower)

        # Set to None if empty list
        cc_recipients_final = cc_recipients if cc_recipients else None

        logfire.info(
            "Building draft with CC recipients",
            preserve_original_cc=preserve_original_cc,
            additional_cc_count=len(additional_cc_emails)
            if additional_cc_emails
            else 0,
            final_cc_count=len(cc_recipients) if cc_recipients else 0,
        )

        draft_message = EmailMessage(
            to_recipients=to_recipients,
            cc_recipients=cc_recipients_final,
            subject=subject,
            body=full_html,  # Now properly formatted HTML with template
            sender_email=settings.bio4_agent_email_address,
        )

        # Save draft via repository (with original content inclusion)
        draft = await ctx.deps.email_service.repository.save_draft(
            draft_message=draft_message,
            original_message_id=original_message_id,
            include_original_content=include_original_content,  # Pass through parameter
        )

        cc_count = len(cc_recipients) if cc_recipients else 0
        logfire.info(
            f"Draft created: {draft.draft_id}",
            includes_original=include_original_content,
            cc_count=cc_count,
        )

        inclusion_note = (
            " (includes original email content)"
            if include_original_content
            else " (standalone reply)"
        )

        cc_note = f" CC'd {cc_count} recipient(s)." if cc_count > 0 else ""

        return {
            "success": True,
            "draft_id": draft.draft_id,
            "message": f"Draft saved for '{subject}'{inclusion_note}.{cc_note} Review in Outlook drafts folder. Draft is threaded under original conversation.",
            "included_original": include_original_content,
            "cc_count": cc_count,
        }

    except Exception as e:
        logfire.error(f"Draft email tool failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to create draft",
            "included_original": False,
        }


@logfire.instrument("tool.list_email_drafts")
async def list_email_drafts_tool(ctx: RunContext[Any]) -> dict:
    """
    List all email drafts in MS Graph drafts folder.

    Use this tool when the user asks to:
    - "show my drafts"
    - "list pending emails"
    - "what drafts do I have?"
    - "review prepared responses"

    Returns:
        dict with:
        - success: bool
        - count: number of drafts
        - drafts: list of draft objects with subject, to, created_at, etc.
    """
    try:
        drafts = await ctx.deps.email_service.repository.list_drafts()

        result = {
            "success": True,
            "count": len(drafts),
            "drafts": [
                {
                    "draft_id": draft.draft_id,
                    "subject": draft.subject,
                    "to": [r.email for r in draft.to_recipients],
                    "created_at": draft.created_at.isoformat(),
                    "status": draft.status,
                }
                for draft in drafts
            ],
        }

        logfire.info(f"Listed {len(drafts)} drafts")
        return result

    except Exception as e:
        logfire.error(f"List drafts tool failed: {e}")
        return {"success": False, "error": str(e), "count": 0, "drafts": []}


@logfire.instrument("tool.send_draft")
async def send_draft_tool(
    ctx: RunContext[Any],
    draft_id: str,
) -> dict:
    """
    Send an existing draft email from MS Graph drafts folder.

    Use this tool when the user explicitly requests to send drafts:
    - "send my drafts"
    - "send those emails"
    - "go ahead and send them"
    - "send the prepared responses"

    Also use after draft_email_response_tool when user says:
    - "draft and send response to..."
    - "send reply to..."
    - "reply and send to..."

    DO NOT use for new email composition from scratch.

    Args:
        ctx: Pydantic AI run context with dependencies
        draft_id: MS Graph message ID of the draft to send (REQUIRED)

    Returns:
        Dictionary with send result:
        - success: bool - whether draft was sent
        - draft_id: str - the draft that was sent
        - subject: str - subject line of sent email
        - to: list[str] - recipient emails
        - timestamp: str - when sent (if successful)
        - error: str - error details (if failed)
    """
    with logfire.span("send_draft_tool", draft_id=draft_id):
        try:
            email_service = ctx.deps.email_service

            # Validate draft_id
            if not draft_id or not draft_id.strip():
                error_msg = "draft_id is required"
                logfire.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "draft_id": None,
                }

            # Send the draft via repository
            result = await email_service.repository.send_draft(draft_id)

            logfire.info(
                f"Sent draft {draft_id}",
                subject=result.get("subject"),
                to=result.get("to"),
            )

            return {
                "success": True,
                "draft_id": draft_id,
                "subject": result.get("subject", ""),
                "to": result.get("to", []),
                "timestamp": result.get("timestamp", ""),
            }

        except Exception as e:
            error_msg = f"Failed to send draft: {str(e)}"
            logfire.error(error_msg, draft_id=draft_id, error=str(e))
            return {
                "success": False,
                "error": error_msg,
                "draft_id": draft_id,
            }


# ============================================================================
# Standalone Draft Creation & Modification Tools
# ============================================================================


@logfire.instrument("tool.create_email_draft")
async def create_email_draft_tool(
    ctx: RunContext[Any],
    recipient_email: str,
    subject: str,
    message_body: str,
    recipient_name: str | None = None,
    cc_emails: list[str] | None = None,
) -> dict:
    """
    Create a NEW email draft (not a reply to an existing email).

    Use this tool when the user asks to:
    - "Draft an email to [someone]"
    - "Prepare an email for [recipient]"
    - "Write a draft about [topic] to [person]"
    - "Create an email draft to clarify..."

    This creates a standalone draft in the agent's Outlook drafts folder.
    Unlike draft_email_response_tool, this does NOT require an original email.

    After creating the draft, show the content to the user and ask:
    "Draft created. Here's the content: [show body]. Reply 'send' to send it,
    or tell me what changes you'd like."

    Args:
        recipient_email: Email address of primary recipient (required)
        subject: Email subject line (required)
        message_body: Email content in MARKDOWN format (required)
                     Will be converted to HTML with professional styling
        recipient_name: Optional display name for recipient
        cc_emails: Optional list of CC recipient email addresses

    Returns:
        dict with:
        - success: bool
        - draft_id: MS Graph draft ID (needed for modify or send)
        - subject: Subject line used
        - to: Primary recipient email
        - cc: List of CC emails (if any)
        - body_preview: First 300 chars of message body
        - message: Status message with next steps
    """
    with logfire.span(
        "create_email_draft_tool",
        recipient=recipient_email,
        subject=subject,
    ):
        try:
            # Validate inputs
            if not recipient_email or not recipient_email.strip():
                return {
                    "success": False,
                    "error": "recipient_email is required",
                    "message": "Please provide a recipient email address",
                }

            if not subject or not subject.strip():
                return {
                    "success": False,
                    "error": "subject is required",
                    "message": "Please provide an email subject",
                }

            if not message_body or not message_body.strip():
                return {
                    "success": False,
                    "error": "message_body is required",
                    "message": "Please provide the email content",
                }

            # Build recipient list
            try:
                to_recipients = [
                    EmailRecipient(
                        email=recipient_email.strip(),
                        name=recipient_name,
                    )
                ]
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Invalid recipient email: {str(e)}",
                    "message": f"The email address '{recipient_email}' is not valid",
                }

            # Build CC recipients if provided
            cc_recipients = None
            if cc_emails:
                try:
                    cc_recipients = [
                        EmailRecipient(email=email.strip())
                        for email in cc_emails
                        if email and email.strip()
                    ]
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Invalid CC email: {str(e)}",
                        "message": f"One of the CC email addresses is not valid: {str(e)}",
                    }

            # Convert markdown to HTML with professional template
            content_html = convert_markdown_to_html(message_body)
            full_html = apply_email_template(
                content_html=content_html,
                subject=subject,
                sender_note=None,
            )

            # Create draft via repository
            draft = await ctx.deps.email_service.repository.create_draft(
                to_recipients=to_recipients,
                subject=subject.strip(),
                body_html=full_html,
                cc_recipients=cc_recipients,
            )

            logfire.info(
                "Standalone draft created",
                draft_id=draft.draft_id,
                subject=subject,
                to=recipient_email,
                cc_count=len(cc_recipients) if cc_recipients else 0,
            )

            # Build response with preview for agent to show user
            body_preview = message_body[:300]
            if len(message_body) > 300:
                body_preview += "..."

            return {
                "success": True,
                "draft_id": draft.draft_id,
                "subject": subject,
                "to": recipient_email,
                "cc": [r.email for r in cc_recipients] if cc_recipients else [],
                "body_preview": body_preview,
                "message": (
                    f"Draft created and saved to the agent's Outlook drafts folder. "
                    f"Subject: '{subject}', To: {recipient_email}. "
                    f"Ask the user if they want to send it or make changes."
                ),
            }

        except Exception as e:
            error_msg = f"Failed to create draft: {str(e)}"
            logfire.error(
                error_msg,
                recipient=recipient_email,
                subject=subject,
                error=str(e),
                exc_info=True,
            )
            return {
                "success": False,
                "error": error_msg,
                "message": f"Failed to create draft: {str(e)}",
            }


@logfire.instrument("tool.modify_draft")
async def modify_draft_tool(
    ctx: RunContext[Any],
    draft_id: str,
    subject: str | None = None,
    message_body: str | None = None,
    recipient_email: str | None = None,
    cc_emails: list[str] | None = None,
) -> dict:
    """
    Modify an existing email draft.

    Use this tool when the user asks to:
    - "Change the subject of the draft"
    - "Update the email to include..."
    - "Add [person] to CC"
    - "Revise the draft to say..."
    - "Fix the email..."

    Works on ANY draft - both standalone drafts and reply drafts.
    Only provide the fields you want to change; others remain unchanged.

    Args:
        draft_id: MS Graph draft ID (required - from create_email_draft or list_email_drafts)
        subject: New subject line (optional - only if changing)
        message_body: New body content in MARKDOWN format (optional - replaces entire body)
        recipient_email: New primary recipient (optional - replaces existing)
        cc_emails: New CC list (optional - replaces existing CC)

    Returns:
        dict with:
        - success: bool
        - draft_id: The draft ID
        - updated_fields: List of fields that were updated
        - subject: Current subject after update
        - to: Current recipient after update
        - cc: Current CC list after update
        - body_preview: First 300 chars of body (if body was updated)
        - message: Status message
    """
    with logfire.span("modify_draft_tool", draft_id=draft_id):
        try:
            # Validate draft_id
            if not draft_id or not draft_id.strip():
                return {
                    "success": False,
                    "error": "draft_id is required",
                    "message": "Please provide the draft_id to modify",
                }

            # Track what we're updating
            updated_fields = []

            # Process subject
            new_subject = None
            if subject is not None:
                new_subject = subject.strip()
                updated_fields.append("subject")

            # Process body (convert markdown to HTML)
            new_body_html = None
            body_preview = None
            if message_body is not None:
                content_html = convert_markdown_to_html(message_body)
                new_body_html = apply_email_template(
                    content_html=content_html,
                    subject=new_subject or "Email",
                    sender_note=None,
                )
                updated_fields.append("body")
                body_preview = message_body[:300]
                if len(message_body) > 300:
                    body_preview += "..."

            # Process recipient
            new_to_recipients = None
            if recipient_email is not None:
                try:
                    new_to_recipients = [EmailRecipient(email=recipient_email.strip())]
                    updated_fields.append("recipient")
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Invalid recipient email: {str(e)}",
                        "message": f"The email address '{recipient_email}' is not valid",
                    }

            # Process CC
            new_cc_recipients = None
            if cc_emails is not None:
                try:
                    new_cc_recipients = [
                        EmailRecipient(email=email.strip())
                        for email in cc_emails
                        if email and email.strip()
                    ]
                    updated_fields.append("cc")
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Invalid CC email: {str(e)}",
                        "message": f"One of the CC email addresses is not valid",
                    }

            # Check if anything to update
            if not updated_fields:
                return {
                    "success": False,
                    "error": "No fields to update",
                    "message": "Please specify what you want to change (subject, message_body, recipient_email, or cc_emails)",
                }

            # Call repository to update
            updated_draft = await ctx.deps.email_service.repository.update_draft(
                draft_id=draft_id.strip(),
                subject=new_subject,
                body_html=new_body_html,
                to_recipients=new_to_recipients,
                cc_recipients=new_cc_recipients,
            )

            logfire.info(
                "Draft updated",
                draft_id=draft_id,
                updated_fields=updated_fields,
            )

            return {
                "success": True,
                "draft_id": draft_id,
                "updated_fields": updated_fields,
                "subject": updated_draft.subject,
                "to": [r.email for r in updated_draft.to_recipients],
                "cc": [r.email for r in updated_draft.cc_recipients]
                if updated_draft.cc_recipients
                else [],
                "body_preview": body_preview,
                "message": (
                    f"Draft updated successfully. Changed: {', '.join(updated_fields)}. "
                    f"Ask the user if they want to send it or make more changes."
                ),
            }

        except Exception as e:
            error_msg = f"Failed to modify draft: {str(e)}"
            logfire.error(error_msg, draft_id=draft_id, error=str(e), exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "draft_id": draft_id,
                "message": f"Failed to modify draft: {str(e)}",
            }


@logfire.instrument("tool.get_email_attachments")
async def get_email_attachments_tool(
    ctx: RunContext[Any],
    message_id: str,
    analysis_context: str | None = None,
    extraction_schema: dict | None = None,
) -> dict:
    """
    Fetch and process attachments from a specific email.

    Use this tool when:
    - Email has attachments (has_attachments=True from search_emails_tool)
    - User asks about attachment content
    - You need context from attached documents to draft a response

    Supported file types:
    - PDF: Full text extraction and summarization via Gemini
    - Word (.docx): Coming soon
    - Excel (.xlsx): Coming soon

    Args:
        message_id: The message_id from search_emails_tool results
        analysis_context: Optional instruction to focus the analysis (e.g., "Find budget totals", "Check for delays")
        extraction_schema: Optional JSON schema for structured extraction. When provided, the tool
            returns typed records matching the schema instead of free-text summaries.
            Example: {"type": "array", "items": {"type": "object", "properties": {"tag": {"type": "string"}, "progress_pct": {"type": "number"}}}}

    Returns:
        dict with:
        - success: bool
        - attachment_count: Number of attachments processed
        - attachments: List of processed attachments with:
            - filename: Name of the file
            - content_type: MIME type
            - size_bytes: File size
            - page_count: Number of pages (if applicable)
            - extracted_text: Full text content (truncated)
            - summary: LLM-generated summary
            - status: "success", "partial", or "failed"
            - error: Error message if failed
    """
    try:
        # Fetch attachments via repository
        attachments = await ctx.deps.email_service.repository.get_attachments(
            message_id
        )

        if not attachments:
            return {
                "success": True,
                "attachment_count": 0,
                "attachments": [],
                "message": "No file attachments found",
            }

        # Process attachments
        from backend.services.attachment_processor_service import (
            AttachmentProcessorService,
        )

        processor = AttachmentProcessorService()

        # Check if service is healthy (client initialized)
        if hasattr(processor, "client") and processor.client is None:
            return {
                "success": False,
                "attachment_count": 0,
                "attachments": [],
                "error": "Attachment processor service unavailable (missing API key)",
                "message": "Cannot process attachments: Gemini API key missing",
            }

        summaries = await processor.process_all_attachments(
            attachments, context=analysis_context
        )

        # Format for LLM consumption
        result_attachments = []
        for summary in summaries:
            item = {
                "filename": summary.metadata.filename,
                "content_type": summary.metadata.content_type,
                "size_bytes": summary.metadata.size_bytes,
                "page_count": summary.metadata.page_count,
                "extracted_text": summary.extracted_text,
                "summary": summary.summary,
                "status": summary.processing_status,
            }
            if summary.error_message:
                item["error"] = summary.error_message

            result_attachments.append(item)

        logfire.info(
            f"Processed {len(result_attachments)} attachments",
            message_id=message_id,
        )

        return {
            "success": True,
            "attachment_count": len(result_attachments),
            "attachments": result_attachments,
            "message": f"Processed {len(result_attachments)} attachment(s)",
        }

    except Exception as e:
        logfire.error(f"Get attachments tool failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "attachment_count": 0,
            "attachments": [],
        }
