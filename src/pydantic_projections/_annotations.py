from __future__ import annotations

import types
from typing import TYPE_CHECKING, Any, Union, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Callable


def map_annotation(annotation: Any, leaf: Callable[[Any], Any]) -> Any:
    """Rewrite ``annotation`` by applying ``leaf`` to each type inside it.

    Containers, unions and ``Annotated`` metadata are rebuilt around whatever
    ``leaf`` returns, so ``list[P]``, ``dict[str, P]``, ``P | None`` and
    ``Annotated[P, ...]`` are all traversed.

    ``leaf`` declines a candidate by returning it unchanged; returning anything
    else stops the walk for that branch, so a leaf never rewrites its own
    output. An annotation nothing touched comes back identical, so a rewrite
    that changes nothing allocates nothing.
    """
    replaced = leaf(annotation)
    if replaced is not annotation:
        return replaced

    origin = get_origin(annotation)
    if origin is None:
        return annotation

    args = get_args(annotation)
    new_args = tuple(map_annotation(arg, leaf) for arg in args)
    # Identity, not equality: an equal-but-distinct rewrite is still a rewrite,
    # and dropping it would silently discard what `leaf` asked for.
    if all(new is old for new, old in zip(new_args, args, strict=True)):
        return annotation

    if origin is Union or origin is types.UnionType:
        merged = new_args[0]
        for arg in new_args[1:]:
            merged = merged | arg
        return merged

    return origin[new_args] if len(new_args) != 1 else origin[new_args[0]]
