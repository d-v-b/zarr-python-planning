# API reference (v4 final state)

The public Zarr-Python API as projected after the v4 plan lands. Organized by the [Zarr stack](../stack.md).

!!! warning "Projected, unreleased API"
    Stubs only — no behavior. Signatures marked `(inferred)` are not given verbatim in the proposals.

## Groups & arrays
- **[Arrays](array.md)** — `zarr.Array` (single class; async via selective `*_async` methods), including lazy/eager indexing, Array-API conformance, region writes, and chunk introspection.
- **[Groups](group.md)** — `zarr.Group` (single class; async via selective `*_async` methods), hierarchy navigation and traversal.
- **[Creating arrays & groups](create.md)** — explicit constructors that replace `mode=`.
- **[Opening hierarchies](open.md)** — `open`, `open_for_read`, `open_or_create`, `open_nodes`, ZEP-8 URLs.

## The stack
- **[Metadata](metadata.md)** — pure-data documents and chunk-addressing helpers.
- **[Data types](dtype.md)** — the dtype system and ML dtypes.
- **[Codecs](codec.md)** — the sync-first codec capability bundle.
- **[Stores](store.md)** — capability protocols, backends, and composable wrappers.
- **[Hierarchy verbs](hierarchy.md)** — the typed engine boundary.
- **[Engines](engines.md)** — default Python, `zarrs`, and TensorStore engines.

## Cross-cutting
- **[Concurrency](concurrency.md)** — typed `ComputeConcurrency` / `IoConcurrency`.
- **[Observability](observability.md)** — metrics, tracing, introspection.
- **[Configuration](config.md)** — the namespaced config substrate.
- **[Errors](errors.md)** — the typed exception hierarchy.
