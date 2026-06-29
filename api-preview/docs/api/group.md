# Groups

Hierarchical organization of arrays and subgroups, with traversal and display helpers. A **single `Group` class** holds all the code; async is exposed selectively via `*_async` methods on the IO-bound traversal and creation operations only (there is no separate `AsyncGroup`). Source: [missing-apis.md](../proposals/missing-apis.md), [hierarchy-layer.md](../proposals/hierarchy-layer.md).

::: zarr.group.Group
