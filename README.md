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

The `Store` abstraction is the lowest layer of Zarr-Python and the place where the 3.0 redesign carries the most accumulated debt. The current API was shaped for "support arbitrary backends via fsspec, with cloud-friendly latency," and it does that. But it conflates several concerns (path handling, capability modeling, sync vs async, lifecycle) into a single nominal class hierarchy, and the inheritance-based extension model has produced a stream of regressions whenever the `FsspecStore` join logic, path normalization, or backend-detection has been touched.

The 4.0 direction should be: **stores are sets of capabilities, composed from protocols, with backend-specific path handling pushed to backend-specific stores rather than enforced generically.** The `obstore`-backed store is already organized this way, and so is `obspec`'s capability protocol set. We should treat them as the model and bring the rest of the store layer in line.

##### The `Store` API is unwieldy

The current `Store` ABC bundles together several axes that should be modeled independently:

- **Stateful vs stateless.** Stores carry `_is_open`, allowed-exception sets, prototype caches, and read-only flags. They should be stateless capability objects that are cheap to instantiate; lifecycle (open/close, transactional state) should live in a separate context type.
- **Paths.** Stores currently do not own a path, which limits their usefulness in top-down hierarchy traversal and forces the surrounding `StorePath` wrapper to carry path state. Most real-world store usage pairs a store instance with a fixed root, and modeling that pairing in the type system would simplify equality, hashing, and serialization.
- **Sync vs async.** All store methods are async, including those backing fundamentally synchronous backends (`MemoryStore`, `LocalStore`, `ZipStore`). This forces wrapper layers like `_make_async` and `AsyncFileSystemWrapper`, which have themselves been a source of bugs ([zarr#3195](https://github.com/zarr-developers/zarr-python/pull/3195)). Sync-default with an opt-in async layer would map more cleanly onto the underlying backends.
- **Useless parameters.** `prototype` is required on every read call but ignored by most backends. It belongs in a configuration object, not the per-call signature.
- **Read-only semantics.** `read_only` is a boolean flag mutable via `with_read_only()`. The semantics of writes-after-readonly-clone, equality across read-only variants, and capability advertisement are inconsistent.
- **Async creation.** Several stores require `await Store.open(...)` before use. The reason is mostly to perform an async existence check; this could be deferred to first-use or hoisted into a synchronous probe.
- **Atomic and transactional writes.** V3 lost V2's atomic rename-into-place semantics ([zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410), [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094)). The pieces exist (Icechunk demonstrates a transactional model) but they need to be reflected in the Store API surface, not bolted on.

##### The `Store` API is hard to extend

Stores can wrap other stores, but the pattern relies on inheritance and method override. This produces three concrete problems:

- **Capability erasure.** A wrapper that adds caching has to subclass `Store`, which means its type no longer advertises which underlying capabilities are present. Code that wants to know "does this store support range reads?" cannot ask the type system.
- **Diamond inheritance.** Combining wrappers (caching + tracing + retry) requires linearizing the MRO and hoping no override conflicts. In practice users write a single bespoke wrapper rather than compose primitives.
- **No protocol surface for partial implementers.** A backend that only supports reads has to implement (or stub) the full `Store` ABC, including write methods that raise.

The right model is the one [obspec](https://github.com/developmentseed/obspec) uses: structural protocols for individual capabilities (`Get`, `GetRange`, `Put`, `Delete`, `List`, `Head`, `Copy`, `Multipart`), with backends declaring which they implement. [zarrita](https://github.com/manzt/zarrita.js) takes a similar protocol-first approach. Concrete proposal:

- Define capability protocols in zarr's storage layer that mirror or directly reuse `obspec`'s.
- Replace `Store` ABC subclassing with composition: a `Store` is "anything that satisfies the read capability subset I need."
- Wrappers (caching, tracing, range coalescing, retry, read-only enforcement) become protocol-preserving adapters: a `CachingStore[S]` advertises the same protocols as `S`.
- Backends that only support reads (HTTP, ReferenceFileSystem) advertise only the read protocols. Code that requires write capability fails at type-check time, not runtime.

##### Path handling is backend-specific and should not be enforced generically

`FsspecStore` has accumulated a recurring bug pattern around path normalization. The same shape recurs every six to twelve months: someone observes that paths from one backend cause a problem, adds a backend-agnostic normalization step, and that step then breaks a different backend's path semantics. A few cycles from the recent record:

- [zarr#2348](https://github.com/zarr-developers/zarr-python/pull/2348) added "raise error if path includes scheme," which was reverted in [zarr#3343](https://github.com/zarr-developers/zarr-python/pull/3343) when swift-fs was found to need the scheme in the path.
- [zarr#3193](https://github.com/zarr-developers/zarr-python/pull/3193) backed out a check about `auto_mkdir` because not all fsspec backends support it.
- [zarr#3679](https://github.com/zarr-developers/zarr-python/pull/3679) refactored the `FsspecStore` join logic from `_dereference_path` to `_join_paths`, introducing a `path="/"` regression for `ReferenceFileSystem` reported as [zarr#3922](https://github.com/zarr-developers/zarr-python/issues/3922).
- [zarr#3924](https://github.com/zarr-developers/zarr-python/pull/3924) attempted to fix #3922 by applying the zarr-key-level `normalize_path` helper to the constructor's `path` argument. That stripped leading slashes and broke absolute-path access on `LocalFileSystem`, surfacing as broken `titiler-xarray` upstream tests.
- [zarr#3926](https://github.com/zarr-developers/zarr-python/pull/3926) reverts the off-target change in #3924 and restores the v3.1.6 verbatim-path contract on the join sites.

The takeaway is not "we keep getting it wrong." The takeaway is that **a backend-agnostic path normalization routine cannot exist**, because path semantics are backend-specific in incompatible ways: a leading slash is meaningful on `LocalFileSystem` (absolute vs CWD-relative) but discarded by `S3FileSystem._strip_protocol`; a `"/"` is a sentinel for "no prefix" on `ReferenceFileSystem` but a real filesystem root on local; backslashes are valid bytes in S3 keys but path separators on Windows; `..` is a meaningful component on POSIX but rejected by S3 key validators. Any zarr-side normalization that picks one of these wins picks against another.

The sustainable design treats path handling as a backend concern:

- **Generic `FsspecStore` becomes a thin verbatim-path wrapper.** The store stores `path` exactly as given, joins it with keys via a uniform helper that handles only the empty-root and trailing-slash cases (the v3.1.6 `_dereference_path`), and otherwise does no normalization. This is the contract #3926 restores; it should be documented in the constructor docstring so future contributors do not re-add normalization. Use it across all I/O sites including the listing methods (`list`/`list_dir`/`list_prefix`), which currently still concatenate with raw f-strings and have a pre-existing `path="/"` bug independent of #3926.
- **An optional `validate_path` hook.** Default no-op. Users wrapping unusual backends (HuggingFaceFileSystem, WebdavFileSystem, custom community backends) can supply a callable to enforce backend-specific construction-time checks without zarr-python having to ship a class for every backend that exists.
- **First-class cloud stores route through `obstore`.** `ObstoreStore` already provides per-backend types (`S3Store`, `GCSStore`, `AzureStore`, `HTTPStore`) that enforce backend-specific path validation at construction. For S3, GCS, Azure, and HTTP, this is the better path; `FsspecStore` becomes the fallback for backends `obstore` does not cover (memory, reference, FTP/SFTP, custom fsspec backends).
- **Family-level `FsspecStore` subclasses, if needed.** If specific fsspec backends accumulate enough quirks to warrant it, introduce a small set of family classes (bare-key, absolute-path, bucket-key) rather than a class per protocol. Three classes cover most real divergence; per-protocol classes (`LocalFsspecStore`, `S3FsspecStore`, ...) duplicate logic and do not help custom backends.

This direction is consistent with the "compositional, capability-based" goal in the previous subsection: backend-specific stores are a refinement of the protocol surface, not a parallel inheritance hierarchy.

##### The `Store` API is missing basic idioms necessary for high performance

- **Caching.** We do not expose a caching layer on our latency-sensitive stores. For immutable datasets we are wasting huge amounts of user time and IO. The [experimental caching layer](https://zarr.readthedocs.io/en/stable/api/zarr/experimental/#zarr.experimental.cache_store) has been popular but has no migration plan to the main codebase. Caching belongs in the wrapper-protocol design above: a `CachingStore[S]` adapter that preserves `S`'s capabilities and adds memoization, with eviction policies and TTL exposed as configuration. Open issues: [zarr#278](https://github.com/zarr-developers/zarr-python/issues/278), [zarr#382](https://github.com/zarr-developers/zarr-python/issues/382), [zarr#2988](https://github.com/zarr-developers/zarr-python/issues/2988), [zarr#3570](https://github.com/zarr-developers/zarr-python/issues/3570).
- **Range coalescing.** We do not coalesce multiple byte-range reads. The [PR adding this](https://github.com/zarr-developers/zarr-python/pull/3004) requires infrastructure currently missing from the Store API. A protocol-based design makes this natural: a `GetRanges` capability advertises batch range fetching, a coalescing wrapper transforms many `GetRange` calls into one `GetRanges` call, and stores that already support batch fetching (S3 via `cat_ranges`, obstore's `get_ranges`) skip the wrapper.
- **Concurrent capability advertisement.** The protocol surface should advertise concurrency-safety guarantees so callers can pick batching strategies without probing. Today every caller has to know which backends are async-safe, which are thread-safe, and which are neither.

##### Proposed public API

A scaffolding sketch of the capability protocols, backend stores, wrappers, transactions, and migration story is in [proposals/stores-api.md](./proposals/stores-api.md). It is concrete enough to argue about but not committed to specific names or module layout.


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
