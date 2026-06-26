"""Concrete store backends for the Zarr v4 store layer.

Source: [proposals/stores.md](../proposals/stores.md)

Each backend implements a subset of the capability protocols in
:mod:`zarr.store.protocols` against a particular storage substrate (local
filesystem, in-memory dict, ZIP archive, fsspec filesystem, or obstore object
store). Backends are composed with the wrappers in :mod:`zarr.store.wrappers`
to add caching, retries, tracing, and sync/async adaptation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fsspec.asyn import AsyncFileSystem
    from obstore.store import ObjectStore

    from zarr.store.types import KeyRange
    from zarr.store.wrappers import Caching, CachingAsync

__all__ = [
    "LocalStore",
    "MemoryStore",
    "ZipStore",
    "FsspecStore",
    "ObstoreStore",
]


class LocalStore:
    """A store backed by a directory on the local filesystem.

    Source: [proposals/stores.md](../proposals/stores.md)

    Capabilities: Get, GetRange, GetRanges, Put, Delete, List,
    ListWithDelimiter, Head, Copy, Serializable, ThreadSafe, plus the
    corresponding streaming reads. Keys map to paths under ``root``/``prefix``.
    """

    def __init__(
        self,
        root: Path | str,
        prefix: str = "",
        *,
        bounds: KeyRange | None = None,
        mkdir: bool = False,
    ) -> None:
        """Open a local store rooted at ``root`` (optionally under ``prefix``).

        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @property
    def bounds(self) -> KeyRange:
        """The key range this store is restricted to.

        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    def __truediv__(self, sub: str) -> LocalStore:
        """Return a sub-store scoped beneath ``sub``.

        Source: [proposals/stores.md](../proposals/stores.md) (inferred)
        """
        ...

    def with_caching(self, **kwargs: Any) -> Caching[LocalStore]:
        """Wrap this store in a synchronous caching layer.

        Source: [proposals/stores-caching.md](../proposals/stores-caching.md) (inferred)
        """
        ...


class MemoryStore:
    """A store backed by an in-process mapping.

    Source: [proposals/stores.md](../proposals/stores.md)

    Capabilities: Get, GetRange, GetRanges, Put, Delete, List,
    ListWithDelimiter, Head, Copy, Serializable, ThreadSafe. Primarily useful
    for testing and ephemeral hierarchies.
    """

    def __init__(self) -> None:
        """Create an empty in-memory store.

        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    def with_caching(self, **kwargs: Any) -> Caching[MemoryStore]:
        """Wrap this store in a synchronous caching layer.

        Source: [proposals/stores-caching.md](../proposals/stores-caching.md) (inferred)
        """
        ...


class ZipStore:
    """A store backed by a ZIP archive.

    Source: [proposals/stores.md](../proposals/stores.md)

    Capabilities: Get, GetRange, List, ListWithDelimiter, Head (read mode);
    Put when opened for writing. May be constructed from a path or a file-like
    object (for example :class:`io.BytesIO`). Acts as both a sync and async
    context manager.
    """

    def __init__(self, path: str | Path, mode: str = "r") -> None:
        """Open a ZIP-backed store at ``path`` in the given ``mode``.

        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    def flush(self) -> None:
        """Flush pending writes to the underlying archive.

        Source: missing-apis.md (inferred)
        """
        ...

    def reopen(self) -> None:
        """Reopen the archive, for example to switch from write to read mode.

        Source: missing-apis.md (inferred)
        """
        ...

    def __enter__(self) -> ZipStore:
        """Enter the store context.

        Source: [proposals/stores.md](../proposals/stores.md) (inferred)
        """
        ...

    def __exit__(self, *exc: object) -> None:
        """Exit the store context, flushing and closing the archive.

        Source: [proposals/stores.md](../proposals/stores.md) (inferred)
        """
        ...

    async def __aenter__(self) -> ZipStore:
        """Enter the async store context.

        Source: [proposals/stores.md](../proposals/stores.md) (inferred)
        """
        ...

    async def __aexit__(self, *exc: object) -> None:
        """Exit the async store context, flushing and closing the archive.

        Source: [proposals/stores.md](../proposals/stores.md) (inferred)
        """
        ...


class FsspecStore:
    """A store backed by an fsspec ``AsyncFileSystem``.

    Source: [proposals/stores.md](../proposals/stores.md)

    Capabilities: Get, GetRange, GetRanges, Put, Delete, List,
    ListWithDelimiter, Head, plus their async counterparts. Bridges the broad
    range of fsspec filesystem implementations into the capability model.
    """

    def __init__(
        self,
        fs: AsyncFileSystem,
        path: str = "",
        *,
        validate_path: Callable[[str], None] | None = None,
        bounds: KeyRange | None = None,
    ) -> None:
        """Open a store over the fsspec filesystem ``fs`` rooted at ``path``.

        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    def with_caching(self, **kwargs: Any) -> Caching[FsspecStore]:
        """Wrap this store in a caching layer.

        Source: [proposals/stores-caching.md](../proposals/stores-caching.md) (inferred)
        """
        ...


class ObstoreStore:
    """A store backed by an obstore ``ObjectStore``.

    Source: [proposals/stores.md](../proposals/stores.md)

    Async-family only. Capabilities: GetAsync, GetRangeAsync, GetRangesAsync,
    PutAsync, DeleteAsync, ListAsync, ListWithDelimiterAsync, HeadAsync,
    CopyAsync, plus async streaming reads. Wraps the Rust-backed obstore client
    for high-throughput object-store access.
    """

    def __init__(self, store: ObjectStore) -> None:
        """Open a store delegating to the obstore ``ObjectStore``.

        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    def with_caching_async(self, **kwargs: Any) -> CachingAsync[ObstoreStore]:
        """Wrap this store in an asynchronous caching layer.

        Source: [proposals/stores-caching.md](../proposals/stores-caching.md) (inferred)
        """
        ...
