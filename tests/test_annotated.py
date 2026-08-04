from __future__ import annotations

from typing import Annotated, Protocol

import pytest
from models import Address, AddressSummary
from pydantic import BaseModel, Field, ValidationError

from pydantic_projections import project, projection


class _WithMeta(Protocol):
    name: Annotated[str, Field(min_length=3, description="what to call them")]
    age: int


class _WithDefault(Protocol):
    name: Annotated[str, Field(default="anonymous")]


class _WithExamples(Protocol):
    name: Annotated[str, Field(examples=["Alice"])]


class _WithAnnotatedAddress(Protocol):
    id: int
    address: Annotated[AddressSummary, Field(description="where they live")]


class _WithAnnotatedProperty(Protocol):
    @property
    def label(self) -> Annotated[str, Field(min_length=3)]: ...


class _Labelled(BaseModel):
    label: str


class _Owner(BaseModel):
    id: int
    address: Address


def describe_projection():
    def when_a_member_carries_field_metadata():
        def it_exposes_the_constraint_in_the_schema():
            schema = projection(_WithMeta).model_json_schema()

            assert schema["properties"]["name"]["minLength"] == 3

        def it_keeps_the_description():
            schema = projection(_WithMeta).model_json_schema()

            assert schema["properties"]["name"]["description"] == "what to call them"

        def it_enforces_the_constraint():
            with pytest.raises(ValidationError):
                projection(_WithMeta)(name="ab", age=1)

        def it_leaves_unannotated_members_alone():
            schema = projection(_WithMeta).model_json_schema()

            assert schema["properties"]["age"] == {"title": "Age", "type": "integer"}

        def with_examples():
            def it_keeps_them():
                schema = projection(_WithExamples).model_json_schema()

                assert schema["properties"]["name"]["examples"] == ["Alice"]

        def with_a_default():
            def it_stays_required():
                schema = projection(_WithDefault).model_json_schema()

                assert schema["required"] == ["name"]

        def with_a_protocol_inside_the_annotation():
            def it_still_substitutes_the_projection():
                source = _Owner(
                    id=1,
                    address=Address(street="1 Main St", zip_code="75001", country="FR"),
                )

                projected = project(source, _WithAnnotatedAddress)

                assert projected.address.street == "1 Main St"
                assert not hasattr(projected.address, "country")

    def when_a_property_member_is_annotated():
        def it_keeps_the_metadata():
            schema = projection(_WithAnnotatedProperty).model_json_schema()

            assert schema["properties"]["label"]["minLength"] == 3

        def it_still_projects_the_value():
            projected = project(_Labelled(label="Alice"), _WithAnnotatedProperty)

            assert projected.label == "Alice"
