"""Email repository for Microsoft Graph operations."""

import logfire
from typing import Any
from datetime import datetime, timezone
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.file_attachment import FileAttachment
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
    SendMailPostRequestBody,
)
from msgraph.generated.users.item.messages.item.create_reply.create_reply_post_request_body import (
    CreateReplyPostRequestBody,
)
from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)
from kiota_abstractions.base_request_configuration import RequestConfiguration

from backend.models.domain import (
    EmailMessage,
    SentEmailResult,
    EmailRecipient,
    EmailSearchFilters,
    UnreadEmail,
    EmailDraft,
)
from backend.config.settings import settings


class EmailRepository:
    """
    Repository for email operations using Microsoft Graph SDK.

    Responsibilities:
    - Initialize MS Graph client with Azure credentials
    - Send emails via MS Graph API
    - Handle MS Graph SDK-specific error mapping
    - Return typed DTOs (SentEmailResult)

    Pattern: Thin adapter over MS Graph SDK (similar to DatabaseRepository over Supabase)
    """

    def __init__(self):
        """Initialize repository with MS Graph client."""
        self.client: GraphServiceClient | None = None
        self._initialize_client()

    def _initialize_client(self):
        """
        Initialize Microsoft Graph client using credentials from settings.

        Uses ClientSecretCredential (service principal authentication).
        """
        try:
            tenant_id = settings.tenant_id
            client_id = settings.client_id
            client_secret = settings.client_secret

            if not all([tenant_id, client_id, client_secret]):
                logfire.error(
                    "Missing Microsoft Graph credentials",
                    tenant_id_present=bool(tenant_id),
                    client_id_present=bool(client_id),
                    client_secret_present=bool(client_secret),
                )
                self.client = None
                return

            # Create Azure credential
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )

            # Create Graph client
            self.client = GraphServiceClient(credentials=credential)

            logfire.info("Microsoft Graph client initialized successfully")

        except Exception as e:
            logfire.error(
                "Failed to initialize Microsoft Graph client",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            self.client = None

    def _create_recipient(self, recipient: EmailRecipient) -> Recipient:
        """
        Convert EmailRecipient DTO to MS Graph Recipient object.

        Args:
            recipient: Our internal DTO

        Returns:
            MS Graph SDK Recipient object
        """
        graph_recipient = Recipient()
        graph_recipient.email_address = EmailAddress()
        graph_recipient.email_address.address = recipient.email
        graph_recipient.email_address.name = recipient.name or recipient.email
        return graph_recipient

    def _create_attachment(self, attachment: Any) -> FileAttachment:
        """
        Convert EmailAttachment DTO to MS Graph FileAttachment.

        Args:
            attachment: Our internal attachment DTO

        Returns:
            MS Graph SDK FileAttachment object
        """
        file_attachment = FileAttachment()
        file_attachment.name = attachment.filename
        file_attachment.content_type = (
            attachment.content_type or "application/octet-stream"
        )
        file_attachment.content_bytes = attachment.content
        file_attachment.odata_type = "#microsoft.graph.fileAttachment"
        return file_attachment

    def _format_quoted_email(
        self,
        from_email: str,
        from_name: str | None,
        sent_datetime: datetime,
        to_recipients: list[EmailRecipient],
        cc_recipients: list[EmailRecipient] | None,
        subject: str,
        body_html: str,
    ) -> str:
        """
        Format original email content as quoted reply (private helper).

        Creates HTML structure matching Outlook's native reply format:
        - Horizontal separator line
        - Left border (blue vertical line)
        - Email metadata (From, Sent, To, Cc, Subject)
        - Original body content (indented)

        Args:
            from_email: Sender's email address
            from_name: Sender's display name (optional)
            sent_datetime: Original email timestamp
            to_recipients: List of original To recipients
            cc_recipients: List of original Cc recipients (optional)
            subject: Original email subject
            body_html: Original email body (HTML format)

        Returns:
            HTML string with formatted quoted content

        Note:
            This is a private helper method (prefixed with _) following the
            repository's convention for internal utility functions.
        """
        # Format sender name
        sender_display = f"{from_name} <{from_email}>" if from_name else from_email

        # Format datetime in readable format
        # Example: "Monday, January 8, 2025 2:30 PM"
        sent_formatted = sent_datetime.strftime("%A, %B %d, %Y %I:%M %p")

        # Format To recipients
        to_list = ", ".join(
            [f"{r.name} <{r.email}>" if r.name else r.email for r in to_recipients]
        )

        # Format Cc recipients (if any)
        cc_html = ""
        if cc_recipients:
            cc_list = ", ".join(
                [f"{r.name} <{r.email}>" if r.name else r.email for r in cc_recipients]
            )
            cc_html = f"<strong>Cc:</strong> {cc_list}<br>"

        # Build quoted email HTML
        quoted_html = f"""
<hr style="border: none; border-top: 1px solid #ccc; margin: 20px 0;">
<div style="border-left: 3px solid #0078d4; padding-left: 15px; margin-left: 10px; color: #333; font-family: Calibri, Arial, sans-serif; font-size: 11pt;">
    <p style="margin: 5px 0; font-size: 10pt; color: #666;">
        <strong>From:</strong> {sender_display}<br>
        <strong>Sent:</strong> {sent_formatted}<br>
        <strong>To:</strong> {to_list}<br>
        {cc_html}
        <strong>Subject:</strong> {subject}
    </p>
    <div style="margin-top: 10px; color: #000;">
        {body_html}
    </div>
</div>
"""

        return quoted_html

    @logfire.instrument("EmailRepository.send_email")
    async def send_email(self, email: EmailMessage) -> SentEmailResult:
        """
        Send email using Microsoft Graph API.

        Args:
            email: Typed EmailMessage DTO with all send parameters

        Returns:
            SentEmailResult with success status and metadata

        Raises:
            ValueError: If MS Graph client not initialized
            Exception: If MS Graph API call fails
        """
        if not self.client:
            error_msg = "Microsoft Graph client not initialized - check credentials"
            logfire.error(error_msg)
            return SentEmailResult(
                success=False,
                message_id=None,
                recipients_count=0,
                subject=email.subject,
                error_message=error_msg,
            )

        with logfire.span(
            "send_email_msgraph",
            subject=email.subject,
            recipients_count=len(email.to_recipients),
        ):
            try:
                # Create MS Graph Message object
                message = Message()
                message.subject = email.subject

                # Set body (HTML format)
                message.body = ItemBody()
                message.body.content_type = BodyType.Html
                message.body.content = email.body  # Service layer handles markdown→HTML

                # Set recipients
                message.to_recipients = [
                    self._create_recipient(r) for r in email.to_recipients
                ]

                if email.cc_recipients:
                    message.cc_recipients = [
                        self._create_recipient(r) for r in email.cc_recipients
                    ]

                if email.bcc_recipients:
                    message.bcc_recipients = [
                        self._create_recipient(r) for r in email.bcc_recipients
                    ]

                # Add attachments if present
                if email.attachments:
                    message.attachments = [
                        self._create_attachment(a) for a in email.attachments
                    ]
                    logfire.info(f"Added {len(email.attachments)} attachments")

                # Create send request body
                send_mail_body = SendMailPostRequestBody()
                send_mail_body.message = message
                send_mail_body.save_to_sent_items = True

                # Send email from specified sender
                await self.client.users.by_user_id(email.sender_email).send_mail.post(
                    body=send_mail_body
                )

                # Calculate total recipients
                total_recipients = len(email.to_recipients)
                if email.cc_recipients:
                    total_recipients += len(email.cc_recipients)
                if email.bcc_recipients:
                    total_recipients += len(email.bcc_recipients)

                logfire.info(
                    "Email sent successfully via MS Graph",
                    subject=email.subject,
                    total_recipients=total_recipients,
                )

                return SentEmailResult(
                    success=True,
                    message_id=None,  # MS Graph sendMail doesn't return message ID
                    recipients_count=total_recipients,
                    subject=email.subject,
                    timestamp=datetime.now(timezone.utc),
                    error_message=None,
                )

            except Exception as e:
                error_msg = f"Failed to send email via MS Graph: {str(e)}"
                logfire.error(
                    "MS Graph send email failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    subject=email.subject,
                    exc_info=True,
                )

                return SentEmailResult(
                    success=False,
                    message_id=None,
                    recipients_count=0,
                    subject=email.subject,
                    timestamp=datetime.now(timezone.utc),
                    error_message=error_msg,
                )

    @logfire.instrument("EmailRepository.check_health")
    async def check_health(self) -> dict[str, Any]:
        """
        Check Microsoft Graph service health.

        Returns:
            Status dictionary with health information
        """
        if not self.client:
            return {
                "status": "unavailable",
                "message": "Microsoft Graph client not initialized",
            }

        try:
            # Simple connectivity check
            # Could extend to actually test API access if needed
            return {
                "status": "operational",
                "message": "Microsoft Graph client initialized",
            }
        except Exception as e:
            logfire.error("MS Graph health check failed", error=str(e))
            return {
                "status": "error",
                "message": f"Health check error: {str(e)}",
            }

    # RESPOND EMAIL SECTION
    @logfire.instrument("repo.email.search_emails")
    async def search_emails(self, filters: EmailSearchFilters) -> list[UnreadEmail]:
        """
        Search emails with flexible filters using MS Graph OData queries.

        Builds dynamic $filter and $search queries based on provided filters.
        Translates MS Graph response to UnreadEmail DTOs.

        Args:
            filters: EmailSearchFilters with optional sender, date, subject filters

        Returns:
            List of UnreadEmail DTOs matching the filters

        Raises:
            Exception: If MS Graph API call fails
        """
        try:
            # Build query parameters using MS Graph SDK classes
            query_params = (
                MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters()
            )
            query_params.top = filters.limit
            query_params.orderby = ["receivedDateTime desc"]

            # Build filter parts
            filter_parts = []

            # Sender filter
            if filters.sender:
                filter_parts.append(f"from/emailAddress/address eq '{filters.sender}'")

            # Date range filters (MS Graph requires timezone in ISO format)
            if filters.date_from:
                # Ensure timezone-aware datetime, convert to UTC if not
                date_val = filters.date_from
                if date_val.tzinfo is None:
                    date_val = date_val.replace(tzinfo=timezone.utc)
                iso_date = date_val.isoformat()
                filter_parts.append(f"receivedDateTime ge {iso_date}")

            if filters.date_to:
                # Ensure timezone-aware datetime, convert to UTC if not
                date_val = filters.date_to
                if date_val.tzinfo is None:
                    date_val = date_val.replace(tzinfo=timezone.utc)
                iso_date = date_val.isoformat()
                filter_parts.append(f"receivedDateTime le {iso_date}")

            # Unread filter (note: isRead eq false means unread)
            if filters.is_unread is not None:
                is_read_value = "false" if filters.is_unread else "true"
                filter_parts.append(f"isRead eq {is_read_value}")

            # Attachment filter -- only apply via $filter when $search is NOT used,
            # because MS Graph does not support combining $filter with $search.
            # When $search is active, has_attachments is applied as post-query filter.
            post_filter_has_attachments: bool | None = None
            if filters.has_attachments is not None:
                if filters.subject_contains:
                    # Defer to post-query filtering
                    post_filter_has_attachments = filters.has_attachments
                else:
                    filter_parts.append(
                        f"hasAttachments eq {str(filters.has_attachments).lower()}"
                    )

            if filter_parts:
                query_params.filter = " and ".join(filter_parts)

            if filters.subject_contains:
                query_params.search = f'"subject:{filters.subject_contains}"'
                # $orderBy is not supported with $search
                query_params.orderby = None
                # $filter is not supported with $search -- clear any filter
                # that was built above (e.g. date filters). We keep only
                # the post_filter_has_attachments for later.
                if filter_parts:
                    logfire.info(
                        "Clearing $filter because $search is active; "
                        "date/sender filters will not apply with subject search",
                    )
                    query_params.filter = None

            # Determine folder path
            folder_map = {"inbox": "inbox", "sent": "sentitems", "drafts": "drafts"}
            folder_path = folder_map[filters.folder]

            # Wrap in RequestConfiguration
            config = RequestConfiguration(query_parameters=query_params)

            # Make MS Graph API call using bio4@lognos.io user ID
            logfire.info(
                "Searching emails",
                user_id=settings.bio4_lognos_user_id,
                folder=filters.folder,
                filters=filters.model_dump(),
            )

            messages = (
                await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .mail_folders.by_mail_folder_id(folder_path)
                .messages.get(config)
            )

            if not messages or not messages.value:
                logfire.info("No emails found matching filters")
                return []

            # Map to UnreadEmail DTOs
            result = []
            for msg in messages.value:
                email_dto = UnreadEmail(
                    message_id=msg.id,
                    conversation_id=msg.conversation_id,
                    from_email=msg.from_.email_address.address
                    if msg.from_
                    else "unknown",
                    from_name=msg.from_.email_address.name if msg.from_ else None,
                    to_recipients=[
                        EmailRecipient(
                            email=r.email_address.address, name=r.email_address.name
                        )
                        for r in (msg.to_recipients or [])
                    ],
                    cc_recipients=[
                        EmailRecipient(
                            email=r.email_address.address, name=r.email_address.name
                        )
                        for r in (msg.cc_recipients or [])
                    ]
                    if msg.cc_recipients
                    else None,
                    subject=msg.subject or "(no subject)",
                    body_preview=msg.body_preview or "",
                    body_content=msg.body.content if msg.body else "",
                    received_datetime=msg.received_date_time,
                    is_read=msg.is_read or False,
                    has_attachments=msg.has_attachments or False,
                )
                result.append(email_dto)

            # Post-query filtering for has_attachments when $search was used
            # (MS Graph does not support $filter with $search)
            if post_filter_has_attachments is not None:
                before_count = len(result)
                result = [
                    e
                    for e in result
                    if e.has_attachments == post_filter_has_attachments
                ]
                logfire.info(
                    "Applied post-query has_attachments filter",
                    before=before_count,
                    after=len(result),
                    has_attachments=post_filter_has_attachments,
                )

            logfire.info(f"Found {len(result)} emails matching filters")
            return result

        except Exception as e:
            logfire.error(f"Failed to search emails: {e}")
            raise

    @logfire.instrument("repo.email.get_email_by_id")
    async def get_email_by_id(self, message_id: str) -> UnreadEmail:
        """
        Fetch full email content by message ID.

        Used when agent needs complete email body for analysis.

        NOTE: We use inbox path to avoid URL encoding issues with message IDs
        containing special characters. MS Graph properly handles IDs through folder path.
        """
        try:
            # Use inbox folder path to properly handle message ID encoding
            msg = (
                await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .mail_folders.by_mail_folder_id("inbox")
                .messages.by_message_id(message_id)
                .get()
            )

            if not msg:
                raise ValueError(f"Email {message_id} not found")

            return UnreadEmail(
                message_id=msg.id,
                conversation_id=msg.conversation_id,
                from_email=msg.from_.email_address.address if msg.from_ else "unknown",
                from_name=msg.from_.email_address.name if msg.from_ else None,
                to_recipients=[
                    EmailRecipient(
                        email=r.email_address.address, name=r.email_address.name
                    )
                    for r in (msg.to_recipients or [])
                ],
                cc_recipients=[
                    EmailRecipient(
                        email=r.email_address.address, name=r.email_address.name
                    )
                    for r in (msg.cc_recipients or [])
                ]
                if msg.cc_recipients
                else None,
                subject=msg.subject or "(no subject)",
                body_preview=msg.body_preview or "",
                body_content=msg.body.content if msg.body else "",
                received_datetime=msg.received_date_time,
                is_read=msg.is_read or False,
                has_attachments=msg.has_attachments or False,
            )

        except Exception as e:
            logfire.error(f"Failed to fetch email {message_id}: {e}")
            raise

    @logfire.instrument("repo.email.save_draft")
    async def save_draft(
        self,
        draft_message: EmailMessage,
        original_message_id: str,
        include_original_content: bool = True,
    ) -> EmailDraft:
        """
        Save reply draft to MS Graph using createReply API.

        Creates a draft response that:
        - Threads under original conversation (same conversationId)
        - Optionally includes quoted original email content
        - Auto-populates recipients from original message
        - Appears in Outlook Drafts folder

        Args:
            draft_message: EmailMessage with response content
            original_message_id: ID of message being replied to (required for threading)
            include_original_content: Whether to append quoted original email to body (default: True)

        Returns:
            EmailDraft DTO with draft_id and conversation_id

        Raises:
            Exception: If MS Graph API call fails

        Note:
            This method uses the createReply API endpoint, not messages.post().
            This ensures proper conversation threading and recipient handling.
        """
        try:
            # Optionally fetch and append original email content
            body_html = draft_message.body

            if include_original_content:
                try:
                    # Fetch original email with full body
                    logfire.info(
                        "Fetching original email for content inclusion",
                        message_id=original_message_id,
                    )

                    original_msg = (
                        await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                        .messages.by_message_id(original_message_id)
                        .get()
                    )

                    if original_msg and original_msg.body:
                        # Format original email as quoted reply (using private method)
                        quoted_content = self._format_quoted_email(
                            from_email=original_msg.from_.email_address.address
                            if original_msg.from_
                            else "unknown",
                            from_name=original_msg.from_.email_address.name
                            if original_msg.from_
                            else None,
                            sent_datetime=original_msg.received_date_time,
                            to_recipients=[
                                EmailRecipient(
                                    email=r.email_address.address,
                                    name=r.email_address.name,
                                )
                                for r in (original_msg.to_recipients or [])
                            ],
                            cc_recipients=[
                                EmailRecipient(
                                    email=r.email_address.address,
                                    name=r.email_address.name,
                                )
                                for r in (original_msg.cc_recipients or [])
                            ]
                            if original_msg.cc_recipients
                            else None,
                            subject=original_msg.subject or "(no subject)",
                            body_html=original_msg.body.content,
                        )

                        # Append quoted content to reply body
                        body_html = draft_message.body + quoted_content

                        logfire.info("Original email content included in draft body")
                    else:
                        logfire.warn("Original email has no body content")

                except Exception as fetch_error:
                    # Log warning but continue (don't fail draft creation)
                    logfire.warn(
                        "Failed to fetch original email for quoting",
                        error=str(fetch_error),
                        message_id=original_message_id,
                    )
                    # Continue with draft creation without original content

            # Build request body for createReply API
            request_body = CreateReplyPostRequestBody()

            message = Message()
            message.subject = draft_message.subject
            message.body = ItemBody()
            message.body.content_type = BodyType.Html
            message.body.content = body_html  # Includes original content if requested

            # Set CC recipients if provided
            if draft_message.cc_recipients:
                message.cc_recipients = [
                    self._create_recipient(r) for r in draft_message.cc_recipients
                ]
                logfire.info(
                    "Setting CC recipients on draft",
                    cc_count=len(draft_message.cc_recipients),
                )

            request_body.message = message

            # Call createReply API to maintain threading
            result = (
                await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .messages.by_message_id(original_message_id)
                .create_reply.post(request_body)
            )

            if not result:
                raise Exception("createReply returned no result")

            logfire.info(
                "Draft created successfully",
                draft_id=result.id,
                conversation_id=result.conversation_id,
                includes_original=include_original_content,
            )

            return EmailDraft(
                draft_id=result.id,
                original_message_id=original_message_id,
                to_recipients=draft_message.to_recipients,
                cc_recipients=draft_message.cc_recipients,
                subject=result.subject or draft_message.subject,
                body_markdown=draft_message.body,  # Original markdown
                body_html=body_html,  # HTML with quoted content
                created_at=datetime.now(timezone.utc),
                status="draft",
            )

        except Exception as e:
            logfire.error(
                "Failed to save draft",
                error=str(e),
                original_message_id=original_message_id,
            )
            raise

    @logfire.instrument("repo.email.list_drafts")
    async def list_drafts(self) -> list[EmailDraft]:
        """
        List all drafts in MS Graph drafts folder.
        """
        try:
            messages = (
                await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .mail_folders.by_mail_folder_id("drafts")
                .messages.get()
            )

            if not messages or not messages.value:
                return []

            result = []
            for msg in messages.value:
                draft = EmailDraft(
                    draft_id=msg.id,
                    original_message_id=msg.conversation_id or msg.id,
                    to_recipients=[
                        EmailRecipient(
                            email=r.email_address.address, name=r.email_address.name
                        )
                        for r in (msg.to_recipients or [])
                    ],
                    cc_recipients=[
                        EmailRecipient(
                            email=r.email_address.address, name=r.email_address.name
                        )
                        for r in (msg.cc_recipients or [])
                    ]
                    if msg.cc_recipients
                    else None,
                    subject=msg.subject or "(no subject)",
                    body_markdown="",  # Not available from list
                    body_html=msg.body.content if msg.body else "",
                    created_at=msg.created_date_time or datetime.now(timezone.utc),
                    status="draft",
                )
                result.append(draft)

            return result

        except Exception as e:
            logfire.error(f"Failed to list drafts: {e}")
            raise

    @logfire.instrument("repo.email.send_draft")
    async def send_draft(self, draft_id: str) -> dict:
        """
        Send an existing draft message via MS Graph.

        Uses the MS Graph /send endpoint to send a draft that's already
        been created and saved in the drafts folder.

        Args:
            draft_id: MS Graph message ID of the draft

        Returns:
            dict with subject, to (recipients), and timestamp of sent message

        Raises:
            Exception if draft doesn't exist or send fails
        """
        try:
            # First, get draft details before sending (for return info)
            draft_message = (
                await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .messages.by_message_id(draft_id)
                .get()
            )

            if not draft_message:
                raise ValueError(f"Draft {draft_id} not found")

            # Extract info for response
            subject = draft_message.subject or "(no subject)"
            to_recipients = [
                r.email_address.address for r in (draft_message.to_recipients or [])
            ]

            # Send the draft using MS Graph
            await (
                self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .messages.by_message_id(draft_id)
                .send.post()
            )

            logfire.info(
                f"Draft {draft_id} sent successfully",
                subject=subject,
                to=to_recipients,
            )

            # Note: After sending, the draft is moved to Sent Items automatically
            return {
                "subject": subject,
                "to": to_recipients,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logfire.error(
                f"Failed to send draft {draft_id}: {e}",
                error=str(e),
                draft_id=draft_id,
            )
            raise

    @logfire.instrument("repo.email.create_draft")
    async def create_draft(
        self,
        to_recipients: list[EmailRecipient],
        subject: str,
        body_html: str,
        cc_recipients: list[EmailRecipient] | None = None,
    ) -> EmailDraft:
        """
        Create a standalone email draft using MS Graph POST /messages.

        Unlike save_draft(), this creates a NEW email draft that is not
        a reply to an existing message. The draft is saved directly to
        the Drafts folder.

        Args:
            to_recipients: Primary recipients (TO field)
            subject: Email subject line
            body_html: Email body in HTML format (already converted from markdown)
            cc_recipients: Optional CC recipients

        Returns:
            EmailDraft DTO with draft_id and draft details

        Raises:
            ValueError: If MS Graph client not initialized
            Exception: If MS Graph API call fails
        """
        if not self.client:
            raise ValueError("Microsoft Graph client not initialized")

        try:
            # Build MS Graph Message object
            message = Message()
            message.subject = subject
            message.body = ItemBody()
            message.body.content_type = BodyType.Html
            message.body.content = body_html

            # Set To recipients
            message.to_recipients = [self._create_recipient(r) for r in to_recipients]

            # Set CC recipients if provided
            if cc_recipients:
                message.cc_recipients = [
                    self._create_recipient(r) for r in cc_recipients
                ]

            # POST to messages endpoint creates a draft (NOT sent)
            result = await self.client.users.by_user_id(
                settings.bio4_lognos_user_id
            ).messages.post(message)

            if not result:
                raise Exception("POST /messages returned no result")

            logfire.info(
                "Standalone draft created successfully",
                draft_id=result.id,
                subject=subject,
                to_count=len(to_recipients),
                cc_count=len(cc_recipients) if cc_recipients else 0,
            )

            return EmailDraft(
                draft_id=result.id,
                original_message_id=None,  # Standalone draft, not a reply
                to_recipients=to_recipients,
                cc_recipients=cc_recipients,
                subject=result.subject or subject,
                body_markdown="",  # Not stored, caller has it
                body_html=body_html,
                created_at=datetime.now(timezone.utc),
                status="draft",
            )

        except Exception as e:
            logfire.error(
                "Failed to create standalone draft",
                error=str(e),
                subject=subject,
            )
            raise

    @logfire.instrument("repo.email.update_draft")
    async def update_draft(
        self,
        draft_id: str,
        subject: str | None = None,
        body_html: str | None = None,
        to_recipients: list[EmailRecipient] | None = None,
        cc_recipients: list[EmailRecipient] | None = None,
    ) -> EmailDraft:
        """
        Update an existing draft using MS Graph PATCH /messages/{id}.

        Only fields that are provided (not None) will be updated.
        This works on any draft - both standalone drafts and reply drafts.

        Args:
            draft_id: MS Graph message ID of the draft to update
            subject: New subject line (optional)
            body_html: New body content in HTML (optional)
            to_recipients: New To recipients (optional, replaces existing)
            cc_recipients: New CC recipients (optional, replaces existing)

        Returns:
            EmailDraft DTO with updated draft details

        Raises:
            ValueError: If draft_id not found or client not initialized
            Exception: If MS Graph API call fails
        """
        if not self.client:
            raise ValueError("Microsoft Graph client not initialized")

        try:
            # Build Message with only fields to update
            message = Message()
            updated_fields = []

            if subject is not None:
                message.subject = subject
                updated_fields.append("subject")

            if body_html is not None:
                message.body = ItemBody()
                message.body.content_type = BodyType.Html
                message.body.content = body_html
                updated_fields.append("body")

            if to_recipients is not None:
                message.to_recipients = [
                    self._create_recipient(r) for r in to_recipients
                ]
                updated_fields.append("to_recipients")

            if cc_recipients is not None:
                message.cc_recipients = [
                    self._create_recipient(r) for r in cc_recipients
                ]
                updated_fields.append("cc_recipients")

            if not updated_fields:
                raise ValueError("No fields to update provided")

            # PATCH the message
            result = await (
                self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .messages.by_message_id(draft_id)
                .patch(message)
            )

            if not result:
                raise Exception(f"PATCH /messages/{draft_id} returned no result")

            # Build updated EmailDraft from result
            final_to = (
                to_recipients
                if to_recipients is not None
                else [
                    EmailRecipient(
                        email=r.email_address.address,
                        name=r.email_address.name,
                    )
                    for r in (result.to_recipients or [])
                ]
            )
            final_cc = (
                cc_recipients
                if cc_recipients is not None
                else (
                    [
                        EmailRecipient(
                            email=r.email_address.address,
                            name=r.email_address.name,
                        )
                        for r in (result.cc_recipients or [])
                    ]
                    if result.cc_recipients
                    else None
                )
            )

            logfire.info(
                "Draft updated successfully",
                draft_id=draft_id,
                updated_fields=updated_fields,
            )

            return EmailDraft(
                draft_id=result.id,
                original_message_id=None,  # Can't determine from PATCH result
                to_recipients=final_to,
                cc_recipients=final_cc,
                subject=result.subject or "",
                body_markdown="",  # Not stored
                body_html=result.body.content if result.body else "",
                created_at=result.created_date_time or datetime.now(timezone.utc),
                status="draft",
            )

        except Exception as e:
            logfire.error(
                "Failed to update draft",
                error=str(e),
                draft_id=draft_id,
            )
            raise

    # ATTACHMENT SECTION
    @logfire.instrument("repo.email.get_attachments")
    async def get_attachments(
        self,
        message_id: str,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10MB default limit
    ) -> list["EmailAttachmentInfo"]:
        """
        Fetch all attachments for a specific email.

        Uses MS Graph GET /users/{id}/messages/{message_id}/attachments
        Only fetches file attachments (not inline images or reference attachments).

        Args:
            message_id: MS Graph message ID
            max_size_bytes: Maximum size per attachment to download

        Returns:
            List of EmailAttachmentInfo with content bytes populated
        """
        if not self.client:
            raise ValueError("MS Graph client not initialized")

        try:
            # Import locally to avoid circular dependencies
            from backend.models.attachment import EmailAttachmentInfo
            import base64

            # Get attachments list
            attachments_response = (
                await self.client.users.by_user_id(settings.bio4_lognos_user_id)
                .messages.by_message_id(message_id)
                .attachments.get()
            )

            if not attachments_response or not attachments_response.value:
                return []

            result = []
            for att in attachments_response.value:
                # Only process file attachments
                if att.odata_type != "#microsoft.graph.fileAttachment":
                    continue

                # Skip if too large
                if att.size and att.size > max_size_bytes:
                    logfire.warn(
                        f"Skipping large attachment: {att.name} ({att.size} bytes)"
                    )
                    continue

                # Handle content bytes
                content = None
                if hasattr(att, "content_bytes") and att.content_bytes:
                    raw_content = att.content_bytes
                    try:
                        # Try to decode regardless of type (str or bytes)
                        # validate=True ensures we don't accidentally decode non-base64 binary data
                        content = base64.b64decode(raw_content, validate=True)
                    except Exception:
                        # If decode fails, assume it's already raw bytes
                        if isinstance(raw_content, bytes):
                            content = raw_content
                        else:
                            logfire.error(f"Failed to process content for {att.name}")
                            continue

                if content:
                    result.append(
                        EmailAttachmentInfo(
                            attachment_id=att.id,
                            filename=att.name,
                            content_type=att.content_type or "application/octet-stream",
                            size_bytes=att.size or len(content),
                            content_bytes=content,
                        )
                    )

            logfire.info(f"Fetched {len(result)} attachments for message {message_id}")
            return result

        except Exception as e:
            logfire.error(f"Failed to fetch attachments for {message_id}: {e}")
            raise
