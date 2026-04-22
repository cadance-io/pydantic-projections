from __future__ import annotations

from models import (
    Address,
    AddressSummary,
    UserWithAddress,
    UserWithAddressDict,
    UserWithAddressList,
    UserWithAddressSummary,
    UserWithOptionalAddress,
)

from pydantic_projections import project, projection


def _make_user(**overrides) -> UserWithAddress:
    defaults = {
        "id": 1,
        "name": "Alice",
        "address": Address(street="1 Main St", zip_code="90210", country="US"),
    }
    defaults.update(overrides)
    return UserWithAddress(**defaults)


def describe_nested_projection():
    def when_a_field_is_itself_a_protocol():
        def it_recursively_projects_the_inner_model():
            user = _make_user()
            result = project(user, UserWithAddressSummary)

            dumped = result.model_dump()
            assert dumped == {
                "id": 1,
                "name": "Alice",
                "address": {"street": "1 Main St", "zip_code": "90210"},
            }

        def when_deserialising_json():
            def it_ignores_extras_on_the_inner_model():
                raw = (
                    '{"id":1,"name":"Alice",'
                    '"address":{"street":"1 Main St","zip_code":"90210",'
                    '"country":"US","extra":"ignored"}}'
                )
                result = projection(UserWithAddressSummary).model_validate_json(raw)

                assert "country" not in type(result.address).model_fields

    def when_the_field_is_a_list_of_protocols():
        def it_projects_each_element():
            user = _make_user(
                past_addresses=[
                    Address(street="a", zip_code="1", country="US"),
                    Address(street="b", zip_code="2", country="FR"),
                ]
            )
            result = project(user, UserWithAddressList)

            dumped = result.model_dump()
            assert dumped == {
                "id": 1,
                "past_addresses": [
                    {"street": "a", "zip_code": "1"},
                    {"street": "b", "zip_code": "2"},
                ],
            }

    def when_the_field_is_a_dict_of_protocols():
        def it_projects_each_value():
            user = _make_user(
                nicknames={
                    "home": Address(street="x", zip_code="1", country="US"),
                }
            )
            result = project(user, UserWithAddressDict)

            dumped = result.model_dump()
            assert dumped["nicknames"]["home"] == {"street": "x", "zip_code": "1"}

    def when_the_field_is_an_optional_protocol():
        def with_a_value_present():
            def it_projects_the_inner_model():
                user = _make_user(
                    shipping=Address(street="y", zip_code="2", country="US")
                )
                result = project(user, UserWithOptionalAddress)

                assert result.shipping is not None
                assert result.shipping.model_dump() == {
                    "street": "y",
                    "zip_code": "2",
                }

        def without_a_value():
            def it_stays_none():
                user = _make_user(shipping=None)
                result = project(user, UserWithOptionalAddress)

                assert result.shipping is None


def describe_cache_for_nested():
    def when_building_a_nested_projection_twice():
        def it_reuses_the_inner_projection_class():
            outer_a = projection(UserWithAddressSummary)
            outer_b = projection(UserWithAddressSummary)

            assert outer_a is outer_b
            assert projection(AddressSummary) is projection(AddressSummary)
