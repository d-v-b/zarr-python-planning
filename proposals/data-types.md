# Data types

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

## Summary

Zarr-Python's data-type system currently covers NumPy's built-in dtypes well and not much else. The gap that matters most for the next year of users is **ML-specific dtypes** — `bfloat16`, the various low-precision floats (`float8_*`), `int4`, and so on. These dtypes are essential for ML workloads (training checkpoints, inference weights, intermediate activations), already standardized in the wider ecosystem via Google's [`ml_dtypes`](https://github.com/jax-ml/ml_dtypes) package, but unsupported in Zarr-Python today.

This proposal commits to first-class support. The mechanism is straightforward: either `ml_dtypes` becomes an optional dependency of `zarr-python` (lighter delta, single package), or the definitions live in a separate `zarr-ml-dtypes` package (cleaner separation, one more package to publish). Either way, users get to store and read these dtypes through the same APIs as everything else.

The broader data-type work — ragged arrays, vlen strings, dtype/codec interactions, registry issues — is also in scope but treated as follow-on work, building on the `zarr-dtype` substrate from the foundation work (Stream 1 · M1 structural refactor). ML dtypes are the load-bearing case because they unblock a specific, large, growing user community (ML practitioners using Zarr for model weights and training data) that Zarr-Python is currently failing.

## The problem

ML workloads have settled on a handful of low-precision dtypes that aren't in NumPy's core type system:

- **`bfloat16`** — the bfloat16 brain-float format, ubiquitous in deep learning training. PyTorch, JAX, and TensorFlow all support it natively; Zarr-Python does not ([zarr#2656](https://github.com/zarr-developers/zarr-python/issues/2656)).
- **`float8_e4m3fn`, `float8_e5m2`, and other float8 variants** — used for inference and increasingly for training on newer hardware (H100, TPU v5).
- **`int4`, `uint4`** — packed sub-byte integer types for quantized model weights.

The ML ecosystem standardized on Google's [`ml_dtypes`](https://github.com/jax-ml/ml_dtypes) package as the canonical NumPy extension for these types. JAX, TensorFlow, and many downstream tools depend on it. Users wanting to store ML model checkpoints in Zarr — for training-snapshot interop, model-zoo distribution, or any other reason — hit the dtype-not-supported wall immediately.

The workarounds users adopt today (storing as `uint8` or `uint16` with manual reinterpretation) lose round-trip safety: a stored array no longer carries enough information to tell a reader what it actually is.

## The direction

Two coherent options for where the dtype definitions live:

**Option A: `ml_dtypes` as an optional dependency of `zarr-python`.** When the user has `ml_dtypes` installed, `zarr-python` recognizes its dtypes and round-trips them through metadata correctly. The dependency is opt-in (no impact on users who don't need ML dtypes). The lightest delta to ship.

**Option B: separate `zarr-ml-dtypes` package.** A focused package that depends on both `zarr-dtype` (per the [functional-core packaging plan](./functional-core.md#concrete-packaging-plan)) and `ml_dtypes`, and registers the ML dtypes with Zarr-Python's dtype registry. Cleaner separation; one more package to publish and version-coordinate.

The two options are close in cost. **Recommendation: Option A** unless the dependency footprint of `ml_dtypes` (its own transitive dependencies, install size) turns out to be unacceptable as an optional in `zarr-python`. The deciding question is whether `ml_dtypes` is well-behaved enough as a dependency to live inside `zarr-python`'s optional-extra surface; it appears to be (small, pure-Python plus a small C extension, narrow scope) but worth checking before committing.

Either way, the user-facing story is the same: install `zarr[ml]` (or `zarr-ml-dtypes`), and the ML dtypes work end-to-end through `Array` and `Group` APIs.

## Other data-type gaps (follow-on work)

The same dtype infrastructure work should address these, but they ship as subsequent 3.x minors (Stream 1) after the ML dtypes:

- **Ragged arrays** ([zarr#2618](https://github.com/zarr-developers/zarr-python/issues/2618)) — variable-length elements per index. Useful for sequence data, sparse arrays, text. Requires extending the metadata schema, not just adding a type.
- **Variable-length strings** ([zarr#3102](https://github.com/zarr-developers/zarr-python/issues/3102)) — first-class support for `str` and `bytes` data without per-element length-prefix gymnastics.
- **Dtype-codec interactions** ([zarr#3491](https://github.com/zarr-developers/zarr-python/issues/3491)) — some codecs depend on dtype shape (bit width, endianness); the interaction surface needs to be clean.
- **Dtype registry issues** ([zarr#3117](https://github.com/zarr-developers/zarr-python/issues/3117), [zarr#3282](https://github.com/zarr-developers/zarr-python/issues/3282)) — adding a new dtype today requires touching too many places; the registry shape should support clean extension.

The mechanism in the [`zarr-dtype` package](./functional-core.md#the-packages) — pure-data dtype descriptions plus a registry — is the substrate for all of these. Once `zarr-dtype` is extracted from the rest of `zarr-python`, adding a new dtype family becomes a small additive change to that package rather than a refactor of the array core.

## Investigation: Arrow as a substrate for non-numerical dtypes

The data-type gaps that ML dtypes don't fix — nullable scalars, variable-length strings, structured / nested types, ragged data — are all things [Apache Arrow](https://arrow.apache.org/) handles natively. Arrow has a well-defined columnar memory format, first-class null masks, variable-length and nested types as primitive constructs, and a stable cross-language data model used by Polars, DuckDB, Parquet, Iceberg, and most of the modern analytical-data stack. Many of the dtypes Zarr-Python users have been asking about for years are *easy* in Arrow and *hard or impossible* in NumPy.

This proposal **commits to investigating how to integrate Arrow data structures with Zarr-Python**, without committing to a specific shape of integration. The investigation is itself the deliverable.

### What we know is true

- **Arrow does not conform to the Python [Array API standard](https://data-apis.org/array-api/latest/)**, and is not on a path to. Arrow's data model is *columnar/tabular* (1-D typed arrays, possibly nested), not *n-dimensional numerical*. The framing that worked for the [device-agnostic IO proposal](./gpu.md) — "Arrow is just another Array API namespace" — does not work. Arrow has to be integrated as a separate kind of materialization target, not via `__array_namespace__`.
- **The interop primitives exist.** Arrow buffers satisfy the Python buffer protocol; Arrow has a stable C Data Interface for zero-copy cross-library handoff; pyarrow's `Array` constructors accept buffer-protocol inputs without copying. The plumbing for "give me this Zarr chunk as a pyarrow.Array" is not novel infrastructure.
- **The dtype gap is real and not addressable any other way.** Nullable `int`, vlen `str`, struct types, list-of-struct — these are not expressible in NumPy without losing round-trip safety. ML dtypes (the focus above) cover one large user community; Arrow types would cover the next one (the analytical / tabular data community), plus give us a clean answer to long-standing requests like [tabular data in Zarr](https://github.com/zarr-developers/zarr-python/issues/149).

### What we don't know

These are real open questions, not rhetorical ones:

- **What's the user-facing surface?** Is it a `arr.to_arrow()` method? A `materialize(format="arrow")` argument on lazy views? A separate `pyarrow_array(zarr_array)` factory? Something else?
- **How deep does Arrow go?** Is it only a materialization target (NumPy stays internal; Arrow is just an output format)? Or do Arrow types become first-class in stored Zarr data (Arrow buffers persisted, null masks stored, vlen offsets in the chunk format)? These are very different scopes.
- **What's the metadata story?** A Zarr array whose stored data is "nullable int32" needs a metadata identifier for the type. The Zarr V3 spec doesn't have one. This is cross-implementation work — a Zarr Enhancement Proposal at minimum — and ours alone to drive.
- **How do codecs interact?** Lossless codecs (blosc, gzip) don't care about array shape, so they work on Arrow buffers as-is. Codecs that *do* care — endian, delta, transpose — would need Arrow-aware implementations or a clear "Arrow types skip these codecs" rule.
- **What does this mean for the engine boundary?** zarrs and TensorStore are NumPy-shaped. If a Zarr array has Arrow dtypes, can the zarrs or TensorStore engines handle it, or does the user fall back to the Python engine? Probably the latter, but worth being explicit.

### What we commit to

The Arrow investigation ships as M2 (Stream 1): an **investigation document** (likely `proposals/arrow-integration.md` once it exists) that catalogs the design space, prototypes the smallest useful end-to-end path (probably a `to_arrow()` materialization for nullable-int and vlen-string types), and identifies which questions can be answered without spec work and which need a ZEP.

Beyond that: depending on what the investigation finds, either a focused proposal that ships specific integration features as subsequent 3.x minors (Stream 1), or a deferred-with-reasoning note explaining what we learned and why we held off.

The honest framing: **investigating the right way to integrate Arrow with Zarr is itself a valuable project**, even if the answer turns out to be "the right way is small" or "not yet." Committing to the investigation is a deliverable; committing to a specific design we don't have evidence for is overreach.

## Relationship to other proposals

- [`functional-core.md` § Concrete packaging plan](./functional-core.md#concrete-packaging-plan) — names `zarr-dtype` as a focused package that ships pure dtype definitions independently of the rest of `zarr-python`. This proposal commits to the contents of that package growing the ML-dtype support.
- [`codecs.md`](./codecs.md) — dtype-codec interactions ([zarr#3491](https://github.com/zarr-developers/zarr-python/issues/3491)) are partly a codec-API concern; the new codec API needs to handle dtype-dependent codecs cleanly.
- [`observability.md` § Pillar 2](./observability.md#pillar-2-stored-state-introspection) — public `ArrayV3Metadata` exposes dtype information; the new ML dtypes need to round-trip through that surface.

## Open questions

- **Option A vs Option B** (single optional dependency vs separate package). Recommendation is Option A; verify `ml_dtypes` is well-behaved as a dependency before committing.
- **Which ML dtypes ship in the first additive 3.x minor (Stream 1 · M0)** vs which can wait. `bfloat16` is non-negotiable. The float8 variants and int4/uint4 should land in the same release; they all live in the same `ml_dtypes` package, so the cost is uniform once the integration is built.
- **Metadata schema for ML dtypes.** Zarr V3 uses string-based dtype identifiers, and **most of these are already registered in [`zarr-extensions`](https://github.com/zarr-developers/zarr-extensions)** (`bfloat16`, `int4`, `uint4`, and the `float8_*` family, each with an exact name, fill-value encoding, and byte layout). The conformance obligation is therefore to emit those *exact* registered identifiers, not to coin new spellings — an unknown dtype string is a hard open failure per the V3 spec (there is no graceful-ignore path for dtypes), so a single spelling drift turns "readable by tensorstore" into "unreadable everywhere." The one common ML type **not** yet registered is `float8_e4m3fn` (the OCP FP8 E4M3 used on H100/TPU and by PyTorch/JAX); registering it in `zarr-extensions` is a prerequisite cross-repo PR before zarr-python can write it. Any spec coordination beyond adopting the registered identifiers (e.g. new variants) goes through a [ZEP](https://zarr.dev/zeps/).
- **Hardware-specific variants** (e.g. NVIDIA's `e4m3` vs `e4m3fn` differ in NaN handling). The `ml_dtypes` package distinguishes these; the metadata identifiers need to too.
- **The Arrow investigation** (see the dedicated section above) has its own set of open questions — user-facing surface, depth of integration, metadata schema, codec interaction, engine boundary. Those are by definition unresolved; the investigation is what resolves them.
