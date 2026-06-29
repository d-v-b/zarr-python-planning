"""Array API surface for Zarr-Python v4 (projected final state).

Non-functional stubs: signatures and docstrings only. Annotations are strings at
runtime; types owned elsewhere (ArrayMetadata, Store, DType, Metrics, etc.) are
referenced by bare name without importing.

Sources: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md), [proposals/gpu.md](../proposals/gpu.md), [proposals/observability.md](../proposals/observability.md),
proposals/coordinated-writes.md, proposals/missing-apis.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from collections.abc import Hashable, Iterator

if TYPE_CHECKING:
    from zarr.dtype import DType
    from zarr.group import Group
    from zarr.metadata import ArrayMetadata, Selection
    from zarr.observability import Metrics
    from zarr.store import Store

__all__ = [
    "Array",
]

# Module-local alias for an array-like input that has no canonical owner;
# referenced by bare name in annotations so the module imports under the stdlib
# alone.
NDArrayLike = Any


class _LazyIndexer:
    """Lazy indexing accessor returned by ``Array.lazy``.

    Indexing builds a lazy ``Array`` view; no IO is performed until the view is
    materialized (e.g. via ``compute``/``to_numpy``).

    Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
    """

    def __getitem__(self, selection: Selection) -> Array:
        """Build a lazy ``Array`` view for ``selection`` without performing IO.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    def __setitem__(self, selection: Selection, value: NDArrayLike) -> None:
        """Schedule a write of ``value`` into ``selection`` (deferred).

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...


class _EagerIndexer:
    """Eager indexing accessor returned by ``Array.eager``.

    Indexing forces an immediate read and returns a NumPy/array-like result.

    Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
    """

    def __getitem__(self, selection: Selection) -> NDArrayLike:
        """Read ``selection`` immediately and return an array-like result.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    def __setitem__(self, selection: Selection, value: NDArrayLike) -> None:
        """Write ``value`` into ``selection`` immediately.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...


class Array:
    """A Zarr array: a chunked, typed n-dimensional array backed by a store.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """

    @property
    def shape(self) -> tuple[int, ...]:
        """The shape of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def dtype(self) -> DType:
        """The data type of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def chunks(self) -> tuple[int, ...]:
        """The chunk shape of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def metadata(self) -> ArrayMetadata:
        """The array metadata document.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def attrs(self) -> dict[str, Any]:
        """The user-defined attributes of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def device(self) -> Any:
        """The Array-API device on which array data resides.

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    @property
    def nchunks(self) -> int:
        """The total number of chunks in the array.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...

    @property
    def nshards(self) -> int | None:
        """The total number of shards, or ``None`` if the array is not sharded.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...

    @property
    def n_inner_chunks(self) -> int | None:
        """The number of inner chunks per shard, or ``None`` if not sharded.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...

    @property
    def metrics(self) -> Metrics:
        """Accumulated observability metrics for this array.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    @property
    def name(self) -> str:
        """The node name (final path component) of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def path(self) -> str:
        """The full path of the array within its store hierarchy.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def ndim(self) -> int:
        """The number of dimensions of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def size(self) -> int:
        """The total number of elements in the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __getitem__(self, selection: Selection) -> Any:
        """Index the array.

        The eager-vs-lazy default at this bare-``__getitem__`` surface is a
        documented OPEN DECISION POINT in the v4 plan: it flips to lazy only if
        Array-API conformance at this surface is a hard requirement; otherwise the
        eager default stays. Use ``.lazy[...]`` or ``.eager[...]`` for an explicit,
        stable choice.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    def __setitem__(self, selection: Selection, value: NDArrayLike) -> None:
        """Write ``value`` into ``selection``.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    @property
    def lazy(self) -> _LazyIndexer:
        """Return the lazy indexing accessor (builds views, defers IO).

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    @property
    def eager(self) -> _EagerIndexer:
        """Return the eager indexing accessor (forces immediate reads).

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    def compute(self) -> NDArrayLike:
        """Materialize a lazy view into a concrete array-like result.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
        """
        ...

    def to_numpy(self) -> NDArrayLike:
        """Materialize a lazy view into a NumPy array.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md) (inferred)
        """
        ...

    def to_device(self, namespace: str) -> Any:
        """Materialize a lazy view onto the device of the given Array-API namespace.

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def read(self) -> NDArrayLike:
        """Read and materialize a lazy view.

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md) (inferred)
        """
        ...

    def __array_namespace__(self, *, api_version: str | None = None) -> Any:
        """Return the Array-API namespace for this array.

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def __array__(self, dtype: Any = None) -> NDArrayLike:
        """Return a NumPy array representation (Array-API/NumPy protocol).

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def __add__(self, other: Any) -> Array:
        """Element-wise addition (read-only Array-API conformance).

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def __sub__(self, other: Any) -> Array:
        """Element-wise subtraction (read-only Array-API conformance).

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def __mul__(self, other: Any) -> Array:
        """Element-wise multiplication (read-only Array-API conformance).

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def __matmul__(self, other: Any) -> Array:
        """Matrix multiplication (read-only Array-API conformance).

        Source: [proposals/gpu.md](../proposals/gpu.md) (inferred)
        """
        ...

    def __truediv__(self, name: str) -> Array | Group:
        """Hierarchy traversal: ``root / "a" / "b"``.

        Note: ``/`` is reserved for path traversal, not arithmetic division.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
        """
        ...

    def write_region(self, data: NDArrayLike, region: tuple[Any, ...] | str) -> None:
        """Write ``data`` into an aligned region of the array.

        Source: [proposals/coordinated-writes.md](../proposals/coordinated-writes.md)
        """
        ...

    def resize(self, new_shape: tuple[int, ...]) -> None:
        """Resize the array in place to ``new_shape``.

        Source: [proposals/coordinated-writes.md](../proposals/coordinated-writes.md)
        """
        ...

    def append(self, data: NDArrayLike, axis: int = 0) -> None:
        """Append ``data`` along ``axis``, growing the array.

        Source: [proposals/coordinated-writes.md](../proposals/coordinated-writes.md)
        """
        ...

    def chunk_exists(self, coords: tuple[int, ...]) -> bool:
        """Return whether the chunk at ``coords`` exists in storage.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    def chunk_byte_range(self, coords: tuple[int, ...]) -> tuple[str, int, int]:
        """Return the ``(key, start, length)`` byte range backing a chunk.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    def read_block(self, coords: tuple[int, ...]) -> bytes:
        """Read the raw, encoded bytes of the chunk at ``coords``.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    def write_block(self, coords: tuple[int, ...], data: bytes) -> None:
        """Write raw, encoded bytes for the chunk at ``coords``.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    def storage_size(self) -> int:
        """Return the total stored (encoded) size of the array in bytes.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    def iter_chunk_coords(self) -> Iterator[tuple[int, ...]]:
        """Iterate over the grid coordinates of all chunks.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...

    def with_caching(
        self,
        *,
        metadata: bool = True,
        chunks: bool | str = False,
        negative: bool = False,
    ) -> Array:
        """Return a view of this array with the given caching behavior enabled.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...

    def __repr__(self) -> str:
        """Return a concise text representation of the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def _repr_html_(self) -> str:
        """Return a rich HTML representation for notebook display.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def tree(self, *, meta: bool = True) -> str:
        """Return a tree rendering of the array (and optionally its metadata).

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __enter__(self) -> Array:
        """Enter a context manager scope for the array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __exit__(self, *exc: object) -> None:
        """Exit the context manager scope, releasing resources.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __dask_tokenize__(self) -> Hashable:
        """Return a deterministic token identifying this array for Dask.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def copy(self, dst_store: Store, name: str) -> Array:
        """Copy this array to ``name`` in ``dst_store`` and return the new array.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    # ------------------------------------------------------------------ #
    # Async twins.
    #
    # There is no separate ``AsyncArray`` class: a single ``Array`` holds all
    # the code, and async is exposed *selectively* via ``*_async`` methods on
    # only the IO-bound operations that benefit from async concurrency. The
    # fast, in-memory operations (``shape``, ``dtype``, indexing math, reprs)
    # stay pure-sync and never touch an event loop, so they pay no async
    # scheduling overhead.
    #
    # Source: proposals/functional-core.md (single-class direction), and the
    # discussion on zarr-developers/zarr-python#4049.
    # ------------------------------------------------------------------ #
    async def getitem_async(self, selection: Selection) -> NDArrayLike:
        """Awaitable variant of :meth:`__getitem__` (read).

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md) (inferred)
        """
        ...

    async def setitem_async(self, selection: Selection, value: NDArrayLike) -> None:
        """Awaitable variant of :meth:`__setitem__` (write).

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md) (inferred)
        """
        ...

    async def compute_async(self) -> NDArrayLike:
        """Awaitable variant of :meth:`compute` (lazy-view materialization).

        Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md) (inferred)
        """
        ...

    async def write_region_async(
        self, data: NDArrayLike, region: tuple[Any, ...] | str
    ) -> None:
        """Awaitable variant of :meth:`write_region`.

        Source: [proposals/coordinated-writes.md](../proposals/coordinated-writes.md) (inferred)
        """
        ...

    async def resize_async(self, new_shape: tuple[int, ...]) -> None:
        """Awaitable variant of :meth:`resize`.

        Source: [proposals/coordinated-writes.md](../proposals/coordinated-writes.md) (inferred)
        """
        ...

    async def append_async(self, data: NDArrayLike, axis: int = 0) -> None:
        """Awaitable variant of :meth:`append`.

        Source: [proposals/coordinated-writes.md](../proposals/coordinated-writes.md) (inferred)
        """
        ...

    async def read_block_async(self, coords: tuple[int, ...]) -> bytes:
        """Awaitable variant of :meth:`read_block`.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...

    async def write_block_async(self, coords: tuple[int, ...], data: bytes) -> None:
        """Awaitable variant of :meth:`write_block`.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...

    async def storage_size_async(self) -> int:
        """Awaitable variant of :meth:`storage_size`.

        Source: [proposals/observability.md](../proposals/observability.md) (inferred)
        """
        ...
