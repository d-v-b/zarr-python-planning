# Device-agnostic IO (and what that buys us for GPUs)

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

## Summary

The goal of this work is **not** to add GPU support to `zarr-python` as a feature. The goal is to make Zarr-Python's IO surfaces *device-agnostic* — to stop assuming that the destination of a read is a CPU buffer or that the source of a write is one. GPU support falls out for free once the assumption is removed.

The framing matters because the alternative — "let's add a GPU mode" — leads to special-cased code paths, a `prototype: BufferPrototype` knob the user has to set correctly, and a feature surface that grows linearly in the number of devices we choose to support. The device-agnostic framing leads to a small set of capabilities (stores and codecs that write into a caller-provided buffer; an Array facade that returns array-like objects in the caller's preferred namespace) that work for GPUs, for `pyarrow` buffers, for shared-memory buffers, for whatever the user shows up with. We do not enumerate devices; we accept any compliant target.

## The problem with today's GPU story

The current `prototype: BufferPrototype` mechanism is the existing answer to "how does the caller specify a non-CPU destination buffer?" and it's not a working answer:

- The README's `BufferPrototype` discussion in [stores.md](./stores.md#decoupling-prototype-from-the-read-api) explicitly acknowledges that the GPU path is *fictional* in current zarr-python — even with `gpu_buffer_prototype`, the bytes hit the CPU first because neither fsspec nor obstore knows how to allocate on the device. The knob does not actually wire up to the underlying IO.
- Every store read method is required to take a `prototype` argument that almost no call site uses non-defaultly. The variability the parameter was supposed to enable is barely exercised in core code.
- Where `prototype` *does* matter (binding `ArraySpec.prototype` at decode time), it's the codec pipeline reading from `ArraySpec`, not a per-call store argument. The store layer carries the parameter without using it.

The conclusion in stores.md ([§ Decoupling `prototype` from the read API](./stores.md#decoupling-prototype-from-the-read-api)) is to remove `prototype` from the store layer. That's right — but it leaves the underlying question (how does the library serve a non-CPU caller?) unanswered. This proposal answers it.

## The shape: capabilities for caller-provided destinations

Two surfaces gain the capability to write into a caller-provided destination. Both are already in scope for non-GPU reasons; the device-agnostic framing follows naturally.

### Stores: `read_into(key, buffer)` and friends

The store layer grows a streaming-read surface that takes a caller-provided writable buffer and fills it ([`GetStreaming` in stores-api.md](./stores-api.md#streaming-and-caller-allocated-reads-via-getstreaming)). The contract:

- The buffer is **caller-owned**. The store does not allocate, does not retain a reference past the call, and does not modify bytes past the written prefix.
- The buffer is **any object that satisfies the buffer protocol** (or the equivalent device-side protocol, e.g. CUDA Array Interface, DLPack). The store does not introspect what the buffer *is*; it just calls `read_into` on it. A `bytearray`, a `numpy.ndarray`, a `cupy.ndarray`, a `torch.Tensor` on GPU, a shared-memory segment — all work the same way.
- The contract is documented in terms of byte counts and prefix-writing, not in terms of device. The store reports how many bytes were written; the caller knows where they went because the caller provided the buffer.

This is what stores-api.md's `GetStreaming` already specifies. The non-GPU motivations (large objects that exceed memory, pipelined decode, zero-copy slicing) drive the design; the GPU case is the same design used with a device-side buffer.

### Codecs: `decode_into(buffer, spec)`

The codec layer grows a corresponding capability ([codecs.md § Codecs must allocate memory for their outputs](./codecs.md#codecs-must-allocate-memory-for-their-outputs)): every codec exposes a `decode_into(buffer, spec)` method that writes the decoded output into a caller-provided destination. Most `numcodecs` C-level codecs already support this internally; surfacing it requires only that the new codec API include the capability flag and the method.

The same caller-owned, device-agnostic contract applies: the codec writes bytes into the buffer the orchestrator provided. The orchestrator decides what *kind* of buffer that is — a numpy view into a chunk of a CPU output array, a CuPy view into a device array, a slice of a pre-allocated zero-copy region. The codec itself sees one shape.

For codec implementations that *do* have device-specific paths (nvCOMP for GPU decompression, future Apple Silicon-specific codecs), the capability framework supports advertising them: a `decode_into` implementation that requires a CUDA-resident buffer raises a structured error when handed a CPU buffer, and the orchestrator picks a codec implementation that matches the destination. This is the same pattern as `recommended_concurrency` and `PartialDecodeCapability` — the codec advertises what it can do; the pipeline routes accordingly.

### The Array facade: Array API conformance

The third piece is the user-facing layer. The lazy-indexing proposal commits to [Array API standard conformance](./lazy-indexing.md#array-api-conformance), which is the standard interface for "give me an array in whatever namespace I asked for." The user materializes a lazy view by saying which namespace they want; the materialization returns an array in that namespace.

```python
# CPU default — backwards compatible.
arr = np.asarray(view)

# Device-resident output via the Array API namespace.
arr = view.to_device("cupy")          # or torch, or jax, etc.
```

Inside the library, this is "allocate an output array of the right shape in the user-specified namespace, then pass slices of it into the orchestrator as the destination buffers." The orchestrator hands those slices to `decode_into`. No GPU-specific code path; the destination namespace is a parameter, not a branch.

## How GPU support falls out

With those three pieces in place, GPU support is **the case where the user-specified namespace is a GPU array library** (CuPy, PyTorch with CUDA, JAX with a GPU backend). No new code paths. No new capability protocols. The library doesn't know the destination is on a GPU; it just calls `read_into` on a buffer that happens to be device-resident and `decode_into` on a target that happens to be device-resident.

The remaining GPU-specific work is small and bounded:

- **CUDA Array Interface and DLPack support in the buffer-protocol abstraction.** The store and codec layers need to handle objects that satisfy CAI/DLPack rather than the CPU buffer protocol. This is a one-time recognition layer, not a per-call branch.
- **CUDA streams** ([zarr#3271](https://github.com/zarr-developers/zarr-python/issues/3271)). Optional opt-in: a user can pass a CUDA stream to a read/write call, and the store/codec layers propagate it to underlying device operations. Without a stream, the default stream is used. The capability is named in the existing typed-concurrency model as a future addition to `IoConcurrency` resources.
- **GPU-aware codec implementations.** Independent of the library work — these live in third-party packages (nvCOMP bindings, etc.) and plug in via the codec capability system. `zarr-python` ships none of them; downstream users install what they need.

The work `zarr-python` actually owns is mostly the framing and routing — making sure no library-internal code assumes CPU destinations, and that the capability surfaces (`read_into`, `decode_into`, `to_device`) compose. Once that's done, GPU is one of N possible destinations, with no special status.

## What this enables

- **GPU pipelines that don't round-trip through CPU.** A user reading a Zarr array directly into a CuPy buffer for downstream CUDA work no longer pays the CPU bounce. The bytes go from store → device buffer → decode-in-place → CuPy array, with no CPU copy.
- **Library-independent device interop.** A user mixing CuPy, PyTorch, and JAX in the same pipeline doesn't need three different code paths into Zarr-Python. The Array API namespace is the parameter.
- **Future devices for free.** TPUs via JAX, MLX on Apple Silicon, anything with a buffer-protocol-equivalent and an Array API namespace — supported by virtue of being supported by the array library the user picked. No `zarr-python` release needed.
- **The CPU path gets faster too.** `decode_into` plus pre-allocated CPU output buffers (per [performance.md § 5](./performance.md#5-decode_into-is-non-negotiable)) eliminates per-chunk allocation on CPU reads. This is the largest single benefit of the device-agnostic framing — most users will see it without ever touching a GPU.

## What this is not

- **Not a commitment to ship a GPU codec.** Codec implementations for GPU live in third-party packages; `zarr-python`'s contribution is the capability framework that lets them plug in cleanly.
- **Not GPU-specific code paths in the library.** If a routine has a `if device == "cuda":` branch, that's a sign we're doing it wrong. The branches should be at the capability boundary (does this codec advertise `decode_into` for the destination's namespace?), not at the device-type boundary.
- **Not Array API conformance only for the GPU case.** Array API conformance is owned by [lazy-indexing.md](./lazy-indexing.md) and is in scope regardless of GPU. This proposal depends on it but does not duplicate the work.
- **Not a replacement for downstream GPU libraries.** Dask-CUDA, cuML, and similar projects are not consumers of this work in any deep sense; they're examples of pipelines users assemble around Zarr-Python, which will work better when Zarr-Python stops forcing a CPU bounce.

## Relationship to other proposals

- [`stores-api.md` § `GetStreaming`](./stores-api.md#streaming-and-caller-allocated-reads-via-getstreaming) — the store-side capability is already specified there. The section is named "Streaming and caller-allocated reads" to reflect the device-agnostic framing; GPU support is one worked example inside it.
- [`codecs.md` § Codecs must allocate memory for their outputs](./codecs.md#codecs-must-allocate-memory-for-their-outputs) — the codec-side capability. The proposal's framing (`decode_into` for performance) is exactly the framing this proposal needs for device support; no separate work.
- [`lazy-indexing.md` § Array API conformance](./lazy-indexing.md#array-api-conformance) — the user-facing namespace selection mechanism. Materialization through an Array API namespace is what makes GPU outputs a one-line user request.
- [`performance.md` § 5: `decode_into` is non-negotiable](./performance.md#5-decode_into-is-non-negotiable) — the performance motivation for the codec capability. The GPU motivation is a strictly weaker version of this one; the work ships for performance reasons regardless.
- [`functional-core.md`](./functional-core.md) — the engine architecture means GPU-specific work can live in an alternative engine (e.g. `zarr.engines.cuda`) without polluting the default Python engine. The capability framework here is what makes such an engine implementable.

## Open questions

- **DLPack vs CUDA Array Interface vs custom protocol.** Both DLPack and CAI exist; the Array API standard prefers DLPack but CuPy and PyTorch both support both. The library needs to accept whichever the destination buffer satisfies. The pragmatic answer is "we recognize both," but the cost of doing so cleanly is real.
- **Stream propagation through the engine boundary.** When an alternative engine (e.g. a future `zarr.engines.cuda`) takes over IO, CUDA streams need to cross the engine boundary too. The shape of that propagation is open; likely it's a parameter on the engine's `read_chunk`/`read_selection` functions, but the details depend on what engines turn out to need.
- **Whether `read_into` and `decode_into` should be the *primary* surfaces.** Today's specs treat them as opt-in capabilities, with allocation-based methods (`get` returning a `ReadResult` with a `memoryview`) as the default. An alternative framing would make caller-allocated the default and the allocating versions sugar over it. This is a question for the next round of design once the capability machinery is built; flagged here for revisit.
- **Performance ceiling without library-side GPU code.** With third-party GPU codecs and `to_device` materialization, how close can we actually get to native-CuPy throughput on a Zarr read? Worth benchmarking once the capabilities ship.

## Tracking issues

- [zarr#2658](https://github.com/zarr-developers/zarr-python/issues/2658) — Core device abstraction
- [zarr#3271](https://github.com/zarr-developers/zarr-python/issues/3271) — CUDA streams and devices
- [zarr#2199](https://github.com/zarr-developers/zarr-python/issues/2199), [zarr#2473](https://github.com/zarr-developers/zarr-python/issues/2473) — Buffer / array_api alignment
