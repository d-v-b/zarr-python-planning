# Proposed `Caching[S]` wrapper

This document specifies the `Caching[S]` wrapper introduced in the [Stores API proposal](./stores-api.md) and tested by `CachingSpec` in the [conformance suite proposal](./stores-conformance.md). It is a **store-layer**, **key-agnostic** cache: it knows about bytes-at-keys and nothing else. The metadata-vs-chunks distinction that performance.md's default caching policy needs lives at the *hierarchy layer*, not here — see [hierarchy-layer.md § How caching stratifies cleanly](./hierarchy-layer.md#how-caching-stratifies-cleanly) for the layering and [performance.md § Default caching policy](./performance.md#default-caching-policy) for the user-facing defaults. The load-bearing claims are:

1. `Caching[S]` is **key-agnostic**. It caches the literal bytes returned by store reads, keyed by store key (and range, for partial reads). It does not classify keys as "metadata" vs "chunk" — that requires hierarchy knowledge the store layer doesn't have.
2. Cache entries are the literal result of each read call (one entry per `(key,)` for `get`, one per `(key, start, end)` for `get_range`, one per range in a `get_ranges` batch). No promotion, no slicing, no normalization across overlapping ranges.
3. Eviction is LRU bounded by `max_bytes` and `max_entries`, with optional `ttl` for stale-data tolerance. Revalidation uses storage generations (`if_not_match=`) when the backend supports them; falls back to TTL otherwise.
4. Writes (`put`, `delete`, `copy`) invalidate every cache entry whose key matches, so cache coherence holds for callers that go through the same `Caching[S]` instance.
5. **In-flight request deduplication is unconditional** and lives in the shared substrate, not behind this wrapper. Per [performance.md § Caching](./performance.md#caching), every store gets in-flight dedup whether or not it is wrapped in `Caching[S]`. The wrapper consumes the same dedup table.
6. The recommended composition for sharded reads is `Caching[RangeCoalescing[S]]`, with caching above coalescing.
7. `Caching` is refused at construction when composed with `Transactional` (see [stores-transactional.md § Composition](./stores-transactional.md#composition-with-other-wrappers)).
8. Every backend exposes a `with_caching(...)` convenience method that returns a `Caching[Self]`. This is the recommended user-facing entry point for *store-layer* caching. Tiered, hierarchy-aware caching (metadata-on-by-default, chunks-opt-in) is a *separate* wrapper at the hierarchy layer; users typically construct it via `array.with_caching(...)` or `group.with_caching(...)` per [hierarchy-layer.md](./hierarchy-layer.md). The two compose: a hierarchy-layer cache wraps the verbs, which call into a store-layer `Caching[S]`, which talks to the backend.

## Motivation

Zarr workloads are read-heavy and read-repetitive. The codec pipeline for a sharded read issues a deterministic set of `get_range` calls per slice; the same slice issued twice produces the same calls. Metadata reads (`get(zarr.json)`, `get(.zattrs)`) are issued on every array open and rarely change. Hierarchy traversal (`group["sub"]`) re-reads the same metadata documents repeatedly. Without caching, every one of these calls hits the underlying store and pays the latency cost.

The existing [experimental `cache_store`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/experimental/__init__.py) caches at the codec-pipeline layer, above the store. It is popular but has several issues that motivate moving it into the store layer:

- It only caches whole chunks, not metadata or partial reads.
- Its eviction policy is a fixed-size dict with manual eviction by the caller.
- It cannot benefit from range coalescing because it sits above the store.
- It is not part of the stable API and has no migration plan.

A store-level `Caching[S]` wrapper subsumes the experimental layer's functionality, integrates cleanly with the wrapper protocol, and works alongside `RangeCoalescing` and `Retry`. The associated open issues that this addresses: [zarr#278](https://github.com/zarr-developers/zarr-python/issues/278), [zarr#382](https://github.com/zarr-developers/zarr-python/issues/382), [zarr#2988](https://github.com/zarr-developers/zarr-python/issues/2988), [zarr#3570](https://github.com/zarr-developers/zarr-python/issues/3570).

## Caching strategy

Two strategies were considered:

1. **Object-level caching with local slicing.** Every `get_range(key, ...)` call promotes to `get(key)` on the first hit, caches the full object, and serves subsequent range requests by local slicing. Maximally effective for repeated overlapping reads; memory cost is unbounded by range size and surprising for callers with very large objects.
2. **Cache exactly what was requested.** `get_range(key, start=0, end=50)` and `get_range(key, start=0, end=60)` are different cache keys; `get(key)` is yet another. No promotion, no slicing. Memory cost is bounded by what the caller actually requested. Less effective when read patterns vary across slices but doesn't surprise.

We propose strategy 2. The reason: Zarr's read patterns are deterministic per selection, so the "different cache keys for slightly different ranges" failure mode is rare in practice; the predictability of the cache footprint is worth more than the marginal hit-rate gain from local slicing. If a real workload demands object-level caching, it can be added behind a constructor flag (`promote_to_object: bool = False`) without changing the default contract.

## API

```python
class Caching[S]:
    """In-memory LRU cache wrapping S's read capabilities. Writes
    through to the inner store and invalidate matching cache entries.

    Key-agnostic: all cached entries share one LRU bounded by
    `max_bytes` and `max_entries`. The store layer does not know which
    keys are metadata vs chunks; tier-aware caching is the hierarchy
    layer's job (see hierarchy-layer.md).

    Negative-result caching (caching `KeyError`s for a short TTL) is
    opt-in via `cache_negative=True`. The cost / staleness tradeoff is
    documented below.

    Each capability method declares `self: Caching[Capability]` so the
    type checker only allows calls that the inner store actually
    supports (the same self-type narrowing pattern as other wrappers).
    """

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

    def get(
        self: "Caching[Get]",
        key: str,
        *,
        if_not_match: Generation | None = None,
    ) -> ReadResult: ...

    def get_range(
        self: "Caching[GetRange]",
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
        if_not_match: Generation | None = None,
    ) -> ReadResult: ...

    def get_ranges(
        self: "Caching[GetRanges]",
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
        if_not_match: Generation | None = None,
    ) -> Sequence[ReadResult]: ...

    def head(self: "Caching[Head]", key: str) -> ObjectMetadata: ...

    def list(self: "Caching[List]", prefix: str | None = None, *, offset: str | None = None) -> Iterator[str]: ...

    def put(
        self: "Caching[Put]",
        key: str,
        value: bytes | memoryview,
        *,
        if_match: Generation | None = None,
    ) -> PutResult: ...

    def delete(
        self: "Caching[Delete]",
        key: str,
        *,
        if_match: Generation | None = None,
    ) -> None: ...

    def copy(self: "Caching[Copy]", src: str, dst: str) -> None: ...

    # Async variants follow the same pattern with `async def` and
    # `self: Caching[GetAsync]`-style annotations.
```

### `CachingAsync[S]`: the async parallel

`CachingAsync[S]` is the async wrapper with the same semantics as `Caching[S]` — same key-agnostic LRU, same per-key in-flight dedup, same eviction parameters, same composition rules. The split exists for the same reason every other wrapper has sync and async variants (per [stores-api.md § Sync-by-default with async as an opt-in protocol family](./stores-api.md)): each operates over a single sync/async family rather than bridging them.

The constructor signature is identical to `Caching[S]`; only the methods are `async def`. Cache state is shared across all callers of one wrapper instance regardless of which sync/async family they came through. Composition with `SyncToAsync` / `AsyncToSync` works the same way as for the other wrappers.

`CachingAsync[S]` is the return type of `backend.with_caching_async(...)` on async-only backends (see below). Spec coverage in [stores-conformance.md § CachingSpec](./stores-conformance.md) applies to both `Caching` and `CachingAsync` (the test bodies parameterize over the variant).

### The `with_caching(...)` sugar on every backend

Every backend exposes a fluent `with_caching(...)` method that returns a `Caching[Self]`:

```python
class LocalStore:
    def with_caching(self, **kwargs) -> "Caching[LocalStore]":
        return Caching(self, **kwargs)
```

The signature is identical on every backend; `kwargs` forwards to the `Caching` constructor. This is the recommended user-facing entry point for *store-layer* caching ("cache the bytes from this store").

Users who want the tier-aware caching from [performance.md § Default caching policy](./performance.md#default-caching-policy) — metadata on by default, chunks opt-in, ETag revalidation — construct a *hierarchy-layer* cache via `array.with_caching(...)` or `group.with_caching(...)`. The two caches compose: the hierarchy-layer cache wraps the hierarchy verbs ([hierarchy-layer.md](./hierarchy-layer.md)); the verbs call into the store; the store-layer `Caching[S]` (if any) sits between them and the backend. See [hierarchy-layer.md § How caching stratifies cleanly](./hierarchy-layer.md#how-caching-stratifies-cleanly) for the layering picture.

## Defaults

- **`max_bytes = 256 MiB`.** Large enough to hold a working set of decoded metadata and a handful of chunks for typical workloads; small enough not to surprise users who weren't paying attention to memory. Override per workload via the `with_caching(max_bytes=...)` argument.
- **`max_entries = 4096`.** Bounds entry count to avoid pathological "many tiny ranges" cases pushing the LRU into linear-time eviction. Most real workloads hit `max_bytes` first.
- **`ttl = None`** when storage generations are available; `None` defers to revalidation. For backends without generations, set a short TTL (typical: 5–60 seconds depending on staleness tolerance).
- **`cache_negative = False`.** False negatives (cached "not found" for an object that has since been written) are a pernicious bug class. When on, the negative cache is short-TTL'd by default (`cache_negative_ttl = 1.0` second) to bound the staleness window.

## Cache key, lookup, eviction

```python
# Cache keys (illustrative; real implementation may use a more
# compact representation):
ReadKey = (
    tuple[Literal["get"], str]                                # ("get", key)
    | tuple[Literal["get_range"], str, int, int | None]       # ("get_range", key, start, end)
    | tuple[Literal["head"], str]                             # ("head", key)
    | tuple[Literal["list"], str | None, str | None]          # ("list", prefix, offset)
)

# `length` parameter is normalized to `end = start + length` at
# cache-key construction so that two calls that differ only in
# whether they passed end vs length collide on the cache.
```

Eviction is LRU. On a hit, the entry's recency is bumped and the cached value is returned. On a miss, the call is forwarded to the inner store; the result is cached, and any pre-existing entries for the same `key` (across all `(get, key)` and `(get_range, key, ...)` variants) are *not* invalidated, because reads are non-mutating.

When `max_bytes` or `max_entries` is exceeded after a new entry is added, the least-recently-used entries are evicted until both bounds are satisfied. Eviction order is per-entry recency, not entry size; a 100 KiB recently-used entry will outlive a 100 MiB stale entry.

If `ttl` is set, the cache checks the entry's age on read and evicts (treating as a miss) if older than `ttl`.

## Write invalidation

```python
def put(
    self: "Caching[Put]",
    key: str,
    value: bytes | memoryview,
    *,
    if_match: Generation | None = None,
) -> PutResult:
    result = self._inner.put(key, value, if_match=if_match)
    if result.generation is not None:
        self._invalidate_key(key)
    return result

def delete(
    self: "Caching[Delete]",
    key: str,
    *,
    if_match: Generation | None = None,
) -> None:
    self._inner.delete(key, if_match=if_match)
    self._invalidate_key(key)

def copy(self: "Caching[Copy]", src: str, dst: str) -> None:
    self._inner.copy(src, dst)
    self._invalidate_key(dst)
    # Note: `src` is not invalidated because `copy` does not mutate `src`.
```

`_invalidate_key(key)` removes every cache entry where `key` appears as the keyspace argument: `("get", key)`, `("get_range", key, *)`, `("head", key)`, plus any `("list", *, *)` entries that could contain `key` (conservatively: all of them). Implementation strategy: maintain a secondary index from `key → set[ReadKey]` so invalidation is O(matching entries) rather than O(cache size). The `list` invalidation is the awkward case; in practice, list results are usually small and short-lived, and a write to any key invalidates all cached lists. If list-invalidation cost becomes a real concern, the secondary index can be extended to track which prefix patterns each list result covered.

This invalidation contract holds only for writes that go *through the same `Caching[S]` instance*. A second writer (a different process, a different `Caching` instance wrapping the same backend) will not invalidate the first cache; the same is true of any external mutation. This is the documented limitation of in-memory caching with no coherence protocol; users who need cross-process coherence should set a TTL or use a backend with native invalidation hooks (out of scope for this proposal).

## Negative result caching

Off by default. When `cache_negative=True`:

- `get`, `get_range`, `head`: when the inner call raises `KeyError`, cache the absence under the same cache key with a separate "negative" flag and the `cache_negative_ttl` lifetime (default 1 second).
- Subsequent calls within the TTL re-raise `KeyError` from the cache without hitting the inner store.
- `put` to the same key invalidates the negative entry.

The default-off choice is deliberate: cached negatives that survive an external write produce a "key exists in storage but my cache says it doesn't" failure that is hard to diagnose. The 1-second default TTL when enabled bounds the staleness window. Callers running scripts that probe for object existence repeatedly (a common pattern in Icechunk and Zarr's hierarchy walk code) benefit substantially from this; everyone else should leave it off.

## Composition with other wrappers

The recommended ordering for cloud-Zarr workloads:

```python
store = Caching(
    RangeCoalescing(
        Retry(
            AsyncToSync(  # ObstoreStore is async-only; sync wrappers above need a sync surface.
                ObstoreStore(S3Store(bucket="b", region="us-east-1"))
            )
        )
    ),
    max_bytes=512 << 20,  # 512 MiB
)
```

From outside in:

- **`Caching`** is outermost so cache hits short-circuit before any other wrapper does work. A cached coalesced fetch is reused across all callers without re-entering retry, range coalescing, or the underlying obstore call.
- **`RangeCoalescing`** below `Caching` so the cache stores the coalesced result. The cache key is `("get_range", shard_key, group_start, group_end)`, which is what subsequent reads of the same shape ask for.
- **`Retry`** below `RangeCoalescing` so a transient failure on a coalesced fetch is retried as one operation rather than per range.
- **`AsyncToSync`** innermost above the backend because `ObstoreStore` is async-only and the wrappers above expect a sync surface. For an async-throughout stack, drop `AsyncToSync` and use the `Async`-suffixed variants of each wrapper (`CachingAsync`, `RangeCoalescingAsync`, `RetryAsync`).
- **`Tracing`** (when added) wraps the outermost layer to capture both cache hits and the underlying calls; placing it inside `Caching` would miss cache-hit traces and skew operational metrics.

The opposite ordering (`RangeCoalescing[Caching[S]]`) caches per-range fetches *before* coalescing combines them. This caches less because the coalesced groups are formed each call from the (cached) per-range entries, but the cached entries are at the wrong granularity for the coalescing logic to consume. Avoid.

`Caching` composed with `Transactional` is **refused at construction**. `Caching(transactional_store)` raises `TypeError`, and `transactional_store.with_transaction(txn)` on a `Caching`-wrapped store raises symmetrically. See [stores-transactional.md § Composition with other wrappers](./stores-transactional.md#composition-with-other-wrappers) for rationale and the workaround pattern.

## Migration from `experimental.cache_store`

The experimental layer is a function that wraps a store and caches whole-chunk reads at the codec-pipeline layer. Migration:

```python
# Before:
from zarr.experimental import cache_store
store = cache_store(LocalStore("/data"), max_size=256 * 1024 * 1024)

# After:
from zarr.storage.wrappers import Caching
from zarr.storage.stores.local import LocalStore
store = LocalStore("/data").with_caching(max_bytes=256 << 20)
# Or equivalently:
# store = Caching(LocalStore("/data"), max_bytes=256 << 20)
```

Behavioral differences:

- The experimental layer caches at the codec layer (after decoding), so hits return decoded chunks. `Caching[S]` caches at the store layer (before decoding), so hits return raw bytes that still go through the codec pipeline. For the common case of "the codec pipeline is deterministic," the win is the same; for workloads where the codec is expensive (compression-heavy data), the experimental layer's post-decode caching is theoretically better.
- The experimental layer caches per-chunk; `Caching[S]` caches per-`get_range` call. With `RangeCoalescing` above, this is per-coalesced-fetch, which can be larger than per-chunk.
- The experimental layer has no write invalidation. `Caching[S]` does.

For users who want post-decode (decoded-chunk) caching, the right answer is the **hierarchy-layer cache** specified in [hierarchy-layer.md](./hierarchy-layer.md), constructed via `array.with_caching(chunks=True)`. That cache wraps the `read_chunk` verb and stores decoded chunks keyed by `(array_path, chunk_coords)`. It is complementary to the store-layer `Caching[S]`, not a substitute. The two compose: a hierarchy-layer chunk cache wraps the verbs, the verbs call into the store, and a store-layer `Caching[S]` (if configured) catches the encoded-bytes reads.

For the deprecation transition, `experimental.cache_store` keeps emitting a `DeprecationWarning` pointing at `Caching[S]` across the 3.x line (Stream 2), and is removed in the single late major (Stream 3).

## Test plan

The `CachingSpec` in [proposals/stores-conformance.md](./stores-conformance.md#wrapper-preservation-specs) covers the following. Each test uses a counting inner-store mock so cache hits and misses are observable in the assertion.

- `test_cold_read_calls_inner`: first `get(key)` issues exactly one inner `get`.
- `test_warm_read_does_not_call_inner`: second `get(key)` for the same key issues zero inner calls.
- `test_get_range_caches_per_range_tuple`: `get_range(key, start=0, end=50)` and `get_range(key, start=0, end=60)` are separate cache entries; each issues exactly one inner call on first access.
- `test_end_and_length_normalize_to_same_cache_key`: `get_range(key, start=0, end=50)` and `get_range(key, start=0, length=50)` hit the same cache entry.
- `test_max_bytes_eviction`: filling beyond `max_bytes` evicts the LRU entry; the evicted entry is re-fetched from inner on next access.
- `test_max_entries_eviction`: filling beyond `max_entries` evicts the LRU entry regardless of size.
- `test_ttl_expiry`: an entry older than `ttl` triggers a re-fetch.
- `test_put_invalidates_get_cache`: `put(key, value)` causes a subsequent `get(key)` to call inner.
- `test_put_invalidates_get_range_cache`: `put(key, ...)` invalidates `get_range(key, ...)` entries.
- `test_delete_invalidates_cache`: `delete(key)` invalidates all entries for `key`.
- `test_copy_invalidates_dst_only`: `copy(src, dst)` invalidates `dst` cache entries but not `src`.
- `test_negative_caching_off_by_default`: `get(missing)` raises `KeyError` and a second call also raises `KeyError` from inner (one inner call for each, no cache).
- `test_negative_caching_on`: with `cache_negative=True`, the second call within `cache_negative_ttl` raises without an inner call.
- `test_caching_refuses_transactional_inner`: `Caching(transactional_store)` raises `TypeError` at construction. Symmetric test on the transactional side: `transactional_store.with_transaction(txn)` on a `Caching`-wrapped store raises.
- `test_concurrent_get_does_not_double_fetch`: two concurrent `get(key)` calls on a cold cache result in **exactly one** inner call. This is per [performance.md § Caching tier 1](./performance.md#tier-1-unconditional--in-flight-request-deduplication) — in-flight dedup is unconditional regardless of whether `Caching` is in play, and the wrapper consumes the shared substrate's in-flight table.
- `test_caching_is_key_agnostic`: `Caching(store)` treats `get("zarr.json")` and `get("c/0/0")` identically; no metadata-vs-chunk classification happens at this layer. Tier-aware caching is tested separately at the hierarchy layer.
- `test_with_caching_returns_caching_wrapper`: `LocalStore("/x").with_caching()` returns a `Caching[LocalStore]`.

`CapabilityPreservationSpec` runs separately to assert `Caching[S]` advertises the same protocol surface as `S`.

## Open questions

- **Object-level caching with local slicing.** As mentioned in the strategy section, a `promote_to_object: bool = False` flag could enable strategy 1 from the strategy section. Whether to ship this in the initial wrapper or wait for a real workload to demand it is open.
- **Per-call metrics.** Cache hit rate, eviction count, and entry-age distribution are useful for operational visibility. The wrapper could expose them as a `.stats()` accessor, integrate with `Tracing[S]` to emit per-call cache-hit attributes, or both. Out of scope for the initial wrapper; track for the observability proposal.
- **Backing store choice.** The default in-memory LRU is a `dict` plus a `collections.OrderedDict`-like recency list. For larger caches, a disk-backed cache (sqlite, lmdb, plain files) becomes attractive. The wrapper's API is agnostic to the backing store; an alternative `DiskCaching[S]` wrapper or a `backend: CacheBackend` parameter could be added later.
- **Cross-process invalidation.** Out of scope. Mentioned in the migration note above. A future wrapper that integrates with a pub/sub invalidation channel (Redis, etc.) is a separate proposal.
