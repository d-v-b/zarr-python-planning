# Zarr-Python Planning

Plans for the future of Zarr-Python.

## Audience

This planning document is for two audiences. The first is Zarr developers and contributors evaluating where the project should go next. The second is funders, institutional partners, and stakeholders who care about Zarr's success in the scientific Python ecosystem but don't follow the codebase day-to-day. The README is the entry point for both; individual proposal documents under `proposals/` go deeper for developers and reviewers.

## Why Zarr-Python exists

A fair question to start with: **if [TensorStore](https://github.com/google/tensorstore) already has Python bindings, and [zarrs-python](https://github.com/zarrs/zarrs-python) exists, why should Zarr-Python continue to be a project at all?** Why not declare it superseded by the compiled-language implementations, build thin Python wrappers around them, and move on?

The honest answer has two parts.

**A Python-first codebase is itself a strategic asset for the Zarr ecosystem.** The overwhelming majority of scientific data work happens in Python: Xarray, Dask, napari, anndata, scverse, Pangeo, every major bioimaging and geospatial stack. The developers building those tools read Python, write Python, and extend their tools in Python. When a Zarr-related feature is needed — a new convention layer for OME-NGFF, a custom store backend for a lab's storage system, a domain-specific validator, a notebook-side debugging tool — the cost of writing it in Python is hours; the cost of writing it in Rust or C++ with bindings is weeks to months. A Python-native implementation is the substrate that lets the *long tail* of Zarr-using projects extend Zarr cheaply. Conceding the Python-native layer means conceding that long tail to ad-hoc per-project workarounds (which is what we already see — `yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr` all routed around `zarr-python` for various reasons; the [functional-core proposal](./proposals/functional-core.md#parts-of-zarr-python-cannot-be-used-in-isolation) walks through this evidence).

**TensorStore and zarrs are complementary, not competitive.** They are excellent at what they do — high-performance, compiled-language IO with deep optimizations no Python implementation can match. The right relationship between Zarr-Python and them is not "pick one"; it is "Python developers should get both, with no migration cost." A user who needs TensorStore's throughput on a specific workload should not have to abandon Xarray, Dask, every domain-specific Zarr reader, and every store backend `zarr-python` supports. The [engine architecture in performance.md](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines) is the structural commitment to this: `zarr-python` ships native bindings for `zarrs` and TensorStore as alternative engines, selectable with a one-line keyword argument. Users keep the surface; the engine swaps. The competitive narrative inverts — TensorStore and zarrs become *amplifiers* of the Zarr-Python ecosystem rather than off-ramps from it.

This is the both-and answer. We do not have to choose. **We engineer Zarr-Python to be the best pure-Python Zarr implementation available, *and* to be the best wrapper around the compiled-language implementations.** The pure-Python mode is what makes the library extensible by the Python ecosystem; the compiled-language engines are what give that ecosystem access to native-throughput IO when the workload demands it. Most users will live on the pure-Python path because most workloads do not need native throughput; the users who do need it pay the FFI dependency cost and get the speedup without losing anything else.

For this to be a credible story, the pure-Python mode has to actually *be* good — performant, extensible, well-shaped. That is what the rest of this document is about. If we fail at the pure-Python work, the "both-and" answer collapses into "use TensorStore, ignore us," and we lose the Python-native layer that the ecosystem depends on. The proposals below are the technical commitments that make the pure-Python mode worth keeping.

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

The risk under the both-and framing above is that we *under-invest* in the pure-Python mode, and the "the pure-Python path is good enough that the FFI engines are an optimization, not a necessity" claim stops being true. If Zarr-Python is too slow to improve performance, add features, and make APIs better, users will adopt other Python tools like Tensorstore, or simply not use Zarr at all. We have a lot of inertia, thanks to projects like Dask and Xarray, but that can change *very quickly* if someone motivated stands up a cleaner, faster, better Python-based Zarr library. We should run that cleaner, faster, better library. The following sections outline my vision for how we can make that happen.

## Why we can move fast now

There is a counterweight to the fear above. Zarr-Python is in a genuinely fortunate position relative to most library-rewrite efforts: **we have two independently-written, production-quality, high-performance Zarr implementations to learn from.** [Zarrs](https://github.com/zarrs/zarrs) (Rust) and [TensorStore](https://github.com/google/tensorstore) (C++/Google) were written by different teams, in different languages, against different design constraints, with no coordination between them. And they have *converged* on the same architectural patterns — sync-first codec APIs with async as an opt-in adapter; per-codec advertised concurrency budgets; sharded reads with adaptive whole-shard-vs-coalesced strategies; pre-allocated decode buffers; per-key in-flight deduplication; conditional reads with ETag-style generations; pipeline caches inserted between codecs that lack partial-decode support. When two independent reference implementations agree on something this specific, the case for adopting it is much stronger than any one team's design instincts.

This is the rare situation where the hard architectural questions have already been answered for us. We do not have to invent; we have to translate.

That translation work has been **vastly accelerated by large language models.** Reading a 200-thousand-line C++ codebase and a 50-thousand-line Rust codebase to extract their architectural patterns — what each library does, why it does it, how the pieces compose, what's load-bearing vs. incidental — is exactly the kind of cross-codebase synthesis that used to take weeks of senior engineering time and now takes hours. Most of the comparative analysis cited in the proposals below ([codecs.md](./proposals/codecs.md), [stores.md](./proposals/stores.md), [performance.md](./proposals/performance.md)) was assembled with LLM-driven code reading, source-grep, and synthesis loops. The technical work — designing the new APIs, writing the migration plans, building the implementations — is still ours to do, and the LLM-assisted findings have been verified against the source by hand for the load-bearing claims. But the *discovery* phase, which historically dominated the cost of a project like this, has collapsed to a fraction of what it once was.

The combination — two reference implementations we can learn from, plus tools that let us extract their lessons cheaply — is why a project this ambitious is realistic on a 4.0 timeframe rather than being a multi-year research effort. We are not designing in the dark; we are catching up to two libraries that have already done most of the hard thinking. The proposals below reflect the *current* state of that translation: the substantial themes (Functional Core, Codecs, Stores, Lazy Indexing, Performance, Observability, Device-agnostic IO, Data types) are fleshed out; one stub (Consolidated metadata) remains as a placeholder for the next pass and is not blocked on discovery, only on writing time.

## Why this work is overdue

The V3 work was a necessity-driven rewrite under hard backwards-compatibility constraints — support V3, do not break Xarray, Dask, or the long tail of downstream tools. The result made V3 work and preserved the user-facing API, but inherited many of the structural patterns of the V2 implementation it replaced. The library has never had a release whose primary goal was the *shape* of the internals.

That trade-off — features and compatibility first, internals later — was defensible for a long time. As the ecosystem matures, the calculus has flipped. The dependency-footprint workarounds documented in the proposals below, the bespoke external package required for Zarrs integration, the recurring bugs in path handling and async layering all share one root cause: the internals were never designed, they accreted. The accumulated cost of working around them now exceeds the cost of paying them down.

The 4.0 work proposed here is that overdue investment. The user-facing API does not change.

## Foundation: a functional core

Several themes below depend on a common substrate: a refactor of Zarr-Python's internals around a *functional core* — pure data structures and pure functions for the algebra of Zarr (metadata, chunk layouts, slice planning, codec walking) — with the side-effecting protocols (stores, codecs) at the edges. This is itself an internal change, not something user-facing. It is foundational for the Codecs and Stores themes, it shapes the per-level package split (`zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`) covered inside the functional-core proposal itself, and it unlocks the high-performance integration story for Zarrs and TensorStore by providing a clean substrate for engine-level pluggability.

→ [proposals/functional-core.md](./proposals/functional-core.md)

## The Zarr Stack

There are levels of Zarr support. Some applications, like validators for domain-specific Zarr conventions, only need to read Zarr metadata documents. They don't need to read and write chunks. Other applications might only need read-only access to array metadata and the stored chunks, and nothing else. Tensorstore only supports reading and writing arrays, but not the `attributes` field of Zarr metadata, and it doesn't support any operations on Zarr groups. Zarr Python supports all types of operations -- reading and writing arrays and groups -- but doesn't support exactly the same set of data types and codecs as other "complete" implementations. 

The story here is that different applications need to do different operations with Zarr data. This is something we *learned* from seeing how different tools and communities leverage Zarr. Let's call a set of tools that supports these various operations a "Zarr stack". 

Concretely, the levels of the stack — from most abstract to most concrete — look something like this:

1. **Conventions** — domain-specific schemas built on top of Zarr (OME-NGFF, GeoZarr, anndata-zarr). Consumers: validators, format-specific readers, the `yaozarrs` / `ome-zarr-models-py` line of work.
2. **Groups** — Zarr hierarchies, traversal, group-level attributes.
3. **Arrays** — the user-facing array object, plus indexing and slicing. In 4.0 this level grows [lazy indexing and Array API conformance](./proposals/lazy-indexing.md): a `LazyArray` view becomes available alongside the eager `__getitem__`, and the query planner sits here. The default flips to lazy in a later 4.x release; the eager path is removed in 5.0.
4. **Chunk decoding** — the codec pipeline. In 4.0 this becomes a [small stateless capability bundle](./proposals/codecs.md) (encode / decode / optional `decode_into` / capability flags) decoupled from the rest of the library, with concrete codec implementations as plug-ins. This is also the seam where alternative engines (Zarrs, TensorStore) plug in — see the [performance proposal](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines).
5. **Chunk addressing** — chunk grids and key encodings that map array coordinates to store keys. Lives in the [`zarr-metadata` package](./proposals/functional-core.md#the-packages) as pure-data descriptions; accelerating new grids and key encodings (one of the 4.0 goals above) is mechanically a matter of adding new entries to this package.
6. **Stores** — the key-value layer. In 4.0 this is *not* a monolithic `Store` class but a set of [capability protocols](./proposals/stores.md) (`Get`, `GetRange`, `Put`, `Delete`, `List`, ...) that backends declare and compose. Composable wrappers add caching, range coalescing, transactions, and retries on top, and a conformance suite defines what each capability means. See [stores.md](./proposals/stores.md) for the theme proposal; the detailed [API](./proposals/stores-api.md), [wrappers](./proposals/stores-wrappers.md), and [conformance suite](./proposals/stores-conformance.md) are linked from there.
7. **Metadata** — pure data documents describing arrays and groups. Sits at the bottom of the dependency graph: every other level depends on it, it depends on nothing.

A few of these levels are richer than a simple list suggests. Stores (level 6) have both *backends* (concrete implementations like `LocalStore`, `FsspecStore`) and *wrappers* (orthogonal capabilities like `Caching[S]`, `RangeCoalescing[S]`, `Transactional[S]`) that compose. Chunk decoding (level 4) has both the *interface* and pluggable *engines* (the default Python engine, Zarrs, TensorStore). The stack is not just seven nominal types — it is seven boundaries at which different kinds of pluggability live.

Today, `zarr-python` is a monolith that serves every level. A consumer who only needs level 1 has to install the full dependency footprint of level 7. A faster implementation at level 4 (Zarrs, TensorStore) cannot easily plug in without re-implementing levels 1–3. The dependency-footprint workarounds in the ecosystem (`yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr`) and the existence of a bespoke `zarrs-python` integration package are evidence that the monolith shape does not match how the ecosystem actually uses Zarr.

The 4.0 direction is to re-shape `zarr-python` around the stack: each level is something you can depend on, conform to, or replace, without buying every level above it. Concretely:

- **A focused package per level** — `zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`, and so on. See the [functional-core proposal](./proposals/functional-core.md#concrete-packaging-plan) for the concrete plan.
- **A documented interface per level** — capability protocols for stores, a small stateless codec API, pure-data dtypes, declarative hierarchy schemas.
- **A conformance suite per level** — the stores work has the most developed example ([stores-conformance.md](./proposals/stores-conformance.md)); the same pattern extends to codecs, dtypes, and engines.
- **Engine pluggability at the chunk-decoding level** — alternative implementations (Zarrs, TensorStore) can take over without re-doing the layers above. See [performance.md § Wrapping `zarrs` and TensorStore as alternative engines](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines).

This reframes our 4.0 goal of *"support Python tools across all levels of the Zarr stack"* from a slogan into a concrete commitment: every level has a named package, a documented interface, and a conformance suite. It also reframes high-performance backends from competitors to **peers at specific levels** — a user can keep `zarr-python`'s metadata, hierarchy, and indexing while routing chunk reads through Zarrs.

The mechanism for this re-shaping is the [functional-core refactor](./proposals/functional-core.md), which extracts the pure-data and pure-function parts of each level out of the monolith and into independently usable pieces.

## What we're changing

Each theme below has a corresponding proposal document under `proposals/`. Substantial themes (Functional Core, Codecs, Stores, Lazy Indexing, Performance, Observability, Device-agnostic IO, Data types) have full proposals; the rest are stubs awaiting expansion.

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

First-class support for ML-specific dtypes — `bfloat16`, the `float8` variants, packed `int4`/`uint4` — via Google's [`ml_dtypes`](https://github.com/jax-ml/ml_dtypes) package, either as an optional dependency of `zarr-python` or as a separate `zarr-ml-dtypes` package. Unblocks the substantial and growing ML community using Zarr for model checkpoints and training data. Ragged arrays, vlen strings, and dtype/codec interactions are follow-on work on the same `zarr-dtype` substrate. The proposal also commits to *investigating* Apache Arrow integration as a substrate for the dtypes the Array API can't express (nullable scalars, vlen strings, nested types) — the investigation itself is the 4.0 deliverable; what ships is determined by what we find.

→ [proposals/data-types.md](./proposals/data-types.md)

### Device-agnostic IO

The goal here is **not** to add GPU support as a feature — it's to make Zarr-Python's IO surfaces device-agnostic in the first place. Stores and codecs grow APIs for writing into a caller-provided buffer (`read_into`, `decode_into`); the Array facade returns array-like objects in the user's chosen [Array API](https://data-apis.org/array-api/) namespace. GPU support falls out for free once the assumption of CPU destinations is removed. CPU paths get faster too, because pre-allocated output buffers eliminate per-chunk allocation regardless of where the buffer lives.

→ [proposals/gpu.md](./proposals/gpu.md)

### Observability

A cross-cutting theme covering two pillars: **performance metrics and tracing** (a small library-owned `Metrics` object plus OpenTelemetry auto-instrumentation across stores, codecs, caches, concurrency admission, and the engine boundary) and **stored-state introspection** (public APIs for asking the library about chunk-level structure, materialization, byte ranges, and storage footprint without reading the chunks — the surface VirtualiZarr and Kerchunk have been asking for).

→ [proposals/observability.md](./proposals/observability.md)

### Missing APIs

The user-facing APIs that don't fit into the other themes but that users have been asking for, in some cases for years. Five user-facing API areas (hierarchy navigation, chunk introspection, constructor and lifecycle UX, display and debugging, IO conveniences) plus a section on the configuration substrate replacement (retiring `donfig`).

→ [proposals/missing-apis.md](./proposals/missing-apis.md)

### Performance

Performance is cross-cutting. Typed concurrency resources (`ComputeConcurrency`, `IoConcurrency`); synchronous codec encode/decode; range coalescing; pre-allocated decode buffers; in-flight request deduplication; ETag-style revalidation; a unified `AsyncCache`-shaped caching substrate with sensible defaults; an adaptive whole-shard-vs-coalesced read strategy; and pluggable high-performance backends via the engine boundary (Zarrs, TensorStore). The integrated story — including the concurrency and correctness model — lives in this one proposal so reviewers and stakeholders can read about end-to-end speedups in one place.

→ [proposals/performance.md](./proposals/performance.md)
