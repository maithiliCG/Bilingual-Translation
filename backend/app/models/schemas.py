"""Pydantic schemas for request/response models."""

from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class JobStatus(str, Enum):
    """Job processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class LanguageInfo(BaseModel):
    """Language information."""
    code: str
    name: str
    native_name: str


class TranslateRequest(BaseModel):
    """Translation request metadata (file comes via multipart)."""
    target_language: str = Field(..., description="Target language code (e.g., 'te', 'hi')")


class PageResult(BaseModel):
    """Result for a single page."""
    page_number: int
    status: str = "pending"
    original_markdown: Optional[str] = None
    translated_markdown: Optional[str] = None
    reconstructed_html: Optional[str] = None
    original_image_base64: Optional[str] = None
    layout_details: Optional[list] = None
    error: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Job status response."""
    job_id: str
    status: JobStatus
    total_pages: int = 0
    completed_pages: int = 0
    current_stage: str = ""
    message: str = ""
    pages: List[PageResult] = []
    error: Optional[str] = None


class SSEPageEvent(BaseModel):
    """Server-Sent Event for a page completion."""
    event_type: str = "page_complete"
    job_id: str
    page_number: int
    total_pages: int
    status: str
    original_image_base64: Optional[str] = None
    original_markdown: Optional[str] = None
    translated_markdown: Optional[str] = None
    reconstructed_html: Optional[str] = None
    error: Optional[str] = None


class SSEProgressEvent(BaseModel):
    """Server-Sent Event for progress updates."""
    event_type: str = "progress"
    job_id: str
    message: str
    stage: str
    page_number: Optional[int] = None
    total_pages: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "1.0.0"
    services: dict = {}
