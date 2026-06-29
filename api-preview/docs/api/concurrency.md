# Concurrency

Typed, library-owned concurrency resources with per-call budgets that strictly shrink down the call stack. The defaults are dask-safe: a single shared process-global pool per resource, conservative when nested inside an outer scheduler. Source: [performance.md](../proposals/performance.md).

::: zarr.concurrency
