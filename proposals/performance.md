# Performance

> **Cross-cutting theme.** The notes here are not a standalone proposal but a summary of how the per-theme changes combine to deliver end-to-end performance wins. For the per-theme details, follow the links below.

Performance work in Zarr-Python 4.0 cuts across multiple themes because the current bottlenecks are structural, not isolated. The headline items:

- **Use efficient implementations of each codec.** Wrap Rust/C++ codec libraries directly rather than relying on Cython-era Numcodecs implementations. See [codecs.md](./codecs.md) for the codec API rewrite that makes this pluggable.
- **Design codec and store APIs in a performance-friendly way.** Synchronous methods as default; encode/decode methods that accept pre-allocated memory; stores that support range coalescing and capability advertisement. See [codecs.md](./codecs.md) for the codec side and [stores.md](./stores.md) for the store side.
- **A functional core that lets us swap in high-performance backends without re-implementing the surrounding library.** The functional-core refactor is the substrate that lets Zarrs and TensorStore plug in cleanly at multiple granularities — codec-only, per-chunk, whole-slice, or whole-array. See [functional-core.md](./functional-core.md).

Performance is the integrated outcome of the per-theme changes. The argument for tracking it as its own theme is that reviewers and stakeholders should be able to read one document to see how the per-theme work adds up to user-visible speedups, rather than chasing the story across multiple proposals.
