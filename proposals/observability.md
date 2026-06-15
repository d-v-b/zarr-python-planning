# Observability

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

## Summary

Observability is the property that lets a user, an ops team, or a downstream library answer two questions at runtime: **"what is my Zarr-Python deployment doing?"** and **"what is actually in my Zarr data?"** Both questions are answered poorly today. Performance issues require sampling profilers and source-reading to diagnose; cache hit rates and concurrency saturation are invisible; "which chunks of this array are materialized?" requires reaching into private APIs. The v4 work fixes both, on the same substrate as the rest of the proposal set.

This proposal has two pillars:

1. **Performance metrics and tracing** — instrumentation for IO, codec, cache, and concurrency operations that users can read at runtime or stream to standard observability backends (OpenTelemetry being the obvious one).
2. **Stored-state introspection** — public APIs for asking the library about the structure and content of stored Zarr data without actually reading the chunks: chunk-level metadata, materialization predicates, byte-range information, encoded-bytes access, storage footprint.

Both pillars are cross-cutting in the same way [performance.md](./performance.md) is — observability touches every layer (stores, codecs, caches, engines, arrays), and the right answer is uniform instrumentation across all of them rather than per-component logging that drifts.

## Pillar 1: Performance metrics and tracing

### The problem

Today, the only way to find out *why* a Zarr workload is slow is to attach a sampling profiler, read the source to figure out which call paths are which, and guess. Concretely:

- **Cache effectiveness is invisible.** Hit rate, eviction count, byte budget utilization, in-flight dedup hits — none of these are exposed. A user who turns on chunk caching with `array.with_caching(chunks=True)` has no way to tell whether it's helping.
- **IO behavior is opaque.** Number of store calls per user request, range-coalescing effectiveness, ETag revalidation hit rate, retry count — all hidden. A user who suspects their object-storage workload is over-fetching has no signal.
- **Concurrency utilization is hidden.** Whether the `ComputeConcurrency` pool is saturated, whether `IoConcurrency` is bottlenecked, whether per-codec parallelism budgets are being fully used — invisible. This is particularly bad given that the [§1 concurrency model](./performance.md#1-concurrency-is-typed-library-owned-and-shared-across-nested-calls) makes pool ownership a load-bearing design choice; users need to *see* whether their tuning is right.
- **Codec hot paths are not measured.** Whether decode dominates or IO dominates a workload, whether the partial-decoder cache is paying off, whether sharded reads are using the adaptive whole-shard heuristic — none queryable.
- **Downstream-library integration is hand-rolled.** Dask, Xarray, and similar projects each instrument their *own* call to `zarr-python`, but they cannot see what happens *inside* a Zarr operation. Open telemetry trace spans stop at the Zarr boundary.

The motivating issue is [zarr#2958](https://github.com/zarr-developers/zarr-python/issues/2958) (OpenTelemetry integration); the broader case is [zarr#1774](https://github.com/zarr-developers/zarr-python/issues/1774) (logging for store/array/group operations).

### The direction

Two surfaces, both ride on the same underlying instrumentation:

#### Programmatic metrics surface

A `Metrics` object lives next to the typed concurrency resources from [performance.md § 1](./performance.md#1-concurrency-is-typed-library-owned-and-shared-across-nested-calls). It is library-owned, threaded through `Array` and `Group` construction, and accumulates per-instance counters and timing distributions. Users read it directly:

```python
m = array.metrics
m.store_get_count                # number of store.get calls
m.store_get_bytes                # total bytes fetched
m.cache_hits, m.cache_misses     # per-tier (metadata, chunks, ...)
m.cache_dedup_hits               # in-flight dedup wins
m.coalesce_groups                # range-coalescing groups formed
m.coalesce_wasted_bytes          # bytes inside coalesced ranges that nobody asked for
m.decode_seconds_total           # cumulative decode wall time
m.compute_concurrency_inflight   # current ComputeConcurrency pool saturation
m.compute_concurrency_waited     # cumulative time waited at admission queue
```

Metrics are per-`Array` by default (so independent arrays don't pollute each other's stats), with an opt-in process-wide aggregator for users who want one number per deployment. Reset is explicit. The shape is small and stable — a handful of counters and a handful of timing histograms — not a free-form key-value bag.

#### Tracing via OpenTelemetry

The library auto-instruments its hot paths with OpenTelemetry spans when an OTel tracer is configured ([zarr#2958](https://github.com/zarr-developers/zarr-python/issues/2958)). Span names match a stable convention (`zarr.store.get`, `zarr.codec.decode`, `zarr.array.read_selection`, `zarr.engine.read_chunk`, `zarr.cache.hit`, etc.). Attributes carry the data points a debugging user actually wants: keys, byte counts, chunk coordinates, cache-tier hits, retry counts.

The `Tracing[S]` store wrapper from [stores-wrappers.md § Tracing](./stores-wrappers.md#tracings) is the model — duck-typed against OpenTelemetry's `Tracer` interface, zero-cost when no tracer is configured. The new work is *extending* the same pattern beyond stores to cover the codec pipeline, the cache substrate, and the engine boundary. Users get one configuration knob (the tracer); the library handles plumbing.

For users not on OpenTelemetry, the spans are also published to a lightweight in-process event bus that the `Metrics` object reads — so the same instrumentation feeds both surfaces without duplicating call-site code.

#### Tracing across the engine boundary

This is the load-bearing observability question for the engine architecture in [performance.md § Wrapping zarrs and TensorStore as alternative engines](./performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines). When a user switches from the Python engine to `zarrs`, the spans `zarr.array.read_selection` should still exist (managed by zarr-python) and contain child spans for the engine's work. The engine module is responsible for publishing spans for its part of the work; the zarr-python layer threads the tracer context through to the engine call. For native engines (zarrs, TensorStore), the spans they emit appear as child spans of the zarr-python span.

This means a user diagnosing a slow read sees one trace covering the whole stack — planner work (Python), engine dispatch (Python), engine compute (native), store IO (native or Python), cache hits/misses (Python). The trace is the answer to "where is the time actually going?" and works the same regardless of engine.

### What ships

- A `Metrics` dataclass with the counters and timers above, attached per-`Array`.
- OpenTelemetry auto-instrumentation across stores, codecs, caches, concurrency admission, engine boundary. Zero-cost when no tracer is set.
- A `zarr.metrics_process_wide` aggregator for users who want one set of numbers per process.
- Documentation on integration with common backends: OpenTelemetry collectors, Prometheus via the OpenTelemetry exporter, Datadog/Honeycomb/Tempo via their OTel pipelines.
- The existing `LatencyStore` from [missing-apis.md § Display and debugging](./missing-apis.md) is promoted to a public store wrapper as a useful adjunct for benchmarking.

## Pillar 2: Stored-state introspection

### The problem

Users routinely need to ask questions about Zarr data *without reading the chunks*: "is this chunk materialized or fill-value-implied?", "where in the store does chunk (i, j) live and how big is it?", "what's the total on-disk footprint of this array?", "give me the encoded bytes of this chunk so I can do something with them outside Zarr-Python." Today most of these require either reaching into private APIs or reimplementing the chunk-addressing logic per project.

The most consistent demand comes from the virtual-Zarr ecosystem: [VirtualiZarr](https://github.com/zarr-developers/VirtualiZarr), [Kerchunk](https://github.com/fsspec/kerchunk), and similar projects that build *references* to Zarr data without copying it. They need a public introspection surface to do their work; today they reach into internals.

But the use cases are broader than virtual-Zarr — every Zarr user who has tried to answer "why is this 1 TB array taking 2 TB on disk?" or "which chunks of this 4D array have been written?" knows the gap.

### The direction

A small, public surface on `Array` (and `Group` where appropriate) that exposes the answers without reading any chunk data:

```python
# Iteration over the chunk grid — coordinates only, no IO.
for coords in array.chunks:                       # zarr#2454
    ...

# Predicate: is this chunk materialized, or fill-value-implied?
array.chunk_exists(coords)                        # zarr#2507

# Where does this chunk live in the store, and how big?
array.chunk_byte_range(coords)
# -> (store_key, start, length)                   # zarr#1113

# Encoded-bytes access — skip the codec pipeline.
array.read_block(coords)                          # zarr#543
array.write_block(coords, encoded_bytes)

# Storage footprint of the whole array.
array.storage_size()                              # total bytes across all materialized chunks

# Public metadata classes — for code that constructs / parses metadata
# without going through the Array facade.
from zarr.metadata import ArrayV3Metadata          # zarr#2986
metadata = ArrayV3Metadata(...)

# Disambiguated counts under sharding.
array.nchunks       # logical chunks the user sees
array.nshards       # shard-level objects in the store (None if not sharded)
array.n_inner_chunks # per-shard subchunks (None if not sharded)
#                                                   # zarr#3296
```

The surface is small but it unblocks substantial downstream work:

- **VirtualiZarr / Kerchunk**: a public `chunk_byte_range` plus `read_block` is the entire integration surface they need. Today they reimplement the chunk-coordinate-to-store-key logic per project, which means each new Zarr feature (sharding, new key encodings) requires per-project updates. With a public API, they just call it.
- **Storage cost analysis**: `storage_size()` plus iteration over `chunks` gives users a one-liner to ask "what's my array actually costing me on S3?"
- **Sparse-data workflows**: `chunk_exists` + iterating over `chunks` is "which regions of my array have been written?", which today requires a manual probe.
- **Repair and migration tools**: read-block / write-block enables chunk-level copy/move/repack without round-tripping through decode/encode.

### Where the work lives

Most of the introspection surface is **pure-data computation** — chunk-coordinate-to-key math, fill-value detection, shape arithmetic — which fits naturally into the [`zarr-metadata` package](./functional-core.md#the-packages) as functions on metadata documents. The functional-core refactor makes this nearly free: once chunk addressing is a pure function in `zarr-metadata`, exposing it as `array.chunk_byte_range(coords)` is a one-line method on the `Array` facade.

The block-level read/write surface (`read_block`, `write_block`) is a thin pass-through on top of the [store layer](./stores.md): one store `get` / `put` with the chunk key, skipping the codec pipeline. It belongs on `Array` for ergonomics but is implemented in terms of `store.get(array.chunk_byte_range(coords).key)`.

The public `ArrayV3Metadata` is `zarr-metadata`'s top-level export. VirtualiZarr already depends on it informally; the work is making the dependency formal and stable.

## What this enables

- **Users debug performance themselves.** A slow workload becomes a tractable problem with metrics + traces. The current "attach a profiler and read source" workflow becomes "look at the cache hit rate."
- **Ops teams get a deployment-level view.** OpenTelemetry integration means Zarr-Python operations appear in the same dashboards as the rest of the user's stack. No bespoke logging configuration.
- **Downstream libraries see *inside* Zarr operations.** Dask, Xarray, napari can trace user requests through their own code *and* through Zarr in one continuous trace. The Zarr boundary stops being an opaque black box in the trace viewer.
- **The virtual-Zarr ecosystem is unblocked.** VirtualiZarr, Kerchunk, and similar projects get a stable public API for chunk introspection instead of internal-API archaeology.
- **Cost and capacity questions become one-liners.** `array.storage_size()`, `sum(1 for c in array.chunks if array.chunk_exists(c))`, etc. — the questions every user has eventually had to answer with custom scripts now have a public method.
- **The engine boundary stays transparent.** Switching engines doesn't break the trace view; users see one consistent picture regardless of which engine is doing the work.

## What this is not

- **Not a metrics framework.** The `Metrics` object exposes a fixed, small set of counters and timers — not a general-purpose user-extensible metrics system. Users who want richer metrics use OpenTelemetry directly.
- **Not a logging framework.** Structured logging at the per-call level is a debugging tool, not a routine output. The library does not log unless the user opts in via the tracer or a debug flag.
- **Not a query language for stored data.** `chunk_exists` and `chunk_byte_range` answer specific questions; they are not the beginning of a SQL-style query surface over Zarr stores.
- **Not a replacement for the consolidated metadata story.** [Consolidated metadata](./consolidated-metadata.md) is about fast hierarchy open; observability is about runtime introspection. They are orthogonal.

## Relationship to other proposals

- [`performance.md`](./performance.md) — the metrics surface counts things the performance work *delivers* (cache hits, concurrency utilization, range-coalesce groups). Without the performance work, there's not much to count; without observability, users can't see whether the performance work is helping.
- [`stores-wrappers.md`](./stores-wrappers.md) — `Tracing[S]` is the existing wrapper-based model for store-level tracing. The work here extends that model to other layers; `Tracing[S]` is preserved unchanged.
- [`functional-core.md`](./functional-core.md) — chunk-addressing math becomes pure functions in `zarr-metadata`. The introspection surface on `Array` is a thin layer over those functions.
- [`missing-apis.md`](./missing-apis.md) — chunk introspection used to live there; the API list is now owned by this proposal, with a pointer remaining in missing-apis for discoverability. `LatencyStore` promotion (also in missing-apis) lands here too.
- [`codecs.md`](./codecs.md) — codec instrumentation (decode time, partial-decoder cache hits, parallelism utilization) is published via the same tracer/metrics surface, but the codec API itself isn't modified.

## Open questions

- **OpenTelemetry as the only tracing target?** OTel is the obvious choice — it's the de facto industry standard. But supporting it strictly means a real dependency (the OTel API package, which is well-behaved) and a commitment to following OTel semantic conventions. Worth confirming before locking in.
- **Span name and attribute conventions.** The list above is illustrative. Aligning with [OTel's semantic conventions for storage clients](https://opentelemetry.io/docs/specs/semconv/) where they exist would help downstream consumers (Tempo, Datadog) recognize Zarr traces. Worth a one-pass audit of OTel's spec.
- **Per-`Array` vs per-process metrics aggregation.** Per-`Array` is the right default for testability; users who want process-wide need an explicit aggregator. Whether the aggregator is opt-in or default-on is a small choice with usability implications.
- **`chunk_exists` semantics for sharded arrays.** Does it mean "this *subchunk* is materialized" (the user-visible interpretation) or "this *shard* exists" (the store-level interpretation)? Both are useful; probably we expose both with different names.
- **Block read/write security implications.** `read_block` / `write_block` bypasses the codec pipeline; a malicious or corrupt block written this way will be returned verbatim on a subsequent decoded read, with no validation. Worth documenting as a sharp edge.
