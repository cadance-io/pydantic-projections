from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel

from pydantic_projections import (
    cache_clear,
    project_json,
    project_json_bytes,
    projection,
)


class _Source(BaseModel):
    id: int
    name: str


class _Summary(Protocol):
    id: int
    name: str


class _Isolated(Protocol):
    x: int


def describe_project_json():
    def when_called_on_a_valid_instance():
        def it_returns_the_projected_JSON():
            source = _Source(id=1, name="Alice")

            raw = project_json(source, _Summary)

            assert json.loads(raw) == {"id": 1, "name": "Alice"}

    def when_forwarded_dump_kwargs():
        def it_passes_them_to_model_dump_json():
            source = _Source(id=1, name="Alice")

            raw = project_json(source, _Summary, indent=2)

            assert "\n" in raw


def describe_project_json_bytes():
    def when_called_on_a_valid_instance():
        def it_returns_bytes_matching_project_json():
            source = _Source(id=1, name="Alice")

            raw = project_json_bytes(source, _Summary)

            assert isinstance(raw, bytes)
            assert raw == project_json(source, _Summary).encode()


def describe_cache_clear():
    def when_called_after_building_a_projection():
        def it_invalidates_the_cache():
            cls_a = projection(_Isolated)
            cache_clear()
            cls_b = projection(_Isolated)

            assert cls_a is not cls_b
