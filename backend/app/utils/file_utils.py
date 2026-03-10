"""Utility functions for file and image operations."""

import base64
import io
from pathlib import Path
from typing import Optional


def file_to_base64(file_path: str) -> str:
    """Convert a file to base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def bytes_to_base64(data: bytes) -> str:
    """Convert bytes to base64 string."""
    return base64.b64encode(data).decode("utf-8")


def base64_to_bytes(b64_string: str) -> bytes:
    """Convert base64 string to bytes."""
    return base64.b64decode(b64_string)


def make_data_uri(data: bytes, mime_type: str = "image/png") -> str:
    """Create a data URI from bytes."""
    b64 = bytes_to_base64(data)
    return f"data:{mime_type};base64,{b64}"


def get_mime_type(filename: str) -> str:
    """Get MIME type from filename."""
    ext = Path(filename).suffix.lower()
    mime_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    return mime_map.get(ext, "application/octet-stream")


def ensure_dir(path: str) -> Path:
    """Ensure directory exists and return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
