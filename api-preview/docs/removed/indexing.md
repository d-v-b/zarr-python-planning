# Eager indexing (removed in 4.0)

The eager-default `Array.__getitem__` that performs IO immediately and returns NumPy. **Replaced by** the lazy default plus the [`array.eager[...]`](../api/array.md) escape hatch — eager *access* remains available, but the eager *default* is removed (and only if the Array-API conformance decision flips; see the decision-point note on `Array.__getitem__`). Source: [lazy-indexing.md](../proposals/lazy-indexing.md).

::: zarr_legacy.array
