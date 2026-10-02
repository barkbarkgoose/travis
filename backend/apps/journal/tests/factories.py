"""Small test helpers for building images and API clients."""

from __future__ import annotations

import io

import pillow_heif
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

pillow_heif.register_heif_opener()


def make_image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (60, 40), color=(200, 50, 50)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def make_image_file(
    name: str = "photo.jpg", fmt: str = "JPEG", content_type: str = "image/jpeg", **kwargs
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, make_image_bytes(fmt=fmt, **kwargs), content_type=content_type)


def make_heic_file(name: str = "photo.heic") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name, make_image_bytes(fmt="HEIF"), content_type="image/heic"
    )
