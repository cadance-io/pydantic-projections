from __future__ import annotations

import pytest
from models import Account

from pydantic_projections import pick, project, projection


def describe_pick():
    def when_picking_fields():
        def it_takes_the_types_from_the_source():
            fields = projection(pick(Account, "id", "email")).model_fields

            assert fields["id"].annotation is int
            assert fields["email"].annotation is str

        def it_makes_them_required():
            fields = projection(pick(Account, "id", "nickname")).model_fields

            assert fields["nickname"].is_required()

        def it_omits_everything_not_picked():
            fields = projection(pick(Account, "id", "email")).model_fields

            assert "password_hash" not in fields
            assert "nickname" not in fields

        def it_names_the_projection_after_the_source():
            assert projection(pick(Account, "id")).__name__ == "AccountViewProjection"

        def with_an_explicit_name():
            def it_uses_it_for_the_projection_class():
                picked = pick(Account, "id", name="AccountTeaser")

                assert projection(picked).__name__ == "AccountTeaserProjection"

    def when_called_twice():
        def with_the_same_arguments():
            def it_returns_the_same_protocol():
                assert pick(Account, "id", "email") is pick(Account, "id", "email")

        def with_different_arguments():
            def it_returns_distinct_protocols():
                assert pick(Account, "id") is not pick(Account, "email")

    def when_a_source_field_carries_metadata():
        def it_carries_the_constraint():
            schema = projection(pick(Account, "email")).model_json_schema()

            assert schema["properties"]["email"]["minLength"] == 3

        def it_carries_the_description():
            schema = projection(pick(Account, "email")).model_json_schema()

            assert schema["properties"]["email"]["description"] == "login address"

        def without_metadata():
            def it_carries_only_the_annotation():
                picked = pick(Account, "email", metadata=False)
                schema = projection(picked).model_json_schema()

                assert "minLength" not in schema["properties"]["email"]
                assert "description" not in schema["properties"]["email"]

    def when_a_source_field_has_an_alias():
        def it_drops_the_alias():
            fields = projection(pick(Account, "legacy_id")).model_fields

            assert fields["legacy_id"].alias is None

        def it_still_projects_from_an_instance(account):
            projected = project(account, pick(Account, "legacy_id"))

            assert projected.legacy_id == 7

        def with_aliases_enabled():
            def it_keeps_the_alias():
                picked = pick(Account, "legacy_id", aliases=True)
                fields = projection(picked).model_fields

                assert fields["legacy_id"].alias == "legacyID"

    def when_a_source_field_has_a_default():
        def it_is_still_required():
            schema = projection(pick(Account, "nickname")).model_json_schema()

            assert schema["required"] == ["nickname"]

    def when_picking_a_computed_field():
        def it_uses_the_return_type(account):
            projected = project(account, pick(Account, "id", "label"))

            assert projected.label == "Account 1"

    def when_the_picked_protocol_is_projected():
        def it_round_trips_an_instance(account):
            projected = project(account, pick(Account, "id", "email"))

            assert projected.id == 1
            assert projected.email == "alice@example.com"
            assert not hasattr(projected, "password_hash")

    def when_a_name_is_unknown():
        def it_raises_at_call_time():
            with pytest.raises(ValueError, match="no_such_field"):
                pick(Account, "id", "no_such_field")

    def when_no_names_are_given():
        def it_raises_a_value_error():
            with pytest.raises(ValueError, match="at least one field name"):
                pick(Account)

    def when_the_source_is_not_a_model():
        def it_raises_a_type_error():
            with pytest.raises(TypeError, match="BaseModel"):
                pick(dict, "id")  # type: ignore[type-var]
