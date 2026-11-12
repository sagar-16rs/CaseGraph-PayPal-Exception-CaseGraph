from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class UploadValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DetectedFile:
    mime: str
    extension: str


_ALLOWED_EXTENSIONS = {
    ".pdf": ("application/pdf",),
    ".png": ("image/png",),
    ".gif": ("image/gif",),
    ".jpg": ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
}


def _detect(data: bytes) -> DetectedFile:
    if data.startswith(b"%PDF-"):
        return DetectedFile("application/pdf", ".pdf")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedFile("image/png", ".png")
    if data.startswith((b"GIF87a", b"GIF89a")):
        return DetectedFile("image/gif", ".gif")
    if data.startswith(b"\xff\xd8\xff"):
        return DetectedFile("image/jpeg", ".jpg")
    raise UploadValidationError("unsupported file signature")


def validate_upload(filename: str, data: bytes, declared_content_type: str | None, max_bytes: int) -> DetectedFile:
    if not filename or len(filename) > 512:
        raise UploadValidationError("invalid filename")
    if "\x00" in filename or ":" in filename:
        raise UploadValidationError("filename contains forbidden characters")
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise UploadValidationError("unsupported file extension")
    if not data:
        raise UploadValidationError("empty files are not allowed")
    if len(data) > max_bytes:
        raise UploadValidationError("file exceeds configured size limit")

    detected = _detect(data)
    allowed_mimes = _ALLOWED_EXTENSIONS[suffix]
    if detected.mime not in allowed_mimes:
        # JPEG may use .jpg or .jpeg; normalize stored extension to original suffix.
        raise UploadValidationError("file extension does not match file signature")
    if declared_content_type:
        declared = declared_content_type.split(";", 1)[0].strip().lower()
        if declared and declared not in {detected.mime, "application/octet-stream"}:
            raise UploadValidationError("declared Content-Type does not match file signature")
    return DetectedFile(detected.mime, suffix)
