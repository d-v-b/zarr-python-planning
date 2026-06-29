"""Legacy 3.x sync bridge.

Mirrors ``zarr.core.sync.sync``, the function that drives a coroutine to
completion on zarr's private event loop. In 4.0.0 the explicit
async-to-sync bridge moves behind ``zarr.store.AsyncToSync`` / ``zarr.to_sync``.

Real 3.x location: ``zarr.core.sync``
Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
"""

from __future__ import annotations

from asyncio import AbstractEventLoop
from collections.abc import Coroutine
from typing import Any, TypeVar

from ._util import _legacy

__all__ = ["sync"]

T = TypeVar("T")


@_legacy(
    replaced_by="zarr.store.AsyncToSync / zarr.to_sync",
    migration="Wrap async stores/objects with zarr.store.AsyncToSync or call zarr.to_sync.",
)
def sync(
    coro: Coroutine[Any, Any, T],
    loop: AbstractEventLoop | None = None,
    timeout: float | None = None,
) -> T:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store.AsyncToSync` / `zarr.to_sync`
        **Migration:** Wrap async stores/objects with zarr.store.AsyncToSync or call zarr.to_sync.

    Run a coroutine to completion on zarr's private event loop and return its result.

    Real 3.x location: `zarr.core.sync.sync`
    Source: [proposals/stores.md](../proposals/stores.md), missing-apis.md
    """
    ...
