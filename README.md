# Zarr-Python Planning

Plans for the future of Zarr-Python.

## Audience

This planning document is for two audiences. The first is Zarr developers and contributors evaluating where the project should go next. The second is funders, institutional partners, and stakeholders who care about Zarr's success in the scientific Python ecosystem but don't follow the codebase day-to-day. The README is the entry point for both; individual proposal documents under `proposals/` go deeper for developers and reviewers.

## Background

_at the time of this writing, the current released version of Zarr-Python is 3.1.6_

The [3.0 release](https://github.com/zarr-developers/zarr-python/releases/tag/v3.0.0) of Zarr-Python featured a total redesign of the internals of the library. The new design was shaped by the following goals:
- Full support for Zarr [V2](https://zarr-specs.readthedocs.io/en/latest/v2/v2.0.html) and [V3](https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html) storage formats.
- Storage APIs that were ergonomic for high-latency storage (e.g., cloud object storage).
- Backwards compatibility with Zarr-Python 2.x, where possible.

We largely achieved those goals: compared to Zarr-Python 2.18 (the last release in the 2.x series), Zarr-Python 3.x has infinitely better support for the Zarr V3 format and vastly improved IO performance for cloud storage backends. 

We hit these marks while retaining a very high degree of backwards compatibility with the 2.x APIs. Some Zarr-Python consumers are still migrating to 3.x, but large downstream libraries like `Xarray` and `dask` managed the transition relatively easily.

Over 1 year since the 3.0 release, I feel comfortable stating that the 2.x -> 3.0 transition is effectively resolved. 

So what's next for `Zarr-Python`?

## Zarr 4.0 goals

Our old Zarr-Python 3.0 goals are accomplished. That means it's time to define Zarr-Python 4.0 in terms of some new goals. 

If the 3.0 goals could be sloganized as "Migrate to Zarr V3, and improve cloud storage support", I propose the following slogan for the 4.0 goals: "Support a Zarr-based Python ecosystem for chunked arrays". The Zarr-Python project should be *foundational* for the increasingly large number of Python packages that work with data in the Zarr format. We want to position Zarr Python packages as viable core components for *any* project that works with Zarr data.

To reach this I think we should push in the following directions:

- Give Zarr-Python users excellent performance, out of the box. 
- Make Zarr-Python APIs ergonomic and useful for developers. 
- Expand our scope to cover vital quality-of-life routines like data copying, rechunking, and the like.
- Support the growth of Python tools that don't use Zarr-Python explicitly.  
- Accelerate the implementation of new codecs, chunk grids, chunk key encodings, etc. 

## What I'm afraid of

I worry that if we don't keep moving forward as a library, we will fall behind. If Zarr Python is too slow to improve performance, add features, and make APIs better, users will adopt other Python tools like Tensorstore, or simply not use Zarr at all. We have a lot of inertia, thanks to projects like Dask and Xarray, but that can change *very quickly* if someone motivated stands up a cleaner, faster, better Python-based Zarr library. We should run that cleaner, faster, better library. The following sections outline my vision for how we can make that happen.

## Why this work is overdue

The V3 work was a necessity-driven rewrite under hard backwards-compatibility constraints — support V3, do not break Xarray, Dask, or the long tail of downstream tools. The result made V3 work and preserved the user-facing API, but inherited many of the structural patterns of the V2 implementation it replaced. The library has never had a release whose primary goal was the *shape* of the internals.

That trade-off — features and compatibility first, internals later — was defensible for a long time. As the ecosystem matures, the calculus has flipped. The dependency-footprint workarounds documented in the proposals below, the bespoke external package required for Zarrs integration, the recurring bugs in path handling and async layering all share one root cause: the internals were never designed, they accreted. The accumulated cost of working around them now exceeds the cost of paying them down.

The 4.0 work proposed here is that overdue investment. The user-facing API does not change.

## Foundation: a functional core

Several themes below depend on a common substrate: a refactor of Zarr-Python's internals around a *functional core* — pure data structures and pure functions for the algebra of Zarr (metadata, chunk layouts, slice planning, codec walking) — with the side-effecting protocols (stores, codecs) at the edges. This is itself an internal change, not a user-facing one. It is foundational for the Packaging, Codecs, and Stores themes, and it unlocks the high-performance integration story for Zarrs and TensorStore by providing a clean substrate for engine-level pluggability.

→ [proposals/functional-core.md](./proposals/functional-core.md)

## What we're changing

Each theme below has a corresponding proposal document under `proposals/`. Substantial themes (Packaging, Codecs, Stores) have full proposals; the rest are stubs awaiting expansion.

### Packaging

Split Zarr-Python into separate packages along the real dependency boundaries of the Zarr format — `zarr-metadata`, `zarr-dtype`, `zarr-codec`, and so on. Today a downstream tool that only needs to parse metadata still has to install numpy, numcodecs, and fsspec — and several projects (yaozarrs, mesh-n-bone, xcube-resampling, ngff-zarr) have already routed around `zarr-python` because of that cost. Splitting hardens the conceptual boundaries inside the library and lets downstream tools depend on exactly the surface they use.

→ [proposals/packaging.md](./proposals/packaging.md)

### Codecs

The codec API is wrapped in an unnecessary async layer (a profiling-hotspot), defines abstract base classes that are not actually abstract, bakes batching into every encode/decode signature, and forces output allocation even when the caller has a buffer ready. Many Zarr V2 codecs still have no V3 equivalent. Rewrite the codec API as a small, stateless capability bundle decoupled from the rest of `zarr-python`, with clear paths for migrating existing codecs, integrating Zarrs/TensorStore at the codec level, and reducing the role of Numcodecs.

→ [proposals/codecs.md](./proposals/codecs.md)

### Stores

The store abstraction conflates lifecycle, path handling, sync/async, capability advertisement, and read-only semantics into one inheritance hierarchy, and the resulting maintenance friction has produced a recurring stream of regressions. Redesign stores as composable capability protocols (Get, Put, List, ...) with composable wrappers (caching, range coalescing, retries), a sync/async family split, transactional semantics, and a shared conformance suite that backends and wrappers parameterize.

→ [proposals/stores.md](./proposals/stores.md) (with tier-3 specs linked from there)

### Consolidated metadata

Zarr's pattern of bundling all metadata into a single root-level document is essential for performance on high-latency storage and widely used by downstream tools. The current Zarr-Python support has open design questions around codec/dtype/grid representations, write-time invalidation, and migration between V2/V3 consolidated formats.

→ [proposals/consolidated-metadata.md](./proposals/consolidated-metadata.md)

### Data types

Several open requests for data-type support: bfloat16 and other ML dtypes, ragged arrays, dtype/codec interactions, and registry issues that surface when new types are added.

→ [proposals/data-types.md](./proposals/data-types.md)

### Concurrency and thread safety

Long-standing issues around thread-unsafe initialization, multiprocessing failures, async event-loop conflicts, and the path forward for free-threaded CPython.

→ [proposals/concurrency.md](./proposals/concurrency.md)

### Caching

Decoded-chunk caching has been one of the oldest open requests. Layered caching, negative-result caching, and fixing fsspec caching interactions with FsspecStore are all in scope. The store-level Caching wrapper covers a different layer; this theme covers the rest.

→ [proposals/caching.md](./proposals/caching.md)

### GPU and device support

Core device abstraction, CUDA streams/devices, and alignment with the array-api standard.

→ [proposals/gpu.md](./proposals/gpu.md)

### Observability

OpenTelemetry integration and structured logging across store, array, and group operations.

→ [proposals/observability.md](./proposals/observability.md)

### Migration tooling

V2-to-V3 migration acceleration and a CLI for copy/remove/convert/rechunk operations.

→ [proposals/migration-tooling.md](./proposals/migration-tooling.md)

### Missing APIs

A grab bag of features users have asked for: declarative hierarchy modelling and schema validation, lazy slicing and array-api alignment, a stable async/sync bridge, array views, and rechunking.

→ [proposals/missing-apis.md](./proposals/missing-apis.md)

## Performance

Performance is cross-cutting. Synchronous codec encode/decode, range coalescing, smarter buffer allocation, and pluggable high-performance backends (Zarrs, TensorStore) all touch multiple themes — codecs, stores, and the functional core. The integrated story lives in its own proposal so reviewers and stakeholders can read about end-to-end speedups in one place.

→ [proposals/performance.md](./proposals/performance.md)
