"""
Email Processing Service

Orchestrates email response workflow:
- Validates search filters
- Coordinates repository calls
- Aggregates batch processing results
"""

import logfire
from datetime import datetime, timezone

from backend.models.domain import (
    EmailSearchFilters,
    UnreadEmail,
    EmailDraft,
    EmailProcessingResult,
)
from backend.repositories.email_repository import EmailRepository


class EmailProcessingService:
    """
    Service for email processing workflows.

    Coordinates between agent tools and email repository.
    Handles batch processing logic and error aggregation.
    """

    def __init__(self, email_repository: EmailRepository):
        """
        Initialize with email repository dependency.

        Args:
            email_repository: EmailRepository instance for MS Graph operations
        """
        self.email_repo = email_repository

    @logfire.instrument("service.email_processing.search_and_validate")
    async def search_and_validate_emails(
        self, filters: EmailSearchFilters
    ) -> list[UnreadEmail]:
        """
        Search emails and validate results before processing.

        Args:
            filters: EmailSearchFilters with search criteria

        Returns:
            List of UnreadEmail DTOs ready for processing

        Raises:
            ValueError: If filters are invalid
        """
        logfire.info("Searching emails with filters", filters=filters.model_dump())

        # Validate folder
        if filters.folder not in ["inbox", "sent", "drafts"]:
            raise ValueError(f"Invalid folder: {filters.folder}")

        # Search emails
        emails = await self.email_repo.search_emails(filters)

        logfire.info(f"Found {len(emails)} emails matching criteria")
        return emails

    @logfire.instrument("service.email_processing.create_batch_result")
    def create_batch_result(
        self,
        processed_count: int,
        drafts: list[EmailDraft],
        errors: list[dict] | None = None,
    ) -> EmailProcessingResult:
        """
        Create aggregated result for batch email processing.

        Args:
            processed_count: Number of emails processed
            drafts: List of successfully created drafts
            errors: List of error details (if any)

        Returns:
            EmailProcessingResult DTO with complete summary
        """
        return EmailProcessingResult(
            processed_count=processed_count,
            drafts_created=drafts,
            errors=errors,
            timestamp=datetime.now(timezone.utc),
        )
