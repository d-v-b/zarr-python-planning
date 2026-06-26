"""Legacy 3.x mode-taking top-level API.

Mirrors the ``mode=``-taking constructors from ``zarr.api.synchronous``. In
4.0.0 the overloaded ``mode`` parameter is removed in favor of explicit
intent-revealing constructors (``zarr.open_for_read``, ``zarr.create``,
``zarr.create_or_overwrite``, ``zarr.open_or_create``).

Real 3.x location: ``zarr.api.synchronous``
Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
"""

from __future__ import annotations

from typing import Any

from ._util import _legacy

__all__ = ["open", "open_group", "open_array", "save", "load"]

Array = Any
Group = Any


@_legacy(
    replaced_by="zarr.open_for_read / zarr.create / zarr.create_or_overwrite / zarr.open_or_create",
    migration="Pick the explicit constructor matching your intent instead of passing mode=.",
)
def open(
    store: Any = None,
    *,
    mode: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> Array | Group:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.open_for_read` / `zarr.create` / `zarr.create_or_overwrite` / `zarr.open_or_create`
        **Migration:** Pick the explicit constructor matching your intent instead of passing mode=.

    Open an array or group, dispatching on the persisted node type.

    Real 3.x location: `zarr.api.synchronous.open`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...


@_legacy(
    replaced_by="zarr.open_for_read / zarr.create / zarr.create_or_overwrite / zarr.open_or_create",
    migration="Pick the explicit constructor matching your intent instead of passing mode=.",
)
def open_group(
    store: Any = None,
    *,
    mode: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> Group:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.open_for_read` / `zarr.create` / `zarr.create_or_overwrite` / `zarr.open_or_create`
        **Migration:** Pick the explicit constructor matching your intent instead of passing mode=.

    Open a group.

    Real 3.x location: `zarr.api.synchronous.open_group`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...


@_legacy(
    replaced_by="zarr.open_for_read / zarr.create / zarr.create_or_overwrite / zarr.open_or_create",
    migration="Pick the explicit constructor matching your intent instead of passing mode=.",
)
def open_array(
    store: Any = None,
    *,
    mode: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> Array:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.open_for_read` / `zarr.create` / `zarr.create_or_overwrite` / `zarr.open_or_create`
        **Migration:** Pick the explicit constructor matching your intent instead of passing mode=.

    Open an array.

    Real 3.x location: `zarr.api.synchronous.open_array`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...


@_legacy(
    replaced_by="zarr.create_or_overwrite",
    migration="Use the explicit create_or_overwrite constructor to write arrays.",
)
def save(store: Any, *args: Any, **kwargs: Any) -> None:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.create_or_overwrite`
        **Migration:** Use the explicit create_or_overwrite constructor to write arrays.

    Save one or more arrays to ``store``.

    Real 3.x location: `zarr.api.synchronous.save`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...


@_legacy(
    replaced_by="zarr.open_for_read",
    migration="Use zarr.open_for_read to load arrays.",
)
def load(store: Any, path: str | None = None) -> Any:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.open_for_read`
        **Migration:** Use zarr.open_for_read to load arrays.

    Load array(s) from ``store``.

    Real 3.x location: `zarr.api.synchronous.load`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...
