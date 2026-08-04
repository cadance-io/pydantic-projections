"""Elegant projection of Pydantic ``BaseModel``s through Python ``Protocol``s.

Public API:
    - :func:`project` — one-shot: project an instance through a Protocol.
    - :func:`projection` — get (or build) the cached ``BaseModel`` class for a Protocol.
    - :func:`pick` — derive a Protocol from an existing model, without restating
      its field list.
    - :func:`project_json` — shortcut for ``project(...).model_dump_json(...)``.
    - :func:`project_json_bytes` — bytes-returning equivalent; skips the ``str`` hop.
    - :func:`cache_clear` — clear the projection class and ``pick`` Protocol caches.
    - :class:`ProjectionError` — raised when an instance does not satisfy the Protocol.
    - :class:`ProjectedResponse` — FastAPI response class that serializes a source
      instance through a Protocol straight to JSON bytes. Available only if
      ``fastapi`` is installed; imported lazily via attribute access.
    - :func:`openapi_response` — FastAPI ``responses=`` entry for a projection,
      so the OpenAPI spec advertises the projection's schema. Lazy fastapi import.
"""

from typing import TYPE_CHECKING, Any

from ._core import (
    ProjectionError,
    _build,
    project,
    project_json,
    project_json_bytes,
    projection,
)
from ._pick import _protocol_for, pick

if TYPE_CHECKING:
    # Re-exported lazily via __getattr__ to avoid importing fastapi when unused.
    from .fastapi import ProjectedResponse, openapi_response  # noqa: F401

__all__ = [
    "ProjectionError",
    "cache_clear",
    "pick",
    "project",
    "project_json",
    "project_json_bytes",
    "projection",
]


def cache_clear() -> None:
    """Clear the projection class and ``pick`` Protocol caches.

    Useful in test fixtures that redefine Protocols or in hot-reload workflows.
    """
    _build.cache_clear()
    _protocol_for.cache_clear()


_LAZY_FASTAPI_EXPORTS = frozenset({"ProjectedResponse", "openapi_response"})


def __getattr__(name: str) -> Any:
    if name in _LAZY_FASTAPI_EXPORTS:
        from . import fastapi as _fastapi  # noqa: PLC0415

        return getattr(_fastapi, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
