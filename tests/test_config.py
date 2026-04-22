from __future__ import annotations

from typing import Protocol

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from pydantic_projections import projection


class _Source(BaseModel):
    user_id: int
    full_name: str


class _Summary(Protocol):
    user_id: int
    full_name: str


class _Simple(Protocol):
    x: int


def describe_projection_config():
    def when_given_an_alias_generator():
        def it_applies_the_generator_on_serialisation():
            cls = projection(
                _Summary,
                config=ConfigDict(alias_generator=to_camel, populate_by_name=True),
            )
            result = cls.model_validate(_Source(user_id=1, full_name="Alice"))

            dumped = result.model_dump(by_alias=True)
            assert dumped == {"userId": 1, "fullName": "Alice"}

    def when_frozen_is_true():
        def it_rejects_mutation():
            cls = projection(_Simple, frozen=True)

            instance = cls.model_validate({"x": 1})
            with pytest.raises(ValidationError):
                instance.x = 2

        def it_caches_separately_from_the_unfrozen_variant():
            assert projection(_Simple, frozen=True) is not projection(_Simple)

    def when_the_same_config_is_passed_twice():
        def it_returns_the_same_cached_class():
            cfg = ConfigDict(alias_generator=to_camel, populate_by_name=True)

            first = projection(_Summary, config=cfg)
            second = projection(_Summary, config=cfg)

            assert first is second

    def when_an_unhashable_config_value_is_passed():
        def it_raises_a_type_error():
            bad_config = ConfigDict()
            bad_config["json_schema_extra"] = ["not", "hashable"]  # type: ignore[typeddict-item]

            with pytest.raises(TypeError, match="hashable"):
                projection(_Simple, config=bad_config)
