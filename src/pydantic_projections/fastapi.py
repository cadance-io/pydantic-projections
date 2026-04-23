"""FastAPI integration: a Response class that serializes a source through a Protocol.

:class:`ProjectedResponse` bypasses FastAPI's ``serialize_response`` +
``jsonable_encoder`` + ``json.dumps`` chain by calling the projection class's
Rust-backed ``__pydantic_validator__`` and ``__pydantic_serializer__`` directly,
producing JSON bytes in a single pass.

Import requires ``fastapi``; install with ``pip install pydantic-projections[fastapi]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from ._core import ProjectionError, projection

try:
    from fastapi.responses import Response
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pydantic_projections.fastapi requires fastapi; install with "
        "`pip install pydantic-projections[fastapi]` or `pip install fastapi`."
    ) from exc

if TYPE_CHECKING:
    from starlette.background import BackgroundTask


class ProjectedResponse(Response):
    """FastAPI ``Response`` that serializes ``instance`` through ``protocol``.

    Usage::

        @app.get("/users/{id}")
        def get_user(id: int):
            return ProjectedResponse(db.get_user(id), UserSummary)

    Do **not** set ``response_model`` on the endpoint when returning this
    response — FastAPI would run validation + serialization again, defeating
    the purpose. Declaring the return type as ``Response`` or leaving it
    unannotated is fine.

    Raises :class:`ProjectionError` at render time if the source does not
    satisfy the Protocol.
    """

    media_type = "application/json"

    def __init__(
        self,
        instance: Any,
        protocol: type,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        background: BackgroundTask | None = None,
    ) -> None:
        # Must be set before super().__init__, which calls self.render().
        self._instance = instance
        self._protocol = protocol
        super().__init__(
            content=None,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
            background=background,
        )

    def render(self, content: Any) -> bytes:
        model_cls = projection(self._protocol)
        try:
            projected = model_cls.__pydantic_validator__.validate_python(
                self._instance, from_attributes=True
            )
        except ValidationError as exc:
            raise ProjectionError(
                f"{type(self._instance).__name__} does not satisfy "
                f"{getattr(self._protocol, '__name__', self._protocol)!r}: {exc}",
                protocol=self._protocol,
                source_type=type(self._instance),
                validation_error=exc,
            ) from exc
        return model_cls.__pydantic_serializer__.to_json(projected)
