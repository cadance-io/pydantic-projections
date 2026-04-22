"""Elegant projection of Pydantic ``BaseModel``s through Python ``Protocol``s.

Public API:
    - :func:`project` — one-shot: project an instance through a Protocol.
    - :func:`projection` — get (or build) the cached ``BaseModel`` class for a Protocol.
    - :func:`project_json` — shortcut for ``project(...).model_dump_json(...)``.
    - :func:`cache_clear` — clear the projection class cache.
    - :class:`ProjectionError` — raised when an instance does not satisfy the Protocol.
"""

from ._core import (
    ProjectionError,
    cache_clear,
    project,
    project_json,
    projection,
)

__all__ = [
    "ProjectionError",
    "cache_clear",
    "project",
    "project_json",
    "projection",
]
