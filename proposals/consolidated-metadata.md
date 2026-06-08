# Consolidated metadata

> **Status:** the *design pass* is in scope for the foundation work (M1) and is **spec/ZEP-routed** — consolidated metadata is a *format* decision, not a library-internal one. It appears nowhere in the [Zarr V3 core spec](https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html) and is unread by tensorstore, zarrs, zarr-js, n5, and GDAL, so any V3 stored representation must go through a spec PR/ZEP, and the document **must be marked `must_understand=false`** so non-supporting readers ignore it and fall back to walking the hierarchy. The full reimplementation may extend beyond M1; what M1 commits to is the design. The notes below sketch it.

## Current planning notes

Zarr's "consolidated metadata" pattern bundles the metadata documents for every node in a hierarchy into a single document at the root, so that opening a hierarchy requires one fetch rather than walking the tree. The pattern is essential for performance on high-latency storage (object stores) and is widely used by downstream tools (Xarray, in particular).

Open topics for the 4.0 design:

- Relationship to the new [functional core](./functional-core.md): consolidated metadata is a flat path → node-metadata mapping, a natural fit for `zarr-metadata`'s pure-data layer.
- Representation of codec, dtype, and chunk-grid configurations inside the consolidated document.
- Write-time invalidation semantics under concurrent writers; integration with the metadata cache from [performance.md § Caching](./performance.md#caching).
- Migration between V2 and V3 consolidated formats — **the one place this work can surface an on-disk format break**, so it carries the most spec scrutiny.
- `must_understand=false` semantics and the fallback-to-hierarchy-walk path for non-supporting readers.
- **Sequencing:** the design must land *before* the functional-core metadata data model and the hierarchy layer's `read_consolidated_metadata` verb crystallize around an implementation-defined shape, so it can't be deferred behind them.
