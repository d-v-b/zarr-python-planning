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
# Capability protocols. Backends declare which they implement. Naming
# follows obspec (https://developmentseed.org/obspec/latest/) with one
# deliberate divergence: the keyspace argument is `key` (the Zarr V3
# storage spec's term) rather than obspec's `path`. Everything else
# matches obspec exactly: `Async` class suffix, `_async` method suffix,
# range methods take `start` / `end` / `length`, batch range methods
# take parallel `starts` / `ends` / `lengths`, listing splits into
# `List` and `ListWithDelimiter`. Structural compatibility with obspec
# is preserved at call sites that pass the keyspace argument positionally.
#
# Runtime-checkable so `isinstance(store, GetRange)` works for callers
# that need to probe. Most callers should use static typing
# (`def f(store: Get & GetRange) -> ...`) and let the type checker
# enforce capability requirements.

from typing import Protocol, runtime_checkable
from collections.abc import Iterator, Sequence

@runtime_checkable
class Get(Protocol):
    def get(self, key: str) -> memoryview: ...

@runtime_checkable
class GetRange(Protocol):
    def get_range(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> memoryview: ...

@runtime_checkable
class GetRanges(Protocol):
    """Batch range read. Backends that support this natively (S3 cat_ranges,
    obstore get_ranges) advertise it; a `RangeCoalescing` wrapper synthesizes
    it for backends that only have `GetRange`."""
    def get_ranges(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
    ) -> Sequence[memoryview]: ...

@runtime_checkable
class Put(Protocol):
    def put(self, key: str, value: bytes | memoryview) -> None: ...

@runtime_checkable
class Delete(Protocol):
    def delete(self, key: str) -> None: ...

@runtime_checkable
class List(Protocol):
    """Recursive listing. Mirrors obspec's `List`."""
    def list(self, prefix: str | None = None, *, offset: str | None = None) -> Iterator[str]: ...

@runtime_checkable
class ListWithDelimiter(Protocol):
    """Non-recursive listing that returns common prefixes (directory-like).
    Mirrors obspec's `ListWithDelimiter`. Replaces today's `list_dir` /
    `list_prefix` distinction."""
    def list_with_delimiter(self, prefix: str | None = None) -> "ListResult": ...

@runtime_checkable
class Head(Protocol):
    def head(self, key: str) -> "ObjectMetadata": ...

@runtime_checkable
class Copy(Protocol):
    def copy(self, src: str, dst: str) -> None: ...

@runtime_checkable
class Transactional(Protocol):
    """Multi-key atomic transactions. Backends advertise this when
    they support batching writes into an atomic commit. Per-key
    atomicity is a property of `Put` and not require this protocol.

    Algorithm, per-backend support matrix, OCC extension via
    `TransactionalOCC`, composition rules with other wrappers, and
    the test plan are in [stores-transactional.md](./stores-transactional.md)."""
    def transaction(self) -> "TransactionContext": ...

# Async variants (`GetAsync`, `GetRangeAsync`, `GetRangesAsync`, `PutAsync`,
# `DeleteAsync`, `ListAsync`, `ListWithDelimiterAsync`, `HeadAsync`,
# `CopyAsync`) follow the same shape with `async def` and an `_async`
# method-name suffix. Backends pick whichever flavor matches their
# underlying I/O model; the sync/async bridge is a wrapper, not a subclass.
# See the README's sync-by-default subsection for the per-backend mapping.
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

## Path ownership and Prefixed wrapper

```python
# zarr/storage/prefixed.py
#
# Replaces today's `StorePath`. A `Prefixed[S]` wrapper fixes an
# additional prefix on every key passed through to S, while preserving
# the capability surface of S. Hierarchy traversal (today's
# StorePath.__truediv__) becomes Prefixed.__truediv__. Equality, hashing,
# and pickling are uniform via composition with the inner store.

class Prefixed[S]:
    """Capability-preserving wrapper that joins a fixed prefix with every
    key passed to S. Replaces today's `StorePath` as the type carried by
    `Array.store` and `Group.store` for sub-scope addresses.

    Each capability method declares its `self` type as `Prefixed[Capability]`
    so the type checker accepts the call iff S satisfies the matching
    capability protocol. This is the "self-type narrowing" pattern: a
    `Prefixed[ReadOnlyBackend]` (where ReadOnlyBackend satisfies Get but
    not Put) type-checks for `.get(...)` and rejects `.put(...)` at the
    static-typing layer, with no runtime machinery and no TYPE_CHECKING
    stubs that lie about the surface. Verified to work on `pyright` and
    `mypy --strict` (covariance is inferred from usage; no explicit
    `TypeVar(..., covariant=True)` needed under PEP 695 generics).
    """

    def __init__(self, inner: S, prefix: str = "") -> None: ...

    def __truediv__(self, other: str) -> "Prefixed[S]":
        """Hierarchy traversal: returns a Prefixed[S] with the prefix
        extended by `other`. Same semantics as today's `StorePath / key`.
        Preserves S, so the resulting Prefixed has the same capability
        surface as the original."""
        ...

    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...

    # Capability methods, hand-written but each is two lines: a
    # self-typed signature plus a single-line delegation. The type
    # checker enforces the per-S restriction.

    def get(self: "Prefixed[Get]", key: str) -> memoryview:
        return self._inner.get(_join(self._prefix, key))

    def get_range(
        self: "Prefixed[GetRange]",
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> memoryview:
        return self._inner.get_range(
            _join(self._prefix, key), start=start, end=end, length=length
        )

    def get_ranges(
        self: "Prefixed[GetRanges]",
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
    ) -> Sequence[memoryview]:
        return self._inner.get_ranges(
            _join(self._prefix, key), starts=starts, ends=ends, lengths=lengths
        )

    def put(self: "Prefixed[Put]", key: str, value: bytes | memoryview) -> None:
        self._inner.put(_join(self._prefix, key), value)

    def delete(self: "Prefixed[Delete]", key: str) -> None:
        self._inner.delete(_join(self._prefix, key))

    def list(
        self: "Prefixed[List]",
        prefix: str | None = None,
        *,
        offset: str | None = None,
    ) -> Iterator[str]: ...

    def list_with_delimiter(
        self: "Prefixed[ListWithDelimiter]",
        prefix: str | None = None,
    ) -> "ListResult": ...

    def head(self: "Prefixed[Head]", key: str) -> "ObjectMetadata":
        return self._inner.head(_join(self._prefix, key))

    def copy(self: "Prefixed[Copy]", src: str, dst: str) -> None:
        self._inner.copy(_join(self._prefix, src), _join(self._prefix, dst))

    def transaction(self: "Prefixed[Transactional]") -> "TransactionContext":
        return self._inner.transaction()

    # Async variants follow exactly the same shape with `async def` and
    # `self: Prefixed[GetAsync]`-style annotations.
    async def get_async(self: "Prefixed[GetAsync]", key: str) -> memoryview:
        return await self._inner.get_async(_join(self._prefix, key))

    # ... and so on for get_range_async, get_ranges_async, put_async,
    # delete_async, list_async, list_with_delimiter_async, head_async,
    # copy_async. About sixty lines total for the full sync + async surface.
```

The same self-type-narrowing pattern carries through to the other wrappers in the [Wrappers section below](#wrappers): `ReadOnly[S]` simply omits the methods it strips (no `put`, `delete`, `copy`, `transaction`), so calls to them fail at type-check time as "attribute does not exist." `Caching[S]`, `Retry[S]`, `Tracing[S]` use the same `self: Caching[Get]` / `self: Retry[Put]` annotations to make every preserved capability conditionally available based on what S satisfies. `RangeCoalescing[S]` is the one wrapper that actively *adds* a capability beyond S's surface (synthesizing `GetRanges` from `GetRange`), so its `get_ranges` method is unconditional rather than self-type-narrowed.

The user-facing factory returns either a bare backend store (for the scope root) or a `Prefixed[S]` wrap (for a sub-prefix):

```python
# zarr/storage/factory.py

def make_store(
    store_like: StoreLike,
    *,
    path: str | None = None,
    storage_options: dict | None = None,
) -> Store | Prefixed[Store]:
    """Resolve a string / Path / Store / URL into a usable store.
    Replaces today's `make_store_path`. No `await` required for
    stateless backends (`LocalStore`, `MemoryStore`, `FsspecStore`,
    `ObstoreStore`); resource-holding backends (`ZipStore`) expose
    explicit context-manager construction."""
    ...
```

`Array.store` and `Group.store` carry the result type directly. `Array.store_path` / `Group.store_path` are kept as deprecation accessors that return the same `Prefixed[S]` value during the migration window.

## Backend stores

### `LocalStore`

```python
# zarr/storage/stores/local.py

class LocalStore:
    """Filesystem-backed store. Synchronous; implements Get, GetRange,
    GetRanges, Put, Delete, List, ListWithDelimiter, Head, Copy,
    Transactional (via rename-into-place)."""

    def __init__(self, root: Path | str, *, mkdir: bool = False) -> None: ...
    def get(self, key: str) -> memoryview: ...
    def get_range(self, key: str, *, start: int, end: int | None = None, length: int | None = None) -> memoryview: ...
    def get_ranges(self, key: str, *, starts: Sequence[int], ends: Sequence[int] | None = None, lengths: Sequence[int] | None = None) -> Sequence[memoryview]: ...
    def put(self, key: str, value: bytes | memoryview) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self, prefix: str | None = None, *, offset: str | None = None) -> Iterator[str]: ...
    def list_with_delimiter(self, prefix: str | None = None) -> ListResult: ...
    def head(self, key: str) -> ObjectMetadata: ...
    def copy(self, src: str, dst: str) -> None: ...
    def transaction(self) -> TransactionContext: ...
```

`LocalStore` is fully constructed by `__init__`. The existence check that today lives in `_open()` moves to `__init__`: passing a missing root raises `FileNotFoundError` immediately unless `mkdir=True` is set, in which case the directory is created. There is no `_is_open` flag, no `await store.open(...)`, and no lazy-open machinery.

### `ZipStore`

```python
# zarr/storage/stores/zip.py

class ZipStore:
    """Zip-archive-backed store. Synchronous; implements the read
    capabilities (and `Put` / `Delete` when opened in a writable mode).
    The only backend with non-trivial lifecycle: holds an open zipfile
    handle and a lock for the duration of use.

    The strictness of the context-manager contract is undecided; see
    the "Open questions" section below for the option space. The stub
    here shows context manager support unconditionally; whether
    methods called outside a context manager are an error, a warning,
    or supported lazy-open behavior is the open question."""

    def __init__(
        self,
        path: Path | str,
        *,
        mode: Literal["r", "a", "w", "x"] = "r",
        compression: int = zipfile.ZIP_STORED,
        allow_zip64: bool = True,
    ) -> None: ...

    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...

    # Sync capability methods. Behavior outside a context manager
    # depends on the resolution of the open question below.
    def get(self, key: str) -> memoryview: ...
    def get_range(self, key: str, *, start: int, end: int | None = None, length: int | None = None) -> memoryview: ...
    # ... rest of the read capability set, plus Put / Delete when mode
    # permits writes.

    # Pickling: __getstate__ / __setstate__ exist already on today's
    # ZipStore and stay; the file handle and lock are recreated on
    # the unpickling side, which lets `ZipStore` survive distributed
    # scheduling at the cost of re-acquiring the file handle on each
    # worker.
```

`ZipStore` is the prototype for "resource-holding store" in the wrapper-and-protocol design. Future backends with similar resource lifecycles (a hypothetical SQLite-backed store, a process-local mmap-pool store) follow the same pattern.

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
    capability set. Because `obstore` already implements obspec's
    protocols, this class is a thin pass-through whose main job is to
    rename `path` to `key` at the call boundary and make the protocol
    surface explicit on zarr's side. Path validation is enforced by the
    underlying obstore type (S3Store, GCSStore, AzureStore, HTTPStore)
    at construction."""

    def __init__(self, store: "obstore.store.ObjectStore") -> None: ...
    async def get_async(self, key: str) -> memoryview: ...
    async def get_range_async(self, key: str, *, start: int, end: int | None = None, length: int | None = None) -> memoryview: ...
    async def get_ranges_async(self, key: str, *, starts: Sequence[int], ends: Sequence[int] | None = None, lengths: Sequence[int] | None = None) -> Sequence[memoryview]: ...
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
        allowed_exceptions: tuple[type[Exception], ...] = (FileNotFoundError, IsADirectoryError, NotADirectoryError),
    ) -> None: ...

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "FsspecStore": ...
    @classmethod
    def from_upath(cls, upath: "UPath", **kwargs) -> "FsspecStore": ...

    async def get_async(self, key: str) -> memoryview: ...
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
    """Strips Put, Delete, Copy, Transactional from S's capability set.
    See [stores-wrappers.md](./stores-wrappers.md#readonlys) for the
    self-type-narrowing implementation pattern."""
    def __init__(self, inner: S) -> None: ...

class Caching[S]:
    """Adds an in-memory LRU over S's read capabilities. Eviction by
    bytes or entries; optional TTL. Writes invalidate the cache.

    Caching strategy (cache exactly what was requested vs object-level
    promotion), defaults (256 MiB / 4096 entries, TTL off, negative
    caching off), eviction policy, write invalidation, recommended
    composition with `RangeCoalescing` and `Retry`, and the migration
    plan for `experimental.cache_store` are specified in
    [stores-caching.md](./stores-caching.md)."""
    def __init__(
        self,
        inner: S,
        *,
        max_bytes: int = 256 << 20,            # 256 MiB
        max_entries: int = 4096,
        ttl: float | None = None,
        cache_negative: bool = False,
        cache_negative_ttl: float = 1.0,
    ) -> None: ...

class RangeCoalescing[S]:
    """Synthesizes `GetRanges` for stores that only implement `GetRange`.
    Coalesces ranges within `max_gap` bytes into single requests up to
    `max_request` bytes. No-op if S already implements `GetRanges`.

    Algorithm, defaults (1 MiB / 64 MiB), failure semantics, and the test
    plan that pins the "exactly one underlying `get_range` call" claim
    are specified in [stores-range-coalescing.md](./stores-range-coalescing.md)."""
    def __init__(
        self,
        inner: S,
        *,
        max_gap: int = 1 << 20,            # 1 MiB
        max_request: int = 64 << 20,       # 64 MiB
    ) -> None: ...

class Tracing[S]:
    """Wraps every method in an OpenTelemetry span (or whatever tracer
    is supplied). Zero-cost via __new__ short-circuit when no tracer
    is set. See [stores-wrappers.md](./stores-wrappers.md#tracings)
    for span naming, attributes, and the OpenTelemetry duck-typing."""
    def __init__(self, inner: S, *, tracer: "Tracer | None" = None) -> None: ...

class Retry[S]:
    """Retries transient failures with exponential backoff and jitter.
    See [stores-wrappers.md](./stores-wrappers.md#retrys) for the
    retry semantics, the per-call budget contract, and the rationale
    behind the defaults."""
    def __init__(
        self,
        inner: S,
        *,
        max_attempts: int = 3,
        retry_on: tuple[type[Exception], ...] = (TimeoutError, ConnectionError),
        initial_backoff: float = 0.1,
        max_backoff: float = 10.0,
        backoff_multiplier: float = 2.0,
        jitter: float = 0.1,
    ) -> None: ...

class SyncToAsync[S]:
    """Adapts a sync store to advertise async protocols by running each
    call in a thread pool. The inverse `AsyncToSync` exists for the
    other direction. See [stores-wrappers.md](./stores-wrappers.md#synctoasyncs)
    for executor choice, GIL contention notes, and reentrancy contract."""
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
# store satisfies GetAsync, GetRangeAsync, GetRangesAsync, ListAsync, ...
# typing-time check: zarr.open_group(store) requires GetAsync & ListAsync

# 2) A user that wants caching + range coalescing on top of a local store:
from zarr.storage.stores.local import LocalStore
from zarr.storage.wrappers import Caching, RangeCoalescing

store = Caching(RangeCoalescing(LocalStore("/data/array.zarr")), max_bytes=1 << 30)
# Capability set is preserved. Caching outermost, RangeCoalescing inside,
# matching the recommended ordering in stores-caching.md so that cached
# results are coalesced fetches.

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

# 5) Hierarchy traversal via Prefixed (replaces today's StorePath):
from zarr.storage.prefixed import Prefixed

s3 = ObstoreStore(S3Store(bucket="my-bucket", region="us-east-1"))
group_root = Prefixed(s3, "datasets/2026")          # equivalent to today's StorePath(s3, "datasets/2026")
subgroup = group_root / "north_atlantic"             # equivalent to today's __truediv__
array = subgroup / "sst"                             # Prefixed[ObstoreStore], same capability surface as s3

# 6) ZipStore must be entered as a context manager:
from zarr.storage.stores.zip import ZipStore

with ZipStore("data.zip", mode="r") as zs:
    array = zarr.open(zs, path="my/array")
    chunk = array[0:100]
# zs is closed on exit; the file handle is released.
```

## Migration shims and deprecation surface

The above is a 4.0 design. To get there without an abrupt break, the public-facing migration plan should be:

- **Keep `Store` as a typing alias for the union of common capabilities** during the deprecation window. Code that currently writes `store: Store` continues to type-check.
- **`FsspecStore`, `LocalStore`, `MemoryStore`, `ObstoreStore` keep their current names** and grow toward the proposed shapes incrementally. The biggest user-visible deltas are that read methods return `memoryview` instead of `Buffer` (the per-call `prototype` argument is dropped, with the existing `prototype.buffer.from_bytes` wrapping happening at the codec-pipeline / array layer rather than inside each store), and that most methods become sync by default. See the [README subsection on prototype decoupling](../README.md#decoupling-prototype-from-the-read-api) and the [return-type subsection](../README.md#returning-memoryview-from-store-read-methods) for the rationale and step-by-step migration plan.
- **`StorePath` becomes a deprecation alias for `Prefixed[Store]`.** Existing `StorePath(store, path)` calls return a `Prefixed(store, path)` and emit a `DeprecationWarning`. `Array.store_path` and `Group.store_path` are kept as accessors that return the same `Prefixed[S]` value as the new `Array.store` / `Group.store` attributes, with a deprecation note pointing at the new attribute names. `__truediv__` semantics are preserved verbatim so existing hierarchy-traversal code continues to work.
- **`Store.open` classmethod and the `_is_open` / `_open` / `_ensure_open` machinery is removed.** Stateless backends (`MemoryStore`, `FsspecStore`, `ObstoreStore`) lose nothing because their `_open` was a no-op already. `LocalStore` moves its existence check to `__init__` with an opt-in `mkdir=False` flag (default raises `FileNotFoundError` if the root does not exist). `ZipStore`'s lifecycle contract is the one undecided sub-question; see the [open question on `ZipStore` lifecycle](#open-questions) below for the option space. The other stores' lifecycle resolution is independent and does not block on it. See the [README subsection on lifecycle, paths, and the future of `StorePath`](../README.md#lifecycle-paths-and-the-future-of-storepath).
- **`with_read_only()` is removed in favor of the `ReadOnly[S]` wrapper.** During the deprecation window, `store.with_read_only(True)` returns `ReadOnly(store)` and emits a `DeprecationWarning`. The `read_only` constructor argument on every backend store is dropped at the same time; existing call sites using `LocalStore(root, read_only=True)` migrate to `ReadOnly(LocalStore(root))`.
- **Wrappers are additive.** Shipping `Caching`, `RangeCoalescing`, etc. does not require removing anything.
- **Capability protocols ship first**, before any breaking changes to existing stores. This lets downstream libraries (xarray, dask, virtualizarr) adopt protocol-based typing on their side ahead of the 4.0 cutover.
- **The `experimental.cache_store` module retires** in favor of the `Caching` wrapper, with a deprecation warning that points at the new API.

The migration story for `FsspecStore` specifically is the smallest delta in the proposal: the existing class keeps the same constructor signature, gains a `validate_path` keyword argument with default `None`, and documents the verbatim-path contract. Everything else in the FsspecStore section is unchanged.

## Open questions

- **Async naming.** Resolved in favor of two protocol families with the obspec-aligned `Async` suffix on classes and `_async` suffix on methods (sync `Get` / `GetRange` / `GetRanges` / ... and async `GetAsync` / `GetRangeAsync` / `GetRangesAsync` / ...). See the [README subsection on sync-by-default](../README.md#sync-by-default-with-async-as-an-opt-in-protocol-family) for the rationale, the per-backend mapping, and the deprecation path for `zarr.core.sync.sync()`.
- **Capability intersection types.** Python's `Protocol` does not yet support `&` (intersection) cleanly across all type checkers. The usage examples assume PEP-695-style type expressions. May need to fall back to explicit `Protocol`-merging classes (`class ReadCapable(Get, GetRange, List, Head, Protocol): ...`).
- **`Transactional` granularity.** Resolved as a two-protocol design: `Transactional` for plain multi-key atomic transactions, `TransactionalOCC` extending it with snapshot-isolation semantics for backends like Icechunk. See [stores-transactional.md](./stores-transactional.md) for the full design, per-backend support matrix, and migration plan (including the V2 rename-into-place restoration for `LocalStore`).
- **Backwards compatibility window.** How long does the `Store` ABC remain importable? One major release? Two? Affects how aggressively wrappers can replace inheritance-based extension.
- **Return type.** Resolved in favor of `memoryview` over `bytes` and obspec's `Buffer`. See the [README subsection on returning `memoryview`](../README.md#returning-memoryview-from-store-read-methods) for the three-way comparison and the per-backend migration. The door stays open to upgrade to obspec's `Buffer` later if explicit lifetime semantics become necessary; the migration would be additive.
- **GPU re-coupling, if it becomes necessary.** Option 1 ([README](../README.md#decoupling-prototype-from-the-read-api)) gives up zero-copy DMA into device buffers in principle. If the obstore GPU integration matures and we want that path back, the smallest delta is option 3: introduce a `ReadContext` parameter that carries a `BufferPrototype`, and let stores that opt in return `Buffer` instead of `bytes`. Backends without the opt-in continue to return `bytes` and get wrapped above. This is a strictly additive change relative to option 1, so committing to option 1 now does not foreclose option 3 later.
- **`ZipStore` lifecycle contract.** Whether methods called outside a context manager should raise, warn, or be supported indefinitely. Five options are in play:
  1. **Indefinite lazy-open.** Status quo behavior preserved; context manager is documented as recommended but not required. `__del__` and pickle round-trip handle cleanup. No deprecation, no break. Lowest risk; resource-holding stores stay an explicit exception in the design (which the README already carves out).
  2. **Deprecation cycle.** `DeprecationWarning` for one or two releases, then `RuntimeError`. Final state is uniform with the rest of the design. Cost: real ergonomic tax on distributed scheduling (dask, ray) where task functions today receive an opened store and would need to enter a context manager per task.
  3. **New parallel store.** Add `StrictZipStore` alongside the existing `ZipStore`. Old class keeps lazy-open indefinitely; new class requires context manager. Variant: the protocol-based redesign's `ZipStore` is the strict one, today's `Store` ABC `ZipStore` keeps lazy-open. Migration cost is paid as part of the broader API migration rather than as a `ZipStore`-specific event.
  4. **Mode-conditional strictness.** Read mode allows lazy-open (leaking a handle is benign; the OS reclaims and the data is fine); write modes (`"w" | "a" | "x"`) require a context manager (a process exiting without close on a writable zip corrupts the central directory). Targets the actual correctness risk but introduces an asymmetric contract on one class.
  5. **Constructor flag.** `ZipStore(path, strict=False)` keeps lazy-open; `strict=True` requires context manager. Default off. Single class, opt-in. Flag becomes API surface to maintain.

  Trade-offs in [README sub-discussion to be added if this becomes a sticking point]; the corruption risk in write mode is the same under all options because `__del__ → close()` is the safety net in every case. Distributed pickling round-trips correctly under options 1, 3 (old class), 4 (read), and 5 (default), and takes a real ergonomic tax under options 2 and 4 (write).
