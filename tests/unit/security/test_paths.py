"""Tests for the filesystem path security policy."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nexusai.app.security.paths import (
    PathNotFoundError,
    PathNotReadableError,
    PathOutsideRootError,
    PathPolicy,
    PathResolutionStatus,
    UnsupportedFileTypeError,
)


@pytest.fixture
def workspace(tmp_path):
    """Return a workspace with an allowed root and an outside directory."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (allowed / "ok.md").write_text("hello", encoding="utf-8")
    (allowed / "bad.exe").write_text("x", encoding="utf-8")
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    return tmp_path, allowed, outside


def test_valid_path_is_allowed(workspace):
    """Test that a file inside the root is allowed."""
    _tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed])
    resolved = policy.resolve(allowed / "ok.md")
    assert resolved.is_absolute()
    assert resolved.exists()


def test_traversal_is_rejected(workspace):
    """Test that ../ traversal is rejected."""
    _tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed])
    with pytest.raises(PathOutsideRootError):
        policy.resolve(allowed / ".." / "outside" / "secret.txt")


def test_absolute_path_outside_root_is_rejected(workspace):
    """Test that an absolute path outside the root is rejected."""
    _tmp, _allowed, outside = workspace
    policy = PathPolicy(roots=[outside.parent / "allowed"])
    with pytest.raises(PathOutsideRootError):
        policy.resolve(outside / "secret.txt")


def test_path_outside_root_is_rejected(workspace):
    """Test that a path in an unconfigured directory is rejected."""
    _tmp, allowed, outside = workspace
    policy = PathPolicy(roots=[allowed])
    with pytest.raises(PathOutsideRootError):
        policy.resolve(outside / "secret.txt")


def test_nonexistent_path_is_reported(workspace):
    """Test that a missing file is reported as not found."""
    _tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed])
    with pytest.raises(PathNotFoundError):
        policy.resolve(allowed / "missing.md")


def test_unsupported_extension_is_rejected(workspace):
    """Test that an unreadable file type is rejected."""
    _tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed])
    with pytest.raises(UnsupportedFileTypeError):
        policy.resolve(allowed / "bad.exe")


def test_directory_is_rejected(workspace):
    """Test that a directory is not treated as a readable document."""
    _tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed])
    with pytest.raises(PathNotReadableError):
        policy.resolve(allowed)


def test_no_roots_rejects_relative_path(tmp_path):
    """Test that a relative path is rejected when no root is configured."""
    policy = PathPolicy(roots=[])
    with pytest.raises(PathOutsideRootError):
        policy.resolve("some/file.md")


def test_relative_path_resolves_against_base_dir(workspace):
    """Test that a relative path is resolved against the base directory."""
    tmp, _allowed, _outside = workspace
    (tmp / "data").mkdir()
    (tmp / "data" / "file.md").write_text("hello", encoding="utf-8")

    policy = PathPolicy(roots=[tmp / "data"], base_dir=tmp)
    resolved = policy.resolve(Path("data/file.md"))
    assert resolved.exists()


def test_relative_path_still_checked_against_roots(workspace):
    """Test that base-dir resolution does not widen what may be read."""
    tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed], base_dir=tmp)
    with pytest.raises(PathOutsideRootError):
        policy.resolve(Path("outside/secret.txt"))


def test_symlink_escape_is_rejected(workspace):
    """Test that a symlink inside the root pointing outside is rejected.

    Creating a symlink needs a privilege that Windows does not grant by
    default, so the test is skipped when the platform refuses.
    """
    _tmp, allowed, outside = workspace
    link = allowed / "escape.md"
    try:
        os.symlink(outside / "secret.txt", link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not available here: {exc}")

    policy = PathPolicy(roots=[allowed])
    with pytest.raises(PathOutsideRootError):
        policy.resolve(link)


def test_symlink_inside_root_is_allowed(workspace):
    """Test that a symlink to a file inside the root is allowed."""
    _tmp, allowed, _outside = workspace
    target = allowed / "ok.md"
    link = allowed / "link.md"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not available here: {exc}")

    policy = PathPolicy(roots=[allowed])
    assert policy.is_allowed(link)


def test_check_reports_status_without_raising(workspace):
    """Test the non-raising check."""
    _tmp, allowed, outside = workspace
    policy = PathPolicy(roots=[allowed])

    status, resolved, message = policy.check(allowed / "ok.md")
    assert status == PathResolutionStatus.ALLOWED
    assert resolved is not None
    assert message is None

    status, resolved, message = policy.check(outside / "secret.txt")
    assert status == PathResolutionStatus.OUTSIDE_ROOT
    assert resolved is None
    assert message


def test_is_allowed_helper(workspace):
    """Test the boolean helper."""
    _tmp, allowed, outside = workspace
    policy = PathPolicy(roots=[allowed])
    assert policy.is_allowed(allowed / "ok.md") is True
    assert policy.is_allowed(outside / "secret.txt") is False


def test_add_root(workspace):
    """Test that a root can be added later."""
    _tmp, allowed, outside = workspace
    policy = PathPolicy(roots=[allowed])
    assert policy.is_allowed(outside / "secret.txt") is False
    policy.add_root(outside)
    assert policy.is_allowed(outside / "secret.txt") is True


def test_multiple_roots(workspace):
    """Test that several roots are honoured."""
    tmp, allowed, outside = workspace
    other = tmp / "other"
    other.mkdir()
    (other / "file.md").write_text("x", encoding="utf-8")

    policy = PathPolicy(roots=[allowed, other])
    assert policy.is_allowed(allowed / "ok.md") is True
    assert policy.is_allowed(other / "file.md") is True
    assert policy.is_allowed(outside / "secret.txt") is False


def test_root_itself_is_traversable_for_containment(workspace):
    """Test that a path equal to the root is inside it."""
    _tmp, allowed, _outside = workspace
    policy = PathPolicy(roots=[allowed])
    assert policy.is_within_roots(allowed) is True
    assert policy.is_within_roots(allowed.parent) is False
