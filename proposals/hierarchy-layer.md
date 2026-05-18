# The Hierarchy Layer

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

## Summary

Zarr-Python today has three implicit layers: the **store** (key-value bytes), the **codec pipeline** (encoded bytes ↔ decoded chunks), and the user-facing **`Array` / `Group`** facade. The middle ground between "the store" and "the user's `Array`" — the layer that knows about Zarr's *hierarchy semantics* (an array is metadata plus chunks at a path, a group is a set of children, chunks live at coordinates derived from grids and key encodings) — exists, but isn't formalized. It's whatever the `Array` and `Group` classes happen to do, plus whatever the codec pipeline happens to need, plus whatever lives in the `core/sync.py` async bridge.

This proposal **formalizes the hierarchy layer as a small set of typed verbs over the store API**. Verbs like `read_array_metadata(store, path)`, `write_chunk(store, array_path, coords, data, codecs)`, `list_children(store, group_path)` become *the* hierarchy-layer surface. The `Array` and `Group` classes become thin facades that compose those verbs. Alternative engines (`zarrs`, TensorStore) implement those verbs. Hierarchy-aware caching wraps those verbs.

The framing matters because the alternative — informal semantics scattered across `Array`, the codec pipeline, and the metadata classes — is what's currently producing several of the architectural pains the rest of the proposal set is trying to fix. The cache-layering ambiguity that the audit caught is the clearest symptom: the metadata cache *can't* live cleanly at the store layer (the store is key-agnostic) or at the `Array` layer (which doesn't exist when `zarr.open(...)` is reading the root metadata document). It belongs at the hierarchy layer — which, until now, hasn't been a named place.

## What the verbs are

A first-cut set of hierarchy-layer verbs. Names and exact signatures are illustrative; what's load-bearing is **the capability is the verb, not the type that hosts it**.

### Metadata verbs

```python
read_array_metadata(store, path) -> ArrayMetadata
write_array_metadata(store, path, metadata: ArrayMetadata) -> None
read_group_metadata(store, path) -> GroupMetadata
write_group_metadata(store, path, metadata: GroupMetadata) -> None
read_consolidated_metadata(store, root) -> ConsolidatedMetadata | None
```

These translate hierarchy paths into store-key reads/writes of the canonical metadata documents (`zarr.json` in V3, `.zarray` / `.zgroup` / `.zattrs` in V2). The store layer sees the keys; the hierarchy layer knows *which keys mean what*.

### Hierarchy verbs

```python
list_children(store, group_path) -> Iterator[ChildName]
node_exists(store, path) -> bool
node_kind(store, path) -> Literal["array", "group", "absent"]
walk_hierarchy(store, root) -> Iterator[Path]
delete_node(store, path) -> None      # recursive for groups
```

These are the verbs `Group.__iter__`, `Group.__contains__`, and `Group.tree()` decompose into. They know about the V2/V3 layout convention; the store layer just sees `list(prefix=...)` and `delete(key)`.

### Chunk verbs

```python
chunk_key(metadata, coords) -> str
chunk_exists(store, metadata, coords) -> bool
chunk_byte_range(store, metadata, coords) -> StoreByteRange
read_chunk(store, metadata, coords, codecs, selection=None) -> ChunkData
write_chunk(store, metadata, coords, data, codecs) -> None
read_selection(store, metadata, selection, codecs) -> ChunkedOutput
write_selection(store, metadata, selection, data, codecs) -> None
```

These run the codec pipeline over store reads/writes for chunk-shaped data. They are what [lazy-indexing.md § Selection pushdown through the codec pipeline](./lazy-indexing.md#selection-pushdown-through-the-codec-pipeline) and [performance.md § 1](./performance.md#1-concurrency-is-typed-library-owned-and-shared-across-nested-calls) consume. The `selection` argument carries the pushdown.

These are a superset of the four engine functions named loosely in [functional-core.md § A thin imperative shell](./functional-core.md#a-thin-imperative-shell-with-engines-as-namespaces). Making them the engine boundary, plus adding the metadata and hierarchy verbs, is the substantive change here.

### Capability advertisement

Not every implementation supports every verb. A read-only engine omits the write verbs; a metadata-only engine implements only the metadata verbs (this is what `yaozarrs`-style downstream tools would consume from `zarr-metadata`). Capability advertisement follows the same protocol pattern as the store layer ([stores-api.md § Capability protocols](./stores-api.md#capability-protocols)) — each verb is a protocol method on an interface; an implementation declares which protocols it satisfies.

## Why this is a real layer

Three arguments for why the hierarchy layer deserves to be named and specified, rather than left as glue between store and array:

### 1. It has its own knowledge that neither the store nor the array layer can carry

The store layer is key-agnostic by design. Asking it to know that `zarr.json` is metadata, that `c/0/0` is a chunk, or that `group_path/array_name/zarr.json` is the metadata for an array named `array_name` inside `group_path` — that's a layering violation. The Caching wrapper that the audit caught started leaking hierarchy knowledge (via a `metadata_key_pattern` regex) because there was no other place to put it. Naming the hierarchy layer gives that knowledge a home.

The `Array` and `Group` facade layer doesn't carry it either, in the case that matters most: `zarr.open(store, "/")` reads the root metadata document *before* an `Array` or `Group` exists. The hierarchy verbs are what `zarr.open` decomposes into, and they need to operate without an existing facade object.

### 2. It is the natural engine boundary

The [functional-core.md engine architecture](./functional-core.md#a-thin-imperative-shell-with-engines-as-namespaces) currently names four engine functions: `read_chunk`, `read_selection`, `write_chunk`, `write_selection`. That set is the *chunk verbs* from above with the metadata, hierarchy, and group verbs cut. It works for the chunk-read fast path that performance.md cares about, but it doesn't cover what an engine actually needs to do.

A `zarrs` engine that wants to handle "open this group and walk its children" needs the *hierarchy* verbs too, not just the chunk verbs. Otherwise the Python engine does the hierarchy traversal in Python (one round trip per child to read its metadata) and only hands off the chunk reads to `zarrs` — losing most of the benefit. The formal verb set is what makes engines actually replaceable end-to-end.

### 3. Several "missing API" requests are hierarchy verbs in disguise

The chunk-introspection surface in [observability.md § Pillar 2](./observability.md#pillar-2-stored-state-introspection) — `array.chunks`, `chunk_exists`, `chunk_byte_range`, `read_block` — is exactly the chunk verbs, exposed on `Array`. The composite-hierarchy story in [missing-apis.md § 1](./missing-apis.md) (`KvStack` as the answer to "open these stores together") is about *which store the hierarchy verbs run against*. The constructor cleanup in [missing-apis.md § 3](./missing-apis.md) (explicit `open_for_read` / `create` / etc.) is a redesign of how user-facing entry points compose the hierarchy verbs.

Treating these as separate features in separate proposals is fine, but they share a substrate. Naming that substrate clarifies all of them.

## How caching stratifies cleanly

The cache layering question that motivated this proposal becomes mechanical once the verbs exist. Each cache wraps the verbs it can semantically reason about:

| Cache | Wraps | Lives at | Why |
|---|---|---|---|
| Encoded-bytes cache | `store.get`, `store.get_range`, `store.get_ranges` | Store layer | The store knows about bytes-at-keys. No hierarchy knowledge needed. |
| Negative-result cache | `store.get` → `KeyError` | Store layer | Same — key-level negative results. |
| Metadata cache | `read_array_metadata`, `read_group_metadata` | Hierarchy layer | Knows that the cached value is a parsed metadata document, not arbitrary bytes. Can revalidate via ETags on the underlying store call. |
| Decoded-chunk cache | `read_chunk` | Hierarchy layer | The cached value is a decoded chunk array, not bytes. Keyed by `(array_path, chunk_coords)`, not by store key. |
| Shard-index cache | (inside the sharding codec) | Codec layer | The shard index is internal to how the sharding codec evaluates `read_chunk` — invisible above. |
| Partial-decoder cache | (inside the codec chain) | Codec layer | Per-call lifetime; managed by the codec pipeline. |
| In-flight dedup | Substrate (every layer) | Shared substrate | Each layer's cache uses the same substrate's in-flight table. No layering violation; the substrate is below all of them. |

`stores-caching.md`'s `Caching[S]` retreats to the store-layer cases (encoded bytes, negative results) — it stops trying to differentiate metadata from chunks. A new hierarchy-layer cache wrapper handles the metadata and decoded-chunk cases. They compose: a decoded-chunk cache wraps `read_chunk`, which calls `store.get`, which is wrapped by a `Caching[S]` encoded-bytes cache, which talks to the backend. Two cache wrappers, one per layer, no abstraction violation.

The user-facing `with_caching(...)` method (per [performance.md § Default caching policy](./performance.md#default-caching-policy)) exists on *both* backends and on `Array` / `Group`, with different semantics:

- `backend.with_caching(...)` → store-layer cache. Key-agnostic LRU. Useful for "cache anything from S3 for 10 seconds."
- `array.with_caching(metadata=True, chunks=False)` → hierarchy-layer cache. Tier-aware; metadata on by default; chunks opt-in. This is the surface performance.md's default-caching-policy story wants.

The defaults from performance.md (metadata on, chunks opt-in, negative opt-in) apply to the hierarchy-layer cache. The store-layer cache stays opt-in throughout; its `with_caching` on a backend is the lower-level escape hatch.

## What this means for the rest of the proposal set

This proposal **clarifies** several others without invalidating them. Specifically:

- [`functional-core.md`](./functional-core.md). The engine architecture's "four functions" become the chunk verbs from this proposal. The engine interface grows the metadata and hierarchy verbs too. functional-core.md's "engines as namespaces" framing survives; this proposal sharpens what "the namespace exports" means.
- [`stores-caching.md`](./stores-caching.md). `Caching[S]` retreats to a key-agnostic store-layer cache. The tier toggles (`metadata`, `chunks`, `negative`) and the `metadata_key_pattern` knob move out — they become the *hierarchy-layer* cache's surface. The performance.md tier defaults (metadata on, chunks opt-in) apply to that new cache, not to `Caching[S]`.
- [`performance.md`](./performance.md). The caching catalog stays accurate but the placement note grows a clarification: encoded-chunk, shard-index, and negative caches are store-layer; decoded-chunk, metadata, and partial-decoder caches are hierarchy-layer (the last is codec-layer specifically). The substrate is shared across layers; the wrappers aren't.
- [`observability.md` § Pillar 2](./observability.md#pillar-2-stored-state-introspection). The chunk-introspection API list — `array.chunks`, `chunk_exists`, `chunk_byte_range`, `read_block` — *is* the chunk verbs exposed on `Array`. observability.md keeps owning the user-facing surface; this proposal owns the underlying verb set those methods delegate to.
- [`lazy-indexing.md` § Selection pushdown through the codec pipeline](./lazy-indexing.md#selection-pushdown-through-the-codec-pipeline). The selection-pushdown story is "how `read_chunk` evaluates a sub-selection." `read_chunk` is a hierarchy verb; lazy-indexing.md describes its execution semantics.
- [`codecs.md`](./codecs.md). Codecs are still codecs; nothing changes in their API. They become the *implementation* of `read_chunk`'s decode step rather than the implementation of `Array.__getitem__`'s decode step. The mental model is sharper; the code surface is the same.
- [`stores-conformance.md`](./stores-conformance.md). The store-layer conformance suite stays as is. A new hierarchy-layer conformance suite tests the verbs (round-trip metadata, walk hierarchy, write-then-read chunk, etc.) against any implementation that claims to provide them. Engines (`zarrs`, TensorStore) parameterize the same suite.

## What this is not

- **Not a redesign of `Array` or `Group`.** The user-facing facade stays. `Array.__getitem__`, `Group["sub"]`, `zarr.open(...)` all work exactly as today. What changes is the internal decomposition: those facades now call named verbs rather than a mix of internal helpers.
- **Not a new wire format.** The verbs operate on Zarr V2 and V3 stored documents as they exist. No new on-disk objects. (Persisted hierarchy links remain out of scope, per [missing-apis.md § 1](./missing-apis.md).)
- **Not the same as the codec pipeline.** The codec pipeline is what `read_chunk` calls into for the bytes-to-arrays step. The hierarchy layer is *above* the codec pipeline; it orchestrates calls into both the store and the codec pipeline.
- **Not the same as the functional core.** The functional core is the pure-data layer (metadata documents, chunk-grid math, codec configs). The hierarchy layer is one level up — it operates on the pure-data structures plus a live store. The two compose: hierarchy verbs use pure-core functions to figure out *what* to do and call into the store / codec pipeline to *do* it.

## Relationship to other proposals

- [`functional-core.md`](./functional-core.md) — provides the pure-data substrate the hierarchy verbs operate on. The engine-as-module-of-functions framing is sharpened by naming the full verb set here.
- [`stores-api.md`](./stores-api.md) — the lower-layer protocol the hierarchy verbs sit on. Unchanged by this proposal.
- [`stores-caching.md`](./stores-caching.md) — `Caching[S]` retreats to key-agnostic store-layer; the metadata/chunks/negative tiers move to a new hierarchy-layer cache wrapper specified here. Requires a coordinated edit.
- [`codecs.md`](./codecs.md) — codecs become the implementation of `read_chunk`'s decode step. No API changes; framing clarification.
- [`lazy-indexing.md`](./lazy-indexing.md) — selection pushdown is the execution semantics of `read_chunk` when called with a `selection` argument.
- [`observability.md`](./observability.md) — the chunk-introspection user-facing API is the chunk verbs surfaced on `Array`.
- [`performance.md`](./performance.md) — the caching catalog gets a placement clarification (store-layer vs. hierarchy-layer vs. codec-layer caches); the typed concurrency resources apply to hierarchy-verb execution the same way they apply to codec execution.
- [`missing-apis.md`](./missing-apis.md) — constructor and lifecycle redesign composes the hierarchy verbs at user-facing entry points (`zarr.open_for_read` etc.). Composite-hierarchy via `KvStack` works because the verbs operate on whatever store they're handed.

## Open questions

- **Verb naming.** The names above (`read_array_metadata`, `write_chunk`, etc.) are illustrative. The convention — verb-prefix style (`read_*`, `write_*`) vs. noun-method style — needs a small design pass. Whatever convention lands, it should be consistent across the verb set.
- **Where the verbs physically live.** Module-level functions in a `zarr.hierarchy` package? Methods on an `Engine` protocol? A `HierarchyOps` class injected into `Array` / `Group`? Each has tradeoffs (functions are simplest, methods are easiest to extend per-engine, injected classes are easiest to test). Defer until the implementation PR; the *semantics* are the proposal, the dispatch mechanism is implementation.
- **Granularity of the `read_selection` verb.** It's a coarser verb than `read_chunk`; the planner (per lazy-indexing.md) consumes it directly. Whether `read_selection` is a *defined* verb at this layer (engines implement it as a primitive) or a *derived* operation (engines implement `read_chunk`; `read_selection` is sugar over chunk iteration) is the same question TensorStore answers via its `IndexTransform` machinery. We probably want both — engines that can do `read_selection` primitively (TensorStore, `zarrs`) advertise it; engines that can't (a simple Python engine) get a derived implementation that calls `read_chunk` repeatedly.
- **Hierarchy-layer conformance suite.** Mirrors [stores-conformance.md](./stores-conformance.md) in shape: per-verb spec classes, parameterized over engines and over backing-store fixtures. Out of scope for this proposal; expected as a follow-on once the verbs are settled.
- **Transactional semantics across verbs.** A multi-verb operation (write metadata + write chunks) wants atomicity. Today this rides on `Transactional[S]` at the store layer ([stores-transactional.md](./stores-transactional.md)); the hierarchy layer needs to surface "open a transaction" as a verb that wraps the underlying store transaction. The shape of that wrapper is open.
- **Async variants.** Same story as the store layer (`stores-api.md`): every sync verb gets an `Async` variant; the sync/async bridge wrappers cross between them. Naming and dispatch mirror what's already specified for the store layer.
