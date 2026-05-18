# Caching

> **Status:** stub. For the high-level pitch, see the [parent README](../README.md). The notes below are placeholder content; this proposal awaits expansion. Note that the store-level cache wrapper is specified in [stores-caching.md](./stores-caching.md); this theme covers caching concerns above the store layer (e.g., decoded chunks).

## Current planning notes

- LRU cache for decoded chunks ([zarr#278](https://github.com/zarr-developers/zarr-python/issues/278)) — one of the oldest open issues
- Layered caching ([zarr#382](https://github.com/zarr-developers/zarr-python/issues/382))
- fsspec caching broken with FSSpecStore ([zarr#2988](https://github.com/zarr-developers/zarr-python/issues/2988))
- Negative result caching ([zarr#3570](https://github.com/zarr-developers/zarr-python/issues/3570))
