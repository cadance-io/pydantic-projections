"""Micro-benchmarks for project() / project_json() / project_json_bytes.

Run with: ``uv run pytest benches/ --benchmark-only``.

Reported numbers are environment-dependent — look at the *relative* column when
comparing paths. The benchmarks exist to detect regressions in the direct
validator / serializer fast-path, not to produce numbers for marketing.
"""

from __future__ import annotations

from models import (
    Address,
    User,
    UserSummary,
    UserWithAddress,
    UserWithAddressSummary,
)

from pydantic_projections import (
    project,
    project_json,
    project_json_bytes,
    projection,
)


def _user() -> User:
    return User(id=1, name="Alice", email="a@b.c", password_hash="secret")


def _user_nested() -> UserWithAddress:
    addr = Address(street="1 Main", zip_code="00000", country="FR")
    return UserWithAddress(
        id=1,
        name="Alice",
        address=addr,
        past_addresses=[addr, addr],
        nicknames={"home": addr},
        shipping=addr,
    )


def describe_flat_projection_cost():
    def when_projecting_a_user_to_a_summary_protocol():
        def it_runs_through_project(benchmark):
            u = _user()
            benchmark(project, u, UserSummary)

        def it_runs_through_model_validate_for_reference(benchmark):
            u = _user()
            cls = projection(UserSummary)
            benchmark(cls.model_validate, u)


def describe_nested_projection_cost():
    def when_the_protocol_has_nested_and_container_fields():
        def it_runs_through_project(benchmark):
            u = _user_nested()
            benchmark(project, u, UserWithAddressSummary)


def describe_json_emission_cost():
    def when_emitting_JSON_via_project_json():
        def it_returns_a_str(benchmark):
            u = _user()
            benchmark(project_json, u, UserSummary)

    def when_emitting_JSON_via_project_json_bytes():
        def it_returns_bytes_directly(benchmark):
            u = _user()
            benchmark(project_json_bytes, u, UserSummary)

    def when_emitting_nested_JSON():
        def it_runs_project_json_bytes(benchmark):
            u = _user_nested()
            benchmark(project_json_bytes, u, UserWithAddressSummary)
