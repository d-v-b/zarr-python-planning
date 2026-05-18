# Lazy Indexing

> Theme proposal. For the high-level pitch and audience framing, see the [parent README](../README.md).

## Summary

`zarr-python`'s `Array.__getitem__` performs I/O eagerly and returns a NumPy array. This single design choice forces every performance-sensitive user into Dask, blocks Zarr from participating in the Python Array API ecosystem, and prevents the library from doing the most basic IO optimizations (slice fusion, deduplication, range coalescing) on its own.

This proposal is to make indexing **lazy by default**: `z[...]` returns a Zarr array view, and materialization is explicit. With laziness in place, we can align with the [Python Array API standard](https://data-apis.org/array-api/latest/) and introduce a small query planner that fuses adjacent operations into a single IO plan before any chunks are fetched.

The user-facing change is real but contained: the public API change is well-scoped, the migration path is staged, and the performance ceiling for IO-bound workloads goes up substantially without users having to adopt Dask.

## The problem

### Slicing returns the wrong type

`Array.__getitem__(slice)` returns `np.ndarray`. This is unique among the array libraries that Zarr aspires to interoperate with — NumPy, Dask, JAX, CuPy, TensorStore, Zarrs — all of which return an instance of the same array type they were sliced from. Returning a different type breaks the simplest mental model a user has of a collection: *"slicing a thing of type T gives me a thing of type T."*

The current behavior is consistent with `h5py`, which itself inherited it from a NumPy-centric era. That era is over: every modern array library returns a view-like object and defers materialization.

The discussion thread is at [`zarr-python#1603`](https://github.com/zarr-developers/zarr-python/discussions/1603) (23 comments).

### Eager IO blocks the optimizations the library should be doing

Because every `__getitem__` is an immediate IO call, `zarr-python` has no opportunity to optimize across calls. Concretely:

- **Duplicate slice elision.** A user who writes `z[100:200]` twice produces two identical IO requests. A lazy layer could deduplicate them trivially — and would beat caching at it, because there is no allocation, no decode, and no cache lookup on the second request.
- **Adjacent slice fusion.** A user who writes `z[0:50]` and then `z[50:100]` triggers two reads of the chunk that contains the boundary. A lazy layer that sees both selections before any IO happens can issue one read for the union and split the result.
- **Sub-chunk request batching.** Two slices into different halves of the same chunk are two full-chunk reads today; a lazy layer can collapse them into one chunk read served twice.
- **Cross-array coalescing.** Multiple slices into multiple arrays in the same store can produce a single coalesced range request (this is what `obstore` and TensorStore do at the store layer; without lazy indexing at the array layer, the Zarr-Python user never gets the benefit).

The user-visible consequence today is that the only way to get any of these optimizations is to adopt Dask. Dask is excellent for distributed computation but has [well-documented overhead for arrays with many small chunks](https://docs.dask.org/en/stable/array-best-practices.html), and forcing every performance-sensitive Zarr user through Dask means we are shipping a library whose default indexing path is the wrong one for the workloads users actually have.

### Indexing parameters have nowhere to go

`__getitem__` accepts no keyword arguments. This has forced a stream of array-construction parameters that really belong to *individual IO calls* — `synchronizer`, `write_empty_chunks`, `meta_array`, and others — to live as array-instance attributes. The user cannot change them per-call. They cannot be changed at all without constructing a new array.

A lazy view object gives these parameters a natural home: the materialization call (`.compute()`, `np.asarray(view)`, or whatever the chosen API is) accepts them as keyword arguments, scoped to the IO that actually uses them.

### Array API misalignment

The [Python Array API standard](https://data-apis.org/array-api/latest/) defines a common surface that NumPy, CuPy, JAX, PyTorch, and others have adopted. Libraries written against the standard — `scipy`, `scikit-image`, parts of `xarray` — can use any array-api-conformant array transparently.

`zarr-python` does not conform, primarily because `__getitem__` returns NumPy instead of `Self`. Until that changes, a Zarr array cannot be passed directly to array-api code; users have to materialize first, which throws away every advantage a chunked-array library is supposed to offer.

The question has been raised explicitly in [`zarr-python#2197`](https://github.com/zarr-developers/zarr-python/discussions/2197).

## The direction

### Lazy is an accessor on `Array`, not a new type

The end state is that `Array.__getitem__` *itself* returns a lazy view. We get there without splitting the codebase into two array types. The migration runs entirely on the existing `Array` class:

- **In 4.0**, `Array` grows an opt-in accessor — `array.lazy[...]` (working name; the actual name is settled in the migration PR). The accessor's `__getitem__` returns an array view bound to the source `Array` plus a composed selection. The bare `array[...]` keeps its existing eager-NumPy behavior; users opt in by going through the accessor.
- **In a later 4.x release**, `Array.__getitem__` itself flips to return the same view object the accessor returns. The accessor stays as an unambiguous explicit form but becomes a no-op (`array.lazy[...]` and `array[...]` behave identically).
- **In a future major release** (after the deprecation window completes), the eager path is gone and so is the need for the accessor; `Array.__getitem__` is the only path.

There is never a `LazyArray` class. There is never a period where downstream code has to handle two array types via `isinstance` checks. The change rides on a single type whose `__getitem__` semantics evolve across releases — the same pattern `pathlib.Path` used to absorb `os.path` behaviors without introducing a parallel type.

The view that `array.lazy[...]` returns is *also* an `Array` (or a compatible subclass / view-flavored object that satisfies the same surface). It records *what to do* without doing it. Composed selections, materialization triggers, and Array API conformance all attach to that one type.

```python
z = zarr.open(...)             # Array

# 4.0: opt-in lazy via accessor; bare __getitem__ is eager NumPy.
arr = z[10:20, :, ::2]         # eager: ndarray, IO happens here.
v   = z.lazy[10:20, :, ::2]    # lazy: an Array view, no IO yet.
w   = v[..., 0]                # composed; still no IO.
arr = np.asarray(w)            # materialization: NumPy out.

# Later 4.x: __getitem__ itself flips. The two forms become equivalent.
v   = z[10:20, :, ::2]         # lazy by default.
v   = z.lazy[10:20, :, ::2]    # same.
```

Materialization is triggered by:
- Explicit conversion: `np.asarray(view)`, `view.compute()`, `view.to_numpy()`.
- Array API entry points where the standard requires concrete data.
- Iteration or scalar coercion (with the usual warnings about expensive operations).

The view carries the metadata of the result (shape, dtype, chunk layout) computed from the source plus the composed selection — these are pure functions of the inputs, computed from the `IndexTransform` algebra (see below) and the source array's metadata. This is exactly the kind of thing the [functional core](./functional-core.md) makes easy to compute.

### Composition of selections: the `IndexTransform` algebra

Chained indexing composes selections rather than materializing intermediate arrays. `z[a][b]` is equivalent to `z[compose(a, b)]` with respect to the eventual IO. The selection representation needs to be richer than a single Python `slice` object to support boolean indexing, fancy indexing, and the Array API's advanced indexing rules.

The data structure for this is `IndexTransform`: an internal type representing a composable, lazy coordinate mapping from output indices to source-array indices. It is *internal* — users don't see it directly; they see the lazy view object whose composition is implemented in terms of it. The foundational `IndexTransform` library is in flight at [zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906) and lands ahead of the rest of the lazy-indexing work.

`IndexTransform` is what the planner (below) consumes when turning chained selections into IO plans. Because composition is a pure function on `IndexTransform` values, the planner can reason about an arbitrarily deep chain of `array.lazy[a][b][c][...]` calls without materializing any intermediates.

### Array API conformance

With `__getitem__: Array -> Array` in place, the bulk of the work for array-api conformance is unblocked. We commit to conforming to the standard's read-only surface — `__getitem__`, `__array_namespace__`, shape/dtype/device properties, and the unary/binary operators where they make sense for a Zarr array. Write operations stay outside the standard.

The result is that downstream libraries that already accept any array-api-conformant array — substantial portions of SciPy, scikit-image, and others — start working with Zarr arrays for free.

### A query planner

The view recording opens the door to a planner that sits between the user's chained operations and the actual IO. The planner sees a batch of pending IO operations (either because the user has constructed multiple views and is materializing them together, or because of explicit batching primitives) and produces an IO plan. The plan can:

- Deduplicate identical reads.
- Fuse adjacent or overlapping selections into single reads.
- Coalesce reads of nearby chunks into range requests at the store layer.
- Reorder operations to maximize cache locality.
- Pre-allocate output buffers and dispatch decodes with `decode_into` where the codec supports it.

The planner is a pure function from a list of pending operations to an IO plan. It lives in the [functional core](./functional-core.md) — no I/O, no state, no async. The execution layer (engine) takes the plan and runs it. This is the same shape as TensorStore's `Spec → ResolvedSpec → IO` pipeline and a natural fit for the engine architecture proposed in the functional-core refactor.

### Selection pushdown through the codec pipeline

The planner's most consequential output is not "which chunks to fetch" — it's the per-chunk **sub-selection** that travels down through the codec pipeline. When the user reads a scalar `z[100, 100]` from a chunked, sharded, blosc-compressed array, the naive implementation reads the whole chunk, decompresses it, allocates the full chunk's worth of memory, and slices the scalar out. The right implementation reads only the bytes containing that scalar, decompresses only those bytes, and allocates only the scalar.

Both reference implementations do this — and they agree on every architectural choice:

- **The selection travels as a structured object through the entire pipeline.** TensorStore uses `IndexTransform<>` as the universal currency; each codec composes its own coordinate change into it and forwards a new `IndexTransform` to the next codec. zarrs uses an `&dyn Indexer` (typically `ArraySubset`) that mutates per level. In both, the carrier type is uniform across the pipeline; the *meaning* changes as the selection descends through coordinate-transforming codecs (transpose permutes axes, sharding maps shard coords to inner-chunk coords).
- **Codecs advertise whether they can partial-decode.** zarrs uses an explicit `PartialDecoderCapability { partial_read, partial_decode }` flag per codec; TensorStore uses method-override (codecs that can partial-decode override the polymorphic `Read(transform, ...)` method; codecs that can't inherit the default whole-chunk-decode-then-slice fallback). The mechanism differs; the outcome is the same: each codec self-declares whether the planner can ask it to do less.
- **Sharding is the headline win.** Both libraries' sharding codecs are hand-written to push the selection all the way down: read the shard index (~KB), issue byte-range GETs only for the intersecting inner chunks (~MB each), decompress only those. The wire outcome for `z[100, 100]` on a typical sharded array (1024³ array, 256³ chunks, 64³ subchunks, blosc) is **one shard-index read plus one inner-subchunk fetch**, not a whole-chunk fetch.
- **Where pushdown can't continue, the fallback is whole-chunk-decode-then-slice plus caching.** When the chain contains a codec that can't partial-decode (blosc, gzip, anything stateful), the pipeline caches the full decode of *that codec's output* at the boundary so subsequent sub-selections of the same chunk reuse it. zarrs makes this explicit via `ArrayPartialDecoderCache` / `BytesPartialDecoderCache` adapters inserted into the chain at construction time; TensorStore uses its LRU `ChunkCache` for the same purpose. This is [performance.md § 7](./performance.md#7-internal-pipeline-caches-between-non-partial-decode-codecs).

The decision of how far to push is local and structural: no cost model, no heuristic. Each codec is asked "can you do partial decode here?" — if yes, the selection descends further; if no, this is where the fallback happens. The pipeline knows the answer at construction time because the capability is part of the codec's protocol surface.

For `zarr-python`, **the convergence on architectural choices means we can adopt the pattern with high confidence; the difference on mechanism is a design choice we get to make**. The recommendation:

1. **Carry the selection as `IndexTransform`** all the way through the pipeline. The PR at [zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906) ships exactly the structure we need; this is the substrate.
2. **Use zarrs's explicit capability + factory model** rather than TensorStore's polymorphic-method-with-default-override model. Reasons: (a) it composes more cleanly with [codecs.md](./codecs.md)'s capability-advertising design (`PartialDecodeCapability` is already specified there); (b) it makes the cache-insertion logic from [performance.md § 7](./performance.md#7-internal-pipeline-caches-between-non-partial-decode-codecs) a structural pre-computation rather than a runtime fallback; (c) Python's method-override mechanics are less forgiving than Rust traits or C++ virtuals, so explicit factories are the right shape.
3. **The codec API grows a per-chunk partial-decode entry point** alongside its whole-chunk `decode` / `decode_into` methods. The signature carries the sub-selection in `IndexTransform` form; codecs that don't advertise `partial_decode=True` get the whole-chunk-decode-then-slice fallback transparently via the cache inserted by the pipeline ([performance.md § 7](./performance.md#7-internal-pipeline-caches-between-non-partial-decode-codecs)).

The end-to-end story: planner produces an IO plan whose per-chunk entries carry an `IndexTransform`; the codec pipeline accepts that transform and pushes it down as far as the codec capabilities allow; pushdown halts at the first non-partial-decode codec, where the cached whole-chunk decode services the sub-selection. A scalar read produces a scalar's worth of allocation; a 100-element slice produces 100 elements' worth; only sharded blosc-compressed pipelines hit a 1-MiB-sub-chunk decompression floor, which is the unavoidable cost of the compression and is what the cache amortizes for subsequent reads.

### Explicit batching

Users get two ways to opt into batched IO:

- Implicit: when an expression evaluates multiple views (e.g., a list comprehension of slices) inside a `with zarr.batch():` block, the views' selections are collected and submitted to the planner as a batch.
- Explicit: a top-level helper like `zarr.materialize([v1, v2, v3])` that returns the materialized arrays in one shot.

The implicit batching context is the ergonomic win; the explicit form is the one we can guarantee is always optimal.

## What this enables

**A first-class IO optimization story without Dask.** The most-requested optimizations for IO-bound Zarr workloads — deduplication, fusion, range coalescing — become things `zarr-python` does on its own, for users who never wrote a line of Dask.

**Array API ecosystem participation.** Zarr arrays start working as inputs to any array-api-conformant function. The library re-enters a part of the scientific Python ecosystem it has been locked out of.

**A natural home for per-IO parameters.** `synchronizer`, `write_empty_chunks`, `meta_array`, and future additions live on the materialization call instead of polluting array construction. The `Array` and view classes get simpler.

**An obvious place to plug in engines.** A lazy plan is exactly the input format an alternative execution engine (Zarrs, TensorStore) wants. Per the [functional-core proposal](./functional-core.md), an engine is a small module that consumes plans and produces arrays. Lazy indexing is the producer side of that interface.

**A path to laziness for write operations later.** This proposal scopes itself to reads, but the same machinery — selection composition, plan construction, batched execution — applies to writes. `z[...] = data` can stage a write into a transaction (see [stores-transactional.md](./stores-transactional.md)) instead of executing immediately.

## What this is not

- **Not a Dask replacement.** Dask handles distribution, scheduling, and computation graphs. This proposal handles IO planning for a single Zarr array surface. Users who want distributed computation continue to use Dask; the difference is that Dask is no longer the *only* way to get basic IO batching.
- **Not full lazy compute.** Element-wise operations, reductions, and broadcasting are not part of this proposal. The lazy view is a *view onto stored data*, not a deferred computation graph. Arithmetic operations materialize the view as today.
- **Not a new array type.** The end state is `Array` with lazy semantics, not `LazyArray` next to `Array`. The accessor in 4.0 is the opt-in mechanism; the codebase carries one array type throughout.
- **Not an immediate flag-day break.** The current eager-numpy behavior remains available behind a flag (or as a deprecated `Array.get_eager(...)` method) through one or more 4.x releases. New code uses the lazy API; existing code keeps working with a deprecation warning.
- **Not "make zarr arrays act like numpy arrays."** This proposal pushes the other direction: zarr arrays act like zarr arrays, and conversion to numpy is explicit.

## Migration

The transition is staged. No new array *type* is ever introduced; the migration is entirely about the semantics of `Array.__getitem__`.

1. **4.0**: ship the foundational `IndexTransform` algebra ([zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906)) and the `array.lazy[...]` accessor. The accessor's `__getitem__` returns a lazy view bound to the source `Array`. The bare `array[...]` keeps its existing eager-NumPy behavior. Users opt in by going through the accessor; no downstream code breaks. A deprecation warning starts firing on bare `array[...]` calls in cases where the lazy form would be preferable, pointing users at the accessor.
2. **4.x**: flip the default of `Array.__getitem__` to lazy. The `array.lazy[...]` accessor stays as an unambiguous explicit form but becomes a no-op (`array.lazy[...]` and `array[...]` behave identically). An escape hatch (`array.eager[...]` or `array[..., eager=True]` or similar — name to be settled) is available for the remaining holdouts and itself emits a deprecation warning.
3. **A future major release** (after the deprecation window): remove the eager escape hatch and the (now-redundant) `array.lazy[...]` accessor. `Array.__getitem__` is the only path; it is lazy.

Each step is a release boundary, not a flag day. The user-facing surface for the lazy API is published in 4.0 and stable from that point on; only the *default* changes between 4.0 and 4.x. Crucially, **the codebase never carries two array types**: an `Array` is always an `Array`; what changes is what its `__getitem__` returns by default.

The interaction with downstream libraries is the load-bearing question for sequencing. Xarray, Dask, and napari all consume `zarr-python`'s eager `__getitem__`; they will need a release that supports both eager and lazy paths before we can flip the default. The transition mirrors the 2.x→3.x migration: announce, give downstreams time, then flip. Because there is no new array type to handle, the downstream change is "accept that `array[...]` now returns a view that materializes on `np.asarray`," not "handle a new `LazyArray` class."

## Relationship to existing proposals

- [`functional-core.md`](./functional-core.md) — the planner and the selection algebra live in the functional core. The view-versus-engine split is the same shape as the rest of the functional-core design. This proposal is one of the strongest motivators for the functional-core work.
- [`codecs.md`](./codecs.md) — the planner is what makes `decode_into` and other allocation-saving codec capabilities exploitable in practice. Without a plan, the orchestrator doesn't know what to pre-allocate.
- [`stores.md`](./stores.md) — range coalescing, sketched as a store-level capability, is more powerful when an array-level planner can hand the store a batch of reads instead of dribbling them in one at a time.
- [`stores-transactional.md`](./stores-transactional.md) — the same lazy-then-execute pattern extends to writes once this proposal lands.
- [`missing-apis.md`](./missing-apis.md) — the lazy-slicing and array-api bullets move out of `missing-apis.md` and become this proposal. The async/sync bridge, array views (a special case of lazy indexing), and rechunking bullets stay there.

## Open questions

- **Selection representation.** Python's `slice` is not expressive enough. Options: a dataclass-based `IndexExpr` algebra (TensorStore-style), a NumPy-fancy-index-style array, or something custom. The choice has downstream implications for the planner.
- **Naming.** The accessor name (`array.lazy` is the working name; `array.view` and `array.slice` were considered) and the escape-hatch name for stage 2 (`array.eager`, `array[..., eager=True]`, or similar). The internal `IndexTransform` name is settled by the [in-flight PR](https://github.com/zarr-developers/zarr-python/pull/3906); it's an internal data structure and not user-facing, so its name is not load-bearing for documentation.
- **Materialization API.** `np.asarray(view)` is automatic; `view.compute()` is explicit. Do we want both? Just one? Does it return NumPy specifically, or whatever the array-api `__array_namespace__` resolution gives us?
- **Batching boundary.** Is `with zarr.batch():` the right shape, or do we want something more like a session object that batches its own calls? The TensorStore `Batch` API is one reference point.
- ~~Interaction with caching.~~ **Resolved** by [performance.md § Caching](./performance.md#caching): the query planner sits *above* the cache substrate. Building an IO plan consults the cache and the in-flight-dedup table; chunks already in cache produce no IO in the resulting plan, chunks with an in-flight read produce a join-the-future entry rather than a duplicate fetch. The cache layer is responsible for storage and eviction; the planner is responsible for what to fetch.
- **Write semantics during deprecation window.** `z[...] = data` is a separate code path from `__getitem__` and does not become lazy in this proposal. Whether it *should* — and whether write laziness needs its own deprecation window — is open.
