# The Zarr stack

The v4 work re-shapes `zarr-python` from a monolith into seven levels, each of which is independently dependable, conformable, and replaceable. In the real plan each level becomes a focused package (`zarr-metadata`, `zarr-store`, `zarr-codec`, `zarr-dtype`, …) re-exported through the `zarr` facade. In this preview they are submodules of one importable `zarr` package, but the boundaries are the same.

| # | Level | Module in this preview | Notes |
|---|---|---|---|
| 1 | **Conventions** | *(out of scope here)* | Domain schemas (OME-NGFF, GeoZarr) built on top of Zarr. |
| 2–3 | **Groups & Arrays** | [`zarr.Array`](api/array.md), [`zarr.Group`](api/group.md) | The user-facing facade; lazy indexing and Array-API conformance live here. |
| 4 | **Chunk decoding** | [`zarr.codec`](api/codec.md) | A small stateless capability bundle; also the engine seam. |
| 5 | **Chunk addressing** | [`zarr.metadata`](api/metadata.md) | Chunk grids and key encodings as pure data. |
| 6 | **Stores** | [`zarr.store`](api/store.md) | Capability protocols + composable wrappers, not one ABC. |
| 7 | **Metadata** | [`zarr.metadata`](api/metadata.md) | Pure data documents; the bottom of the dependency graph. |

Two cross-cutting layers stitch the levels together:

- **[Hierarchy verbs](api/hierarchy.md)** (`zarr.hierarchy`) — a typed verb set (`read_array_metadata`, `read_chunk`, `read_selection`, …) that composes the store API into hierarchy-shaped operations. This verb set *is* the [engine boundary](api/engines.md).
- **[Engines](api/engines.md)** (`zarr.engines`) — the default pure-Python engine plus opt-in `zarrs` and `tensorstore` wrappers that implement the verbs against compiled-language backends while preserving the `zarr-python` surface.

Supporting modules: [`zarr.concurrency`](api/concurrency.md) (typed concurrency resources), [`zarr.observability`](api/observability.md) (metrics + tracing + chunk introspection), [`zarr.config`](api/config.md) (the donfig replacement), and [`zarr.exceptions`](api/errors.md) (the typed error hierarchy).
