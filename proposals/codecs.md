# Codecs

> Theme proposal. For the high-level pitch, see the [parent README](../README.md). See also [packaging.md](./packaging.md) for the packaging side of the codec story.

In addition to the packaging issues addressed in [packaging.md](./packaging.md#case-study-codecs), there are a few other pain points related to codecs that we should fix as part of a Zarr Python 4.0 effort:

- The Zarr Python codec API is unwieldy and inefficient.
- Many popular Zarr V2 codecs have no Zarr V3 equivalent.
- The role of the Numcodecs package in the context of Zarr V3 is unclear.

I will expand on these issues individually and propose solutions. One family of solutions takes the form of a total codec class rewrite.

## The codec API is unwieldy and inefficient

The structure of the [`Codec` base class](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/src/zarr/abc/codec.py#L85) in Zarr Python has a few issues worth fixing, which I enumerate here. Many of these issues could be addressed by incremental changes to the existing `Codec` base class, but I propose a more drastic replacement -- a full rewrite of the codec API, with a backwards-compatibility layer.

### Unnecessary async encode / decode routines

*The codec base class defines `encode` and `decode` as asynchronous functions.* 

This design supports the sharding codec, which does IO and thus may benefit from asynchronous execution. But the vast majority of codecs do not do IO. Instead they are CPU-bound routines like data compression. Wrapping these routines in an async layer hurts their performance.

In order to avoid blocking the `asyncio` event loop these routines are run on a thread using `asyncio.to_thread`. The async event loop has to coordinate with a thread pool, which means we are adding at least 2 layers of callbacks for what should be a simple blocking synchronous function call. Multiply this overhead by thousands of chunks and it becomes substantial.

Performance profiling of Zarr Python's codec API routinely flags this unnecessary async layer as a performance bottleneck.

Solution: define `encode` and `decode` as synchronous functions, and define asynchronous `encode_async` / `decode_async` for classes that can make use of this functionality. 

### Abstraction leakage in the encode / decode function signature

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


### The codec abstract base class is not abstract

Our codec abstract base classes are not abstract. They define concrete implementations (e.g., [this example](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/src/zarr/abc/codec.py#L221), which couples a nominally abstract method to the global runtime configuration object). This is an abstraction failure. 

Solution: avoid defining implementations in a data structure that is supposed to be abstract. 

In this case, I think re-writing all our pseudo-abstract base classes as completely abstract, structurally-typed protocols is the right choice. A protocol-based approach would weaken the coupling between Zarr-Python and codec implementations and allow a richer expression of codecs with different capabilities. And a clear separation between interface and implementation will make the codec behavior easier for developers to understand.

### Codecs must allocate memory for their outputs

Each codec allocates its own memory for outputs in `encode` and `decode` operations. This adds substantial overhead to chunk decoding, especially the common case of decoding an entire chunk.

Solution: add `encode_into` and `decode_into` methods that don't allocate output buffers, and instead write into a caller-provided buffer. Combined with a codec context (codec pipeline) that manages buffer allocation, this will offer memory savings and simplify our model of what codecs have to do. 

### Codecs don't know about slicing

When we request 1 scalar from an NxM chunk, we allocate memory for the entire chunk, read and decode the entire chunk, then select the single requested scalar. This is inefficient, compared to pushing the selection down into the chunk decoding process. 

Solution: Formally represent how array -> array codecs transform array indices, and index scalars from arrays mid-decoding as soon as they are available. This would offer a massive reduction in memory use for sub-chunk indexing workloads.

### Codecs don't cache

When the codec pipeline decodes a chunk, it throws that decoded chunk away. This means requesting the same chunk again will trigger the same compute, which is wasteful if the data hasn't changed.

Solution: Array -> Array codecs that decode a full chunk should cache that decoded chunk, and re-use it later when subslices are requested. This is something Zarrs does. Combined with giving codecs a model of array selection (slicing) we can get a huge reduction in compute by spending some memory on a cache.

### We should learn from Zarrs and Tensorstore

There are *many* things we could copy from Zarrs and Tensorstore to improve codec performance.

We should also accept reality: a Python library cannot realistically compete on performance with an optimized Rust or C++ solution. So we should *simply not compete*. Instead, we should wrap Zarrs and Tensorestore for chunk encoding / decoding. That means designing our codec API so that its pluggable over different backends. The `CodecPipeline` class today acheives this somewhat, but using Zarrs as a backend still required a [dedicated Python package](https://github.com/zarrs/zarrs-python/). We should learn from this effort and restructure our codec APIs to make this binding simpler.

Today, we tell people with serious performance demands to use Tensorstore or Zarrs. I would rather tell them to keep using Zarr Python, but with a Tensorstore / Zarrs backend.

## V2 codecs with no V3 equivalent

In the Zarr Python 2.x era, the codec API was extremely simple. Zarr Python got all of its codecs from Numcodecs, which was a separate package due to the special build requirements involved with Cython code. Codecs were also unspecified, which was bad: Zarr developers working in other languages had to study the Numcodecs source code instead of a spec to replicate some of these codecs.

The Zarr V3 spec changed things for the better. Codecs got richer semantics and specification documents. But we never updated Numcodecs to natively support Zarr V3 codecs, in part because the Zarr Python 3.x codec implementation depended on a lot of Zarr Python internals. In retrospect this should have been addressed immediately by spinning out these dependencies into logically separated packages (see [the packaging case study](./packaging.md#case-study-codecs)).

There's no direct translation from a Zarr V2 codec to a Zarr V3 codec, which leaves many Zarr V2 codecs that lack a complete Zarr V3 counterpart.

Solution: write specs and implementations for all these codecs, and invest in tooling to make that process as smooth as possible. Large language models make spec-writing quite a bit easier, and we have plenty of examples in zarr-extensions to use as training data, but for codecs that aspire to implementations in multiple languages, there is a human bottleneck that can't be avoided, as each implementation author has to approve a potential integration.

## The role of Numcodecs is unclear

We want the components of the Zarr ecosystem to be easy for people to understand. Right now, the codec infrastructure is confusing: Numcodecs defines Zarr V2 codecs. Zarr Python imports Zarr V2 codec implementations from Numcodecs, and wraps them in *2 different* Zarr V3 compatibility layers. 

Co-opting Zarr V2 infrastructure in Numcodecs was a good strategy when we were sprinting to release Zarr Python 3.x. But it's not a good long-term strategy for the Zarr ecosystem.

Taken on its own, Numcodecs has a few concerning issues:
- The name "Numcodecs" doesn't convey its connection to Zarr
- Numcodecs bundles together many codecs that people might want individually, leading to an unnecessarily large bundle size.
- Numcodecs only supports the much simpler Zarr V2 codec API. Any use of Numcodecs from Zarr Python 3.x requires adapter layers.
- Numcodecs implements fast codec implementations with Cython. This made sense 10 years ago but is less ergonomic today. Python bindings to C++ and Rust have vastly improved to the point where a dense Cython implementation looks much less attractive than bindings around C++ or Rust libraries.

Solution: we aim to eliminate Zarr-Python's Numcodecs dependency. We can do this while keeping Zarr V2 compatibility easily with adapter logic that maps Zarr V3-compatibles codecs to their Zarr V2 counterparts. Some codecs (like `gzip`) can be defined entirely within Zarr-Python. For other codecs, we should search for well-known, community-maintained packages that provide the basic encoding / decoding functionality, and implement the Zarr V2 codec wrappers in Zarr Python itself.
