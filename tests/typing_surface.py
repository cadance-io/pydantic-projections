"""Static-typing surface: every documented call shape must satisfy ``mypy --strict``.

Not collected by pytest (which collects ``test_*.py``); CI type-checks this file
alongside ``src/``. Without it mypy never sees a call site, which is how
``project(x, SomeProtocol)`` shipped four releases with a ``type-abstract`` error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from pydantic_projections import (
    ProjectedResponse,
    openapi_response,
    pick,
    project,
    project_json,
    project_json_bytes,
    projection,
)

if TYPE_CHECKING:
    from fastapi import Response


class User(BaseModel):
    id: int
    name: str


class UserSummary(Protocol):
    id: int
    name: str


class Envelope(Protocol):
    id: int
    owner: UserSummary


UserView = pick(User, "id", "name")


def projected_attribute(user: User) -> str:
    return project(user, UserSummary).name


def projected_nested_attribute(envelope: object) -> str:
    return project(envelope, Envelope).owner.name


def projected_json(user: User) -> str:
    return project_json(user, UserSummary, indent=2)


def projected_json_bytes(user: User) -> bytes:
    return project_json_bytes(user, UserSummary, by_alias=True)


def projection_class() -> type[BaseModel]:
    return projection(UserSummary)


def picked_projection(user: User) -> str:
    return project_json(user, UserView)


def response(user: User) -> Response:
    return ProjectedResponse(user, UserSummary, status_code=201)


def openapi_entry() -> dict[str, object]:
    return openapi_response(UserSummary)
