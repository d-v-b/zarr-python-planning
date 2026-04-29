# Proposed Public API: Stores

This document is a scaffolding for the store-layer redesign described in the [Stores section of the planning README](../README.md#stores). The intent is to make the shape of the proposal concrete enough to argue about. Names, module layout, and exact signatures are all up for revision; the load-bearing claims are:

1. Capabilities are protocols, not subclasses.
2. Backend stores compose those protocols.
3. Wrappers preserve the protocol surface of the store they wrap.
4. Sync is the default; async is an opt-in protocol family, not a baked-in assumption.
5. Path handling is verbatim with an opt-in validator; backend-specific stores can enforce stricter constraints internally.

This is a 4.0-shaped sketch. The migration story at the end describes how to get from today's `Store` ABC to this design without an abrupt break.

## Capability protocols

```python
# zarr/storage/protocols.py
#
# Capability protocols. Backends declare which they implement.
# Async variants live in the same module with `Async` prefix and use the
# same method names; runtime-checkable so `isinstance(store, GetRange)`
# works for callers that need to probe. Most callers should use static
# typing (`def f(store: Get & GetRange) -> ...`) and let the type checker
# enforce capability requirements.

from typing import Protocol, runtime_checkable
from collections.abc import Iterator, Sequence

@runtime_checkable
class Get(Protocol):
    def get(self, key: str) -> bytes: ...

@runtime_checkable
class GetRange(Protocol):
    def get_range(self, key: str, *, start: int, length: int | None = None) -> bytes: ...

@runtime_checkable
class GetRanges(Protocol):
    """Batch range read. Backends that support this natively (S3 cat_ranges,
    obstore get_ranges) advertise it; a `RangeCoalescing` wrapper synthesizes
    it for backends that only have `GetRange`."""
    def get_ranges(self, key: str, *, ranges: Sequence[tuple[int, int | None]]) -> Sequence[bytes]: ...

@runtime_checkable
class Put(Protocol):
    def put(self, key: str, value: bytes) -> None: ...

@runtime_checkable
class Delete(Protocol):
    def delete(self, key: str) -> None: ...

@runtime_checkable
class List(Protocol):
    def list(self, prefix: str = "") -> Iterator[str]: ...

@runtime_checkable
class Head(Protocol):
    def head(self, key: str) -> "ObjectMetadata": ...

@runtime_checkable
class Copy(Protocol):
    def copy(self, src: str, dst: str) -> None: ...

@runtime_checkable
class Transactional(Protocol):
    def transaction(self) -> "TransactionContext": ...

# Async variants (AsyncGet, AsyncGetRange, AsyncPut, ...) follow the same
# shape with `async def`. Backends pick whichever flavor matches their
# underlying I/O model; the sync/async bridge is a wrapper, not a subclass.
```

## Path helpers

```python
# zarr/storage/path.py
#
# The path-join helpers for backends that need them. Stores are not
# required to use these; backend-specific stores can implement their own
# join logic. The verbatim-contract helper exists for the generic
# FsspecStore fallback.

def dereference_path(root: str, key: str) -> str:
    """Combine a backend-side root with a key. Strips trailing slash from
    root, returns bare key when root is empty (the `/` sentinel collapses
    so bare-key backends like ReferenceFileSystem work). No other
    normalization is applied. Backend-specific path validation is the
    caller's responsibility."""
    root = root.rstrip("/")
    return (f"{root}/{key}" if root else key).rstrip("/")

def relativize_path(*, path: str, prefix: str) -> str:
    """Inverse of `dereference_path` for listing return values. Strips a
    `prefix/` from `path` if present."""
```

## Backend stores

### `LocalStore`

```python
# zarr/storage/stores/local.py

class LocalStore:
    """Filesystem-backed store. Synchronous; implements Get, GetRange,
    GetRanges, Put, Delete, List, Head, Copy, Transactional (via
    rename-into-place)."""

    def __init__(self, root: Path | str, *, mkdir: bool = False) -> None: ...
    def get(self, key: str) -> bytes: ...
    def get_range(self, key: str, *, start: int, length: int | None = None) -> bytes: ...
    def get_ranges(self, key: str, *, ranges: Sequence[tuple[int, int | None]]) -> Sequence[bytes]: ...
    def put(self, key: str, value: bytes) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self, prefix: str = "") -> Iterator[str]: ...
    def head(self, key: str) -> ObjectMetadata: ...
    def copy(self, src: str, dst: str) -> None: ...
    def transaction(self) -> TransactionContext: ...
```

### `MemoryStore`

```python
# zarr/storage/stores/memory.py

class MemoryStore:
    """In-process dict-backed store. Synchronous; implements all sync
    capabilities. Cheap to construct and clone."""

    def __init__(self, *, name: str | None = None) -> None: ...
    # full sync capability set
```

### `ObstoreStore`

```python
# zarr/storage/stores/obstore.py

class ObstoreStore:
    """Wraps an obstore object store. Async; implements the full async
    capability set. Path validation is enforced by the underlying obstore
    type (S3Store, GCSStore, AzureStore, HTTPStore) at construction."""

    def __init__(self, store: "obstore.store.ObjectStore") -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def get_range(self, key: str, *, start: int, length: int | None = None) -> bytes: ...
    async def get_ranges(self, key: str, *, ranges: Sequence[tuple[int, int | None]]) -> Sequence[bytes]: ...
    # async capability set
```

### `FsspecStore`

```python
# zarr/storage/stores/fsspec.py

class FsspecStore:
    """Generic fsspec fallback. Used when no backend-specific store
    exists. Stores `path` verbatim and joins with keys via
    `dereference_path` at I/O time. No construction-time normalization
    is applied; pass `validate_path` to enforce backend-specific
    constraints (e.g. rejecting `..`, normalizing backslashes,
    requiring leading `/` for MemoryFileSystem, etc.).

    For S3/GCS/Azure/HTTP, prefer `ObstoreStore`."""

    def __init__(
        self,
        fs: "fsspec.asyn.AsyncFileSystem",
        path: str = "/",
        *,
        validate_path: Callable[[str], None] | None = None,
        read_only: bool = False,
        allowed_exceptions: tuple[type[Exception], ...] = (FileNotFoundError, IsADirectoryError, NotADirectoryError),
    ) -> None: ...

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "FsspecStore": ...
    @classmethod
    def from_upath(cls, upath: "UPath", **kwargs) -> "FsspecStore": ...

    async def get(self, key: str) -> bytes: ...
    # async capability set, all join sites use dereference_path
```

## Wrappers

```python
# zarr/storage/wrappers.py
#
# Wrappers preserve the protocol surface of the store they wrap. The
# generic parameter S carries through so a Caching[LocalStore]
# advertises everything LocalStore does. Static typing ensures wrappers
# composed in any order still satisfy the capabilities the caller needs.

class ReadOnly[S]:
    """Strips Put, Delete, Copy, Transactional from S's capability set."""
    def __init__(self, inner: S) -> None: ...

class Caching[S]:
    """Adds an in-memory LRU over S's read capabilities. Eviction by
    bytes or entries; optional TTL. Writes invalidate the cache."""
    def __init__(
        self,
        inner: S,
        *,
        max_bytes: int | None = None,
        max_entries: int | None = None,
        ttl: float | None = None,
    ) -> None: ...

class RangeCoalescing[S]:
    """Synthesizes `GetRanges` for stores that only implement `GetRange`.
    Coalesces ranges within `max_gap` bytes into single requests up to
    `max_request` bytes. No-op if S already implements `GetRanges`."""
    def __init__(
        self,
        inner: S,
        *,
        max_gap: int = 1024,
        max_request: int = 16 * 1024 * 1024,
    ) -> None: ...

class Tracing[S]:
    """Wraps every method in an OpenTelemetry span (or whatever tracer
    is supplied). Zero-cost if no tracer is set."""
    def __init__(self, inner: S, *, tracer: "Tracer | None" = None) -> None: ...

class Retry[S]:
    """Retries transient failures with exponential backoff. The set of
    retryable exceptions is configurable per backend."""
    def __init__(
        self,
        inner: S,
        *,
        max_attempts: int = 3,
        retry_on: tuple[type[Exception], ...] = (TimeoutError,),
    ) -> None: ...

class SyncToAsync[S]:
    """Adapts a sync store to advertise async protocols by running each
    call in a thread pool. The inverse `AsyncToSync` exists for the
    other direction."""
    def __init__(self, inner: S, *, executor: "Executor | None" = None) -> None: ...
```

## Transactions

```python
# zarr/storage/transactions.py

class TransactionContext(Protocol):
    """Returned by `Transactional.transaction()`. Use as a context
    manager; commit on `__exit__` if no exception, abort on exception.
    Restores V2's atomic rename-into-place semantics for backends that
    support it; backends that do not (S3, in-memory) get a best-effort
    write-batching emulation that is documented as non-atomic."""

    def commit(self) -> None: ...
    def abort(self) -> None: ...
    def __enter__(self) -> "TransactionContext": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool: ...
```

## Usage examples

```python
# 1) A user that just wants to read a Zarr group from S3:
from zarr.storage.stores.obstore import ObstoreStore
from obstore.store import S3Store

store = ObstoreStore(S3Store(bucket="my-bucket", region="us-east-1"))
# store satisfies AsyncGet, AsyncGetRange, AsyncGetRanges, AsyncList, ...
# typing-time check: zarr.open_group(store) requires AsyncGet & AsyncList

# 2) A user that wants caching + range coalescing on top of a local store:
from zarr.storage.stores.local import LocalStore
from zarr.storage.wrappers import Caching, RangeCoalescing

store = RangeCoalescing(Caching(LocalStore("/data/array.zarr"), max_bytes=1 << 30))
# Capability set is preserved; both wrappers are no-ops for capabilities
# they do not modify.

# 3) A user with a custom fsspec backend that wants `..`-rejection:
from zarr.storage.stores.fsspec import FsspecStore

def reject_traversal(path: str) -> None:
    if any(seg in {".", ".."} for seg in path.split("/")):
        raise ValueError(f"path {path!r} contains traversal segments")

store = FsspecStore(my_fs, path="data", validate_path=reject_traversal)

# 4) Read-only view of any store:
from zarr.storage.wrappers import ReadOnly
ro = ReadOnly(store)
# ro: Get & GetRange & List & Head, but not Put/Delete/Copy/Transactional
```

## Migration shims and deprecation surface

The above is a 4.0 design. To get there without an abrupt break, the public-facing migration plan should be:

- **Keep `Store` as a typing alias for the union of common capabilities** during the deprecation window. Code that currently writes `store: Store` continues to type-check.
- **`FsspecStore`, `LocalStore`, `MemoryStore`, `ObstoreStore` keep their current names** and grow toward the proposed shapes incrementally. The biggest user-visible delta is that `prototype` arguments move to construction-time configuration and most methods become sync by default.
- **Wrappers are additive.** Shipping `Caching`, `RangeCoalescing`, etc. does not require removing anything.
- **Capability protocols ship first**, before any breaking changes to existing stores. This lets downstream libraries (xarray, dask, virtualizarr) adopt protocol-based typing on their side ahead of the 4.0 cutover.
- **The `experimental.cache_store` module retires** in favor of the `Caching` wrapper, with a deprecation warning that points at the new API.

The migration story for `FsspecStore` specifically is the smallest delta in the proposal: the existing class keeps the same constructor signature, gains a `validate_path` keyword argument with default `None`, and documents the verbatim-path contract. Everything else in the FsspecStore section is unchanged.

## Open questions

- **Async naming.** Two protocol classes per capability (`Get` and `AsyncGet`) doubles the surface area. Alternatives: a single `Get` whose method may be async (caller awaits as needed), or a generic `Get[Sync]` / `Get[Async]`. Each has type-system tradeoffs.
- **Capability intersection types.** Python's `Protocol` does not yet support `&` (intersection) cleanly across all type checkers. The usage examples assume PEP-695-style type expressions. May need to fall back to explicit `Protocol`-merging classes (`class ReadCapable(Get, GetRange, List, Head, Protocol): ...`).
- **`Transactional` granularity.** A single `transaction()` method may not be enough; some backends want explicit lock acquisition, optimistic concurrency, or multi-store coordination. The Icechunk model is more complete here and may inform the final shape.
- **Backwards compatibility window.** How long does the `Store` ABC remain importable? One major release? Two? Affects how aggressively wrappers can replace inheritance-based extension.
- **`prototype` semantics.** Currently a per-call argument that almost no caller uses meaningfully. Moving it to construction-time configuration is the proposal, but downstream callers that do use it (GPU buffer allocation in particular) need a migration path that does not lose the device-aware behavior.
