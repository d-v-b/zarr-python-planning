# Deferred items

Everything the v4 plan explicitly **does not decide** or **does not do now**, gathered from the README and all 18 proposals. Each item links to its source.

Tags:

- **[OOS]** — out of scope (will not be done as part of this work)
- **[OPEN]** — an undecided design question, to be settled during implementation
- **[LATER]** — will be done, but deferred to follow-on work

The uncertainty concentrates in the [stores](#stores) layer (the most-designed subsystem) and in [data types](#data-types) (Arrow). Two decision points are worth singling out: the **lazy default-flip** and the **mode-replacement constructor names**. (The **`Array`/`AsyncArray` consolidation** is now resolved — single `Array` class, selective `*_async`; see [functional core](#functional-core) below.)

## README & cross-cutting

Source: [`README.md` — What's out of scope](https://github.com/d-v-b/zarr-python-planning/blob/main/README.md#whats-out-of-scope) and the roadmap streams.

- **Persisted hierarchy links** — HDF5-style links surviving across processes need a new on-disk format (a ZEP first). **[OOS]** → [missing-apis.md](proposals/missing-apis.md)
- **`zarr-schema` declarative validation** — likely a separate package layered on `zarr-metadata`. **[LATER]** → [missing-apis.md](proposals/missing-apis.md)
- **Cross-process shared-memory caching** — substrate leaves room for it; doesn't ship now. **[LATER]** → [performance.md](proposals/performance.md#caching-specific-open-questions)
- **Consolidated-metadata full redesign** — only the design pass (spec/ZEP routing) is in scope. **[LATER]** → [consolidated-metadata.md](proposals/consolidated-metadata.md)
- **V2→V3 migration tooling** — the 2.x→3.x transition is considered resolved. **[OOS]**
- **Lazy default-flip** (eager→lazy `array[...]`) and the eager-path removal condition — hinges on whether Array-API conformance is a hard requirement. **[OPEN]** → [lazy-indexing.md](proposals/lazy-indexing.md), [`zarr.Array`](api/array.md)

## Functional core

Source: [functional-core.md — Open questions](proposals/functional-core.md#open-questions-for-follow-on-work).

- **Engine-selection ergonomics** — keyword argument vs URL-scheme routing vs global config. **[OPEN]** → [`zarr.engines`](api/engines.md)
- **Store-declaration format** — likely a typed dataclass with JSON schema. **[OPEN]** → [`zarr.store`](api/store.md)
- **Migration sequencing** — which pieces extract first, and deprecation-window lengths. **[OPEN]**
- **`Array`/`AsyncArray` consolidation** — *resolved*: a single `Array` class holds all the code and exposes async selectively via `*_async` methods on IO-bound operations only (no public `AsyncArray`); see [zarr-developers/zarr-python#4049](https://github.com/zarr-developers/zarr-python/pull/4049). Residual **[OPEN]**: per-operation sync-first vs async-first implementation (the async-overhead point raised by mkitti). → [`zarr.Array`](api/array.md)

## Hierarchy layer

Source: [hierarchy-layer.md — Open questions](proposals/hierarchy-layer.md#open-questions).

- Verb naming convention, verbs' physical location, `read_selection` granularity, async-verb naming/dispatch, transactional multi-verb semantics. **[OPEN]** → [`zarr.hierarchy`](api/hierarchy.md)
- Hierarchy-layer conformance suite. **[LATER]**

## Missing APIs

Source: [missing-apis.md — Open questions](proposals/missing-apis.md#open-questions).

- **Explicit constructor names** — `create` vs `create_array(..., overwrite=True)`, `open_for_read` vs `read`, etc. are placeholders. **[OPEN]** → [Creating arrays & groups](api/create.md), [Opening hierarchies](api/open.md)
- `zarr-schema` validation package. **[LATER]**
- Persisted links via the spec process. **[OOS]**

## Codecs

Source: [codecs.md](proposals/codecs.md).

- Numcodecs elimination (separate, later, delicate). **[LATER]**
- Codec-level wrapping of `zarrs`/TensorStore. **[LATER]** → [`zarr.codec`](api/codec.md), [`zarr.engines`](api/engines.md)

## Data types

Source: [data-types.md — follow-on gaps](proposals/data-types.md#other-data-type-gaps-follow-on-work) and [Open questions](proposals/data-types.md#open-questions).

- Ragged arrays, variable-length strings, dtype↔codec interactions, registry extensibility. **[LATER]** → [`zarr.dtype`](api/dtype.md)
- ML-dtypes package location; first-release dtype prioritization; `float8_e4m3fn` registration & metadata schema. **[OPEN]**
- Arrow: user-facing surface, integration depth, metadata schema, codec interactions, alt-engine support. **[OPEN]**; the investigation's outcome. **[LATER]**

## GPU / device-agnostic IO

Source: [gpu.md — Open questions](proposals/gpu.md#open-questions).

- DLPack vs CUDA Array Interface; CUDA-stream propagation across engines; `read_into`/`decode_into` as primary vs optional surfaces; achievable throughput vs native CuPy. **[OPEN]** → [`zarr.Array`](api/array.md)

## Lazy indexing

Source: [lazy-indexing.md — Open questions](proposals/lazy-indexing.md#open-questions).

- Selection representation; accessor & escape-hatch naming; materialization API; batching API shape; whether writes become lazy. **[OPEN]**
- Default-flip timing. **[LATER]** → [`zarr.Array`](api/array.md)

## Performance

Source: [performance.md — Caching-specific open questions](proposals/performance.md#caching-specific-open-questions) and [Open questions](proposals/performance.md#open-questions).

- Eviction policy (TTL/LRU/hybrid); Dask-worker × chunk-cache guidance; ETag-revalidation × range-coalescing; concurrency-budget defaults; cache-placement granularity; async-codec hot-path migration. **[OPEN]** → [`zarr.concurrency`](api/concurrency.md)
- Interactive-preset defaults; benchmark-coverage gaps; removal of the `sync()` bridge. **[LATER]**
- Cross-process caching; locking around concurrent user writes. **[OOS]**

## Observability

Source: [observability.md — Open questions](proposals/observability.md#open-questions).

- OTel as a hard dependency; span/attribute convention audit; per-array vs process-wide metrics; `chunk_exists` semantics under sharding; `read_block`/`write_block` security guidance. **[OPEN]** → [`zarr.observability`](api/observability.md)

## Consolidated metadata

Source: [consolidated-metadata.md](proposals/consolidated-metadata.md).

- Relationship to the functional core; codec/dtype/grid representation; write-time invalidation under concurrent writers; V2↔V3 format migration; `must_understand=false` fallback. **[OPEN]**
- Design sequencing and full-reimplementation timing. **[LATER]** → [`ConsolidatedMetadata`](api/metadata.md)

## Coordinated writes

Enabled by a transactional engine but **not** provided on plain v3. Source: [coordinated-writes.md](proposals/coordinated-writes.md).

- Atomicity (multi-chunk + metadata), reader isolation mid-write, partial-failure recovery, concurrent appenders, conflict resolution. **[OOS]**

## Stores

The largest cluster of deferred items.

### Overview — [stores.md](proposals/stores.md)
- ZipStore lifecycle contract, LocalStore crash-atomicity, module layout & back-compat window. **[OPEN]**
- Object-level caching opt-in, GPU re-coupling escape hatch. **[LATER]**

### API — [stores-api.md](proposals/stores-api.md)
- Streaming: `WritableBuffer` typing, `total_size=None` semantics **[OPEN]**; stream cancellation, mid-stream generation, `Caching[GetStreaming]` correctness, pipelined decode, `Buffer`-return shim, cursor-style local reads **[LATER]**.
- KvStack: `bytes` vs `str` `KeyRange` bounds, prefix-strip list ordering, cross-layer transactions **[OPEN]**; `Layered` fall-through, per-layer prefix transform, empty-stack semantics, non-string keys **[LATER]**.
- Main: capability **intersection** types **[OPEN]**; device-agnostic re-coupling escape hatch **[LATER]**.
- → [`zarr.store`](api/store.md)

### Wrappers — [stores-wrappers.md](proposals/stores-wrappers.md)
- `Retry` jitter strategy, `Tracing`×`Caching` hit attributes. **[OPEN]**
- `SyncToAsync` GIL contention, `AsyncToSync` reentrancy detection, a `Compose` helper. **[LATER]**

### Caching — [stores-caching.md](proposals/stores-caching.md)
- Object-level local slicing, `.stats()` metrics, disk-backed store, cross-process invalidation. **[LATER]**

### Range coalescing — [stores-range-coalescing.md](proposals/stores-range-coalescing.md)
- Cross-key coalescing, backpressure cap, per-call `max_gap`/`max_request` overrides, partial-success mode, Caching-order interaction. **[LATER]**

### Conformance — [stores-conformance.md](proposals/stores-conformance.md)
- Ship as a separate package, async test-runner choice, "cannot-satisfy" marker. **[OPEN]**
- Hypothesis property tests, performance budgets, obspec test reuse. **[LATER]**

### Transactional — [stores-transactional.md](proposals/stores-transactional.md)
- LocalStore crash-atomicity strictness, `Generation` pickling persistence, KvStack cross-layer atomicity. **[OPEN]**
- `Generation` standardization, free-threaded locking, per-call commit timeouts, an `atomic_update` helper. **[LATER]**
