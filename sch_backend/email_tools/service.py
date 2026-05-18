import logfire
import markdown
import bleach

from sch_backend.email_tools.models import (
    EmailDraftOperationResult,
    EmailDraftSummary,
    EmailDirectSendResult,
    EmailHealthStatus,
    EmailRecipient,
)
from sch_backend.email_tools.repository import EmailRepository


class EmailService:
    def __init__(self, repository: EmailRepository):
        self.repository = repository

    @logfire.instrument("EmailService.check_health")
    async def check_health(self) -> EmailHealthStatus:
        result = await self.repository.check_health()
        return EmailHealthStatus(**result)

    def _render_markdown_html(self, subject: str, body_markdown: str) -> str:
        raw_html = markdown.markdown(body_markdown, extensions=["extra", "sane_lists"])
        allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
            "p",
            "br",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
        ]
        safe_html = bleach.clean(raw_html, tags=allowed_tags, strip=True)
        return f"<div><h3>{bleach.clean(subject, strip=True)}</h3>{safe_html}</div>"

    @logfire.instrument("EmailService.create_draft")
    async def create_draft(
        self,
        recipient_email: str,
        subject: str,
        message_body: str,
        recipient_name: str | None = None,
        cc_emails: list[str] | None = None,
    ) -> EmailDraftOperationResult:
        try:
            to_recipients = [EmailRecipient(email=recipient_email, name=recipient_name)]
            cc_recipients = [EmailRecipient(email=email) for email in (cc_emails or [])]
            body_html = self._render_markdown_html(subject=subject, body_markdown=message_body)

            draft = await self.repository.create_draft(
                to_recipients=to_recipients,
                subject=subject,
                body_html=body_html,
                cc_recipients=cc_recipients or None,
            )
            return EmailDraftOperationResult(
                success=True,
                draft_id=draft["draft_id"],
                subject=draft["subject"],
                to=draft["to"],
                cc=draft["cc"],
                timestamp=draft["created_at"],
                message="Draft created successfully",
            )
        except Exception as error:
            return EmailDraftOperationResult(
                success=False,
                message="Failed to create draft",
                error=str(error),
            )

    @logfire.instrument("EmailService.list_drafts")
    async def list_drafts(self, limit: int = 10) -> list[EmailDraftSummary]:
        drafts = await self.repository.list_drafts(limit=limit)
        return [EmailDraftSummary(**draft) for draft in drafts]

    @logfire.instrument("EmailService.modify_draft")
    async def modify_draft(
        self,
        draft_id: str,
        subject: str | None = None,
        message_body: str | None = None,
        recipient_email: str | None = None,
        cc_emails: list[str] | None = None,
    ) -> EmailDraftOperationResult:
        try:
            to_recipients = None
            if recipient_email is not None:
                to_recipients = [EmailRecipient(email=recipient_email)]

            cc_recipients = None
            if cc_emails is not None:
                cc_recipients = [EmailRecipient(email=email) for email in cc_emails]

            body_html = None
            if message_body is not None:
                body_html = self._render_markdown_html(subject=subject or "Draft Update", body_markdown=message_body)

            updated = await self.repository.update_draft(
                draft_id=draft_id,
                subject=subject,
                body_html=body_html,
                to_recipients=to_recipients,
                cc_recipients=cc_recipients,
            )

            return EmailDraftOperationResult(
                success=True,
                draft_id=updated["draft_id"],
                subject=updated["subject"],
                to=updated["to"],
                cc=updated["cc"],
                timestamp=updated["created_at"],
                message="Draft updated successfully",
            )
        except Exception as error:
            return EmailDraftOperationResult(
                success=False,
                draft_id=draft_id,
                message="Failed to update draft",
                error=str(error),
            )

    @logfire.instrument("EmailService.send_draft")
    async def send_draft(self, draft_id: str) -> EmailDraftOperationResult:
        try:
            sent = await self.repository.send_draft(draft_id=draft_id)
            return EmailDraftOperationResult(
                success=True,
                draft_id=sent["draft_id"],
                subject=sent["subject"],
                to=sent["to"],
                cc=sent["cc"],
                timestamp=sent["timestamp"],
                message="Draft sent successfully",
            )
        except Exception as error:
            return EmailDraftOperationResult(
                success=False,
                draft_id=draft_id,
                message="Failed to send draft",
                error=str(error),
            )

    @logfire.instrument("EmailService.send_email")
    async def send_email(
        self,
        recipient_email: str,
        subject: str,
        message_body: str,
        recipient_name: str | None = None,
        cc_emails: list[str] | None = None,
    ) -> EmailDirectSendResult:
        try:
            to_recipients = [EmailRecipient(email=recipient_email, name=recipient_name)]
            cc_recipients = [EmailRecipient(email=email) for email in (cc_emails or [])]
            body_html = self._render_markdown_html(subject=subject, body_markdown=message_body)

            sent = await self.repository.send_email(
                to_recipients=to_recipients,
                subject=subject,
                body_html=body_html,
                cc_recipients=cc_recipients or None,
            )
            return EmailDirectSendResult(
                success=True,
                subject=sent["subject"],
                to=sent["to"],
                cc=sent["cc"],
                timestamp=sent["timestamp"],
                message="Email sent successfully",
            )
        except Exception as error:
            return EmailDirectSendResult(
                success=False,
                subject=subject,
                to=[recipient_email],
                cc=cc_emails or [],
                message="Failed to send email",
                error=str(error),
            )
