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

### Field metadata

A Protocol member can carry pydantic metadata through `Annotated[T, Field(...)]`. Constraints are enforced and schema hints reach the JSON schema:

```python
from typing import Annotated, Protocol

from pydantic import Field


class UserSummary(Protocol):
    id: int
    name: Annotated[str, Field(min_length=3, examples=["Alice"])]


projection(UserSummary).model_json_schema()["properties"]["name"]
# -> {'examples': ['Alice'], 'minLength': 3, 'title': 'Name', 'type': 'string'}

project(User(id=1, name="Al", email="a@b.c", password_hash="x"), UserSummary)
# -> raises ProjectionError: name is shorter than min_length
```

`@property` members can be annotated the same way, and a Protocol nested inside the annotation (`Annotated[AddressSummary, Field(description=...)]`) is still substituted. A `default=` in the metadata does **not** make the field optional — projected fields stay required.

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

### Deriving a projection from a model (`pick`)

Hand-written response models drift. Thirteen FastAPI routes handing SQLModel `table=True` classes straight to `response_model` publish every raw DB column — `password_hash` today, whatever the next migration adds tomorrow. The usual fix is thirteen hand-written response models, each of which has to be kept in step with its table by hand. `pick(Model, *names)` replaces each one with a single line whose types are read from the source, so they cannot drift from it:

```python
from datetime import datetime

from pydantic import BaseModel
from pydantic_projections import pick, project


class User(BaseModel):
    id: int
    email: str
    created_at: datetime
    password_hash: str


UserView = pick(User, "id", "email", "created_at")

user = User(
    id=1,
    email="alice@example.com",
    created_at=datetime(2026, 1, 1),
    password_hash="secret",
)

project(user, UserView).model_dump_json()
# -> '{"id":1,"email":"alice@example.com","created_at":"2026-01-01T00:00:00"}'
```

`pick` returns an ordinary Protocol, so the rest of this README applies to it unchanged — `project()`, `projection(..., config=, frozen=)`, nesting it inside another Protocol, and both FastAPI patterns described [below](#fastapi-integration):

```python
@app.get("/users/{id}", response_model=projection(UserView))
def get_user(id: int) -> User:
    return db.get_user(id)


@app.get("/fast/users/{id}", responses={200: openapi_response(UserView)})
def get_user_fast(id: int) -> Response:
    return ProjectedResponse(db.get_user(id), UserView)
```

Both return `{"id":1,"email":"alice@example.com","created_at":"2026-01-01T00:00:00"}`, and the second advertises `$ref: '#/components/schemas/UserViewProjection'` in the spec.

`pick` is an allowlist: a column added to `User` later stays private until someone opts it in. There is deliberately no `omit()` counterpart — a denylist publishes every new column by default, which is the failure mode `pick` exists to remove.

- Every picked field is required, whatever default the source declares.
- Constraints (`min_length`, `gt`, …) and schema documentation (`title`, `description`, `examples`, `json_schema_extra`, `deprecated`) carry over. Pass `metadata=False` for bare annotations.
- Aliases are dropped by default: a validation alias makes pydantic look the attribute up under a name the source instance does not have, which breaks `from_attributes`. Pass `aliases=True` to carry the source's *serialization* alias, so a dump with `by_alias=True` matches the source's wire format while validation still reads the attribute name.
- `@computed_field` members are pickable; their return type is used.
- `name=` overrides the generated Protocol's name (default `f"{Model.__name__}View"`, so `UserView` projects to `UserViewProjection`). Set it when two picks of the same model would otherwise collide in an OpenAPI schema. To name the projection class itself, pass `name=` to `projection()` — see [FastAPI integration](#fastapi-integration).
- Unknown names raise at `pick()` call time — import time in practice, not on the first request:

```python
pick(User, "id", "emial")
# -> ValueError: User has no field 'emial'; available: created_at, email, id, password_hash
```

A source that isn't a `BaseModel` subclass raises `TypeError`. Results are cached, so equal calls return the same Protocol and therefore the same projection class; `cache_clear()` clears it.

#### Selecting through nested models

A name may be a dotted path. `pick` follows it into a field typed as another model and publishes only the fields you named, to any depth:

```python
class City(BaseModel):
    id: int
    name: str
    country_code: str


class Address(BaseModel):
    id: int
    street: str
    zip_code: str
    city: City


class Item(BaseModel):
    id: int
    sku: str
    cost: float


class Order(BaseModel):
    id: int
    total: float
    address: Address
    items: list[Item]


OrderView = pick(Order, "id", "total", "address.street", "address.city.name")

project(order, OrderView).model_dump_json()
# -> '{"id":7,"total":9.5,"address":{"street":"1 Main St","city":{"name":"Paris"}}}'
```

Paths traverse containers, so `list[Model]`, `dict[str, Model]` and `Model | None` are selected through the same way:

```python
ItemsView = pick(Order, "id", "items.sku")

project(order, ItemsView).model_dump_json()
# -> '{"id":7,"items":[{"sku":"ABC"},{"sku":"DEF"}]}'
```

Naming a field *without* a path still publishes it whole, nested models included — unchanged, and still what you want when you want the whole thing:

```python
project(order, pick(Order, "id", "address")).model_dump_json()
# -> '{"id":7,"address":{"id":3,"street":"1 Main St","zip_code":"75001","city":{"id":1,"name":"Paris","country_code":"FR"}}}'
```

Every nested level gets its own Protocol, named after its parent — `OrderView` + `address` gives `OrderViewAddress`, then `OrderViewAddressCity` — so two parents picking different subsets of the same model don't collide in an OpenAPI schema:

```python
projection(OrderView).model_json_schema()["$defs"].keys()
# -> dict_keys(['OrderViewAddressCityProjection', 'OrderViewAddressProjection'])
```

That covers different parents. Two selections through the *same* field still produce two Protocols under one name — `pick(Order, "address.street")` and `pick(Order, "address.zip_code")` are both `OrderViewAddress` — so give one of them a `name=`. It prefixes every nested name below it, so a single override disambiguates the whole tree.

`metadata=` and `aliases=` are inherited by every nested level.

Paths are validated at `pick()` call time, like plain names, and the error names the path it failed on:

```python
pick(Order, "id", "address.stret")
# -> ValueError: in Order.address: Address has no field 'stret'; available: city, id, street, zip_code

pick(Order, "id", "total.amount")
# -> ValueError: cannot select through Order.total: <class 'float'> contains no model to select from

pick(Order, "address.")
# -> ValueError: malformed field path 'address.'

pick(Order, "address", "address.street")
# -> ValueError: cannot pick both 'address' and a path through it; pick the whole field or the paths beneath it, not both
```

A head field whose annotation reaches several models (an ambiguous union) raises too, as does a path through a `@computed_field` — a computed field has a return type, not a model to descend into — and a model reached only as a mapping key (`dict[Model, str]`), since the key identifies the entry rather than being part of it.

#### Narrowing a picked field

Paths cover nested selection. Subclassing covers what a path can't express: tightening an annotation the source declares as nullable, and getting a real `class` statement that is valid as a type. Subclass the picked Protocol and restate only the fields you are changing:

```python
class Order(BaseModel):
    id: int | None = None  # SQLModel-style: nullable until the row is flushed
    total: float
    address: Address


class OrderView(pick(Order, "id", "total", "address.street"), Protocol):
    id: int  # narrowed: no longer nullable


projection(OrderView).model_json_schema()["properties"]["id"]
# -> {'title': 'Id', 'type': 'integer'}

project(order, OrderView).model_dump_json()
# -> '{"id":7,"total":9.5,"address":{"street":"1 Main St"}}'
```

Without the override, the field is required but still nullable:

```python
projection(pick(Order, "id", "total")).model_json_schema()["properties"]["id"]
# -> {'anyOf': [{'type': 'integer'}, {'type': 'null'}], 'title': 'Id'}
```

The base class is picked, so the fields you don't restate still can't drift. And because this is a real `class` statement, `OrderView` is valid as a type — `owner: OrderView` type-checks, unlike the bare `pick(...)` result. Type checkers do flag the dynamic base class, so it needs a `# type: ignore[misc]`.

### Typing at the call site

`project(instance, Proto)` is typed to return `Proto`, so `summary.name` resolves to `str` in mypy/pyright without a cast. At runtime the object is a `BaseModel` subclass that structurally satisfies the Protocol.

Every call shape documented here is clean under `mypy --strict` — passing a Protocol class object to `project`, `projection`, `project_json`, `project_json_bytes`, `ProjectedResponse` or `openapi_response` does not need a `# type: ignore[type-abstract]`. `tests/typing_surface.py` type-checks each of them in CI.

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

FastAPI publishes the class name as the OpenAPI schema name, and from there as the type name in every generated client. The default is `f"{Protocol.__name__}Projection"`. Pass `name=` to publish the contract under the name of its server symbol:

```python
UserResponse = projection(pick(User, "id", "email"), name="UserResponse")
# -> '#/components/schemas/UserResponse', not 'UserViewProjection'
```

The name must be a Python identifier, else `projection()` raises `ValueError`. It applies to the outer class only: nested projections keep their default names.

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

Classes are cached per `(protocol, name, config, frozen)`; config values must be hashable.

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
- `pick()` synthesizes its Protocol at runtime, so type checkers see `Any`. `UserView = pick(...)` is a variable, not a class statement: using it as an annotation (`owner: UserView`) is a mypy error (`Variable "UserView" is not valid as a type`) even though it works at runtime. The field names are strings, so typos and renames are not caught statically either — `pick()` validates them eagerly at call time to compensate. [Subclassing the result](#narrowing-a-picked-field) gets you back a real class statement that is valid as a type, at the cost of one `# type: ignore[misc]` for the dynamic base class.
- `pick()` cannot invent non-nullability. A SQLModel `table=True` class annotates its primary key `id: int | None`, so `pick(Model, "id")` yields `int | None` — required, but still nullable in the schema. `pick` fixes required-ness, not the annotation; [subclass the picked Protocol](#narrowing-a-picked-field) and restate that one field to narrow it.

## Development

```bash
uv sync
uv run pytest
uv run python scripts/validate_tests.py
uv run ruff check src/ tests/ benches/ scripts/
uv run mypy src/ tests/typing_surface.py
uv run coverage run -m pytest && uv run coverage report
uv run pytest benches/ --benchmark-only    # perf micro-benches
```

Tests use pytest-describe (`describe_`/`when_`/`with_`/`it_`). See `CLAUDE.md` for conventions.
