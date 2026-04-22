from __future__ import annotations

import types
from functools import cache
from typing import (
    Any,
    Generic,
    Protocol,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

P = TypeVar("P")

_SKIP_IN_MRO: tuple[Any, ...] = (object, Generic, Protocol)


class ProjectionError(ValueError):
    """Raised when an instance does not satisfy a Protocol during projection."""

    def __init__(
        self,
        message: str,
        *,
        protocol: type,
        source_type: type,
        validation_error: ValidationError,
    ) -> None:
        super().__init__(message)
        self.protocol = protocol
        self.source_type = source_type
        self.validation_error = validation_error


def projection(
    protocol: type[P],
    *,
    config: ConfigDict | None = None,
    frozen: bool = True,
) -> type[BaseModel]:
    """Build (or fetch the cached) Pydantic model that mirrors a Protocol's fields.

    By default the returned class ignores unknown fields on input
    (``extra="ignore"``), supports validation from plain attributes
    (``from_attributes=True``), and is **immutable** (``frozen=True``), since a
    projection is a derived view of its source rather than a live entity.
    Nested Protocols and containers of Protocols are recursively projected.
    Pass ``config`` to merge additional ``ConfigDict`` options (e.g.
    ``alias_generator``) and ``frozen=False`` to opt back in to mutation.

    The result is cached per ``(protocol, config, frozen)``. Config values must
    be hashable.
    """
    if not isinstance(protocol, type):
        raise TypeError(f"projection() expects a Protocol class, got {protocol!r}")
    return _build(cast("type", protocol), frozen, _freeze_config(config))


def project(instance: Any, protocol: type[P]) -> P:
    """Project ``instance`` through ``protocol``, returning a typed projection model.

    Raises :class:`ProjectionError` if the instance does not satisfy the Protocol.
    """
    return cast("P", _project_one(instance, protocol))


def project_json(
    instance: Any,
    protocol: type[P],
    **dump_kwargs: Any,
) -> str:
    """Shortcut for ``project(instance, protocol).model_dump_json(**kwargs)``."""
    return _project_one(instance, protocol).model_dump_json(**dump_kwargs)


def cache_clear() -> None:
    """Clear the projection class cache.

    Useful in test fixtures that redefine Protocols or in hot-reload workflows.
    """
    _build.cache_clear()


def _project_one(instance: Any, protocol: type[P]) -> BaseModel:
    model_cls = projection(protocol)
    try:
        return model_cls.model_validate(instance)
    except ValidationError as exc:
        raise ProjectionError(
            f"{type(instance).__name__} does not satisfy "
            f"{getattr(protocol, '__name__', protocol)!r}: {exc}",
            protocol=protocol,
            source_type=type(instance),
            validation_error=exc,
        ) from exc


def _freeze_config(config: ConfigDict | None) -> tuple[tuple[str, Any], ...] | None:
    if config is None:
        return None
    items = tuple(sorted(config.items(), key=lambda kv: kv[0]))
    try:
        hash(items)
    except TypeError as exc:
        raise TypeError(
            "projection() config values must be hashable for caching; "
            f"got unhashable value: {exc}"
        ) from exc
    return items


@cache
def _build(
    protocol: type,
    frozen: bool,
    config_items: tuple[tuple[str, Any], ...] | None,
) -> type[BaseModel]:
    hints = _collect_field_hints(protocol)

    fields: dict[str, Any] = {
        name: (_substitute(annotation), ...)
        for name, annotation in hints.items()
        if not name.startswith("_")
    }

    if not fields:
        raise TypeError(
            f"Protocol {getattr(protocol, '__name__', protocol)!r} declares no "
            "annotated members; nothing to project."
        )

    cfg: dict[str, Any] = {"extra": "ignore", "from_attributes": True}
    if config_items is not None:
        cfg.update(dict(config_items))
    cfg["frozen"] = frozen

    return create_model(
        f"{protocol.__name__}Projection",
        __config__=cast("ConfigDict", cfg),
        **fields,
    )


def _collect_field_hints(protocol: type) -> dict[str, Any]:
    """Merge annotated attributes and ``@property`` declarations into one dict."""
    try:
        hints = dict(get_type_hints(protocol))
    except Exception as exc:
        raise TypeError(
            f"Could not resolve annotations on {protocol!r}: {exc}"
        ) from exc

    for klass in protocol.__mro__:
        if klass in _SKIP_IN_MRO:
            continue
        for name, value in vars(klass).items():
            if name.startswith("_") or name in hints:
                continue
            if not (isinstance(value, property) and value.fget is not None):
                continue
            try:
                prop_hints = get_type_hints(value.fget)
            except Exception:  # noqa: S112
                continue
            if "return" in prop_hints:
                hints[name] = prop_hints["return"]

    return hints


def _is_protocol(t: Any) -> bool:
    return (
        isinstance(t, type) and getattr(t, "_is_protocol", False) and t is not Protocol
    )


def _substitute(annotation: Any) -> Any:
    """Replace Protocol references inside ``annotation`` with their projections."""
    if _is_protocol(annotation):
        return _build(annotation, False, None)

    origin = get_origin(annotation)
    if origin is None:
        return annotation

    args = get_args(annotation)
    new_args = tuple(_substitute(a) for a in args)
    if new_args == args:
        return annotation

    if origin is Union or origin is types.UnionType:
        merged = new_args[0]
        for arg in new_args[1:]:
            merged = merged | arg
        return merged

    return origin[new_args] if len(new_args) != 1 else origin[new_args[0]]
