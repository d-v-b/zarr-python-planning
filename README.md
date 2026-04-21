# Zarr-Python Planning

Plans for the future of Zarr-Python. 

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

I worry that if we don't keep moving forward as a library, we will fall behind. If Zarr Python is too slow to improve performance, add features, and make APIs better, users will adopt other Python tools like Tensorstore, or simply not use Zarr at all. We have a lot of inertia, thanks to projects like Dask and Xarray, but that can change *very quickly* if someone motivated stands up a cleaner, faster, better Python-based Zarr library. We should run that cleaner, faster, better library. The following sections outlines my vision for how we can make that happen.

### What to change

If we want Zarr-Python to support the growing ecosystem of Python tools that work with Zarr data, I think we need to make some concrete changes, which I have divided by category. In each case I identify concrete changes we can make that would make the Zarr Python project a better foundation for the Zarr ecosystem.

- [Packaging](#packaging)
- [Codecs](#codecs)
- [Stores](#stores)
- [Consolidated metadata](#consolidated-metadata)
- [Data types](#data-types)
- [Concurrency and thread safety](#concurrency-and-thread-safety)
- [Caching](#caching)
- [GPU and device support](#gpu-and-device-support)
- [Observability](#observability)
- [Migration tooling](#migration-tooling)
- [Missing APIs](#missing-apis)
- [Improving performance](#improving-performance)

#### Packaging

I believe we should split Zarr-Python into separate packages. `zarr-python` would contain everything, `zarr-metadata` would just handle metadata documents, `zarr-dtype` would handle data types, `zarr-codec` would handle codecs, etc.

Related GitHub content:

- [zarr#3913](https://github.com/zarr-developers/zarr-python/issues/3913)
- [zarr#3867](https://github.com/zarr-developers/zarr-python/issues/3867)
- [zarr#3875](https://github.com/zarr-developers/zarr-python/pull/3875)
- [zarr#2863](https://github.com/zarr-developers/zarr-python/pull/2863)

##### Minimizing transitive dependencies

My first argument is based on offering users what they need, in terms of dependencies: 

The Zarr-Python package today contains the full set of data structures and routines necessary to implement Zarr V2 and V3. These are the core dependencies of Zarr-Python, as of [April 16, 2026](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/pyproject.toml#L35-L40):
```
    'packaging>=22.0',
    'numpy>=2',
    'numcodecs>=0.14',
    'google-crc32c>=1.5',
    'typing_extensions>=4.13',
    'donfig>=0.8',
```
A potential user who only needs to model the contents of a Zarr array metadata document doesn't need anything more than `typing_extensions` (it's needed for `TypedDict` features not released in Python 3.12). The remaining Zarr-Python dependencies like `numcodecs` and `numpy` are thus a barrier to that user adding `zarr` as a dependency to their project.

We should aim to support developers working at *all levels* of the Zarr stack. Forcing every downstream project to add a transitive dependency on NumPy and a codec library like Numcodecs thwarts this objective, and weakens the impact of Zarr-Python on the ecosystem of tools that work with Zarr data.

##### Formalizing project dependency relationships

My second argument is this: splitting Zarr-Python into separate packages would make Zarr-Python development much easier. By splitting Zarr-Python into separate packages we will effectively model the real dependency relationships in our project, and this will make evolving any one of those packages much easier. 

The real dependency relationships in the Zarr format are roughly characterized as follows:

- Parsing metadata documents depends on:
    - a metadata API
- Storing metadata documents depends on:
    - a metadata API
    - a store API
- Finding stored chunks depends on:
    - a metadata API
    - a store API
    - a chunk grid API
    - a chunk key encoding API
- Decoding chunks depends on: 
    - a metadata API
    - a store API 
    - a chunk grid API 
    - a chunk key encoding API
    - a data type API
    - a codec API 
 
If we divide Zarr-Python along these lines, we harden these conceptual boundaries and users who only need a targeted subset of Zarr functionality can depend on exactly the subset they need. This is the approach the [Zarrs library](https://github.com/zarrs/zarrs) uses.

##### Case study: codecs

I think the codec API in Zarr-Python is the best target for immediate upstreaming. Zarr-Python defines its codec API via a `Codec` abstract base classes. External libraries must implement their own codecs by subclassing the `Codec` class from Zarr-Python and registering the codec with Zarr-Python's codec registry. 

This design makes Zarr-Python a dependency of any external codec library. That is not problematic until we consider implementing a core Zarr codec (say, a rust-based `gzip`) in an external library. In this case, `zarr` would depend on `external.gzip`, but the `external` package would depend on `zarr` (for the `Codec` base class). Now if the `Codec` base class changes at all without perfectly synchronized compensatory changes in `external.gzip`, we run the risk of introducing subtle bugs when using `external.gzip` in `zarr`. 

This is not a hypothetical scenario: Zarr-Python used to depend on Numcodecs, which depended on Zarr-Python, and it was a fair bit of work to untangle the two: see PRs:
- [numcodecs#780](https://github.com/zarr-developers/numcodecs/pull/780) 
- [zarr#3376](https://github.com/zarr-developers/zarr-python/pull/3376)

Registering an external class using [entrypoints](https://packaging.python.org/en/latest/specifications/entry-points/) instead of an explicit import *weakens* the coupling, but the coupling is still there. The only real solution is to rewrite the dependency tree and break the cycle. 

So I propose we treat the codec API as a separate piece of software that has a version number, and define semantics for that version number. Zarr-Python and any other package can import from the codec API, possibly with an upper bound on the version if we are developing a new version of the codec API.

As a historical note, Zarr Python 2.x did not have a circular dependency problem here because it imported the codec API from Numcodecs. So this problem is a regression.

#### Codecs

In addition to the packaging issues mentioned in the previous section, there are a few other pain points related to codecs that we should fix as part of a Zarr Python 4.0 effort:

- The Zarr Python codec API is unwieldy and inefficient.
- Many popular Zarr V2 codecs have no Zarr V3 equivalent.
- The role of the Numcodecs package in the context of Zarr V3 is unclear.

I will expand on these issues individually and propose solutions. One family of solutions takes the form of a total codec class rewrite.

##### The codec API is unwieldy and inefficient

The structure of the [`Codec` base class](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/src/zarr/abc/codec.py#L85) in Zarr Python has a few issues worth fixing, which I enumerate here. Many of these issues could be addressed by incremental changes to the existing `Codec` base class, but I propose a more drastic replacement -- a full rewrite of the codec API, with a backwards-compatibility layer.

###### Unnecessary async encode / decode routines

*The codec base class defines `encode` and `decode` as asynchronous functions.* 

This design supports the sharding codec, which does IO and thus may benefit from asynchronous execution. But the vast majority of codecs do not do IO. Instead they are CPU-bound routines like data compression. Wrapping these routines in an async layer hurts their performance.

In order to avoid blocking the `asyncio` event loop these routines are run on a thread using `asyncio.to_thread`. The async event loop has to coordinate with a thread pool, which means we are adding at least 2 layers of callbacks for what should be a simple blocking synchronous function call. Multiply this overhead by thousands of chunks and it becomes substantial.

Performance profiling of Zarr Python's codec API routinely flags this unnecessary async layer as a performance bottleneck.

Solution: define `encode` and `decode` as synchronous functions, and define asynchronous `encode_async` / `decode_async` for classes that can make use of this functionality. 

###### Abstraction leakage in the encode / decode function signature

*The codec base class defines `encode` and `decode` as batch operations*

E.g., 

```python
async def encode(
    self,
    chunks_and_specs: Iterable[tuple[CI | None, ArraySpec]],
) -> Iterable[CO | None]:
    """Encodes a batch of chunks.
    Chunks can be None in which case they are ignored by the codec.

    Parameters
    ----------
    chunks_and_specs : Iterable[tuple[CI | None, ArraySpec]]
        Ordered set of to-be-encoded chunks with their accompanying chunk spec.

    Returns
    -------
    Iterable[CodecOutput | None]
    """
    return await _batching_helper(self._encode_single, chunks_and_specs)
```

Solution: `encode` and `decode` act on a single element. Batching concerns are left to a higher orchestration layer, or a mixin protocol that codec authors can choose to implement. This separates concerns and gives us a far simpler `encode` / `decode` signature.


###### The codec abstract base class is not abstract

Our codec abstract base classes are not abstract. They define concrete implementations (e.g., [this example](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/src/zarr/abc/codec.py#L221), which couples a nominally abstract method to the global runtime configuration object). This is an abstraction failure. 

Solution: avoid defining implementations in a data structure that is supposed to be abstract. 

In this case, I think re-writing all our pseudo-abstract base classes as completely abstract, structurally-typed protocols is the right choice. A protocol-based approach would weaken the coupling between Zarr-Python and codec implementations and allow a richer expression of codecs with different capabilities. And a clear separation between interface and implementation will make the codec behavior easier for developers to understand.

###### Codecs must allocate memory for their outputs

Each codec allocates its own memory for outputs in `encode` and `decode` operations. This adds substantial overhead to chunk decoding, especially the common case of decoding an entire chunk.

Solution: add `encode_into` and `decode_into` methods that don't allocate output buffers, and instead write into a caller-provided buffer. Combined with a codec context (codec pipeline) that manages buffer allocation, this will offer memory savings and simplify our model of what codecs have to do. 

###### Codecs don't know about slicing

When we request 1 scalar from an NxM chunk, we allocate memory for the entire chunk, read and decode the entire chunk, then select the single requested scalar. This is inefficient, compared to pushing the selection down into the chunk decoding process. 

Solution: Formally represent how array -> array codecs transform array indices, and index scalars from arrays mid-decoding as soon as they are available. This would offer a massive reduction in memory use for sub-chunk indexing workloads.

###### Codecs don't cache

When the codec pipeline decodes a chunk, it throws that decoded chunk away. This means requesting the same chunk again will trigger the same compute, which is wasteful if the data hasn't changed.

Solution: Array -> Array codecs that decode a full chunk should cache that decoded chunk, and re-use it later when subslices are requested. This is something Zarrs does. Combined with giving codecs a model of array selection (slicing) we can get a huge reduction in compute by spending some memory on a cache.

###### We should learn from Zarrs and Tensorstore

There are *many* things we could copy from Zarrs and Tensorstore to improve codec performance.

We should also accept reality: a Python library cannot realistically compete on performance with an optimized Rust or C++ solution. So we should *simply not compete*. Instead, we should wrap Zarrs and Tensorestore for chunk encoding / decoding. That means designing our codec API so that its pluggable over different backends. The `CodecPipeline` class today acheives this somewhat, but using Zarrs as a backend still required a [dedicated Python package](https://github.com/zarrs/zarrs-python/). We should learn from this effort and restructure our codec APIs to make this binding simpler.

Today, we tell people with serious performance demands to use Tensorstore or Zarrs. I would rather tell them to keep using Zarr Python, but with a Tensorstore / Zarrs backend.

##### V2 codecs with no V3 equivalent

In the Zarr Python 2.x era, the codec API was extremely simple. Zarr Python got all of its codecs from Numcodecs, which was a separate package due to the special build requirements involved with Cython code. Codecs were also unspecified, which was bad: Zarr developers working in other languages had to study the Numcodecs source code instead of a spec to replicate some of these codecs.

The Zarr V3 spec changed things for the better. Codecs got richer semantics and specification documents. But we never updated Numcodecs to natively support Zarr V3 codecs, in part because the Zarr Python 3.x codec implementation depended on a lot of Zarr Python internals. In retrospect this should have been addressed immediately by spinning out these dependencies into logically separated packages (see [earlier treatment of this topic](#case-study-codecs)).

There's no direct translation from a Zarr V2 codec to a Zarr V3 codec, which leaves many Zarr V2 codecs that lack a complete Zarr V3 counterpart.

Solution: write specs and implementations for all these codecs, and invest in tooling to make that process as smooth as possible. Large language models make spec-writing quite a bit easier, and we have plenty of examples in zarr-extensions to use as training data, but for codecs that aspire to implementations in multiple languages, there is a human bottleneck that can't be avoided, as each implementation author has to approve a potential integration.

##### The role of Numcodecs is unclear

We want the components of the Zarr ecosystem to be easy for people to understand. Right now, the codec infrastructure is confusing: Numcodecs defines Zarr V2 codecs. Zarr Python imports Zarr V2 codec implementations from Numcodecs, and wraps them in *2 different* Zarr V3 compatibility layers. 

Co-opting Zarr V2 infrastructure in Numcodecs was a good strategy when we were sprinting to release Zarr Python 3.x. But it's not a good long-term strategy for the Zarr ecosystem.

Taken on its own, Numcodecs has a few concerning issues:
- The name "Numcodecs" doesn't convey its connection to Zarr
- Numcodecs bundles together many codecs that people might want individually, leading to an unnecessarily large bundle size.
- Numcodecs only supports the much simpler Zarr V2 codec API. Any use of Numcodecs from Zarr Python 3.x requires adapter layers.
- Numcodecs implements fast codec implementations with Cython. This made sense 10 years ago but is less ergonomic today. Python bindings to C++ and Rust have vastly improved to the point where a dense Cython implementation looks much less attractive than bindings around C++ or Rust libraries.

Solution: we aim to eliminate Zarr-Python's Numcodecs dependency. We can do this while keeping Zarr V2 compatibility easily with adapter logic that maps Zarr V3-compatibles codecs to their Zarr V2 counterparts. Some codecs (like `gzip`) can be defined entirely within Zarr-Python. For other codecs, we should search for well-known, community-maintained packages that provide the basic encoding / decoding functionality, and implement the Zarr V2 codec wrappers in Zarr Python itself.

#### Stores

_draft notes_

##### The `Store` API is unwieldy

_draft notes_

- stores are stateful, should be stateless
- stores do not have a path, limits usefulness in top-down zarr hierarchies
- stores methods are all async
- store methods require useless parameters (prototype)
- stores have confusing read-only semantics
- stores require an async creation routine
- atomic / transactional writes — V3 lost V2's atomic rename-into-place semantics ([zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410), [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094))

##### The `Store` API is hard to extend

_draft notes_

- Stores can wrap other stores, but it's an awkward pattern that relies on inheritance We should have a compositional approach that models a store as a set of capabilities layered on top of a storage primitive, rather than a single type. Structural typing via protocols would help here, see [obspec](https://github.com/developmentseed/obspec), and also [zarrita](https://github.com/manzt/zarrita.js).

##### The `Store` API is missing basic idioms necessary for high performance

_draft notes_

- We don't expose a caching layer on our latency-sensitive stores. For immutable datasets, we are wasting huge amounts of user time and IO. We do have an [experimental caching layer](https://zarr.readthedocs.io/en/stable/api/zarr/experimental/#zarr.experimental.cache_store) which has been rather popular but we don't have a plan for migrating this feature to the main codebase.
- We don't coalesce multiple byte-range reads. There's a [PR](https://github.com/zarr-developers/zarr-python/pull/3004) that would add this feature but it requires infrastructure currently missing from the Store API.


#### Data types

_draft notes_

- bfloat16 and mldtypes ([zarr#2656](https://github.com/zarr-developers/zarr-python/issues/2656))
- Ragged arrays ([zarr#2618](https://github.com/zarr-developers/zarr-python/issues/2618))
- Dtype-codec interactions ([zarr#3491](https://github.com/zarr-developers/zarr-python/issues/3491))
- Dtype registry issues ([zarr#3117](https://github.com/zarr-developers/zarr-python/issues/3117), [zarr#3282](https://github.com/zarr-developers/zarr-python/issues/3282))

#### Concurrency and thread safety

_draft notes_

- Thread-unsafe initialization ([zarr#1435](https://github.com/zarr-developers/zarr-python/issues/1435))
- Multiprocessing failures ([zarr#3126](https://github.com/zarr-developers/zarr-python/issues/3126), [zarr#2729](https://github.com/zarr-developers/zarr-python/issues/2729))
- Async event loop conflicts ([zarr#2878](https://github.com/zarr-developers/zarr-python/issues/2878), [zarr#3487](https://github.com/zarr-developers/zarr-python/issues/3487), [zarr#2909](https://github.com/zarr-developers/zarr-python/issues/2909))
- Free-threaded CPython (nogil) support ([zarr#2776](https://github.com/zarr-developers/zarr-python/discussions/2776))

#### Caching

_draft notes_

- LRU cache for decoded chunks ([zarr#278](https://github.com/zarr-developers/zarr-python/issues/278)) — one of the oldest open issues
- Layered caching ([zarr#382](https://github.com/zarr-developers/zarr-python/issues/382))
- fsspec caching broken with FSSpecStore ([zarr#2988](https://github.com/zarr-developers/zarr-python/issues/2988))
- Negative result caching ([zarr#3570](https://github.com/zarr-developers/zarr-python/issues/3570))

#### GPU and device support

_draft notes_

- Core device abstraction ([zarr#2658](https://github.com/zarr-developers/zarr-python/issues/2658))
- CUDA streams/devices ([zarr#3271](https://github.com/zarr-developers/zarr-python/issues/3271))
- Buffer/array_api alignment ([zarr#2199](https://github.com/zarr-developers/zarr-python/issues/2199), [zarr#2473](https://github.com/zarr-developers/zarr-python/issues/2473))

#### Observability

_draft notes_

- OpenTelemetry integration ([zarr#2958](https://github.com/zarr-developers/zarr-python/issues/2958))
- Logging for store/array/group operations ([zarr#1774](https://github.com/zarr-developers/zarr-python/issues/1774))

#### Migration tooling

_draft notes_

- V2-to-V3 migration acceleration ([zarr#3076](https://github.com/zarr-developers/zarr-python/issues/3076))
- Conversion CLI tools ([zarr#3466](https://github.com/zarr-developers/zarr-python/issues/3466), [zarr#3467](https://github.com/zarr-developers/zarr-python/issues/3467), [zarr#3468](https://github.com/zarr-developers/zarr-python/issues/3468))
- CLI for copy, remove, convert, rechunk ([zarr#1511](https://github.com/zarr-developers/zarr-python/issues/1511))

#### Missing APIs

_draft notes_

- Declarative hierarchy modelling / schema validation ([zarr#2364](https://github.com/zarr-developers/zarr-python/discussions/2364))
- Lazy slicing / Array API alignment ([zarr#1603](https://github.com/zarr-developers/zarr-python/discussions/1603), [zarr#2197](https://github.com/zarr-developers/zarr-python/discussions/2197))
- Stable async/sync bridge as public API ([zarr#3835](https://github.com/zarr-developers/zarr-python/discussions/3835))
- Array views
- Rechunking / array re-encoding


#### Improving performance

_draft notes_

These suggestions cut across the previously listed categories, because we need to touch multiple parts of the Zarr Python stack.

- Use efficient implementations of each codec.
- Design codec and store APIs in a performance-friendly way: synchronous methods are default, encode / decode methods can accept pre-allocated memory, stores support range coalescing, etc.
