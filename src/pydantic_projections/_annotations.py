from __future__ import annotations

import types
from typing import TYPE_CHECKING, Any, Union, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable


def map_annotation(annotation: Any, leaf: Callable[[Any], Any]) -> Any:
    """Rewrite ``annotation`` by applying ``leaf`` to each type inside it.

    Containers, unions and ``Annotated`` metadata are rebuilt around whatever
    ``leaf`` returns, so ``list[P]``, ``dict[str, P]``, ``P | None`` and
    ``Annotated[P, ...]`` are all traversed. An annotation ``leaf`` leaves alone
    is returned unchanged — identity included — so a rewrite that changes
    nothing allocates nothing.

    ``leaf`` returning its argument also makes this usable as a visitor: see
    ``_pick._models_in``.
    """
    replaced = leaf(annotation)
    if replaced is not annotation:
        return replaced

    origin = get_origin(annotation)
    if origin is None:
        return annotation

    args = get_args(annotation)
    new_args = tuple(map_annotation(arg, leaf) for arg in args)
    if new_args == args:
        return annotation

    if origin is Union or origin is types.UnionType:
        merged = new_args[0]
        for arg in new_args[1:]:
            merged = merged | arg
        return merged

    return origin[new_args] if len(new_args) != 1 else origin[new_args[0]]
