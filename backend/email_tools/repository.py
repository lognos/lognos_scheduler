from datetime import datetime, timezone
from typing import Any

import logfire
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import SendMailPostRequestBody

from backend.config.settings import settings
from backend.email_tools.models import EmailRecipient


class EmailRepository:
    def __init__(self):
        self.client: GraphServiceClient | None = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        tenant_id = settings.EMAIL_TENANT_ID
        client_id = settings.EMAIL_CLIENT_ID
        client_secret = settings.EMAIL_CLIENT_SECRET

        if not settings.EMAIL_ENABLED:
            self.client = None
            return

        if not all([tenant_id, client_id, client_secret]):
            logfire.warning(
                "Email disabled due to missing Graph credentials",
                tenant_id_present=bool(tenant_id),
                client_id_present=bool(client_id),
                client_secret_present=bool(client_secret),
            )
            self.client = None
            return

        try:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
            self.client = GraphServiceClient(credentials=credential)
        except Exception as error:
            logfire.error(
                "Failed to initialize Microsoft Graph client",
                error=str(error),
                error_type=type(error).__name__,
                exc_info=True,
            )
            self.client = None

    def _mailbox_user_id(self) -> str | None:
        return settings.EMAIL_MAILBOX_USER_ID

    def _build_recipient(self, recipient: EmailRecipient) -> Recipient:
        recipient_model = Recipient()
        recipient_model.email_address = EmailAddress()
        recipient_model.email_address.address = str(recipient.email)
        recipient_model.email_address.name = recipient.name or str(recipient.email)
        return recipient_model

    def _build_message(
        self,
        subject: str,
        body_html: str,
        to_recipients: list[EmailRecipient],
        cc_recipients: list[EmailRecipient] | None = None,
    ) -> Message:
        message = Message()
        message.subject = subject
        message.body = ItemBody()
        message.body.content_type = BodyType.Html
        message.body.content = body_html
        message.to_recipients = [self._build_recipient(item) for item in to_recipients]
        if cc_recipients:
            message.cc_recipients = [self._build_recipient(item) for item in cc_recipients]
        return message

    def _extract_recipients(self, recipients: list[Recipient] | None) -> list[str]:
        result: list[str] = []
        for recipient in recipients or []:
            address = recipient.email_address.address if recipient.email_address else None
            if address:
                result.append(address)
        return result

    async def check_health(self) -> dict[str, Any]:
        if not settings.EMAIL_ENABLED:
            return {
                "status": "disabled",
                "message": "Email subsystem disabled by configuration",
            }

        if not self.client:
            return {
                "status": "unavailable",
                "message": "Microsoft Graph client not initialized",
            }

        mailbox_user_id = settings.EMAIL_MAILBOX_USER_ID
        if not mailbox_user_id:
            return {
                "status": "degraded",
                "message": "Graph client initialized but EMAIL_MAILBOX_USER_ID is missing",
            }

        try:
            await self.client.users.by_user_id(mailbox_user_id).get()
            return {
                "status": "operational",
                "message": "Microsoft Graph email integration available",
            }
        except Exception as error:
            logfire.error(
                "Email health probe failed",
                error=str(error),
                error_type=type(error).__name__,
                exc_info=True,
            )
            return {
                "status": "error",
                "message": f"Graph connectivity error: {str(error)}",
            }

    @logfire.instrument("EmailRepository.create_draft")
    async def create_draft(
        self,
        to_recipients: list[EmailRecipient],
        subject: str,
        body_html: str,
        cc_recipients: list[EmailRecipient] | None = None,
    ) -> dict[str, Any]:
        mailbox_user_id = self._mailbox_user_id()
        if not self.client or not mailbox_user_id:
            raise ValueError("Email client unavailable or mailbox user id missing")

        message = self._build_message(
            subject=subject,
            body_html=body_html,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
        )

        result = await self.client.users.by_user_id(mailbox_user_id).messages.post(message)
        if not result or not result.id:
            raise RuntimeError("Draft creation failed: Microsoft Graph returned empty result")

        return {
            "draft_id": result.id,
            "subject": result.subject or subject,
            "to": self._extract_recipients(result.to_recipients),
            "cc": self._extract_recipients(result.cc_recipients),
            "created_at": datetime.now(timezone.utc),
        }

    @logfire.instrument("EmailRepository.list_drafts")
    async def list_drafts(self, limit: int = 10) -> list[dict[str, Any]]:
        mailbox_user_id = self._mailbox_user_id()
        if not self.client or not mailbox_user_id:
            raise ValueError("Email client unavailable or mailbox user id missing")

        drafts = await (
            self.client.users.by_user_id(mailbox_user_id)
            .mail_folders.by_mail_folder_id("drafts")
            .messages.get()
        )

        if not drafts or not drafts.value:
            return []

        result: list[dict[str, Any]] = []
        for draft in drafts.value[: max(1, limit)]:
            result.append(
                {
                    "draft_id": draft.id,
                    "subject": draft.subject or "(no subject)",
                    "to": self._extract_recipients(draft.to_recipients),
                    "cc": self._extract_recipients(draft.cc_recipients),
                    "created_at": draft.created_date_time or datetime.now(timezone.utc),
                }
            )
        return result

    @logfire.instrument("EmailRepository.update_draft")
    async def update_draft(
        self,
        draft_id: str,
        subject: str | None = None,
        body_html: str | None = None,
        to_recipients: list[EmailRecipient] | None = None,
        cc_recipients: list[EmailRecipient] | None = None,
    ) -> dict[str, Any]:
        mailbox_user_id = self._mailbox_user_id()
        if not self.client or not mailbox_user_id:
            raise ValueError("Email client unavailable or mailbox user id missing")

        patch_message = Message()
        if subject is not None:
            patch_message.subject = subject
        if body_html is not None:
            patch_message.body = ItemBody()
            patch_message.body.content_type = BodyType.Html
            patch_message.body.content = body_html
        if to_recipients is not None:
            patch_message.to_recipients = [self._build_recipient(item) for item in to_recipients]
        if cc_recipients is not None:
            patch_message.cc_recipients = [self._build_recipient(item) for item in cc_recipients]

        updated = await (
            self.client.users.by_user_id(mailbox_user_id)
            .messages.by_message_id(draft_id)
            .patch(patch_message)
        )

        if not updated:
            updated = await (
                self.client.users.by_user_id(mailbox_user_id)
                .messages.by_message_id(draft_id)
                .get()
            )

        if not updated or not updated.id:
            raise RuntimeError("Draft update failed: Microsoft Graph returned empty result")

        return {
            "draft_id": updated.id,
            "subject": updated.subject or "(no subject)",
            "to": self._extract_recipients(updated.to_recipients),
            "cc": self._extract_recipients(updated.cc_recipients),
            "created_at": updated.created_date_time or datetime.now(timezone.utc),
        }

    @logfire.instrument("EmailRepository.send_draft")
    async def send_draft(self, draft_id: str) -> dict[str, Any]:
        mailbox_user_id = self._mailbox_user_id()
        if not self.client or not mailbox_user_id:
            raise ValueError("Email client unavailable or mailbox user id missing")

        draft_message = (
            await self.client.users.by_user_id(mailbox_user_id)
            .messages.by_message_id(draft_id)
            .get()
        )
        if not draft_message:
            raise ValueError(f"Draft {draft_id} not found")

        await (
            self.client.users.by_user_id(mailbox_user_id)
            .messages.by_message_id(draft_id)
            .send.post()
        )

        return {
            "draft_id": draft_id,
            "subject": draft_message.subject or "(no subject)",
            "to": self._extract_recipients(draft_message.to_recipients),
            "cc": self._extract_recipients(draft_message.cc_recipients),
            "timestamp": datetime.now(timezone.utc),
        }

    @logfire.instrument("EmailRepository.send_email")
    async def send_email(
        self,
        to_recipients: list[EmailRecipient],
        subject: str,
        body_html: str,
        cc_recipients: list[EmailRecipient] | None = None,
    ) -> dict[str, Any]:
        mailbox_user_id = self._mailbox_user_id()
        if not self.client or not mailbox_user_id:
            raise ValueError("Email client unavailable or mailbox user id missing")

        message = self._build_message(
            subject=subject,
            body_html=body_html,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
        )

        send_request = SendMailPostRequestBody()
        send_request.message = message
        send_request.save_to_sent_items = True

        await self.client.users.by_user_id(mailbox_user_id).send_mail.post(body=send_request)

        return {
            "subject": subject,
            "to": [str(item.email) for item in to_recipients],
            "cc": [str(item.email) for item in cc_recipients or []],
            "timestamp": datetime.now(timezone.utc),
        }
