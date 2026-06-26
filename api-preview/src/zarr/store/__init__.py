"""The redesigned Zarr-Python v4 store layer.

Source: [proposals/stores.md](../proposals/stores.md)

This package replaces the monolithic ``Store`` abstract base class of earlier
Zarr-Python versions with a capability-protocol design. Instead of inheriting
from one base, a store advertises exactly the operations it supports as a set of
small structural protocols (:mod:`zarr.store.protocols`) -- ``Get``, ``Put``,
``List``, and so on -- and consumers depend only on the narrow protocols they
actually use.

Every capability comes in two parallel families: a synchronous form and an
``_async``-suffixed asynchronous form with an otherwise identical signature.
Backends implement whichever family is natural for their substrate
(:class:`ObstoreStore` is async-only, for example), and the adapter wrappers
:class:`SyncToAsync` / :class:`AsyncToSync` bridge between the two families.

Cross-cutting behaviors are added by composable, generic wrappers
(:mod:`zarr.store.wrappers`) -- caching, retries, tracing, range coalescing,
prefixing, and routing -- which wrap an inner store while forwarding its
capabilities. Concrete backends live in :mod:`zarr.store.backends`, shared value
objects in :mod:`zarr.store.types`, and key helpers in :mod:`zarr.store.path`.

This layer maps to the standalone ``zarr-store`` package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from zarr.store.backends import (
    FsspecStore,
    LocalStore,
    MemoryStore,
    ObstoreStore,
    ZipStore,
)
from zarr.store.path import dereference_path, relativize_path
from zarr.store.protocols import (
    AsyncSafe,
    Copy,
    CopyAsync,
    Delete,
    DeleteAsync,
    Get,
    GetAsync,
    GetRange,
    GetRangeAsync,
    GetRanges,
    GetRangesAsync,
    GetRangesStreaming,
    GetRangesStreamingAsync,
    GetRangeStreaming,
    GetRangeStreamingAsync,
    GetStreaming,
    GetStreamingAsync,
    Head,
    HeadAsync,
    List,
    ListAsync,
    ListWithDelimiter,
    ListWithDelimiterAsync,
    Put,
    PutAsync,
    Serializable,
    ThreadSafe,
    Transactional,
)
from zarr.store.types import (
    AsyncReadStream,
    Generation,
    KeyRange,
    ListResult,
    ObjectMetadata,
    PutResult,
    ReadResult,
    ReadStream,
    StoreDeclaration,
    Transaction,
    TransactionFailed,
    WritableBuffer,
)
from zarr.store.wrappers import (
    AsyncToSync,
    Caching,
    CachingAsync,
    KvStack,
    Prefixed,
    RangeCoalescing,
    RangeCoalescingAsync,
    ReadOnly,
    Retry,
    SyncToAsync,
    Tracing,
)

Store: TypeAlias = Any
"""A store: any object implementing one or more of the capability protocols
(:class:`Get`, :class:`Put`, :class:`List`, ...). There is no single ``Store``
base class in v4 -- capability protocols replace the monolithic ABC.

Source: [proposals/stores.md](../proposals/stores.md)
"""

__all__ = [
    # umbrella type
    "Store",
    # types
    "Generation",
    "WritableBuffer",
    "ReadResult",
    "PutResult",
    "ListResult",
    "ObjectMetadata",
    "StoreDeclaration",
    "KeyRange",
    "ReadStream",
    "AsyncReadStream",
    "Transaction",
    "TransactionFailed",
    # protocols (sync)
    "Get",
    "GetRange",
    "GetRanges",
    "Put",
    "Delete",
    "List",
    "ListWithDelimiter",
    "Head",
    "Copy",
    "GetStreaming",
    "GetRangeStreaming",
    "GetRangesStreaming",
    "Transactional",
    "Serializable",
    # protocols (async)
    "GetAsync",
    "GetRangeAsync",
    "GetRangesAsync",
    "PutAsync",
    "DeleteAsync",
    "ListAsync",
    "ListWithDelimiterAsync",
    "HeadAsync",
    "CopyAsync",
    "GetStreamingAsync",
    "GetRangeStreamingAsync",
    "GetRangesStreamingAsync",
    # protocols (markers)
    "ThreadSafe",
    "AsyncSafe",
    # backends
    "LocalStore",
    "MemoryStore",
    "ZipStore",
    "FsspecStore",
    "ObstoreStore",
    # wrappers
    "ReadOnly",
    "Retry",
    "Tracing",
    "SyncToAsync",
    "AsyncToSync",
    "Caching",
    "CachingAsync",
    "RangeCoalescing",
    "RangeCoalescingAsync",
    "Prefixed",
    "KvStack",
    # path helpers
    "dereference_path",
    "relativize_path",
]
