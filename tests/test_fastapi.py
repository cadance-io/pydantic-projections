from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import (
    Address,
    User,
    UserSummary,
    UserWithAddress,
    UserWithAddressSummary,
)

from pydantic_projections import ProjectedResponse, ProjectionError


def describe_ProjectedResponse():
    def when_endpoint_returns_a_flat_projection():
        def it_emits_only_protocol_fields_as_json():
            app = FastAPI()

            @app.get("/u")
            def get_user() -> object:
                return ProjectedResponse(
                    User(id=1, name="Alice", email="a@b.c", password_hash="secret"),
                    UserSummary,
                )

            client = TestClient(app)
            r = client.get("/u")

            assert r.status_code == 200
            assert r.headers["content-type"] == "application/json"
            assert r.json() == {"id": 1, "name": "Alice"}

    def when_endpoint_returns_a_nested_projection():
        def it_prunes_fields_at_every_level():
            addr = Address(street="1 Main", zip_code="00000", country="FR")
            source = UserWithAddress(id=1, name="Alice", address=addr)
            app = FastAPI()

            @app.get("/u")
            def get_user() -> object:
                return ProjectedResponse(source, UserWithAddressSummary)

            client = TestClient(app)
            r = client.get("/u")

            assert r.status_code == 200
            body = r.json()
            assert body == {
                "id": 1,
                "name": "Alice",
                "address": {"street": "1 Main", "zip_code": "00000"},
            }

    def when_given_a_status_code_and_headers():
        def it_forwards_them_to_the_response():
            user = User(id=1, name="Alice", email="a@b.c", password_hash="s")
            app = FastAPI()

            @app.get("/u")
            def get_user() -> object:
                return ProjectedResponse(
                    user,
                    UserSummary,
                    status_code=201,
                    headers={"x-custom": "yes"},
                )

            client = TestClient(app)
            r = client.get("/u")

            assert r.status_code == 201
            assert r.headers["x-custom"] == "yes"

    def when_source_does_not_satisfy_the_protocol():
        def it_raises_ProjectionError_at_render_time():
            class Bare:
                id = 1  # missing 'name'

            with pytest.raises(ProjectionError) as info:
                ProjectedResponse(Bare(), UserSummary)

            assert info.value.protocol is UserSummary
            assert info.value.source_type is Bare


def describe_lazy_import():
    def when_imported_from_package_root():
        def it_resolves_via_module_getattr():
            import pydantic_projections

            assert pydantic_projections.ProjectedResponse is ProjectedResponse

    def when_accessing_an_unknown_attribute():
        def it_raises_AttributeError():
            import pydantic_projections

            with pytest.raises(AttributeError):
                pydantic_projections.not_a_real_symbol  # noqa: B018


def describe_rendered_bytes():
    def when_a_projection_has_nested_fields():
        def it_matches_project_json_bytes_for_equivalent_source():
            from pydantic_projections import project_json_bytes

            addr = Address(street="1 Main", zip_code="00000", country="FR")
            source = UserWithAddress(id=1, name="Alice", address=addr)
            resp = ProjectedResponse(source, UserWithAddressSummary)

            assert json.loads(resp.body) == json.loads(
                project_json_bytes(source, UserWithAddressSummary)
            )
