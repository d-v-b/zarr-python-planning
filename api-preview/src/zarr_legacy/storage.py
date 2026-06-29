"""Legacy 3.x store-path helper.

Mirrors ``zarr.storage._common.StorePath``, the ``(store, path)`` pairing used
to address a location within a store. In 4.0.0 this is replaced by the typed
``zarr.store.Prefixed[S]`` wrapper.

Real 3.x location: ``zarr.storage._common``
Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
"""

from __future__ import annotations

from typing import Any

from ._util import _legacy

__all__ = ["StorePath"]

Buffer = Any


@_legacy(
    replaced_by="zarr.store.Prefixed",
    migration="Use zarr.store.Prefixed[S] to bind a store to a key prefix.",
)
class StorePath:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store.Prefixed`
        **Migration:** Use zarr.store.Prefixed[S] to bind a store to a key prefix.

    A store paired with a key prefix that addresses a location within it.

    Real 3.x location: `zarr.storage._common.StorePath`
    Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
    """

    def __init__(self, store: Any, path: str = "") -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Prefixed`
            **Migration:** Construct a zarr.store.Prefixed[S] instead.

        Bind ``store`` to a key ``path`` prefix.

        Real 3.x location: `zarr.storage._common.StorePath.__init__`
        Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
        """
        ...

    def __truediv__(self, other: str) -> StorePath:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Prefixed`
            **Migration:** Extend a Prefixed prefix instead.

        Return a new ``StorePath`` with ``other`` appended to the prefix.

        Real 3.x location: `zarr.storage._common.StorePath.__truediv__`
        Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
        """
        ...

    async def get(self, prototype: Any = None, byte_range: Any = None) -> Buffer | None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Prefixed`
            **Migration:** Read through the Prefixed wrapper's store protocols.

        Read the value at this path.

        Real 3.x location: `zarr.storage._common.StorePath.get`
        Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
        """
        ...

    async def set(self, value: Buffer) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Prefixed`
            **Migration:** Write through the Prefixed wrapper's store protocols.

        Write ``value`` at this path.

        Real 3.x location: `zarr.storage._common.StorePath.set`
        Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
        """
        ...

    def __eq__(self, other: object) -> bool:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Prefixed`
            **Migration:** Compare Prefixed instances instead.

        Return whether two ``StorePath`` objects address the same location.

        Real 3.x location: `zarr.storage._common.StorePath.__eq__`
        Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
        """
        ...

    def __str__(self) -> str:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Prefixed`
            **Migration:** Render a Prefixed instance instead.

        Return a human-readable representation of this path.

        Real 3.x location: `zarr.storage._common.StorePath.__str__`
        Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
        """
        ...
