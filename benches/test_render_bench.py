"""Compare FastAPI-relevant render paths on a constructed ``User``.

Paths:
  - FastAPI-style: ``model_validate`` + ``jsonable_encoder`` + ``json.dumps``.
  - Skip encoder: ``model_validate`` + ``model_dump_json().encode()``.
  - Direct: ``validator.validate_python`` + ``serializer.to_json`` — what
    ``ProjectedResponse.render`` does.

Run with: ``uv run pytest benches/ --benchmark-only``.
"""

from __future__ import annotations

import json

import pytest
from models import User, UserSummary

from pydantic_projections import projection

pytest.importorskip("fastapi")

from fastapi.encoders import jsonable_encoder


def _user() -> User:
    return User(id=1, name="Alice", email="a@b.c", password_hash="secret")


def describe_render_paths():
    def when_emitting_a_flat_projection_as_JSON_bytes():
        def it_runs_the_fastapi_style_path(benchmark):
            u = _user()
            cls = projection(UserSummary)

            def run():
                inst = cls.model_validate(u)
                return json.dumps(jsonable_encoder(inst)).encode()

            benchmark(run)

        def it_runs_the_model_dump_json_path(benchmark):
            u = _user()
            cls = projection(UserSummary)

            def run():
                inst = cls.model_validate(u)
                return inst.model_dump_json().encode()

            benchmark(run)

        def it_runs_the_direct_validator_serializer_path(benchmark):
            u = _user()
            cls = projection(UserSummary)
            validator = cls.__pydantic_validator__
            serializer = cls.__pydantic_serializer__

            def run():
                inst = validator.validate_python(u, from_attributes=True)
                return serializer.to_json(inst)

            benchmark(run)
