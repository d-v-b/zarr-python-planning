# Proposed `Transactional[S]` protocol

This document specifies the transactional layer of the [Stores API proposal](./stores-api.md). It addresses the [V2 → V3 regression on atomic rename-into-place](https://github.com/zarr-developers/zarr-python/discussions/3410) and gives [Icechunk](https://github.com/earth-mover/icechunk) and similar transactional-storage backends a typed surface to declare their capabilities against. The load-bearing claims are:

1. Per-key atomicity is a property of `Put`, not of a separate transaction. Backends that support it (most modern object stores, filesystems via rename) advertise `Put` and the contract says individual writes are atomic. `LocalStore` regains rename-into-place behavior, restoring V2's contract.
2. Multi-key atomicity is what `Transactional` is for. The protocol is a context-manager pattern: writes go through the transaction context; commit happens on `__exit__` when no exception fires; abort happens on exception or explicit `abort()`.
3. The transaction context advertises the same write capability surface as `S`. A `Transactional[Put & Delete]` produces a context that has `put` and `delete`. A `Transactional[Put & Delete & Copy]` adds `copy`.
4. Optimistic concurrency control (OCC) is a separate protocol (`TransactionalOCC`) that extends `Transactional` with snapshot-isolation semantics. Backends that need it (Icechunk) advertise both; backends that only need plain transactions advertise just `Transactional`.
5. `Caching[S]` and `Transactional[S]` do not compose; documented in the [caching proposal](./stores-caching.md#composition-with-other-wrappers). Resolution of that composition is tracked here.

## Motivation

Zarr V2 had atomic rename-into-place: `LocalStore` wrote to a temporary file and renamed atomically, which on POSIX filesystems gives a per-key atomic write. This protected readers from torn-write states (a partial array.json or zarr.json being read mid-write). V3's `LocalStore` writes the file directly, which loses this guarantee. [zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410) and [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094) document the regression and several user-reported failure modes.

Beyond the per-key case, multi-key atomicity is the harder problem. Updating an array's metadata document while rewriting its chunks should be visible to readers either as the old state (old metadata, old chunks) or the new state (new metadata, new chunks), never as a mixed state. V2 did not really solve this either; the user pattern was "write chunks first, then metadata last," with the metadata write functioning as a commit point. V3 should make this a first-class capability, both because it is a real correctness gap and because Icechunk has demonstrated a working transactional model that the rest of zarr-python's storage layer can integrate with rather than parallel.

The two-level model below distinguishes these explicitly: per-key atomicity is something every backend should provide and most can; multi-key transactions are an opt-in capability that only some backends will advertise.

## Per-key atomicity

`Put.put(key, value)` is atomic with respect to readers. Readers see either the old value, the new value, or `KeyError`; they never see a partial value or a torn write.

This contract is documented on the `Put` protocol's docstring, not enforced by zarr-python directly. Per-backend implementation:

- **`LocalStore`**. Restore V2's rename-into-place: write to a temporary file in the same directory (so the rename is on the same filesystem and therefore atomic), then `os.rename` to the destination. Cross-platform note: `os.rename` on Windows is not atomic if the destination exists, so `os.replace` (which is) is used instead. This is a one-line behavioral change with measurable benefit and no API impact. It restores the V2 contract that several user reports rely on.
- **`MemoryStore`**. Atomic by virtue of Python's GIL and dict semantics: `dict[key] = value` is a single bytecode and cannot tear. (Free-threaded CPython changes this slightly; tracked in [zarr#2776](https://github.com/zarr-developers/zarr-python/discussions/2776). When that lands, `MemoryStore` will need an explicit lock around its mutation paths.)
- **`ZipStore`**. Not naturally atomic; `zipfile.ZipFile` writes append to the archive and the central directory is only correct on close. The contract says "atomic with respect to readers using a different `ZipStore` instance after this writer closes." Mid-write reads from a different process see undefined state. Document this limitation; do not pretend.
- **`FsspecStore`**. Backend-dependent; most cloud backends are atomic per-object. `FsspecStore` defers to the underlying filesystem.
- **`ObstoreStore`**. S3, GCS, Azure are atomic per-object. HTTP is read-only.

This per-key contract is sufficient for the regression that V3 introduced. It does not require any new protocol.

## Multi-key transactions

```python
@runtime_checkable
class Transactional(Protocol):
    """Backends that support multi-key atomic transactions advertise
    this. Writes inside a transaction are batched and committed
    atomically on `__exit__` (or `commit()`); aborted on exception
    (or `abort()`)."""
    def transaction(self) -> "TransactionContext": ...


class TransactionContext(Protocol):
    """In-progress transaction. The context advertises the same write
    capability surface as the parent store. Reads through the context
    see in-progress writes from this transaction; reads through the
    parent store see only committed state."""

    def commit(self) -> "CommitResult": ...
    def abort(self) -> None: ...

    def __enter__(self) -> "TransactionContext": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool: ...

    # Write capabilities surface through the context with the same
    # signatures as on the parent store. Self-type narrowing applies
    # the same way it does for wrappers.
    def put(self: "TransactionContext", key: str, value: bytes | memoryview) -> None: ...
    def delete(self: "TransactionContext", key: str) -> None: ...
    def copy(self: "TransactionContext", src: str, dst: str) -> None: ...

    # Reads see in-progress writes plus committed state. Reads through
    # `parent_store.get(...)` outside the transaction context see only
    # committed state.
    def get(self: "TransactionContext", key: str) -> memoryview: ...
    def get_range(
        self: "TransactionContext",
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> memoryview: ...


@dataclass(frozen=True)
class CommitResult:
    """Returned from `TransactionContext.commit()`. Backends with
    snapshot or version semantics populate `version`; others leave it
    None."""
    version: "Version | None" = None
    committed_at: "datetime.datetime | None" = None
```

Usage:

```python
with store.transaction() as txn:
    txn.put("path/to/array/zarr.json", new_metadata)
    for chunk_key, chunk_bytes in new_chunks:
        txn.put(chunk_key, chunk_bytes)
# All writes commit atomically here. If the body raised, all writes are aborted.
```

The transaction context's read methods are convenience for "read your own writes within this transaction." A typical caller pattern is to write all the new chunks via the transaction, then read back via the same transaction to verify, then exit the context to commit. Reads through `store.get(...)` outside the transaction see only committed state until the commit completes.

## Per-backend support

| Backend | `Put` atomic? | Multi-key `Transactional`? | Notes |
|---|---|---|---|
| `LocalStore` | yes (rename-into-place) | yes (write to temp dir, rename in batch) | Single-process atomicity only |
| `MemoryStore` | yes | yes (copy-on-write dict overlay) | Trivial |
| `ZipStore` | no | no | Sequential write format |
| `FsspecStore` | depends on fs | no by default | Some fsspec backends may add their own |
| `ObstoreStore` | yes | no by default | S3 / GCS / Azure are per-object atomic; multi-object atomicity needs a manifest layer |
| Icechunk | yes | yes (snapshot-based) | Also implements `TransactionalOCC` |

`LocalStore`'s multi-key transaction can be implemented as: writes during the transaction go to a tempdir; commit walks the tempdir and renames each file into place; abort deletes the tempdir. This is not multi-key atomic in the strict sense (an observer running between renames can see partial state), but is "write-batched" and avoids the partial-write hazard of writes interleaved with the call site's other state changes. Document the limitation precisely; do not over-claim.

`MemoryStore`'s multi-key transaction uses a copy-on-write overlay: writes during the transaction go to an overlay dict; commit merges the overlay into the main dict atomically (under a lock); abort discards the overlay.

`ObstoreStore` does not advertise `Transactional` in the initial implementation. A user who needs multi-key atomicity over S3 / GCS / Azure layers Icechunk on top, or implements a manifest-based transaction layer themselves; the wrapper protocol gives them a place to hang it.

## Optimistic concurrency control

```python
@runtime_checkable
class TransactionalOCC(Transactional, Protocol):
    """Extends `Transactional` with snapshot-isolation semantics.
    Backends that need to support concurrent writers (Icechunk, future
    distributed-coordinated stores) advertise this in addition to
    `Transactional`. Backends that only need single-writer transactions
    advertise just `Transactional`."""
    def transaction(
        self, *, read_version: "Version | None" = None
    ) -> "OCCTransactionContext": ...


class OCCTransactionContext(TransactionContext, Protocol):
    """Transaction with snapshot isolation. Tracks the keys read during
    the transaction; on commit, fails with `ConflictError` if any of
    those keys was modified since `read_version`. Callers handle the
    conflict by retrying with the new version."""

    @property
    def read_version(self) -> "Version": ...

    def commit(self) -> "OCCCommitResult":
        """Returns OCCCommitResult on success.

        Raises
        ------
        ConflictError
            If any key read during the transaction has been modified
            since `read_version`. The exception carries the conflicting
            key set for caller-side retry logic.
        """
        ...


class ConflictError(Exception):
    """Raised by `OCCTransactionContext.commit()` when a concurrent
    writer has modified one of the keys this transaction read. The
    exception carries the set of conflicting keys and the commit
    version that won."""
    keys: frozenset[str]
    winning_version: "Version"
```

`Version` is an opaque-to-zarr-python token (a hash, a monotonic counter, a vector clock). Each backend defines its own concrete type and zarr-python treats it as an `object` whose only operation is equality. The `Version` returned by `OCCCommitResult` is what callers pass to `transaction(read_version=...)` for the next transaction.

Caller pattern for OCC:

```python
def safe_update(store: TransactionalOCC, key: str, transform):
    while True:
        version = store.head_version()
        with store.transaction(read_version=version) as txn:
            current = bytes(txn.get(key))
            new_value = transform(current)
            txn.put(key, new_value)
            try:
                txn.commit()
                return
            except ConflictError:
                continue  # retry with the latest version
```

The retry-on-conflict loop is caller-side because zarr-python cannot safely retry arbitrary user code. A future helper like `store.atomic_update(key, transform)` could wrap this for the common pattern; out of scope for the initial protocol.

## Composition with other wrappers

- **`Prefixed[Transactional[S]]`**: transparent. The prefix wrapper does not interact with transactional semantics; it just joins keys before passing them through. Prefixed across a transaction boundary works correctly.
- **`ReadOnly[Transactional[S]]`**: removes `Transactional` from the surface (because transactions are inherently writes). `ReadOnly` already strips `Put` / `Delete` / `Copy` / `Transactional` per the [stores-api.md](./stores-api.md#wrappers) spec.
- **`Retry[Transactional[S]]`**: composable but the retry semantics need to be transaction-aware. A retry of a failed `commit()` is conceptually different from a retry of a transient `put` failure; the wrapper documents that retry only applies to non-commit operations within the transaction, and `commit()` failures (including `ConflictError`) propagate without retry. Out of scope for the initial wrapper; tracked under the `Retry` proposal when that lands.
- **`RangeCoalescing[Transactional[S]]`**: orthogonal; range coalescing is a read-side optimization and transactions are write-side. Composable with no special handling.
- **`Caching[Transactional[S]]`**: undefined. The cache wrapped around a transactional store would surface stale (pre-commit) reads to callers outside the transaction, and uncommitted writes to callers inside the same transaction depend on whether the cache is per-context or shared. Resolution proposed below.
- **`Tracing[Transactional[S]]`**: composable; tracing wraps each method including `transaction()`, `commit()`, `abort()`. Useful for operational visibility on commit latency and abort rate.

### Resolution for `Caching` × `Transactional`

The undecided composition from the caching proposal: I propose making `Caching[S]` refuse to wrap a `Transactional` store at construction time, and refuse to be wrapped inside a transaction context. Both fail-fast at construction with a clear error message that points at the open question. Callers who want caching of a transactional backend's committed state can wrap a non-transactional view (e.g., a read-only proxy or a separate wrapper that exposes only the read capabilities), at which point the cache is well-defined.

This is the conservative answer. A future proposal can refine it: e.g., a transaction-aware cache that flushes on commit, or a per-transaction cache layer. The conservative answer does not foreclose either; it just refuses to ship the broken composition by default.

## Test plan

`TransactionalSpec` in [proposals/stores-conformance.md](./stores-conformance.md#wrapper-preservation-specs) covers:

- `test_transaction_commit_persists`: writes inside a `with store.transaction():` block are visible after the context exits via `store.get(...)`.
- `test_transaction_abort_discards`: an exception inside the block aborts the transaction; subsequent `store.get(...)` does not see the writes.
- `test_explicit_abort`: calling `txn.abort()` discards writes and `__exit__` does not commit.
- `test_explicit_commit`: calling `txn.commit()` mid-block commits; further writes after `commit()` raise (the context is exhausted).
- `test_isolation_from_concurrent_reader`: a reader through the parent store does not see in-progress writes until commit completes.
- `test_read_your_own_writes`: a `txn.get(key)` after `txn.put(key, value)` returns `value`.
- `test_atomic_multi_key`: a transaction containing multiple `put` calls either commits all or none. Assert by triggering an abort mid-way and confirming none of the keys are visible.
- `test_per_key_atomicity_no_torn_write`: backend-level test with a concurrent reader; a single-key `put` is observed as either the old value or the new value, never a partial. Skipped on backends that document the limitation (`ZipStore`).

`TransactionalOCCSpec` extends `TransactionalSpec` with:

- `test_commit_succeeds_when_no_conflict`: a transaction whose read set was not modified externally commits normally, returning the new `Version`.
- `test_commit_raises_conflict_error_when_read_key_modified`: a transaction reads `key`, an external writer modifies `key`, the transaction's `commit()` raises `ConflictError` carrying `{key}` in the conflicting set.
- `test_conflict_error_does_not_leak_writes`: after a `ConflictError`, the transaction's writes are not visible.
- `test_version_round_trip`: a `read_version` returned from a previous commit can be passed to a new `transaction(read_version=...)` call.

`CapabilityPreservationSpec` runs separately to assert that wrappers preserve the `Transactional` surface where appropriate (e.g., `Prefixed[Transactional[S]]` advertises `Transactional`; `ReadOnly[Transactional[S]]` does not).

## Migration: restoring V2 semantics

The per-key atomicity restoration is the smaller, immediate piece:

- `LocalStore.put` rewrites to write-to-tempdir-then-rename. One-line behavioral change. Restore-V2 contract documented on the `Put` protocol. No API change. Ship in a minor release; reference [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094) and [zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410) in the changelog.

The `Transactional` protocol ships in stages:

1. **Protocol class lands additively.** Backends that don't support it advertise nothing; the typing surface gains `Transactional` and `TransactionContext` definitions.
2. **`MemoryStore` implements `Transactional` first.** Trivial implementation; serves as the test bed for the protocol.
3. **`LocalStore` implements `Transactional`.** Tempdir-batching as described. Document the single-process-atomicity caveat.
4. **Icechunk migrates to advertising `Transactional` and `TransactionalOCC`.** This is what tests the protocol against a real concurrent-writer use case.
5. **Documentation updates.** Replace `with_read_only()` patterns in user-facing docs with `ReadOnly[S]` (covered in the lifecycle subsection), and add transaction patterns where multi-key atomicity is the right answer.

`ObstoreStore` and `FsspecStore` do not advertise `Transactional` in the initial implementation. Users who need multi-key atomicity over object storage compose Icechunk on top.

## Open questions

- **`LocalStore` multi-key atomicity strictness.** The tempdir-batching commit is "all renames in sequence under a lock." This is single-process-atomic but not crash-atomic: a process killed between renames leaves the destination in a mixed state. A stricter implementation could journal the rename operations and replay on recovery; that is a meaningful complexity addition for a marginal correctness gain. Worth deciding before we ship: do we promise crash-atomicity for `LocalStore`'s multi-key transactions, or only single-process-atomicity?
- **Read tracking granularity in `OCCTransactionContext`.** Per-key tracking is what the spec describes. A coarser "any write to this prefix" tracking would be cheaper but produces more false-positive conflicts. Icechunk uses per-key; defer to its choice unless a reason emerges to diverge.
- **`Version` representation.** The protocol leaves `Version` opaque. For interop across backends (a tool that reads from one transactional backend and writes to another), some standardization would help. Icechunk-style content hash is the natural common ground; punt to a follow-up.
- **`atomic_update` helper.** The OCC retry loop is caller-side. A `store.atomic_update(key, transform)` helper would encapsulate the common pattern. Out of scope for the initial protocol; design once we see real usage.
- **Cross-store transactions.** A transaction spanning two stores (e.g., update a chunk in `LocalStore` and a manifest entry in `ObstoreStore`) is not supported and is unlikely to be. Distributed transactions are a large body of work; explicitly out of scope for zarr-python.
- **Caching × Transactional resolution.** Refuse-at-construction is the proposed conservative answer; a transaction-aware cache is a future proposal. Confirm or push back.
- **Async variants.** `TransactionalAsync` follows the same shape with `__aenter__` / `__aexit__` and `await txn.commit()`. The naming aligns with the [sync-by-default subsection](../README.md#sync-by-default-with-async-as-an-opt-in-protocol-family). The initial sync-only protocol can land first with the async variant following.
