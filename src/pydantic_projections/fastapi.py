"""FastAPI integration: a Response class that serializes a source through a Protocol.

:class:`ProjectedResponse` bypasses FastAPI's ``serialize_response`` +
``jsonable_encoder`` + ``json.dumps`` chain by calling the projection class's
Rust-backed ``__pydantic_validator__`` and ``__pydantic_serializer__`` directly,
producing JSON bytes via two Rust-backed calls (validate, then serialize) with
no ``jsonable_encoder`` / ``json.dumps`` step in between.

Import requires ``fastapi``; install with ``pip install pydantic-projections[fastapi]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._core import P, project_json_bytes, projection

try:
    from fastapi.responses import Response
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pydantic_projections.fastapi requires fastapi; install with "
        "`pip install pydantic-projections[fastapi]` or `pip install fastapi`."
    ) from exc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.background import BackgroundTask


# Subclasses Response, not JSONResponse: JSONResponse.render() calls
# json.dumps(), which is exactly the overhead we're avoiding.
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

    Extra ``**dump_kwargs`` are forwarded to the projection's
    ``__pydantic_serializer__.to_json`` (e.g. ``by_alias=True``,
    ``exclude_none=True``, ``indent=2``).

    Raises :class:`ProjectionError` at construction time (Starlette's
    ``Response.__init__`` invokes ``render``) if the source does not satisfy
    the Protocol.
    """

    media_type = "application/json"

    def __init__(
        self,
        instance: Any,
        protocol: type[P],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        background: BackgroundTask | None = None,
        **dump_kwargs: Any,
    ) -> None:
        # All three must be set before super().__init__, which calls render().
        self._instance = instance
        self._protocol = protocol
        self._dump_kwargs = dump_kwargs
        super().__init__(
            content=None,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
            background=background,
        )

    def render(self, content: Any) -> bytes:
        return project_json_bytes(self._instance, self._protocol, **self._dump_kwargs)


def openapi_response(protocol: type[P]) -> dict[str, Any]:
    """FastAPI ``responses=`` entry for a projection.

    Use alongside :class:`ProjectedResponse` so the OpenAPI spec advertises
    the projection's schema::

        @app.get("/u", responses={200: openapi_response(UserSummary)})
        def get_user() -> Response:
            return ProjectedResponse(db.get_user(id), UserSummary)

    Composes for multi-status routes::

        responses={
            200: openapi_response(UserSummary),
            404: {"model": HTTPNotFound},
        }
    """
    return {"model": projection(protocol)}
