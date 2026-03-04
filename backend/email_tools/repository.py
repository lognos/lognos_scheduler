from typing import Any

import logfire
from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient

from backend.config.settings import settings


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
