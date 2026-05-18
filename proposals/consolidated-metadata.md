# Consolidated metadata

> **Status:** stub. For the high-level pitch, see the [parent README](../README.md). The notes below are placeholder content; this proposal awaits expansion.

## Current planning notes

Zarr's "consolidated metadata" pattern bundles the metadata documents for every node in a hierarchy into a single document at the root, so that opening a hierarchy requires one fetch rather than walking the tree. The pattern is essential for performance on high-latency storage (object stores) and is widely used by downstream tools (Xarray, in particular).

Open topics for the 4.0 design:

- Relationship to the new [functional core](./functional-core.md): consolidated metadata is a flat path → node-metadata mapping, a natural fit for `zarr-metadata`'s pure-data layer.
- Representation of codec, dtype, and chunk-grid configurations inside the consolidated document.
- Write-time invalidation semantics; integration with the metadata cache from [performance.md § Caching](./performance.md#caching).
- Migration between V2 and V3 consolidated formats.
