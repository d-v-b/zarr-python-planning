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
- Support the growth of Python tools across all levels of the Zarr stack.  
- Accelerate the implementation of new codecs, chunk grids, chunk key encodings, etc. 

## What I'm afraid of

I worry that if we don't keep moving forward as a library, we will fall behind. If Zarr Python is too slow to improve performance, add features, and make APIs better, users will adopt other Python tools like Tensorstore, or simply not use Zarr at all. We have a lot of inertia, thanks to projects like Dask and Xarray, but that can change *very quickly* if someone motivated stands up a cleaner, faster, better Python-based Zarr library. We should run that cleaner, faster, better library. The following sections outline my vision for how we can make that happen.

## Why this work is overdue

The V3 work was a necessity-driven rewrite under hard backwards-compatibility constraints — support V3, do not break Xarray, Dask, or the long tail of downstream tools. The result made V3 work and preserved the user-facing API, but inherited many of the structural patterns of the V2 implementation it replaced. The library has never had a release whose primary goal was the *shape* of the internals.

That trade-off — features and compatibility first, internals later — was defensible for a long time. As the ecosystem matures, the calculus has flipped. The dependency-footprint workarounds documented in the proposals below, the bespoke external package required for Zarrs integration, the recurring bugs in path handling and async layering all share one root cause: the internals were never designed, they accreted. The accumulated cost of working around them now exceeds the cost of paying them down.

The 4.0 work proposed here is that overdue investment. The user-facing API does not change.

## Foundation: a functional core

Several themes below depend on a common substrate: a refactor of Zarr-Python's internals around a *functional core* — pure data structures and pure functions for the algebra of Zarr (metadata, chunk layouts, slice planning, codec walking) — with the side-effecting protocols (stores, codecs) at the edges. This is itself an internal change, not something user-facing. It is foundational for the Packaging, Codecs, and Stores themes, and it unlocks the high-performance integration story for Zarrs and TensorStore by providing a clean substrate for engine-level pluggability.

→ [proposals/functional-core.md](./proposals/functional-core.md)

## The Zarr Stack

There are levels of Zarr support. Some applications, like validators for domain-specific Zarr conventions, only need to read Zarr metadata documents. They don't need to read and write chunks. Other applications might only need read-only access to array metadata and the stored chunks, and nothing else. Tensorstore only supports reading and writing arrays, but not the `attributes` field of Zarr metadata, and it doesn't support any operations on Zarr groups. Zarr Python supports all types of operations -- reading and writing arrays and groups -- but doesn't support exactly the same set of data types and codecs as other "complete" implementations. 

The story here is that different applications need to do different operations with Zarr data. This is something we *learned* from seeing how different tools and communities leverage Zarr. Let's call a set of tools that supports these various operations a "Zarr stack". 

Concretely, the levels of the stack — from most abstract to most concrete — look something like this:

1. **Conventions** — domain-specific schemas built on top of Zarr (OME-NGFF, GeoZarr, anndata-zarr). Consumers: validators, format-specific readers.
2. **Groups** — Zarr hierarchies, traversal, group-level attributes.
3. **Arrays** — array-level metadata, indexing, slicing, the user-facing array object.
4. **Chunk decoding** — the codec pipeline that turns stored bytes into array values.
5. **Chunk addressing** — chunk grids and key encodings that map array coordinates to store keys.
6. **Stores** — the key-value abstraction over filesystems, object stores, and other backends.
7. **Metadata** — pure data documents describing arrays and groups.

Today, `zarr-python` is a monolith that serves every level. A consumer who only needs level 1 has to install the full dependency footprint of level 7. A faster implementation at level 4 (Zarrs, TensorStore) cannot easily plug in without re-implementing levels 1–3. The dependency-footprint workarounds in the ecosystem (`yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr`) and the existence of a bespoke `zarrs-python` integration package are evidence that the monolith shape does not match how the ecosystem actually uses Zarr.

The 4.0 direction is to re-shape `zarr-python` around the stack: each level is something you can depend on, conform to, or replace, without buying every level above it. Concretely, this means a focused package per level (`zarr-metadata`, `zarr-store`, `zarr-codec`, ...), a conformance suite that defines what it means to serve each level, and a clean seam at the chunk-decoding level where alternative engines like Zarrs and TensorStore can take over without re-doing the layers above them. This reframes our 4.0 goal of *"support Python tools across all levels of the Zarr stack"* from a slogan into a concrete commitment: every level has a named package, a documented interface, and a conformance suite. It also reframes high-performance backends from competitors to **peers at specific levels** — a user can keep `zarr-python`'s metadata, hierarchy, and indexing while routing chunk reads through Zarrs.

The mechanism for this re-shaping is the [functional-core refactor](./proposals/functional-core.md), which extracts the pure-data and pure-function parts of each level out of the monolith and into independently usable pieces.

## What we're changing

Each theme below has a corresponding proposal document under `proposals/`. Substantial themes (Functional Core, Codecs, Stores, Lazy Indexing) have full proposals; the rest are stubs awaiting expansion.

### Codecs

The codec API is wrapped in an unnecessary async layer (a profiling-hotspot), defines abstract base classes that are not actually abstract, bakes batching into every encode/decode signature, and forces output allocation even when the caller has a buffer ready. Many Zarr V2 codecs still have no V3 equivalent. Rewrite the codec API as a small, stateless capability bundle decoupled from the rest of `zarr-python`, with clear paths for migrating existing codecs, integrating Zarrs/TensorStore at the codec level, and reducing the role of Numcodecs.

→ [proposals/codecs.md](./proposals/codecs.md)

### Stores

The store abstraction conflates lifecycle, path handling, sync/async, capability advertisement, and read-only semantics into one inheritance hierarchy, and the resulting maintenance friction has produced a recurring stream of regressions. Redesign stores as composable capability protocols (Get, Put, List, ...) with composable wrappers (caching, range coalescing, retries), a sync/async family split, transactional semantics, and a shared conformance suite that backends and wrappers parameterize.

→ [proposals/stores.md](./proposals/stores.md) (with tier-3 specs linked from there)

### Lazy indexing

`Array.__getitem__` performs IO eagerly and returns NumPy, which makes Zarr arrays the odd one out among modern array libraries, blocks participation in the Python Array API ecosystem, and forces every performance-sensitive user through Dask to recover basic IO optimizations like deduplication, slice fusion, and range coalescing. Make indexing return a lazy view by default, conform to the Array API standard, and introduce a small query planner that turns chained selections into a single IO plan before any chunks are fetched.

→ [proposals/lazy-indexing.md](./proposals/lazy-indexing.md)

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
