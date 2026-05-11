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

The `Store` abstraction is the lowest layer of Zarr-Python and the place where the 3.0 redesign carries the most accumulated debt. The current API was shaped for "support arbitrary backends via fsspec, with cloud-friendly latency," and it does that. But it conflates several concerns (path handling, capability modeling, sync vs async, lifecycle) into a single nominal class hierarchy, and the inheritance-based extension model has produced a stream of regressions whenever the `FsspecStore` join logic, path normalization, or backend-detection has been touched.

The 4.0 direction should be: **stores are sets of capabilities, composed from protocols, with backend-specific path handling pushed to backend-specific stores rather than enforced generically.** The `obstore`-backed store is already organized this way, and so is `obspec`'s capability protocol set. We should treat them as the model and bring the rest of the store layer in line.

##### The `Store` API is unwieldy

The current `Store` ABC bundles together several axes that should be modeled independently:

- **Stateful vs stateless.** Stores carry `_is_open`, allowed-exception sets, prototype caches, and read-only flags. They should be stateless capability objects that are cheap to instantiate; lifecycle should be either trivial (no-op for stateless backends) or explicit (context-manager protocol for resource-holding backends like `ZipStore`). Treated in detail in the [lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath) below.
- **Paths.** Stores currently do not own a path, which limits their usefulness in top-down hierarchy traversal and forces the surrounding `StorePath` wrapper to carry path state. Most real-world store usage pairs a store instance with a fixed root, and modeling that pairing in the type system would simplify equality, hashing, and serialization. Treated in detail in the [lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath) below.
- **Sync vs async.** All store methods are async, including those backing fundamentally synchronous backends (`MemoryStore`, `LocalStore`, `ZipStore`). This forces wrapper layers like `_make_async` and `AsyncFileSystemWrapper`, which have themselves been a source of bugs ([zarr#3195](https://github.com/zarr-developers/zarr-python/pull/3195)). Treated in detail in the [sync-by-default subsection](#sync-by-default-with-async-as-an-opt-in-protocol-family) below.
- **Useless parameters.** `prototype` is required on every read call but barely exercised: most concrete backends just thread it into a single `prototype.buffer.from_bytes` call at the return site, and most call sites in core code default to `default_buffer_prototype()`. Treated in detail in the [next subsection](#decoupling-prototype-from-the-read-api).
- **Read-only semantics.** `read_only` is a boolean flag mutable via `with_read_only()`. The semantics of writes-after-readonly-clone, equality across read-only variants, and capability advertisement are inconsistent. Treated in detail in the [lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath) below (resolved by replacing the flag with the `ReadOnly[S]` wrapper).
- **Async creation.** Several stores require `await Store.open(...)` before use. The reason is mostly to perform an async existence check; this could be deferred to first-use or hoisted into a synchronous probe. Treated in detail in the [lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath) below.
- **Atomic and transactional writes.** V3 lost V2's atomic rename-into-place semantics ([zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410), [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094)). The pieces exist (Icechunk demonstrates a transactional model) but they need to be reflected in the Store API surface, not bolted on. The full design is in [proposals/stores-transactional.md](./proposals/stores-transactional.md): per-key atomicity is a property of `Put` (`LocalStore` regains rename-into-place, restoring V2's contract); multi-key atomicity is a separate `Transactional` protocol with a context-manager API; backends like Icechunk additionally advertise `TransactionalOCC` for snapshot-isolation with concurrent writers.

##### Decoupling `prototype` from the read API

The `prototype: BufferPrototype` argument on every store read method is the most pervasive coupling in the current `Store` ABC, and the one most worth examining in detail because resolving it informs how to review in-flight PRs like [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) (range coalescing).

In current zarr-python, every concrete store has the same shape inside its `get` and `get_partial_values`: pull bytes from the backend, then return `prototype.buffer.from_bytes(raw)`. The wrapper stores (`LoggingStore`, `WrapperStore`) just thread `prototype` through. Of the call sites in core code, almost none thread a non-default prototype: `core/array.py` defaults to `default_buffer_prototype()` at every public entry point, `core/group.py` hardcodes the same default for metadata reads, and `codecs/sharding.py` hardcodes `numpy_buffer_prototype()` for shard index reads. The only place a non-default prototype is meaningfully bound is `ArraySpec.prototype`, which the codec pipeline reads at decode time. So the variability the parameter was supposed to enable is barely exercised, and the one place where it does matter (GPU buffer allocation) gets it from `ArraySpec`, not from a per-call store argument.

There are three end-states for fixing this:

1. **Stores return raw buffer-protocol data; the layer above wraps.** `Get`, `GetRange`, `GetRanges` return a buffer-protocol object (`memoryview` per the [return-type subsection](#returning-memoryview-from-store-read-methods)); the codec pipeline, sharding codec, and metadata loader call `prototype.buffer.from_bytes` themselves using the prototype that lives on `ArraySpec` (data) or a hardcoded CPU prototype (metadata). The store is a pure byte-fetching primitive. Zero-copy DMA into a device buffer is given up in principle, but in current zarr-python that path is not actually wired up: even with `gpu_buffer_prototype` the bytes hit the CPU first when fsspec or obstore returns them, so nothing real is lost in practice.
2. **Prototype moves to store construction-time configuration.** `Store(..., prototype=gpu_buffer_prototype)` and the read methods drop the parameter. Cleaner than today, but you cannot share a store instance across a CPU array and a GPU array in the same process.
3. **Prototype rides on a per-call context object.** Stores still return `Buffer`, but the binding moves to a `ReadContext` (or directly to `ArraySpec`) instead of a positional argument. Zero-copy is preserved in principle. Mostly a rename of where the prototype lives, the store is still typed in terms of `Buffer`.

I propose we commit to option 1. It is what [obspec](https://github.com/developmentseed/obspec) does, and the proposed protocol surface in [proposals/stores-api.md](./proposals/stores-api.md) already reflects it: `Get.get` returns `bytes`, not `Buffer`. The argument for keeping a `Buffer` return type is zero-copy GPU reads, but that is a future concern that requires changes well beyond the store API (the GPU codec layer, the obstore GPU integration). Giving up the in-principle option in option 1 does not block recovering it later by moving to option 3 if the GPU buffer story matures, because the wrapping layer would just become a context object instead of a free function.

Concrete migration path:

- Define `Get` / `GetRange` / `GetRanges` capability protocols that return `bytes`. Ship as additive surface; nothing is removed.
- Add a `BufferWrapping` adapter at the codec-pipeline / array layer that takes a `Get`-protocol store plus a prototype and produces `Buffer` outputs. Existing call sites that default to `default_buffer_prototype()` use it with no behavioral change.
- Migrate concrete backends (`LocalStore`, `MemoryStore`, `ZipStore`, `FsspecStore`, `ObstoreStore`) to expose the new protocols, with the legacy `Buffer`-returning methods kept as deprecation shims that call the new methods and apply `BufferWrapping`.
- Rewrite the sharding codec read path (`codecs/sharding.py`) to fetch raw bytes for the shard index (it already wants CPU-only) and for shard data (using `ArraySpec.prototype` for the wrap).

Implication for [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925): the new `get_ranges` should return raw bytes per range and not take a `prototype` argument. Coalescing is purely a byte-range operation; the buffer-typing decision belongs to the caller. Threading `prototype` through it (as the current PR does) preserves the existing pattern but locks in coupling we are trying to remove. A reviewer can point at this subsection as the end-state target and ask the PR author to drop the parameter from the new method's signature, with the wrapping happening in the sharding codec call site that consumes the result.

##### Sync-by-default with async as an opt-in protocol family

The current `Store` ABC makes every method `async def`. This was the right call for an API that primarily targets cloud object storage, but it has cost us at the protocol layer in two recurring ways. First, fundamentally synchronous backends (`LocalStore`, `MemoryStore`, `ZipStore`) implement async methods that internally do nothing more than call a sync routine, which means every read pays the cost of an event-loop bounce for no benefit. Second, the user-facing zarr API is largely synchronous (`zarr.open(...)[:]`), so calls into the store cross the `zarr.core.sync.sync()` bridge, which has been a steady source of event-loop reentrancy bugs ([zarr#3195](https://github.com/zarr-developers/zarr-python/pull/3195), [zarr#2878](https://github.com/zarr-developers/zarr-python/issues/2878), [zarr#3487](https://github.com/zarr-developers/zarr-python/issues/3487), [zarr#2909](https://github.com/zarr-developers/zarr-python/issues/2909)).

The protocol-based redesign has to take a position on how sync and async cohabit. There are three options for the surface:

1. **Single protocol family with `bytes | Awaitable[bytes]` returns.** One `Get` protocol; backends return either a value or an awaitable; callers do `await _maybe_await(result)`. Simple at the protocol layer. Painful at the call-site layer: the type checker cannot tell you whether you need `await`, every caller has to handle both, and the cost of the `_maybe_await` indirection accumulates over thousands of chunk reads.
2. **Single protocol family parameterized by a sync/async marker (`Get[Sync]`, `Get[Async]`).** Conceptually clean and the type checker can enforce. Python's generics are not quite up to expressing this cleanly today: mypy and pyright have inconsistent support for higher-kinded protocol generics, and the runtime story for `runtime_checkable` protocols with type parameters is fragile. Worth revisiting if the typing ecosystem catches up; not the right answer now.
3. **Two protocol families: sync (`Get`, `GetRange`, `GetRanges`, ...) and async (`GetAsync`, `GetRangeAsync`, `GetRangesAsync`, ...).** Backends declare which they implement. Most backends implement exactly one of the two; backends that can do both natively (FsspecStore over a dual-mode backend) implement both. Bridging wrappers (`SyncToAsync[S]`, `AsyncToSync[S]`) are explicit at the call site. Doubles the protocol surface, but each protocol is small and the doubling is mechanical.

I propose we commit to option 3, and that we adopt [obspec](https://developmentseed.org/obspec/latest/)'s naming directly with one deliberate divergence: protocol classes use the `Async` suffix, methods use the `_async` suffix, range methods take obspec's `start` / `end` / `length` keyword arguments, batch range methods take parallel `starts` / `ends` / `lengths` sequences, and listing splits into `List` (recursive) and `ListWithDelimiter` (directory-style). The one divergence is that the keyspace argument stays `key`, not obspec's `path`, because "key" is the term used by the [Zarr V3 storage spec](https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html#abstract-store-interface) and the current `Store` ABC, and switching it would invite confusion with filesystem-path semantics that the abstract store explicitly does not have. Structural compatibility with obspec is preserved at call sites that pass the argument positionally, which is the overwhelming majority. Reusing obspec's naming for everything else gives us free interop with `obstore` (which already implements obspec's protocols), keeps a single mental model for zarr users who also use object-store libraries directly, and offloads bikeshedding to a project that has already settled the question. The protocol surface doubling is a one-time cost paid inside the storage layer; options 1 and 2 push complexity into every caller and every type signature. Concrete mapping from backends to protocol families:

- `LocalStore`, `MemoryStore`, `ZipStore` implement only the sync protocols. They become plain `def get(...)` methods backed by blocking I/O or in-process state. No `asyncio.to_thread` in the implementation.
- `ObstoreStore` implements only the async protocols. It is async-native at the Rust layer and bridging it to sync would just queue work onto a thread pool that is already managed by tokio.
- `FsspecStore` is the awkward case. Some fsspec backends are async-native (`s3fs`, `gcsfs`, `adlfs`); others are sync-only (`LocalFileSystem`, `MemoryFileSystem`). `FsspecStore` advertises whichever family the underlying filesystem natively supports. Today's `AsyncFileSystemWrapper` becomes a `SyncToAsync` adapter applied to the wrapped filesystem rather than a layer baked into `FsspecStore` itself.
- `SyncToAsync[S]` and `AsyncToSync[S]` are wrappers that bridge. `SyncToAsync` runs each call in a thread pool (today's behavior) and is what callers reach for when they need to fan out concurrent reads over a sync store. `AsyncToSync` drives an event loop and replaces the current `zarr.core.sync.sync()` global bridge with an explicit, per-store choice.

The codec pipeline and array layer declare what they need at the type level. The shard read path needs concurrent fetches and is naturally async, so it asks for `GetAsync & GetRangeAsync`. A user passing a `LocalStore` (sync) gets a clear type error pointing at `SyncToAsync(local_store)` as the fix. A user passing an `ObstoreStore` (async) needs no wrapper. A user calling `arr[:]` on a `LocalStore` from a fully-sync context never crosses an event loop at all, which is the bug class we want to retire.

Concrete migration path:

- Define both protocol families. Ship as additive surface; the existing async-only `Store` ABC continues to work.
- Reimplement `LocalStore`, `MemoryStore`, `ZipStore` to expose sync-natural methods, with the legacy async methods kept as deprecation shims that call the sync method directly (no `to_thread`). This is the largest end-user-visible behavioral change: today `await local_store.get(...)` always goes through a thread, and after migration it would not. Callers that depended on the thread-pool concurrency need to wrap with `SyncToAsync` explicitly. Document this in the deprecation notice.
- Reimplement `ObstoreStore` to expose async-natural methods directly. Callers that need it from sync code wrap with `AsyncToSync` rather than going through the global `sync()` bridge.
- Migrate `FsspecStore` to advertise both protocol families when the underlying filesystem supports both, otherwise advertise only the natively supported family. Retire `AsyncFileSystemWrapper` as a baked-in layer in favor of the explicit `SyncToAsync` wrapper.
- Reimplement `zarr.core.sync.sync()` in terms of `AsyncToSync` so existing user-facing call sites keep working through the deprecation window. This gives us a single chokepoint to retire when the deprecation window closes.

Implication for in-flight PRs: PRs that add new async store methods (like [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925)) land into the async family unambiguously. Reviewers should ask whether the new method also has a sync counterpart in scope. For range coalescing specifically, the answer is "the async version is what matters in practice (the use case is remote stores that benefit from coalescing); a sync `GetRanges` can be added later if a sync-natural backend grows a native batch-read path." That makes #3925 a clean fit for the end-state shape: it adds a method on the async family, the eventual `GetRangesAsync` protocol with method `get_ranges_async`, and does not need a sync mirror to be merge-ready.

##### Returning `memoryview` from store read methods

Once stores stop returning a typed `Buffer` (see the [prototype-decoupling subsection](#decoupling-prototype-from-the-read-api)), there is still a choice about the concrete type the raw bytes come back as. Three plausible options:

1. **`bytes`.** Simple, universal, immutable, picklable. Every backend has to materialize the wire data into a Python `bytes` object before returning, which is a copy at the FFI boundary for backends like `obstore` that hold their data Rust-side. CPython `bytes[a:b]` creates a new `bytes` object and copies, so the sharding codec's per-chunk slicing of a coalesced shard fetch costs an extra copy per chunk multiplied by the number of chunks per shard. The motivating use case for [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) (range coalescing for sharded reads) loses most of its win if the result type forces this copy.
2. **`memoryview`.** Builtin, zero-copy view over any object that exposes the buffer protocol. Slicing is zero-copy. Constructing a numpy array via `np.frombuffer(mv, dtype=...)` is zero-copy. No extra dependency. Lifetime is managed by the standard Python reference graph: a `memoryview` holds a strong reference to its source, so the source stays alive as long as the view does. Real lifetime footguns are limited to explicit `release()` patterns and mmap-style OS resources, which the storage layer can manage at the construction site rather than passing the burden to callers.
3. **obspec `Buffer`.** The custom buffer-protocol type used by `obstore` and `obspec`. Same zero-copy properties as `memoryview`, plus explicit lifetime semantics encoded in the type. Aligning the return type with obspec gives the `ObstoreStore` pass-through a true zero-cost boundary (no `memoryview(...)` wrap, no `bytes(...)` materialization). The cost is a direct dependency in zarr's storage type surface, which constrains how the `Buffer` type can evolve and adds a transitive dependency for users who would otherwise not need it.

I propose we commit to option 2. The argument: option 2 captures the entire performance win of option 3 with no dependency cost, the lifetime story is well-understood (`memoryview` is in everyone's mental model), and the `ObstoreStore` boundary cost is one `memoryview()` call per fetch rather than zero, which is not where the time is spent. The door stays open to switch to option 3 later if we ever need the explicit lifetime semantics for a specific footgun, and the migration would be additive: change return types from `memoryview` to `Buffer`, with `memoryview(buf)` still working at every call site.

Concrete migration:

- `Get` / `GetRange` / `GetRanges` (and the async variants `GetAsync` / `GetRangeAsync` / `GetRangesAsync`) return `memoryview` (`Sequence[memoryview]` for the batch).
- The wrapping layer above (codec pipeline, metadata loader, sharding codec) continues to call `prototype.buffer.from_bytes(mv)`. The method is misleadingly named: zarr's `BytesLike` type alias is `bytes | bytearray | memoryview` (`zarr.core.common:38`) and the CPU implementation goes through `np.frombuffer(bytes_like, dtype="B")`, which is a view rather than a copy when the input supports the buffer protocol. So passing a `memoryview` through this method is already zero-copy on CPU. The GPU implementation calls `cp.frombuffer`, which does a host-to-device copy that is fundamental to GPU access regardless of upstream type. (Zarr's separate `from_buffer` method is for typed-`Buffer`-to-typed-`Buffer` conversion across prototypes, not for raw buffer-protocol input. Renaming `from_bytes` to `from_buffer_protocol` or similar is a useful follow-up that would clarify the intent, but it is not load-bearing for the migration.)
- `LocalStore` reads a file into `bytes` and returns `memoryview(bytes_obj)`, or, if we want kernel-level zero-copy for large reads, mmaps and returns a `memoryview` over the mapping; the choice is internal to `LocalStore` and not visible at the protocol layer.
- `ObstoreStore` returns `memoryview(obstore_result)`. obstore's `Buffer` already supports the buffer protocol so this wrap is zero-copy.
- `MemoryStore` is the odd one out today: it stores typed zarr `Buffer` objects internally and reaches for `prototype.buffer.from_buffer` rather than `from_bytes`. Under the new design it stores `bytes` (or `memoryview`) internally and returns `memoryview` directly, in which case it joins every other backend in being a pure raw-bytes store.
- `FsspecStore` wraps the underlying `cat_file` / `cat_ranges` result in a `memoryview`. Some fsspec backends return `bytes` (one copy already paid before reaching us); others return objects that implement the buffer protocol and stay zero-copy.
- The `Caching[S]` wrapper, when it ships, must copy `memoryview` to `bytes` at the cache write site because cache entries can outlive the source. This is the one place a copy is unavoidable, and it is paid once on cache fill rather than on every read.

Implication for [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925): the new `get_ranges` should return `Sequence[memoryview]` (eventually `GetRangesAsync.get_ranges_async` under the obspec-aligned naming). The sharding codec's slice into the coalesced result is then zero-copy, which is the entire point of the PR. A reviewer can ask the PR author to flip the return type from the current zarr `Buffer` to `memoryview`, or, if that is too disruptive for the merge window, to flag the type change as a planned follow-up so the coalescing logic does not bake in assumptions that would block the eventual flip.

##### Lifecycle, paths, and the future of `StorePath`

Four bullets in the unwieldy list (stateful-vs-stateless, paths, async creation, read-only semantics) are entangled and worth resolving in one subsection. Today's design has `Store` carrying an `_is_open: bool` flag set by an awaited `_open()` method, with every public method calling `_ensure_open()` internally for lazy auto-open; a `with_read_only()` clone for read-only flips; and a separate `StorePath` facade (`zarr.storage._common.StorePath`) that pairs a `Store` with a path and is what `Array.store_path` and `Group.store_path` actually carry. Hierarchy traversal happens through `StorePath.__truediv__`, which constructs a new `StorePath` with the same `Store` and a longer path. The user-facing entry point `make_store_path` resolves a string/Path/Store into an opened `StorePath`.

The pain this design carries:

- **`_is_open` is mostly fictional.** `MemoryStore`, `FsspecStore`, and `ObstoreStore` have no override at all; the base implementation just flips a flag. Only `LocalStore` (mkdir + existence check) and `ZipStore` (open zipfile + create lock) do real work in `_open`, and ZipStore is the only store that holds resources requiring real cleanup. Carrying the flag and the lazy-open machinery on every store to support two stores' worth of real behavior is overhead that complicates pickling, equality, sub-classing, and the protocol surface.
- **Path ownership is split.** Every concrete store except `MemoryStore` and `ObstoreStore` already takes a path-like field in `__init__` (`root` for `LocalStore`, `path` for `ZipStore` and `FsspecStore`), but the user-facing handle is `StorePath(store, path)`, which carries an additional path on top of that. The two paths get composed at the join site every time. Equality on `Array`s requires comparing both `store` and `path` separately. Pickling has to handle both.
- **`StorePath` is structurally a wrapper.** Its `get` / `set` / `delete` / `exists` methods are pure delegations to `self.store.method(self.path, ...)`. `__truediv__` is `Prefixed(self.store, join(self.path, other))` in disguise. The wrapper-protocol design proposed for caching, retry, range coalescing, and read-only fits `StorePath`'s shape naturally; keeping it as a separate type is a special case that the new design can absorb.
- **`with_read_only()` is an in-place flip via clone.** Every concrete store implements it as "construct a new instance with the same backing data and a different `read_only` flag," which is exactly what the proposed `ReadOnly[S]` wrapper does, except the wrapper preserves capability surface at the type level and the clone does not.
- **Async creation is real for one store.** `await Store.open(...)` is necessary for `LocalStore` (existence check) and could be for any backend that wants a probe at construction time. But the async-creation pattern leaks into every call site, and pairs awkwardly with the lazy-auto-open machinery that exists precisely to let callers skip `await store.open(...)`.

There are two coherent end-states.

1. **Keep `StorePath` as the user-facing path-bearing facade.** Stores stay path-less at the protocol level; `StorePath` continues to compose `Store` with a prefix. Lifecycle improves (drop `_is_open`, use explicit context managers for resource-holding stores) but the path-ownership split persists. `Array.store_path: StorePath` stays; equality comparison stays two-fielded; pickling stays special-cased.
2. **Replace `StorePath` with a `Prefixed[S]` wrapper that lives in the wrapper hierarchy alongside `Caching[S]`, `RangeCoalescing[S]`, etc.** Concrete stores own their natural scope in `__init__` (`LocalStore(root)`, `FsspecStore(fs, base_path)`, `ObstoreStore(s3_store)`); the per-call methods take a `key` relative to that scope; an additional prefix on top of the scope is expressed via `Prefixed(store, prefix)`, which is itself a store-typed value satisfying every capability `S` satisfies. Hierarchy traversal becomes `Prefixed.__truediv__`. `Array.store: Prefixed[S]` (or just `Array.store: S` when the array is at the scope root). Equality, hashing, and pickling are uniform: they live on `Prefixed` and its inner store, with no separate facade type to special-case.

I propose we commit to option 2. The argument: `StorePath` is doing wrapper work without being in the wrapper hierarchy; merging it gives us one less special case, makes the conformance suite's `CapabilityPreservationSpec` apply automatically (a wrapped store advertises the same capability surface as its inner store, which is exactly what we want for `Prefixed[S]`), and turns hierarchy traversal into the same `__truediv__` semantic but operating on a typed-by-protocol wrapper rather than a separate facade type. The migration is a rename plus protocol-method delegation; the user-facing API at the `Array` and `Group` level can keep `store_path` as a deprecation alias for `store` during the transition window.

Concrete proposals, with stubs in [proposals/stores-api.md](./proposals/stores-api.md#path-ownership-and-prefixed-wrapper):

- **Drop `_is_open`, `_open`, `_ensure_open`, and the `Store.open` classmethod.** Stateless stores do all init in `__init__` and have no lifecycle to manage. `MemoryStore`, `FsspecStore`, `ObstoreStore` are unaffected (their `_open` was a no-op). `LocalStore` moves its existence check to `__init__` and gains an explicit `mkdir: bool = False` constructor flag (default raises `FileNotFoundError` if the root does not exist; opt in to create). `ZipStore` is the resource-holding case and keeps explicit `__enter__` / `__exit__` (and `__aenter__` / `__aexit__`) for the file handle and lock; the strictness of "must be used as a context manager" versus "lazy-open continues to work" is undecided and tracked as an [open question in the proposal doc](./proposals/stores-api.md#open-questions). The other stores' lifecycle resolution does not block on the `ZipStore` decision.
- **Drop `with_read_only()` in favor of the `ReadOnly[S]` wrapper.** Every existing implementation is "clone with different flag," which is exactly `ReadOnly[S]`'s job. The wrapper preserves the capability surface minus `Put` / `Delete` / `Copy` / `Transactional`, which the type checker now enforces.
- **Move `StorePath` into a `Prefixed[S]` wrapper in `zarr.storage.wrappers`.** `Prefixed[S]` is generic over the inner store type and satisfies every capability `S` satisfies. `__truediv__` produces a new `Prefixed[S]` with a longer prefix. `__eq__` and `__hash__` are uniform; pickling is automatic. During the deprecation window, `StorePath` becomes a thin alias that constructs a `Prefixed[Store]` and emits a warning.
- **`make_store_path` becomes `make_store`.** Resolution from a URL or string returns either a concrete store (when the resolved path is at the scope root) or `Prefixed(concrete_store, sub_prefix)`. No async required for stateless stores; resource-holding stores expose context-manager construction.
- **Every store gets uniform `__eq__` and `__hash__`.** Stateless stores can be `@dataclass(frozen=True)`-shaped or hand-rolled; the contract is "two stores compare equal iff they reference the same data with the same configuration." `Prefixed[S]` extends this through composition. This unblocks distributed schedulers (dask, ray) that rely on stores being usable as dict keys and being correctly comparable across processes.

The migration is staged: the wrapper protocols ship first (additively, no breaks); `Prefixed[S]` ships next; `Array` and `Group` gain a `store: Prefixed[S]` accessor with `store_path` kept as a deprecation alias; the `_is_open` machinery is removed in a separate cleanup pass; `with_read_only` deprecates in favor of `ReadOnly[S]`. Each step is independently reversible if it surfaces problems.

Implication for in-flight PRs: this subsection does not touch [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) directly because the coalescing logic operates at the store-method level, not the call-site level. It does inform any PR that touches `make_store_path`, `Array.store_path` / `Group.store_path` accessors, or `_is_open` / `_open` / `_ensure_open`. A reviewer of such a PR can ask whether the change moves toward `Prefixed[S]` and stateless construction or away from it; reviewers can use the `CapabilityPreservationSpec` from the [conformance suite proposal](./proposals/stores-conformance.md#wrapper-preservation-specs) to verify that any wrapper or facade introduced in such a PR preserves the inner store's capability surface.

##### Equality, hashing, and pickling

Stores in the protocol-based design are stateless capability objects (with `ZipStore` as the documented exception holding a file handle). Stateless makes equality, hashing, and pickling all uniform: a store compares equal iff it references the same data with the same configuration; its hash is based on those same fields; pickling and unpickling round-trip without special handling. This unblocks distributed schedulers (dask, ray, etc.) that need stores as dict keys (for chunk-keyed memoization) and that ship stores across processes via pickle.

Today's stores have inconsistent answers: `LocalStore.__eq__` checks only `root` (ignores `read_only`); `MemoryStore.__eq__` checks dict identity *and* `read_only`; `FsspecStore.__eq__` checks `path + fs + read_only`; `ObstoreStore.__eq__` checks `store + read_only`; `ZipStore.__eq__` checks only `path`. None of them define `__hash__`, so none can be used as dict keys directly. Only `ZipStore` and `ObstoreStore` define `__getstate__` / `__setstate__`, and they do so to handle backend-specific state (the file handle, the obstore object). Picking a uniform contract removes the per-backend ambiguity and the per-backend special-casing.

Concrete proposal:

- Stateless backends (`LocalStore`, `MemoryStore`, `FsspecStore`, `ObstoreStore`) define explicit `__eq__` and `__hash__` based on their full configuration tuple. `@dataclass(frozen=True, eq=True, slots=True)` is the natural pattern for the simple ones; hand-rolled is fine for the ones wrapping third-party objects (`FsspecStore` wraps an `AsyncFileSystem`; `ObstoreStore` wraps an `obstore.ObjectStore`). The `read_only` flag is removed from constructors per the [lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath), which simplifies the equality contract: stores are equal iff they reference the same data with the same configuration, full stop.
- `Prefixed[S]` carries equality and hashing through composition: `Prefixed(s, p) == Prefixed(s', p')` iff `s == s'` and `p == p'`; `hash(Prefixed(s, p)) == hash((Prefixed, s, p))`. This is what makes `Array.store: Prefixed[S]` usable as a key in distributed-scheduler-side caches.
- Wrappers (`ReadOnly`, `Caching`, `RangeCoalescing`, `Retry`, `Tracing`, `SyncToAsync`, `AsyncToSync`) follow the same pattern: explicit `__eq__` and `__hash__` based on `(type, inner, config_tuple)`. Two `Caching(s, max_bytes=X)` instances compare equal iff `s` is equal and `X` matches.
- `ZipStore` is the resource-holding exception. Equality and hashing are based on the file path and mode (the configuration that determines what data the store represents); the file handle and lock are not part of the identity. Pickling drops the handle on `__getstate__` and re-acquires on `__enter__` (today's behavior), so a `ZipStore` pickled and shipped to a worker is "ready to be entered." See the [lifecycle open question](./proposals/stores-api.md#open-questions) on whether the strictness of the context-manager contract changes.

This is straightforward plumbing but has been a long-standing source of friction. Land it as part of the protocol-based redesign rather than as a separate retrofit on the current ABC, since the redesign already touches every store's constructor.

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

- **Caching.** We do not expose a caching layer on our latency-sensitive stores. For immutable datasets we are wasting huge amounts of user time and IO. The [experimental caching layer](https://zarr.readthedocs.io/en/stable/api/zarr/experimental/#zarr.experimental.cache_store) has been popular but has no migration plan to the main codebase. Caching belongs in the wrapper-protocol design above: a `Caching[S]` adapter that preserves `S`'s capabilities and adds memoization, with eviction policies and TTL exposed as configuration. The wrapper is specified in [proposals/stores-caching.md](./proposals/stores-caching.md), with concrete defaults (256 MiB / 4096 entries, TTL off, negative caching off), the cache-key strategy ("cache exactly what was requested"), the write-invalidation contract, the recommended composition with `RangeCoalescing` and `Retry`, and the migration plan for `experimental.cache_store`. Open issues addressed: [zarr#278](https://github.com/zarr-developers/zarr-python/issues/278), [zarr#382](https://github.com/zarr-developers/zarr-python/issues/382), [zarr#2988](https://github.com/zarr-developers/zarr-python/issues/2988), [zarr#3570](https://github.com/zarr-developers/zarr-python/issues/3570).
- **Range coalescing.** We do not coalesce multiple byte-range reads. The [PR adding this](https://github.com/zarr-developers/zarr-python/pull/3925) requires infrastructure currently missing from the Store API. A protocol-based design makes this natural: a `GetRanges` capability advertises batch range fetching, a coalescing wrapper transforms many `GetRange` calls into one `GetRanges` call, and stores that already support batch fetching (S3 via `cat_ranges`, obstore's `get_ranges`) skip the wrapper. The wrapper itself is specified in [proposals/stores-range-coalescing.md](./proposals/stores-range-coalescing.md), with concrete defaults (1 MiB `max_gap`, 64 MiB `max_request`), failure semantics, and a test plan that pins the load-bearing "exactly one underlying `get_range` call when ranges are within `max_gap`" claim that #3925 reviewers can reference.
- **Concurrent capability advertisement.** The protocol surface should advertise concurrency-safety guarantees so callers can pick batching strategies without probing. Today every caller has to know which backends are async-safe, which are thread-safe, and which are neither. Concrete proposal: marker protocols `ThreadSafe(Protocol)` and `AsyncSafe(Protocol)` that backends advertise (or omit) at the type level. `MemoryStore` and `LocalStore` are thread-safe (CPython's GIL plus filesystem semantics); `ObstoreStore` is thread-safe and async-safe (Rust + tokio); `FsspecStore` defers to the underlying filesystem and either advertises the markers or doesn't depending on what the inner `fs` supports; `ZipStore` is thread-safe within a single process via its lock but not across processes. Both markers are runtime-checkable but mostly used at the type level: code that wants to fan out concurrent reads can declare `def f(s: GetAsync & AsyncSafe) -> ...` and let the type checker enforce the requirement, with no runtime probing. Free-threaded CPython ([zarr#2776](https://github.com/zarr-developers/zarr-python/discussions/2776)) elevates `ThreadSafe` from "GIL gives this for free" to "the backend explicitly serializes its mutation paths"; the marker is the place where each backend declares its post-no-GIL contract.

##### Proposed public API

A scaffolding sketch of the capability protocols, backend stores, wrappers, transactions, and migration story is in [proposals/stores-api.md](./proposals/stores-api.md). It is concrete enough to argue about but not committed to specific names or module layout.

##### Conformance test suite

The protocol-first redesign only pays off if there is a shared test contract that backends and wrappers parameterize, rather than per-backend test files that overlap by accident. Without that contract, a PR that adds or modifies a wrapper has no falsifiable claim a reviewer can point at: capability preservation, range-coalescing semantics, cache invalidation rules, and zero-copy guarantees all live in prose. With it, a PR's diff to `tests/storage/test_<thing>_conformance.py` is the load-bearing artifact, and the review reduces to "are these the right specs to inherit and are the fixtures sensible." A scaffolding sketch of the per-capability spec classes, the per-backend matrix, the wrapper preservation specs (including a `RangeCoalescingSpec` that pins the "exactly one underlying `get_range` call when ranges are within `max_gap`" claim), the zero-copy property tests, and the migration story from today's `tests/storage/test_<backend>.py` files is in [proposals/stores-conformance.md](./proposals/stores-conformance.md). The suite is designed to live at `src/zarr/storage/testing/` so external backends (Icechunk, custom user backends) can subclass the same specs without depending on zarr's test layout.

##### Status and rollout

The store-layer redesign is split across this README and several proposal docs. Each proposal commits to one or more decisions and lists its own open questions. The summary below indexes them and gives a staged rollout sequence.

**Resolved decisions**

- Stores are sets of capabilities expressed as obspec-aligned protocols, with `key` as the one Zarr-domain divergence from obspec naming ([sync-by-default subsection](#sync-by-default-with-async-as-an-opt-in-protocol-family)).
- Reads return raw `memoryview`; the codec pipeline wraps via `prototype.buffer.from_bytes` ([return-type subsection](#returning-memoryview-from-store-read-methods)).
- Two protocol families for sync and async; bridging via `SyncToAsync[S]` / `AsyncToSync[S]` wrappers ([sync-by-default subsection](#sync-by-default-with-async-as-an-opt-in-protocol-family)).
- Capability preservation across wrappers via self-type narrowing, verified empirically against pyright and mypy ([lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath)).
- `StorePath` becomes `Prefixed[S]`, a capability-preserving wrapper ([lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath)).
- `_is_open` / `_open` / `_ensure_open` machinery is removed for stateless backends ([lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath)).
- `with_read_only()` becomes the `ReadOnly[S]` wrapper ([lifecycle subsection](#lifecycle-paths-and-the-future-of-storepath)).
- Stores get uniform `__eq__` / `__hash__` / pickling via dataclass-shaped definitions ([equality subsection](#equality-hashing-and-pickling)).
- `LocalStore` regains atomic rename-into-place, restoring V2's per-key atomicity ([transactional proposal](./proposals/stores-transactional.md)).
- Multi-key transactions ship as `Transactional[S]`; OCC backends like Icechunk advertise `TransactionalOCC` ([transactional proposal](./proposals/stores-transactional.md)).
- Range coalescing and caching ship as composable wrappers with concrete defaults and conformance specs ([range-coalescing](./proposals/stores-range-coalescing.md), [caching](./proposals/stores-caching.md)).

**Open questions**

- `ZipStore` lifecycle contract: indefinite lazy-open, deprecation, new parallel store, mode-conditional, or strict flag ([five-option discussion in stores-api.md](./proposals/stores-api.md#open-questions)).
- Concurrent fetch deduplication and object-level caching opt-in flag in `Caching[S]` ([caching open questions](./proposals/stores-caching.md#open-questions)).
- Crash-atomicity for `LocalStore` multi-key transactions ([transactional open questions](./proposals/stores-transactional.md#open-questions)).
- GPU re-coupling escape hatch (additive future option, [stores-api.md open questions](./proposals/stores-api.md#open-questions)).
- Module layout / naming and backwards-compatibility window (decide near implementation time).

**Proposal docs**

- [stores-api.md](./proposals/stores-api.md): the load-bearing protocol surface, backend stubs, wrapper stubs, transactions, migration shims.
- [stores-conformance.md](./proposals/stores-conformance.md): per-capability test specs that backends and wrappers parameterize. The artifact reviewers point at when a PR adds or modifies a backend or wrapper.
- [stores-range-coalescing.md](./proposals/stores-range-coalescing.md): `RangeCoalescing[S]` wrapper, motivating use case for [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925).
- [stores-caching.md](./proposals/stores-caching.md): `Caching[S]` wrapper, replaces `experimental.cache_store`.
- [stores-transactional.md](./proposals/stores-transactional.md): `Transactional` and `TransactionalOCC` protocols, restores V2 atomic rename, gives Icechunk a typed surface.
- [stores-wrappers.md](./proposals/stores-wrappers.md): combined spec for `ReadOnly`, `Retry`, `Tracing`, `SyncToAsync`, `AsyncToSync`, with composition rules and the recommended cloud-Zarr ordering.

**Staged rollout**

1. **Quick wins, zero API change.** `LocalStore` rename-into-place restoration. Ship in a minor release; no protocol work needed; addresses [zarr#3094](https://github.com/zarr-developers/zarr-python/discussions/3094) and [zarr#3410](https://github.com/zarr-developers/zarr-python/discussions/3410) directly.
2. **Capability protocols ship additively.** `Get`, `GetRange`, `GetRanges`, etc., and their `Async` counterparts, alongside the marker protocols `ThreadSafe` and `AsyncSafe`. Conformance suite spec classes ship empty (no assertions yet). Existing `Store` ABC stays. Downstream libraries can adopt protocol-based typing on their side.
3. **Concrete backends grow protocol-based methods alongside the legacy ABC methods.** Each backend keeps its current API and additionally advertises the new protocols, returning `memoryview`. The conformance suite gains assertions; existing per-backend tests migrate one capability at a time.
4. **Wrappers ship.** `ReadOnly`, `Prefixed`, `RangeCoalescing`, `Caching`, `Retry`, `Tracing`, `SyncToAsync`, `AsyncToSync`. Each one ships independently after the protocols and at least one matching backend exist.
5. **`StorePath` deprecation.** `Array.store` and `Group.store` accessors land alongside `Array.store_path` / `Group.store_path` (which become deprecation aliases for the same value). User-facing migration documented.
6. **`Transactional` ships.** First in `MemoryStore` and `LocalStore`. Icechunk migrates to advertising the protocol; reviewers can use `TransactionalOCCSpec` to validate.
7. **Legacy `Store` ABC retires.** After the deprecation window. Final cleanup.

The order is mostly forced by dependencies: protocols before backends, backends before wrappers, wrappers before the migration of `Array` / `Group` accessors. The `LocalStore` rename-into-place fix is independent and ships first as a no-API-change improvement that addresses the most commonly cited V2 → V3 regression.


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
