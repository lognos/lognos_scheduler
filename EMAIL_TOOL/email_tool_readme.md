# Email tool package for agent reuse

## Purpose

This folder contains a direct copy of the communication agent email tool stack so another Pydantic AI agent (for example, the schedule agent) can reuse the same capabilities:

- read emails
- draft responses
- create new drafts
- modify drafts
- send draft or new emails
- process email attachments

## Folder structure

```text
EMAIL_TOOL/
  backend/
    tools/
      email_tools.py
      __init__.py
    services/
      email_service.py
      email_processing_service.py
      attachment_processor_service.py
      __init__.py
    repositories/
      email_repository.py
      __init__.py
    models/
      domain.py
      attachment.py
      __init__.py
    utils/
      formatting.py
      email_templates.py
      __init__.py
    config/
      settings.py
      __init__.py
```

## Included tools

From `backend/tools/email_tools.py`:

- `send_email_tool`
- `send_email_html_tool`
- `check_email_service_health_tool`
- `search_emails_tool`
- `draft_email_response_tool`
- `list_email_drafts_tool`
- `send_draft_tool`
- `create_email_draft_tool`
- `modify_draft_tool`
- `get_email_attachments_tool`

## Core dependencies for runtime

Packages used by this stack:

- `pydantic-ai[google,logfire]`
- `msgraph-sdk`
- `azure-identity`
- `jinja2`
- `markdown`
- `bleach`
- `google-genai`
- `pandas`
- `openpyxl`
- `python-docx`

## Required environment variables

The copied implementation currently depends on `backend/config/settings.py` and expects these values at minimum for email and attachment flow:

- `TENANT_ID`
- `CLIENT_ID`
- `CLIENT_SECRET`
- `BIO4_AGENT_EMAIL_ADDRESS`
- `BIO4_LOGNOS_USER_ID`
- `GOOGLE_API_KEY` (or `GEMINI_API_KEY` fallback)
- `DOC_PROCESSOR_MODEL_NAME` (optional; has a default)

Important: the copied `settings.py` also includes required Supabase variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) because this is a raw copy from the comm backend. If your schedule agent does not use Supabase in this tool, replace this settings dependency with the schedule agent settings module or create a minimal email-tool-specific settings class.

## Integration pattern in the schedule agent

Register the same tools in the schedule agent after wiring dependencies:

```python
from dataclasses import dataclass
from pydantic_ai import Agent

from backend.services.email_service import EmailService
from backend.services.email_processing_service import EmailProcessingService
from backend.repositories.email_repository import EmailRepository
from backend.tools.email_tools import (
    send_email_tool,
    send_email_html_tool,
    check_email_service_health_tool,
    search_emails_tool,
    draft_email_response_tool,
    list_email_drafts_tool,
    send_draft_tool,
    create_email_draft_tool,
    modify_draft_tool,
    get_email_attachments_tool,
)

@dataclass
class ScheduleAgentDependencies:
    email_service: EmailService
    email_processing_service: EmailProcessingService

email_repo = EmailRepository()
email_service = EmailService(repository=email_repo)
email_processing_service = EmailProcessingService(email_repository=email_repo)

agent: Agent[ScheduleAgentDependencies, YourOutputModel] = Agent(...)
agent.tool(send_email_tool)
agent.tool(send_email_html_tool)
agent.tool(check_email_service_health_tool)
agent.tool(search_emails_tool)
agent.tool(draft_email_response_tool)
agent.tool(list_email_drafts_tool)
agent.tool(send_draft_tool)
agent.tool(create_email_draft_tool)
agent.tool(modify_draft_tool)
agent.tool(get_email_attachments_tool)
```

## Notes for adaptation

- Imports are still under `backend.*` to preserve compatibility with your current architecture.
- If the schedule agent uses a different module namespace, update imports consistently across copied files.
- Attachment processing currently supports PDF, DOCX, and XLSX/XLS.
- Draft and send operations use Microsoft Graph mailbox configured by `BIO4_LOGNOS_USER_ID` and sender configured by `BIO4_AGENT_EMAIL_ADDRESS`.
