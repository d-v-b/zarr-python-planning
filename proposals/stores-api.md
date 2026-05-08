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

## GPU and zero-copy reads via `GetInto`

`Get`, `GetRange`, and `GetRanges` follow an allocation-based contract: the store allocates the result buffer, fills it, and returns it. This is the right shape for the common case (CPU reads from CPU-shaped backends) and matches every role-model storage API: TensorStore's `KvStore.read` allocates ([KvStore.read](https://google.github.io/tensorstore/python/api/tensorstore.KvStore.read.html)), zarrs's `ReadableStorageTraits::get` allocates ([ReadableStorageTraits](https://docs.rs/zarrs_storage/latest/zarrs_storage/trait.ReadableStorageTraits.html)), zarrita's `Readable.get` allocates, obstore's `get` allocates.

But the allocation-based contract leaves zero-copy GPU-direct reads on the table. Today's `prototype: BufferPrototype` argument was an attempt to address this — by letting the caller specify "give me back a GPU buffer" — but the README's [decoupling-prototype subsection](../README.md#decoupling-prototype-from-the-read-api) admits the GPU path is fictional in current zarr-python: even with `gpu_buffer_prototype`, the bytes hit the CPU first because neither fsspec nor obstore knows how to allocate on the device. `prototype` is a knob that doesn't actually wire up.

The honest design is to push buffer ownership to the *caller* via a `GetInto` protocol family. The caller allocates the destination buffer (CPU or GPU); the store writes into it. Backends that can DMA directly into device memory (a future GDS-aware obstore, a kvikio-backed store) advertise `GetInto`; backends that can't simply don't advertise it. Callers who need GPU-direct-storage ask for `GetInto` at the type level; everyone else uses the allocation-based `Get`.

This is opt-in additive surface alongside `Get`, not a replacement.

### Capability protocols

```python
# zarr/storage/protocols.py (continued)

@runtime_checkable
class GetInto(Protocol):
    """Read into a caller-provided writable buffer. The buffer must be
    at least as large as the value; the store fills it and returns a
    ReadResult whose `value` is a memoryview over the prefix of the
    buffer that was filled. The generation is reported the same way
    `Get` reports it.

    Backends that can DMA directly into the destination buffer
    (CUDA-aware HTTP, NVIDIA GDS, kvikio-backed storage) avoid the
    intermediate CPU buffer entirely. Backends without that capability
    do not implement this protocol; callers who want zero-copy GPU
    reads use the type system to require `GetInto` and get a clear
    type error when a backend that cannot deliver is passed in."""

    def get_into(self, key: str, buffer: "WritableBuffer") -> ReadResult: ...


@runtime_checkable
class GetRangeInto(Protocol):
    def get_range_into(
        self,
        key: str,
        buffer: "WritableBuffer",
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> ReadResult: ...


@runtime_checkable
class GetRangesInto(Protocol):
    """Batch range read into a caller-provided buffer. The buffer must
    be at least as large as the sum of the requested range lengths;
    the wrapper writes each range's bytes into a contiguous slice of
    the buffer, in input order. The returned ReadResults' `value`
    fields are memoryviews over the corresponding slices."""

    def get_ranges_into(
        self,
        key: str,
        buffer: "WritableBuffer",
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
    ) -> Sequence[ReadResult]: ...


# Async variants follow the same shape with `async def` and `_async`
# method-name suffixes (`GetIntoAsync`, `GetRangeIntoAsync`,
# `GetRangesIntoAsync`).
```

`WritableBuffer` is anything that exposes the *writable* buffer protocol. Concretely: `bytearray`, a writable `memoryview`, `numpy.ndarray` (writable), `cupy.ndarray` via `__cuda_array_interface__`, a `torch.Tensor` via `__cuda_array_interface__` (or `__dlpack__`), an mmap. The protocol does not pin a single concrete type; the conformance suite tests against `bytearray` for the baseline and adds CUDA-array-interface tests for backends that advertise GPU-direct support.

```python
# zarr/storage/protocols.py (continued)

WritableBuffer = TypeAlias  # the union of supported writable buffer-protocol types
# In practice: anything where memoryview(b).readonly is False, OR
# anything with a __cuda_array_interface__ / __dlpack__ exposing a
# writable region. Spelled out concretely in the runtime check.
```

### Buffer ownership contract

Three load-bearing rules, all enforceable by the conformance suite:

1. **The buffer is fully caller-owned.** The store does not retain a reference past the return of `get_into`. The store does not free or modify the buffer outside the prefix it writes. This is the inverse of the `Get` contract (where the *store* owns the returned `memoryview`'s backing).

2. **The store writes into the prefix `[0, len(value))` of the buffer.** Bytes past the prefix are untouched. Callers who need to know how many bytes were written read it from the returned `ReadResult.value`'s length, or from the `head()` precheck.

3. **Buffers that are too small raise.** If the value is larger than the buffer, the store raises `ValueError` (or a more specific subclass) before writing. The check happens before any writes; partially-filled buffers on error are not part of the contract. Callers who want truncation semantics use `GetRangeInto` with an explicit `length`.

The "buffer too small" check forces a tradeoff: either every `get_into` call pays a `head()` round-trip first to size the buffer, or the caller tracks sizes out-of-band. The recommended idiom is to use `GetRangeInto` with explicit `start`/`length`, which is precisely sized by definition. `GetInto` is for the case where the caller already knows the value's size (cached metadata, a manifest, prior `head` call).

### Backend support

| Backend | Implements `GetInto`? | Notes |
|---|---|---|
| `LocalStore` | yes (read into mmap or buffer via `os.read` into a `bytearray`) | Works for any writable CPU buffer; no special GPU path |
| `MemoryStore` | yes (memcpy from internal store to caller buffer) | Works for any writable buffer; GPU path requires CUDA-aware copy |
| `ZipStore` | yes (zipfile.read_into-like, via internal stream) | CPU-only |
| `FsspecStore` | depends on fs | Most fsspec backends materialize to `bytes`; advertise `GetInto` only if a `read_into` path exists |
| `ObstoreStore` | not in initial release | obstore's current API allocates; advertise `GetInto` once obstore grows the equivalent |
| Future GDS-aware obstore | yes (DMA into device buffer when buffer exposes `__cuda_array_interface__`) | The motivating use case |
| Future `KvikioStore` | yes (kvikio-native; bypasses CPU entirely for `cupy` and similar) | Slot reserved |

Most backends implement `GetInto` as a thin shim around their existing read path: read into a temporary, `memoryview(buffer)[:len] = bytes(temp)`. This is a copy, not zero-copy — the win for these backends is purely API uniformity, not performance. The genuine zero-copy win is reserved for backends that have backend-specific support (mmap into the same address space, GDS DMA, kvikio).

This means **`GetInto` is honest about which backends can actually deliver zero-copy.** The protocol declaration is a load-bearing claim; backends that can only do "read then copy" can either advertise `GetInto` (with the documented copy) or skip it (forcing callers to use `Get` and copy themselves). The conformance suite's `ZeroCopyGetIntoSpec` (separate from the basic `GetIntoSpec`) tests whether the destination buffer is *actually* the memory the backend wrote — not a copy. Backends opt into the zero-copy spec only when they can pass it; the rest stay on the basic spec.

### Composition with wrappers

- **`Caching[GetInto]`**: refused at construction. The cache stores bytes in its own memory; `get_into` wants bytes in the caller's buffer. The cache could memcpy from its store to the caller's buffer, but this defeats the zero-copy motivation of `GetInto`. A user who wants caching of large reads should use `Get` (allocation-based) and accept the cache's memory cost; a user who wants zero-copy should not cache. Refuse-at-construction; document. A future "buffer-aware cache" that holds buffers the caller can borrow is a separate proposal.
- **`RangeCoalescing[GetRangeInto]`**: works, with the wrapper managing buffer slicing. The wrapper allocates a coalesced-fetch buffer, issues one `get_range_into` for the group, and writes each requested range's bytes into the corresponding slice of the *caller's* output buffer. The intermediate coalesced buffer is the wrapper's; the output buffer is the caller's; one copy at the slice-out step. Zero-copy from network to caller is preserved when the inner `GetRangeInto` is zero-copy and the slice is contiguous; otherwise the slice copy is the price of coalescing. Algorithm sketch in [stores-range-coalescing.md](./stores-range-coalescing.md), pending an updated subsection that addresses this case.
- **`Transactional[GetInto]`**: orthogonal. `GetInto` is read-side; transactions are write-side. Reads inside a transaction route through `get_into` the same way they route through `get`, with generations tracked the same way.
- **`ReadOnly[GetInto]`**: passes through. `GetInto` is a read capability; `ReadOnly` does not strip read capabilities.
- **`Prefixed[GetInto]`**: passes through.
- **`Tracing[GetInto]`**: works; the span attribute set adds `zarr.store.buffer_kind` (`"cpu"` / `"cuda"` / `"unknown"`) inferred from whether the buffer exposes `__cuda_array_interface__`.

### Conformance

Three new specs land in [stores-conformance.md](./stores-conformance.md):

- **`GetIntoSpec`** parameterizes over backends that satisfy `GetInto`. Asserts that `get_into(key, bytearray(N))` writes the correct bytes; the buffer outside the prefix is untouched; an undersized buffer raises before any writes; the returned `ReadResult.generation` matches what `Get` reports for the same key; nested calls do not interfere.
- **`GetRangeIntoSpec`** mirrors `GetRangeSpec` with buffer-provided semantics. Asserts that `start`/`end`/`length` route to the correct bytes; that the buffer is sized correctly; that empty ranges yield zero-length writes; that out-of-range requests raise.
- **`ZeroCopyGetIntoSpec`** is separately opt-in. A backend advertises this spec only when it can guarantee that the destination buffer is the memory the backend wrote, not a copy. The test creates a buffer, calls `get_into`, mutates a byte of the *backend's* internal storage (via a backend-specific hook), and asserts the caller's buffer reflects the change. Backends like `MemoryStore` (where the backend's storage is the caller's buffer if the implementation chooses) and `LocalStore` with mmap can opt in; `FsspecStore` and copy-based backends do not. This spec is what makes "zero-copy" a falsifiable claim.

### Worked examples

```python
# 1) GPU-direct read into a cupy array (assumes a GDS-aware obstore variant).
import cupy as cp
from zarr.storage.stores.obstore import GDSObstoreStore

store: GetInto = GDSObstoreStore(...)
buf = cp.empty(shard_size, dtype=cp.uint8)
result = store.get_into("c/0/0", buf)
# `buf` now holds the shard's bytes on the GPU. No CPU bounce.
# `result.generation` is the S3 ETag at read time.

# 2) Read directly into a numpy array allocation (CPU).
import numpy as np

store: GetInto = LocalStore("/data")
buf = np.empty(metadata_size, dtype=np.uint8)
result = store.get_into("zarr.json", buf.data)
# `buf` holds the metadata bytes. The store wrote into numpy's memory.

# 3) Range coalescing into a single GPU buffer.
import cupy as cp
from zarr.storage.wrappers import RangeCoalescing

store = RangeCoalescing(GDSObstoreStore(...))
total = sum(lengths)
buf = cp.empty(total, dtype=cp.uint8)
results = store.get_ranges_into(
    "shard.zarr",
    buf,
    starts=starts,
    lengths=lengths,
)
# Each requested range now occupies a contiguous slice of `buf` on the GPU.
# `results[i].value` is a memoryview over `buf[offset:offset+lengths[i]]`.

# 4) Falling back to allocation when GetInto is unavailable.
def read(store: Get | GetInto, key: str, hint_size: int | None = None) -> ReadResult:
    if isinstance(store, GetInto) and hint_size is not None:
        buf = bytearray(hint_size)
        return store.get_into(key, buf)
    return store.get(key)
# Callers who can size the read up front and have a GetInto-capable
# backend get the zero-copy path; everyone else gets the allocation path.
```

### Migration

This subsection's commitments are additive:

- The `GetInto` / `GetRangeInto` / `GetRangesInto` protocols are new.
- The `prototype: BufferPrototype` argument on existing `Get` methods continues to be deprecated per the [README's decoupling-prototype subsection](../README.md#decoupling-prototype-from-the-read-api).
- No backend is required to implement `GetInto` in the initial release. The protocol is the *slot* for future GPU-direct-storage backends.
- `LocalStore` and `MemoryStore` can implement `GetInto` for free (CPU buffer fill); shipping these as the reference implementations validates the protocol shape.

The README's open question on "GPU re-coupling, if it becomes necessary" is resolved by this subsection: `GetInto` *is* the GPU re-coupling, and it is shaped so that the caller (not the store) chooses the device. The README entry can be replaced with a pointer to this section.

### Open questions

- **`WritableBuffer` typing.** The protocol's argument type is informally "anything writable-buffer-protocol-compatible." A precise Python type for this does not exist in the standard library; the closest is `collections.abc.Buffer` (3.12+) but that does not distinguish writable from read-only at the type level. The pragmatic choice is to type the argument as `Any` and rely on a runtime `memoryview(buffer).readonly is False` check, with a separate path for `__cuda_array_interface__` buffers. Worth tracking; not a blocker.
- **Async `GetInto` and lifetime.** An `await store.get_into_async(key, buf)` call holds a reference to `buf` for the duration of the await. If the caller drops `buf` mid-await, the async call has a dangling reference. The contract has to specify "the caller must keep `buf` alive until the await resolves," which is the standard async-buffer contract but worth documenting explicitly.
- **`GetInto` over `Caching`.** Refused at construction in the initial design. Whether a "buffer-aware cache" (one that holds buffers callers can borrow) is worth shipping is a future-proposal question. The conservative initial answer is no; revisit if real workloads demand it.
- **Composition with `Transactional` reads inside `repeatable_read=True` transactions.** The transaction tracks the generation of every read for commit-time conflict detection. `GetInto` reads are reads, so the same tracking applies. Worth confirming in conformance tests; no design change expected.
- **CPU buffers on copy-based backends.** Most backends implement `GetInto` as "read into temporary, memcpy into caller buffer." This is allocation + copy, strictly worse than `Get` (which is just allocation, since the caller can read the result without copying). Should backends in this category advertise `GetInto` (uniform API, slow path) or skip it (callers fall back to `Get`)? The recommendation is to advertise it: the API uniformity is worth the modest slowdown for callers who want one code path, and callers who care about the perf difference can dispatch on `isinstance(store, ZeroCopyGetIntoSpec)` (or an analogous marker). Decide by initial-release time.
- **`GetInto` interaction with `MemoryStore`'s internal buffer.** `MemoryStore` stores `memoryview` over `bytes` internally. The `GetInto` implementation can either (a) `memcpy` from internal to caller (CPU-cheap, breaks zero-copy from internal storage), or (b) require the caller's buffer to be the same memory as the internal storage (impossible in general). Pick (a) and document; a backend that wants true zero-copy from in-memory storage is `MemoryStore.get` returning a memoryview over the internal bytes, which is what `Get` already does.

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

## Bounds and composite stores

`Get`, `Put`, `List`, etc. are sufficient to model a single backend over a single keyspace. Two adjacent capabilities are missing and worth resolving together because they share one primitive (`KeyRange`):

1. **Bounded stores.** A store may want to advertise that its visible keyspace is a sub-range of the underlying backend's full keyspace. Sharding (a shard owns a `KeyRange` of chunk-keys), consolidated-metadata-as-overlay (the overlay covers only metadata keys), and read/write scope safety (a worker handed a store can only touch its assigned slice) all want this.
2. **Composite stores.** A store may compose N base stores, each bound to a disjoint `KeyRange`, dispatching each operation to whichever base owns the key. Tiered storage (hot keys local, cold keys cloud), mixed-backend arrays, consolidated metadata, and migration patterns all want this.

TensorStore models both via a single `KeyRange` primitive and a `kvstack` driver ([TensorStore KvStore.KeyRange](https://google.github.io/tensorstore/python/api/tensorstore.KvStore.KeyRange.html), [kvstack driver](https://google.github.io/tensorstore/kvstore/kvstack/index.html)). zarrs, zarrita, and obstore have neither concept; obstore exposes a `start_after` listing parameter that handles part of the bounded-listing case but does not generalize to composites.

The decision below commits zarr-python to the TensorStore-shaped primitive. The motivating reason is composite stores: a `start_after`-only design handles single-store listing bounds but cannot express the per-layer ranges a composite needs. Committing to `KeyRange` from day one keeps a single coherent bounds vocabulary across the protocol family.

### `KeyRange`

```python
# zarr/storage/keyrange.py

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeyRange:
    """A half-open interval `[inclusive_min, exclusive_max)` in
    lexicographic key order. Both ends are raw key strings; an empty
    string for `inclusive_min` means "no lower bound" and `None` for
    `exclusive_max` means "no upper bound".

    Used to describe the keyspace a bounded store covers and the
    per-layer ranges of a composite store.

    Modeled on TensorStore's `KvStore.KeyRange`."""

    inclusive_min: str = ""
    exclusive_max: str | None = None

    def __post_init__(self) -> None:
        if self.exclusive_max is not None and self.inclusive_min >= self.exclusive_max:
            raise ValueError(
                f"KeyRange is empty: inclusive_min={self.inclusive_min!r} >= "
                f"exclusive_max={self.exclusive_max!r}"
            )

    @classmethod
    def from_prefix(cls, prefix: str) -> "KeyRange":
        """KeyRange covering exactly the keys that start with `prefix`.
        The upper bound is `prefix` with the last byte incremented; if
        prefix is empty, the result is unbounded."""
        if not prefix:
            return cls()
        last = prefix[-1]
        if last == "￿":
            # No representable next character; fall back to an explicit
            # large sentinel. Callers needing exact prefix semantics on
            # arbitrary unicode should use contains() rather than relying
            # on the bound directly.
            return cls(inclusive_min=prefix)
        return cls(inclusive_min=prefix, exclusive_max=prefix[:-1] + chr(ord(last) + 1))

    def contains(self, key: str) -> bool:
        if key < self.inclusive_min:
            return False
        if self.exclusive_max is not None and key >= self.exclusive_max:
            return False
        return True

    def overlaps(self, other: "KeyRange") -> bool:
        """True iff `self` and `other` share at least one key."""
        lo = max(self.inclusive_min, other.inclusive_min)
        hi_self = self.exclusive_max
        hi_other = other.exclusive_max
        if hi_self is None and hi_other is None:
            return True
        hi = hi_self if hi_other is None else hi_other if hi_self is None else min(hi_self, hi_other)
        return lo < hi

    def intersect(self, other: "KeyRange") -> "KeyRange | None":
        """Intersection of two ranges, or None if disjoint."""
        if not self.overlaps(other):
            return None
        lo = max(self.inclusive_min, other.inclusive_min)
        if self.exclusive_max is None:
            hi = other.exclusive_max
        elif other.exclusive_max is None:
            hi = self.exclusive_max
        else:
            hi = min(self.exclusive_max, other.exclusive_max)
        return KeyRange(inclusive_min=lo, exclusive_max=hi)
```

`KeyRange` is plain data: no I/O, no backend coupling. It lives at the top of the storage module so backends, wrappers, and the array layer can all use it.

### Listing methods take `range`

The `List` and `ListWithDelimiter` protocols defined in the [Capability protocols section](#capability-protocols) gain an optional `range: KeyRange | None = None` argument:

```python
@runtime_checkable
class List(Protocol):
    def list(
        self,
        prefix: str | None = None,
        *,
        offset: str | None = None,
        range: KeyRange | None = None,
    ) -> Iterator[str]: ...


@runtime_checkable
class ListWithDelimiter(Protocol):
    def list_with_delimiter(
        self,
        prefix: str | None = None,
        *,
        range: KeyRange | None = None,
    ) -> "ListResult": ...
```

When `range` is provided, the listing yields only keys in `range`. Backends that can push the bound to the wire (S3 `StartAfter`, GCS `startOffset`/`endOffset`, local sorted iteration) do so; others filter client-side. Either way the contract is the same. `prefix` and `range` compose: a call passing both yields keys that start with `prefix` *and* fall in `range`.

This is a backwards-compatible extension to the listing protocols if `range=None` is the default and existing callers are unchanged. Async variants follow the same shape.

### Bounded backends

Every backend store has an implicit `bounds: KeyRange` describing the keyspace it covers. The default is `KeyRange()` (unbounded). Backends that own a sub-range expose it as a property:

```python
class LocalStore:
    def __init__(
        self,
        root: Path | str,
        prefix: str = "",
        *,
        bounds: KeyRange | None = None,
        mkdir: bool = False,
    ) -> None: ...

    @property
    def bounds(self) -> KeyRange: ...

    def __truediv__(self, sub: str) -> "LocalStore":
        """Returns a new LocalStore with the prefix extended by `sub`.
        Bounds, if set, narrow to the intersection with the new prefix's
        natural range."""
        ...
```

Per-key operations on a bounded backend that receive a key outside `bounds` raise `KeyError`. The store's universe *is* `bounds`; out-of-bounds keys are not present from this store's perspective. This matches TensorStore's behavior for sharded reads and is the choice that makes bounded stores composable with the rest of the design (a composite that dispatches by range can rely on `KeyError` from out-of-bounds keys to detect mis-routing).

Listing operations on a bounded backend, when `range=None` is passed, yield only keys in `bounds`. When `range` is passed, yield only keys in `bounds.intersect(range)` (raising `ValueError` if the intersection is empty).

The `bounds` property is what `KvStack` (below) reads to validate that its layers are disjoint and to choose the right layer for each key.

### `KvStack[S]`: composite store

```python
# zarr/storage/wrappers.py (continued)

class KvStack[S]:
    """Composite store dispatching per-key to one of N base stores by
    KeyRange. Modeled on TensorStore's `kvstack` driver.

    Layers are an ordered sequence of `(KeyRange, S)` pairs. The ranges
    must be pairwise disjoint; the constructor raises `ValueError`
    otherwise. Operations on a key dispatch to the unique layer whose
    range contains it; keys outside every layer raise `KeyError`.

    Listing fans out to layers whose ranges overlap the requested range
    and merges results in lexicographic order.

    Capability advertisement is the **intersection** of the layers'
    capability surfaces: `KvStack[S]` advertises `Get` only if every
    layer satisfies `Get`, `Put` only if every layer satisfies `Put`,
    and so on. The honest surface; a layer that cannot satisfy a
    capability cannot be silently bypassed."""

    def __init__(self, layers: Sequence[tuple[KeyRange, S]]) -> None:
        # Validate disjointness.
        sorted_layers = sorted(layers, key=lambda t: t[0].inclusive_min)
        for i in range(1, len(sorted_layers)):
            prev_range, _ = sorted_layers[i - 1]
            curr_range, _ = sorted_layers[i]
            if prev_range.overlaps(curr_range):
                raise ValueError(
                    f"KvStack layers must be disjoint; "
                    f"{prev_range} overlaps {curr_range}"
                )
        self._layers = sorted_layers

    def _route(self, key: str) -> S:
        for kr, layer in self._layers:
            if kr.contains(key):
                return layer
        raise KeyError(f"no layer covers key {key!r}")

    def get(self: "KvStack[Get]", key: str) -> memoryview:
        return self._route(key).get(key)

    def put(self: "KvStack[Put]", key: str, value: bytes | memoryview) -> None:
        self._route(key).put(key, value)

    def delete(self: "KvStack[Delete]", key: str) -> None:
        self._route(key).delete(key)

    def list(
        self: "KvStack[List]",
        prefix: str | None = None,
        *,
        offset: str | None = None,
        range: KeyRange | None = None,
    ) -> Iterator[str]:
        # Restrict to layers whose range overlaps the requested range
        # (or all layers if range is None). Yield in lex order; because
        # layer ranges are disjoint and pre-sorted, concatenating each
        # layer's listing in layer order is already lex-ordered.
        ...

    # Async variants follow the same shape.
```

The capability-intersection rule is what makes `KvStack` honest. If a user constructs `KvStack([(r1, read_only_s1), (r2, read_write_s2)])`, the resulting store only advertises `Get` (and other read capabilities) — calling `put(...)` would silently route to `s1` or `s2` depending on the key, and silently fail on `s1` is exactly the bug class the protocol-based redesign is trying to retire. Failing at the type/protocol layer instead is the correct contract.

`KvStack[S]` itself satisfies `bounds`: its `bounds` is the union-bounding-box of its layers' ranges. A layer whose `bounds` extends beyond its declared `KeyRange` (because the underlying backend covers more keys than the stack assigns to it) is *itself* a bounded view: the stack effectively narrows each layer's keyspace to the layer's `KeyRange`. Nested `KvStack`s are well-defined; the outer stack's layers can themselves be `KvStack` instances.

### Worked examples

```python
# 1) Tiered metadata + chunks: metadata locally, chunks on S3.
from zarr.storage.keyrange import KeyRange
from zarr.storage.wrappers import KvStack
from zarr.storage.stores.local import LocalStore
from zarr.storage.stores.obstore import ObstoreStore

store = KvStack([
    (KeyRange.from_prefix("zarr.json"), LocalStore("/cache/metadata")),
    (KeyRange.from_prefix("c/"), ObstoreStore(s3_store)),
])
# Reads/writes of "zarr.json" route to local; reads of "c/0/0" route to S3.

# 2) Migration: read from new store, fall through to old via key-prefix carve.
# (Disjoint ranges, not "fall through on miss" — that pattern needs a different
# wrapper, see open questions below.)
store = KvStack([
    (KeyRange(exclusive_max="2026/"), legacy_store),
    (KeyRange(inclusive_min="2026/"), new_store),
])

# 3) Consolidated-metadata-as-overlay: metadata served from a fast in-memory
# store synthesized from a consolidated file; chunks fall through to the real
# backend.
overlay = MemoryStore.from_consolidated(consolidated_json)
store = KvStack([
    (KeyRange.from_prefix("zarr.json"), overlay),
    (KeyRange.from_prefix("c/"), real_store),
])
# Hits on metadata keys are served by `overlay` without touching the network.

# 4) Sharded array: each shard is a bounded view of an underlying object.
# (Sketch; the actual sharding-as-composite redesign is a follow-up.)
shard_layers = [
    (KeyRange(inclusive_min=f"c/{i*64}", exclusive_max=f"c/{(i+1)*64}"),
     bounded_view(shard_objects[i], chunk_range_for_shard(i)))
    for i in range(num_shards)
]
chunks_store = KvStack(shard_layers)
```

### Conformance

Two new specs land in [stores-conformance.md](./stores-conformance.md):

- **`KeyRangeListSpec`** parameterizes over backends that satisfy `List`. Asserts `range` filtering yields exactly the expected keys, that combining `prefix` and `range` intersects correctly, and that empty intersections yield no keys without erroring.
- **`KvStackSpec`** asserts disjointness validation at construction, correct routing on per-key operations, lex-ordered merged listing, capability intersection (constructing a stack with mixed read/write layers advertises only read capabilities), and that out-of-coverage keys raise `KeyError`.

`CapabilityPreservationSpec` runs against `KvStack` with the modification that the wrapper preserves the *intersection* of inner capabilities, not the union or pass-through.

### Migration

This subsection's commitments are additive:

- `KeyRange` is a new dataclass; nothing currently uses it.
- `range` argument on `List` / `ListWithDelimiter` is a new optional parameter; existing callers unchanged.
- `bounds` property on backends is new; defaults to `KeyRange()` (unbounded) for everything that doesn't opt in.
- `KvStack[S]` is a new wrapper; nothing has to migrate to use it.

The sharding codec migration to `KvStack`-shaped composites is explicitly future work, not initial scope. Consolidated metadata migration to `KvStack`-shaped overlays is the natural validation use case for the design and can be tackled in the same release that ships `KvStack`, since consolidated metadata is independently being reconsidered (see the [README's consolidated-metadata section](../README.md#consolidated-metadata)).

### Open questions

- **`bytes` vs `str` for `KeyRange` bounds.** TensorStore uses `bytes` for `KeyRange.inclusive_min` and `exclusive_max` ([KvStore.KeyRange](https://google.github.io/tensorstore/python/api/tensorstore.KvStore.KeyRange.html), documented as "half-open interval of byte string keys, according to lexicographical order"). The byte-typed choice is principled: successor functions ("next key after `p`"), cloud-backend wire comparison (S3 / GCS / Azure compare keys lexicographically as UTF-8 bytes, not as unicode codepoints), and sentinels for "highest possible key" (`b'\xff' * N`) are all cleanly expressible for bytes and ad-hoc for unicode strings. The kludge in `KeyRange.from_prefix` above (the `'￿'` fallback for the high end of unicode) is the visible symptom of using `str`. zarr-python's protocol uses `str` keys throughout, which is consistent with current practice and matches Zarr V3 spec keys (which are ASCII-restricted, so the str/bytes equivalence is faithful). Revisit if non-ASCII keys ever become a real use case, or if the `KeyRange.from_prefix` corner case bites a real user. The migration would be additive: a `bytes`-typed parallel API alongside the `str`-typed one, with the `str` version converting at the boundary.
- **Fall-through composition.** `KvStack` requires disjoint ranges. The migration pattern "read from new, fall through to old on miss" wants overlapping ranges with priority. That is a different wrapper (`Layered[S]` or `Fallthrough[S]`) and a different composition algebra. Out of scope here; flag for a follow-up if the migration use case becomes load-bearing. The conservative interim is "manage the migration with disjoint key prefixes and a `KvStack`," which is enforceable by a one-time backfill.
- **Per-layer prefix transformation.** TensorStore's `kvstack` driver supports per-layer prefix-stripping (a layer's underlying store sees keys with the layer's prefix removed). zarr-python's design with prefix-on-the-backend makes this less necessary — each layer can carry its own prefix internally — but a `subtract_prefix` constructor option may still be useful for layers wrapping shared backends. Out of scope for the initial wrapper; revisit if real use cases need it.
- **List ordering with prefix-stripping wrappers.** If a layer presents post-prefix keys but the composite lists pre-prefix keys, the merge has to re-add the prefix before yielding. The straightforward case (no prefix transformation) is unambiguous; the prefix-stripping case is one open question deeper.
- **Cross-layer transactions.** A `Transactional[KvStack[Transactional[S]]]` writes that span layers cannot be atomic without a coordinator. Document that transactions are per-layer; multi-layer atomicity is out of scope (the cross-store-transactions point already in the [transactional proposal](./stores-transactional.md#open-questions) covers this).
- **Empty stack semantics.** `KvStack([])` is a store that owns no keys. Every operation raises `KeyError`. Useful as a degenerate base case for programmatic construction; document it as well-defined rather than an error.
- **`KeyRange` representation for non-string keys.** The current spec assumes lex-ordered string keys, which matches the rest of the storage protocol. If the storage protocol ever supports non-string keys (bytes, structured), `KeyRange` would need to generalize. Punt; revisit if the underlying assumption changes.

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
