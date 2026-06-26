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

This is the both-and answer. We do not have to choose. **We engineer Zarr-Python to be the best pure-Python Zarr implementation available, *and* to be the best wrapper around the compiled-language implementations.** The pure-Python mode is what makes the library extensible by the Python ecosystem; the compiled-language engines are what give that ecosystem access to native-throughput IO when the workload demands it. Most users will live on the pure-Python path because most workloads do not need native throughput — interactive analysis, dashboards, single-machine science pipelines, hierarchies opened on a notebook. The users who *do* need native throughput (cloud-scale ML training, petabyte-scale climate-model post-processing, distributed checkpointing for large language models) pay the FFI dependency cost and get the speedup without losing anything else. The Stream 1 performance work below — M0's range coalescing and request dedup plus M1's codec, concurrency, and cache work — is what makes the "most workloads don't need native throughput" claim true in practice; if that work stalls, the both-and framing collapses.

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

## Zarr-Python v4 goals

Our old Zarr-Python 3.0 goals are accomplished. That means it's time to define Zarr-Python **v4** in terms of some new goals. ("v4" names the body of work, delivered across many releases — see the [Roadmap](#roadmap) for how it maps to actual version numbers; it is not a single "4.0" feature release.)

If the 3.0 goals could be sloganized as "Migrate to Zarr V3, and improve cloud storage support", we propose the following slogan for the v4 goals: "Support a Zarr-based Python ecosystem for chunked arrays". The Zarr-Python project should be *foundational* for the increasingly large number of Python packages that work with data in the Zarr format. We want to position Zarr Python packages as viable core components for *any* project that works with Zarr data.

To reach this we should push in the following directions:

- Give Zarr-Python users excellent performance, out of the box. 
- Make Zarr-Python APIs ergonomic and useful for developers. 
- Expand our scope to cover vital quality-of-life routines like data copying, rechunking, and the like.
- Support the growth of Python tools across all levels of the Zarr stack.  
- Accelerate the implementation of new codecs, chunk grids, chunk key encodings, etc. 

## Why now

Two things make now the right moment for the v4 work — one a risk, one an asset — and together they argue for moving now rather than later.

**The risk: under-investment in the pure-Python mode collapses the both-and framing.** The "pure-Python path is good enough that the FFI engines are an optimization, not a necessity" claim is load-bearing for the strategic case above. If Zarr-Python is too slow to improve performance, add features, and make APIs better, users will adopt other Python tools like Tensorstore, or simply not use Zarr at all. The inertia from Dask, Xarray, and the named institutional users above is real but can change *very quickly* if someone motivated stands up a cleaner, faster, better Python-based Zarr library. We should run that cleaner, faster, better library.

**The asset: two independent reference implementations have already answered the hard architectural questions.** [Zarrs](https://github.com/zarrs/zarrs) (Rust) and [TensorStore](https://github.com/google/tensorstore) (C++/Google) were written by different teams, in different languages, against different design constraints, with no coordination between them. And they have *converged* on the same architectural patterns — sync-first codec APIs with async as an opt-in adapter; per-codec advertised concurrency budgets; sharded reads with adaptive whole-shard-vs-coalesced strategies; pre-allocated decode buffers; per-key in-flight deduplication; conditional reads with ETag-style generations; pipeline caches inserted between codecs that lack partial-decode support. When two independent reference implementations agree on something this specific, the case for adopting it is much stronger than any one team's design instincts. We do not have to invent; we have to translate.

That translation work has been **vastly accelerated by large language models.** Reading a 200-thousand-line C++ codebase and a 50-thousand-line Rust codebase to extract their architectural patterns — what each library does, why it does it, how the pieces compose, what's load-bearing vs. incidental — is exactly the kind of cross-codebase synthesis that used to take weeks of senior engineering time and now takes hours. Most of the comparative analysis cited in the proposals below ([codecs.md](./proposals/codecs.md), [stores.md](./proposals/stores.md), [performance.md](./proposals/performance.md)) was assembled with LLM-driven code reading, source-grep, and synthesis loops. The technical work — designing the new APIs, writing the migration plans, building the implementations — is still ours to do, and the LLM-assisted findings have been verified against the source by hand for the load-bearing claims. But the *discovery* phase, which historically dominated the cost of a project like this, has collapsed to a fraction of what it once was.

The combination — a real risk if we don't move, plus two reference implementations to learn from and tools that let us extract their lessons cheaply — is why a project this ambitious is realistic on the v4 timeframe rather than being a multi-year research effort. The proposals below reflect the *current* state of that translation: the substantial themes (Functional Core, Hierarchy Layer, Codecs, Stores, Lazy Indexing, Performance, Observability, Device-agnostic IO, Data types) are fleshed out; one stub (Consolidated metadata) remains as a placeholder for the next pass and is not blocked on discovery, only on writing time.

Two pieces of the foundation work are already real, not aspirational. The first focused package from the proposed split — [`zarr-metadata`](https://github.com/zarr-developers/zarr-metadata) ([on PyPI](https://pypi.org/project/zarr-metadata/), spec-defined metadata types for Zarr V2 and V3) — has been spun out and published as a standalone project. The [`IndexTransform` algebra](https://github.com/zarr-developers/zarr-python/pull/3906) that lazy indexing is built on is in flight as a PR against `zarr-python`. The foundation work is partly already done — and, tellingly, both pieces shipped (or are shipping) as *additive* changes against the 3.x line, not behind a major release. That is the template for the whole additive stream described in the [Roadmap](#roadmap).

## Why this work is overdue

The V3 work was a necessity-driven rewrite under hard backwards-compatibility constraints — support V3, do not break Xarray, Dask, or the long tail of downstream tools. The result made V3 work and preserved the user-facing API, but inherited many of the structural patterns of the V2 implementation it replaced. The library has never had a release whose primary goal was the *shape* of the internals.

That trade-off — features and compatibility first, internals later — was defensible for a long time. As the ecosystem matures, the calculus has flipped. The dependency-footprint workarounds documented in the proposals below, the bespoke external package required for Zarrs integration, the recurring bugs in path handling and async layering all share one root cause: the internals were never designed, they accreted. The accumulated cost of working around them now exceeds the cost of paying them down.

The v4 work proposed here is that overdue investment.

### What we do and don't commit to for backwards compatibility

This work changes the public API: methods will be renamed, signatures will change, deprecated patterns will be removed, the codec and store APIs will be rewritten. But — per the [stream model below](#roadmap) — those changes are *delivered additively first*, and the breaking *removals* are concentrated in a single late major release (4.0.0) rather than front-loaded into one big break. The 2.x → 3.x transition was carried out under hard backwards-compatibility constraints; this work is where we get to fix what those constraints prevented us from fixing — paying the cost down gradually across the 3.x line, not in one release.

What we *do* commit to:

- **Conformance with community standards.** Where there is a relevant cross-language standard, Zarr-Python v4 conforms to it: the [Python Array API](https://data-apis.org/array-api/) at the array surface; the Zarr V3 spec and its extensions at the storage layer; OpenTelemetry for tracing; standard buffer-protocol and device-interop conventions (CUDA Array Interface, DLPack) for device-agnostic IO. Compatibility with the *standard* is a stronger guarantee than compatibility with a previous version of our own API, because it interoperates across the broader ecosystem.
- **Functional coverage.** Anything you can do in Zarr-Python 3.x you can still do once the v4 work has landed — typically *better*, sometimes through a renamed API, but the underlying capability is preserved. We will not silently remove the ability to read or write any Zarr-format data that 3.x supports. Where the API changes, the migration is documented and the change is justified by a concrete improvement.
- **A deprecation window.** Renames and removals land through one or more deprecation cycles. The default-flip in lazy indexing (eager → lazy) is the most visible example: the opt-in `array.lazy[...]` accessor ships additively as a minor, any default flip follows only as a later deprecation (and only if Array-API conformance requires it; see the [decision point](#the-lazy-default-flip-is-a-decision-point-not-a-flagship)), and eager removal lands in the single late major (4.0.0) after the deprecation window. Downstream libraries (Xarray, Dask, napari) get release windows to absorb each change before the next one lands.

The honest framing: **the API is going to change, and we believe the changes are worth the cost.** Downstream maintainers should expect to update their code; this transition is not a no-op for them. But the cost is spread across the 3.x line and the concentrated breaking work is limited to one late major. We commit to making each change worthwhile and to giving downstream time to adapt — not to preserving every method signature.

## What could derail this

Two scenarios would invalidate the case above. Both are real; neither is hypothetical.

**Zarr is supplanted by a new data format emerging from the ML world.** The format-design pressure from ML workloads — checkpoint-shaped IO, tensor-native types, GPU-resident buffers, single-writer atomicity — is producing new and competing storage formats faster than at any point in Zarr's history. If one of them displaces Zarr as the default for large-scale scientific arrays, the institutional dependencies catalogued below shift onto a different substrate and the v4 work becomes maintenance of a fading library. The mitigation is in the proposal itself: the v4 work explicitly targets the gaps (ML dtypes, device-agnostic IO, distributed checkpointing via TensorStore-engine wrapping) that would make a competing format necessary. If we ship the foundation and performance work (Stream 1), Zarr stays competitive on the workloads that would otherwise drive a replacement.

**Zarr-Python is abandoned in favor of TensorStore, zarrs, or a more agile Python library.** This is the failure mode the both-and framing is designed against. If Zarr-Python's pure-Python mode is too slow, too awkward, or too hard to extend, performance-sensitive users move to TensorStore via its Python bindings, and the long tail of small Zarr-using tools either follows or routes around Zarr-Python ad hoc (which is already happening — `yaozarrs`, `mesh-n-bone`, etc.). The mitigation, again, is the work itself: the proposals deliver the performance, extensibility, and ergonomics that make Zarr-Python worth choosing over the alternatives, and the engine-wrapping work means users who *do* need TensorStore's throughput get it without leaving the Zarr-Python ecosystem. If we *don't* ship the pure-Python performance work (Stream 1's M0 and M1 tiers), the alternative-library scenario becomes likely within one or two release cycles.

Both risks point at the same conclusion: the v4 work is what keeps Zarr-Python relevant. Not doing it is not the safe option.

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

The picture is unusual: a single open-source library that anchors **published petabyte-scale climate archives, an international bioimaging standard, an NIH-funded neurophysiology archive, a commercial product, and substantial parts of the Python ML-physics stack at NVIDIA, Apple, Google, and ECMWF**. Each of these depends on Zarr-Python remaining good. The v4 work is the investment that lets it keep being good.

## The Zarr Stack

There are levels of Zarr support. Some applications, like validators for domain-specific Zarr conventions, only need to read Zarr metadata documents. They don't need to read and write chunks. Other applications might only need read-only access to array metadata and the stored chunks, and nothing else. Tensorstore only supports reading and writing arrays, but not the `attributes` field of Zarr metadata, and it doesn't support any operations on Zarr groups. Zarr Python supports all types of operations -- reading and writing arrays and groups -- but doesn't support exactly the same set of data types and codecs as other "complete" implementations. 

The story here is that different applications need to do different operations with Zarr data. This is something we *learned* from seeing how different tools and communities leverage Zarr. Let's call a set of tools that supports these various operations a "Zarr stack". 

Concretely, the levels of the stack — from most abstract to most concrete — look something like this:

1. **Conventions** — domain-specific schemas built on top of Zarr (OME-NGFF, GeoZarr, anndata-zarr). Consumers: validators, format-specific readers, the `yaozarrs` / `ome-zarr-models-py` line of work.
2. **Groups** — Zarr hierarchies, traversal, group-level attributes.
3. **Arrays** — the user-facing array object, plus indexing and slicing. Under the v4 work this level grows [lazy indexing and Array API conformance](./proposals/lazy-indexing.md): an opt-in `array.lazy[...]` accessor on the existing `Array` class returns a lazy view (an additive 3.x minor), and the query planner sits here. The default of bare `array[...]` flips to lazy only as a separate later decision (a loud 3.x minor, if Array-API conformance requires it); the eager path is removed in the 4.0.0 major after the deprecation window. There is no new array type — the migration runs on a single `Array` class whose `__getitem__` semantics evolve across releases.
4. **Chunk decoding** — the codec pipeline. Under the v4 work this becomes a [small stateless capability bundle](./proposals/codecs.md) (encode / decode / optional `decode_into` / capability flags) decoupled from the rest of the library, with concrete codec implementations as plug-ins. This is also the seam where alternative engines (Zarrs, TensorStore) plug in — see the [performance proposal](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines).
5. **Chunk addressing** — chunk grids and key encodings that map array coordinates to store keys. Lives in the [`zarr-metadata` package](./proposals/functional-core.md#the-packages) as pure-data descriptions; accelerating new grids and key encodings (one of the v4 goals above) is mechanically a matter of adding new entries to this package.
6. **Stores** — the key-value layer. Under the v4 work this is *not* a monolithic `Store` class but a set of [capability protocols](./proposals/stores.md) (`Get`, `GetRange`, `Put`, `Delete`, `List`, ...) that backends declare and compose. Composable wrappers add caching, range coalescing, transactions, and retries on top, and a conformance suite defines what each capability means. See [stores.md](./proposals/stores.md) for the theme proposal; the detailed [API](./proposals/stores-api.md), [wrappers](./proposals/stores-wrappers.md), and [conformance suite](./proposals/stores-conformance.md) are linked from there.
7. **Metadata** — pure data documents describing arrays and groups. Sits at the bottom of the dependency graph: every other level depends on it, it depends on nothing.

A few of these levels are richer than a simple list suggests. Stores (level 6) have both *backends* (concrete implementations like `LocalStore`, `FsspecStore`) and *wrappers* (orthogonal capabilities like `Caching[S]`, `RangeCoalescing[S]`, `Transactional[S]`) that compose. Chunk decoding (level 4) has both the *interface* and pluggable *engines* (the default Python engine, Zarrs, TensorStore). The stack is not just seven nominal types — it is seven boundaries at which different kinds of pluggability live.

Today, `zarr-python` is a monolith that serves every level. A consumer who only needs level 1 has to install the full dependency footprint of level 7. A faster implementation at level 4 (Zarrs, TensorStore) cannot easily plug in without re-implementing levels 1–3. The dependency-footprint workarounds in the ecosystem (`yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr`) and the existence of a bespoke `zarrs-python` integration package are evidence that the monolith shape does not match how the ecosystem actually uses Zarr.

The v4 direction is to re-shape `zarr-python` around the stack: each level is something you can depend on, conform to, or replace, without buying every level above it. Concretely:

- **A focused package per level** — `zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`, and so on. See the [functional-core proposal](./proposals/functional-core.md#concrete-packaging-plan) for the concrete plan.
- **A documented interface per level** — capability protocols for stores, a small stateless codec API, pure-data dtypes, declarative hierarchy schemas.
- **A conformance suite per level** — the stores work has the most developed example ([stores-conformance.md](./proposals/stores-conformance.md)); the same pattern extends to codecs, dtypes, and engines.
- **Engine pluggability at the chunk-decoding level** — alternative implementations (Zarrs, TensorStore) can take over without re-doing the layers above. See [performance.md § Wrapping `zarrs` and TensorStore as alternative engines](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines).

This reframes our v4 goal of *"support Python tools across all levels of the Zarr stack"* from a slogan into a concrete commitment: every level has a named package, a documented interface, and a conformance suite. It also reframes high-performance backends from competitors to **peers at specific levels** — a user can keep `zarr-python`'s metadata, hierarchy, and indexing while routing chunk reads through Zarrs.

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

`Array.__getitem__` performs IO eagerly and returns NumPy, which makes Zarr arrays the odd one out among modern array libraries, blocks participation in the Python Array API ecosystem, and forces every performance-sensitive user through Dask to recover basic IO optimizations like deduplication, slice fusion, and range coalescing. Add an opt-in `array.lazy[...]` accessor (an additive 3.x minor) backed by a stable coordinate-mapping algebra ([PR open](https://github.com/zarr-developers/zarr-python/pull/3906)), flip the default of bare `array[...]` to lazy only as a separate later decision (a loud 3.x minor, if Array-API conformance requires it), and conform to the Array API standard alongside. A small query planner turns chained selections into a single IO plan before any chunks are fetched. No new array type is introduced — the codebase carries one `Array` class throughout.

→ [proposals/lazy-indexing.md](./proposals/lazy-indexing.md)

### Consolidated metadata

Zarr's pattern of bundling all metadata into a single root-level document is essential for performance on high-latency storage and widely used by downstream tools. The current Zarr-Python support has open design questions around codec/dtype/grid representations, write-time invalidation, and migration between V2/V3 consolidated formats.

→ [proposals/consolidated-metadata.md](./proposals/consolidated-metadata.md)

### Data types

First-class support for ML-specific dtypes — `bfloat16`, the `float8` variants, packed `int4`/`uint4` — via Google's [`ml_dtypes`](https://github.com/jax-ml/ml_dtypes) package, either as an optional dependency of `zarr-python` or as a separate `zarr-ml-dtypes` package. Unblocks the substantial and growing ML community using Zarr for model checkpoints and training data. Ragged arrays, vlen strings, and dtype/codec interactions are follow-on work on the same `zarr-dtype` substrate. The proposal also commits to *investigating* Apache Arrow integration as a substrate for the dtypes the Array API can't express (nullable scalars, vlen strings, nested types) — the investigation itself is the v4 deliverable; what ships is determined by what we find.

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

### Coordinated and Distributed Writes

Zarr-Python's write path is still user-coordinated: it assumes one process holds the array open and the caller handles not-clobbering, create-before-write, and cleanup. The two patterns that actually produce large Zarr archives — parallel disjoint-region writes (a coordinator creates the array, N workers each fill a non-overlapping slab) and append-along-axis growth — have no design home. Draw the line between what Zarr-Python provides directly on plain v3 (disjoint chunk-aligned region writes, a create-then-hand-out-regions primitive with chunk-alignment *checked* not assumed, single-writer resize/append — none needing a format change) and what it cannot provide there but instead *enables* by exposing the seam a transactional engine builds on (atomicity, reader isolation, recovery, concurrent appenders, conflict resolution), so that coordination extends the Zarr hierarchy rather than living in a parallel format.

→ [proposals/coordinated-writes.md](./proposals/coordinated-writes.md)

## Roadmap

> **Revision note.** An earlier version of this section sequenced the work as four serial phases gated behind a single breaking **4.0** release. On closer examination that sequencing concentrates migration cost and user-visible payoff in the wrong places: the foundation is *additive* (it needs no breaking release), while the only irreducibly breaking work is a small set of *removals*. This section is re-sequenced accordingly — additive value ships continuously as EffVer minors, deprecations accumulate across that line, and breaking removals are concentrated in a single, late, well-signposted major. **"v4" names this whole body of work, delivered across many releases — it is not a single feature release.** Concretely: the additive work ships as EffVer **3.x minor releases**, deprecations accumulate across the 3.x line, and the only release literally numbered **4.0.0** is the final, minimal, removals-only major. There is no big-bang "4.0" feature release; where this document earlier said "4.0 work" it now says "v4 work" to make that explicit.

The proposals above describe *what* changes; this section describes *when* and *in what order*. The work is organized into **three streams that run in parallel**, not a serial phase gate:

1. **Stream 1 — Additive value.** Everything with an additive path — the overwhelming majority of the plan, including the entire foundation — ships as ordinary EffVer 3.x minor releases. No migration required. This stream starts now.
2. **Stream 2 — Deprecation accumulation.** As Stream 1 ships additive replacements, the surfaces they supersede are marked deprecated, with warnings, across the 3.x line. No removals.
3. **Stream 3 — Breaking removals.** A single, minimal, late major release removes the deprecated surfaces — and *only* those — once their replacements have shipped and downstream has had release windows to migrate.

The reframe rests on a fact already visible in the repository: the foundation does not need a major version. [`zarr-metadata`](https://pypi.org/project/zarr-metadata/) — the first package from the per-level split — shipped as a standalone release while `zarr-python` sat at 3.1.6, and the [`IndexTransform` algebra](https://github.com/zarr-developers/zarr-python/pull/3906) is in flight as an additive PR against `main`. Both are additive in delivery — though to be precise about what that proves: extracting a focused package is *cleanly* additive, while rewiring the monolith to consume it is a genuine internal rewrite, just one that can land incrementally behind the stable facade rather than behind a major version. Either way the structural work labeled "Phase 0" in earlier drafts is the *least* breaking part of the plan for downstream users, not a gate that must clear before anything else moves.

A reader who wants the granular per-proposal sequencing should follow the links into the proposals themselves; each substantial proposal has its own migration / sequencing section. What follows is the release-shaped view of how those plans compose.

### Streams mapped to releases

| Stream | Release vehicle | Scope |
|---|---|---|
| **Stream 1** — Additive value | EffVer **3.x minors**, shipping continuously | The quick wins (M0), the foundation (M1), and the user-facing surface built on it (M2) — all additive. See the tiers below. |
| **Stream 2** — Deprecation accumulation | Warnings across the **3.x** line | `mode=` constructors, the `Buffer`/`prototype` read contract, `zarr.core.sync.sync()`, and — conditionally — eager `array[...]`, each deprecated *after* its additive replacement ships in Stream 1. |
| **Stream 3** — Breaking removals | One minimal **late major (`4.0.0`)** | Removal of the deprecated surfaces, and nothing else. Lands only after Stream 2's deprecation windows elapse and downstream ships dual-path releases. This is the only release literally numbered 4.0.0. |

The release vehicle is the point of the restructure: additive work does not wait on a major version, and the major version does not carry anything but removals. The streams are not gated on calendar dates; the work ships when it's ready.

### Stream 1 — Additive value (EffVer 3.x minors)

The bulk of the plan. Sub-ordered into three tiers by dependency and by how soon a user sees the benefit. The tiers are a *suggested ordering within one continuous stream*, not gated phases — M1 does not block M0, and design work for M2 runs alongside M0/M1 implementation.

#### M0 — Ship-now wins (days-to-weeks each, no dependencies, no migration)

High-ROI, dependency-free improvements that deliver visible value while the foundation is being built. None depend on the functional-core refactor; all ship as minors and most are S/M effort. This is the tier that was buried in the old phase ordering — it is pulled to the front here precisely so users see improvement during the otherwise payoff-free foundation window. The first item is a measurement harness, on purpose: the performance claims throughout this plan are currently *projected, not measured*, so the benchmark suite that validates them lands before the levers it scores.

- **Benchmark suite for the target access patterns** — cloud-latency reads (S3/GCS), multi-consumer concurrent reads, sharded sparse writes, repeated re-opens, and fancy indexing into compressed shards. [performance.md](./proposals/performance.md) concedes these patterns are *not yet covered* by the existing CodSpeed suite; building that coverage is a prerequisite for measuring every performance lever in M0/M1, and it is what turns "the FFI engines are an optimization, not a necessity" from a projection into an evidenced claim. Ships first so subsequent levers land with before/after numbers. → [proposals/performance.md](./proposals/performance.md)
- **LocalStore atomic rename-into-place** — fixes a known path-handling regression; no API change. → [proposals/stores.md](./proposals/stores.md)
- **Typed-concurrency nested-semaphore fix** — ends the "nested calls multiply concurrency" bug (a fresh `asyncio.Semaphore` is built per call today) ahead of the full concurrency rework. Ships with a *dask-safe default* — a single shared pool, conservative when running inside an outer scheduler — not a whole-machine pool per worker; see the typed-concurrency item in M1. → [proposals/performance.md § 1](./proposals/performance.md#1-concurrency-is-typed-library-owned-and-shared-across-nested-calls)
- **Store-layer range coalescing** — batched partial reads, merging nearby byte-ranges into one request. Already partly present: the current `WrapperStore.get_ranges` carries `max_gap_bytes` / `max_coalesced_bytes`, so this is an incremental wrapper, not new architecture. (ETag-based conditional reads move to M1, since they depend on the `Generation` contract introduced with the stores API.) → [proposals/stores-range-coalescing.md](./proposals/stores-range-coalescing.md)
- **Sync-first codec adoption on the default read path** — the synchronous single-chunk codec path (`SupportsSyncCodec` / `ChunkTransform`, with `_decode_sync` on every concrete codec) is *already merged* in `zarr-python`; wiring it into the default array read/write path removes the async-wrapping profiling hotspot without waiting on the full codec API rewrite or the functional-core refactor. Scope guard: this is the *sync invocation path only* — it keeps the existing V2-codec read path intact (a backward-read break against the NASA/ECMWF/Pangeo V2 installed base is non-negotiable), does not deliver the third-party-codec compat shim (which is unspecified and belongs to the M1 codec rewrite), and does not touch the contested Numcodecs-elimination question. → [proposals/codecs.md](./proposals/codecs.md)
- **In-flight request deduplication** — unconditional; collapses concurrent identical reads. (Coherence note: dedup only collapses concurrent reads of the *same* key — it carries no cross-key consistency guarantee, and the shared in-flight table needs explicit locking under free-threaded CPython.) → [proposals/performance.md § Caching](./proposals/performance.md#caching)
- **ML dtype support** via optional `ml_dtypes` (`bfloat16`, the `float8` variants, packed `int4`/`uint4`) — unblocks the ML-checkpoint community. Conformance constraint: zarr-python must emit the **exact identifiers registered in `zarr-extensions`** (an unknown dtype string is a hard open failure per the v3 spec — there is no graceful-ignore path, so a spelling drift turns "readable by tensorstore" into "unreadable everywhere"). Most are already registered (`bfloat16`, `int4`, `uint4`, seven `float8_*` variants); the notable gap is **`float8_e4m3fn`** — the FP8 type H100/PyTorch actually use — which is *not yet registered* and must land in `zarr-extensions` first. That registration PR is the one real cross-repo dependency in M0. → [proposals/data-types.md](./proposals/data-types.md)
- **Constructor and display UX** — explicit constructors replacing `mode=`, typed exception hierarchy, rich reprs + `tree(meta=False)`, context-manager protocol, file-like `ZipStore`, `__dask_tokenize__`, deterministic metadata output. → [proposals/missing-apis.md](./proposals/missing-apis.md)

#### M1 — Foundation (additive, mostly invisible to users)

Two distinct kinds of work live here, and they have *different* dependency relationships — a distinction that is load-bearing, and that holds up against the current `zarr-python` source:

- **Performance levers** (codec API, full typed concurrency, cache substrate, conditional reads) do **not** depend on the functional-core refactor. The current codec pipeline is already a registry-swappable seam holding no `Array`/store reference; the sync-first path and the partial-decode mixin are already in the tree; and caching/coalescing already compose as `WrapperStore` subclasses. These ship incrementally on current internals — the refactor makes them *cleaner*, not *possible*. Treating them as gated behind the refactor is the sequencing error this revision corrects. The one genuine exception is **engine-wrapping** of `zarrs`/TensorStore (in M2), which does need the functional-core engine seam — and that seam must be the full hierarchy-verb set, not the "exactly four functions" some proposals still describe, or the wrapped engines fall back to doing hierarchy traversal in Python.
- **The structural refactor** (functional-core extraction, per-level package split, stores API, hierarchy verbs) is the internal-quality investment justified on its own merits — chiefly the dependency-footprint and engine-pluggability wins — not as a precondition for the performance work.

Both ship additively, as new packages and new surfaces beside the existing ones, with independent done-states because neither gates the other.

**Performance levers — done when** each lands as the supported surface on current internals, validated against the M0 benchmark suite rather than asserted: the new codec API (sync-first, `decode_into`, `recommended_concurrency`, `PartialDecodeCapability`) with a compat shim over existing codecs; `ComputeConcurrency` / `IoConcurrency` library-owned with a dask-safe default; the cache substrate with the default policy from [performance.md § Default caching policy](./proposals/performance.md#default-caching-policy); and store-layer conditional reads (ETag-aware revalidation via `Generation`) working end-to-end.

**Structural refactor — done when** the functional-core refactor has landed, the four focused packages (`zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`) are published ([`zarr-metadata`](https://pypi.org/project/zarr-metadata/) is shipped; the other three follow), the new stores API is in `zarr-python` (with backends migrated and the conformance suite green), the hierarchy-layer verbs are defined and exported, and the `IndexTransform` algebra from [zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906) is merged. At that point downstream tools that need only a subset of Zarr functionality can depend on the focused packages instead of pulling in the whole library.

*Performance levers (ship on current internals, no refactor dependency):*

- **Codec API rewrite** — sync-first encode/decode, single-element signatures, `decode_into` capability, `recommended_concurrency` advertisement, `PartialDecodeCapability` flags. The sync path and partial-decode mixin already exist in the tree (see the M0 sync-codec item); this formalizes the public surface. Compat shim over existing codecs, decoupled from the Numcodecs-elimination work (which backfills over many minors). → [proposals/codecs.md](./proposals/codecs.md)
- **Typed concurrency resources** — library-owned `ComputeConcurrency` / `IoConcurrency` pools with per-call budgets that strictly shrink down the call stack. **The default must be dask-safe**: a single shared *process-global* pool per resource (not a fresh pool per call or per array), compute and IO sized separately (compute ≈ a cgroup/affinity-aware core count, IO a latency-hiding constant decoupled from cores), and *conservative when nested* inside an outer scheduler. Without this, the per-worker whole-machine default reproduces dask oversubscription — ~2× cores under the threaded scheduler, and ≈ `CPU_COUNT²` threads under the multiprocessing scheduler (each of `cpu_count` worker processes spins its own `cpu_count`-sized pool). The narrow nested-semaphore fix ships earlier in M0; this is the full rework. → [proposals/performance.md § 1](./proposals/performance.md#1-concurrency-is-typed-library-owned-and-shared-across-nested-calls)
- **Cache substrate** — one `AsyncCache`-shaped base; store-layer encoded-bytes cache via `Caching[S]`; hierarchy-layer caches via `array.with_caching(...)` / `group.with_caching(...)`. The default policy is chunks-opt-in and dedup-unconditional, but **metadata-on-by-default is a correctness regression on generation-less stores** (today's behavior re-reads on every open and is never stale; an on-by-default cache introduces a TTL-length stale window). So pin the metadata cache to **ETag-only revalidation with any TTL fallback opt-in and loudly noted as an EffVer default change** — and *do not flip metadata-cache-on before the conditional-reads revalidation below is wired*, or the cache ships without its safety mechanism. → [proposals/performance.md § Caching](./proposals/performance.md#caching), [proposals/hierarchy-layer.md § How caching stratifies cleanly](./proposals/hierarchy-layer.md#how-caching-stratifies-cleanly)
- **Store-layer conditional reads** — ETag-aware *revalidation* via `Generation`; lets repeated opens cost a `304` instead of a full GET. Lives here rather than M0 because it depends on the stores API's `Generation` contract. Precision — this is conditional *reads*, whose worst failure on an ETag-less / `If-Match`-ignoring backend (older MinIO, some Ceph RGW, ETag-less fsspec, `generation=None` stores) is *degrading to no revalidation* — a stale window or a redundant fetch, never a wrong answer. It must **not** be conflated with conditional *writes* (compare-and-swap / OCC): the same `Generation` token is **not** a safe CAS primitive on eventually-consistent or `If-Match`-ignoring endpoints, where it can report a write applied while silently losing it. Any write-side OCC promise is a separate, late item gated on a multi-backend race-conformance test, not part of this read-path lever. → [proposals/stores-range-coalescing.md](./proposals/stores-range-coalescing.md), [proposals/performance.md](./proposals/performance.md)

*Structural refactor (internal-quality, justified on its own merits):*

- **Functional-core refactor** — extract the pure-data layer (metadata, chunk-addressing math, codec configurations) from the side-effecting layer (stores, codec execution, IO). Establishes the engine boundary that lets alternative engines plug in. → [proposals/functional-core.md](./proposals/functional-core.md)
- **Per-level package split** — `zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype` as focused packages, with `zarr-python` as the facade that re-exports them and ships the default Python engine. **First package already shipped**: [`zarr-metadata`](https://github.com/zarr-developers/zarr-metadata) is published on [PyPI](https://pypi.org/project/zarr-metadata/). → [proposals/functional-core.md § Concrete packaging plan](./proposals/functional-core.md#concrete-packaging-plan)
- **Stores API** — capability protocols, `ReadResult` / `PutResult` / `Generation`, the wrapper-based composition model, the `Serializable` capability that lets stores cross language boundaries. Lands as a new surface beside the existing `Store`. The largest async-boundary payoff comes from routing cloud IO through the async-native **obstore** backend: removing `zarr.core.sync.sync()` does not by itself remove fsspec's separate event loop, so the "double bridge" of two background loops is only fully closed on the obstore path, not by the protocol redesign alone. → [proposals/stores.md](./proposals/stores.md) (plus tier-3 specs)
- **Formal hierarchy layer** — a small set of typed verbs (`read_array_metadata`, `write_chunk`, `list_children`, `read_selection`, ...) that compose the store API into hierarchy-shaped operations. The engine boundary is this verb set. → [proposals/hierarchy-layer.md](./proposals/hierarchy-layer.md)
- **Configuration substrate replacement** — retire `donfig`; the namespaced-key / env-override / preset surface survives. **This is a prerequisite, not a peer:** the dask-safe concurrency default, the cache default policy, preset selection, and engine selection all need a place to live, so the substrate must land *before* those perf-lever defaults — it is the first thing in this tier, resolving the earlier ambiguity over when it lands in its favor. → [proposals/missing-apis.md § 6](./proposals/missing-apis.md)
- **`IndexTransform` algebra** — the coordinate-mapping data structure lazy indexing is built on; already in flight at [zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906). No new array type is introduced — the codebase carries one `Array` throughout. → [proposals/lazy-indexing.md](./proposals/lazy-indexing.md)
- **Consolidated-metadata design (spec/ZEP-route, not implement)** — the design pass for the single highest-leverage xarray integration point. Crucially this is a *format* decision, not a library-internal one: consolidated metadata appears nowhere in the v3 core spec and is unread by tensorstore, zarrs, zarr-js, n5, and GDAL, so a v3 stored representation must go through a spec PR/ZEP and the document **must be marked `must_understand=false`** so non-supporting readers fall back to walking the hierarchy. The design must settle the representation of codec / dtype / chunk-grid configs, write-time invalidation under concurrent writers, and the one format-break corner — **V2↔V3 consolidated-format migration** — and it must land *before* the functional-core metadata data model and the hierarchy layer's `read_consolidated_metadata` verb crystallize around an implementation-defined shape. Co-designed with xarray, whose `open_zarr` path depends on opening a hierarchy in one request. Spec/ZEP routing is the M1 deliverable; any v3 representation ships only after the spec blesses it. → [proposals/consolidated-metadata.md](./proposals/consolidated-metadata.md)

#### M2 — User-facing surface (built on M1)

The work users see directly, implementable once the M1 substrate exists. All additive: opt-in accessors and new namespaces, not default-behavior changes (the one default change, the lazy flip, is treated separately below).

**Done when**: the opt-in `array.lazy[...]` accessor and query planner are wired in (turning chained selections into batched IO plans); `read_into` / `decode_into` are exposed for caller-provided destinations and Array-API namespace selection works at materialization; the `Metrics` object plus OpenTelemetry auto-instrumentation produce useful traces across stores, codecs, caches, and the engine boundary; the chunk-introspection verbs are exposed on `Array` (unblocking VirtualiZarr and Kerchunk); the `zarrs` and TensorStore engines are available as opt-in dependencies selectable by a keyword argument on `zarr.open(...)`. At that point users see the work directly: their code can read as Array-API code, their tooling sees Zarr operations in trace viewers, and FFI-engine users get native throughput without leaving the ecosystem.

- **Opt-in lazy indexing + query planner** — `array.lazy[...]` accessor and the planner that consumes the `IndexTransform` algebra from M1; an Array-API-conformant surface alongside. No default change here. → [proposals/lazy-indexing.md](./proposals/lazy-indexing.md)
- **Device-agnostic IO** — `read_into` / `decode_into` capabilities; Array-API namespace selection at materialization. GPU support falls out for free; the more common application is pre-allocated CPU buffers. → [proposals/gpu.md](./proposals/gpu.md)
- **Observability** — `Metrics` object, OpenTelemetry auto-instrumentation across the stack, chunk-level introspection APIs (the surface VirtualiZarr and Kerchunk need; mechanically the chunk verbs from the hierarchy layer surfaced on `Array`). → [proposals/observability.md](./proposals/observability.md)
- **Engine wrappers for `zarrs` and TensorStore** — `zarr.engines.zarrs` and `zarr.engines.tensorstore` modules that implement the hierarchy verbs against the compiled-language implementations while preserving the `zarr-python` surface. Same `Array`, same `Group`, same Xarray/Dask/napari interop. → [proposals/performance.md § Wrapping zarrs and TensorStore as alternative engines](./proposals/performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines)
- **Arrow integration investigation** — scoped exploration of how Arrow data structures (nullable types, vlen strings, nested types) integrate with Zarr-Python. The investigation itself is the deliverable; what ships is determined by what we find. → [proposals/data-types.md § Investigation: Arrow as a substrate for non-numerical dtypes](./proposals/data-types.md#investigation-arrow-as-a-substrate-for-non-numerical-dtypes)
- **Remaining missing-APIs conveniences** — `__truediv__` traversal, `open_nodes`, `copy` / `copy_all`, ZEP 8 URLs, CLI, in-library rechunking primitive. → [proposals/missing-apis.md](./proposals/missing-apis.md)

### Stream 2 — Deprecation accumulation (across the 3.x line)

Warnings only; no behavior is removed in this stream. Each deprecation is switched on *after* its additive replacement has shipped in Stream 1, so users always have a migration target before they see a warning:

- `mode=`-taking constructors — after the explicit constructor family ships (M0).
- The `Buffer` / `prototype` read contract — after `ReadResult` / `memoryview` ships (M1 stores work).
- `zarr.core.sync.sync()` — after the public `AsyncToSync` bridge ships (M1). Note: xarray depends on `sync()`; the public bridge is its replacement, and this deprecation must not precede it.
- Eager `array[...]` — *conditionally*, and only after an explicit eager escape hatch (`array.eager[...]` / `array.read()`) ships. See the decision point below.

### Stream 3 — Breaking removals (one minimal, late major: `4.0.0`)

The single honest breaking release — and the only release literally numbered **4.0.0**. It contains *only* removals whose replacements shipped in Stream 1 and whose Stream 2 deprecation windows have elapsed with downstream dual-path releases out. Nothing new is delivered here; the release is small by construction:

- Removal of the eager `array[...]` path (after the `array.eager[...]` escape hatch and deprecation window).
- Removal of the legacy `Store` ABC and the `Buffer` / `prototype` read contract.
- Removal of the `mode=` constructors.
- Removal of the `zarr.core.sync.sync()` bridge.

This is the only release downstream maintainers must treat as breaking, and it arrives last — after the value has already been delivered additively.

### The lazy default-flip is a decision point, not a flagship

Flipping the default of bare `array[...]` from eager to lazy is the single highest-migration-cost item in the plan, and — unlike the rest of Stream 1 — its benefit accrues mostly to power users and library authors rather than the person slicing an array in a notebook. It is therefore handled as an explicit decision, not bundled into the additive work:

- The **opt-in** `array.lazy[...]` accessor and the planner ship additively in M2, with no default change. This captures the performance value for everyone who wants it, with zero migration.
- Whether the **default** ever flips hinges entirely on whether Array-API conformance at the bare-`__getitem__` surface is a hard requirement. If it is not, the eager default stays and the explicit accessor is the whole story. If it is, the flip happens — but as a long-window Stream 2 deprecation with an `array.eager[...]` escape hatch and explicit downstream coordination (xarray's `ZarrArrayWrapper.get_duck_array`, dask's `is_arraylike`/`getter`), never as a reason to adopt a major version.

### What's out of scope

- **Persisted hierarchy links** (HDF5-style soft/hard/external links that survive across processes). Would require Zarr-Python to define a new on-disk object format unilaterally; needs a Zarr Enhancement Proposal first. The `KvStack` composite store covers the session-time use cases. → [proposals/missing-apis.md § 1](./proposals/missing-apis.md)
- **Declarative hierarchy schema validation as a shipped feature** — likely a separate `zarr-schema` package layered on `zarr-metadata`, deferred.
- **Cross-process shared-memory caching** — the substrate is designed not to foreclose it, but it doesn't ship now. → [proposals/performance.md § Caching-specific open questions](./proposals/performance.md#caching-specific-open-questions)
- **Consolidated metadata — full reimplementation.** The *design pass* is now in scope (M1, structural refactor), because it is the highest-leverage xarray integration point (one-request dataset opening on object storage). What remains deferred is only the complete shipped redesign, which may extend beyond M1; the design decision is no longer parked. → [proposals/consolidated-metadata.md](./proposals/consolidated-metadata.md)
- **Migration tooling for V2→V3** — the 2.x → 3.x transition is effectively resolved (per the Background section); we're not investing further in migration acceleration.

### How the streams compose

The streams run in parallel, not in series. Stream 1 has an *internal* dependency order — M2's surface work consumes M1's substrate — but **M0 depends on nothing and ships first**, so users see improvement immediately rather than waiting for the foundation. Stream 2 trails Stream 1 by one release per item (deprecate only after the replacement ships). Stream 3 trails Stream 2 by the length of each deprecation window plus downstream's dual-path releases.

There is no foundation gate. The earlier framing — "Phase 0 must land before anything else ships" — is exactly what this restructure removes: the package split is cleanly additive (proven by `zarr-metadata` shipping at 3.1.6) and the internal refactor, though a real rewrite, lands incrementally behind the stable facade, so the foundation ships *alongside* the quick wins rather than blocking them. The performance levers, in particular, do not depend on the refactor at all — the current codec pipeline, store-wrapper, and concurrency primitives already admit them (see M1).

The load-bearing pitch remains the pure-Python performance work — M0's coalescing, dedup, and sync-codec adoption plus M1's codec, concurrency, and cache work — *measured against the M0 benchmark suite*, not asserted. It is what makes "the FFI engines are an optimization, not a necessity" true; if it stalls, the [both-and framing](#why-zarr-python-exists) collapses. But because it ships as minors, it delivers value continuously rather than waiting behind a major release.

## Next steps

The proposals above describe what we want to do. Three groups of readers can move this forward; the asks for each are different.

### If you fund open-source science software

Zarr-Python is the kind of foundational infrastructure project that produces outsized leverage when it's funded well — a single library that anchors petabyte-scale climate archives, an international bioimaging standard, an NIH-funded neurophysiology archive, a commercial product, and substantial parts of the Python ML-physics stack (see [Who funds and depends on this work](#who-funds-and-depends-on-this-work) for the specifics). The v4 work proposed here is the structural investment that lets the library keep being good for those users, and the kind of investment that the urgent feature work of normal release cycles rarely accommodates.

**If your organization funds open-source scientific software** — whether through a structured program (CZI EOSS, NSF CSSI, NumFOCUS, Wellcome) or through direct support — **the maintainers would value the chance to discuss this work with you.** A specific resource ask (FTE-quarters by phase, named deliverables, success metrics) is being prepared and is available on request. Reach out via [the project's GitHub org](https://github.com/zarr-developers) or to the maintainers directly.

### If you contribute to Zarr-Python or the surrounding ecosystem

The proposal set is sized for collective work, not one team. Specific entry points:

- **The lazy-indexing PR** ([zarr#3906](https://github.com/zarr-developers/zarr-python/pull/3906)) is in flight. Review, testing, and feedback are welcome now. It is among the first pieces of the foundation work to ship.
- **The individual proposals** are the discussion venue for the rest of the work. Each substantial proposal — [functional-core.md](./proposals/functional-core.md), [stores.md](./proposals/stores.md), [hierarchy-layer.md](./proposals/hierarchy-layer.md), [codecs.md](./proposals/codecs.md), [performance.md](./proposals/performance.md), [lazy-indexing.md](./proposals/lazy-indexing.md), [observability.md](./proposals/observability.md), [gpu.md](./proposals/gpu.md), [data-types.md](./proposals/data-types.md) — has its own open-questions section. Comments and counter-proposals on those are the natural way in.
- **The smaller stubs** ([consolidated-metadata.md](./proposals/consolidated-metadata.md)) are placeholders awaiting expansion. Domain expertise on consolidated metadata is particularly welcome.
- **The Zarr V3 spec process** is where decisions that cross language boundaries land. Several open questions in the proposals above (persisted hierarchy links, ML dtype identifiers, the cache-tier conventions) ultimately need [Zarr Enhancement Proposals](https://zarr.dev/zeps/). Spec-side participation matters.

### If your project depends on Zarr-Python

The most useful thing downstream maintainers can do is **weigh in on the proposals while the design is still movable**. If your project's use of Zarr-Python would be affected by any of the work proposed here — the codec API rewrite, the stores rewrite, the lazy-indexing default-flip — read the relevant proposal and comment on it. The migration commitments below are written assuming downstream readiness; if there are workloads or patterns that don't fit, the planning phase is when to surface them.

The [`yaozarrs`, `mesh-n-bone`, `xcube-resampling`, `ngff-zarr`](./proposals/functional-core.md#parts-of-zarr-python-cannot-be-used-in-isolation) story (downstream projects that routed *around* Zarr-Python for various reasons) is exactly what the functional-core and packaging work aim to fix. If your project is on that list — explicitly or in spirit — the v4 work is partly for you, and your input on whether it actually solves your problem is load-bearing.
