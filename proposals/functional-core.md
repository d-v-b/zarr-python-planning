# Toward a Functional Core for Zarr-Python

> Theme proposal. For the high-level pitch and audience framing, see the [parent README](../README.md).

## Summary

Zarr-Python has accumulated structural debt that makes it harder than it should be to (1) integrate with high-performance implementations like Zarrs (Rust) and TensorStore (C++), (2) be adopted in parts by Python tools that don't want the full Zarr-Python dependency footprint, and (3) evolve safely as the project grows.

This document proposes a refactor of the *internals* — not the public API — toward a clean separation between the **algebra of Zarr** (pure data and pure functions: metadata, chunk layouts, encoded selections, planning) and the parts that actually perform I/O. With that separation in place, faster backends become drop-in replacements, parts of Zarr-Python become independently usable, and the surface area each new feature has to reason about shrinks.

## Why this work is overdue

See the [parent README](../README.md#why-this-work-is-overdue) for the strategic framing. In short: the V3 work was a necessity-driven rewrite under backwards-compatibility constraints and never set the *shape* of the internals; the cost of working around the resulting structural debt now exceeds the cost of paying it down. This proposal is that overdue investment, scoped to the internal refactor toward a functional core.

## The problem

### Integrating faster backends is harder than it should be

[Zarrs](https://github.com/zarrs/zarrs) (Rust) and [TensorStore](https://github.com/google/tensorstore) (C++/Google) are alternative implementations of the Zarr storage format that out-perform Zarr-Python on many workloads, because they are written in compiled languages with finer-grained control over memory and I/O. When a Zarr-Python user hits a performance ceiling, our current answer is to recommend switching libraries — a poor outcome for users (who lose Zarr-Python's ecosystem when they switch) and a poor outcome for the project (which concedes the high-performance use case rather than competing in it).

Today, giving Zarr-Python users access to Zarrs' performance requires a separate external package ([`zarrs-python`](https://github.com/zarrs/zarrs-python)) that re-implements much of Zarr-Python's array logic while delegating chunk decoding to Zarrs. That project is a real achievement, but the cost of the integration is structural: there is no clean seam in Zarr-Python at which an external implementation can take over without re-doing the layers above it. There is no straightforward way for a user to say *"use Zarr-Python's APIs and metadata handling, but route the actual chunk reads through Zarrs (or TensorStore)"* — even though that is exactly what a performance-sensitive user wants.

The cause is structural. Zarr-Python's internal abstractions (the codec pipeline, the paired `Array`/`AsyncArray` layering, the way path handling is split between `Store` and `StorePath`) bundle data, behavior, and execution strategy into the same objects. There is no layer at which "what to do" is separated from "how to do it."

### Parts of Zarr-Python cannot be used in isolation

The clearest evidence is from developers in the Zarr ecosystem who have actively routed around `zarr-python` to avoid its dependency footprint.

Talley Lambert (napari core, [`pymmcore-plus`](https://github.com/pymmcore-plus) maintainer) wanted to use [`ome-zarr-models-py`](https://github.com/ome-zarr-models/ome-zarr-models-py) for OME-NGFF metadata models while building a small microscopy-streaming library, but could not, because `ome-zarr-models-py` transitively requires `zarr-python`. From [the discussion thread](https://github.com/ome-zarr-models/ome-zarr-models-py/issues/161):

> *"I'd rather not depend on zarr-python in my use case... we actually don't depend on zarr for anything else, and some users may still be using other packages that pin, for example, to `zarr<3` given the breakages that came there... I don't feel great about bringing in something that might break people's environments, particularly when all I really wanted was the model."*

His resolution was to write a new package, [`yaozarrs`](https://github.com/tlambert03/yaozarrs), with one dependency (`pydantic`). The downstream effect is a one-developer parallel implementation of the OME-NGFF metadata work, and a tool author re-implementing parsing rather than depending on the de facto standard library.

The pattern recurs across the ecosystem:

- [`janelia-cellmap/mesh-n-bone#14`](https://github.com/janelia-cellmap/mesh-n-bone/pull/14) (merged) — *"Remove zarr runtime dependency, use tensorstore + direct JSON for metadata."* Author description: *"removes a heavy runtime dependency."*
- [`xcube-dev/xcube-resampling#31`](https://github.com/xcube-dev/xcube-resampling/pull/31) (merged) — *"Remove zarr dependency"* in an ESA Earth-observation data-cube project.
- [`fideus-labs/ngff-zarr#114`](https://github.com/fideus-labs/ngff-zarr/issues/114) — writing OME-Zarr v0.5 metadata via TensorStore plus the standard-library `json` package, specifically to avoid pulling in `zarr-python`.
- [`pymmcore-plus/ome-writers#115`](https://github.com/pymmcore-plus/ome-writers/pull/115) — *"Replace zarr-based LiveTiffStore with native ArrayLike implementations."*

Internally, the issue is acknowledged. [`zarr-python#2391`](https://github.com/zarr-developers/zarr-python/issues/2391) *"Rethinking Zarr's core dependencies"* and [`zarr-python#3597`](https://github.com/zarr-developers/zarr-python/issues/3597) *"avoid required, indirect dependencies"* both target the dependency tree directly. [`zarr-python#1370`](https://github.com/zarr-developers/zarr-python/issues/1370) documented `zarr` blocking napari's Python 3.11 CI because of a transitive dependency without wheels.

The shape of the pattern: a developer wants a small piece of Zarr functionality — typically metadata parsing or schema validation — and finds the cost of taking the dependency exceeds the cost of re-implementing the piece they need. The ecosystem accumulates one-off parsers that drift from the spec, or workarounds built on TensorStore (which performs the IO without offering the high-level Zarr APIs `zarr-python` provides). Both outcomes weaken `zarr-python`'s role as the foundation of the Zarr ecosystem.

### The sync/async boundary leaks into every layer

Every store method is async. Every codec encode/decode method is async, even for codecs that do pure CPU work and have no business being async. Performance profiling routinely flags the async-around-sync indirection as a real bottleneck. The deeper cost is conceptual: because async is everywhere, the boundary between *"decide what to do"* (computing chunk keys, planning a slice) and *"actually do it"* (fetch bytes, decompress) is blurred. There is no place to write a pure, testable function that says *"given this metadata and this selection, here are the chunk keys to fetch and the regions they contribute to the output."* Such a function would require neither an event loop nor a store, but the current layering does not let it exist as a separable thing.

### Testing requires the whole stack

Because logic is intertwined with I/O, testing a chunk-grid math change requires standing up a store and a codec pipeline. There is no algebraic core to write fast, deterministic unit tests against. This slows development, raises the cost of new contributions, and makes regressions easier to introduce.

### Extension by external libraries is painful

Adding a new codec, a new chunk grid, a new key encoding, or a new data type all require touching Zarr-Python internals or working around them. The README's section on the codec base class enumerates the specific friction: the base class is not actually abstract; batch operations are baked into the signature; output allocations cannot be elided; codecs do not know about array slicing; the registration model creates circular dependencies between Zarr-Python and codec packages. The same pattern recurs in other extension points.

## The direction

The proposal is to separate Zarr-Python's internals into three concentric layers.

### A functional core

The "algebra of Zarr" — the parts you can reason about without doing any I/O — becomes pure data structures (`ArrayMetadata`, `GroupMetadata`, `ChunkGrid`, `KeyEncoding`, `CodecConfig`, `Selection`, ...) and pure functions over them (parse and validate metadata, compute which chunks overlap a selection, encode chunk coordinates to keys, build the assembly plan for stitching decoded chunks into an output array).

This core has no side effects. It does no I/O, knows nothing about async, holds no mutable state. It is deterministic, picklable, hashable, and safe to use from multiple threads or from free-threaded CPython. It can be packaged and depended on independently: a tool that only needs to parse metadata depends on a small `zarr-metadata` package with no numpy or numcodecs dependency.

This is where the testing story gets dramatically better. The core is testable as pure functions, with no fixtures, no stores, no event loops.

### A small edge layer for side effects

Two kinds of objects survive in the new design: **stores** and **codecs**.

**Stores** are objects (as in the existing stores proposal) because they encapsulate connections to external systems (filesystems, object stores) and have capability surfaces (read, write, list, range-fetch) that vary by backend. The existing stores work — capability protocols, sync/async families, composable wrappers for caching/prefixing/range coalescing — stands. We add one capability: stores serialize to a portable declaration, so they can cross language boundaries. A store created in Python can be handed to a Zarrs or TensorStore engine, which materializes its own equivalent on the other side.

**Codecs** are objects because they bundle related operations on the same identity: at minimum `encode` and `decode`, and optionally `encode_into` / `decode_into` for codecs that can write into pre-allocated output buffers — a real, measurable performance win. One codec class, multiple methods, optional capabilities is the right shape for an OO surface. Codec *instances* are stateless; per-call configuration (gzip level, blosc block size) is data in the metadata, passed as an argument.

### A thin imperative shell, with engines as namespaces

Higher-level operations become module-level functions, not classes. Concretely an engine exports exactly four functions:

- `read_chunk(store, metadata, chunk_coords, ...)` — fetch and decode one chunk.
- `read_selection(store, metadata, plan, ...)` — execute an IO plan covering many chunks for one selection.
- `write_chunk(store, metadata, chunk_coords, data, ...)` — encode and write one chunk.
- `write_selection(store, metadata, plan, data, ...)` — execute an IO plan for a multi-chunk write.

The selection functions take an **IO plan** — a pure data structure produced by the core from a metadata document plus a selection. The plan enumerates the chunks to touch, the byte ranges within each, how decoded chunks compose into the output, and any cache-hit short-circuits. Producing the plan is a pure function in the core; executing it is the engine's job. This is the same split as TensorStore's `Spec → ResolvedSpec → IO` pipeline and the natural seam at which alternative engines plug in (see [performance.md § Wrapping `zarrs` and TensorStore as alternative engines](./performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines)).

There are no `ChunkPipeline`, `CodecPipeline`, or `SliceExecutor` classes. Those were objects whose only purpose was to hold a single method, which is what a function is.

An **engine** is a module that exports those four functions. Zarr-Python ships a default Python engine. Alternative engines are alternative modules. A Zarrs engine is a module whose `read_selection` hands the plan off to Zarrs internally; a TensorStore engine is the equivalent for TensorStore. Mixing across engines — for example, "Python's orchestration with Zarrs' codecs" — is a short module that imports the parts you want from each.

The public `Array` and `Group` classes are thin facades. An `Array` holds a metadata document, a store, an engine, and a codec registry, and delegates each method to the engine. Switching backends means swapping one of those four pieces of state; the public API does not change.

Per [performance.md § Where the caching substrate sits relative to engines](./performance.md#where-the-caching-substrate-sits-relative-to-engines), the caching substrate (in-flight dedup, metadata cache, chunk cache when opted in) sits **above** the engine boundary. Engine calls see deduped, cache-checked requests; engines may keep their own internal caches but do not override the substrate.

## How the new shape solves the problems

| Problem | How the new shape resolves it |
|---|---|
| Integrating Zarrs/TensorStore requires a bespoke external package | An engine is a module of four functions. An integration with another implementation ships those four functions and inherits everything above the I/O — metadata handling, hierarchy traversal, key encoding — unchanged. |
| Parts of Zarr-Python cannot be used in isolation | The functional core splits cleanly into focused packages (e.g. `zarr-metadata`, `zarr-dtype`, `zarr-codec`). Downstream tools depend on the parts they need. |
| Async/sync leaks into every layer | Async belongs only in the shell. The same engine has sync and async variants in separate modules; the core is identical for both. The recurring event-loop reentrancy bugs go away because the only place an event loop is involved is the shell. |
| Testing requires the whole stack | The core is pure functions over pure data. Tests run in milliseconds with no fixtures, no event loops, no stores. |
| Extension is painful | Codecs, chunk grids, key encodings, and data types become small additions to the core (pure data) plus, where needed, a small stateless object (codecs). No deep base classes to subclass, no internal hooks to override. |

## What this enables

**Performance parity for users without forcing a library switch.** A user who needs Zarrs' speed selects a different engine instead of switching libraries. They keep Xarray, Dask, napari, and every other Zarr-Python integration. The high-performance use case stops being a reason to leave the ecosystem.

**Smaller, focused packages the broader ecosystem can adopt.** Tools that only need to parse metadata, compute chunk layouts, or validate a Zarr V3 document can depend on a small package without pulling in numpy, fsspec, and numcodecs. This is exactly what `yaozarrs`, `ngff-zarr`'s metadata path, and `mesh-n-bone`'s direct-JSON approach are already reaching for. It unlocks adoption in places where the current dependency footprint is prohibitive (lightweight services, embedded uses, JavaScript-side validators that today re-implement parsing in another language).

**Faster pace of feature work.** Most new features — new codecs, new chunk grids, new key encodings, new data types — become pure-data additions to the core, tested without I/O. Less infrastructure per change, more changes per release.

**Cleaner integration with downstream libraries.** Dask, Xarray, and similar projects that today reach into Zarr-Python internals to optimize specific patterns can target the core's pure functions instead of brittle internal APIs.

**A path to splitting Zarr-Python into focused packages.** The motivation for splitting Zarr-Python into multiple packages is the same motivation as the functional-core refactor: model the real dependency relationships, support partial adoption, harden conceptual boundaries. The concrete package list and dependency map are spelled out below.

## What this is not

- **Not a public API change.** The `zarr.open`, `zarr.create_array`, `Array[...]`, `Group[...]` surfaces stay where they are. Existing user code keeps working.
- **Not a function-by-function API design.** This document argues the direction and the shape of the solution. Concrete signatures and module layouts are deferred to follow-on proposals.
- **Not a redesign of the store layer.** The existing stores proposal stands; we add only the serialization capability that lets stores cross language boundaries.
- **Not a single-release push.** The refactor is incremental and staged. The functional core can be extracted and tested alongside the existing internals; engines can be added one at a time; the public facade can migrate to delegating into the core gradually, with no flag day.

## Concrete packaging plan

The functional core gives us clean seams along which `zarr-python` can be split into independently installable packages. This section names the packages and the dependency relationships they should preserve.

### The packages

- `zarr-metadata` — pure data structures and parsers for Zarr V2 and V3 metadata documents. Also owns the **chunk-addressing** types — `ChunkGrid` (regular and Rectilinear), `ChunkKeyEncoding` (V2 and V3 variants, including future entries from `zarr-extensions`) — because they are pure-data descriptions consumed by both metadata parsing and chunk lookup. This is the package that grows when a new chunk grid or key encoding is specified, which is one of the README's 4.0 acceleration goals.
- `zarr-dtype` — Zarr data type system.
- `zarr-codec` — the codec interface (no concrete codec implementations). Defines the `Codec` protocol family, `recommended_concurrency`, `PartialDecodeCapability`, `decode_into`, and so on. Codec implementations live in `zarr-python` or in third-party packages that depend on `zarr-codec`.
- `zarr-store` — the store interface (capability protocols).
- `zarr-python` — the user-facing facade that re-exports the pieces above, ships the default Python engine, and ships the concrete built-in codecs (`gzip`, the V2/V3 codec wrappers, and so on).

Today, a downstream tool that only needs to parse metadata still has to install `numpy`, `numcodecs`, `google-crc32c`, `fsspec`, and the rest of [Zarr-Python's runtime dependencies](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/pyproject.toml#L35-L40). A `zarr-metadata` package needs little more than `typing_extensions`. The evidence from `yaozarrs`, `mesh-n-bone`, `xcube-resampling`, and `ngff-zarr` (above) is the cost of *not* doing this split.

### The dependency relationships

The split mirrors the real dependency structure of the Zarr format:

- Parsing metadata documents depends on: a metadata API.
- Storing metadata documents depends on: a metadata API + a store API.
- Finding stored chunks depends on: a metadata API + a store API + a chunk grid API + a chunk key encoding API.
- Decoding chunks depends on: all of the above + a data type API + a codec API.

Modeling these as actual package boundaries hardens the conceptual boundaries inside the project and lets downstream tools depend on exactly the surface they use. This is the approach [`zarrs`](https://github.com/zarrs/zarrs) uses on the Rust side.

### Case study: breaking the codec circular dependency

Today, `zarr-python` defines the codec interface via a `Codec` base class. Any external codec library must subclass it and register with the codec registry — making `zarr-python` a runtime dependency of every external codec library. The pathological case is implementing a *core* codec (say, a Rust-based `gzip`) in an external library: `zarr` depends on `external.gzip`, but `external.gzip` depends on `zarr` for the `Codec` base class. Any change to `Codec` without a perfectly synchronized update to `external.gzip` is a source of subtle bugs.

This is not hypothetical. `zarr-python` used to depend on `numcodecs`, which depended on `zarr-python`. Untangling the cycle took real work — see [`numcodecs#780`](https://github.com/zarr-developers/numcodecs/pull/780) and [`zarr-python#3376`](https://github.com/zarr-developers/zarr-python/pull/3376). Registering codecs via [entry points](https://packaging.python.org/en/latest/specifications/entry-points/) instead of explicit imports *weakens* the coupling but does not remove it.

Extracting `zarr-codec` as an independent package with its own version number, importable by `zarr-python` and any other package, is the only real fix. (As a historical note: Zarr-Python 2.x avoided this cycle by importing the codec interface from `numcodecs`. The cycle is a regression introduced by the 3.x rewrite.)

### Related GitHub content

- [`zarr#3913`](https://github.com/zarr-developers/zarr-python/issues/3913)
- [`zarr#3867`](https://github.com/zarr-developers/zarr-python/issues/3867)
- [`zarr#3875`](https://github.com/zarr-developers/zarr-python/pull/3875)
- [`zarr#2863`](https://github.com/zarr-developers/zarr-python/pull/2863)
- [`zarr#2391`](https://github.com/zarr-developers/zarr-python/issues/2391) — *Rethinking Zarr's core dependencies*
- [`zarr#3597`](https://github.com/zarr-developers/zarr-python/issues/3597) — *avoid required, indirect dependencies*

## Relationship to existing proposals

- [`proposals/stores-api.md`](./stores-api.md) — preserved as-is, with one addition: a `Serializable` capability that lets a store produce a portable declaration of how to connect to its backend (an S3 URL, a path, an fsspec URL — not the store's contents). The conformance suite gains a matching specification.
- [`proposals/stores-conformance.md`](./stores-conformance.md), [`proposals/stores-range-coalescing.md`](./stores-range-coalescing.md), [`proposals/stores-transactional.md`](./stores-transactional.md), [`proposals/stores-wrappers.md`](./stores-wrappers.md) — preserved unchanged. The functional core sits above the store layer and does not touch their design.
- [`proposals/stores-caching.md`](./stores-caching.md) — preserved in shape, with two requirements imposed by [performance.md § Default caching policy](./performance.md#default-caching-policy): the wrapper grows the three-tier toggles (`metadata` / `chunks` / `negative`) and every backend grows a `with_caching(...)` convenience method. The wrapper class itself stays.
- README sections on **Codecs**, **Concurrency**, and **Data types** — the functional core enables the directions argued in each of these sections. The codec API rewrite folds in naturally (codecs become small, stateless, capability-bundled objects); the concurrency story simplifies because async lives only in the shell; new data type support becomes a pure-data addition.

## Open questions for follow-on work

- **Engine selection ergonomics at the public surface.** Explicit keyword argument, URL-scheme routing, global configuration, or some combination — to be specified when drafting the facade layer.
- **Format of the store declaration.** Likely a typed dataclass with a JSON schema; alignment with obstore's URL+config pattern worth exploring. The declaration carries store identity and connection info — not stored data.
- **Migration sequencing.** Which core pieces extract first; whether the existing `Array`/`AsyncArray` pair stays or collapses into a single facade with sync and async methods; how long deprecation windows last. To be addressed in the implementation plan.
