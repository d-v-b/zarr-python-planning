# Proposed `Transactional` protocol

This document specifies the transactional layer of the [Stores API proposal](./stores-api.md). It addresses the [V2 → V3 regression on atomic rename-into-place](https://github.com/zarr-developers/zarr-python/discussions/3410) and gives [Icechunk](https://github.com/earth-mover/icechunk) and similar transactional-storage backends a typed surface to declare their capabilities against.

The design adopts TensorStore's transaction model directly. TensorStore has eight years of production experience with transactions over object-storage-shaped backends and has settled on a small, opinionated surface: a free-standing `Transaction` object bound to stores by view, two boolean knobs (`atomic` and `repeatable_read`) covering the entire isolation/atomicity space, per-key generations rather than store-wide versions, and conditional writes via `if_equal` on per-call methods rather than baked into a separate protocol family. ([TensorStore Transaction](https://google.github.io/tensorstore/python/api/tensorstore.Transaction.html), [KvStore.with_transaction](https://google.github.io/tensorstore/python/api/tensorstore.KvStore.with_transaction.html))

The load-bearing claims are:

1. **Per-key atomicity is a property of `Put`, not a transaction.** Backends that support it (most modern object stores, filesystems via rename) advertise `Put` and the contract says individual writes are atomic. `LocalStore` regains rename-into-place, restoring V2's contract.
2. **Per-key conditional writes are a property of `Put`, not a transaction.** A `put(key, value, if_match=generation)` succeeds iff the current generation matches; the result reports the new generation or `None` if the precondition failed. This is the OCC primitive every other layer is built on.
3. **`Put.put` returns a `PutResult` carrying the post-write generation**, never `None`. `Get.get` returns a `ReadResult` carrying the read value plus its generation. The generation is a per-key, opaque token that the backend produces; it is *not* comparable across keys.
4. **Multi-key atomicity is what `Transactional` is for.** The protocol exposes a free-standing `Transaction()` object bound to stores by `store.with_transaction(txn)`. Two boolean knobs — `atomic` and `repeatable_read` — span the isolation/atomicity space. Commit raises `TransactionFailed` if the requested guarantees cannot be delivered; backends never silently degrade.
5. **Atomicity is delivered by adapters, not promised by stores.** Object-storage backends (`ObstoreStore`, most `FsspecStore` backends) cannot natively deliver multi-key atomicity. The pattern is to wrap them in a transactional adapter (Icechunk, or a future zarr-native equivalent) that imposes atomicity via a manifest swap. This is the same pattern TensorStore uses with OCDBT.
6. **`Caching[S]` and `Transactional[S]` do not compose**; refused at construction. Documented in the [caching proposal](./stores-caching.md#composition-with-other-wrappers).

## Motivation

Zarr V2 had atomic rename-into-place: `LocalStore` wrote to a temporary file and renamed atomically, which on POSIX filesystems gives a per-key atomic write. This protected readers from torn-write states (a partial `array.json` or `zarr.json` being read mid-write). V3's `LocalStore` writes the file directly, which loses this guarantee. [zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410) and [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094) document the regression and several user-reported failure modes.

Beyond the per-key case, two harder problems exist:

- **Multi-key atomicity.** Updating an array's metadata while rewriting its chunks should be visible to readers either as the old state or the new state, never as a mix. V2 did not really solve this either; the user pattern was "write chunks first, then metadata last," with the metadata write functioning as a commit point. V3 should make this a first-class capability.
- **Concurrent writers.** Two callers updating the same key concurrently need a way to detect conflict and retry. Without an OCC primitive, the only safe pattern is "single writer per array," which is increasingly untenable as Zarr-backed pipelines parallelize writes.

The protocol below addresses both, by following TensorStore's two-knob model rather than inventing a parallel one.

## Per-key atomicity and generations

### `Put` returns `PutResult`

`Put.put` is defined in [stores-api.md § Capability protocols](./stores-api.md#capability-protocols). The signature and return shape are reproduced here for convenience:

```python
@runtime_checkable
class Put(Protocol):
    def put(
        self,
        key: str,
        value: bytes | memoryview,
        *,
        if_match: "Generation | None" = None,
        if_none_match: bool = False,
    ) -> PutResult: ...

# PutResult, also in stores-api.md:
#   generation: Generation | None = None
#   applied: bool = True
# - applied=False = conditional precondition failed; generation reports
#   the current backend generation.
# - generation=None with applied=True = backend has no object identity
#   (cannot support conditional writes).
```

`Generation` is an opaque type — a string, bytes, an int, an ETag, an IceChunk content-hash. zarr-python treats it as `object` whose only operation is equality. Concrete backends define their own `Generation` representation; the protocol does not constrain the wire form. The canonical definition is in [stores-api.md](./stores-api.md#capability-protocols).

`if_match=g` requires the current key's generation to equal `g`; if not, the put returns `PutResult(generation=current_g, applied=False)` without raising. `if_none_match=True` requires the key to be absent; if the key exists, same behavior — returns the current generation, `applied=False`. Both flags compose only with each other (`if_match=` requires the key to exist; `if_none_match=True` requires absence). Mutual exclusion is enforced by the wrapper at call time.

This contract matches TensorStore's `KvStore.write(key, value, if_equal=...)`, which "resolves successfully but reports 'didn't happen'" on precondition failure rather than raising. Using a result type rather than an exception makes conflict-handling code a normal control-flow path rather than a try/except sandwich, and matches obstore's `PutResult` shape.

### `Get` returns `ReadResult`

`Get.get` is defined in [stores-api.md § Capability protocols](./stores-api.md#capability-protocols). The signature and return shape are reproduced here for convenience:

```python
@runtime_checkable
class Get(Protocol):
    def get(self, key: str, *, if_not_match: "Generation | None" = None) -> ReadResult: ...

# ReadResult, also in stores-api.md:
#   value: memoryview
#   generation: Generation        # opaque; equality is the only operation
```

`if_not_match=g` is a cache-validation primitive: if the current generation matches `g`, the read returns `ReadResult(value=memoryview(b''), generation=g)` with no payload. Modeled directly on TensorStore's `KvStore.read(key, if_not_equal=...)`. Useful for `Caching[S]` revalidation against a backend that supports generations.

`ReadResult` is the canonical return shape across the stores cluster (see [stores-api.md § Capability protocols](./stores-api.md#capability-protocols)). The advantage of this shape is that the generation is available at every read site without a follow-up `head()` call, which is the foundation for the conditional-write story below.

### Per-backend support for generations

| Backend | `Generation` source |
|---|---|
| `LocalStore` | `(mtime_ns, inode, size)` tuple, encoded as a string |
| `MemoryStore` | Monotonic per-key counter, bumped on every write |
| `ZipStore` | None — Zip format has no generation concept |
| `FsspecStore` | ETag where the underlying fs exposes one; otherwise None |
| `ObstoreStore` | The backend's native ETag/version (S3 ETag, GCS generation, Azure ETag) |
| Icechunk-as-adapter | Content hash of the value |

Backends without a generation set the field to `None`. Calls passing `if_match` or `if_none_match` to a backend without generation support raise `TypeError` rather than silently ignoring the precondition; the alternative would silently lose conflict detection. (Pinning this as `TypeError` per the canonical definition in [stores-api.md § Capability protocols](./stores-api.md#capability-protocols); the conformance suite asserts this in `test_put_if_match_on_backend_without_generations_raises_typeerror`.)

### `LocalStore` rename-into-place

Restore V2's rename-into-place: write to a temporary file in the same directory (so the rename is on the same filesystem and therefore atomic), then `os.replace` to the destination (`os.rename` is not atomic on Windows when the destination exists). One-line behavioral change, no API impact. Restores the V2 contract that several user reports rely on. ([zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094), [zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410))

## Transaction object and binding

```python
# zarr/storage/transactions.py

class Transaction:
    """Free-standing transaction object. Bind to a store via
    `store.with_transaction(txn)`; one transaction can be bound to many
    stores, and reads/writes through any binding share the same staging
    state.

    Two knobs span the isolation and atomicity space:

    - `atomic=True`: commit either applies all staged writes or none.
      If the underlying store(s) cannot deliver atomicity, commit
      raises `TransactionFailed`. Never silently degrades.
    - `repeatable_read=True`: every read records the generation observed;
      at commit, those generations are rechecked against current state.
      Any divergence raises `TransactionFailed`.

    Modeled on TensorStore's `Transaction` (see
    https://google.github.io/tensorstore/python/api/tensorstore.Transaction.html)."""

    def __init__(self, *, atomic: bool = False, repeatable_read: bool = False) -> None: ...

    @property
    def aborted(self) -> bool: ...

    @property
    def committed(self) -> bool: ...

    def commit(self) -> None:
        """Commit synchronously. Raises TransactionFailed if any
        precondition fails or the requested atomicity cannot be
        delivered. After successful commit, the transaction is
        single-use exhausted; further operations raise."""
        ...

    async def commit_async(self) -> None: ...

    def abort(self) -> None:
        """Discard all staged writes. Idempotent."""
        ...

    def __enter__(self) -> "Transaction": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Commits on clean exit; aborts on exception."""
        ...

    async def __aenter__(self) -> "Transaction": ...
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool: ...


class TransactionFailed(Exception):
    """Raised by Transaction.commit() / commit_async() when:
    - `atomic=True` was requested but the bound stores cannot deliver it
    - `repeatable_read=True` and a tracked generation diverged
    - a precondition (`if_match` / `if_none_match`) on a staged put failed
    - any underlying store-side error during commit

    Carries `keys: frozenset[str]` (the keys whose preconditions failed
    or whose generations diverged) and `reason: str`."""
    keys: frozenset[str]
    reason: str
```

```python
@runtime_checkable
class Transactional(Protocol):
    """Backends and adapters that participate in transactions advertise
    this. The store gains a `with_transaction(txn)` method that returns
    a transaction-bound view of itself; reads and writes through the view
    are staged in `txn` rather than applied immediately."""

    def with_transaction(self, txn: Transaction) -> "Self": ...
```

`with_transaction` returns a typed-by-protocol view: the view satisfies the same capabilities the original store did, but routes its calls through `txn`. The same `Transaction` instance can be passed to `with_transaction` on multiple stores and stays consistent across all of them — this is what makes cross-store transactional *staging* free at the syntactic level (atomicity remains a property the commit may refuse).

### One transaction, many bindings

```python
txn = Transaction(atomic=True, repeatable_read=False)

metadata_view = metadata_store.with_transaction(txn)
chunks_view = chunks_store.with_transaction(txn)

with txn:
    metadata_view.put("zarr.json", new_metadata)
    for k, v in new_chunks:
        chunks_view.put(k, v)
# Commit attempts to apply both halves atomically. If `metadata_store`
# and `chunks_store` are different backends (no shared coordinator),
# the commit raises TransactionFailed because cross-store atomicity is
# not deliverable.
```

This is the TensorStore pattern verbatim. Cross-backend transactional staging is syntactically free; cross-backend atomicity raises at commit time. The right way to get atomic cross-key writes over object storage is to put both halves behind a single transactional adapter (Icechunk, or a future zarr-native one), not to coordinate across separate backends.

## The two knobs

### `atomic`

`atomic=False` (default) is "isolated, possibly partial commit." Writes are staged in-memory; commit applies them but does not promise atomicity. If commit fails partway, some writes may have landed. Suitable for write batching where the caller tolerates partial application (most large data ingest patterns where individual chunks are independent).

`atomic=True` is "all or nothing." Commit either applies every staged write or applies none. Backends that can deliver this (Icechunk via manifest swap, `LocalStore` via batch rename if the implementation supports it, `MemoryStore` via copy-on-write overlay) advertise it through their commit logic. Backends that cannot (raw `ObstoreStore` over S3, `FsspecStore` over most filesystems) raise `TransactionFailed` if a transaction with `atomic=True` is bound to them.

The "raise rather than degrade" rule is the most important part of this design. Silent degradation produces invisible data corruption when a caller assumed atomicity and didn't get it. TensorStore's stance, which we adopt: if you ask for atomic and we can't deliver, the commit raises. The error message names the offending store(s) so the caller knows whether to wrap them in a transactional adapter or relax the requirement.

### `repeatable_read`

`repeatable_read=False` (default) is "no precondition tracking." Reads inside the transaction return their values; the generations are visible on each `ReadResult` but are not recorded by the transaction.

`repeatable_read=True` is "snapshot-isolated reads." Every read inside the transaction records the observed generation. At commit, each recorded generation is rechecked against current state; divergence raises `TransactionFailed` with the conflicting key set. This is the OCC isolation level — the standard "read-modify-write" safety pattern is:

```python
def safe_update(store: Transactional, key: str, transform):
    while True:
        txn = Transaction(atomic=True, repeatable_read=True)
        view = store.with_transaction(txn)
        with txn:
            current = view.get(key)
            view.put(key, transform(current.value))
        return  # If commit raised, the `with` block's __exit__ propagates
```

The retry loop is caller-side. zarr-python does not ship an `atomic_update` helper in the initial protocol; TensorStore deliberately does not either, on the grounds that retry policy (max attempts, backoff, jitter, give-up signal) is application-specific. If a real workload demands one, it can be added later as a thin wrapper around `Transaction(atomic=True, repeatable_read=True)`.

### The two knobs span the space

| `atomic` | `repeatable_read` | Use case |
|---|---|---|
| False | False | Plain write batching; partial-apply tolerable; no concurrent-writer concern |
| True | False | Multi-key atomic write where reads are not load-bearing (initial array creation, full-array overwrite) |
| False | True | OCC reads without write atomicity (rare; mostly a check-then-write pattern where individual writes are safe per-key) |
| True | True | Full transactional update with concurrent writers (Icechunk's primary mode, the safe-update pattern above) |

Two booleans cover the entire space TensorStore has used in production for eight years. Treating the bottom-right cell as a separate protocol type would be unnecessary complexity.

## Per-backend support

| Backend | `Put` atomic? | `Generation` available? | Supports `Transactional`? | Notes |
|---|---|---|---|---|
| `LocalStore` | yes (rename) | yes (mtime+inode+size) | yes (`atomic=True` via batch rename, single-process only) | Crash-atomicity is an open question |
| `MemoryStore` | yes (GIL/dict) | yes (per-key counter) | yes (`atomic=True` via copy-on-write overlay) | Trivial implementation |
| `ZipStore` | no | no | no | Sequential write format; no generation concept |
| `FsspecStore` | depends on fs | depends on fs | no by default | Defers to underlying filesystem |
| `ObstoreStore` | yes (per object) | yes (ETag/generation) | no by default | Per-key OCC works via `if_match`; multi-key atomicity needs an adapter |
| Icechunk-as-adapter | yes | yes (content hash) | yes (`atomic=True` via manifest swap) | The reference transactional adapter |

The key reframe: **Icechunk is an *adapter*, not a backend.** It wraps a non-transactional store (typically `ObstoreStore` over S3) and imposes atomicity and OCC semantics via a manifest layer. This is the same pattern TensorStore's OCDBT driver uses, and it generalizes: the right way to add transactional semantics to any object-storage backend is to wrap it in an adapter that owns a manifest.

`ObstoreStore` and `FsspecStore` thus do *not* advertise `Transactional` directly. A user who wants multi-key atomicity over S3 does:

```python
inner = ObstoreStore(S3Store(bucket="b", region="us-east-1"))
# `IcechunkAdapter` here is illustrative — the actual integration is
# in the [icechunk](https://github.com/earth-mover/icechunk) project,
# which ships its own adapter that satisfies the Transactional protocol
# defined here. The name and exact constructor signature are owned by
# that project; this proposal commits to the protocol surface, not to
# Icechunk's API.
store = IcechunkAdapter(inner, repository="my-array")
# store: Transactional, with atomic and repeatable_read both available
```

## `LocalStore` multi-key atomicity

`LocalStore` can deliver `atomic=True` within a single process via a tempdir-batch-rename strategy:

1. Writes during the transaction go to a per-transaction tempdir.
2. On commit, acquire a process-local lock on the store root.
3. Walk the tempdir and `os.replace` each file into its destination.
4. Release the lock.

This is single-process atomic but **not crash-atomic**: a process killed between renames leaves the destination in a mixed state. A stricter implementation would journal the rename operations and replay on recovery. Whether to ship the strict version is an open question (see below); the relaxed version is enough for most callers and matches the V2 multi-key write pattern (`os.rename` per key, no journal).

Document the limitation precisely. Do not over-claim.

## Composition with other wrappers

- **`Prefixed[Transactional[S]]`**: transparent. The prefix wrapper does not interact with transactional semantics; it just joins keys before passing them through. Cross-prefix transactions work correctly.
- **`ReadOnly[Transactional[S]]`**: removes write capabilities. The store still satisfies `Transactional` (transactions over read-only stores are degenerate but well-defined: any commit with no staged writes is a no-op; staged writes raise at construction).
- **`Retry[Transactional[S]]`**: composable with caveat. `Retry` retries transient I/O failures on individual operations; `commit()` failures (specifically `TransactionFailed`) are *not* retried because a failed atomic commit indicates either a real conflict (caller should retry the *whole transaction*, not just the commit) or a non-deliverable atomicity request (retrying won't help). Document in [Retry's wrapper spec](./stores-wrappers.md#retrys).
- **`RangeCoalescing[Transactional[S]]`**: orthogonal. Range coalescing is read-side; transactions are write-side. Composable with no special handling.
- **`Caching[Transactional[S]]`**: refused at construction. The cache wrapped around a transactional store would surface stale (pre-commit) reads to callers outside the transaction, and the per-transaction reads-see-staged-writes semantic is incompatible with a shared cache. Resolution proposed in the [caching proposal](./stores-caching.md#composition-with-other-wrappers): `Caching` raises if its inner store advertises `Transactional`, and the transaction view refuses to wrap a `Caching` instance. A future transaction-aware cache is a separate proposal.
- **`Tracing[Transactional[S]]`**: composable. Tracing wraps each method including `with_transaction()`, `commit()`, `commit_async()`, `abort()`. Useful for operational visibility on commit latency, abort rate, and conflict rate.
- **`KvStack[Transactional[S]]`**: cross-layer atomicity is *not* supported. A transaction can stage writes spanning multiple `KvStack` layers; commit applies per-layer atomically (when each layer satisfies `Transactional`) but offers no atomicity across layers. This is the same constraint as cross-backend transactions in general — atomicity needs a coordinator that the protocol does not provide.

## Test plan

`TransactionalSpec` in [proposals/stores-conformance.md](./stores-conformance.md#wrapper-preservation-specs) covers:

- `test_transaction_commit_persists`: writes inside a `with txn:` block are visible after the context exits.
- `test_transaction_abort_discards`: an exception inside the block aborts; subsequent reads do not see the writes.
- `test_explicit_abort`: `txn.abort()` discards writes and `__exit__` does not commit.
- `test_explicit_commit`: `txn.commit()` mid-block commits; further writes after `commit()` raise.
- `test_one_transaction_many_bindings`: a single `Transaction` bound to two stores stages writes across both; commit applies them in order. Cross-store *atomic* commit raises `TransactionFailed` if neither store-pair has a shared coordinator.
- `test_isolation_from_concurrent_reader`: a reader through the parent store does not see in-progress writes until commit completes.
- `test_read_your_own_writes`: a `view.get(key)` after `view.put(key, value)` returns `value`.
- `test_atomic_true_all_or_nothing`: a `Transaction(atomic=True)` containing multiple puts either commits all or none. Trigger an abort mid-way; assert no keys are visible.
- `test_atomic_true_raises_on_undeliverable`: a `Transaction(atomic=True)` bound to a store whose backend cannot deliver atomicity (e.g., raw `ObstoreStore` over S3) raises `TransactionFailed` with a clear message.
- `test_repeatable_read_succeeds_when_no_conflict`: a `Transaction(repeatable_read=True)` whose read set was not modified externally commits normally.
- `test_repeatable_read_raises_on_conflict`: a `Transaction(repeatable_read=True)` reads `key`; an external writer modifies `key`; commit raises `TransactionFailed` carrying `{key}` in the conflicting set.
- `test_per_key_atomicity_no_torn_write`: a single-key `put` is observed as either old or new value, never partial. Skipped on backends that document the limitation (`ZipStore`).
- `test_put_if_match_succeeds_when_generation_matches`: `put(key, v, if_match=g)` where `g` is the current generation returns `PutResult(applied=True)`.
- `test_put_if_match_fails_when_generation_diverged`: `put(key, v, if_match=g)` where `g` is stale returns `PutResult(applied=False, generation=current_g)` without raising.
- `test_put_if_none_match_succeeds_when_key_absent`: `put(key, v, if_none_match=True)` on a missing key returns `PutResult(applied=True)`.
- `test_put_if_none_match_fails_when_key_exists`: same call on a present key returns `PutResult(applied=False)` without raising.
- `test_get_if_not_match_returns_empty_value_when_unchanged`: `get(key, if_not_match=g)` where `g` is the current generation returns `ReadResult(value=memoryview(b''), generation=g)`.
- `test_transaction_single_use`: a committed or aborted `Transaction` cannot be reused; further binding or commit raises.

Per-backend test files inherit `TransactionalSpec` and provide fixtures. Backends that do not advertise `Transactional` skip the suite.

## Migration

Restoring per-key atomicity is the smaller, immediate piece:

- `LocalStore.put` rewrites to write-to-tempfile-then-replace. One-line behavioral change. Restore-V2 contract documented on the `Put` protocol. No API change. Ship in a minor release.

The structural changes ship in stages:

1. **`Generation`, `PutResult`, `ReadResult` types land additively.** New return types on `Get` and `Put`. Existing `bytes`-shaped callers migrate to `result.value`. The migration is mechanical and can be done backend-by-backend with deprecation shims.
2. **`if_match` / `if_none_match` arguments on `Put`, `if_not_match` on `Get`.** Optional kwargs; no behavior change for callers that do not pass them. Backends without generation support raise on receiving these kwargs rather than silently ignoring.
3. **`Transaction` class and `Transactional` protocol land additively.** Backends that don't support transactions advertise nothing; the typing surface gains `Transaction` and `Transactional` definitions.
4. **`MemoryStore` implements `Transactional` first.** Trivial (copy-on-write overlay); serves as the test bed.
5. **`LocalStore` implements `Transactional`.** Tempdir-batch-rename. Document single-process-atomicity caveat.
6. **Icechunk migrates to advertising `Transactional` via the adapter pattern.** This validates the protocol against real concurrent-writer use.
7. **Documentation updates.** Replace existing "write metadata last as commit point" patterns with `with txn: ...` patterns where multi-key atomicity is the right answer.

`ObstoreStore` and `FsspecStore` do not advertise `Transactional` at any stage. Users who need transactional semantics over object storage compose Icechunk (or a similar adapter) on top.

## Open questions

- **`LocalStore` crash-atomicity strictness.** Tempdir-batch-rename is single-process atomic but not crash-atomic. A journaled implementation that replays renames on recovery is a meaningful complexity addition for a marginal correctness gain. Decide before shipping the multi-key atomicity for `LocalStore`: do we promise crash-atomicity, or only single-process-atomicity? The minimum-viable answer is single-process plus clear documentation.
- **`Generation` representation across backends.** The protocol leaves `Generation` opaque (`object` with equality). For interop across backends (a tool that reads from one transactional adapter and writes to another), some standardization would help. Icechunk-style content hash is the natural common ground; punt to a follow-up.
- **`Generation` for `MemoryStore`.** A monotonic per-key counter is the obvious choice. Open question: should `MemoryStore` instances persist their counters across pickling round-trips so a generation observed pre-pickle is comparable post-pickle? Yes is the conservative answer (otherwise OCC across distributed workers breaks); document the contract.
- **Free-threaded CPython interactions.** `MemoryStore`'s atomicity story rests on the GIL today. Under free-threaded CPython ([zarr#2776](https://github.com/zarr-developers/zarr-python/discussions/2776)), `MemoryStore` needs explicit locking around mutation and generation-counter updates. Track with the broader free-threaded CPython work; not a blocker for the protocol design.
- **Per-call timeouts on commit.** Long-running commits (large transactions over slow backends) want a timeout knob. TensorStore's `commit_async` returns a `Future` whose `.result(timeout=...)` provides this; zarr-python's `commit()` is sync and would need a `timeout` kwarg. Open question: ship with `timeout` from day one, or punt? Recommend punt — `commit_async()` plus standard `asyncio.wait_for` covers the use case without protocol surface bloat.
- ~~`Caching` × `Transactional` resolution.~~ **Resolved as refused-at-construction**, per claim 6 above and the symmetric refusal in [stores-caching.md § Composition with other wrappers](./stores-caching.md#composition-with-other-wrappers). A transaction-aware cache is a future proposal.
- **Cross-store transactions.** A transaction spanning two unrelated stores cannot deliver atomicity without a coordinator. The proposal makes this explicit: `atomic=True` raises at commit if the bound stores do not share a coordinator. Distributed transactions are a large body of work; explicitly out of scope for zarr-python. The recommended pattern is to put both halves behind a single transactional adapter.
- **`atomic_update` helper.** Out of scope for the initial protocol. TensorStore deliberately does not ship one; we follow. Add later if a real workload justifies it.
- **`Transactional` on `KvStack`.** A `KvStack` whose layers all satisfy `Transactional` could in principle advertise `Transactional` itself, but commit semantics across layers are weaker than per-layer (atomicity does not compose across heterogeneous backends). Open question: should `KvStack` advertise `Transactional` in the per-layer-only sense, or refuse to advertise it at all? The conservative answer is "advertise per-layer and document that cross-layer atomicity is not delivered"; the strict answer is "do not advertise." Decide before shipping `KvStack` against a transactional layer.
