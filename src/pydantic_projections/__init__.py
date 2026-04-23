"""Elegant projection of Pydantic ``BaseModel``s through Python ``Protocol``s.

Public API:
    - :func:`project` — one-shot: project an instance through a Protocol.
    - :func:`projection` — get (or build) the cached ``BaseModel`` class for a Protocol.
    - :func:`project_json` — shortcut for ``project(...).model_dump_json(...)``.
    - :func:`project_json_bytes` — bytes-returning equivalent; skips the ``str`` hop.
    - :func:`cache_clear` — clear the projection class cache.
    - :class:`ProjectionError` — raised when an instance does not satisfy the Protocol.
    - :class:`ProjectedResponse` — FastAPI response class that serializes a source
      instance through a Protocol straight to JSON bytes. Available only if
      ``fastapi`` is installed; imported lazily via attribute access.
"""

from typing import TYPE_CHECKING, Any

from ._core import (
    ProjectionError,
    cache_clear,
    project,
    project_json,
    project_json_bytes,
    projection,
)

if TYPE_CHECKING:
    from .fastapi import ProjectedResponse

__all__ = [
    "ProjectedResponse",
    "ProjectionError",
    "cache_clear",
    "project",
    "project_json",
    "project_json_bytes",
    "projection",
]


def __getattr__(name: str) -> Any:
    if name == "ProjectedResponse":
        from .fastapi import ProjectedResponse  # noqa: PLC0415

        return ProjectedResponse
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
