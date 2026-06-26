# Buffer / prototype (removed in 4.0)

The `Buffer` / `NDBuffer` / `BufferPrototype` read contract and `default_buffer_prototype`. **Replaced by** the `ReadResult` / `memoryview` read contract plus `read_into` / `decode_into` and Array-API namespace selection at materialization. Source: [gpu.md](../proposals/gpu.md), [stores.md](../proposals/stores.md).

::: zarr_legacy.abc_buffer
