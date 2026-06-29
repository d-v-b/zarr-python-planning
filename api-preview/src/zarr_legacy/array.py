"""Legacy 3.x eager-indexing array.

Mirrors the eager ``__getitem__`` / ``__setitem__`` semantics of
``zarr.core.array.Array``, where indexing materializes a NumPy result
immediately. In 4.0.0 indexing becomes lazy by default; eager access remains
available through the ``array.eager[...]`` escape hatch, but the eager default
is removed.

Real 3.x location: ``zarr.core.array``
Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
"""

from __future__ import annotations

from typing import Any

from ._util import _legacy

__all__ = ["Array"]

NDArrayLike = Any


@_legacy(
    replaced_by="zarr.Array (lazy default) + array.eager[...] escape hatch",
    migration="Indexing is lazy by default in 4.0.0; use array.eager[...] for immediate materialization.",
)
class Array:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.Array` lazy default + `array.eager[...]` escape hatch
        **Migration:** Indexing is lazy by default in 4.0.0; use array.eager[...] for immediate materialization.

    Array whose ``__getitem__`` eagerly materializes a NumPy result.

    Real 3.x location: `zarr.core.array.Array`
    Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
    """

    def __getitem__(self, selection: Any) -> NDArrayLike:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** lazy indexing + `array.eager[...]`
            **Migration:** Use array.eager[selection] to keep eager materialization.

        Eagerly read ``selection`` and return it as a NumPy array.

        Real 3.x location: `zarr.core.array.Array.__getitem__`
        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    def __setitem__(self, selection: Any, value: NDArrayLike) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** lazy indexing + `array.eager[...]`
            **Migration:** Use array.eager[selection] = value to keep eager writes.

        Write ``value`` into ``selection``.

        Real 3.x location: `zarr.core.array.Array.__setitem__`
        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...
