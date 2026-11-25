from __future__ import annotations

import operator
from typing import Protocol

import pytest
from pydantic import BaseModel, ValidationError

from pydantic_projections import ProjectionError, project, projection


class _Summary(Protocol):
    id: int
    name: str


class _Partial:
    def __init__(self, id: int) -> None:
        self.id = id


def describe_project_errors():
    def when_the_source_is_missing_a_required_field():
        def it_raises_a_projection_error_including_the_protocol_name():
            source = _Partial(id=1)

            with pytest.raises(ProjectionError) as exc_info:
                project(source, _Summary)

            err = exc_info.value
            assert "_Summary" in str(err)
            assert err.protocol is _Summary
            assert err.source_type is _Partial
            assert isinstance(err.validation_error, ValidationError)

    def when_the_source_value_has_an_incompatible_type():
        def it_also_raises_a_projection_error():
            class BadSource:
                id = "not-an-int"
                name = "Alice"

            with pytest.raises(ProjectionError) as exc_info:
                project(BadSource(), _Summary)

            assert isinstance(exc_info.value.validation_error, ValidationError)


def describe_projection_build_errors():
    def when_the_protocol_has_no_annotated_members():
        def it_raises_a_type_error():
            class _Empty(Protocol):
                pass

            with pytest.raises(TypeError, match="nothing to project"):
                projection(_Empty)

    def when_the_protocol_references_an_unresolved_forward_name():
        def it_raises_a_type_error():
            class _Unresolvable(Protocol):
                ref: "DefinitelyNotDefined"  # type: ignore[name-defined]  # noqa: F821, UP037

            with pytest.raises(TypeError, match="_Unresolvable"):
                projection(_Unresolvable)

    def when_a_property_on_the_protocol_references_an_unresolved_forward_name():
        def it_raises_a_type_error_that_names_the_property():
            class _UnresolvableProp(Protocol):
                id: int

                @property
                def owner(self) -> "DefinitelyNotDefined": ...  # type: ignore[name-defined]  # noqa: F821, UP037

            with pytest.raises(TypeError, match=r"_UnresolvableProp.*\.owner"):
                projection(_UnresolvableProp)

        def with_the_property_inherited_from_a_base_protocol():
            def it_names_the_base_that_declares_it():
                class _DeclaresOwner(Protocol):
                    @property
                    def owner(self) -> "DefinitelyNotDefined": ...  # type: ignore[name-defined]  # noqa: F821, UP037

                class _InheritsOwner(_DeclaresOwner, Protocol):
                    id: int

                with pytest.raises(TypeError, match=r"declared on .*_DeclaresOwner"):
                    projection(_InheritsOwner)

    def when_a_property_on_the_protocol_has_no_return_annotation():
        def it_is_silently_skipped():
            class _Src(BaseModel):
                name: str

            class _OnlyUntypedProp(Protocol):
                name: str

                @property
                def untyped(self):  # type: ignore[no-untyped-def]
                    return "x"

            cls = projection(_OnlyUntypedProp)

            assert "untyped" not in cls.model_fields
            assert cls.model_validate(_Src(name="Alice")).name == "Alice"

    def when_a_property_getter_is_not_a_function():
        def it_is_skipped_like_an_unannotated_property():
            class _AttrgetterProp(Protocol):
                id: int
                alias = property(operator.attrgetter("id"))

            assert list(projection(_AttrgetterProp).model_fields) == ["id"]
