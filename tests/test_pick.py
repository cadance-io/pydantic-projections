from __future__ import annotations

import json
from typing import Annotated, Protocol

import pytest
from models import Account, Address, UserWithAddress
from pydantic import BaseModel, ConfigDict, Field, computed_field
from pydantic.fields import FieldInfo

from pydantic_projections import cache_clear, pick, project, project_json, projection
from pydantic_projections._pick import _CARRIED


class _City(BaseModel):
    name: Annotated[str, Field(min_length=2, description="what locals call it")]
    country: str


class _Street(BaseModel):
    label: str
    city: _City


class _Directory(BaseModel):
    by_city: dict[_City, str]


class _Building(BaseModel):
    id: int
    street: _Street
    either: _Street | _City


def _building() -> _Building:
    city = _City(name="Paris", country="FR")
    return _Building(id=1, street=_Street(label="Main", city=city), either=city)


def _city_name_schema(picked: type) -> dict:
    """Follow the $refs down to the nested city's `name`, as a consumer would."""
    schema = projection(picked).model_json_schema()
    definitions = schema["$defs"]

    def descend(node: dict, field: str) -> dict:
        return definitions[node["properties"][field]["$ref"].rsplit("/", 1)[-1]]

    return descend(descend(schema, "street"), "city")["properties"]["name"]


def _owner() -> UserWithAddress:
    return UserWithAddress(
        id=1,
        name="Alice",
        address=Address(street="1 Main St", zip_code="75001", country="FR"),
        past_addresses=[Address(street="2 Old Rd", zip_code="75002", country="FR")],
        nicknames={"home": Address(street="3 Way", zip_code="75003", country="FR")},
        shipping=Address(street="4 Quay", zip_code="75004", country="FR"),
    )


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

        def with_a_repeated_name():
            def it_collapses_to_one_protocol():
                assert pick(Account, "id", "id") is pick(Account, "id")

    def when_the_cache_is_cleared():
        def it_rebuilds_the_protocol():
            before = pick(Account, "id", "email")
            cache_clear()

            assert pick(Account, "id", "email") is not before

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

                assert schema["properties"]["email"] == {
                    "title": "Email",
                    "type": "string",
                }

        def it_only_names_attributes_pydantic_still_has():
            assert set(_CARRIED) <= set(FieldInfo.__slots__)

    def when_a_source_field_has_an_alias():
        def it_projects_from_the_attribute_name(account):
            projected = project(account, pick(Account, "legacy_id"))

            assert projected.legacy_id == 7

        def it_keeps_the_alias_off_the_wire(account):
            raw = project_json(account, pick(Account, "legacy_id"), by_alias=True)

            assert json.loads(raw) == {"legacy_id": 7}

        def with_aliases_enabled():
            def it_emits_the_alias_on_the_wire(account):
                picked = pick(Account, "legacy_id", aliases=True)

                raw = project_json(account, picked, by_alias=True)

                assert json.loads(raw) == {"legacyID": 7}

            def it_still_projects_from_the_attribute_name(account):
                projected = project(account, pick(Account, "legacy_id", aliases=True))

                assert projected.legacy_id == 7

    def when_a_source_field_has_a_default():
        def it_is_still_required():
            schema = projection(pick(Account, "nickname")).model_json_schema()

            assert schema["required"] == ["nickname"]

    def when_picking_a_computed_field():
        def it_uses_the_return_type(account):
            projected = project(account, pick(Account, "id", "label"))

            assert projected.label == "Account 1"

    def when_a_picked_field_is_another_model():
        def it_publishes_that_model_whole():
            source = UserWithAddress(
                id=1,
                name="Alice",
                address=Address(street="1 Main St", zip_code="75001", country="FR"),
            )

            projected = project(source, pick(UserWithAddress, "id", "address"))

            assert projected.address.country == "FR"

    def when_a_name_is_a_dotted_path():
        def it_selects_only_the_named_nested_fields():
            projected = project(_owner(), pick(UserWithAddress, "id", "address.street"))

            assert projected.address.street == "1 Main St"
            assert not hasattr(projected.address, "country")

        def it_names_the_nested_protocol_after_its_parent():
            picked = pick(UserWithAddress, "id", "address.street")

            defs = projection(picked).model_json_schema()["$defs"]

            assert list(defs) == ["UserWithAddressViewAddressProjection"]

        def it_keeps_the_source_order_of_the_head_fields():
            picked = pick(UserWithAddress, "address.street", "id")

            assert list(projection(picked).model_fields) == ["address", "id"]

        def for_a_list_of_models():
            def it_selects_through_the_container():
                picked = pick(UserWithAddress, "past_addresses.street")

                projected = project(_owner(), picked)

                assert projected.past_addresses[0].street == "2 Old Rd"
                assert not hasattr(projected.past_addresses[0], "country")

        def for_an_optional_model():
            def it_selects_through_the_union():
                picked = pick(UserWithAddress, "shipping.street")

                projected = project(_owner(), picked)

                assert projected.shipping.street == "4 Quay"

        def for_a_dict_of_models():
            def it_selects_through_the_values():
                picked = pick(UserWithAddress, "nicknames.zip_code")

                projected = project(_owner(), picked)

                assert projected.nicknames["home"].zip_code == "75003"

        def with_deeper_nesting():
            def it_recurses():
                projected = project(_building(), pick(_Building, "street.city.name"))

                assert projected.street.city.name == "Paris"
                assert not hasattr(projected.street.city, "country")
                assert not hasattr(projected.street, "label")

            def it_carries_the_nested_metadata():
                picked = pick(_Building, "street.city.name")

                assert _city_name_schema(picked)["minLength"] == 2

            def without_metadata():
                def it_drops_it_at_every_level():
                    picked = pick(_Building, "street.city.name", metadata=False)

                    assert "minLength" not in _city_name_schema(picked)

        def when_the_head_is_not_a_model():
            def it_raises_at_call_time():
                with pytest.raises(ValueError, match="str contains no model"):
                    pick(Account, "email.length")

        def when_the_head_is_ambiguous():
            def it_raises_at_call_time():
                with pytest.raises(ValueError, match="ambiguous between"):
                    pick(_Building, "either.name")

        def when_the_head_is_a_computed_field():
            def it_raises_at_call_time():
                with pytest.raises(ValueError, match="computed field"):
                    pick(Account, "label.x")

        def when_the_model_is_a_mapping_key():
            def it_raises_at_call_time():
                with pytest.raises(ValueError, match="mapping key"):
                    pick(_Directory, "by_city.name")

        def when_a_nested_name_is_unknown():
            def it_names_the_path_in_the_error():
                with pytest.raises(
                    ValueError, match=r"through UserWithAddress\.address:.*'stret'"
                ):
                    pick(UserWithAddress, "address.stret")

        def when_the_whole_field_is_also_picked():
            def it_raises_at_call_time():
                with pytest.raises(ValueError, match="cannot pick both 'address'"):
                    pick(UserWithAddress, "address", "address.street")

        def when_the_path_is_malformed():
            def it_raises_at_call_time():
                with pytest.raises(ValueError, match="malformed"):
                    pick(UserWithAddress, "address.")

    def when_the_picked_protocol_is_subclassed():
        def it_narrows_the_annotation():
            class _Nullable(BaseModel):
                id: int | None = None
                total: float

            class _View(pick(_Nullable, "id", "total"), Protocol):  # type: ignore[misc]
                id: int

            schema = projection(_View).model_json_schema()

            assert schema["properties"]["id"] == {"title": "Id", "type": "integer"}
            assert schema["required"] == ["id", "total"]

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

    def when_a_computed_field_has_no_resolved_type():
        def it_raises_a_type_error():
            class _Deferred(BaseModel):
                model_config = ConfigDict(defer_build=True)

                total: float

                @computed_field
                @property
                def doubled(self) -> float:
                    return self.total * 2

            with pytest.raises(TypeError, match="model_rebuild"):
                pick(_Deferred, "doubled")
