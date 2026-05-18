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

Higher-level operations — read a chunk, read a selection, write a chunk, write a selection — become module-level functions. They compose pure functions from the core (to figure out what to do) with method calls on stores and codecs (to actually do it). There are no `ChunkPipeline`, `CodecPipeline`, or `SliceExecutor` classes. Those were objects whose only purpose was to hold a single method, which is what a function is.

An **engine** is a module that exports this small set of read/write functions. Zarr-Python ships a default Python engine. Alternative engines are alternative modules. A Zarrs engine is a module whose `read_selection` hands off to Zarrs internally; a TensorStore engine is the equivalent for TensorStore. Mixing across engines — for example, "Python's orchestration with Zarrs' codecs" — is a short module that imports the parts you want from each.

The public `Array` and `Group` classes are thin facades. An `Array` holds a metadata document, a store, an engine, and a codec registry, and delegates each method to the engine. Switching backends means swapping one of those four pieces of state; the public API does not change.

## How the new shape solves the problems

| Problem | How the new shape resolves it |
|---|---|
| Integrating Zarrs/TensorStore requires a bespoke external package | An engine is a module of four functions. An integration with another implementation ships those four functions and inherits everything above the I/O — metadata handling, hierarchy traversal, key encoding — unchanged. |
| Parts of Zarr-Python cannot be used in isolation | The functional core splits cleanly into focused packages (e.g. `zarr-metadata`, `zarr-dtype`, `zarr-codec-spec`). Downstream tools depend on the parts they need. |
| Async/sync leaks into every layer | Async belongs only in the shell. The same engine has sync and async variants in separate modules; the core is identical for both. The recurring event-loop reentrancy bugs go away because the only place an event loop is involved is the shell. |
| Testing requires the whole stack | The core is pure functions over pure data. Tests run in milliseconds with no fixtures, no event loops, no stores. |
| Extension is painful | Codecs, chunk grids, key encodings, and data types become small additions to the core (pure data) plus, where needed, a small stateless object (codecs). No deep base classes to subclass, no internal hooks to override. |

## What this enables

**Performance parity for users without forcing a library switch.** A user who needs Zarrs' speed selects a different engine instead of switching libraries. They keep Xarray, Dask, napari, and every other Zarr-Python integration. The high-performance use case stops being a reason to leave the ecosystem.

**Smaller, focused packages the broader ecosystem can adopt.** Tools that only need to parse metadata, compute chunk layouts, or validate a Zarr V3 document can depend on a small package without pulling in numpy, fsspec, and numcodecs. This is exactly what `yaozarrs`, `ngff-zarr`'s metadata path, and `mesh-n-bone`'s direct-JSON approach are already reaching for. It unlocks adoption in places where the current dependency footprint is prohibitive (lightweight services, embedded uses, JavaScript-side validators that today re-implement parsing in another language).

**Faster pace of feature work.** Most new features — new codecs, new chunk grids, new key encodings, new data types — become pure-data additions to the core, tested without I/O. Less infrastructure per change, more changes per release.

**Cleaner integration with downstream libraries.** Dask, Xarray, and similar projects that today reach into Zarr-Python internals to optimize specific patterns can target the core's pure functions instead of brittle internal APIs.

**A path to the packaging goals already articulated in the README.** The motivation for splitting Zarr-Python into multiple packages is the same motivation as the functional-core refactor: model the real dependency relationships, support partial adoption, harden conceptual boundaries.

## What this is not

- **Not a public API change.** The `zarr.open`, `zarr.create_array`, `Array[...]`, `Group[...]` surfaces stay where they are. Existing user code keeps working.
- **Not a function-by-function API design.** This document argues the direction and the shape of the solution. Concrete signatures and module layouts are deferred to follow-on proposals.
- **Not a redesign of the store layer.** The existing stores proposal stands; we add only the serialization capability that lets stores cross language boundaries.
- **Not a single-release push.** The refactor is incremental and staged. The functional core can be extracted and tested alongside the existing internals; engines can be added one at a time; the public facade can migrate to delegating into the core gradually, with no flag day.

## Relationship to existing proposals

- [`proposals/stores-api.md`](./stores-api.md) — preserved as-is, with one addition: a `Serializable` capability and a versioned store declaration data format. The conformance suite gains a matching specification.
- [`proposals/stores-conformance.md`](./stores-conformance.md), [`proposals/stores-caching.md`](./stores-caching.md), [`proposals/stores-range-coalescing.md`](./stores-range-coalescing.md), [`proposals/stores-transactional.md`](./stores-transactional.md), [`proposals/stores-wrappers.md`](./stores-wrappers.md) — preserved unchanged. The functional core sits above the store layer and does not touch its design.
- README sections on **Codecs**, **Packaging**, **Concurrency**, and **Data types** — the functional core enables the directions argued in each of these sections. The codec API rewrite folds in naturally (codecs become small, stateless, capability-bundled objects); the packaging split becomes implementable because the core has clean package-shaped seams; the concurrency story simplifies because async lives only in the shell; new data type support becomes a pure-data addition.

## Open questions for follow-on work

- **Engine selection ergonomics at the public surface.** Explicit keyword argument, URL-scheme routing, global configuration, or some combination — to be specified when drafting the facade layer.
- **Format and version of the store declaration.** Likely a typed dataclass with a JSON schema; alignment with obstore's URL+config pattern worth exploring.
- **Migration sequencing.** Which core pieces extract first; whether the existing `Array`/`AsyncArray` pair stays or collapses into a single facade with sync and async methods; how long deprecation windows last. To be addressed in the implementation plan.
