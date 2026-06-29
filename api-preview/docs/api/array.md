# Arrays

The user-facing array. Indexing, Array-API conformance, region writes, and chunk introspection. There is a **single `Array` class** that holds all the code; async is exposed selectively via `*_async` methods on the IO-bound operations only (there is no separate `AsyncArray`). Source: [lazy-indexing.md](../proposals/lazy-indexing.md), [gpu.md](../proposals/gpu.md), [observability.md](../proposals/observability.md), [coordinated-writes.md](../proposals/coordinated-writes.md).

::: zarr.array.Array
