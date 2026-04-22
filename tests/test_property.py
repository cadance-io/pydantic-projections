from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, computed_field

from pydantic_projections import project


class _Source(BaseModel):
    name: str

    @computed_field
    @property
    def greeting(self) -> str:
        return f"Hello, {self.name}"


class _HasGreeting(Protocol):
    @property
    def greeting(self) -> str: ...


class _MixedProto(Protocol):
    name: str

    @property
    def greeting(self) -> str: ...


def describe_property_style_protocols():
    def when_the_protocol_declares_a_field_as_a_property():
        def it_reads_the_return_type_from_the_getter():
            result = project(_Source(name="Alice"), _HasGreeting)

            assert result.greeting == "Hello, Alice"

    def when_the_protocol_mixes_annotations_and_properties():
        def it_projects_both_kinds():
            result = project(_Source(name="Alice"), _MixedProto)

            assert result.name == "Alice"
            assert result.greeting == "Hello, Alice"
