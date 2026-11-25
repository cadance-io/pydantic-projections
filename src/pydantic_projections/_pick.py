from __future__ import annotations

import re
import types
from collections.abc import Mapping
from functools import cache
from typing import TYPE_CHECKING, Annotated, Any, Protocol, get_args, get_origin

from pydantic import BaseModel, Field
from pydantic_core import PydanticUndefined

from ._annotations import map_annotation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic.fields import ComputedFieldInfo, FieldInfo

# FieldInfo / ComputedFieldInfo attributes worth republishing on a projection.
# Allowlisted rather than copied wholesale: a `default` would defeat the
# library's "a projected field is always required" invariant, and a validation
# alias would redirect `from_attributes` lookup to an attribute the source
# instance does not have.
_CARRIED = ("title", "description", "examples", "json_schema_extra", "deprecated")

# The OpenAPI 3 rule for a key of `components/schemas`, which a name becomes.
_OPENAPI_KEY = re.compile(r"[A-Za-z0-9._-]+")

# One explicit name states one published contract, so a second selection
# under it is refused. Default names are derived and may repeat.
_picked_by_name: dict[str, type[Any]] = {}


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

    A name may be a dotted path, selecting through a field typed as another
    model — including through ``list``, ``dict`` and ``| None`` — to any depth::

        pick(Order, "id", "address.street", "address.city.name")

    Naming a field without a path publishes that field whole, nested models
    included. Picking both a field and a path through it is an error.

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

    ``name`` overrides the generated Protocol's name, and prefixes every nested
    name below it, so one override disambiguates a whole tree. The projection
    class, and so the OpenAPI schema, takes the same name. Worth setting when
    two picks of the same model — or two selections through the same field —
    would otherwise collide in an OpenAPI schema. It must be a ``str`` that is
    a valid OpenAPI schema key, and no other selection may use it.

    The result is cached, so equal calls yield the same Protocol (and therefore
    the same projection class). The cache holds a reference to ``model``; call
    :func:`cache_clear` when picking from models built at runtime.
    """
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise TypeError(f"pick() expects a BaseModel subclass, got {model!r}")
    if not names:
        raise ValueError("pick() requires at least one field name to project")
    # Path syntax is checked here, against what the caller actually typed:
    # _protocol_for only ever sees the tail of a path it is descending into.
    malformed = [n for n in names if not all(part for part in n.split("."))]
    if malformed:
        raise ValueError(
            f"malformed field path {', '.join(repr(n) for n in malformed)}"
        )
    if name is not None:
        _check_name(name)
    # Deduplicated before the cache lookup, so that equal selections written
    # differently still resolve to one Protocol.
    picked = _protocol_for(model, tuple(dict.fromkeys(names)), metadata, aliases, name)
    if name is not None:
        _claim_name(name, picked)
    return picked


def _check_name(name: str) -> None:
    if not isinstance(name, str):
        raise TypeError(f"pick() name must be a str, got {name!r}")
    if not _OPENAPI_KEY.fullmatch(name):
        raise ValueError(
            f"pick() name {name!r} is not a valid OpenAPI schema key; "
            "use letters, digits, '.', '-' and '_'"
        )


def _claim_name(name: str, picked: type[Any]) -> None:
    owner = _picked_by_name.setdefault(name, picked)
    if owner is not picked:
        raise ValueError(
            f"pick() name {name!r} already names another selection; "
            "one name publishes one schema, so choose another name"
        )


@cache
def _protocol_for(
    model: type[BaseModel],
    names: tuple[str, ...],
    metadata: bool,
    aliases: bool,
    name: str | None,
) -> type[Any]:
    # Selection is validated here rather than in pick() because a dotted path
    # recurses back through this function for each level it descends. Unknown
    # heads are rejected first: a typo should be reported as a typo, not as
    # whatever else it happens to conflict with.
    _reject_unknown(model, tuple(dict.fromkeys(n.partition(".")[0] for n in names)))
    selection = _group_paths(names)
    protocol_name = name or f"{model.__name__}View"

    namespace = {
        "__annotations__": {
            field: _annotation_for(
                model,
                field,
                paths,
                parent=protocol_name,
                metadata=metadata,
                aliases=aliases,
            )
            for field, paths in selection.items()
        },
        # Keeps forward references inside the source's annotations resolvable.
        "__module__": model.__module__,
    }
    return types.new_class(
        protocol_name,
        (Protocol,),
        exec_body=lambda ns: ns.update(namespace),
    )


def _group_paths(names: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Map each head field to the paths selected beneath it, in source order.

    An empty tuple means the field itself was picked, not a path through it.
    """
    selection: dict[str, list[str]] = {}
    whole: set[str] = set()
    for entry in names:
        head, _, rest = entry.partition(".")
        selection.setdefault(head, [])
        if rest:
            selection[head].append(rest)
        else:
            whole.add(head)

    both = [head for head, paths in selection.items() if paths and head in whole]
    if both:
        raise ValueError(
            f"cannot pick both {', '.join(repr(h) for h in both)} and a path "
            "through it; pick the whole field or the paths beneath it, not both"
        )
    return {head: tuple(dict.fromkeys(paths)) for head, paths in selection.items()}


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
    paths: tuple[str, ...],
    *,
    parent: str,
    metadata: bool,
    aliases: bool,
) -> Any:
    field = model.model_fields.get(name)
    if field is not None:
        annotation = field.annotation
        if paths:
            try:
                annotation = _select_through(
                    annotation,
                    paths,
                    f"{parent}{_camel(name)}",
                    metadata=metadata,
                    aliases=aliases,
                )
            except (ValueError, TypeError) as exc:
                # One decoration point, so a failure at any depth reports the
                # path that reached it rather than just the innermost model.
                raise type(exc)(
                    f"cannot select through {model.__name__}.{name}: {exc}"
                ) from exc
        return _annotate(
            field, annotation, field.metadata, metadata=metadata, aliases=aliases
        )

    if paths:
        raise ValueError(
            f"cannot select through {model.__name__}.{name}: "
            "it is a computed field, not a model field"
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


def _select_through(
    annotation: Any,
    paths: tuple[str, ...],
    name: str,
    *,
    metadata: bool,
    aliases: bool,
) -> Any:
    """Swap the model inside ``annotation`` for a Protocol picking ``paths``."""
    nested = _model_in(annotation)
    picked = _protocol_for(nested, paths, metadata, aliases, name)
    return map_annotation(annotation, lambda leaf: picked if leaf is nested else leaf)


def _model_in(annotation: Any) -> type[BaseModel]:
    """The single model reachable through ``annotation``; ambiguity is an error."""
    found = _models_in(annotation)

    if any(in_key for _, in_key in found):
        raise ValueError(
            f"{_render(annotation)} holds it as a mapping key, "
            "which identifies the entry rather than being part of it"
        )

    models = list(dict.fromkeys(model for model, _ in found))
    if not models:
        raise ValueError(f"{_render(annotation)} contains no model to select from")
    if len(models) > 1:
        raise ValueError(
            f"{_render(annotation)} is ambiguous between "
            f"{', '.join(model.__name__ for model in models)}"
        )
    return models[0]


def _models_in(
    annotation: Any,
    *,
    in_key: bool = False,
) -> list[tuple[type[BaseModel], bool]]:
    """Every model inside ``annotation``, flagged when it sits in a mapping key."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [(annotation, in_key)]

    args = get_args(annotation)
    origin = get_origin(annotation)
    if isinstance(origin, type) and issubclass(origin, Mapping) and len(args) == 2:
        key, value = args
        return [*_models_in(key, in_key=True), *_models_in(value, in_key=in_key)]

    return [model for arg in args for model in _models_in(arg, in_key=in_key)]


def _render(annotation: Any) -> str:
    """``float`` rather than ``<class 'float'>``, without flattening generics."""
    if isinstance(annotation, type) and not get_args(annotation):
        return annotation.__name__
    return str(annotation)


def _camel(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_"))


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
