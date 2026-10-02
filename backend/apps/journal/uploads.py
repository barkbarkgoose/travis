"""Photo upload pipeline: validate, hash, and derive display/thumbnail copies.

Nothing here trusts the browser's `Content-Type` or the filename extension —
every file is decoded with Pillow before it's accepted, which is what actually
rejects an SVG or a renamed script. The original bytes the visitor uploaded are
stored exactly as received; only the display and thumbnail derivatives are
regenerated from that decode.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone

import pillow_heif
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import ExifTags, Image, UnidentifiedImageError

pillow_heif.register_heif_opener()

# Pillow's format name for each type we accept. SVG, PDF, GIF, and anything
# else Pillow can technically open are deliberately excluded.
ALLOWED_FORMATS = {"JPEG", "PNG", "HEIF", "WEBP"}

DISPLAY_MAX_DIMENSION = 2000
THUMB_MAX_DIMENSION = 480
DISPLAY_JPEG_QUALITY = 85
THUMB_JPEG_QUALITY = 80

# EXIF tag ids, resolved by name once at import time rather than re-scanning
# ExifTags.TAGS per file.
_EXIF_TAGS_BY_NAME = {name: tag_id for tag_id, name in ExifTags.TAGS.items()}
_DATETIME_ORIGINAL_TAG = _EXIF_TAGS_BY_NAME.get("DateTimeOriginal")
_ORIENTATION_TAG = _EXIF_TAGS_BY_NAME.get("Orientation")


class UploadRejected(ValueError):
    """A user-facing reason the upload was refused."""


@dataclass
class ProcessedPhoto:
    original_bytes: bytes
    display: ContentFile
    thumb: ContentFile
    sha256: str
    size: int
    mime: str
    exif_taken_at: datetime | None


def _mime_for_format(pillow_format: str) -> str:
    return {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "HEIF": "image/heic",
        "WEBP": "image/webp",
    }[pillow_format]


def _parse_exif_datetime(value: str) -> datetime | None:
    # EXIF DateTimeOriginal has no timezone; treat it as local time captured,
    # stored naive-to-UTC is wrong, so we leave it naive and let the caller
    # decide — here we just attach UTC as a placeholder read time is not
    # authoritative anyway (uploaded_at, which is tz-aware, is the fallback).
    try:
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").replace(tzinfo=dt_timezone.utc)
    except (ValueError, TypeError):
        return None


def _make_derivative(image: Image.Image, max_dimension: int, quality: int) -> ContentFile:
    derived = image.copy()
    derived.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    if derived.mode not in ("RGB", "L"):
        derived = derived.convert("RGB")
    buffer = io.BytesIO()
    # exif=b"" strips all EXIF (including GPS) from the derivative; the
    # original, stored separately and untouched, is the record that keeps it.
    derived.save(buffer, format="JPEG", quality=quality, optimize=True, exif=b"")
    return ContentFile(buffer.getvalue())


def process_upload(raw: bytes, max_bytes: int | None = None) -> ProcessedPhoto:
    """Validate and process an uploaded photo's raw bytes.

    Raises `UploadRejected` with a message safe to show the uploader.
    """
    max_bytes = max_bytes or getattr(settings, "MAX_PHOTO_UPLOAD_BYTES", 25 * 1024 * 1024)
    if len(raw) > max_bytes:
        raise UploadRejected(
            f"That photo is too large ({len(raw) / 1024 / 1024:.1f} MB). "
            f"The limit is {max_bytes / 1024 / 1024:.0f} MB."
        )
    if not raw:
        raise UploadRejected("The upload was empty.")

    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()  # cheap structural check; re-open below to actually decode
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise UploadRejected(
            "That doesn't look like a photo we can accept (JPEG, PNG, HEIC or WebP)."
        )

    pillow_format = (image.format or "").upper()
    if pillow_format not in ALLOWED_FORMATS:
        raise UploadRejected(
            f"{pillow_format or 'That file type'} isn't supported. "
            "Please upload a JPEG, PNG, HEIC or WebP photo."
        )

    exif_taken_at = None
    try:
        exif = image.getexif()
        if _DATETIME_ORIGINAL_TAG and _DATETIME_ORIGINAL_TAG in exif:
            exif_taken_at = _parse_exif_datetime(exif[_DATETIME_ORIGINAL_TAG])
        # Respect EXIF orientation before generating derivatives, since the
        # thumbnail/display copies carry no EXIF of their own to correct it.
        if _ORIENTATION_TAG and _ORIENTATION_TAG in exif:
            orientation = exif[_ORIENTATION_TAG]
            rotations = {3: 180, 6: 270, 8: 90}
            if orientation in rotations:
                image = image.rotate(rotations[orientation], expand=True)
    except Exception:
        # A malformed EXIF block should never fail the whole upload.
        pass

    display = _make_derivative(image, DISPLAY_MAX_DIMENSION, DISPLAY_JPEG_QUALITY)
    thumb = _make_derivative(image, THUMB_MAX_DIMENSION, THUMB_JPEG_QUALITY)

    return ProcessedPhoto(
        original_bytes=raw,
        display=display,
        thumb=thumb,
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        mime=_mime_for_format(pillow_format),
        exif_taken_at=exif_taken_at,
    )
