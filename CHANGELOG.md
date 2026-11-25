# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- A `@property` on a Protocol whose return annotation does not resolve now raises `TypeError` that names the Protocol, the property and the class that declares it. Before, `projection()` dropped the property with no error, so the projection published fewer fields than the Protocol declared. An unresolvable attribute annotation already raised `TypeError`. A property with no return annotation, or with a getter that is not a function (such as `operator.attrgetter`), is still skipped.
- Every CI job ran its tests on Python 3.11, whatever its matrix version, because each `uv run` followed `.python-version`. The jobs now set `UV_PYTHON`, and a step fails when the interpreter is not the matrix version.

### Added
- CI tests Python 3.14, and the package declares the `Python :: 3.14` classifier.

## [0.6.1] - 2026-08-05

### Fixed
- The distribution now ships a `py.typed` marker, so consumers actually see the library's types. Without it mypy reports `Skipping analyzing "pydantic_projections": module is installed, but missing library stubs or py.typed marker` and every downstream project has to add an `ignore_missing_imports` override — which silences the error by discarding the annotations, defeating the `Callable[..., P]` work in 0.6.0. The package has advertised `Typing :: Typed` since the first release while the marker was never present, so the classifier was inaccurate for every version through 0.6.0. `hatchling` picks the file up from the package directory with no build-config change. The publish workflow now inspects the built wheel and fails if the marker is absent, so this cannot regress into a release again.

## [0.6.0] - 2026-08-05

### Added
- Dotted paths in `pick()` — a name may now be a path, so `pick(Order, "id", "address.street", "address.city.name")` selects through a field typed as another model instead of publishing that model whole. Paths descend to any depth and traverse containers, so `list[Model]`, `dict[str, Model]` and `Model | None` are all selected through. Naming a field without a path still publishes it whole, nested models included — unchanged, and still what you want when you want the whole thing. Each nested level gets its own Protocol named after its parent (`OrderView` + `address` gives `OrderViewAddress`, then `OrderViewAddressCity`), so two parents picking different subsets of the same model do not collide in an OpenAPI schema; `metadata=` and `aliases=` are inherited by every level. Selection is validated at `pick()` call time, import time in practice: a head field whose annotation resolves to no model or to several (an ambiguous union) raises `ValueError`, as does a path through a `@computed_field`, a model reached only as a mapping key (`dict[Model, str]` — the key identifies the entry rather than being part of it), an unknown leaf (the error names the path it failed on), a malformed path such as `"address."`, and picking both a field and a path through it. Closes #5.

### Fixed
- The documented call shapes are now clean under `mypy --strict`. Every public entry point declared `protocol: type[P]`, and mypy emits `type-abstract` whenever a Protocol class object is passed to a `type[T]` parameter — so `project(user, UserSummary)` was an error under `--strict` for an ordinary hand-written Protocol, across `project`, `projection`, `project_json`, `project_json_bytes`, `ProjectedResponse` and `openapi_response`. Present since 0.1.0 and invisible because CI only ran mypy over `src/`. The parameter is now `Callable[..., P]`: the error is gone, inference is unchanged (`project(u, UserSummary)` still reveals `UserSummary`), a non-callable argument is still rejected statically, and anything that is not a Protocol class still raises `TypeError` at runtime. Closes #6.
- `ProjectedResponse` and `openapi_response` are now listed in `__all__`. They were only implicitly re-exported, so importing them from `pydantic_projections` failed under `mypy --strict`. A new `tests/typing_surface.py` — not collected by pytest — is type-checked in CI so neither regresses silently.

## [0.5.0] - 2026-08-04

### Added
- `pick(model, *names, metadata=True, aliases=False, name=None)` — derive a Protocol from an existing model instead of restating its field list, so the projected types cannot drift from the source. Returns an ordinary Protocol, so `project()`, `projection(config=, frozen=)`, `ProjectedResponse`, `openapi_response`, and nesting inside another Protocol all work unchanged. It is an allowlist: a field added to the model later stays private until someone opts it in, which is why there is deliberately no `omit()` counterpart. Every picked field is required whatever default the source declares; constraints (`min_length`, `gt`, …) and schema documentation (`title`, `description`, `examples`, `json_schema_extra`, `deprecated`) carry over, and `metadata=False` gives bare annotations. Aliases are dropped by default because a validation alias makes pydantic look the attribute up under a name the source instance does not have; `aliases=True` carries the source's serialization alias only, so a dump with `by_alias=True` matches the source's wire format while validation still reads the attribute name. The allowlist is one level deep — a picked field typed as another model is published whole; subclass the picked Protocol to narrow it. `@computed_field` members are pickable and use their return type. `name=` overrides the generated Protocol's name (default `f"{Model.__name__}View"`), useful when two picks of the same model would collide in an OpenAPI schema. Unknown field names raise `ValueError` at `pick()` call time rather than at first use; a non-model source raises `TypeError`. Results are cached, so equal calls yield the same Protocol and therefore the same projection class — `cache_clear()` clears both caches.

### Fixed
- `Annotated[T, Field(...)]` metadata declared on a Protocol member is no longer stripped. Annotations were resolved without `include_extras=True`, so pydantic metadata was silently discarded: a `min_length` never fired, and `description` / `examples` never reached the JSON schema. Both annotated attributes and `@property` members now keep their metadata, and a Protocol nested inside an annotation is still substituted. **Behaviour change**: constraints that previously did nothing now apply, so code that relied on the old silence will start seeing `ValidationError`s (wrapped in `ProjectionError` by `project()`). A `default=` in the metadata still does not make the field optional — projected fields remain required.

## [0.4.0] - 2026-05-07

### Added
- `ProjectedResponse` — FastAPI response class that serializes a source instance through a Protocol straight to JSON bytes, bypassing FastAPI's `serialize_response` + `jsonable_encoder` + `json.dumps` chain. Benchmarked ~2–4× faster than the `response_model=projection(...)` baseline on raw ser/deser work (varies by FastAPI version and response shape). Accepts `**dump_kwargs` (e.g. `by_alias=True`, `exclude_none=True`, `indent=2`) forwarded to the projection's serializer. Raises `ProjectionError` at construction time if the source does not satisfy the Protocol. Import from `pydantic_projections` (lazy); requires the `fastapi` optional extra.
- `openapi_response(protocol)` — returns the FastAPI `responses=` entry for a projection so the OpenAPI spec advertises the projection's schema without manual `{"model": ...}` plumbing. Pairs with `ProjectedResponse`. Composes for multi-status routes. Lazy fastapi import.
- `project_json_bytes(instance, protocol, **kwargs) -> bytes` — emits JSON bytes via the projection class's Rust-backed serializer, skipping the `str` intermediate that `model_dump_json().encode()` goes through.
- Optional `fastapi` install extra: `pip install pydantic-projections[fastapi]`.
- `benches/` suite driven by `pytest-benchmark` for measuring the projection and render paths.

### Changed
- `project()` and `project_json()` now invoke `__pydantic_validator__.validate_python` directly instead of going through `BaseModel.model_validate`. Observable behaviour is identical; per-call cost drops by roughly 1.3–1.5× depending on shape.
- `project_json()` now emits its result through `__pydantic_serializer__.to_json` (decoded to `str`) rather than `BaseModel.model_dump_json`. Observable behaviour and accepted `**kwargs` are unchanged.

## [0.3.0] - 2026-04-22

### Changed
- **BREAKING**: `projection(...)` now defaults to `frozen=True`. A projection is a derived view of its source, so mutation is almost always a bug; projections are now immutable by default and are hashable (usable as `dict` keys / in `set`s). Pass `frozen=False` to restore the previous behaviour.

### Fixed
- `frozen` and `config=` now propagate into nested Protocol projections. Previously only the top-level projection inherited these settings, so an alias generator applied at the outer level silently skipped nested models and a frozen outer projection still permitted mutation of its inner projections.
- `ConfigDict(extra=...)` and `ConfigDict(from_attributes=...)` passed via `config=` no longer override the library's `extra="ignore"` / `from_attributes=True` invariants.

### Changed
- Nested projections are now cached under the outer `(frozen, config)` tuple, so each distinct outer configuration produces its own inner projection class. Previously all nested classes for a given Protocol were a single shared instance.

## [0.2.0] - 2026-04-22

### Added
- Nested Protocol projection: fields typed as other Protocols are recursively projected.
- Container support: `list[P]`, `dict[K, P]`, `tuple[P, ...]`, `P | None`, `Union[...]` are traversed and their inner Protocols substituted.
- Call-site typing: `project(instance, Proto)` is declared to return `P`, so mypy/pyright resolve attribute access without casts.
- `@property`-style Protocol declarations: `@property def x(self) -> T: ...` is supported alongside annotated attributes.
- Config pass-through via `projection(Proto, config=ConfigDict(...), frozen=bool)`.
- `ProjectionError` wraps `pydantic.ValidationError` with `protocol`, `source_type`, and `validation_error` attributes.
- `project_json(instance, Proto, **kwargs)` shortcut.
- `cache_clear()` for test fixtures and hot-reload workflows.
- MIT LICENSE and GitHub Actions CI workflow (Python 3.11 / 3.12 / 3.13).

### Changed
- Cache key is now `(protocol, frozen, sorted-config-items)`; non-hashable config values raise `TypeError`.

## [0.1.0] - 2026-04-22

### Added
- Initial release.
- `project(instance, Protocol)` and `projection(Protocol)` APIs.
- Extras ignored on deserialisation; `from_attributes=True` for dict / JSON / object inputs.
- Class caching per Protocol via `functools.cache`.
- pytest-describe test suite with AST-based structure validator.

[Unreleased]: https://github.com/cadance-io/pydantic-projections/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/cadance-io/pydantic-projections/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/cadance-io/pydantic-projections/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/cadance-io/pydantic-projections/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/cadance-io/pydantic-projections/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/cadance-io/pydantic-projections/releases/tag/v0.3.0
