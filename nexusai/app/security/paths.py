"""Filesystem path security for NexusAI.

Every path that reaches the filesystem — whether from the document API,
the tool registry or the executor — passes through this module first. The
policy is deliberately narrow:

* A path is resolved to a canonical absolute path.
* The canonical path must sit inside an allowed root.
* Symlinks are resolved *before* the containment check, so a link inside
  the root that points outside it is rejected.
* ``..`` traversal is resolved away by canonicalisation and then caught
  by the containment check.
* The resolved path must exist, be a regular file, and be readable.

The result is that a caller can never read a file outside the configured
roots, however the path was spelled.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path


class PathPolicyError(Exception):
    """Base class for path policy violations."""

    def __init__(self, message: str, code: str) -> None:
        self.code = code
        super().__init__(message)


class PathOutsideRootError(PathPolicyError):
    """The resolved path lies outside every allowed root."""


class UnsupportedFileTypeError(PathPolicyError):
    """The file extension is not one NexusAI can read."""


class PathNotFoundError(PathPolicyError):
    """The path does not exist."""


class PathNotReadableError(PathPolicyError):
    """The path is not a regular file, or cannot be read."""


class PathResolutionStatus(StrEnum):
    """Outcome of a path policy check."""

    ALLOWED = "allowed"
    OUTSIDE_ROOT = "outside_root"
    UNSUPPORTED_TYPE = "unsupported_type"
    NOT_FOUND = "not_found"
    NOT_READABLE = "not_readable"


#: File extensions NexusAI is able to read. The document extractors cover
#: the first four; the tabular extensions are read by the CSV analysis
#: tool.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".txt",
        ".text",
        ".md",
        ".markdown",
        ".csv",
        ".tsv",
    }
)


class PathPolicy:
    """Restricts filesystem access to a set of allowed roots.

    Attributes:
        roots: The canonical directories that may be read.
    """

    def __init__(
        self,
        roots: Iterable[Path | str] | None = None,
        allowed_extensions: frozenset[str] | None = None,
        base_dir: Path | str | None = None,
    ) -> None:
        self.roots: list[Path] = []
        for root in roots or []:
            resolved = self._canonicalise(Path(root))
            if resolved is not None and resolved not in self.roots:
                self.roots.append(resolved)
        self.allowed_extensions = (
            allowed_extensions
            if allowed_extensions is not None
            else ALLOWED_EXTENSIONS
        )
        # Relative paths are interpreted against this directory. It is the
        # project root by default, so a caller writing
        # ``data/sample/file.md`` means what they expect. The resolved path
        # is still checked against the allowed roots.
        self.base_dir = (
            self._canonicalise(Path(base_dir)) if base_dir is not None else None
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _canonicalise(path: Path) -> Path | None:
        """Return the canonical form of *path*, or None when it cannot exist.

        ``Path.resolve`` is used with ``strict=False`` so a path that does
        not exist still resolves; symlinks in the existing part of the
        path are still resolved, which is what makes a symlink escape
        detectable.
        """
        try:
            return Path(os.path.realpath(str(path)))
        except (OSError, ValueError):
            return None

    def is_within_roots(self, candidate: Path) -> bool:
        """Return True when *candidate* is inside one of the allowed roots."""
        for root in self.roots:
            try:
                candidate.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _find_under_roots(self, name: str) -> Path | None:
        """Find a file with the given name under one of the allowed roots.

        The search is recursive but bounded to the allowed roots, so a
        match is always inside an allowed root. The first match in root
        order wins; a shallow directory is walked before a deep one so
        the closest match is preferred.
        """
        for root in self.roots:
            if not root.is_dir():
                continue
            # Prefer the shallowest match so the nearest file wins.
            matches = sorted(
                (path for path in root.rglob(name) if path.is_file()),
                key=lambda path: (len(path.relative_to(root).parts), str(path)),
            )
            if matches:
                return matches[0]
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve(self, path: Path | str) -> Path:
        """Resolve *path* under the policy, or raise a policy error.

        Args:
            path: The requested path.

        Returns:
            The canonical absolute path.

        Raises:
            PathNotFoundError: The path does not exist.
            PathOutsideRootError: The path resolves outside the allowed roots.
            UnsupportedFileTypeError: The extension is not readable.
            PathNotReadableError: The path is not a readable regular file.
        """
        raw = Path(path)

        if not raw.is_absolute():
            # A bare file name such as ``sales_2026.csv`` names a file
            # without saying where it is. It is looked for under each
            # allowed root. This never widens what may be read: a
            # candidate is only accepted when it is inside a root.
            is_bare_name = len(raw.parts) == 1
            if is_bare_name:
                found = self._find_under_roots(raw.name)
                if found is not None:
                    raw = found

            if not raw.is_absolute():
                # Otherwise a relative path is interpreted against the base
                # directory — the project root by default — so a caller
                # writing ``data/sample/file.md`` means what they expect.
                # The result is still checked against the allowed roots.
                if self.base_dir is not None:
                    raw = self.base_dir / raw
                elif self.roots:
                    raw = self.roots[0] / raw
                else:
                    raise PathOutsideRootError(
                        "No allowed document root is configured.", code="no_roots"
                    )

        canonical = self._canonicalise(raw)
        if canonical is None:
            raise PathNotReadableError(
                f"Could not resolve path: {path}", code="unresolvable_path"
            )

        # The containment check comes before the existence check so that a
        # path outside the root is reported as such rather than leaking
        # whether it exists.
        if not self.is_within_roots(canonical):
            raise PathOutsideRootError(
                f"Path is outside the allowed document root: {path}",
                code="outside_root",
            )

        if not canonical.exists():
            raise PathNotFoundError(
                f"Path does not exist: {path}", code="not_found"
            )

        if not canonical.is_file():
            raise PathNotReadableError(
                f"Path is not a regular file: {path}", code="not_a_file"
            )

        suffix = canonical.suffix.lower()
        if self.allowed_extensions and suffix not in self.allowed_extensions:
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{suffix or '(no extension)'}'",
                code="unsupported_type",
            )

        if not os.access(canonical, os.R_OK):
            raise PathNotReadableError(
                f"Path is not readable: {path}", code="not_readable"
            )

        return canonical

    def check(self, path: Path | str) -> tuple[PathResolutionStatus, Path | None, str | None]:
        """Check *path* under the policy without raising.

        Returns:
            A tuple of (status, resolved path or None, message or None).
        """
        try:
            resolved = self.resolve(path)
        except PathPolicyError as exc:
            status = {
                "outside_root": PathResolutionStatus.OUTSIDE_ROOT,
                "no_roots": PathResolutionStatus.OUTSIDE_ROOT,
                "unsupported_type": PathResolutionStatus.UNSUPPORTED_TYPE,
                "not_found": PathResolutionStatus.NOT_FOUND,
                "not_a_file": PathResolutionStatus.NOT_READABLE,
                "not_readable": PathResolutionStatus.NOT_READABLE,
                "unresolvable_path": PathResolutionStatus.NOT_READABLE,
            }.get(exc.code, PathResolutionStatus.NOT_READABLE)
            return status, None, str(exc)
        return PathResolutionStatus.ALLOWED, resolved, None

    def is_allowed(self, path: Path | str) -> bool:
        """Return True when *path* may be read under the policy."""
        status, _, _ = self.check(path)
        return status == PathResolutionStatus.ALLOWED

    def add_root(self, root: Path | str) -> None:
        """Add an allowed root."""
        resolved = self._canonicalise(Path(root))
        if resolved is not None and resolved not in self.roots:
            self.roots.append(resolved)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PathPolicy(roots={[str(r) for r in self.roots]})"
