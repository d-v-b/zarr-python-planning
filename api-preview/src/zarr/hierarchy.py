"""Typed hierarchy verbs forming the engine boundary for Zarr-Python v4.

These functions are the typed verbs that constitute the boundary between the
user-facing API and the engine layer. Every synchronous verb defined here has
an ``_async`` counterpart with the same parameters; to keep this surface
readable only a representative subset of the async variants is shown.

Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from zarr.codec import Codec
    from zarr.metadata import (
        ArrayMetadata,
        ConsolidatedMetadata,
        GroupMetadata,
        Selection,
    )
    from zarr.store import Store

# Array-like buffer alias with no canonical owner; referenced by bare name in
# annotations so this stub imports against the standard library alone.
NDArrayLike = Any  # owned elsewhere (array-like buffer)

__all__ = [
    "read_array_metadata",
    "write_array_metadata",
    "read_group_metadata",
    "write_group_metadata",
    "read_consolidated_metadata",
    "list_children",
    "node_exists",
    "node_kind",
    "walk_hierarchy",
    "delete_node",
    "chunk_exists",
    "chunk_byte_range",
    "read_chunk",
    "write_chunk",
    "read_selection",
    "write_selection",
    "create_for_regions",
    "write_region",
    "resize",
    "append",
    "read_array_metadata_async",
    "read_chunk_async",
    "write_chunk_async",
    "read_selection_async",
    "write_selection_async",
]


def read_array_metadata(store: Store, path: str) -> ArrayMetadata:
    """Read array metadata at ``path`` from ``store``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def write_array_metadata(store: Store, path: str, metadata: ArrayMetadata) -> None:
    """Write array ``metadata`` to ``path`` in ``store``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def read_group_metadata(store: Store, path: str) -> GroupMetadata:
    """Read group metadata at ``path`` from ``store``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def write_group_metadata(store: Store, path: str, metadata: GroupMetadata) -> None:
    """Write group ``metadata`` to ``path`` in ``store``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def read_consolidated_metadata(store: Store, path: str) -> ConsolidatedMetadata | None:
    """Read consolidated metadata at ``path``, or ``None`` if absent.

    Source: [proposals/consolidated-metadata.md](../proposals/consolidated-metadata.md)
    """
    ...


def list_children(store: Store, path: str) -> Iterator[str]:
    """Iterate the immediate child node names under ``path``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def node_exists(store: Store, path: str) -> bool:
    """Return whether a node exists at ``path``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def node_kind(store: Store, path: str) -> Literal["array", "group", "absent"]:
    """Return the kind of node at ``path``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def walk_hierarchy(store: Store, path: str) -> Iterator[str]:
    """Recursively iterate all node paths beneath ``path``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def delete_node(store: Store, path: str) -> None:
    """Delete the node at ``path`` and its contents.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def chunk_exists(store: Store, metadata: ArrayMetadata, coords: tuple[int, ...]) -> bool:
    """Return whether the chunk at grid ``coords`` exists.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def chunk_byte_range(
    store: Store, metadata: ArrayMetadata, coords: tuple[int, ...]
) -> tuple[str, int, int]:
    """Return the (key, start, stop) byte range backing a chunk.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def read_chunk(
    store: Store,
    metadata: ArrayMetadata,
    coords: tuple[int, ...],
    codecs: Sequence[Codec],
    selection: Selection | None = None,
) -> NDArrayLike:
    """Read and decode a single chunk, optionally a sub-``selection`` of it.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def write_chunk(
    store: Store,
    metadata: ArrayMetadata,
    coords: tuple[int, ...],
    data: NDArrayLike,
    codecs: Sequence[Codec],
) -> None:
    """Encode and write a single chunk.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def read_selection(
    store: Store,
    metadata: ArrayMetadata,
    selection: Selection,
    codecs: Sequence[Codec],
) -> NDArrayLike:
    """Read and decode an arbitrary ``selection`` across chunks.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def write_selection(
    store: Store,
    metadata: ArrayMetadata,
    selection: Selection,
    data: NDArrayLike,
    codecs: Sequence[Codec],
) -> None:
    """Encode and write ``data`` to an arbitrary ``selection``.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


def create_for_regions(
    store: Store,
    path: str,
    metadata: ArrayMetadata,
    regions: Sequence[Any],
) -> list[Any]:
    """Initialize an array for coordinated writes over the given ``regions``.

    Source: coordinated-writes.md (inferred)
    """
    ...


def write_region(
    store: Store,
    metadata: ArrayMetadata,
    data: NDArrayLike,
    region: tuple[Any, ...] | str,
    codecs: Sequence[Codec],
) -> None:
    """Write ``data`` to a single coordinated-write ``region``.

    Source: coordinated-writes.md
    """
    ...


def resize(store: Store, path: str, new_shape: tuple[int, ...]) -> None:
    """Resize the array at ``path`` to ``new_shape``.

    Source: coordinated-writes.md
    """
    ...


def append(
    store: Store,
    path: str,
    data: NDArrayLike,
    axis: int = 0,
    *,
    codecs: Sequence[Codec] | None = None,
) -> None:
    """Append ``data`` to the array at ``path`` along ``axis``.

    Source: coordinated-writes.md
    """
    ...


async def read_array_metadata_async(store: Store, path: str) -> ArrayMetadata:
    """Async counterpart of :func:`read_array_metadata`.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


async def read_chunk_async(
    store: Store,
    metadata: ArrayMetadata,
    coords: tuple[int, ...],
    codecs: Sequence[Codec],
    selection: Selection | None = None,
) -> NDArrayLike:
    """Async counterpart of :func:`read_chunk`.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


async def write_chunk_async(
    store: Store,
    metadata: ArrayMetadata,
    coords: tuple[int, ...],
    data: NDArrayLike,
    codecs: Sequence[Codec],
) -> None:
    """Async counterpart of :func:`write_chunk`.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


async def read_selection_async(
    store: Store,
    metadata: ArrayMetadata,
    selection: Selection,
    codecs: Sequence[Codec],
) -> NDArrayLike:
    """Async counterpart of :func:`read_selection`.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...


async def write_selection_async(
    store: Store,
    metadata: ArrayMetadata,
    selection: Selection,
    data: NDArrayLike,
    codecs: Sequence[Codec],
) -> None:
    """Async counterpart of :func:`write_selection`.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """
    ...
