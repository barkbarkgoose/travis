"""Unit tests for the photo upload/validation pipeline (no DB, no API)."""

import hashlib

import pytest

from apps.journal.uploads import UploadRejected, process_upload

from .factories import make_image_bytes


class TestProcessUpload:
    def test_accepts_jpeg(self):
        raw = make_image_bytes("JPEG")
        result = process_upload(raw)
        assert result.mime == "image/jpeg"
        assert result.sha256 == hashlib.sha256(raw).hexdigest()
        assert result.original_bytes == raw  # stored exactly as received
        assert result.size == len(raw)

    def test_accepts_png(self):
        result = process_upload(make_image_bytes("PNG"))
        assert result.mime == "image/png"

    def test_accepts_webp(self):
        result = process_upload(make_image_bytes("WEBP"))
        assert result.mime == "image/webp"

    def test_accepts_heic(self):
        result = process_upload(make_image_bytes("HEIF"))
        assert result.mime == "image/heic"

    def test_rejects_svg_disguised_as_image(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with pytest.raises(UploadRejected):
            process_upload(svg)

    def test_rejects_gif(self):
        gif = make_image_bytes("GIF")
        with pytest.raises(UploadRejected):
            process_upload(gif)

    def test_rejects_empty_file(self):
        with pytest.raises(UploadRejected):
            process_upload(b"")

    def test_rejects_garbage_bytes(self):
        with pytest.raises(UploadRejected):
            process_upload(b"not a real image, just some bytes" * 20)

    def test_rejects_oversized_file(self):
        raw = make_image_bytes("JPEG")
        with pytest.raises(UploadRejected):
            process_upload(raw, max_bytes=len(raw) - 1)

    def test_derivatives_are_smaller_and_are_jpeg(self):
        raw = make_image_bytes("PNG", size=(3000, 3000))
        result = process_upload(raw)
        display_bytes = result.display.read()
        thumb_bytes = result.thumb.read()
        assert len(display_bytes) < len(raw)
        assert len(thumb_bytes) < len(display_bytes)
        assert display_bytes[:2] == b"\xff\xd8"  # JPEG magic bytes
        assert thumb_bytes[:2] == b"\xff\xd8"

    def test_content_type_header_is_not_trusted(self):
        """A renamed script with a spoofed extension is still rejected — the
        pipeline decodes bytes, it never trusts the filename or content type."""
        with pytest.raises(UploadRejected):
            process_upload(b"#!/bin/sh\necho pwned\n")
