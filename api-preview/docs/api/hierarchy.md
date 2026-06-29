# Hierarchy verbs

The typed verb set that composes the [store](store.md) API into hierarchy-shaped operations (`read_array_metadata`, `read_chunk`, `read_selection`, region writes, …). This verb set **is** the [engine boundary](engines.md). Every sync verb has an `_async` counterpart; a representative subset of the async variants is shown. Source: [hierarchy-layer.md](../proposals/hierarchy-layer.md), [coordinated-writes.md](../proposals/coordinated-writes.md).

::: zarr.hierarchy
