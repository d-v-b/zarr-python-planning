# Concurrency and thread safety

> **Status:** stub. For the high-level pitch, see the [parent README](../README.md). The notes below are placeholder content; this proposal awaits expansion.

## Current planning notes

- Thread-unsafe initialization ([zarr#1435](https://github.com/zarr-developers/zarr-python/issues/1435))
- Multiprocessing failures ([zarr#3126](https://github.com/zarr-developers/zarr-python/issues/3126), [zarr#2729](https://github.com/zarr-developers/zarr-python/issues/2729))
- Async event loop conflicts ([zarr#2878](https://github.com/zarr-developers/zarr-python/issues/2878), [zarr#3487](https://github.com/zarr-developers/zarr-python/issues/3487), [zarr#2909](https://github.com/zarr-developers/zarr-python/issues/2909))
- Free-threaded CPython (nogil) support ([zarr#2776](https://github.com/zarr-developers/zarr-python/discussions/2776))
