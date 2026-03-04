"""Email service for business logic and orchestration."""

import logfire

from backend.repositories.email_repository import EmailRepository
from backend.utils.formatting import convert_markdown_to_html
from backend.utils.email_templates import apply_email_template
from backend.models.domain import (
    EmailMessage,
    EmailRecipient,
    SentEmailResult,
    EmailAttachment,
)
from backend.config.settings import settings


class EmailService:
    """
    Service layer for email operations.

    Responsibilities:
    - Apply business logic (validation, formatting)
    - Convert markdown to HTML
    - Apply email templates
    - Orchestrate repository calls
    - Handle errors gracefully

    Pattern: Business logic layer between tools and repository
    """

    def __init__(self, repository: EmailRepository):
        """Initialize service with email repository."""
        self.repository = repository

    @logfire.instrument("EmailService.send_email")
    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_markdown: str,
        to_name: str | None = None,
        cc_recipients: list[EmailRecipient] | None = None,
        attachments: list[EmailAttachment] | None = None,
        sender_note: str | None = None,
    ) -> SentEmailResult:
        """
        Send an email with markdown content.

        Business logic:
        - Validates recipient email format
        - Converts markdown to HTML
        - Applies professional email template
        - Uses configured agent email as sender

        Args:
            to_email: Primary recipient email address
            subject: Email subject line
            body_markdown: Email body in markdown format
            to_name: Optional recipient display name
            cc_recipients: Optional CC recipients
            attachments: Optional file attachments
            sender_note: Optional note about request context

        Returns:
            SentEmailResult with success status and metadata
        """
        with logfire.span(
            "send_email",
            to_email=to_email,
            subject=subject,
        ):
            try:
                # Create recipient DTO (validates email format)
                try:
                    recipient = EmailRecipient(
                        email=to_email,
                        name=to_name,
                    )
                except Exception as e:
                    error_msg = f"Invalid recipient email: {str(e)}"
                    logfire.error(error_msg, to_email=to_email)
                    return SentEmailResult(
                        success=False,
                        message_id=None,
                        recipients_count=0,
                        subject=subject,
                        error_message=error_msg,
                    )

                # Convert markdown to HTML
                content_html = convert_markdown_to_html(body_markdown)

                # Apply email template
                full_html = apply_email_template(
                    content_html,
                    subject,
                    sender_note,
                )

                # Create email message DTO
                email_message = EmailMessage(
                    to_recipients=[recipient],
                    subject=subject,
                    body=full_html,
                    cc_recipients=cc_recipients,
                    bcc_recipients=None,
                    attachments=attachments,
                    sender_email=settings.bio4_agent_email_address,
                )

                # Send via repository
                result = await self.repository.send_email(email_message)

                logfire.info(
                    "Email sent via service",
                    success=result.success,
                    to_email=to_email,
                    subject=subject,
                )

                return result

            except Exception as e:
                error_msg = f"Email service error: {str(e)}"
                logfire.error(
                    "Failed to send email in service layer",
                    error=str(e),
                    error_type=type(e).__name__,
                    to_email=to_email,
                    exc_info=True,
                )

                return SentEmailResult(
                    success=False,
                    message_id=None,
                    recipients_count=0,
                    subject=subject,
                    error_message=error_msg,
                )

    @logfire.instrument("EmailService.send_email_html")
    async def send_email_html(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        to_name: str | None = None,
        cc_recipients: list[EmailRecipient] | None = None,
        attachments: list[EmailAttachment] | None = None,
        sender_note: str | None = None,
    ) -> SentEmailResult:
        """
        Send an email with raw HTML content.

        Business logic:
        - Validates recipient email format
        - Sends HTML body without markdown conversion
        - Does not apply the standard email template
        - Uses configured agent email as sender

        Args:
            to_email: Primary recipient email address
            subject: Email subject line
            body_html: Email body in HTML format
            to_name: Optional recipient display name
            cc_recipients: Optional CC recipients
            attachments: Optional file attachments
            sender_note: Optional note about request context

        Returns:
            SentEmailResult with success status and metadata
        """
        with logfire.span(
            "send_email_html",
            to_email=to_email,
            subject=subject,
        ):
            try:
                try:
                    recipient = EmailRecipient(
                        email=to_email,
                        name=to_name,
                    )
                except Exception as e:
                    error_msg = f"Invalid recipient email: {str(e)}"
                    logfire.error(error_msg, to_email=to_email)
                    return SentEmailResult(
                        success=False,
                        message_id=None,
                        recipients_count=0,
                        subject=subject,
                        error_message=error_msg,
                    )

                if not body_html or not body_html.strip():
                    error_msg = "Email body cannot be empty"
                    logfire.error(error_msg, to_email=to_email)
                    return SentEmailResult(
                        success=False,
                        message_id=None,
                        recipients_count=0,
                        subject=subject,
                        error_message=error_msg,
                    )

                email_message = EmailMessage(
                    to_recipients=[recipient],
                    subject=subject,
                    body=body_html,
                    cc_recipients=cc_recipients,
                    bcc_recipients=None,
                    attachments=attachments,
                    sender_email=settings.bio4_agent_email_address,
                )

                result = await self.repository.send_email(email_message)

                logfire.info(
                    "HTML email sent via service",
                    success=result.success,
                    to_email=to_email,
                    subject=subject,
                )

                return result

            except Exception as e:
                error_msg = f"Email service error: {str(e)}"
                logfire.error(
                    "Failed to send HTML email in service layer",
                    error=str(e),
                    error_type=type(e).__name__,
                    to_email=to_email,
                    exc_info=True,
                )

                return SentEmailResult(
                    success=False,
                    message_id=None,
                    recipients_count=0,
                    subject=subject,
                    error_message=error_msg,
                )

    @logfire.instrument("EmailService.check_health")
    async def check_health(self) -> dict:
        """
        Check email service health.

        Returns:
            Health status dictionary
        """
        return await self.repository.check_health()
