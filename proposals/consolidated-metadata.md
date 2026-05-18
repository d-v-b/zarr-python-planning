# Consolidated metadata

> **Status:** stub awaiting content. For the high-level pitch, see the [parent README](../README.md). The README TOC lists this theme but the substance has not yet been written.

## Scope

Zarr's "consolidated metadata" pattern bundles the metadata documents for every node in a hierarchy into a single document at the root, so that opening a hierarchy requires one fetch rather than walking the tree. The pattern is essential for performance on high-latency storage (object stores) and is widely used by downstream tools (Xarray, in particular).

This theme covers the design of consolidated metadata support in Zarr-Python 4.0, including:

- The relationship between consolidated metadata and the new [functional core](./functional-core.md) (consolidated metadata is a flat path → node-metadata mapping; a natural fit for L0 data + L1 functions).
- Representation of codec, dtype, and chunk-grid configurations inside the consolidated document.
- Write-time invalidation semantics.
- Migration between V2 and V3 consolidated formats.

## Current planning notes

_None yet. This stub is a placeholder so the README TOC has a real target._
