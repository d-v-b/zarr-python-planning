# Migration map

The single breaking release in the v4 plan is `4.0.0`, which removes a small set of surfaces *after* their additive replacements have shipped across the 3.x line and downstream has had release windows to adapt. This page maps each removed surface to its replacement. The removed surfaces are stubbed under [Removed in 4.0](removed/index.md); their replacements are in the [API reference](api/index.md).

| Removed in 4.0.0 (3.x surface) | Replaced by | Migration |
|---|---|---|
| `zarr.abc.store.Store` ABC ([stub](removed/stores.md)) | [`zarr.store`](api/store.md) capability protocols (`Get`, `GetRange`, `Put`, …) + `ReadResult` / `Generation` | Implement only the capability protocols your backend supports; compose `Caching`, `RangeCoalescing`, `Retry` wrappers instead of subclassing one ABC. |
| `RangeByteRequest` / `OffsetByteRequest` / `SuffixByteRequest` ([stub](removed/stores.md)) | `get_range(..., start=, end=, length=)` keyword args on [`GetRange`](api/store.md) | Pass byte ranges as keyword arguments rather than request objects. |
| `zarr.abc.codec` `BaseCodec` / `ArrayArrayCodec` / `ArrayBytesCodec` / `BytesBytesCodec` / `CodecPipeline` ([stub](removed/codecs.md)) | [`zarr.codec.Codec`](api/codec.md) — one sync-first bundle | Implement `encode`/`decode` (single-element, sync) plus optional `decode_into`; advertise `recommended_concurrency` and `partial_decode_capability`. |
| `ArrayBytesCodecPartialDecodeMixin` / `PartialEncodeMixin` ([stub](removed/codecs.md)) | `PartialDecodeCapability` flags on [`zarr.codec.Codec`](api/codec.md) | Advertise partial capability via the flag instead of a mixin. |
| `Buffer` / `NDBuffer` / `BufferPrototype` / `default_buffer_prototype` ([stub](removed/buffer.md)) | The `ReadResult` / `memoryview` read contract + `read_into` / `decode_into` + Array-API namespace selection | Read returns a `memoryview`; choose an output namespace at materialization (`array.to_device(...)`) rather than threading a prototype. |
| `zarr.core.sync.sync()` ([stub](removed/sync.md)) | [`zarr.store.AsyncToSync`](api/store.md) / `zarr.to_sync` | Wrap an async store with `AsyncToSync`, or use the public `zarr.to_sync` bridge. |
| `mode=`-taking `open` / `open_group` / `open_array` ([stub](removed/constructors.md)) | Explicit constructors: [`open_for_read`](api/open.md), [`create`](api/create.md), [`create_or_overwrite`](api/create.md), [`open_or_create`](api/open.md) | Replace `mode="r"` / `"w"` / `"a"` / `"w-"` with the constructor naming your intent. |
| Eager-default `Array.__getitem__` ([stub](removed/indexing.md)) | Lazy default + [`array.eager[...]`](api/array.md) escape hatch | Bare indexing becomes lazy *if* the conformance decision flips (see the [decision-point note](api/array.md)); use `.eager[...]` for an explicit immediate read. |
| `zarr.storage._common.StorePath` ([stub](removed/storage.md)) | [`zarr.store.Prefixed[S]`](api/store.md) | Use the `Prefixed` wrapper (and `store / "sub"`) for prefix navigation. |
| `zarr.core.config.Config` (donfig) ([stub](removed/config.md)) | [`zarr.config`](api/config.md) substrate | Same namespaced keys and `ZARR_*` env overrides; donfig is retired. |
