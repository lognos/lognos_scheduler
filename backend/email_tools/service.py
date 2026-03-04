import logfire

from backend.email_tools.models import EmailHealthStatus
from backend.email_tools.repository import EmailRepository


class EmailService:
    def __init__(self, repository: EmailRepository):
        self.repository = repository

    @logfire.instrument("EmailService.check_health")
    async def check_health(self) -> EmailHealthStatus:
        result = await self.repository.check_health()
        return EmailHealthStatus(**result)
