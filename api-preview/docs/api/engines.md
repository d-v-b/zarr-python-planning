# Engines

The default pure-Python engine plus opt-in `zarrs` and TensorStore wrappers. An engine implements the [hierarchy verb set](hierarchy.md) end-to-end; alternative engines preserve the `zarr.Array` / `zarr.Group` surface and Xarray/Dask interop. Selected with the `engine=` keyword on `zarr.open(...)`. Source: [performance.md](../proposals/performance.md), [functional-core.md](../proposals/functional-core.md).

::: zarr.engines

::: zarr.engines.python

::: zarr.engines.zarrs

::: zarr.engines.tensorstore
