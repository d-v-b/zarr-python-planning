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

### A lazy view as the result of indexing

`Array.__getitem__(selection)` returns a `LazyArray` (or whatever it ends up being called) — a Zarr array view bound to a source array and a composed selection. The view records *what to do* without doing it.

```python
z = zarr.open(...)             # Array
v = z[10:20, :, ::2]           # LazyArray, no IO
w = v[..., 0]                  # LazyArray, selection composed
arr = np.asarray(w)            # IO happens here, returns NumPy
```

Materialization is triggered by:
- Explicit conversion: `np.asarray(view)`, `view.compute()`, `view.to_numpy()`.
- Array API entry points where the standard requires concrete data.
- Iteration or scalar coercion (with the usual warnings about expensive operations).

The view carries the metadata of the result (shape, dtype, chunk layout) computed from the source plus the composed selection — these are pure functions of the inputs, which is exactly the kind of thing the [functional core](./functional-core.md) makes easy to compute.

### Composition of selections

Chained indexing composes selections rather than materializing intermediate arrays. `z[a][b]` is equivalent to `z[compose(a, b)]` with respect to the eventual IO. The selection representation needs to be richer than a single Python `slice` object to support boolean indexing, fancy indexing, and the array-api advanced indexing rules; the same representation is what the planner consumes.

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
- **Not full lazy compute.** Element-wise operations, reductions, and broadcasting are not part of this proposal. A `LazyArray` view is a *view onto stored data*, not a deferred computation graph. Returning a different type from arithmetic operations is out of scope.
- **Not an immediate flag-day break.** The current eager-numpy behavior remains available behind a flag (or as a deprecated `Array.get_eager(...)` method) through one or more 4.x releases. New code uses the lazy API; existing code keeps working with a deprecation warning.
- **Not "make zarr arrays act like numpy arrays."** This proposal pushes the other direction: zarr arrays act like zarr arrays, and conversion to numpy is explicit.

## Migration

The transition is staged:

1. **4.0**: introduce `LazyArray` and `Array.lazy_getitem(...)`. `__getitem__` retains its current eager behavior; a deprecation warning fires when `__getitem__` is used on an array constructed with `lazy=True`.
2. **4.x**: flip the default. `Array.__getitem__` returns `LazyArray` by default. `Array(eager_getitem=True)` is available as an escape hatch and emits a deprecation warning.
3. **5.0**: remove eager `__getitem__`. The escape hatch is removed; all indexing is lazy.

Each step is a release boundary, not a flag day. The user-facing surface for the lazy API is published in 4.0 and stable from that point on; only the *default* changes between 4.0 and 4.x.

The interaction with downstream libraries is the load-bearing question for sequencing. Xarray, Dask, and napari all consume `zarr-python`'s eager `__getitem__`; they will need a release that supports both eager and lazy paths before we can flip the default. The transition mirrors the 2.x→3.x migration: announce, give downstreams time, then flip.

## Relationship to existing proposals

- [`functional-core.md`](./functional-core.md) — the planner and the selection algebra live in the functional core. The view-versus-engine split is the same shape as the rest of the functional-core design. This proposal is one of the strongest motivators for the functional-core work.
- [`codecs.md`](./codecs.md) — the planner is what makes `decode_into` and other allocation-saving codec capabilities exploitable in practice. Without a plan, the orchestrator doesn't know what to pre-allocate.
- [`stores.md`](./stores.md) — range coalescing, sketched as a store-level capability, is more powerful when an array-level planner can hand the store a batch of reads instead of dribbling them in one at a time.
- [`stores-transactional.md`](./stores-transactional.md) — the same lazy-then-execute pattern extends to writes once this proposal lands.
- [`missing-apis.md`](./missing-apis.md) — the lazy-slicing and array-api bullets move out of `missing-apis.md` and become this proposal. The async/sync bridge, array views (a special case of lazy indexing), and rechunking bullets stay there.

## Open questions

- **Selection representation.** Python's `slice` is not expressive enough. Options: a dataclass-based `IndexExpr` algebra (TensorStore-style), a NumPy-fancy-index-style array, or something custom. The choice has downstream implications for the planner.
- **Naming.** `LazyArray`, `ArrayView`, `Slice`, `IndexExpr` — there's a naming exercise to do that affects every example in the documentation.
- **Materialization API.** `np.asarray(view)` is automatic; `view.compute()` is explicit. Do we want both? Just one? Does it return NumPy specifically, or whatever the array-api `__array_namespace__` resolution gives us?
- **Batching boundary.** Is `with zarr.batch():` the right shape, or do we want something more like a session object that batches its own calls? The TensorStore `Batch` API is one reference point.
- ~~Interaction with caching.~~ **Resolved** by [performance.md § Caching](./performance.md#caching): the query planner sits *above* the cache substrate. Building an IO plan consults the cache and the in-flight-dedup table; chunks already in cache produce no IO in the resulting plan, chunks with an in-flight read produce a join-the-future entry rather than a duplicate fetch. The cache layer is responsible for storage and eviction; the planner is responsible for what to fetch.
- **Write semantics during deprecation window.** `z[...] = data` is a separate code path from `__getitem__` and does not become lazy in this proposal. Whether it *should* — and whether write laziness needs its own deprecation window — is open.
