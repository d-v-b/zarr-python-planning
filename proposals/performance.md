# Performance

> **Cross-cutting theme.** The notes here are not a standalone proposal but a synthesis of the per-theme changes that combine to deliver end-to-end performance wins. For per-theme details, follow the links to [codecs.md](./codecs.md), [stores.md](./stores.md), [functional-core.md](./functional-core.md), and [lazy-indexing.md](./lazy-indexing.md). The caching design lives in [§ Caching](#caching) below.

## Summary

Performance in `zarr-python` is not bottlenecked on raw codec speed. The single largest source of avoidable latency is the *shape* of the library: each layer makes its own concurrency, caching, and allocation decisions independently of the layers around it, so the simple optimizations every other modern array library does — batched reads, deduplicated requests, pre-allocated buffers, capped per-codec parallelism — fall through the cracks.

This document catalogs nine architectural patterns that both [`zarrs`](https://github.com/zarrs/zarrs) (Rust) and [TensorStore](https://github.com/google/tensorstore) (C++) follow, points out where `zarr-python` does not follow them, and proposes a sequenced set of changes. All nine patterns are implementable in pure Python and are independent of the language each reference implementation is written in. The convergence between two independent reference implementations is the strongest evidence available that these are the right patterns — not language-specific tricks. (A separate set of optimizations — true lock-free buffer writes, work-stealing thread pools at rayon granularity — does require native code; those are catalogued in [What is not portable](#what-is-not-portable) below, as items we are declining to chase rather than as lessons.)

## What we can learn from `zarrs` and TensorStore

### 1. Concurrency is typed, library-owned, and shared across nested calls

Both reference implementations treat parallelism as a *limited resource* — not as a per-call argument the caller has to pick correctly. They differ on whether the resource has identity (TensorStore does, zarrs delegates to Rayon), but they agree on the underlying property: there is exactly one cap on actual parallelism, and every nested call within a workload respects it without coordination.

- **TensorStore**: [`Context`](https://google.github.io/tensorstore/python/api/tensorstore.Context.html) carries typed resources — `data_copy_concurrency` (CPU), `file_io_concurrency` (disk), `http_request_concurrency` (network) — each backed by its own bounded `TaskGroup` thread pool with an `AdmissionQueue`. Codec work and IO compete for *different* budgets and cannot starve each other. Nested operations through the same `Context` share the pools; the cap is enforced at the pool, not at the call site.
- **zarrs**: a per-call `CodecOptions::concurrent_target` integer flows down the call stack via `calc_concurrency_outer_inner(target, outer_rc, inner_rc)` in [`zarrs/src/array/concurrency.rs`](https://github.com/zarrs/zarrs/blob/main/zarrs/src/array/concurrency.rs), which splits `target` between outer (chunk-level) and inner (codec-level) parallelism such that `outer × inner ≤ target`. Each codec advertises a `min..max` range via `recommended_concurrency()`; the splitter respects those ranges. **The value only shrinks as it descends** — there is no path for nested code to grow it. Cross-call coordination is delegated to Rayon's global pool: zarrs's `concurrent_target` is a hint into Rayon, which owns the actual thread cap.

**Today in `zarr-python`**: there is *no owned cap*. The single knob is the global `zarr.config["async.concurrency"]` integer ([config.py:103](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/config.py#L103), default `10`). Every call site reads it independently and constructs a *fresh* `asyncio.Semaphore(N)` inside `concurrent_map` ([common.py:95](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/common.py#L95)). The semaphore lives for that one call only. The consequence: an outer `read` with semaphore N spawns `read_batch` coroutines that each construct *their own* semaphore N for store gets, and so on through `BatchedCodecPipeline.read` → `read_batch` → store fetches. Limits don't compose — they multiply. For a shards-of-blosc workload with M concurrent user calls, total inflight is up to `M × N × subchunks_per_shard × blosc_threads`. The user is told they set the budget; they did not.

**Proposed change.** Adopt a hybrid that takes the right axis from each reference implementation:

- **Typed library-owned resources** (TensorStore-shaped). The library owns named pools: at minimum `ComputeConcurrency` (codec encode/decode, buffer copies) and `IoConcurrency` (store reads/writes). Each pool has a bounded thread/admission cap, configurable but library-owned. Nested calls share the same pools because they're library objects, not per-call values. This is the *horizontal* axis — the answer to "what happens when M callers hit the library concurrently."
- **A per-call shrinking-value budget** (zarrs-shaped). When a call enters the library, it requests a slice of the `ComputeConcurrency` pool — call it the call's `concurrent_target`. That value descends the call stack and **strictly shrinks** at each nesting level via a `calc_concurrency_outer_inner`-equivalent: at each codec, the budget is split between outer (chunk-level) parallelism and inner (codec-level) parallelism such that `outer × inner ≤ target`. Each codec advertises a `recommended_concurrency() -> { min, max }` range so the splitter knows where the codec can productively use the budget. This is the *vertical* axis — the answer to "how should one call's budget be divided among the work it does."
- **The two compose.** Pool admission (horizontal) enforces the system-level cap; budget shrinking (vertical) prevents the in-call thread explosion that today's nested-semaphore pattern produces. Two concurrent calls each request their slice from the same pool, the pool's admission queue serializes excess, and inside each call the budget descends monotonically. No multiplication; no coordination protocol; one cap.

This is the single highest-leverage performance change in the proposal — both because the §1–§9 work depends on the codec pipeline knowing what its budget is, and because it closes the long-standing correctness gap where nested calls multiply concurrency. The codec API surface needed for the vertical axis is `recommended_concurrency()` on the base protocol (see [codecs.md § Codecs report their parallelism budget](./codecs.md#codecs-report-their-parallelism-budget)). The plumbing for the horizontal axis is a typed-resource object threaded through `Array` and `Group` construction — same shape as the engine and codec-registry plumbing the [functional-core refactor](./functional-core.md) already requires. The interaction with Dask and free-threaded CPython is treated in [§ Concurrency and correctness](#concurrency-and-correctness) below.

### 2. Per-entry in-flight deduplication

Both libraries guarantee that two concurrent requests for the same chunk produce *one* IO operation.

- **TensorStore**: [`AsyncCache`](https://github.com/google/tensorstore/blob/master/tensorstore/internal/cache/async_cache.h) holds at most one in-flight read or writeback per cache entry. Concurrent requests share the result via futures. This is more powerful than LRU caching because it works even on a *cold* cache — there is nothing to evict, just nothing to duplicate.
- **zarrs**: the sharding partial decoder caches subchunk partial-decoders keyed by index (using [`moka::sync::Cache`](https://docs.rs/moka)), so fancy indexing into the same subchunk hits one decode.

**Today in `zarr-python`**: nothing. Concurrent reads for the same chunk independently re-fetch and re-decode.

**Proposed change**: a per-key `Future` dictionary in the chunk-loading path. Pure Python. Captures the common pattern of multiple consumers (Xarray + a dashboard, Dask workers on the same node) fetching the same chunk concurrently.

### 3. Range coalescing in the store layer

Both libraries merge overlapping or adjacent byte ranges before issuing IO.

- **TensorStore**: `GenericCoalescingBatchReadEntry` + `ForEachCoalescedRequest` walks a batch of `(key, generation, range)` tuples and merges them. The S3 driver tunes the policy with `max_extra_read_bytes=4095, target_coalesced_size=128 MiB`. Results are scattered back via zero-copy `Cord` slicing.
- **zarrs**: `get_partial_many(key, ByteRangeIterator)` is the store-trait verb that hands a sorted list of ranges to the backend. Codecs `sorted_by_key(byte_range)` before calling — the source comment is literally *"Sorting byte ranges may improve store retrieve efficiency."*

**Today in `zarr-python`**: `Store.get_partial_values` exists but the codec pipeline doesn't consistently use it, and no coalescing happens anywhere in the stack.

**Proposed change**: a batched store API (`get_partial_many` shape) with capability flags, range sorting at the codec callers, and a coalescing policy at the store layer with sensible defaults for S3/GCS. See [stores.md](./stores.md) and [stores-range-coalescing.md](./stores-range-coalescing.md).

### 4. Conditional reads using ETags

TensorStore's `KvsBackedCache` issues `If-None-Match: <cached_generation>` on every revalidation. Cache hits cost an HTTP 304 — no body transfer, no decompression. `zarrs` supports the same idea via storage generations in its store trait.

**Today in `zarr-python`**: `FsspecStore` does not expose ETag-aware reads. Repeated opens of the same store (Xarray sessions, dashboards) re-download the full metadata and consolidated-metadata documents every time.

**Proposed change**: storage generations as a store-capability, and metadata loaders that consult them. The change is mostly in the store layer; the cache layer benefits without further work.

### 5. `decode_into` is non-negotiable

Both libraries pass a pre-allocated output buffer into every decode call.

- **zarrs**: `ArrayBytesDecodeIntoTarget::Fixed(&mut ArrayBytesFixedDisjointView)` is plumbed through every `decode_into` and `partial_decode_into`. Sharding decode allocates *one* output `Vec`, wraps it in `UnsafeCellSlice`, and writes all subchunks into the spare capacity in parallel.
- **TensorStore**: `NDIterable` fuses slicing, transpose, and dtype conversion into a single streaming pass that writes directly into the destination — equivalent to a streaming `decode_into`.

**Today in `zarr-python`**: each chunk decode allocates its own output. For a 1024-chunk read, that is 1024 allocations and 1024 copies on the hot path.

**Proposed change**: standardize a decode-into-buffer capability on the codec interface (working name `decode_into`; final naming is the [codecs.md](./codecs.md) proposal's call). Most `numcodecs` C-level codecs already write into a provided buffer; the cost is surfacing the capability in the new codec API. For codecs that don't support it, the fallback allocates per call (the current behavior). The orchestrator pre-allocates the output once per top-level read and slices views into it for each chunk decode.

### 6. Skip fill-value subchunks in sharding writes

`zarrs` checks `ArrayBytes::is_fill_value(fill_value)` before encoding each subchunk and uses the shard-index sentinel `(offset = u64::MAX, size = u64::MAX)` to represent the empty subchunk — no encode, no bytes, no IO. For sparse data this is both a write-time speed-up and a storage-size reduction.

**Today in `zarr-python`**: every subchunk is encoded regardless of content.

**Proposed change**: a fill-value check before sharding-encode, with the sentinel in the shard index. Pure Python, contained to the sharding codec.

### 7. Internal pipeline caches between non-partial-decode codecs

`zarrs`'s `CodecChain::new` walks the chain backwards and, at each codec that lacks `partial_decode` capability, inserts an `ArrayPartialDecoderCache` or `BytesPartialDecoderCache`. The cached value is one full decode; subsequent partial reads of the same chunk avoid redoing the blosc/gzip step.

**Today in `zarr-python`**: partial decode either works for the entire pipeline or not at all. A user doing fancy indexing into a sharded blosc-compressed array re-runs blosc decompression for every fragment of a subchunk.

**Proposed change**: a `PartialDecodeCapability` flag on every codec (`{ partial_read, partial_decode }`), and a pipeline that inserts caches at the right points automatically. The cache type and eviction policy are open questions; per-decoder lifetime (as in zarrs) is the simplest starting point.

### 8. Sync-by-default, async as an opt-in adapter

Both libraries treat async as an adapter, not the substrate.

- **zarrs**: sync API by default; `#[cfg(feature = "async")]` for the async surface.
- **TensorStore**: async at the IO layer (`Future`-returning kvstore ops), but codec encode/decode are synchronous; async is not pushed through the codec stack.

**Today in `zarr-python`**: async-everywhere is the existing complaint in [functional-core.md](./functional-core.md) and [codecs.md](./codecs.md). The performance evidence is that *nobody else does this*, and both reference implementations explicitly route around it. Sync-first encode/decode is a precondition for several of the changes above (in particular, the concurrency-budget propagation in §1, which becomes much simpler when there is no `asyncio.to_thread` round-trip per codec call).

### 9. Adaptive read-whole-shard vs index-then-ranges

TensorStore's `ReadOperationState::ShouldReadEntireShard()` heuristically decides whether to fetch the shard index and coalesce sub-chunk ranges, or just read the whole shard in one GET. `zarrs`'s sharding read path makes a similar choice: full shard for whole-shard reads, intersecting subchunks for subsets.

**Today in `zarr-python`**: the sharding codec uses one strategy regardless of the access pattern.

**Proposed change**: an adaptive heuristic in the sharding codec keyed off the fraction of subchunks requested. Self-contained change inside the sharding codec.

## Caching

Caching deserves its own section because the lessons above interlock around it in a way that is easy to miss when each is read in isolation. §2 (in-flight dedup), §4 (ETag revalidation), §7 (internal pipeline cache), and §9 (adaptive shard reads) are all cache decisions wearing different hats. Both reference implementations recognized this and built one substrate that all of them are specializations of. `zarr-python` today has none of this substrate, and what little caching exists is implemented in mutually-unaware silos. This section catalogs every cache the library should have, names the substrate that backs all of them, and gives the placement story.

### The substrate: one `AsyncCache`-shaped base

The most important design lesson from TensorStore is not any specific cache — it's that one base abstraction backs every cache in the system. [`AsyncCache`](https://github.com/google/tensorstore/blob/master/tensorstore/internal/cache/async_cache.h) is a class that combines four concerns most cache implementations treat separately:

1. **Per-key in-flight deduplication.** At most one read and one writeback in flight per entry; concurrent requests share a future on the same operation. Works on a cold cache.
2. **Cache of decoded (or partially-decoded) values.** Standard LRU role.
3. **Conditional revalidation.** Each entry carries a `TimestampedStorageGeneration` (ETag-equivalent); revalidation issues `if_not_equal=cached_generation` and a hit costs an HTTP 304 with no decode.
4. **Shared byte budget.** All entries across all subclasses report their size via `DoGetSizeInBytes()` to a single [`CachePool`](https://github.com/google/tensorstore/blob/master/tensorstore/internal/cache/cache.h), which evicts LRU across the whole pool regardless of which subclass produced the entry.

The cache instances `AsyncCache` powers are then specializations of this base:

| Specialization | Caches | Keyed by | Where it sits |
|---|---|---|---|
| [`KvsBackedCache`](https://github.com/google/tensorstore/blob/master/tensorstore/internal/cache/kvs_backed_cache.h) | raw bytes from a key-value store | store key | Above the `KvStore`, below the codec pipeline |
| `ChunkCache` ([chunk_cache.h](https://github.com/google/tensorstore/blob/master/tensorstore/internal/cache/chunk_cache.h)) | decoded array chunks (`SharedArray<const void>`) | chunk coordinates | Above the codec pipeline, below the array facade |
| `ShardIndexCache` (in `zarr3_sharding_indexed.cc`) | shard-index portion of a shard | shard key | Inside the sharding codec |
| Metadata caches | parsed array/group metadata documents | metadata key | Above the store, used by every driver |

`zarrs` reaches a similar conclusion with [three distinct chunk-cache types](https://github.com/zarrs/zarrs/blob/main/zarrs/src/array/chunk_cache.rs) (`ChunkCacheTypeEncoded`, `ChunkCacheTypeDecoded`, `ChunkCacheTypePartialDecoder`) plus internal codec-chain caches, but they are not unified under one substrate. TensorStore is the cleaner model.

The lesson for `zarr-python`: introduce *one* base — call it `AsyncCache` for now — and make every cache below a specialization of it. The shared budget, in-flight dedup, and revalidation come for free at every layer; we don't have to re-implement them once per cache type.

### The full catalog

Six caches `zarr-python` should ship as additive 3.x minors (Stream 1; the cache substrate and the unconditional caches in M0/M1, the opt-in chunk caches in M1), each a specialization of the shared substrate:

#### 1. Chunk cache (decoded)

Decoded array chunks keyed by `(array, chunk_coords)`. This is the cache [zarr#278](https://github.com/zarr-developers/zarr-python/issues/278) has been requesting for years. The cache is opt-in (caching decoded chunks can hurt for write-heavy or one-shot workloads, as `zarrs`'s docs explicitly warn) but available as a wrapper or context manager.

**What this fixes**: repeated access to the same chunks in interactive analysis, the multi-consumer case where Xarray and a dashboard read the same arrays, dask graphs that materialize the same chunk multiple times.

**Substrate features used**: in-flight dedup (1), decoded-value LRU (2), shared budget (4).

#### 2. Chunk cache (encoded)

Raw chunk bytes keyed by store key. Useful when decoded chunks are too large to cache but the network round-trip is the bottleneck — relevant for cloud workloads where decode is fast but GET latency is high.

**Substrate features used**: all four. Encoded chunks revalidate cheaply with ETags (3).

#### 3. Shard index cache

The index portion of a shard, separate from sub-chunk data. After the first read of a shard, subsequent subchunk reads in the same shard skip the index round-trip — a substantial latency win for large sharded arrays accessed with fine-grained selections.

**Substrate features used**: in-flight dedup (1), decoded LRU (2). The shard index is small; budget pressure is unlikely.

#### 4. Metadata cache

Parsed array and group metadata, plus consolidated metadata documents. Today, every `zarr.open(...)` re-fetches metadata. With ETag revalidation a cache hit costs a 304; an Xarray session that re-opens the same store on every refresh goes from seconds to milliseconds. Closely related to [consolidated-metadata.md](./consolidated-metadata.md).

**Substrate features used**: all four. ETag revalidation (3) is the headline benefit.

#### 5. Partial-decoder cache (internal pipeline)

This is §7 of the lessons section, made concrete. When the codec chain contains a codec that lacks partial-decode support (blosc, gzip), the pipeline inserts a cache between it and the partial-decode caller. The cached value is one full decode of that codec's output. Subsequent fancy-indexing reads of the same chunk skip re-decompression of the same bytes.

**Substrate features used**: in-flight dedup (1), decoded LRU (2). Per-decoder lifetime is the simplest starting point; `zarrs` uses [`moka::sync::Cache`](https://docs.rs/moka) for this and the equivalent in Python is straightforward.

#### 6. Negative result cache

Confirmed-absent keys, for the case where `exists()` or `get()` returns "not found." Without this cache, every `Group.__contains__("missing_key")` reissues a STAT to the backend. Relevant for code that probes for optional attributes or hierarchies. See [zarr#3570](https://github.com/zarr-developers/zarr-python/issues/3570).

**Substrate features used**: in-flight dedup (1), shared budget (4). Negative entries are small but can be numerous; TTL eviction (rather than pure LRU) is the right policy.

### Cache placement on the stack

Mapped onto the Zarr Stack levels from the README:

```
Application (Xarray, napari, dashboards)
────────────────────────────────────────
Arrays / Groups                            ← Chunk cache (decoded)
                                           ← Metadata cache
────────────────────────────────────────
Chunk decoding (codec pipeline)            ← Partial-decoder cache (internal)
────────────────────────────────────────
Chunk addressing                           ← Shard index cache
────────────────────────────────────────
Stores                                     ← Chunk cache (encoded)
                                           ← Negative result cache
────────────────────────────────────────
```

The substrate is a **horizontal capability** that cuts through every level. Each instance caches the right granularity for the boundary it sits at. The shared `CachePool` ensures that when memory is tight, the LRU evicts across all caches uniformly rather than letting any one cache monopolize the budget.

The caches at the array/group layer (decoded chunk, metadata) are not store-layer wrappers. They wrap the [hierarchy-layer verbs](./hierarchy-layer.md) (`read_array_metadata`, `read_chunk`, ...) because the store layer is key-agnostic and cannot tell a metadata read from a chunk read. The encoded-chunk and negative-result caches at the bottom of the diagram *are* store-layer wrappers ([`Caching[S]`](./stores-caching.md)) because they cache bytes-at-keys and need no hierarchy knowledge. The shard-index and partial-decoder caches live inside the codec pipeline and are managed by it. The substrate is shared; the wrappers stratify by what each layer can reason about.

### How caching interacts with other proposals

Caching-specific cross-references (the document-level [Relationship to other proposals](#relationship-to-other-proposals) covers everything else):

- [`stores.md`](./stores.md) — provides the storage-generation capability that the metadata and encoded-chunk caches use for ETag revalidation. The existing [`stores-caching.md`](./stores-caching.md) wrapper becomes a *consumer* of the shared substrate rather than a separate implementation.
- [`stores-range-coalescing.md`](./stores-range-coalescing.md) — coalescing happens *before* the cache is consulted (a coalesced range can scatter back to multiple cache entries). Composes cleanly.
- [`codecs.md`](./codecs.md) — the partial-decoder cache requires the `PartialDecodeCapability` flag on every codec. Without it, the pipeline can't know where to insert caches.
- [`consolidated-metadata.md`](./consolidated-metadata.md) — the metadata cache is the consumption side of consolidated metadata. Together they collapse open-time latency for hierarchies.
- [`functional-core.md`](./functional-core.md) — the cache substrate is a stateful object (mutable LRU, mutable in-flight table) and lives in the edge layer alongside stores and codecs, not in the pure core.
- [`lazy-indexing.md`](./lazy-indexing.md) — the query planner sits above the cache: it consults the cache (and the in-flight table) when building the IO plan, so a slice whose chunks are already cached generates no IO at all.

### Default caching policy

The catalog above describes *what caches can exist*. A separate decision is **which of them are on by default**. The position taken here is that the right default is not uniform — some caches are unconditional wins, others are workload-dependent, and the library should ship a three-tier policy rather than one global switch.

This policy is implemented at the **hierarchy layer**, not the store layer. The store layer's `Caching[S]` ([stores-caching.md](./stores-caching.md)) is key-agnostic — it cannot tell a metadata read from a chunk read because the store layer doesn't know about hierarchy semantics. The tier-aware policy below requires hierarchy knowledge ("this is a `read_array_metadata` call; cache it" vs "this is a `read_chunk` call; only cache if opted in") and therefore lives in the hierarchy-layer cache wrapper that wraps the hierarchy verbs ([hierarchy-layer.md § How caching stratifies cleanly](./hierarchy-layer.md#how-caching-stratifies-cleanly)). The user-facing entry point is `array.with_caching(...)` and `group.with_caching(...)`; the store-layer `backend.with_caching(...)` is a separate, key-agnostic surface for "cache the raw bytes from this backend."

#### Tier 1: Unconditional — in-flight request deduplication

In-flight dedup (per-key futures, lesson §2) is not a cache in the usual sense. It does not retain anything after the request completes; it only guarantees that two concurrent calls for the same key produce one IO. The cost is a single dict entry per in-flight request, freed on completion. There is no staleness window, no memory budget to tune, and no workload for which it is the wrong call.

**Position**: every store has in-flight dedup. There is no opt-out. It lives in the substrate ([§ Caching above](#the-substrate-one-asynccache-shaped-base)), not behind a wrapper. Wrappers that *do* cache (the chunk and metadata caches below) reuse this same in-flight table; the substrate's in-flight machinery is what makes the cache-promotion pattern (decoded chunk cache fronting an undecoded read) safe under concurrent access.

The user gets this whether they construct `LocalStore("/data.zarr")`, `Caching(ObstoreStore(s3_store))`, or any other combination. Concurrent reads of the same chunk under Xarray + a dashboard are collapsed to one IO without the user thinking about it.

#### Tier 2: On by default — metadata cache

Zarr metadata is small, changes infrequently, and is re-read on every `zarr.open(...)`. The ETag-revalidation path (lesson §4) makes the cache safe under most concurrency: a stale cache costs an HTTP 304 to refresh, not a wrong answer. The pathological cases — metadata that churns faster than the cache TTL, multi-writer scenarios with no synchronization — are detectable (revalidation fails, generations don't match) and rare in practice.

The benefit is concrete. Xarray's `open_zarr(...)` re-reads the consolidated metadata document on every call; today that is a full GET, decode, and validate. With metadata caching plus ETags, repeat opens cost a 304 — the user-perceived dashboard refresh time drops from seconds to milliseconds.

**Position**: the metadata cache is on by default with a small bounded budget (proposed starting point: ~10 MB, configurable; the number is a placeholder for benchmarking). Revalidation uses storage generations when the underlying store supports them (per [stores.md](./stores.md)); for stores that don't, the cache uses a short TTL (proposed starting point: ~5 seconds, configurable). When a TTL-tracked entry is read past its TTL the cache transparently re-fetches the metadata document, decodes it, and replaces the entry. On generation-bearing stores, revalidation is exact and there is no staleness window. **On generation-less stores the on-by-default cache is a behavior change that must be called out loudly:** today's behavior re-reads metadata on every open and is *never* stale, whereas a default-on TTL cache introduces a staleness window of up to the TTL. The default therefore pins to ETag/generation revalidation where available and treats the TTL fallback as opt-in with a loud note — and the metadata cache is not flipped on by default before store-layer conditional reads (revalidation) are wired, or it ships without its safety mechanism.

A user with a legitimate need to disable it (test fixtures that depend on observing every read; correctness-debug sessions) does so with `array.with_caching(metadata=False)`.

#### Tier 3: Opt-in — chunk cache

Chunk caching is workload-dependent in a way the other two are not:

- **Read-heavy interactive analysis** (the prototypical Jupyter-with-Xarray workload): caching is the right default. Repeated access to overlapping regions is the access pattern, and the speedup is multiplicative.
- **One-shot bulk processing** (write-once-read-once pipelines, ETL into a sink): caching is wasted memory. The cache fills, the data is never re-read, and the user's RSS goes up for no benefit.
- **Bulk write workloads** (initial array population, rechunking, format conversion): caching can hurt. Each chunk write invalidates any cached read of the same chunk; the cache thrashes and the invalidation overhead is pure cost.
- **Multi-writer scenarios** (Dask workers writing to disjoint regions; Icechunk transactional writers): caching introduces a coordination problem that has to be solved per-deployment. Default-on caching makes "did this writer see the other writer's change?" an implicit question the user has to answer for every operation.

The two reference implementations agree. `zarrs`'s [chunk-cache documentation](https://github.com/zarrs/zarrs/blob/main/zarrs/src/array/chunk_cache.rs) explicitly warns: *"Chunk caching may reduce performance. Benchmark your algorithm."* TensorStore exposes caching as an explicit `cache_pool` resource that the user attaches. Neither makes it the default.

**Position**: the chunk cache is opt-in. The user enables it explicitly on an opened array or group, *not* on a store (because the store layer is key-agnostic and can't distinguish chunks from metadata):

```python
# Open an array — no chunk caching by default.
arr = zarr.open_array("/data.zarr")

# Same array, chunk caching enabled with the default size:
arr = zarr.open_array("/data.zarr").with_caching(chunks=True)

# Or with an explicit budget:
arr = zarr.open_array("/data.zarr").with_caching(chunks="256 MB")
```

The `Array.with_caching(...)` / `Group.with_caching(...)` methods construct the hierarchy-layer cache wrapper (per [hierarchy-layer.md](./hierarchy-layer.md)). They are sugar over the wrapper constructor; making them one-call methods means users discover them via autocomplete and documentation, not by knowing to wrap manually. A separate, key-agnostic `backend.with_caching(...)` exists on every backend ([stores-caching.md](./stores-caching.md)) for the lower-level case "cache raw bytes from this backend"; the two compose.

For the cases where chunk caching is obviously right — interactive Jupyter sessions in particular — the project ships a named preset. Concretely, something along the lines of `zarr.use_preset("interactive")` (or `ZARR_PRESET=interactive` in the environment) flips a small set of defaults for that process: chunk caching on, larger metadata budget, and any other interactive-friendly settings the preset gains. The preset is a named bundle of config overrides; the configuration substrate that holds them is being redesigned (see [configuration.md](./configuration.md) — `donfig` is being retired as part of the foundation work (Stream 1 · M1)), but the *shape* — a preset name resolving to a bundle of overrides — survives whatever substrate replaces it. The user gains the caching with one config line; the library does not silently double the memory cost of every script that opens a Zarr array.

#### Other caches in the catalog

The remaining caches in the catalog (encoded chunk cache, shard index cache, partial-decoder cache, negative-result cache) follow the same logic:

- **Encoded chunk cache**: opt-in at the *store* layer via `backend.with_caching(...)` (key-agnostic; sees raw bytes). Same workload-dependence as the decoded chunk cache.
- **Shard index cache**: on by default for sharded arrays. The shard index is small, accessed on every subchunk read, and never changes once a shard is written. The cost is negligible. Managed inside the sharding codec.
- **Partial-decoder cache (internal pipeline cache)**: managed by the codec pipeline itself, not user-facing. The pipeline inserts caches at the right points per [lesson §7](#7-internal-pipeline-caches-between-non-partial-decode-codecs); the user does not see them. Lifetime is per-call (one full decode reused across the partial reads of that call), so memory pressure is bounded by request shape.
- **Negative result cache**: off by default. Lives at the *store* layer ([stores-caching.md](./stores-caching.md) — `cache_negative=True`). Useful for code that probes for optional keys; harmful for code that races a check against a create.

#### Summary

| Cache | Default | Why |
|---|---|---|
| In-flight dedup | Unconditional | No staleness, no budget, always-correct, always-helpful |
| Metadata cache | On (small budget, ETag-revalidated) | Small, infrequent changes, big interactive-latency win |
| Shard index cache | On (sharded arrays only) | Tiny, immutable, hot path |
| Chunk cache (decoded) | Opt-in via `array.with_caching(chunks=True)` (hierarchy layer) | Workload-dependent; bad default for writes and bulk ETL |
| Chunk cache (encoded) | Opt-in via `backend.with_caching(...)` (store layer; key-agnostic) | Same workload-dependence as decoded; different layer |
| Partial-decoder cache | On (automatic, per-call lifetime, no user surface) | Bounded by request shape; the win is fancy indexing into compressed chunks (§7) |
| Negative-result cache | Opt-in via `backend.with_caching(cache_negative=True)` (store layer) | Race conditions with concurrent creates |

The principle: the default is the right answer for *almost everyone* in the case where the answer is universally correct, and opt-in everywhere else. The user who wants more caching gets it with a single method call; the user who wants none gets it the same way. The library does not silently make memory or consistency decisions for the user when those decisions depend on workload.

### Substrate sketch

The cache substrate is one base class: a dict keyed by entry-key holding `(value, generation, size, future-or-None)`, an LRU ordering (`collections.OrderedDict` for a first cut), a byte-budget counter with an eviction loop, and a per-key `asyncio.Future` (or `concurrent.futures.Future`) for in-flight dedup. Eviction policies, LRU implementations, and per-thread variants are well-trodden ground — the work is in shape, not in performance-critical kernels.

### Caching-specific open questions

(The document-level [Open questions](#open-questions) covers cross-cutting concerns; these are caching-only.)

- **Per-process vs shared-memory.** Cross-process caching ([zarr#3488](https://github.com/zarr-developers/zarr-python/discussions/3488)) is out of scope for the v4 work but should not be designed *away* — the substrate should leave room.
- **TTL vs LRU vs hybrid eviction.** LRU works for most caches; the negative-result and metadata caches want TTL when the backend lacks storage generations. Pluggable eviction policy is the cleanest answer.
- **Interaction with Dask workers.** Each worker has its own process; without shared-memory caching, the chunk cache is per-worker. May want explicit guidance for Dask users on cache sizing.
- **Tuning the `interactive` preset.** What does the preset turn on beyond chunk caching? Encoded-chunk caching too? Larger metadata budget? The preset is a useful escape hatch but its contents need to be decided.
- **ETag revalidation × range coalescing.** When the cache holds validated ranges and the user requests an overlapping selection, do we revalidate first and then fetch misses, or fold revalidation into the coalesced fetch? TensorStore's `KvsBackedCache` does revalidate-first-then-fetch-miss; we should probably match it, but the interaction needs to be specified before implementation.

## Concurrency and correctness

Performance work is meaningless if the result returns wrong answers. `zarr-python` today has a stream of open bugs against thread safety, multiprocessing, and async-event-loop reentrancy ([zarr#1435](https://github.com/zarr-developers/zarr-python/issues/1435), [zarr#3126](https://github.com/zarr-developers/zarr-python/issues/3126), [zarr#2729](https://github.com/zarr-developers/zarr-python/issues/2729), [zarr#2878](https://github.com/zarr-developers/zarr-python/issues/2878), [zarr#3487](https://github.com/zarr-developers/zarr-python/issues/3487), [zarr#2909](https://github.com/zarr-developers/zarr-python/issues/2909)) — most of them traceable to the same structural choice as the performance bottlenecks: async layered on top of sync, with stateful objects whose lifecycle and event-loop affinity aren't clearly specified, and no library-owned concurrency cap to coordinate them under.

This section takes a position on the correctness model that the performance changes assume. It is the contract under which §1's typed-resource concurrency model, the cache substrate, and the engine boundary are sound.

### Who owns the concurrency cap

**Position:** the library does, via typed resource objects threaded through `Array` / `Group` / store construction. This is the concrete commitment §1 above relies on.

Two named resources, both library-owned, both bounded:

- **`ComputeConcurrency`** — bounds CPU-bound parallelism (codec encode/decode, buffer copies, planner work). Backed by a `ThreadPoolExecutor` with an explicit `max_workers` cap.
- **`IoConcurrency`** — bounds IO-bound parallelism (store reads/writes, network operations). Backed by an `asyncio` event loop with an `asyncio.Semaphore`-style admission queue, or a separate `ThreadPoolExecutor` for sync stores.

Per-call budget descends through the call stack as a shrinking integer (per §1's zarrs-shaped vertical axis): a call requests a slice of `ComputeConcurrency`, the slice is split between outer and inner parallelism at each nesting level, the budget at depth N is always ≤ the budget at depth N−1. The pool's admission queue enforces the *system-level* cap; the shrinking value enforces the *per-call* invariant. The two compose.

Resources are constructed once (defaulted by the library or supplied by the user) and live at the facade. Two concurrent user calls on the same `Array` request slices from the same pools — they automatically share the budget, no coordination required.

Defaults:

- `ComputeConcurrency` defaults to a **cgroup/affinity-aware** core count (not raw `os.process_cpu_count()`, which ignores container CPU quotas and over-allocates on a quota-limited host), drawn from a **single shared process-global pool** rather than a fresh pool per call or per array, and **conservative when nested** inside an outer scheduler (see [§ Interaction with Dask](#interaction-with-dask-and-other-host-runtimes)).
- `IoConcurrency` is a **separate** pool sized to a latency-hiding constant **decoupled from the core count** (proposed: ~32), because IO latency, not core throughput, is the bottleneck — scaling it with `cpu_count` is wrong on both small and large machines.
- Both are configurable. The configuration substrate itself is being redesigned — the current `donfig`-based `zarr.config` is to be replaced as part of the foundation work (Stream 1 · M1); see [configuration.md](./configuration.md). The shape of the knobs is `compute_max_workers` and `io_max_workers` regardless of how they're surfaced.

This replaces today's single global `zarr.config["async.concurrency"]` integer ([config.py:103](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/config.py#L103)) and the singleton `_get_executor` ([sync.py:49](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/sync.py#L49)). The typed pools ship as an additive 3.x minor (Stream 1) alongside the old integer; the `async.concurrency` key is then deprecated (Stream 2) and removed only in the single late major (Stream 3). The integer goes away; the pool stays (now categorized).

### Interaction with Dask and other host runtimes

Dask workers already manage their own thread pools and don't want `zarr-python` to spawn a competing one inside each worker. The typed-resource model makes this clean: at `Array` construction, the user (or Dask itself, via integration code) supplies `ComputeConcurrency` and `IoConcurrency` instances backed by the host's executors instead of the library defaults. The shrinking-value budget propagation still works — the call requests a slice of the supplied resource — but the actual threads come from Dask's pool, not a library singleton.

This is the same shape as TensorStore's `Context` integration with external schedulers. The current "library spawns a singleton pool no one asked for" pattern is what makes the Dask integration story today require careful tuning of `async.concurrency` to avoid pool-times-pool blowup. The typed-resource model retires that class of bug **when a host pool is injected** — but the *default* must also be safe, because most Dask users will not write injection code. A naive `os.process_cpu_count()` default reproduces the blowup: under the threaded scheduler ~`cpu_count` worker threads each drive zarr's shared pool (~2× core oversubscription), and under the multiprocessing scheduler ~`cpu_count` worker *processes* each spin their own ~`cpu_count`-sized pool (≈ `cpu_count²` threads box-wide). The default is therefore the cgroup-aware, shared, conservative-when-nested one specified in the Defaults list above; injection remains the path to *exact* host-pool sharing.

### Thread safety

**Position:** every object specified in this proposal set — store backends and wrappers, codec instances, cache substrate entries, lazy-array views, IO plans — is **safe to share across threads for read operations**. Store-handle-holding backends (`ZipStore`) document any exceptions explicitly.

This is more restrictive than today (where shared array initialization is unsafe per [zarr#1435](https://github.com/zarr-developers/zarr-python/issues/1435)) but much weaker than "all operations are thread-safe regardless of what the user does." Concretely:

- **Reads are concurrent-safe**. Two threads calling `store.get(key)` or `array[selection]` on the same store/array in parallel observe consistent results. The cache substrate's in-flight dedup (lesson §2) guarantees this even when both threads miss the cache simultaneously.
- **Writes are user-coordinated**. Two threads calling `array[selection] = data` for overlapping selections is the user's responsibility to serialize, exactly as in NumPy. Per-key atomicity (via `Put`'s `if_match` in stores-api.md) is what backends offer for atomic concurrent writes to the *same* key; multi-key atomicity is `Transactional`'s job.
- **Object construction is not the problem it is today**. The lifecycle changes in [stores.md](./stores.md) (stateless backends, no `_is_open`, construction-time existence checks) make store construction itself trivially thread-safe. Array and group construction become thread-safe by the same route: the functional core's pure-data layer has no mutable shared state to race on.

The conformance suite gains a `ThreadSafetySpec` (in [stores-conformance.md](./stores-conformance.md)) that parameterizes per backend and per wrapper, exercising the contract under `concurrent.futures.ThreadPoolExecutor` and Hypothesis-driven concurrent operation sequences.

### Multiprocessing

**Position:** stores are **picklable** and **fork-safe**. Pickling a store and unpickling it in another process produces an equivalent store. Forking a process holding a store produces working copies in both parent and child without explicit reconstruction.

The current state is the opposite — [zarr#3126](https://github.com/zarr-developers/zarr-python/issues/3126) (modifying a `MemoryStore` from multiprocessing fails) and [zarr#2729](https://github.com/zarr-developers/zarr-python/issues/2729) (V3 + multiprocessing raises `JSONDecodeError`) both document this. The root cause is shared mutable state (event loops, lazy-open flags, fsspec filesystem instances) that doesn't survive the process boundary.

The `Serializable` capability from [stores-api.md § Capability protocols](./stores-api.md#capability-protocols) is the building block: any store advertising `Serializable` has `__getstate__` / `__setstate__` defined in terms of `to_declaration` / `from_declaration`, which is exactly the shape pickle wants. For fork-safety, the rule is "no event loops, no file handles, no caches in `__init__`" — pure declarations only. Resource-holding backends (`ZipStore`, future SQLite stores) document their fork behavior and provide an explicit `__post_fork__` hook for child-side reinitialization.

Cache contents are *not* preserved across pickling or forking; each process gets a fresh cache. This matches what users expect from a per-process LRU.

### Async event loops

**Position:** async support is a thin opt-in layer at the IO edge, not a substrate. The same store has sync and async surfaces specified independently (per [stores-api.md](./stores-api.md)'s sync-first design), and there is **exactly one supported reentrancy contract**: sync code calls sync APIs; async code calls async APIs; the bridges (`SyncToAsync[S]`, `AsyncToSync[S]`) are explicit user choices, not implicit machinery.

The bugs being fixed:

- [zarr#2878](https://github.com/zarr-developers/zarr-python/issues/2878): `async zarr.create_array` fails on the second call through `async.run()`. Root cause: a shared global event loop that gets closed between calls. Fix: no implicit global loop. Async store methods use the caller's loop.
- [zarr#3487](https://github.com/zarr-developers/zarr-python/issues/3487): mixing fsspec and `FsspecStore` raises *"Task attached to a different loop."* Root cause: implicit loop ownership inside the store. Fix: store doesn't own a loop; the caller's context does.
- [zarr#2909](https://github.com/zarr-developers/zarr-python/issues/2909): using both `AsyncArray` and `Array` simultaneously breaks. Root cause: the sync-on-top-of-async pattern needs to drive a loop from inside an already-running loop. Fix: per [stores-wrappers.md § AsyncToSync](./stores-wrappers.md#asynctosyncs), `AsyncToSync` documents the reentrancy rule explicitly and the implementation raises a clear error rather than deadlocking when a user violates it.

This is fundamentally enabled by lesson §8 (sync-by-default codec API): once the codec hot path is sync, the only async surface is the store, and the only place a loop needs to live is the user's call frame.

### Free-threaded CPython (no-GIL)

**Position:** the proposal set targets free-threaded CPython 3.13+ as a first-class deployment target ([zarr#2776](https://github.com/zarr-developers/zarr-python/discussions/2776)). All of the above thread-safety guarantees hold without the GIL; the structural changes that make them true (functional-core pure-data layer, stateless stores, explicit cache substrate with one in-flight table) are exactly the structural changes that make no-GIL safe.

Two specific implications:

- **Free-threaded mode amplifies the win from sync-first codecs.** With the GIL, parallel codec decode is bottlenecked on GIL contention; per-chunk parallelism barely helps because every thread is fighting for the same lock. Free-threaded mode plus the §1 typed-resource model means N codec decodes can actually run in parallel — and the `ComputeConcurrency` pool's admission queue is what stops them from exceeding the configured cap.
- **The cache substrate's in-flight dedup must use thread-safe primitives** under free-threaded mode. `asyncio.Future` and `concurrent.futures.Future` both work, but the dict mutation around them needs explicit locking that doesn't exist today under GIL assumptions.

`zarr-python`'s C-extension dependencies (notably `numcodecs`) gain no-GIL support on their own schedule; the proposal here is that `zarr-python` itself does not assume the GIL, and audits any remaining `threading`-unsafe code as part of the foundation work (Stream 1 · M1).

### Sequencing relative to §1–§9

These correctness concerns are not separate work items — they are properties the §1–§9 changes deliver as side effects of the structural cleanup. Concretely:

- The §1 typed-resource concurrency work depends on sync-first codecs (§8) and gives us the natural place to put per-codec lock discipline.
- The cache substrate (sequencing table row 4) is the place to put the in-flight dedup table that's also the thread-safety primitive.
- The store-lifecycle simplification in [stores.md](./stores.md) (stateless backends, no `_is_open`, no implicit loop) is what makes pickling, forking, and event-loop interop tractable.
- The `Serializable` capability (per the addition above) is what makes pickling work cleanly.

In other words, getting concurrency right is the *test* that the rest of the proposal succeeded. If the §1–§9 work plus the cache substrate and store-lifecycle changes ship and the open concurrency bugs above are still open, something didn't actually land.

### What we are not committing to

- **No `multiprocessing.shared_memory`-based shared caches across processes.** Cross-process caching is out of scope ([zarr#3488](https://github.com/zarr-developers/zarr-python/discussions/3488)), per the [caching open questions](#caching-specific-open-questions).
- **No locking around user code.** If a user calls `array[selection] = data1` and `array[selection] = data2` concurrently from two threads, the library does not detect or prevent it. Per-key atomicity at the store layer is the contract; coordination above that is the user's job.
- **No async-from-sync convenience helpers.** The `zarr.core.sync.sync()` bridge and similar global bridges are deprecated across the 3.x line (Stream 2) once the public `AsyncToSync` bridge ships, and removed only in the single late major (Stream 3). Users who want to call async-only stores from sync code wrap the store in `AsyncToSync[S]` explicitly (per [stores-wrappers.md](./stores-wrappers.md)).

## What is *not* portable

A handful of optimizations from the reference implementations are not realistic in pure Python. For each, we describe what is genuinely unportable and what the workable Python equivalent looks like:

- **True parallel codec execution within a single chunk.** The GIL plus Python-level codec dispatch overhead makes this rarely worthwhile; both reference implementations do per-*chunk* parallelism, not per-codec-within-chunk. No Python equivalent is proposed.
- **Rust-style lock-free disjoint writes into one preallocated buffer (`UnsafeCellSlice`).** The Rust pattern of unsafe-aliased concurrent writes into one `Vec` is not expressible in Python. **The workable Python equivalent** is "allocate output once, take numpy views into it per subchunk, decode-into in parallel." This works when the codec releases the GIL during decode — most `numcodecs` C-level codecs already do — and is enabled by §5 above. We are giving up the Rust-specific construct, not the optimization.
- **Work-stealing thread pools at the granularity of rayon or TensorStore's `TaskGroup`.** Python's `ThreadPoolExecutor` plus bounded admission queues (per §1) gets us close enough; the difference matters mostly for very-high-throughput numerical workloads where Python is the wrong tool anyway.

## Wrapping `zarrs` and TensorStore as alternative engines

The architectural changes above close most of the performance gap between `zarr-python` and the reference implementations, but they do not close all of it. For workloads where the user genuinely wants compiled-language throughput — large reads from cloud storage, dense decode-heavy pipelines, very wide concurrency — we should make `zarrs` and TensorStore available as **pluggable engines** behind `zarr-python`'s public API, not as separate libraries the user has to migrate to. (Note that this puts `zarrs` and TensorStore in two roles simultaneously: above, they are *models* we learn architectural patterns from; here, they are *backends* we propose to wrap. The two roles are complementary — learning from them informs the engine interface, and wrapping them gives users their performance without the migration cost.)

This is the producer side of the engine architecture in [functional-core.md](./functional-core.md). An engine is a small module that exports four functions — `read_chunk`, `read_selection`, `write_chunk`, `write_selection` — and consumes a metadata document, a store, and an IO plan to produce materialized arrays. The default engine is pure Python; alternative engines exist for `zarrs` and TensorStore.

### What we ship

- `zarr.engines.python` — the default engine. Always available, pure-Python, no extra dependencies. Implements every feature.
- `zarr.engines.zarrs` — a thin wrapper module published either inside `zarr-python` (with an optional dependency) or as a sibling package (`zarr-engine-zarrs`). Delegates the four functions to `zarrs` via the existing [`zarrs-python`](https://github.com/zarrs/zarrs-python) bindings — but driven by `zarr-python`'s metadata, hierarchy, and store layers rather than reimplementing them. The current `zarrs-python` package reimplements much of `zarr-python`'s array logic precisely because there is no clean seam; the functional-core refactor provides that seam.
- `zarr.engines.tensorstore` — equivalent wrapper for TensorStore. Same shape, different backend.

Switching engines is a one-line keyword argument or configuration setting:

```python
arr = zarr.open(..., engine="zarrs")    # delegates IO to zarrs
arr = zarr.open(..., engine="default")  # pure-Python (current behavior)
```

The public `Array` and `Group` classes do not change. Xarray, Dask, napari, and every other downstream library continue to work with arrays returned by any engine — they see the same `Array` surface regardless of which engine is loaded underneath.

### Where the caching substrate sits relative to engines

The cache substrate from [§ Caching](#caching) is *above* the engine boundary, not inside any one engine. Concretely:

- The metadata cache, chunk cache (when opted into), shard index cache, and negative-result cache all sit at the `Array`/`Group` layer. They wrap engine calls; the engine sees deduped, cache-checked requests rather than raw user requests.
- In-flight deduplication is unconditional regardless of engine. Two concurrent `read_chunk` calls for the same chunk produce one engine call, even if the engine is `zarrs` or `tensorstore`.
- Engines bring their own internal caches (TensorStore's `KvsBackedCache`, zarrs's codec-chain caches) if they want; those are private to the engine and not user-configurable through `zarr-python`'s cache surface.

This preserves the "every store has dedup, metadata cache is on by default" position from [§ Default caching policy](#default-caching-policy) regardless of which engine the user selects. Switching from the Python engine to `zarrs` changes how chunks are decoded, not whether they are deduplicated or cached.

### Why this is the right shape

**Users keep their ecosystem.** Today, choosing `zarrs` or TensorStore for performance means leaving `zarr-python` entirely. The user loses Xarray's `open_zarr`, Dask's `from_zarr`, every domain-specific reader built on top, and every store backend `zarr-python` supports. The engine model says: keep the surface, swap the engine.

**Engines stay in their lane.** A `zarrs` engine doesn't need to handle metadata, hierarchy, attributes, or convention-level validation — `zarr-python` does that. The engine handles exactly what it is good at: turning chunk byte ranges into decoded arrays as fast as possible.

**Mix-and-match becomes natural.** A user can plausibly want *"Python orchestration with Zarrs's blosc codec"* or *"TensorStore's IO with Python's codec pipeline."* In the engine model these are short modules that import the relevant pieces from each engine. We don't have to anticipate every combination — the functional-core split makes composition cheap.

**The competitive narrative inverts.** Instead of "TensorStore is the faster choice; you have to leave us to get its speed," the message becomes "TensorStore is a backend you can plug into the library you already use." `zarr-python` stays the center of gravity for the Zarr ecosystem; the high-performance backends become amplifiers rather than competitors.

### What this requires

- **The functional-core refactor** ([functional-core.md](./functional-core.md)). This is the precondition. Without a clean seam between "what to do" and "how to do it," an engine cannot take over IO without re-implementing the layers above.
- **A serializable store declaration**. The engine runs in native code (or via FFI). It needs to know how to construct its own equivalent of the user's store on the other side. Specified as the [`Serializable` capability in stores-api.md](./stores-api.md#capability-protocols); produces a `StoreDeclaration` data structure that the engine consumes. The method names in the current sketch are illustrative — what matters is the capability.
- **A serializable codec configuration**. Same constraint, same shape, already implicit in the new codec API ([codecs.md](./codecs.md)).
- **An engine conformance suite**. The same architectural changes that benefit the Python engine (sync-first codecs, batched store API, range coalescing, etc.) should be expected of any engine — a conformance test suite ensures alternative engines preserve the semantics users rely on.

### Sequencing this alongside the §1–§9 work

The architectural changes (§1–§9) and the wrapping work are complementary, not competing:

1. **First, fix the Python engine** (§1–§9). The default engine is what every user gets out of the box. Most workloads don't justify the extra dependency of an FFI engine. The Python engine should be fast enough that the alternative engines are an optimization, not a necessity.
2. **In parallel, design the engine interface.** This is essentially the functional-core API surface and can be drafted alongside §1–§3. The interface design is the bottleneck, not the wrapping itself.
3. **Then, ship the wrappers.** `zarr.engines.zarrs` first (the existing `zarrs-python` work is a starting point); `zarr.engines.tensorstore` once the interface has stabilized.

The first two steps share infrastructure with the rest of the proposal. The third is incremental on top.

## Sequencing

The recommended order, by leverage:

| # | Change | Depends on | Pure Python? |
|---|---|---|---|
| 1 | Typed library-owned concurrency resources (`ComputeConcurrency`, `IoConcurrency`) + per-codec `recommended_concurrency` + shrinking-value propagation through the call stack | sync codec API ([codecs.md](./codecs.md)) | yes |
| 2 | `decode_into` standardized across all codecs | new codec API ([codecs.md](./codecs.md)) | yes |
| 3 | Store-layer range coalescing + batched API | new store API ([stores.md](./stores.md), [stores-range-coalescing.md](./stores-range-coalescing.md)) | yes |
| 4 | Cache substrate (one `AsyncCache`-shaped base) | nothing | yes |
| 5 | In-flight chunk-fetch deduplication via per-key futures | substrate (row 4) | yes |
| 6 | Metadata cache on by default with ETag revalidation | substrate (row 4), storage generations (row 9) | yes |
| 7 | Shard index cache | substrate (row 4), sharding codec | yes |
| 8 | Chunk caches (decoded, encoded) as opt-in `with_caching(...)` | substrate (row 4), `with_caching` API in [stores-caching.md](./stores-caching.md) | yes |
| 9 | Conditional reads via ETags / storage generations | store generation capability ([stores.md](./stores.md)) | yes |
| 10 | Internal pipeline caches after non-partial-decode codecs | new codec API ([codecs.md](./codecs.md)), substrate (row 4) | yes |
| 11 | Skip fill-value subchunks in sharding writes | nothing | yes |
| 12 | Adaptive whole-shard vs index-and-coalesce read strategy | row 3 helps | yes |
| 13 | Drop async from the codec hot path | codec API rewrite ([codecs.md](./codecs.md)) | yes |

(Note: rows in this table use plain numbers; cross-references like "row 4" disambiguate from the §1–§9 lesson numbers in [What we can learn from `zarrs` and TensorStore](#what-we-can-learn-from-zarrs-and-tensorstore).)

Rows 1–3 are the high-leverage architectural changes, with row 1 (typed concurrency resources) the single most impactful — it is the change that closes the largest source of variance in cloud Zarr workloads today. Everything else is incremental on top.

## Relationship to other proposals

- [`codecs.md`](./codecs.md) — provides the new codec API surface needed for §1 (`recommended_concurrency`), §5 (`decode_into`), §7 (`PartialDecodeCapability` flags), and §8 (sync-first).
- [`stores.md`](./stores.md), [`stores-range-coalescing.md`](./stores-range-coalescing.md) — provide §3 (batched store API, coalescing) and §4 (storage generations).
- [`functional-core.md`](./functional-core.md) — the substrate that makes all of the above plug together cleanly. Without the functional core, each of these changes is a local patch to an entangled internals; with it, they compose.
- [`lazy-indexing.md`](./lazy-indexing.md) — the query planner introduced there is what makes batched IO (§3) and `decode_into` pre-allocation (§5) exploitable from a user's chained `__getitem__` calls. Without lazy indexing, the user has no way to *express* a batched read; with it, batched IO is the default.

## What this enables for users

- **Cloud reads stop wasting bandwidth on duplicate fetches** (§2, §3, §4). For the dashboard / multi-consumer pattern this is a multiplicative win.
- **Sharded reads stop allocating per subchunk** (§5). For the typical 1024-subchunk shard this turns 1024 allocations into 1.
- **Sharded writes of sparse data stop encoding empty subchunks** (§6). Sparse arrays (masks, label volumes) write substantially faster and take less space.
- **Fancy indexing into compressed chunks stops re-decompressing** (§7). For interactive analysis this changes the user-perceived latency floor.
- **Thread count stays bounded** (§1). The shards-of-blosc thread explosion goes away; latency variance drops.
- **Repeated opens cost a 304** (§4). Xarray session startup and dashboard refreshes drop from seconds to milliseconds for unchanged data.

## Open questions

- **Concurrency budget defaults.** What is the right global concurrent_target — number of cores, fixed, configurable? How does it interact with Dask, which already manages its own thread pools?
- **Cache placement granularity.** Per-pipeline, per-store, per-process? §7's internal pipeline cache and the chunk cache from [§ Caching](#caching) need a coherent story.
- **Migration story for the async hot path** (§8). How do existing async-codec implementations migrate? The codec API rewrite ([codecs.md](./codecs.md)) addresses this with a backwards-compatibility layer.
- **Benchmark coverage.** `zarr-python` already runs a [CodSpeed](https://codspeed.io/) benchmark suite in CI (`tests/benchmarks/`, triggered weekly and on PRs labeled `benchmark`). The current coverage is read/write parametrized by compression × layout × `{memory, local}` store, plus indexing. The access patterns these proposals target — cloud-store latency (S3/GCS), multi-consumer concurrent reads (the in-flight dedup case), sharded sparse writes (the fill-value-skip case), repeated re-opens (the ETag-revalidation case), and fancy indexing into compressed shards (the internal-cache case) — are not yet covered. Extending the existing CodSpeed suite to cover these patterns is a prerequisite for measuring any of the changes here, not a separate effort.
