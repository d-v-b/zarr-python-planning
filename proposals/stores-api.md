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
from dataclasses import dataclass

# `Generation` is the per-key, opaque, backend-produced token that
# identifies a particular state of a key. ETag for HTTP backends, mtime
# for filesystems, a snapshot id for transactional backends. Treated as
# `object` at the protocol layer; equality is the only operation defined
# on it. See stores-transactional.md for the full contract.
Generation = object

@dataclass(frozen=True)
class ReadResult:
    """The return value of `Get.get` and friends. Carries the value plus
    the key's current generation so callers can revalidate cheaply with
    `if_not_match=` on a subsequent read."""
    value: memoryview
    generation: Generation

@dataclass(frozen=True)
class PutResult:
    """The return value of `Put.put`. Carries the post-write generation
    so callers can chain conditional writes (`if_match=prior.generation`)
    without re-reading the key.

    `applied=False` means a conditional write's precondition failed.
    In that case `generation` reports the *current* generation of the
    key (so the caller can compare to what they expected and decide
    whether to retry), and the stored value is unchanged.

    `generation=None` with `applied=True` means the backend has no
    notion of object identity (e.g. a barebones `MemoryStore` with no
    generation counter). Such backends cannot support conditional
    writes; they raise `TypeError` if `if_match=` is provided."""
    generation: Generation | None = None
    applied: bool = True

@runtime_checkable
class Get(Protocol):
    def get(
        self,
        key: str,
        *,
        if_not_match: Generation | None = None,
    ) -> ReadResult: ...

@runtime_checkable
class GetRange(Protocol):
    def get_range(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
        if_not_match: Generation | None = None,
    ) -> ReadResult: ...

@runtime_checkable
class GetRanges(Protocol):
    """Batch range read. Backends that support this natively (S3 cat_ranges,
    obstore get_ranges) advertise it; a `RangeCoalescing` wrapper synthesizes
    it for backends that only have `GetRange`. Returns one `ReadResult` per
    requested range; all results share the same generation since they come
    from the same underlying object read."""
    def get_ranges(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
        if_not_match: Generation | None = None,
    ) -> Sequence[ReadResult]: ...

@runtime_checkable
class Put(Protocol):
    def put(
        self,
        key: str,
        value: bytes | memoryview,
        *,
        if_match: Generation | None = None,
        if_none_match: bool = False,
    ) -> PutResult: ...

@runtime_checkable
class Delete(Protocol):
    def delete(
        self,
        key: str,
        *,
        if_match: Generation | None = None,
    ) -> None: ...

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
    atomicity and conditional writes are properties of `Put` (via
    `if_match`) and do not require this protocol.

    Adopts TensorStore's external-transaction model: a free-standing
    `Transaction` object is bound to a store with `store.with_transaction(txn)`,
    which returns a view of the store whose writes flow into `txn`.
    Two boolean knobs (`atomic` and `repeatable_read`) on `Transaction`
    span the isolation/atomicity space.

    Full design (Transaction object, repeatable-read semantics, per-backend
    support matrix, composition rules) is in
    [stores-transactional.md](./stores-transactional.md)."""
    def with_transaction(self, txn: "Transaction") -> "Self": ...

@runtime_checkable
class Serializable(Protocol):
    """The store can produce a portable declaration of itself — enough
    *configuration* for a different process (or a different language
    runtime) to reconstruct an equivalent store pointing at the same
    backend. This is store identity and connection info (an S3 URL with
    credential reference, a filesystem path, an fsspec URL plus storage
    options), not the contents of the store. The store's data lives
    where it always lived; the declaration just describes how to talk
    to it.

    Required for cross-engine portability: alternative engines like
    `zarr.engines.zarrs` and `zarr.engines.tensorstore` run in native
    code (or via FFI), so they need to materialize their own equivalent
    of the user's store on the other side of the language boundary.
    See [functional-core.md § The direction](./functional-core.md#the-direction)
    and [performance.md § Wrapping zarrs and TensorStore as alternative engines](./performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines).

    Also useful for pickling stores across Dask workers, persisting
    store configuration in URL form, and round-tripping store identity
    in test fixtures.

    The method names `to_declaration` / `from_declaration` here are
    illustrative. What this proposal commits to is the *capability* —
    "stores can serialize their identity and configuration to a portable
    data format that another runtime can reconstruct from" — not the
    spelling. The final method names, the exact shape of
    `StoreDeclaration`, and the registration mechanism for reconstructing
    a store from one are open questions to be settled at implementation
    time."""

    def to_declaration(self) -> "StoreDeclaration": ...

    @classmethod
    def from_declaration(cls, declaration: "StoreDeclaration") -> "Self": ...

@dataclass(frozen=True)
class StoreDeclaration:
    """Portable description of a store's identity and connection
    configuration. Sketch; the field set is illustrative.

    - `kind` identifies the backend type (e.g. `"local"`, `"s3"`,
      `"memory"`, `"zip"`, `"fsspec"`).
    - `config` is the backend-specific reconstruction payload, keyed by
      `kind`. For `"local"`, the path; for `"s3"`, the bucket plus
      region plus prefix plus credential reference; for `"fsspec"`, the
      URL plus storage options. Must be JSON-round-trippable.

    This describes *how to connect* to a store, not the data in the
    store. Per-key contents and per-key generations are unrelated; this
    is store-identity-as-data.

    Alignment with [obstore's URL+config pattern](https://developmentseed.org/obstore/)
    and TensorStore's [Spec](https://google.github.io/tensorstore/spec/index.html)
    is the target; the exact shape will be specified once one external
    engine integration drives the field set."""

    kind: str
    config: dict[str, object]

@dataclass
class ListResult:
    """The return value of `ListWithDelimiter.list_with_delimiter`.
    `objects` are the keys directly under `prefix`; `prefixes` are
    common-prefix strings that name "subdirectory"-style groupings."""
    objects: Sequence[str]
    prefixes: Sequence[str]

@dataclass(frozen=True)
class ObjectMetadata:
    """The return value of `Head.head`. Subset of cloud-store object
    metadata that is portable across S3/GCS/Azure/local.

    `generation` is the per-key opaque token; `size_bytes` is the
    object's length in bytes; `last_modified` is a UNIX timestamp in
    seconds, or `None` if the backend doesn't track it."""
    generation: Generation
    size_bytes: int
    last_modified: float | None

# Async variants (`GetAsync`, `GetRangeAsync`, `GetRangesAsync`, `PutAsync`,
# `DeleteAsync`, `ListAsync`, `ListWithDelimiterAsync`, `HeadAsync`,
# `CopyAsync`) follow the same shape with `async def` and an `_async`
# method-name suffix. Backends pick whichever flavor matches their
# underlying I/O model; the sync/async bridge is a wrapper, not a subclass.
# See the README's sync-by-default subsection for the per-backend mapping.
```

## Streaming and caller-allocated reads via `GetStreaming`

`Get`, `GetRange`, and `GetRanges` follow an allocation-based contract: the store allocates the result buffer, fills it, and returns it. This is the right shape for the common case (small reads where the store knows the size up front) and matches every role-model storage API: TensorStore's `KvStore.read` allocates ([KvStore.read](https://google.github.io/tensorstore/python/api/tensorstore.KvStore.read.html)), zarrs's `ReadableStorageTraits::get` allocates ([ReadableStorageTraits](https://docs.rs/zarrs_storage/latest/zarrs_storage/trait.ReadableStorageTraits.html)), zarrita's `Readable.get` allocates, obstore's `get` allocates.

But the allocation-based contract leaves three problems on the table:

1. **Device-agnostic IO is fictional.** Today's `prototype: BufferPrototype` argument was an attempt to let the caller specify "give me back a buffer of this kind" — most visibly to support GPU destinations — but the [decoupling-prototype subsection in stores.md](./stores.md#decoupling-prototype-from-the-read-api) acknowledges that the non-CPU path doesn't actually wire up: even with `gpu_buffer_prototype`, bytes hit the CPU first because the store doesn't know how to allocate on the device. The right shape is the opposite: stop asking the store to allocate at all, and let the caller hand the store a destination buffer of whatever kind they want. See [gpu.md § Device-agnostic IO](./gpu.md) for the broader framing — GPU support is one application of this; CPU pre-allocated buffers (the most common use) is another.
2. **Values that exceed memory.** A 100 GiB shard cannot be read into a `bytes`/`memoryview` in one shot. The current API forces the caller to use `GetRange` to manually pull slice-by-slice, which is awkward and loses any pipelining benefit the backend could offer.
3. **Pipelined decode.** A network read of a multi-MiB shard delivers bytes incrementally over hundreds of milliseconds. The codec pipeline could start decoding the first chunk while the last chunk is still in flight. The one-shot `Get` blocks the caller from any of this; today's zarr-python collects the full payload before any downstream code runs.

The honest design that addresses all three is a streaming protocol where the caller provides the destination buffer and pumps chunks through. The destination is whatever satisfies the buffer protocol (or the device-side equivalent — CUDA Array Interface, DLPack); the store does not introspect what kind of buffer it is. This is the shape zstd's streaming API takes ([zstd manual](https://facebook.github.io/zstd/zstd_manual.html), `ZSTD_decompressStream`): both ends are caller-owned, both have explicit cursors, the callee advances both. It is also the shape Python's `io.RawIOBase.readinto` takes for in-process streams.

We adopt it for stores: `GetStreaming` returns a `ReadStream` that the caller drains chunk-by-chunk into a writable buffer. A `read_full(key, buffer)` convenience covers the one-shot case (caller knows the size up front) without duplicating the protocol family.

This is opt-in additive surface alongside `Get`, not a replacement.

### Capability protocols

```python
# zarr/storage/protocols.py (continued)

@runtime_checkable
class GetStreaming(Protocol):
    """Open a streaming read. Returns a `ReadStream` whose `read_into`
    method the caller calls repeatedly to drain chunks into a
    caller-provided writable buffer.

    Backends that hold open a connection or file handle for the
    duration of the read implement this directly (HTTP chunked
    transfer, S3 streaming GET, file handle, mmap region). The
    backend owns connection lifetime via the stream's context-manager
    protocol; the caller owns the destination buffer.

    Backends that can DMA directly into the destination buffer
    (CUDA-aware HTTP, NVIDIA GDS, kvikio-backed storage) avoid the
    intermediate CPU buffer entirely. Backends without that capability
    fall back to read-then-copy at the FFI boundary; the protocol is
    honest about which path each backend takes via the
    `ZeroCopyGetStreamingSpec` (see Conformance).

    The one-shot read pattern is `stream.read_full(buffer)`, which
    fills the buffer in a single drain and raises if the value is
    larger. It covers the simple "caller knows the size up front"
    case without a separate protocol."""

    def get_streaming(self, key: str) -> "ReadStream": ...


@runtime_checkable
class GetRangeStreaming(Protocol):
    def get_range_streaming(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> "ReadStream": ...


@runtime_checkable
class GetRangesStreaming(Protocol):
    """Batch streaming range read. Returns one ReadStream per range
    (in input order), or a single multiplexed ReadStream that
    demultiplexes per-range when drained. The latter is the
    `RangeCoalescing` wrapper's preferred shape because one
    underlying connection serves all ranges; see [stores-range-coalescing.md](./stores-range-coalescing.md)."""

    def get_ranges_streaming(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
    ) -> Sequence["ReadStream"]: ...


# Async variants follow the same shape with `async def`, `_async`
# method-name suffixes (`GetStreamingAsync`, `GetRangeStreamingAsync`,
# `GetRangesStreamingAsync`), and an `AsyncReadStream` whose
# `read_into_async` returns an awaitable.
```

### `ReadStream`

```python
class ReadStream:
    """Stateful streaming-read handle. Holds a connection, file
    descriptor, or cursor. Use as a context manager to ensure cleanup
    (network sockets, file handles, mmap regions all need explicit
    release).

    Modeled on Python's `io.RawIOBase` plus a generation field, with
    the `readinto`-shaped contract: each call writes into a
    caller-provided buffer and returns the number of bytes written;
    zero means end of stream."""

    @property
    def generation(self) -> "Generation | None":
        """The value's generation, captured at stream open. Stable
        for the lifetime of the stream. Calls to `read_into` after
        the stream is opened do not change this value; if the
        underlying object changes mid-stream, the backend either
        raises (preferred, for backends that detect it) or silently
        delivers stale bytes (documented for backends that cannot)."""

    @property
    def total_size(self) -> int | None:
        """The total size of the stream's value, if known up front.
        None for backends that don't know (HTTP without
        Content-Length). Callers can use this to size scratch buffers
        appropriately for `read_full`-style consumption."""

    def read_into(self, buffer: "WritableBuffer") -> int:
        """Read up to `len(buffer)` bytes into `buffer`, starting at
        offset 0. Returns the number of bytes written. Returns 0 at
        end-of-stream.

        The buffer must expose the writable buffer protocol (see
        WritableBuffer). The store writes into the prefix
        `[0, returned_count)`; bytes past the prefix are untouched."""

    def read_full(self, buffer: "WritableBuffer") -> int:
        """Drain the entire remaining stream into `buffer`. Returns
        the total bytes written.

        Raises ValueError if the stream's remaining size exceeds the
        buffer (no partial fill on this contract — partial fill is
        the job of `read_into`).

        This is the one-shot convenience that covers the common case
        of "I know the size up front, give me the bytes."""

    @property
    def closed(self) -> bool: ...

    def close(self) -> None:
        """Release any held resources. Idempotent. After close,
        further `read_into` raises."""

    def __enter__(self) -> "Self": ...
    def __exit__(self, *exc) -> None: ...


class AsyncReadStream:
    """Async variant. Same shape with `async def` on read_into / read_full,
    `__aenter__` / `__aexit__` for context-manager use."""

    @property
    def generation(self) -> "Generation | None": ...
    @property
    def total_size(self) -> int | None: ...

    async def read_into_async(self, buffer: "WritableBuffer") -> int: ...
    async def read_full_async(self, buffer: "WritableBuffer") -> int: ...

    async def aclose(self) -> None: ...
    async def __aenter__(self) -> "Self": ...
    async def __aexit__(self, *exc) -> None: ...
```

`WritableBuffer` is anything that exposes the *writable* buffer protocol. Concretely: `bytearray`, a writable `memoryview`, `numpy.ndarray` (writable), `cupy.ndarray` via `__cuda_array_interface__`, a `torch.Tensor` via `__cuda_array_interface__` or `__dlpack__`, an mmap. The protocol does not pin a single concrete type; the conformance suite tests against `bytearray` for the baseline and adds CUDA-array-interface tests for backends that advertise GPU-direct support.

```python
WritableBuffer = TypeAlias  # the union of supported writable buffer-protocol types
# In practice: anything where memoryview(b).readonly is False, OR
# anything with a __cuda_array_interface__ / __dlpack__ exposing a
# writable region. Spelled out concretely in the runtime check.
```

### Buffer ownership contract

Five rules, all enforceable by the conformance suite:

1. **The buffer is fully caller-owned.** The store does not retain a reference past the return of `read_into` / `read_full`. The store does not free or modify the buffer outside the prefix it writes. This is the inverse of the `Get` contract (where the *store* owns the returned `memoryview`'s backing).

2. **`read_into` writes into the prefix `[0, returned_count)` of the buffer.** Bytes past `returned_count` are untouched. The caller learns how many bytes were written from the return value, not from the buffer length.

3. **`read_into` may write fewer bytes than the buffer size.** A short return is *not* end-of-stream — only a zero return means EOS. Callers must loop until they see zero. (This matches `os.read` and `io.RawIOBase.readinto` exactly; the contract is well-known.)

4. **`read_full` raises `ValueError` if the stream's remaining bytes exceed the buffer.** No partial fill on `read_full`; partial fill is what `read_into` is for.

5. **The stream must be closed.** Either via context manager (`with` / `async with`) or explicit `close()`. Failing to close leaks the underlying connection / file handle. The conformance suite asserts that `close()` is idempotent and that double-close does not raise.

The contract is unambiguous about EOS: zero bytes returned from `read_into` means the stream is exhausted. Backends that have a `total_size` available expose it for callers who want to size scratch buffers up front; backends that don't (HTTP without Content-Length, chunked transfer encodings) leave it as `None`.

### One-shot via `read_full`

The common "caller knows the size up front" case — fill this buffer in one call — is `read_full`:

```python
with store.get_streaming("zarr.json") as stream:
    n = stream.read_full(buf)
    # buf[:n] holds the value; the read's generation is stream.generation
```

No separate `get_into`-shaped protocol is needed; the one-shot pattern is one call on the streaming surface.

The slight syntactic overhead (one extra line for the context manager) buys uniform handling of small and large reads. Callers who want a `get_into`-style convenience can wrap once:

```python
def get_into(store: GetStreaming, key: str, buffer: WritableBuffer) -> ReadResult:
    with store.get_streaming(key) as stream:
        n = stream.read_full(buffer)
        return ReadResult(value=memoryview(buffer)[:n], generation=stream.generation)
```

This helper lives in `zarr.storage.helpers` for callers who don't want to manage streams. Behind it, every read is a stream; the one-shot interface is just sugar.

### Streaming for values larger than memory

```python
# Stream a 100 GiB shard through a 1 MiB scratch buffer.
buf = bytearray(1 << 20)
with store.get_streaming("huge-shard") as stream:
    while True:
        n = stream.read_into(buf)
        if n == 0:
            break
        consume(buf[:n])
# Total memory used: 1 MiB. No need to materialize the whole value.
```

This is the load-bearing case a one-shot read into a sized buffer cannot handle: the value's size is not known up front, or the value is larger than memory. Combined with codec-pipeline streaming (a separate proposal), it lets zarr-python read shards that don't fit in memory.

### Streaming for pipelined decode

```python
# Decode chunks as they arrive from the network.
buf = bytearray(1 << 20)
decoder = ChunkDecoder(...)
with store.get_streaming("shard.zarr") as stream:
    while True:
        n = stream.read_into(buf)
        if n == 0:
            break
        decoder.feed(buf[:n])  # decoder emits chunks as boundaries are crossed
for chunk in decoder.flush():
    process(chunk)
```

The decoder works on bytes as they arrive. End-to-end latency drops from "network full delivery + decode time" to "first chunk arrival + per-chunk decode time." This is what zarrs and TensorStore do internally; exposing it at the store layer in zarr-python lets the array/codec layers take advantage.

### Device-agnostic destinations (GPU as one example)

The protocol does not care what kind of buffer the caller provides; it just calls `read_into` on whatever satisfies the buffer protocol (or the device-side equivalents — `__cuda_array_interface__`, `__dlpack__`). A CPU read into a pre-allocated `bytearray`, a CPU read into a numpy view of a larger output array, and a GPU read into a CuPy buffer are the same call shape:

```python
import cupy as cp

# CPU pre-allocated destination (the common case): no per-read allocation.
buf = bytearray(shard_size)
with store.get_streaming("c/0/0") as stream:
    n = stream.read_full(buf)

# GPU destination: same call, different buffer.
buf = cp.empty(shard_size, dtype=cp.uint8)
with gds_store.get_streaming("c/0/0") as stream:
    n = stream.read_full(buf)
# A GDS-aware backend DMAs directly into GPU memory; backends without
# device awareness fall back to "read into temp, memcpy into caller
# buffer" with the documented copy. Either way, the protocol shape is
# the same and the caller doesn't have to branch on device type.
```

See [gpu.md](./gpu.md) for the broader framing of *why* the protocol is shaped this way — device-agnostic IO is the goal, and GPU support falls out as a consequence of stores accepting whatever buffer the caller provides.

### Backend support

| Backend | Implements `GetStreaming`? | Notes |
|---|---|---|
| `LocalStore` | yes (open file handle, `os.read` into buffer) | Trivial; no special GPU path |
| `MemoryStore` | yes (memoryview slice over internal bytes) | Stream is a thin cursor; closes are no-op |
| `ZipStore` | yes (`zipfile.ZipFile.open(...)` returns a stream) | CPU-only |
| `FsspecStore` | yes when fs supports it | Most async fsspec backends expose a streaming Body; sync fsspec backends often allocate. Per-fs |
| `ObstoreStore` | yes (obstore exposes a streaming Body via `get_async`) | Existing API maps directly |
| Future GDS-aware obstore | yes (DMA into device buffer when buffer exposes `__cuda_array_interface__`) | The motivating GPU use case |
| Future `KvikioStore` | yes (kvikio-native; bypasses CPU entirely for `cupy` and similar) | Slot reserved |

`MemoryStore` and `LocalStore` (without mmap) implement `read_into` as a memcpy from internal storage to caller buffer; this is API-uniform with the network case but does not deliver zero-copy from the backend's storage. Backends opt into the conformance suite's `ZeroCopyGetStreamingSpec` (see below) only when they can pass it.

Network backends (`ObstoreStore`, async `FsspecStore` over HTTP / S3 / GCS / Azure) are the ones that gain the most from the streaming surface: they get pipelined delivery instead of allocate-and-block, which is the pipelined-decode payoff.

### Composition with wrappers

- **`Caching[GetStreaming]`**: the design is *resolvable* — streaming stores let the cache capture bytes incrementally as they flow through (the cache wraps `read_into` to write into both the caller's buffer and a cache-side buffer, then commits on stream completion). The detailed specification — including the dropped-stream correctness handling called out in the [open question below](#open-questions) — is deferred to [stores-caching.md](./stores-caching.md). Until that section lands, treat `Caching[GetStreaming]` as documented-but-not-yet-specified.
- **`RangeCoalescing[GetRangeStreaming]`**: works, with the wrapper opening one underlying stream against the coalesced byte range and demultiplexing per-range slices to caller-provided buffers as they arrive. The wrapper's `get_ranges_streaming` returns a `Sequence[ReadStream]`; each per-range stream draws from the shared underlying stream's buffer in offset order. This is genuinely more efficient than the one-shot version for sharded reads from cloud storage — the caller can start decoding the first range's chunks before the last range's bytes have arrived. Algorithm sketch in [stores-range-coalescing.md](./stores-range-coalescing.md), pending an updated subsection.
- **`Transactional[GetStreaming]`**: orthogonal. `GetStreaming` is read-side; transactions are write-side. Reads inside a transaction stream the same way they do outside. Generations recorded on stream open, not on each `read_into` call.
- **`ReadOnly[GetStreaming]`**: passes through. `GetStreaming` is a read capability; `ReadOnly` does not strip read capabilities.
- **`Prefixed[GetStreaming]`**: passes through.
- **`Tracing[GetStreaming]`**: works; one span per `get_streaming(key)` call covering the entire stream lifetime, with attributes for total bytes consumed, number of `read_into` calls, and time-to-first-byte. The span attribute set adds `zarr.store.buffer_kind` (`"cpu"` / `"cuda"` / `"unknown"`) inferred from whether the buffer exposes `__cuda_array_interface__`.

### Conformance

Three new specs land in [stores-conformance.md](./stores-conformance.md):

- **`GetStreamingSpec`** parameterizes over backends that satisfy `GetStreaming`. Asserts that draining a stream produces the same bytes as `Get` would; `read_into` returns 0 at EOS; `read_into` may return less than the buffer size and that's not EOS; `read_full` raises if the buffer is too small; the stream is properly closed via context manager; `total_size` matches the value's actual size when reported; `generation` is stable across calls within a single stream.
- **`GetRangeStreamingSpec`** mirrors `GetRangeSpec` with streaming semantics. Asserts that `start`/`end`/`length` route to the correct byte range; that the stream is exactly that long; that empty ranges yield zero-length streams; that out-of-range requests raise on stream open (not on first `read_into`).
- **`ZeroCopyGetStreamingSpec`** is separately opt-in. A backend advertises this spec only when it can guarantee that the destination buffer is the memory the backend wrote, not a copy. The test creates a buffer, drains a stream into it, mutates a byte of the *backend's* internal storage (via a backend-specific hook), and asserts the caller's buffer reflects the change. Backends like `MemoryStore` (where the backend's storage can be the caller's buffer) and `LocalStore` with mmap can opt in; `FsspecStore` and copy-based backends do not. This spec is what makes "zero-copy" a falsifiable claim.

### Worked examples

```python
# 1) Device-agnostic read into a CuPy buffer (GPU as one example of a
# caller-allocated destination; assumes a GDS-aware obstore variant).
import cupy as cp
from zarr.storage.stores.obstore import GDSObstoreStore

store: GetStreaming = GDSObstoreStore(...)
buf = cp.empty(shard_size, dtype=cp.uint8)
with store.get_streaming("c/0/0") as stream:
    n = stream.read_full(buf)
# `buf` holds the shard's bytes on the GPU. No CPU bounce.
# `stream.generation` is the S3 ETag at read time.

# 2) Stream a value larger than memory through a 1 MiB scratch buffer.
buf = bytearray(1 << 20)
total = 0
with store.get_streaming("huge-shard") as stream:
    while True:
        n = stream.read_into(buf)
        if n == 0:
            break
        process(buf[:n])
        total += n

# 3) Pipelined decode of a sharded array.
buf = bytearray(4 << 20)
decoder = ShardDecoder(...)
with store.get_streaming("shard.zarr") as stream:
    while True:
        n = stream.read_into(buf)
        if n == 0:
            break
        decoder.feed(buf[:n])
for chunk in decoder.finish():
    yield chunk
# Time-to-first-chunk is bounded by network TTFB + decode of the first
# chunk's bytes, not by full shard delivery.

# 4) One-shot read of metadata via the read_full convenience.
buf = bytearray(metadata_size)  # size known from prior head() or schema
with store.get_streaming("zarr.json") as stream:
    stream.read_full(buf)
# `buf` holds the metadata.

# 5) Range-coalesced streaming read of multiple chunks from a shard.
from zarr.storage.wrappers import RangeCoalescing

store = RangeCoalescing(GDSObstoreStore(...))
streams = store.get_ranges_streaming(
    "shard.zarr",
    starts=starts,
    lengths=lengths,
)
# Each stream draws from a shared coalesced underlying stream. Drain
# them in order; the wrapper handles fan-out from the shared buffer.
for stream, target in zip(streams, target_buffers):
    with stream:
        stream.read_full(target)
```

### Migration

This subsection's commitments are additive:

- The `GetStreaming` / `GetRangeStreaming` / `GetRangesStreaming` protocols are new.
- `ReadStream` is a new class.
- The `prototype: BufferPrototype` argument on existing `Get` methods continues to be deprecated per the [README's decoupling-prototype subsection](../README.md#decoupling-prototype-from-the-read-api).
- No backend is required to implement `GetStreaming` in the initial release. The protocol is the slot for streaming-capable backends.
- `LocalStore` and `MemoryStore` can implement `GetStreaming` for free (open file handle, slice over internal bytes); shipping these as the reference implementations validates the protocol shape.
- `ObstoreStore` and async-fsspec backends are the ones that benefit most; their existing streaming APIs map directly onto `read_into`.

`GetStreaming` is the device-agnostic IO surface, shaped so that the caller (not the store) chooses the destination — GPU is one application; pre-allocated CPU buffers are the more common one. See [gpu.md](./gpu.md) for the broader framing.

### Open questions

- **`WritableBuffer` typing.** The protocol's argument type is informally "anything writable-buffer-protocol-compatible." A precise Python type for this does not exist in the standard library; the closest is `collections.abc.Buffer` (3.12+) but that does not distinguish writable from read-only at the type level. The pragmatic choice is to type the argument as `Any` and rely on a runtime `memoryview(buffer).readonly is False` check, with a separate path for `__cuda_array_interface__` buffers. Worth tracking; not a blocker.
- **Stream lifetime under async cancellation.** An `async with stream:` block that is cancelled mid-drain should release the underlying connection cleanly. Most async backends handle this via `__aexit__`, but partial reads on cancellation are a contract worth pinning: the buffer's prefix is whatever was drained before cancellation, and the stream is closed. Document explicitly.
- **`total_size=None` semantics.** Backends that don't know the total size up front (HTTP without Content-Length, chunked transfer) leave `total_size` as None. Callers who want to call `read_full` with a sized buffer have to either know the size from elsewhere (manifest, prior `head()`) or use `read_into` in a loop. This is unavoidable; the protocol cannot synthesize a size the backend doesn't know.
- **Generation stability mid-stream.** The contract says `generation` is stable for the lifetime of the stream. Backends that detect mid-stream changes (HTTP `If-Match` failure, S3 ETag drift) should raise rather than deliver inconsistent bytes. Backends that cannot detect (fsspec over a backend without versioning) document the limitation. Worth a per-backend audit.
- **`Caching[GetStreaming]` cache-fill correctness.** The streaming-cache pattern captures bytes into a cache entry as they flow through. If the caller drops the stream mid-drain, the cache entry is incomplete and must not be served on subsequent reads. Provisional design: the cache wrapper marks entries as "in progress" until the stream closes successfully; partial entries are discarded. Owed in [stores-caching.md](./stores-caching.md); not yet written there.
- **Pipelined decode integration.** The streaming surface is necessary but not sufficient for pipelined decode; the codec pipeline also has to be streaming-capable. That work belongs in the [Codecs section of the README](../README.md#codecs). The store-layer protocol is shipped first; codec adoption follows.
- **Backwards-compatible shim.** During the migration window, the existing `Buffer`-returning `Get.get` methods can be implemented in terms of `GetStreaming` (open stream, read_full into a bytearray, wrap as Buffer). This means a backend can ship `GetStreaming` first and get the legacy surface for free. Worth flagging as the recommended migration order.
- **Cursor-style alternative for local backends.** A `GetIntoStreaming` protocol with explicit `(buffer, source_offset, dest_offset)` cursors would suit local-only backends (LocalStore, MemoryStore) better than the stateful `ReadStream`, because there's no connection to hold open. Stays open as a future addition if a real performance gap emerges; the stream-with-trivial-state pattern is fine for v1.

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

    def get(
        self: "KvStack[Get]",
        key: str,
        *,
        if_not_match: Generation | None = None,
    ) -> ReadResult:
        return self._route(key).get(key, if_not_match=if_not_match)

    def put(
        self: "KvStack[Put]",
        key: str,
        value: bytes | memoryview,
        *,
        if_match: Generation | None = None,
    ) -> PutResult:
        return self._route(key).put(key, value, if_match=if_match)

    def delete(
        self: "KvStack[Delete]",
        key: str,
        *,
        if_match: Generation | None = None,
    ) -> None:
        self._route(key).delete(key, if_match=if_match)

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

# 5) Composite hierarchy from multiple stores — the session-time
# replacement for "hierarchy links" (see missing-apis.md § 1). One
# logical hierarchy assembled from two backing stores, with a
# subdirectory served from somewhere else.
#
# Equivalent to "creating an external link at /experiments/2026 that
# points at the other store", but without persisting any link object.
# The composition lives in the user's open-time code; nothing is
# written to either store.
store = KvStack([
    (KeyRange.from_prefix("experiments/2026/"),
     Prefixed(ObstoreStore(s3_2026_bucket), "")),
    (KeyRange.complement_of_prefix("experiments/2026/"), main_store),
])
# zarr.open(store) sees a single tree; reads under experiments/2026/
# go to S3, everything else stays local.
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

    def get(
        self: "Prefixed[Get]",
        key: str,
        *,
        if_not_match: Generation | None = None,
    ) -> ReadResult:
        return self._inner.get(_join(self._prefix, key), if_not_match=if_not_match)

    def get_range(
        self: "Prefixed[GetRange]",
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
        if_not_match: Generation | None = None,
    ) -> ReadResult:
        return self._inner.get_range(
            _join(self._prefix, key), start=start, end=end, length=length,
            if_not_match=if_not_match,
        )

    def get_ranges(
        self: "Prefixed[GetRanges]",
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
        if_not_match: Generation | None = None,
    ) -> Sequence[ReadResult]:
        return self._inner.get_ranges(
            _join(self._prefix, key), starts=starts, ends=ends, lengths=lengths,
            if_not_match=if_not_match,
        )

    def put(
        self: "Prefixed[Put]",
        key: str,
        value: bytes | memoryview,
        *,
        if_match: Generation | None = None,
    ) -> PutResult:
        return self._inner.put(_join(self._prefix, key), value, if_match=if_match)

    def delete(
        self: "Prefixed[Delete]",
        key: str,
        *,
        if_match: Generation | None = None,
    ) -> None:
        self._inner.delete(_join(self._prefix, key), if_match=if_match)

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

    def with_transaction(
        self: "Prefixed[Transactional]", txn: "Transaction"
    ) -> "Prefixed[Transactional]":
        return Prefixed(self._inner.with_transaction(txn), self._prefix)

    # Async variants follow exactly the same shape with `async def` and
    # `self: Prefixed[GetAsync]`-style annotations, returning ReadResult /
    # PutResult per the protocol surface above.
    async def get_async(
        self: "Prefixed[GetAsync]",
        key: str,
        *,
        if_not_match: Generation | None = None,
    ) -> ReadResult:
        return await self._inner.get_async(_join(self._prefix, key), if_not_match=if_not_match)

    # ... and so on for get_range_async, get_ranges_async, put_async,
    # delete_async, list_async, list_with_delimiter_async, head_async,
    # copy_async. About sixty lines total for the full sync + async surface.
```

The same self-type-narrowing pattern carries through to the other wrappers in the [Wrappers section below](#wrappers): `ReadOnly[S]` simply omits the write methods (`put`, `delete`, `copy`), so calls to them fail at type-check time as "attribute does not exist." `with_transaction` is preserved. `Caching[S]`, `Retry[S]`, `Tracing[S]` use the same `self: Caching[Get]` / `self: Retry[Put]` annotations to make every preserved capability conditionally available based on what S satisfies. `RangeCoalescing[S]` is the one wrapper that actively *adds* a capability beyond S's surface (synthesizing `GetRanges` from `GetRange`), so its `get_ranges` method is unconditional rather than self-type-narrowed.

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
    Transactional (via rename-into-place), Serializable."""

    def __init__(self, root: Path | str, *, mkdir: bool = False) -> None: ...
    def get(self, key: str, *, if_not_match: Generation | None = None) -> ReadResult: ...
    def get_range(self, key: str, *, start: int, end: int | None = None, length: int | None = None, if_not_match: Generation | None = None) -> ReadResult: ...
    def get_ranges(self, key: str, *, starts: Sequence[int], ends: Sequence[int] | None = None, lengths: Sequence[int] | None = None, if_not_match: Generation | None = None) -> Sequence[ReadResult]: ...
    def put(self, key: str, value: bytes | memoryview, *, if_match: Generation | None = None) -> PutResult: ...
    def delete(self, key: str, *, if_match: Generation | None = None) -> None: ...
    def list(self, prefix: str | None = None, *, offset: str | None = None) -> Iterator[str]: ...
    def list_with_delimiter(self, prefix: str | None = None) -> ListResult: ...
    def head(self, key: str) -> ObjectMetadata: ...
    def copy(self, src: str, dst: str) -> None: ...
    def with_transaction(self, txn: Transaction) -> "LocalStore": ...

    # Discovery sugar for the key-agnostic store-layer cache. Available
    # on every backend; forwards to the Caching constructor. Tier-aware
    # caching (metadata-on-default, chunks-opt-in) lives at the
    # hierarchy layer; see hierarchy-layer.md.
    def with_caching(self, **kwargs) -> "Caching[LocalStore]": ...
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
    # depends on the resolution of the open question below. All methods
    # use the same ReadResult / PutResult / Generation conventions as
    # LocalStore above.
    def get(self, key: str, *, if_not_match: Generation | None = None) -> ReadResult: ...
    def get_range(self, key: str, *, start: int, end: int | None = None, length: int | None = None, if_not_match: Generation | None = None) -> ReadResult: ...
    # ... rest of the read capability set, plus Put / Delete when mode
    # permits writes.
    def with_caching(self, **kwargs) -> "Caching[ZipStore]": ...

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
    # Full sync capability set. Signatures match LocalStore's (ReadResult
    # / PutResult / Generation), plus `with_transaction(txn)` and
    # `with_caching(...)`.
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
    async def get_async(self, key: str, *, if_not_match: Generation | None = None) -> ReadResult: ...
    async def get_range_async(self, key: str, *, start: int, end: int | None = None, length: int | None = None, if_not_match: Generation | None = None) -> ReadResult: ...
    async def get_ranges_async(self, key: str, *, starts: Sequence[int], ends: Sequence[int] | None = None, lengths: Sequence[int] | None = None, if_not_match: Generation | None = None) -> Sequence[ReadResult]: ...
    async def put_async(self, key: str, value: bytes | memoryview, *, if_match: Generation | None = None) -> PutResult: ...
    async def delete_async(self, key: str, *, if_match: Generation | None = None) -> None: ...
    # ... rest of the async capability set, plus with_transaction_async.
    # `with_caching` returns a sync Caching wrapper around an
    # AsyncToSync-adapted self. The return type is `Caching[AsyncToSync[Self]]`,
    # not `Caching[Self]` — the inner store needs the sync surface that
    # AsyncToSync provides.
    def with_caching(self, **kwargs) -> "Caching[AsyncToSync[ObstoreStore]]": ...
    # For an async-throughout stack, use with_caching_async instead, which
    # returns CachingAsync[Self] without the AsyncToSync adapter.
    def with_caching_async(self, **kwargs) -> "CachingAsync[ObstoreStore]": ...
```

Note: `ObstoreStore` is async-only. Worked examples below that compose it with sync wrappers (`Retry`, `RangeCoalescing`, `Caching`) require an explicit `AsyncToSync(ObstoreStore(...))` step; `with_caching` on `ObstoreStore` performs this adaptation internally — **the returned object has a sync capability surface, not the original async surface**. Users building async-throughout pipelines should call `with_caching_async(...)` instead, which returns `CachingAsync[Self]` and preserves the async surface. Calling `.with_caching(...)` on an async backend silently collapses the pipeline to sync; the separate method names exist to make that choice explicit.

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

    async def get_async(self, key: str, *, if_not_match: Generation | None = None) -> ReadResult: ...
    # Full async capability set; all join sites use dereference_path.
    # Signatures otherwise match `ObstoreStore`'s, including the
    # with_caching / with_caching_async pair.
    def with_caching(self, **kwargs) -> "Caching[AsyncToSync[FsspecStore]]": ...
    def with_caching_async(self, **kwargs) -> "CachingAsync[FsspecStore]": ...
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
    """Strips the write methods (Put, Delete, Copy) from S's capability
    set. Preserves Transactional (read-only transactions are well-defined;
    see stores-transactional.md).
    See [stores-wrappers.md](./stores-wrappers.md#readonlys) for the
    self-type-narrowing implementation pattern."""
    def __init__(self, inner: S) -> None: ...

class Caching[S]:
    """Adds a key-agnostic in-memory LRU over S's read capabilities.
    Eviction by bytes or entries; optional TTL. Writes invalidate the
    cache. Unconditional in-flight request deduplication is provided by
    the shared substrate, not by this wrapper.

    Tier-aware caching (metadata-on-default, chunks-opt-in) lives at
    the hierarchy layer (see hierarchy-layer.md), not here. This
    wrapper does not classify keys.

    Caching strategy (cache exactly what was requested vs object-level
    promotion), eviction policy, write invalidation, recommended
    composition with `RangeCoalescing` and `Retry`, and the migration
    plan for `experimental.cache_store` are specified in
    [stores-caching.md](./stores-caching.md).

    `Caching(inner)` raises `TypeError` if `inner` advertises
    `Transactional`. The two cannot compose: a cache wrapped around a
    transactional store would surface stale (pre-commit) reads to
    callers outside the transaction. See [stores-transactional.md §
    Composition with other wrappers](./stores-transactional.md#composition-with-other-wrappers)
    for the symmetric refusal on the transactional side."""
    def __init__(
        self,
        inner: S,
        *,
        max_bytes: int = 256 << 20,        # 256 MiB
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
#
# Adopts TensorStore's external-transaction model. A free-standing
# Transaction object is created, bound to one or more stores via
# `store.with_transaction(txn)`, and committed once at the top of the
# call stack. Per-key conditional writes (`if_match=...`) and per-key
# atomicity (a property of `Put`) are independent of this protocol;
# `Transaction` is what gives you *multi-key* atomicity.

class Transaction:
    """A free-standing transaction context. Created outside any store,
    bound to stores via `store.with_transaction(txn)`. Two boolean knobs
    span the isolation/atomicity space. Full semantics, per-backend
    support matrix, and conflict-handling are in
    [stores-transactional.md](./stores-transactional.md)."""

    def __init__(
        self,
        *,
        atomic: bool = False,
        repeatable_read: bool = False,
    ) -> None: ...

    def commit(self) -> None: ...
    def abort(self) -> None: ...
    def __enter__(self) -> "Transaction": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool: ...

    async def commit_async(self) -> None: ...
    async def __aenter__(self) -> "Transaction": ...
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool: ...
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
# ro: Get & GetRange & List & Head & Transactional, but not Put/Delete/Copy

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
- **`Transactional` granularity.** Resolved as a single protocol with TensorStore's external-transaction shape: `store.with_transaction(txn)` binds a free-standing `Transaction(atomic=..., repeatable_read=...)` object to the store. Snapshot-isolation is `atomic=True, repeatable_read=True` on the same `Transaction` — no separate protocol. See [stores-transactional.md](./stores-transactional.md) for the full design, per-backend support matrix, and migration plan (including the V2 rename-into-place restoration for `LocalStore`).
- **Backwards compatibility window.** How long does the `Store` ABC remain importable? One major release? Two? Affects how aggressively wrappers can replace inheritance-based extension.
- **Return type.** Resolved in favor of `memoryview` over `bytes` and obspec's `Buffer`. See the [README subsection on returning `memoryview`](../README.md#returning-memoryview-from-store-read-methods) for the three-way comparison and the per-backend migration. The door stays open to upgrade to obspec's `Buffer` later if explicit lifetime semantics become necessary; the migration would be additive.
- **Device-agnostic IO re-coupling, if it becomes necessary.** Option 1 ([stores.md](./stores.md#decoupling-prototype-from-the-read-api)) gives up zero-copy DMA into caller-allocated (e.g. GPU) buffers via the *allocating* `Get`/`GetRange` path. The full device-agnostic story is delivered by `GetStreaming` instead — see [§ Streaming and caller-allocated reads via `GetStreaming`](#streaming-and-caller-allocated-reads-via-getstreaming) above and [gpu.md](./gpu.md) for the broader framing. If we later want the allocating path to also accept caller-specified destinations, the smallest delta is option 3 from stores.md: introduce a `ReadContext` parameter that carries a `BufferPrototype`. This is strictly additive relative to option 1.
- **`ZipStore` lifecycle contract.** Whether methods called outside a context manager should raise, warn, or be supported indefinitely. Five options are in play:
  1. **Indefinite lazy-open.** Status quo behavior preserved; context manager is documented as recommended but not required. `__del__` and pickle round-trip handle cleanup. No deprecation, no break. Lowest risk; resource-holding stores stay an explicit exception in the design (which the README already carves out).
  2. **Deprecation cycle.** `DeprecationWarning` for one or two releases, then `RuntimeError`. Final state is uniform with the rest of the design. Cost: real ergonomic tax on distributed scheduling (dask, ray) where task functions today receive an opened store and would need to enter a context manager per task.
  3. **New parallel store.** Add `StrictZipStore` alongside the existing `ZipStore`. Old class keeps lazy-open indefinitely; new class requires context manager. Variant: the protocol-based redesign's `ZipStore` is the strict one, today's `Store` ABC `ZipStore` keeps lazy-open. Migration cost is paid as part of the broader API migration rather than as a `ZipStore`-specific event.
  4. **Mode-conditional strictness.** Read mode allows lazy-open (leaking a handle is benign; the OS reclaims and the data is fine); write modes (`"w" | "a" | "x"`) require a context manager (a process exiting without close on a writable zip corrupts the central directory). Targets the actual correctness risk but introduces an asymmetric contract on one class.
  5. **Constructor flag.** `ZipStore(path, strict=False)` keeps lazy-open; `strict=True` requires context manager. Default off. Single class, opt-in. Flag becomes API surface to maintain.

  Trade-offs in [README sub-discussion to be added if this becomes a sticking point]; the corruption risk in write mode is the same under all options because `__del__ → close()` is the safety net in every case. Distributed pickling round-trips correctly under options 1, 3 (old class), 4 (read), and 5 (default), and takes a real ergonomic tax under options 2 and 4 (write).
