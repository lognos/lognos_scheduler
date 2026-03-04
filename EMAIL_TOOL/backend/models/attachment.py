"""
Domain models for attachment processing.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

class AttachmentMetadata(BaseModel):
    """Metadata about a processed attachment."""
    model_config = ConfigDict(strict=True, frozen=True)
    
    filename: str = Field(..., min_length=1, description="Name of the file")
    content_type: str = Field(..., pattern=r"^application/.*|^text/.*|^image/.*", description="MIME type")
    size_bytes: int = Field(..., ge=0, description="Size in bytes")
    page_count: int | None = Field(None, ge=0, description="Number of pages (PDF)")
    sheet_count: int | None = Field(None, ge=0, description="Number of sheets (Excel)")
    sheet_names: list[str] | None = Field(None, description="List of visible sheet names (Excel)")
    paragraph_count: int | None = Field(None, ge=0, description="Number of paragraphs (Word)")

class AttachmentSummary(BaseModel):
    """Result of processing an attachment."""
    model_config = ConfigDict(strict=True, frozen=True)
    
    metadata: AttachmentMetadata
    extracted_text: str = Field(..., description="Full extracted text (truncated)")
    summary: str = Field(..., description="LLM-generated summary")
    processing_status: Literal["success", "partial", "failed"]
    error_message: str | None = None

class EmailAttachmentInfo(BaseModel):
    """Attachment info from MS Graph."""
    model_config = ConfigDict(strict=True, frozen=True)
    
    attachment_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    content_type: str
    size_bytes: int = Field(..., ge=0)
    content_bytes: bytes | None = None  # Populated when fetched
