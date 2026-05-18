from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class EmailHealthStatus(BaseModel):
    model_config = ConfigDict(strict=True)

    status: str
    message: str


class EmailRecipient(BaseModel):
    model_config = ConfigDict(strict=True)

    email: EmailStr
    name: str | None = None


class EmailDraftSummary(BaseModel):
    model_config = ConfigDict(strict=True)

    draft_id: str
    subject: str
    to: list[str]
    cc: list[str] = []
    created_at: datetime


class EmailDraftOperationResult(BaseModel):
    model_config = ConfigDict(strict=True)

    success: bool
    draft_id: str | None = None
    subject: str | None = None
    to: list[str] = []
    cc: list[str] = []
    timestamp: datetime | None = None
    message: str
    error: str | None = None


class EmailDirectSendResult(BaseModel):
    model_config = ConfigDict(strict=True)

    success: bool
    subject: str
    to: list[str]
    cc: list[str] = []
    timestamp: datetime | None = None
    message: str
    error: str | None = None
