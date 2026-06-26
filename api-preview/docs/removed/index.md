# Removed in 4.0 (legacy)

!!! danger "These surfaces are removed in 4.0.0"
    Everything in this section mirrors the **current 3.x public API that the v4 plan deprecates and then removes in the single, late `4.0.0` major**. They are shown here, with their replacements, so downstream maintainers can plan the jump. None of this is the destination — see the [API reference](../api/index.md) for that, and the [Migration map](../migration.md) for the old → new table.

The plan concentrates *all* breaking removals into `4.0.0`, and only after each replacement has shipped additively across the 3.x line and downstream has had release windows to migrate. The removed surfaces:

- **[Store ABC](stores.md)** — the monolithic `zarr.abc.store.Store` → [capability protocols](../api/store.md).
- **[Codec ABCs](codecs.md)** — async/batched `BaseCodec` family and `CodecPipeline` → the sync-first [`zarr.codec.Codec`](../api/codec.md) bundle.
- **[Buffer / prototype](buffer.md)** — `Buffer` / `NDBuffer` / `BufferPrototype` → the `ReadResult` / `memoryview` contract + `read_into` / `decode_into`.
- **[sync() bridge](sync.md)** — `zarr.core.sync.sync()` → [`AsyncToSync`](../api/store.md) / `zarr.to_sync`.
- **[mode= constructors](constructors.md)** — `open(..., mode=...)` → [explicit constructors](../api/open.md).
- **[Eager indexing](indexing.md)** — eager-default `Array.__getitem__` → lazy default + [`array.eager[...]`](../api/array.md).
- **[StorePath](storage.md)** — `zarr.storage._common.StorePath` → [`Prefixed[S]`](../api/store.md).
- **[donfig config](config.md)** — `zarr.core.config.Config` → the [`zarr.config`](../api/config.md) substrate.
