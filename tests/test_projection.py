from __future__ import annotations

import pytest
from models import UserSummary

from pydantic_projections import project, projection


def describe_projection():
    def when_called_twice():
        def with_the_same_protocol():
            def it_returns_the_same_cached_class():
                assert projection(UserSummary) is projection(UserSummary)

    def when_validating_json():
        def with_extra_fields():
            def it_ignores_them():
                raw = '{"id":1,"name":"Alice","email":"x@y.z","extra":"ignored"}'
                result = projection(UserSummary).model_validate_json(raw)

                assert result.id == 1
                assert result.name == "Alice"
                assert "email" not in type(result).model_fields
                assert not hasattr(result, "email")

    def when_round_tripping_a_projection_through_json():
        def it_preserves_the_declared_fields(user):
            raw = project(user, UserSummary).model_dump_json()
            roundtripped = projection(UserSummary).model_validate_json(raw)

            assert roundtripped.id == 1
            assert roundtripped.name == "Alice"

    def when_the_argument_is_not_a_class():
        def it_raises_a_type_error():
            with pytest.raises(TypeError):
                projection("not a class")  # type: ignore[arg-type]
