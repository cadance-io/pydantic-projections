from __future__ import annotations

import json

from models import UserDisplay, UserMaybeName, UserSummary

from pydantic_projections import project


def describe_project():
    def when_serialising_a_user_to_a_protocol():
        def it_keeps_only_the_protocols_fields(user):
            result = project(user, UserSummary).model_dump()
            assert result == {"id": 1, "name": "Alice"}

        def it_produces_matching_json(user):
            raw = project(user, UserSummary).model_dump_json()
            assert json.loads(raw) == {"id": 1, "name": "Alice"}

    def when_the_protocol_widens_a_field_to_optional():
        def it_still_carries_the_source_value(user):
            result = project(user, UserMaybeName)
            assert result.name == "Alice"

    def when_the_protocol_declares_a_computed_property():
        def it_reads_the_value_from_the_source(user):
            result = project(user, UserDisplay)
            assert result.display_name == "User: Alice"
