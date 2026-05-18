# Zarr-Python Planning

Plans for the future of Zarr-Python.

## Who we are

This document is written by the [zarr-python core developers](https://github.com/zarr-developers/zarr-python). The proposals below are our shared assessment of the project's direction; the work to deliver them will run through the normal Zarr-Python development process — public discussion on the proposals, PRs against the [`zarr-developers/zarr-python`](https://github.com/zarr-developers/zarr-python) repository, and the existing release cadence.

## Audience

This planning document is for two audiences. The first is Zarr developers and contributors evaluating where the project should go next. The second is funders, institutional partners, and stakeholders who care about Zarr's success in the scientific Python ecosystem but don't follow the codebase day-to-day. The README is the entry point for both; individual proposal documents under `proposals/` go deeper for developers and reviewers.

## Why Zarr-Python exists

A fair question to start with: **if [TensorStore](https://github.com/google/tensorstore) already has Python bindings, and [zarrs-python](https://github.com/zarrs/zarrs-python) exists, why should Zarr-Python continue to be a project at all?** Why not declare it superseded by the compiled-language implementations, build thin Python wrappers around them, and move on?

The honest answer has two parts.

**A Python-first codebase is itself a strategic asset for the Zarr ecosystem.** The overwhelming majority of scientific data work happens in Python: Xarray, Dask, napari, anndata, scverse, Pangeo, every major bioimaging and geospatial stack. The developers building those tools read Python, write Python, and extend their tools in Python. When a Zarr-related feature is needed — a new convention layer for OME-NGFF, a custom store backend for a lab's storage system, a domain-specific validator, a notebook-side debugging tool — the cost of writing it in Python is hours; the cost of writing it in Rust or C++ with bindings is weeks to months. A Python-native implementation is the substrate that lets the *long tail* of Zarr-using projects extend Zarr cheaply. Conceding the Python-native layer means conceding that long tail to ad-hoc per-project workarounds (which is what we already see — `yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr` all routed around `zarr-python` for various reasons; the [functional-core proposal](./proposals/functional-core.md#parts-of-zarr-python-cannot-be-used-in-isolation) walks through this evidence).

The institutional users whose work depends on Zarr-Python are concrete and named: **NASA** (Zarr is an approved [ESDS storage convention](https://www.earthdata.nasa.gov/about/esdis/esco/standards-practices/zarr-storage-specification-v2); JPL's ITS_LIVE, GES DISC, NSIDC publish cloud-native archives via Zarr-Python), **ECMWF / Copernicus** (the ERA5 reanalysis — ~2 PB, the dominant ML weather training dataset — is published as Zarr and consumed via Zarr-Python; the Anemoi ML-weather stack declares Zarr-Python as a dependency), **NOAA** (Zarr is named in the NOAA Open Data Dissemination cloud-format strategy), **NIH BRAIN Initiative** (the [DANDI Archive](https://www.dandiarchive.org/) and [NWB](https://www.nwb.org/) ecosystem ship Zarr-Python as a first-class storage backend via `hdmf-zarr`), the **OME consortium** (EMBL-EBI, HHMI Janelia, Allen Institute — OME-NGFF / OME-Zarr is the international bioimaging standard, and `ome-zarr-py` is built directly on Zarr-Python), **scverse** (the Python single-cell omics ecosystem — `anndata` and `spatialdata` declare Zarr-Python as a dependency), **Pangeo** (the NSF/NASA-funded geoscience community whose entire stack rests on Zarr-Python via Xarray and Dask), and **Earthmover** (the commercial company building [Icechunk](https://icechunk.io/) — VC-backed and built directly on Zarr-Python). These are not collateral mentions; in many of these projects, a Zarr-Python API break would force a coordinated downstream response across the institution's engineering teams. Conceding the Python-native layer means conceding the ability for that long list of organizations to continue extending Zarr through Python — which is the language they actually use.

**TensorStore and zarrs are complementary, not competitive.** They are excellent at what they do — high-performance, compiled-language IO with deep optimizations no Python implementation can match. The right relationship between Zarr-Python and them is not "pick one"; it is "Python developers should get both, with no migration cost." A user who needs TensorStore's throughput on a specific workload should not have to abandon Xarray, Dask, every domain-specific Zarr reader, and every store backend `zarr-python` supports. The [engine architecture in performance.md](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines) is the structural commitment to this: `zarr-python` ships native bindings for `zarrs` and TensorStore as alternative engines, selectable with a one-line keyword argument. Users keep the surface; the engine swaps. The competitive narrative inverts — TensorStore and zarrs become *amplifiers* of the Zarr-Python ecosystem rather than off-ramps from it.

TensorStore in particular already owns a Zarr-shaped segment that Zarr-Python does not currently serve: **large-scale distributed checkpointing for ML training**. On the JAX side, Google's [Orbax](https://github.com/google/orbax) (the de facto JAX checkpointing library) backends onto TensorStore; so do Apple's [AXLearn](https://github.com/apple/axlearn), Stanford/Marin's [Levanter](https://github.com/marin-community/levanter), and the JAX team's own example repos. On the PyTorch side, NVIDIA's [Megatron-LM](https://github.com/NVIDIA/Megatron-LM) and [NeMo](https://github.com/NVIDIA/NeMo) ship a `dist_checkpointing/strategies/tensorstore.py` backend; [MLCommons training benchmarks](https://github.com/mlcommons/training) use TensorStore in the GPT-3/Megatron reference. The engine-wrapping work is what lets those workloads use Zarr-Python's API surface (and the rest of Zarr-Python's ecosystem) while delegating IO to TensorStore — closing a documented adoption gap rather than chasing a hypothetical one.

This is the both-and answer. We do not have to choose. **We engineer Zarr-Python to be the best pure-Python Zarr implementation available, *and* to be the best wrapper around the compiled-language implementations.** The pure-Python mode is what makes the library extensible by the Python ecosystem; the compiled-language engines are what give that ecosystem access to native-throughput IO when the workload demands it. Most users will live on the pure-Python path because most workloads do not need native throughput — interactive analysis, dashboards, single-machine science pipelines, hierarchies opened on a notebook. The users who *do* need native throughput (cloud-scale ML training, petabyte-scale climate-model post-processing, distributed checkpointing for large language models) pay the FFI dependency cost and get the speedup without losing anything else. The Phase 1 performance work below is what makes the "most workloads don't need native throughput" claim true in practice; if that work stalls, the both-and framing collapses.

For this to be a credible story, the pure-Python mode has to actually *be* good — performant, extensible, well-shaped. That is what the rest of this document is about. If we fail at the pure-Python work, the "both-and" answer collapses into "use TensorStore, ignore us," and we lose the Python-native layer that the ecosystem depends on. The proposals below are the technical commitments that make the pure-Python mode worth keeping.

## Background

_at the time of this writing, the current released version of Zarr-Python is 3.1.6_

The [3.0 release](https://github.com/zarr-developers/zarr-python/releases/tag/v3.0.0) of Zarr-Python featured a total redesign of the internals of the library. The new design was shaped by the following goals:
- Full support for Zarr [V2](https://zarr-specs.readthedocs.io/en/latest/v2/v2.0.html) and [V3](https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html) storage formats.
- Storage APIs that were ergonomic for high-latency storage (e.g., cloud object storage).
- Backwards compatibility with Zarr-Python 2.x, where possible.

We largely achieved those goals: compared to Zarr-Python 2.18 (the last release in the 2.x series), Zarr-Python 3.x has infinitely better support for the Zarr V3 format and vastly improved IO performance for cloud storage backends. 

We hit these marks while retaining a very high degree of backwards compatibility with the 2.x APIs. Some Zarr-Python consumers are still migrating to 3.x, but large downstream libraries like `Xarray` and `dask` managed the transition relatively easily.

Over 1 year since the 3.0 release, we feel comfortable stating that the 2.x -> 3.0 transition is effectively resolved.

So what's next for `Zarr-Python`?

## Zarr 4.0 goals

Our old Zarr-Python 3.0 goals are accomplished. That means it's time to define Zarr-Python 4.0 in terms of some new goals. 

If the 3.0 goals could be sloganized as "Migrate to Zarr V3, and improve cloud storage support", we propose the following slogan for the 4.0 goals: "Support a Zarr-based Python ecosystem for chunked arrays". The Zarr-Python project should be *foundational* for the increasingly large number of Python packages that work with data in the Zarr format. We want to position Zarr Python packages as viable core components for *any* project that works with Zarr data.

To reach this we should push in the following directions:

- Give Zarr-Python users excellent performance, out of the box. 
- Make Zarr-Python APIs ergonomic and useful for developers. 
- Expand our scope to cover vital quality-of-life routines like data copying, rechunking, and the like.
- Support the growth of Python tools across all levels of the Zarr stack.  
- Accelerate the implementation of new codecs, chunk grids, chunk key encodings, etc. 

## Why now

Two things make 4.0 the right moment for this work — one a risk, one an asset — and together they argue for moving now rather than later.

**The risk: under-investment in the pure-Python mode collapses the both-and framing.** The "pure-Python path is good enough that the FFI engines are an optimization, not a necessity" claim is load-bearing for the strategic case above. If Zarr-Python is too slow to improve performance, add features, and make APIs better, users will adopt other Python tools like Tensorstore, or simply not use Zarr at all. The inertia from Dask, Xarray, and the named institutional users above is real but can change *very quickly* if someone motivated stands up a cleaner, faster, better Python-based Zarr library. We should run that cleaner, faster, better library.

**The asset: two independent reference implementations have already answered the hard architectural questions.** [Zarrs](https://github.com/zarrs/zarrs) (Rust) and [TensorStore](https://github.com/google/tensorstore) (C++/Google) were written by different teams, in different languages, against different design constraints, with no coordination between them. And they have *converged* on the same architectural patterns — sync-first codec APIs with async as an opt-in adapter; per-codec advertised concurrency budgets; sharded reads with adaptive whole-shard-vs-coalesced strategies; pre-allocated decode buffers; per-key in-flight deduplication; conditional reads with ETag-style generations; pipeline caches inserted between codecs that lack partial-decode support. When two independent reference implementations agree on something this specific, the case for adopting it is much stronger than any one team's design instincts. We do not have to invent; we have to translate.

That translation work has been **vastly accelerated by large language models.** Reading a 200-thousand-line C++ codebase and a 50-thousand-line Rust codebase to extract their architectural patterns — what each library does, why it does it, how the pieces compose, what's load-bearing vs. incidental — is exactly the kind of cross-codebase synthesis that used to take weeks of senior engineering time and now takes hours. Most of the comparative analysis cited in the proposals below ([codecs.md](./proposals/codecs.md), [stores.md](./proposals/stores.md), [performance.md](./proposals/performance.md)) was assembled with LLM-driven code reading, source-grep, and synthesis loops. The technical work — designing the new APIs, writing the migration plans, building the implementations — is still ours to do, and the LLM-assisted findings have been verified against the source by hand for the load-bearing claims. But the *discovery* phase, which historically dominated the cost of a project like this, has collapsed to a fraction of what it once was.

The combination — a real risk if we don't move, plus two reference implementations to learn from and tools that let us extract their lessons cheaply — is why a project this ambitious is realistic on a 4.0 timeframe rather than being a multi-year research effort. The proposals below reflect the *current* state of that translation: the substantial themes (Functional Core, Hierarchy Layer, Codecs, Stores, Lazy Indexing, Performance, Observability, Device-agnostic IO, Data types) are fleshed out; one stub (Consolidated metadata) remains as a placeholder for the next pass and is not blocked on discovery, only on writing time.

Two pieces of Phase 0 are already real, not aspirational. The first focused package from the proposed split — [`zarr-metadata`](https://github.com/zarr-developers/zarr-metadata) ([on PyPI](https://pypi.org/project/zarr-metadata/), spec-defined metadata types for Zarr V2 and V3) — has been spun out and published as a standalone project. The [`IndexTransform` algebra](https://github.com/zarr-developers/zarr-python/pull/3906) that lazy indexing is built on is in flight as a PR against `zarr-python`. The Phase 0 work is partly already done; the rest is on the same trajectory.

## Why this work is overdue

The V3 work was a necessity-driven rewrite under hard backwards-compatibility constraints — support V3, do not break Xarray, Dask, or the long tail of downstream tools. The result made V3 work and preserved the user-facing API, but inherited many of the structural patterns of the V2 implementation it replaced. The library has never had a release whose primary goal was the *shape* of the internals.

That trade-off — features and compatibility first, internals later — was defensible for a long time. As the ecosystem matures, the calculus has flipped. The dependency-footprint workarounds documented in the proposals below, the bespoke external package required for Zarrs integration, the recurring bugs in path handling and async layering all share one root cause: the internals were never designed, they accreted. The accumulated cost of working around them now exceeds the cost of paying them down.

The 4.0 work proposed here is that overdue investment.

### What we do and don't commit to for backwards compatibility

A 4.0 release is a breaking-change release. We are **not** making a blanket backwards-compatibility commitment for the public API: methods will be renamed, signatures will change, deprecated patterns will be removed, the codec and store APIs will be rewritten. The 2.x → 3.x transition was carried out under hard backwards-compatibility constraints; the 4.0 transition is the one where we get to fix what those constraints prevented us from fixing.

What we *do* commit to:

- **Conformance with community standards.** Where there is a relevant cross-language standard, Zarr-Python 4.0 conforms to it: the [Python Array API](https://data-apis.org/array-api/) at the array surface; the Zarr V3 spec and its extensions at the storage layer; OpenTelemetry for tracing; standard buffer-protocol and device-interop conventions (CUDA Array Interface, DLPack) for device-agnostic IO. Compatibility with the *standard* is a stronger guarantee than compatibility with a previous version of our own API, because it interoperates across the broader ecosystem.
- **Functional coverage.** Anything you can do in Zarr-Python 3.x you can do in Zarr-Python 4.x — typically *better*, sometimes through a renamed API, but the underlying capability is preserved. We will not silently remove the ability to read or write any Zarr-format data that 3.x supports. Where the API changes, the migration is documented and the change is justified by a concrete improvement.
- **A deprecation window.** Renames and removals land through one or more deprecation cycles. The aggressive default-flip in lazy indexing (eager → lazy) is the most visible example: opt-in lazy in 4.0, default flip in a later 4.x release, eager removal in 5.0. Downstream libraries (Xarray, Dask, napari) get release windows to absorb each change before the next one lands.

The honest framing: **the API is going to change, and we believe the changes are worth the cost.** Downstream maintainers should expect to update their code; the 4.0 transition is not a no-op for them. We commit to making each change worthwhile and to giving downstream time to adapt — not to preserving every method signature.

## What could derail this

Two scenarios would invalidate the case above. Both are real; neither is hypothetical.

**Zarr is supplanted by a new data format emerging from the ML world.** The format-design pressure from ML workloads — checkpoint-shaped IO, tensor-native types, GPU-resident buffers, single-writer atomicity — is producing new and competing storage formats faster than at any point in Zarr's history. If one of them displaces Zarr as the default for large-scale scientific arrays, the institutional dependencies catalogued below shift onto a different substrate and the 4.0 work becomes maintenance of a fading library. The mitigation is in the proposal itself: the 4.0 work explicitly targets the gaps (ML dtypes, device-agnostic IO, distributed checkpointing via TensorStore-engine wrapping) that would make a competing format necessary. If we ship Phase 0 and Phase 1, Zarr stays competitive on the workloads that would otherwise drive a replacement.

**Zarr-Python is abandoned in favor of TensorStore, zarrs, or a more agile Python library.** This is the failure mode the both-and framing is designed against. If Zarr-Python's pure-Python mode is too slow, too awkward, or too hard to extend, performance-sensitive users move to TensorStore via its Python bindings, and the long tail of small Zarr-using tools either follows or routes around Zarr-Python ad hoc (which is already happening — `yaozarrs`, `mesh-n-bone`, etc.). The mitigation, again, is the work itself: the proposals deliver the performance, extensibility, and ergonomics that make Zarr-Python worth choosing over the alternatives, and the engine-wrapping work means users who *do* need TensorStore's throughput get it without leaving the Zarr-Python ecosystem. If we *don't* ship Phase 1 — the pure-Python performance work — the alternative-library scenario becomes likely within one or two release cycles.

Both risks point at the same conclusion: the 4.0 work is what keeps Zarr-Python relevant. Not doing it is not the safe option.

## Who funds and depends on this work

Zarr-Python is not a hobby project, and the institutions whose work depends on it are not abstract. A short list of the named users and funders, to make the stakes concrete:

**Institutional users with code-visible Zarr-Python dependencies:**

- **Earthmover** (commercial; VC-backed, $7.2M seed in 2025) — [Icechunk](https://github.com/earth-mover/icechunk), the transactional storage engine for Zarr, ships Zarr-Python integration as a product surface. Direct contributors to Zarr-Python.
- **NVIDIA** — [`earth2studio`](https://github.com/NVIDIA/earth2studio) (AI weather/climate framework) and [`physicsnemo`](https://github.com/NVIDIA/PhysicsNeMo) (Physics-ML) declare Zarr-Python as a dependency.
- **ECMWF** (intergovernmental EU weather agency) — the [Anemoi](https://github.com/ecmwf/anemoi-datasets) ML-weather stack (`anemoi-datasets`, `anemoi-inference`, `anemoi-registry`, `climetlab`, `earthkit-data`) all declare Zarr-Python deps.
- **Google Research** — [`google-research/arco-era5`](https://github.com/google-research/arco-era5) (the canonical analysis-ready ERA5 publication), [`weatherbench2`](https://github.com/google-research/weatherbench2) declare Zarr-Python deps; the [canonical CMIP6 Zarr archive](https://cloud.google.com/blog/products/data-analytics/new-climate-model-data-now-google-public-datasets) is hosted on Google Cloud.
- **Microsoft** — [`microsoft/ltp-megatron-lm`](https://github.com/microsoft/ltp-megatron-lm) (a Microsoft fork of Megatron-LM) ships a Zarr-Python distributed-checkpointing strategy at `megatron/core/dist_checkpointing/strategies/zarr.py`; [`microsoft/AIforEarthDataSets`](https://github.com/microsoft/AIforEarthDataSets) and [`microsoft/nova-agent`](https://github.com/microsoft/nova-agent) (whole-slide image processing) also import Zarr-Python directly. [Planetary Computer](https://planetarycomputer.microsoft.com/) hosts Zarr datasets at scale.
- **OME consortium** (EMBL-EBI, HHMI Janelia, Allen Institute, German BioImaging, Glencoe Software, others) — [`ome-zarr-py`](https://github.com/ome/ome-zarr-py), the reference implementation of the OME-NGFF / OME-Zarr bioimaging standard, declares Zarr-Python as a dependency. HHMI Janelia and Allen Institute for Neural Dynamics each maintain ~10+ production pipelines importing Zarr-Python directly.
- **DANDI Archive / Neurodata Without Borders** (NIH BRAIN Initiative) — the [`dandi-cli`](https://github.com/dandi/dandi-cli) and [`hdmf-zarr`](https://github.com/hdmf-dev/hdmf-zarr) ship Zarr-Python integration as the NIH-funded neurophysiology data backend.
- **scverse** — the Python single-cell omics ecosystem; [`anndata`](https://github.com/scverse/anndata) and [`spatialdata`](https://github.com/scverse/spatialdata) declare Zarr-Python deps.
- **NumFOCUS / PyData** — [Xarray](https://github.com/pydata/xarray), the geoscience array library that every Pangeo-style pipeline routes through, declares Zarr-Python as a dependency; [Dask](https://github.com/dask/dask) and [napari](https://github.com/napari/napari) too.
- **Pangeo community** (NSF/NASA-funded; LDEO/Columbia, NCAR, others) — [`rechunker`](https://github.com/pangeo-data/rechunker) and the broader Pangeo Forge / xarray-Dask-Zarr stack are built on Zarr-Python.
- **CarbonPlan** (climate-impact nonprofit), **Development Seed** (geospatial consultancy maintaining [`titiler`](https://github.com/developmentseed/titiler) and `obstore`), **Glencoe Software** (commercial bioimage tooling) all ship Zarr-Python-dependent tools.

**Historical and active funders of Zarr-Python and the Zarr ecosystem:**

- **Chan Zuckerberg Initiative EOSS** (Essential Open Source Software for Science) — direct grant to the Zarr project; separate grants to the scverse / AnnData / CELLxGENE stack that depends on it.
- **NSF** — funds Pangeo, the LEAP Science and Technology Center at Columbia, and EarthCube / Pangeo Forge work.
- **NASA ACCESS program** — funds Pangeo-ML; NASA Earthdata Cloud and NASA HEC adopt Zarr as an officially approved storage convention.
- **NIH BRAIN Initiative** — funds DANDI and the NWB ecosystem.
- **Wellcome Trust / MRC** (historical) — funded the original Zarr work at the Oxford Big Data Institute, where Zarr was created for malaria genomics.
- **Earthmover** (commercial, ongoing) — VC-backed funding flowing into Zarr-Python and Icechunk maintenance.
- **NumFOCUS** — fiscal sponsor of the Zarr project.

The picture is unusual: a single open-source library that anchors **published petabyte-scale climate archives, an international bioimaging standard, an NIH-funded neurophysiology archive, a commercial product, and substantial parts of the Python ML-physics stack at NVIDIA, Apple, Google, and ECMWF**. Each of these depends on Zarr-Python remaining good. The 4.0 work is the investment that lets it keep being good.

## The Zarr Stack

There are levels of Zarr support. Some applications, like validators for domain-specific Zarr conventions, only need to read Zarr metadata documents. They don't need to read and write chunks. Other applications might only need read-only access to array metadata and the stored chunks, and nothing else. Tensorstore only supports reading and writing arrays, but not the `attributes` field of Zarr metadata, and it doesn't support any operations on Zarr groups. Zarr Python supports all types of operations -- reading and writing arrays and groups -- but doesn't support exactly the same set of data types and codecs as other "complete" implementations. 

The story here is that different applications need to do different operations with Zarr data. This is something we *learned* from seeing how different tools and communities leverage Zarr. Let's call a set of tools that supports these various operations a "Zarr stack". 

Concretely, the levels of the stack — from most abstract to most concrete — look something like this:

1. **Conventions** — domain-specific schemas built on top of Zarr (OME-NGFF, GeoZarr, anndata-zarr). Consumers: validators, format-specific readers, the `yaozarrs` / `ome-zarr-models-py` line of work.
2. **Groups** — Zarr hierarchies, traversal, group-level attributes.
3. **Arrays** — the user-facing array object, plus indexing and slicing. In 4.0 this level grows [lazy indexing and Array API conformance](./proposals/lazy-indexing.md): an opt-in `array.lazy[...]` accessor on the existing `Array` class returns a lazy view, and the query planner sits here. The default of bare `array[...]` flips to lazy in a later 4.x release; the eager path is removed in 5.0. There is no new array type — the migration runs on a single `Array` class whose `__getitem__` semantics evolve across releases.
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

The mechanism for this re-shaping is the two foundational pieces of work described in the next two sections: the **functional-core refactor** (pure-data layer) and the **formal hierarchy layer** (typed verbs over the store API). Together they extract the pure-data and pure-function parts of each stack level out of the monolith and into independently usable pieces.

## Foundation: a functional core

The first foundational piece is a refactor of Zarr-Python's internals around a *functional core* — pure data structures and pure functions for the algebra of Zarr (metadata, chunk layouts, slice planning, codec walking) — with the side-effecting protocols (stores, codecs) at the edges. This is itself an internal change, not something user-facing. It is what makes the per-level package split (`zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`) implementable, and it unlocks the high-performance integration story for Zarrs and TensorStore by providing a clean substrate for engine-level pluggability.

→ [proposals/functional-core.md](./proposals/functional-core.md)

## Foundation: a formal hierarchy layer

The second foundational piece is a formal **hierarchy layer** that sits between the store API (key-agnostic bytes) and the user-facing `Array` / `Group` facade — corresponding to the boundary between the Stores level (6) and the Groups/Arrays levels (2–3) above. Today the hierarchy layer exists implicitly — it's whatever `Array` and `Group` happen to do — but it's not named, not specified, and not engine-pluggable in the way the codec layer and the store layer are. This proposal makes it a typed surface: a small set of verbs (`read_array_metadata`, `write_chunk`, `list_children`, `read_selection`, ...) that take a store and a hierarchy-shaped intent. Alternative engines implement the verbs end-to-end (not just chunk reads); hierarchy-aware caching wraps them; the chunk-introspection user surface in [observability.md](./proposals/observability.md) is the verbs exposed on `Array`. Naming this layer resolves several abstraction ambiguities that have been leaking across the proposal set, most visibly in the cache-layering question.

→ [proposals/hierarchy-layer.md](./proposals/hierarchy-layer.md)

## What we're changing

Each theme below has a corresponding proposal document under `proposals/`. Substantial themes (Functional Core, Hierarchy Layer, Codecs, Stores, Lazy Indexing, Performance, Observability, Device-agnostic IO, Data types) have full proposals; the rest are stubs awaiting expansion.

### Codecs

The codec API is wrapped in an unnecessary async layer (a profiling-hotspot), defines abstract base classes that are not actually abstract, bakes batching into every encode/decode signature, and forces output allocation even when the caller has a buffer ready. Many Zarr V2 codecs still have no V3 equivalent. Rewrite the codec API as a small, stateless capability bundle decoupled from the rest of `zarr-python`, with clear paths for migrating existing codecs, integrating Zarrs/TensorStore at the codec level, and reducing the role of Numcodecs.

→ [proposals/codecs.md](./proposals/codecs.md)

### Stores

The store abstraction conflates lifecycle, path handling, sync/async, capability advertisement, and read-only semantics into one inheritance hierarchy, and the resulting maintenance friction has produced a recurring stream of regressions. Redesign stores as composable capability protocols (Get, Put, List, ...) with composable wrappers (caching, range coalescing, retries), a sync/async family split, transactional semantics, and a shared conformance suite that backends and wrappers parameterize.

→ [proposals/stores.md](./proposals/stores.md) (with tier-3 specs linked from there)

### Performance

A cross-cutting theme that ties the codec, store, and functional-core work into one performance story. Typed library-owned concurrency resources (`ComputeConcurrency`, `IoConcurrency`); synchronous codec encode/decode; range coalescing; pre-allocated decode buffers; in-flight request deduplication; ETag-style revalidation; a unified `AsyncCache`-shaped caching substrate with sensible defaults; an adaptive whole-shard-vs-coalesced read strategy; the concurrency-and-correctness contract; and pluggable high-performance backends via the engine boundary (Zarrs, TensorStore). The integrated story lives in this one proposal so reviewers and stakeholders can read about end-to-end speedups in one place.

→ [proposals/performance.md](./proposals/performance.md)

### Lazy indexing

`Array.__getitem__` performs IO eagerly and returns NumPy, which makes Zarr arrays the odd one out among modern array libraries, blocks participation in the Python Array API ecosystem, and forces every performance-sensitive user through Dask to recover basic IO optimizations like deduplication, slice fusion, and range coalescing. Add an opt-in `array.lazy[...]` accessor in 4.0 backed by a stable coordinate-mapping algebra ([PR open](https://github.com/zarr-developers/zarr-python/pull/3906)), flip the default of bare `array[...]` to lazy in a later 4.x release, and conform to the Array API standard alongside. A small query planner turns chained selections into a single IO plan before any chunks are fetched. No new array type is introduced — the codebase carries one `Array` class throughout.

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

## Roadmap

The proposals above describe *what* changes; this section describes *when* and *in what order*. Work is grouped into four phases. Each phase has a clear purpose, depends on the phase before it, and produces value on its own — there is no big-bang release where everything ships at once.

A reader who wants the granular per-proposal sequencing should follow the links into the proposals themselves; each substantial proposal has its own migration / sequencing section. What follows is the release-shaped view of how those plans compose.

### Phases mapped to releases

| Phase | Release target | Approximate scope |
|---|---|---|
| **Phase 0** — Foundation | **4.0** | functional-core refactor, per-level package split, stores API rewrite, formal hierarchy layer, `IndexTransform` algebra ([zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906), already in flight) |
| **Phase 1** — Performance and concurrency | **4.x** (incremental minor releases on top of 4.0) | codec API rewrite, typed concurrency resources, cache substrate, store-layer range coalescing and conditional reads |
| **Phase 2** — User-facing surface | **4.x** (continuing) | Array API conformance + query planner, device-agnostic IO, observability, missing APIs (explicit constructors, typed exceptions, rich reprs, etc.). The default flip from eager to lazy `__getitem__` ships in a Phase 2 release. |
| **Phase 3** — Ecosystem | **4.x → 5.0** | ML dtype support, engine wrappers for `zarrs` and TensorStore, Arrow integration investigation. The 5.0 release boundary is where the eager `__getitem__` path is removed (per [lazy-indexing.md § Migration](./proposals/lazy-indexing.md#migration)). |

Phases are not gated on calendar dates; the work ships when it's ready. The release column above describes which *kind* of release each phase corresponds to (a major 4.0 vs incremental 4.x minor releases vs the 5.0 break), not when.

The phases below describe the per-work-package contents of each release tier.

### Phase 0 — Foundation (lands first; required by everything else)

The structural work that the rest of the plan depends on. Until this lands, the other phases can be designed in parallel but cannot ship.

**Done when**: the functional-core refactor has landed, the four focused packages (`zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`) are published ([`zarr-metadata`](https://pypi.org/project/zarr-metadata/) is shipped; the other three follow), the new stores API is in `zarr-python` (with backends migrated and the conformance suite green), the hierarchy-layer verbs are defined and exported, and the `IndexTransform` algebra from [zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906) is merged. At that point `zarr-python` has the clean seams that Phases 1–3 build on, and downstream tools that only need a subset of Zarr functionality can depend on the focused packages instead of pulling in the whole library.

1. **Functional-core refactor** — extract the pure-data layer (metadata, chunk-addressing math, codec configurations) from the side-effecting layer (stores, codec execution, IO). Establishes the engine boundary that lets alternative engines plug in. → [proposals/functional-core.md](./proposals/functional-core.md)
2. **Per-level package split** — `zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype` as focused packages, with `zarr-python` as the facade that re-exports them and ships the default Python engine. **First package already shipped**: [`zarr-metadata`](https://github.com/zarr-developers/zarr-metadata) is published on [PyPI](https://pypi.org/project/zarr-metadata/) and contains the spec-defined metadata types for Zarr V2 and V3. The remaining three packages follow the same pattern. → [proposals/functional-core.md § Concrete packaging plan](./proposals/functional-core.md#concrete-packaging-plan)
3. **Stores API rewrite** — capability protocols, `ReadResult` / `PutResult` / `Generation`, the wrapper-based composition model, the `Serializable` capability that lets stores cross language boundaries. → [proposals/stores.md](./proposals/stores.md) (plus tier-3 specs)
4. **Formal hierarchy layer** — a small set of typed verbs (`read_array_metadata`, `write_chunk`, `list_children`, `read_selection`, ...) that compose the store API into hierarchy-shaped operations. The engine boundary is this verb set. The chunk-introspection user surface, hierarchy-aware caching, and several user-facing API gaps all consume it. → [proposals/hierarchy-layer.md](./proposals/hierarchy-layer.md)
5. **Lazy indexing — the composable coordinate-mapping algebra** — the foundational `IndexTransform` data structure that lazy `__getitem__` is built on. **Ahead of the rest of Phase 0**: the library is already in flight at [zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906). The 4.0 migration adds an opt-in `array.lazy[...]` accessor to the existing `Array` class; later 4.x flips the default of bare `array[...]`; 5.0 removes the eager path. No new array type is ever introduced — the codebase carries one `Array` whose `__getitem__` semantics evolve across releases. → [proposals/lazy-indexing.md](./proposals/lazy-indexing.md)

### Phase 1 — Performance and concurrency (lands on Phase 0)

The architectural patterns from `zarrs` and TensorStore that make the pure-Python mode credible. Each work package here can ship as a minor release once Phase 0 is in place.

**Done when**: the new codec API (sync-first, `decode_into`, `recommended_concurrency`, `PartialDecodeCapability`) is the supported surface; `ComputeConcurrency` and `IoConcurrency` are library-owned and the nested-semaphore multiplication bug is gone; the cache substrate is in place with the default policy from [performance.md § Default caching policy](./proposals/performance.md#default-caching-policy) (metadata-on, chunks-opt-in, in-flight dedup unconditional); store-layer range coalescing and ETag-based conditional reads work end-to-end. At that point the pure-Python performance gap with `zarrs` / TensorStore has narrowed to a small constant factor for most workloads, and the both-and framing — "the FFI engines are an optimization, not a necessity" — becomes defensible.

6. **Codec API rewrite** — sync-first encode/decode, single-element signatures, `decode_into` capability, `recommended_concurrency` advertisement, `PartialDecodeCapability` flags. → [proposals/codecs.md](./proposals/codecs.md)
7. **Typed concurrency resources + shrinking-value budget** — library-owned `ComputeConcurrency` / `IoConcurrency` pools; per-call budgets that strictly shrink as they descend the call stack; ends the "nested calls multiply concurrency" bug. → [proposals/performance.md § 1](./proposals/performance.md#1-concurrency-is-typed-library-owned-and-shared-across-nested-calls)
8. **Cache substrate** — one `AsyncCache`-shaped base, in-flight dedup unconditional; store-layer encoded-bytes cache via `Caching[S]`; hierarchy-layer metadata and decoded-chunk caches via `array.with_caching(...)` / `group.with_caching(...)`. → [proposals/performance.md § Caching](./proposals/performance.md#caching), [proposals/hierarchy-layer.md § How caching stratifies cleanly](./proposals/hierarchy-layer.md#how-caching-stratifies-cleanly)
9. **Store-layer range coalescing and conditional reads** — batched `get_partial_many`-shaped API, ETag-aware revalidation via `Generation`, the rest of the perf lessons §3–§9 from performance.md. → [proposals/performance.md](./proposals/performance.md), [proposals/stores-range-coalescing.md](./proposals/stores-range-coalescing.md)

### Phase 2 — User-facing surface (lands on Phase 1)

The work users see directly. Most of this becomes implementable once the Phase 0 + 1 substrate is in place.

**Done when**: `Array` is Array-API conformant; the query planner is wired into the lazy-indexing accessor and the default of bare `array[...]` has flipped to lazy; `read_into` / `decode_into` are exposed for caller-provided destinations and the Array API namespace selection works at materialization; the `Metrics` object plus OpenTelemetry auto-instrumentation produce useful traces across stores, codecs, caches, and the engine boundary; the chunk-introspection verbs are exposed on `Array` (unblocking VirtualiZarr and Kerchunk); the explicit-constructor family has shipped and the `mode=`-taking entry points are deprecated. At that point users see the 4.0 work directly: their code reads as Array-API code, their tooling sees Zarr operations in trace viewers, and the constructor and indexing patterns are the ones the rest of the scientific Python ecosystem uses.

10. **Array API conformance and the query planner** — `Array` grows into a full Array-API-conformant surface; the planner that consumes the `IndexTransform` algebra from Phase 0 turns chained selections into batched IO plans. (The underlying algebra and the opt-in accessor ship in Phase 0; the planner and conformance layer ship here, on top of the cache substrate and concurrency resources from Phase 1. The default flip happens here as well.) → [proposals/lazy-indexing.md](./proposals/lazy-indexing.md)
11. **Device-agnostic IO** — `read_into` / `decode_into` capabilities; Array API namespace selection at materialization. GPU support falls out for free; the more common application is pre-allocated CPU buffers. → [proposals/gpu.md](./proposals/gpu.md)
12. **Observability** — `Metrics` object, OpenTelemetry auto-instrumentation across the stack, chunk-level introspection APIs (the surface VirtualiZarr and Kerchunk need; mechanically the chunk verbs from the hierarchy layer surfaced on `Array`). → [proposals/observability.md](./proposals/observability.md)
13. **Missing APIs** — explicit constructors replacing `mode=`; typed exceptions; rich reprs; `__truediv__` group traversal; `__dask_tokenize__`; ZEP 8 URLs; the rest of the user-facing convenience surface. → [proposals/missing-apis.md](./proposals/missing-apis.md)

### Phase 3 — Ecosystem (lands on Phase 2)

The work that extends the library's reach beyond what `zarr-python` ships directly.

**Done when**: ML dtypes (`bfloat16`, the `float8` variants, `int4`/`uint4`) round-trip through Zarr-Python end-to-end via `ml_dtypes`; the `zarrs` and TensorStore engines are available as opt-in dependencies and the engine-selection keyword argument works on `zarr.open(...)`; the Arrow-integration investigation has produced either a working `array.to_arrow()` materialization for nullable / vlen / nested types or a deferred-with-reasoning note explaining what we learned. At that point the both-and framing is delivered: pure-Python users have a good library; FFI-engine users get TensorStore or `zarrs` performance without leaving the ecosystem; ML users find Zarr-Python a usable target for model checkpoints.

14. **ML dtype support** — `ml_dtypes` integration for `bfloat16`, `float8` variants, `int4`/`uint4`. Unblocks the ML community using Zarr for model checkpoints. → [proposals/data-types.md](./proposals/data-types.md)
15. **Engine wrappers for `zarrs` and TensorStore** — `zarr.engines.zarrs` and `zarr.engines.tensorstore` modules that implement the hierarchy verbs against the compiled-language implementations while preserving the `zarr-python` surface. Same `Array`, same `Group`, same Xarray/Dask/napari interop. → [proposals/performance.md § Wrapping zarrs and TensorStore as alternative engines](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines)
16. **Arrow integration investigation** — scoped exploration of how Arrow data structures (nullable types, vlen strings, nested types) integrate with Zarr-Python. The investigation itself is the 4.0 deliverable; what ships is determined by what we find. → [proposals/data-types.md § Investigation: Arrow as a substrate for non-numerical dtypes](./proposals/data-types.md#investigation-arrow-as-a-substrate-for-non-numerical-dtypes)

### What's out of scope for 4.0

- **Persisted hierarchy links** (HDF5-style soft/hard/external links that survive across processes). Would require Zarr-Python to define a new on-disk object format unilaterally; needs a Zarr Enhancement Proposal first. The `KvStack` composite store covers the session-time use cases. → [proposals/missing-apis.md § 1](./proposals/missing-apis.md)
- **Declarative hierarchy schema validation as a shipped feature** — likely a separate `zarr-schema` package layered on `zarr-metadata`, deferred to 4.x.
- **Cross-process shared-memory caching** — the substrate is designed not to foreclose it, but it doesn't ship in 4.0. → [proposals/performance.md § Caching-specific open questions](./proposals/performance.md#caching-specific-open-questions)
- **Consolidated metadata redesign as a substantial proposal** — currently a stub; expected to be expanded in a follow-up pass. → [proposals/consolidated-metadata.md](./proposals/consolidated-metadata.md)
- **Migration tooling for V2→V3** — the 2.x → 3.x transition is effectively resolved (per the Background section); we're not investing further in migration acceleration.

### How phases compose

The phases are not strict serial dependencies. Within a phase, items can ship in parallel; across phases, the dependency is *infrastructural* (Phase 1 requires the functional-core refactor's clean seams to exist, Phase 2 requires Phase 1's cache substrate and concurrency resources, etc.) but the *design* work for later phases can run alongside earlier-phase implementation.

What this means for a reader trying to estimate the work: Phase 0 is the gate. Once functional-core, packaging, and the stores API rewrite are landed, the rest of the plan ships incrementally as the team works through it. There is no "big push" needed; each subsequent work package can be a focused minor release.

The pure-Python performance work (Phase 1) is the load-bearing pitch for "Zarr-Python continues to be worth using as more than a compatibility shim." If we ship Phase 0 and stall on Phase 1, the [both-and framing](#why-zarr-python-exists) collapses. If we ship Phase 1, everything downstream is incremental on top.

## Next steps

The proposals above describe what we want to do. Three groups of readers can move this forward; the asks for each are different.

### If you fund open-source science software

Zarr-Python is the kind of foundational infrastructure project that produces outsized leverage when it's funded well — a single library that anchors petabyte-scale climate archives, an international bioimaging standard, an NIH-funded neurophysiology archive, a commercial product, and substantial parts of the Python ML-physics stack (see [Who funds and depends on this work](#who-funds-and-depends-on-this-work) for the specifics). The 4.0 work proposed here is the structural investment that lets the library keep being good for those users, and the kind of investment that the urgent feature work of normal release cycles rarely accommodates.

**If your organization funds open-source scientific software** — whether through a structured program (CZI EOSS, NSF CSSI, NumFOCUS, Wellcome) or through direct support — **the maintainers would value the chance to discuss this work with you.** A specific resource ask (FTE-quarters by phase, named deliverables, success metrics) is being prepared and is available on request. Reach out via [the project's GitHub org](https://github.com/zarr-developers) or to the maintainers directly.

### If you contribute to Zarr-Python or the surrounding ecosystem

The proposal set is sized for collective work, not one team. Specific entry points:

- **The lazy-indexing PR** ([zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906)) is in flight. Review, testing, and feedback are welcome now. It is the first piece of Phase 0 to ship.
- **The individual proposals** are the discussion venue for the rest of the work. Each substantial proposal — [functional-core.md](./proposals/functional-core.md), [stores.md](./proposals/stores.md), [hierarchy-layer.md](./proposals/hierarchy-layer.md), [codecs.md](./proposals/codecs.md), [performance.md](./proposals/performance.md), [lazy-indexing.md](./proposals/lazy-indexing.md), [observability.md](./proposals/observability.md), [gpu.md](./proposals/gpu.md), [data-types.md](./proposals/data-types.md) — has its own open-questions section. Comments and counter-proposals on those are the natural way in.
- **The smaller stubs** ([consolidated-metadata.md](./proposals/consolidated-metadata.md)) are placeholders awaiting expansion. Domain expertise on consolidated metadata is particularly welcome.
- **The Zarr V3 spec process** is where decisions that cross language boundaries land. Several open questions in the proposals above (persisted hierarchy links, ML dtype identifiers, the cache-tier conventions) ultimately need [Zarr Enhancement Proposals](https://zarr.dev/zeps/). Spec-side participation matters.

### If your project depends on Zarr-Python

The most useful thing downstream maintainers can do is **weigh in on the proposals while the design is still movable**. If your project's use of Zarr-Python would be affected by any of the work proposed here — the codec API rewrite, the stores rewrite, the lazy-indexing default-flip — read the relevant proposal and comment on it. The migration commitments below are written assuming downstream readiness; if there are workloads or patterns that don't fit, the planning phase is when to surface them.

The [`yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr`](./proposals/functional-core.md#parts-of-zarr-python-cannot-be-used-in-isolation) story (downstream projects that routed *around* Zarr-Python for various reasons) is exactly what the functional-core and packaging work aim to fix. If your project is on that list — explicitly or in spirit — the 4.0 work is partly for you, and your input on whether it actually solves your problem is load-bearing.
