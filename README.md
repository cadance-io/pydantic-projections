# pydantic-projections

[![PyPI](https://img.shields.io/pypi/v/pydantic-projections.svg)](https://pypi.org/project/pydantic-projections/)
[![CI](https://github.com/cadance-io/pydantic-projections/actions/workflows/ci.yml/badge.svg)](https://github.com/cadance-io/pydantic-projections/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/pydantic-projections.svg)](https://pypi.org/project/pydantic-projections/)

Elegant projection of Pydantic `BaseModel`s through Python `Protocol`s — serialise and deserialise only the fields a Protocol declares, nothing more.

## Install

```bash
uv add pydantic-projections
# or
pip install pydantic-projections
```

For the optional FastAPI integration (`ProjectedResponse`), install the extra:

```bash
pip install pydantic-projections[fastapi]
```

## Why

You have a fat `BaseModel` for internal use, and you want to expose only a subset of its fields over an API, to a logging system, or to a downstream consumer. Pydantic already lets you do this with `model_dump(include=...)`, but that's stringly-typed and type-unsafe. A `Protocol` describes the shape you want; `pydantic-projections` turns that Protocol into a real BaseModel at runtime, cached per `(protocol, frozen, config)` triple.

## Usage

```python
from typing import Protocol

from pydantic import BaseModel
from pydantic_projections import project, projection


class User(BaseModel):
    id: int
    name: str
    email: str
    password_hash: str


class UserSummary(Protocol):
    id: int
    name: str


user = User(id=1, name="Alice", email="a@b.c", password_hash="secret")

# One-shot: project an instance, get a BaseModel typed as UserSummary
summary = project(user, UserSummary)
summary.model_dump_json()
# -> '{"id":1,"name":"Alice"}'

# Get the reusable class (cached): useful for response_model, schema export, etc.
SummaryModel = projection(UserSummary)
SummaryModel.model_validate_json('{"id":1,"name":"Alice","extra":"ignored"}')
# -> extra fields are ignored
SummaryModel.model_json_schema()
# -> standard pydantic JSON schema
```

### Nested protocols and containers

Protocols can reference other Protocols. The projection is built recursively, so `list[P]`, `dict[str, P]`, `tuple[P, ...]`, `P | None`, `Union[P, ...]`, and plain `P` all work:

```python
class AddressSummary(Protocol):
    street: str
    zip_code: str


class UserWithAddresses(Protocol):
    id: int
    name: str
    address: AddressSummary
    past_addresses: list[AddressSummary]
    shipping: AddressSummary | None
```

### `@property`-style Protocols

Protocols that declare fields as properties are also supported — the property's return type is used:

```python
class UserDisplay(Protocol):
    @property
    def display_name(self) -> str: ...


project(user, UserDisplay).display_name
```

### Computed / derived fields on the source

`@computed_field` / `@property` declarations on the source model are readable through the projection, because validation runs with `from_attributes=True`:

```python
class User(BaseModel):
    id: int
    name: str

    @computed_field
    @property
    def display_name(self) -> str:
        return f"User: {self.name}"


class UserDisplay(Protocol):
    display_name: str


project(user, UserDisplay).display_name  # -> "User: Alice"
```

### Typing at the call site

`project(instance, Proto)` is typed to return `Proto`, so `summary.name` resolves to `str` in mypy/pyright without a cast. At runtime the object is a `BaseModel` subclass that structurally satisfies the Protocol.

### FastAPI integration

Two patterns, in order of speed:

**Drop-in `response_model`.** `projection(Proto)` returns a real BaseModel class, so it plugs into FastAPI's `response_model` unchanged — the endpoint's output is pruned to the Protocol's fields and the OpenAPI schema matches:

```python
from fastapi import FastAPI
from pydantic_projections import projection

app = FastAPI()


@app.get("/users/{id}", response_model=projection(UserSummary))
def get_user(id: int) -> User:
    return db.get_user(id)  # returns the fat User; caller sees only UserSummary's fields
```

This path still goes through FastAPI's full `serialize_response` + `jsonable_encoder` + `json.dumps` chain every request. Fine for most endpoints.

**High-throughput: `ProjectedResponse`.** For hot paths, return a `ProjectedResponse` instead. It bypasses `serialize_response`/`jsonable_encoder` entirely and emits JSON bytes via two Rust-backed calls (validate, then serialize) on the projection class's `__pydantic_validator__` and `__pydantic_serializer__`, with no `jsonable_encoder` / `json.dumps` step in between:

```python
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic_projections import ProjectedResponse

app = FastAPI()


@app.get("/users/{id}")
def get_user(id: int) -> Response:
    return ProjectedResponse(db.get_user(id), UserSummary)
```

Don't set `response_model` when using `ProjectedResponse` — FastAPI would run validation + serialization again and defeat the purpose. `ProjectedResponse(...)` validates at construction time, so a source that doesn't satisfy the Protocol raises `ProjectionError` from the handler (catchable via a FastAPI exception handler). Install with `pip install pydantic-projections[fastapi]`.

Extra serializer kwargs (`by_alias=True`, `exclude_none=True`, `indent=2`, …) are forwarded to the projection's `__pydantic_serializer__.to_json`, so a project using a camelCase `alias_generator` in its `projection()` config can do `ProjectedResponse(user, UserSummary, by_alias=True)`.

**OpenAPI schema.** Because `response_model` is unset, FastAPI cannot derive a 200 response schema for the endpoint — the OpenAPI spec will show an empty schema. Use `openapi_response(Protocol)` to advertise the projection's schema via `responses=`:

```python
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic_projections import ProjectedResponse, openapi_response

app = FastAPI()


@app.get("/users/{id}", responses={200: openapi_response(UserSummary)})
def get_user(id: int) -> Response:
    return ProjectedResponse(db.get_user(id), UserSummary)
```

This advertises the projection's schema in the spec (`$ref: '#/components/schemas/UserSummaryProjection'`) without re-running serialization on the response path. `openapi_response()` returns a `{"model": ...}` entry, so it composes naturally with other status codes: `responses={200: openapi_response(UserSummary), 404: {"model": NotFound}}`.

See `benches/test_render_bench.py` for the comparison; in our measurements `ProjectedResponse` is roughly 2–4× faster than the `response_model=projection(...)` path on raw ser/deser work, depending on FastAPI version and response shape. Note that FastAPI's `TestClient` is a poor way to measure this — its per-call transport setup dominates — use `uvicorn` + an external HTTP benchmark tool (`wrk`, `hey`, `oha`) for end-to-end numbers.

### Config pass-through and `frozen`

Projections are **immutable by default** (`frozen=True`): a projection is a derived view of its source, so attempting `instance.x = ...` raises `ValidationError`. Opt back into mutation with `frozen=False` if you need it. Merge additional `ConfigDict` options (e.g. alias generator for camelCase output) via `config=`:

```python
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

CamelSummary = projection(
    UserSummary,
    config=ConfigDict(alias_generator=to_camel, populate_by_name=True),
)

MutableSummary = projection(UserSummary, frozen=False)
```

`frozen` and `config` propagate into every Protocol reachable from the outer one, so an alias generator applied at the top level also camelCases nested projections. `extra="ignore"` and `from_attributes=True` are hard invariants — user-supplied `ConfigDict` cannot override them.

Classes are cached per `(protocol, config, frozen)` triple; config values must be hashable.

### Error handling

`project()` wraps pydantic's `ValidationError` in a `ProjectionError` that carries the protocol, source type, and original validation error:

```python
from pydantic_projections import ProjectionError

try:
    project(partial_user, UserSummary)
except ProjectionError as e:
    e.protocol           # the Protocol class
    e.source_type        # type(instance)
    e.validation_error   # the underlying pydantic ValidationError
```

### JSON shortcut

```python
from pydantic_projections import project_json, project_json_bytes

project_json(user, UserSummary)                 # str
project_json(user, UserSummary, indent=2)       # forwards **kwargs to the projection's serializer
project_json_bytes(user, UserSummary)           # bytes — skip the str intermediate
```

Prefer `project_json_bytes` when writing to a socket or HTTP response: it calls the projection class's Rust-backed serializer directly and avoids the bytes→str→bytes round-trip.

### Cache management

```python
from pydantic_projections import cache_clear
cache_clear()  # useful in test fixtures or hot-reload workflows
```

## Semantics

- **Extras are ignored** on deserialisation (`extra="ignore"`). This is a hard invariant — passing `extra="forbid"` via `config=` does not override it.
- **`from_attributes=True`** — accepts dicts, JSON, or arbitrary objects that expose the Protocol's members. Also a hard invariant.
- **Projections are immutable by default** (`frozen=True`). Pass `frozen=False` for a mutable variant.
- **`frozen` and `config=` propagate to nested projections** — an alias generator or `frozen` flag applied at the top level also applies to every Protocol reachable through containers and unions.
- **Optional widening** is allowed: source `name: str` is accepted by a Protocol declaring `name: str | None`.
- **Narrowing** is not: if the source value is `None` for a Protocol field typed `str`, validation raises.
- **Classes are cached** per `(protocol, config, frozen)` via `functools.cache`.

## Performance

- `project()` and `project_json()` invoke the projection class's `__pydantic_validator__` directly, skipping `BaseModel.model_validate`'s Python wrapper. Observable behaviour is unchanged; per-call cost is ~1.3–1.5× lower.
- `project_json_bytes()` emits bytes via `__pydantic_serializer__.to_json` directly, avoiding `model_dump_json().encode()`'s bytes→str→bytes round-trip.
- `ProjectedResponse` (FastAPI) skips `serialize_response` + `jsonable_encoder` + `json.dumps` and goes straight from source → validated projection → JSON bytes via two Rust-backed calls (`validate_python`, then `to_json`) with no `jsonable_encoder` / `json.dumps` step in between. In our benches (`benches/test_render_bench.py`) the fast path runs roughly 2–4× faster than the `response_model=projection(...)` baseline, depending on FastAPI version and response shape. Run locally with `uv run pytest benches/ --benchmark-only` — numbers vary by machine, so compare relative columns.

## Limitations

- Cyclic Protocols (a Protocol that references itself transitively) are not supported and will recurse.
- Generic Protocols (`Protocol[T]`) with unresolved `TypeVar`s are not supported.
- Config values passed via `config=` must be hashable for caching.

## Development

```bash
uv sync
uv run pytest
uv run python scripts/validate_tests.py
uv run ruff check src/ tests/ benches/ scripts/
uv run mypy src/
uv run coverage run -m pytest && uv run coverage report
uv run pytest benches/ --benchmark-only    # perf micro-benches
```

Tests use pytest-describe (`describe_`/`when_`/`with_`/`it_`). See `CLAUDE.md` for conventions.
