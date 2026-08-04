from __future__ import annotations

import types
from functools import cache
from typing import Annotated, Any, Protocol

from pydantic import BaseModel, Field

# FieldInfo / ComputedFieldInfo attributes worth republishing on a projection.
# Allowlisted rather than copied wholesale: a `default` would defeat the
# library's "a projected field is always required" invariant, and an alias
# redirects `from_attributes` lookup to an attribute the source does not have.
_CARRIED = ("title", "description", "examples", "json_schema_extra", "deprecated")
_ALIASES = ("alias", "validation_alias", "serialization_alias")


def pick(
    model: type[BaseModel],
    *names: str,
    metadata: bool = True,
    aliases: bool = False,
    name: str | None = None,
) -> type[Any]:
    """Derive a Protocol from ``model`` exposing only ``names``.

    An allowlist: a field added to ``model`` later stays private until someone
    opts it in. Annotations come from the source, so they cannot drift from it.

    The result is an ordinary Protocol — pass it to :func:`project`,
    :func:`projection`, ``ProjectedResponse``, or nest it inside another
    Protocol. Every picked field is required, whatever default the source
    declares, since a projection describes a value that already exists.

    ``@computed_field`` members are pickable; their return type is used.

    Field constraints (``min_length``, ``gt``, …) and schema documentation
    (``title``, ``description``, ``examples``, ``json_schema_extra``,
    ``deprecated``) carry over. Pass ``metadata=False`` for bare annotations.
    Aliases are dropped by default because a validation alias makes pydantic
    look the attribute up under a name the source instance does not have; pass
    ``aliases=True`` if the source's aliases are what you want on the wire.

    ``name`` overrides the generated Protocol's name — worth setting when two
    picks of the same model would otherwise collide in an OpenAPI schema.

    The result is cached, so equal calls yield the same Protocol (and therefore
    the same projection class).
    """
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise TypeError(f"pick() expects a BaseModel subclass, got {model!r}")
    if not names:
        raise ValueError("pick() requires at least one field name to project")
    return _protocol_for(model, names, metadata, aliases, name)


@cache
def _protocol_for(
    model: type[BaseModel],
    names: tuple[str, ...],
    metadata: bool,
    aliases: bool,
    name: str | None,
) -> type[Any]:
    _reject_unknown(model, names)
    namespace = {
        "__annotations__": {
            field: _annotation_for(model, field, metadata, aliases) for field in names
        },
        # Keeps forward references inside the source's annotations resolvable.
        "__module__": model.__module__,
    }
    return types.new_class(
        name or f"{model.__name__}View",
        (Protocol,),
        exec_body=lambda ns: ns.update(namespace),
    )


def _reject_unknown(model: type[BaseModel], names: tuple[str, ...]) -> None:
    known = {*model.model_fields, *model.model_computed_fields}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(
            f"{model.__name__} has no field {', '.join(repr(n) for n in unknown)}; "
            f"available: {', '.join(sorted(known))}"
        )


def _annotation_for(
    model: type[BaseModel],
    name: str,
    metadata: bool,
    aliases: bool,
) -> Any:
    field = model.model_fields.get(name)
    if field is not None:
        return _annotate(field, field.annotation, field.metadata, metadata, aliases)
    computed = model.model_computed_fields[name]
    return _annotate(computed, computed.return_type, (), metadata, aliases)


def _annotate(
    info: Any,
    annotation: Any,
    constraints: Any,
    metadata: bool,
    aliases: bool,
) -> Any:
    """Re-attach the allowlisted metadata of ``info`` to ``annotation``."""
    if not metadata:
        return annotation

    attrs = (*_CARRIED, *_ALIASES) if aliases else _CARRIED
    carried = {a: value for a in attrs if (value := getattr(info, a, None)) is not None}

    extras = [*constraints]
    if carried:
        extras.append(Field(**carried))
    if not extras:
        return annotation
    return Annotated[(annotation, *extras)]
