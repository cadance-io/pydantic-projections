from __future__ import annotations

import types
from functools import cache
from typing import TYPE_CHECKING, Annotated, Any, Protocol

from pydantic import BaseModel, Field
from pydantic_core import PydanticUndefined

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic.fields import ComputedFieldInfo, FieldInfo

# FieldInfo / ComputedFieldInfo attributes worth republishing on a projection.
# Allowlisted rather than copied wholesale: a `default` would defeat the
# library's "a projected field is always required" invariant, and a validation
# alias would redirect `from_attributes` lookup to an attribute the source
# instance does not have.
_CARRIED = ("title", "description", "examples", "json_schema_extra", "deprecated")


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
    The allowlist is one level deep — a picked field whose type is another
    ``BaseModel`` publishes that model whole. Nest a Protocol member typed as a
    ``pick`` of that model to narrow it.

    The result is an ordinary Protocol — pass it to :func:`project`,
    :func:`projection`, ``ProjectedResponse``, nest it inside another Protocol,
    or subclass it to narrow a field::

        class OrderView(pick(Order, "id", "total"), Protocol):
            id: int  # narrowed from the source's ``int | None``

    Every picked field is required, whatever default the source declares, since
    a projection describes a value that already exists.

    ``@computed_field`` members are pickable; their return type is used.

    Field constraints (``min_length``, ``gt``, …) and schema documentation
    (``title``, ``description``, ``examples``, ``json_schema_extra``,
    ``deprecated``) carry over. Pass ``metadata=False`` for bare annotations —
    which also drops the aliases ``aliases=True`` would have carried.

    Aliases are dropped by default. ``aliases=True`` carries the source's
    *serialization* alias only (falling back to ``alias``), so a dump with
    ``by_alias=True`` matches the source's wire format. Validation aliases are
    never carried: they would make pydantic look the attribute up under a name
    the source instance does not have, leaving the projection unusable.

    ``name`` overrides the generated Protocol's name — worth setting when two
    picks of the same model would otherwise collide in an OpenAPI schema.

    The result is cached, so equal calls yield the same Protocol (and therefore
    the same projection class). The cache holds a reference to ``model``; call
    :func:`cache_clear` when picking from models built at runtime.
    """
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise TypeError(f"pick() expects a BaseModel subclass, got {model!r}")
    if not names:
        raise ValueError("pick() requires at least one field name to project")
    unique = tuple(dict.fromkeys(names))
    _reject_unknown(model, unique)
    return _protocol_for(model, unique, metadata, aliases, name)


@cache
def _protocol_for(
    model: type[BaseModel],
    names: tuple[str, ...],
    metadata: bool,
    aliases: bool,
    name: str | None,
) -> type[Any]:
    namespace = {
        "__annotations__": {
            field: _annotation_for(model, field, metadata=metadata, aliases=aliases)
            for field in names
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
        noun = "fields" if len(unknown) > 1 else "field"
        raise ValueError(
            f"{model.__name__} has no {noun} "
            f"{', '.join(repr(n) for n in unknown)}; "
            f"available: {', '.join(sorted(known))}"
        )


def _annotation_for(
    model: type[BaseModel],
    name: str,
    *,
    metadata: bool,
    aliases: bool,
) -> Any:
    field = model.model_fields.get(name)
    if field is not None:
        return _annotate(
            field, field.annotation, field.metadata, metadata=metadata, aliases=aliases
        )

    computed = model.model_computed_fields[name]
    if computed.return_type is PydanticUndefined:
        raise TypeError(
            f"{model.__name__}.{name} has no resolved return type; "
            f"call {model.__name__}.model_rebuild() before pick()"
        )
    return _annotate(
        computed, computed.return_type, (), metadata=metadata, aliases=aliases
    )


def _annotate(
    info: FieldInfo | ComputedFieldInfo,
    annotation: Any,
    constraints: Sequence[Any],
    *,
    metadata: bool,
    aliases: bool,
) -> Any:
    """Re-attach the allowlisted metadata of ``info`` to ``annotation``."""
    if not metadata:
        return annotation

    carried: dict[str, Any] = {
        attr: value for attr in _CARRIED if (value := getattr(info, attr, None))
    }
    if aliases and (wire := _wire_alias(info)) is not None:
        carried["serialization_alias"] = wire

    extras = [*constraints]
    if carried:
        extras.append(Field(**carried))
    if not extras:
        return annotation
    return Annotated[(annotation, *extras)]


def _wire_alias(info: FieldInfo | ComputedFieldInfo) -> str | None:
    """The alias a dump with ``by_alias=True`` should emit, if any."""
    serialization = getattr(info, "serialization_alias", None)
    alias = getattr(info, "alias", None)
    return serialization or alias
