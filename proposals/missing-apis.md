# Missing APIs

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

The proposals in the rest of this set address the load-bearing structural work: the functional-core refactor, the codec API, the store-layer redesign, lazy indexing, the cross-cutting performance work (which folds in caching and concurrency), and observability (which folds in chunk-level stored-state introspection). This document collects the user-facing APIs that don't fit into any of those themes but that users have been asking for — in some cases for years.

The catalog is not exhaustive. It is the result of an audit of open feature requests and discussions in the [zarr-developers/zarr-python](https://github.com/zarr-developers/zarr-python) issue tracker, filtered to user-facing API gaps that aren't already covered by another proposal. Items are grouped into six numbered themes plus a configuration substrate section. One of the themes (Chunk-level introspection) is now a pointer to [observability.md](./observability.md) where the work actually lives; the rest are owned here. Each theme has a paragraph of motivation, a list of the concrete asks, and a commitment.

## 1. Hierarchy navigation and manipulation

Zarr hierarchies are dict-shaped — a tree of groups with arrays at the leaves — but the Python API for moving around in one is thin. You can `group["subgroup"]` and you can walk children, but the ergonomic operations that downstream libraries reach for (Pythonic path traversal, bulk-open many nodes, declarative shape validation, composite hierarchies assembled from multiple stores) either don't exist or live in private/awkward surfaces. Xarray, Dask, VirtualiZarr, and napari all hit this. Several of them have written internal workarounds.

Concrete asks:

- **Pythonic path traversal** via `__truediv__`: `root / "experiment_1" / "channel_2"` instead of nested `__getitem__` ([zarr#3365](https://github.com/zarr-developers/zarr-python/issues/3365)).
- **Batch node access** — `zarr.open_nodes(store, paths)` and a public synchronous concurrent open for groups/metadata ([zarr#1805](https://github.com/zarr-developers/zarr-python/issues/1805), [zarr#3859](https://github.com/zarr-developers/zarr-python/issues/3859)). Today the only way to open N arrays concurrently is to drop into the private `zarr.core.sync.sync()` helper. Pairs with the stable async/sync bridge work in [stores-wrappers.md § AsyncToSync](./stores-wrappers.md#asynctosyncs).
- **Composite hierarchies from multiple stores.** The user-facing surface for "open these N stores together as one hierarchy" is `zarr.open(KvStack(...))`, where [`KvStack`](./stores-api.md#kvstacks-composite-store) routes per-key to one of several backing stores by `KeyRange`. This covers the session-time use cases the long-running HDF5-style link request ([zarr#389](https://github.com/zarr-developers/zarr-python/issues/389), [zarr#297](https://github.com/zarr-developers/zarr-python/issues/297), [zarr#690](https://github.com/zarr-developers/zarr-python/issues/690)) was reaching for — external data references, "open these two stores as one tree," prefix-routing for staged migrations. *Persisted* links — a stored object that says "treat `/a/link` as a pointer to `/b/actual`, surviving across processes" — are explicitly out of scope: implementing them would require Zarr-Python to define a new on-disk object format unilaterally, which is not ours to do. Persisted links wait on a cross-implementation [Zarr Enhancement Proposal](https://zarr.dev/zeps/).
- **`copy_store` / `copy` / `copy_all`** — the v2 functions, never ported to v3 ([zarr#2407](https://github.com/zarr-developers/zarr-python/issues/2407)). Python-side; the CLI equivalent is in §5 below.
- **Declarative hierarchy modelling and schema validation** ([zarr#2364](https://github.com/zarr-developers/zarr-python/discussions/2364)) — a way to declare "this hierarchy must contain a group X with arrays of these shapes and dtypes, and these attributes" and validate an opened hierarchy against the schema. The convention layer in the [Zarr Stack](../README.md#the-zarr-stack) (level 1) consumes this; OME-NGFF, GeoZarr, and anndata-zarr all hand-roll their own validators today.

**Commitment.** The `__truediv__` and `open_nodes` work is small and lands first in 4.x. `copy_store` / `copy` / `copy_all` ship in 4.x as Python-side functions. The composite-hierarchy story is already in the store layer (`KvStack`) and only needs the documentation surfacing it as the answer to the link request. Declarative schema validation likely benefits from being a separate small package (`zarr-schema`?) layered on `zarr-metadata` and is deferred beyond 4.x; the sequencing section below reflects this.

## 2. Chunk-level introspection

> **Moved.** The chunk introspection API surface (iteration over chunk coordinates, `chunk_exists`, `chunk_byte_range`, `read_block`/`write_block`, public `ArrayV3Metadata`, disambiguated nchunks/nshards/n_inner_chunks) is now the spine of [observability.md § Pillar 2: Stored-state introspection](./observability.md#pillar-2-stored-state-introspection). The framing is broader there — chunk introspection is one half of a unified observability story alongside performance metrics — but the concrete API list and the VirtualiZarr/Kerchunk motivation are the same.

## 3. Constructor and lifecycle UX

The current `zarr.open(...)` / `zarr.create(...)` / `zarr.open_array(...)` family takes a `mode=` argument with file-mode semantics (`"r"`, `"r+"`, `"w"`, `"w-"`, `"a"`) inherited from h5py. The semantics are subtle, frequently misused, and produce confusing errors when violated. Users have been asking to replace the mode-string pattern with explicit, named constructors — the same shift `pathlib.Path` made over `os.path`, or the one `pandas.read_csv` / `pd.DataFrame.to_csv` represents over the mode-based file APIs.

Concrete asks:

- **Explicit constructors** to replace `mode=`: `zarr.open_for_read(...)`, `zarr.create(...)` (raises if exists), `zarr.create_or_overwrite(...)`, `zarr.open_or_create(...)`, etc. ([zarr#2466](https://github.com/zarr-developers/zarr-python/issues/2466), [zarr#3976](https://github.com/zarr-developers/zarr-python/issues/3976)). The old `mode=`-taking functions get deprecated, then removed.
- **Typed exception hierarchy** instead of bare `ValueError` / `FileNotFoundError`: `PathExistsError`, `PathNotFoundError`, `InvalidMetadataError`, etc. ([zarr#605](https://github.com/zarr-developers/zarr-python/issues/605), [zarr#2821](https://github.com/zarr-developers/zarr-python/issues/2821)). Lets downstream code `except PathExistsError:` instead of pattern-matching on error messages.
- **Context-manager protocol on `Array` and `Group`** ([zarr#2619](https://github.com/zarr-developers/zarr-python/issues/2619)). Restores v2's `with zarr.open(...) as g:` pattern; particularly useful for resource-holding stores like `ZipStore`.
- **Stable async/sync bridge as public API** ([zarr#3835](https://github.com/zarr-developers/zarr-python/discussions/3835)). Xarray needs `zarr.core.sync.sync()` to become a stable public surface; covered architecturally by [stores-wrappers.md § AsyncToSync](./stores-wrappers.md#asynctosyncs) but the user-facing factory and documentation are part of this theme.

**Commitment.** The explicit-constructor family ships in 4.0 alongside the deprecation of the `mode=` family. Typed exceptions ship with the constructor work — they're cheap and the constructor signatures are where the new exception types get raised. Context manager protocol is a small addition; ships with 4.0. The async/sync bridge is already specified in stores-wrappers.md; this theme owns the public re-export and the documentation.

## 4. Display, debugging, and introspection

Several of the most-thumbs-up'd issues are about how `Array` and `Group` *render* — in REPLs, in Jupyter, in `repr()`, in `tree()`. The complaints are uniform: the current reprs are sparse, the HTML output for Jupyter is basic, the tree view doesn't have a "metadata only" mode, and there's no first-class way to inspect what's in a hierarchy without a separate exploration script. Compare to `xarray.Dataset`'s rich HTML repr, or `dask.array`'s detailed tree view; Zarr falls visibly short.

Concrete asks:

- **Rich reprs for groups and arrays** — full HTML repr for Jupyter, structured text repr for terminals ([zarr#2026](https://github.com/zarr-developers/zarr-python/issues/2026)). Xarray's repr is the reference target.
- **`Group.tree(...)` with a metadata-omit mode** ([zarr#224](https://github.com/zarr-developers/zarr-python/issues/224)) — show the hierarchy without the per-array metadata block, for compact navigation.
- **Promote `LatencyStore` to public API** ([zarr#3358](https://github.com/zarr-developers/zarr-python/issues/3358)) — currently buried in tests/internals; useful for users benchmarking their own pipelines. Pairs cleanly with the wrapper protocol from [stores-wrappers.md](./stores-wrappers.md) (`LatencyStore` becomes another wrapper alongside `Caching`, `Retry`, etc.). Also called out as a benchmarking adjunct in [observability.md § Pillar 1](./observability.md#pillar-1-performance-metrics-and-tracing).
- **Deterministic and pretty-printable metadata output** ([zarr#3281](https://github.com/zarr-developers/zarr-python/issues/3281)) — stable key ordering when serializing `zarr.json`, plus a "pretty" option for human-readable JSON. Important for content-addressed storage, diff workflows, and reproducibility.

**Commitment.** Rich reprs and `tree(meta=False)` ship in 4.0; small, high-visibility improvements that pay back immediately on every user's first session. `LatencyStore` is promoted to a public store wrapper in the same release as the other store wrappers ([stores-wrappers.md](./stores-wrappers.md)). Deterministic metadata output is a single flag on the metadata writer; ships with the `zarr-metadata` package.

## 5. IO conveniences

A handful of long-requested conveniences that don't fit the other themes but each have substantial user interest:

- **File-like / in-memory `ZipStore` construction** ([zarr#1018](https://github.com/zarr-developers/zarr-python/issues/1018)) — `ZipStore(io.BytesIO(...))` instead of `ZipStore(path_on_disk)`. Critical for Pyodide / browser deployments, tarball-extraction workflows, and tests.
- **Roundtrip through `ZipStore`** ([zarr#3194](https://github.com/zarr-developers/zarr-python/issues/3194)) — write to a `ZipStore`, then read from the same store object without re-opening. Surfaces the need for a `Store.flush()` / `Store.reopen(mode=...)` convenience.
- **ZEP 8 URL syntax** ([zarr#2943](https://github.com/zarr-developers/zarr-python/issues/2943)) — `zarr.open("zarr://s3://bucket/path?...")` as a single URL-driven entry point that resolves to the right backend. Aligns with [obstore](https://developmentseed.org/obstore/)'s URL+config pattern; reduces the boilerplate of constructing a backend, then a store, then an `Array`.
- **CLI for copy, remove, convert, rechunk** ([zarr#1511](https://github.com/zarr-developers/zarr-python/issues/1511)) — the command-line surface that's been requested for years. `zarr cp src dst`, `zarr rm path`, `zarr ls`, `zarr rechunk array.zarr -c "100,100,100"`. Builds on the `copy` Python API from §1 and the rechunking primitive below.
- **In-library rechunking primitive** — related to [rechunker](https://github.com/pangeo-data/rechunker) as prior art; the 4.0 ambition is a rechunking function that lives in `zarr-python` itself rather than a separate package, integrating with the engine boundary so high-performance engines can accelerate it.
- **`__dask_tokenize__` on Zarr objects** ([zarr#202](https://github.com/zarr-developers/zarr-python/issues/202)) — stable hashing for Dask graph deduplication. One-line integration that the Dask side has been requesting for years.
- **Configurable attribute serializer hook** ([zarr#156](https://github.com/zarr-developers/zarr-python/issues/156)) — let users register handlers for non-JSON-native values (numpy scalars, numpy arrays, datetimes). Today `group.attrs["x"] = np.float32(1.0)` is silently lossy or raises.

**Commitment.** File-like `ZipStore`, ZEP 8 URLs, and `__dask_tokenize__` are small enough to ship in 4.0 alongside the store and constructor work. The CLI and the rechunking primitive are larger and ship as 4.x increments; the rechunking primitive in particular benefits from the engine architecture being in place so a `zarrs`-engine `rechunk` can be substantially faster than a pure-Python one. The attrs serializer hook ships with the `zarr-metadata` package.

## 6. Configuration substrate

The current `donfig`-based [`zarr.config`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/config.py) is being retired in 4.0. The user-facing surface — namespaced keys (e.g. `concurrency.compute_max_workers`), environment-variable overrides (`ZARR_*`), named presets like `"interactive"` — survives; the substrate that holds the values gets replaced. Substrate choice is open (Pydantic settings? a custom thin layer? `attrs` plus env binding?) and will be decided as part of the 4.0 work.

The performance proposal's [Default caching policy](./performance.md#default-caching-policy) and [typed concurrency resources](./performance.md#who-owns-the-concurrency-cap) both depend on this work landing.

## Sequencing

- **4.0**: explicit constructors + typed exceptions, context manager protocol, rich reprs + `tree(meta=False)`, file-like `ZipStore`, `__dask_tokenize__`, deterministic metadata output, configuration substrate replacement. (Chunk introspection, public `ArrayV3Metadata`, and public `LatencyStore` ship in 4.0 too but are owned by [observability.md](./observability.md).)
- **4.x**: `__truediv__` traversal, `open_nodes`, `copy_store` / `copy` / `copy_all`, ZEP 8 URLs, CLI, in-library rechunking primitive, attrs serializer hook.
- **Beyond 4.x**: declarative schema validation (likely a separate `zarr-schema` package, follow-on proposal).
- **Out of scope until a Zarr Enhancement Proposal lands**: persisted hierarchy links. They require defining a new stored object format, which is cross-implementation work that Zarr-Python cannot do unilaterally.

## Open questions

- **Naming.** Several of the explicit-constructor names above are placeholders. The exact set (`open_for_read` vs `read`; `create_or_overwrite` vs `create(..., overwrite=True)`; etc.) needs a small design pass once we commit to the direction.
