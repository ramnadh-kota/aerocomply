"""Unit tests for storage key/filename safety helpers (pure functions, no I/O)."""

from __future__ import annotations

import uuid

import pytest

from app.services.storage.keys import build_object_key, sanitize_filename


class TestSanitizeFilename:
    def test_normal_filename_is_unchanged(self):
        assert sanitize_filename("report.pdf") == "report.pdf"

    def test_spaces_are_preserved(self):
        assert sanitize_filename("inspection photo.jpg") == "inspection photo.jpg"

    def test_unicode_filename_is_preserved(self):
        assert sanitize_filename("检查报告.pdf") == "检查报告.pdf"

    def test_forward_slash_keeps_only_final_segment(self):
        assert sanitize_filename("a/b/c.pdf") == "c.pdf"

    def test_backslash_keeps_only_final_segment(self):
        assert sanitize_filename("a\\b\\c.pdf") == "c.pdf"

    def test_path_traversal_is_defeated(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_absolute_path_keeps_only_final_segment(self):
        assert sanitize_filename("/etc/passwd") == "passwd"

    def test_windows_absolute_path_keeps_only_final_segment(self):
        assert sanitize_filename("C:\\Windows\\System32\\evil.exe") == "evil.exe"

    def test_empty_filename_falls_back(self):
        assert sanitize_filename("") == "file"

    def test_dot_and_dotdot_fall_back(self):
        assert sanitize_filename(".") == "file"
        assert sanitize_filename("..") == "file"

    def test_control_characters_are_stripped(self):
        assert sanitize_filename("report\x00\x1f.pdf") == "report.pdf"

    def test_long_filename_is_truncated_preserving_extension(self):
        name = "a" * 300 + ".pdf"
        result = sanitize_filename(name)
        assert len(result) <= 200
        assert result.endswith(".pdf")

    def test_long_filename_without_short_extension_is_hard_truncated(self):
        name = "a" * 300
        result = sanitize_filename(name)
        assert len(result) <= 200

    def test_custom_fallback_is_used(self):
        assert sanitize_filename("", fallback="unnamed") == "unnamed"

    def test_special_characters_are_preserved_when_safe(self):
        # Not a path separator or control char -- safe to keep as-is; S3 keys
        # accept a wide range of characters and this is not an authorization
        # boundary (only path-escape and length are).
        assert sanitize_filename("report (final) v2.pdf") == "report (final) v2.pdf"


class TestBuildObjectKey:
    def test_builds_deterministic_key(self):
        org_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        resource_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        file_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        key = build_object_key(
            namespace="evidence",
            organization_id=org_id,
            resource_id=resource_id,
            file_id=file_id,
            filename="report.pdf",
        )
        assert key == (
            "evidence/11111111-1111-1111-1111-111111111111/"
            "22222222-2222-2222-2222-222222222222/"
            "33333333-3333-3333-3333-333333333333_report.pdf"
        )

    def test_sanitizes_the_filename_component(self):
        key = build_object_key(
            namespace="evidence",
            organization_id=uuid.uuid4(),
            resource_id=uuid.uuid4(),
            file_id=uuid.uuid4(),
            filename="../../etc/passwd",
        )
        assert key.endswith("_passwd")
        assert ".." not in key

    def test_rejects_invalid_namespace(self):
        with pytest.raises(ValueError):
            build_object_key(
                namespace="Evidence/../whatever",
                organization_id=uuid.uuid4(),
                resource_id=uuid.uuid4(),
                file_id=uuid.uuid4(),
                filename="a.pdf",
            )

    def test_different_organizations_never_collide(self):
        resource_id = uuid.uuid4()
        file_id = uuid.uuid4()
        key_a = build_object_key(
            namespace="evidence",
            organization_id=uuid.uuid4(),
            resource_id=resource_id,
            file_id=file_id,
            filename="a.pdf",
        )
        key_b = build_object_key(
            namespace="evidence",
            organization_id=uuid.uuid4(),
            resource_id=resource_id,
            file_id=file_id,
            filename="a.pdf",
        )
        assert key_a != key_b
