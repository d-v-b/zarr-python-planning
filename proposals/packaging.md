# Packaging

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

I believe we should split Zarr-Python into separate packages. `zarr-python` would contain everything, `zarr-metadata` would just handle metadata documents, `zarr-dtype` would handle data types, `zarr-codec` would handle codecs, etc.

Related GitHub content:

- [zarr#3913](https://github.com/zarr-developers/zarr-python/issues/3913)
- [zarr#3867](https://github.com/zarr-developers/zarr-python/issues/3867)
- [zarr#3875](https://github.com/zarr-developers/zarr-python/pull/3875)
- [zarr#2863](https://github.com/zarr-developers/zarr-python/pull/2863)

## Minimizing transitive dependencies

My first argument is based on offering users what they need, in terms of dependencies: 

The Zarr-Python package today contains the full set of data structures and routines necessary to implement Zarr V2 and V3. These are the core dependencies of Zarr-Python, as of [April 16, 2026](https://github.com/zarr-developers/zarr-python/blob/520344adc7843f3b56eba51269d265ddeed3c44b/pyproject.toml#L35-L40):
```
    'packaging>=22.0',
    'numpy>=2',
    'numcodecs>=0.14',
    'google-crc32c>=1.5',
    'typing_extensions>=4.13',
    'donfig>=0.8',
```
A potential user who only needs to model the contents of a Zarr array metadata document doesn't need anything more than `typing_extensions` (it's needed for `TypedDict` features not released in Python 3.12). The remaining Zarr-Python dependencies like `numcodecs` and `numpy` are thus a barrier to that user adding `zarr` as a dependency to their project.

We should aim to support developers working at *all levels* of the Zarr stack. Forcing every downstream project to add a transitive dependency on NumPy and a codec library like Numcodecs thwarts this objective, and weakens the impact of Zarr-Python on the ecosystem of tools that work with Zarr data.

## Formalizing project dependency relationships

My second argument is this: splitting Zarr-Python into separate packages would make Zarr-Python development much easier. By splitting Zarr-Python into separate packages we will effectively model the real dependency relationships in our project, and this will make evolving any one of those packages much easier. 

The real dependency relationships in the Zarr format are roughly characterized as follows:

- Parsing metadata documents depends on:
    - a metadata API
- Storing metadata documents depends on:
    - a metadata API
    - a store API
- Finding stored chunks depends on:
    - a metadata API
    - a store API
    - a chunk grid API
    - a chunk key encoding API
- Decoding chunks depends on: 
    - a metadata API
    - a store API 
    - a chunk grid API 
    - a chunk key encoding API
    - a data type API
    - a codec API 
 
If we divide Zarr-Python along these lines, we harden these conceptual boundaries and users who only need a targeted subset of Zarr functionality can depend on exactly the subset they need. This is the approach the [Zarrs library](https://github.com/zarrs/zarrs) uses.

## Case study: codecs

I think the codec API in Zarr-Python is the best target for immediate upstreaming. Zarr-Python defines its codec API via a `Codec` abstract base classes. External libraries must implement their own codecs by subclassing the `Codec` class from Zarr-Python and registering the codec with Zarr-Python's codec registry. 

This design makes Zarr-Python a dependency of any external codec library. That is not problematic until we consider implementing a core Zarr codec (say, a rust-based `gzip`) in an external library. In this case, `zarr` would depend on `external.gzip`, but the `external` package would depend on `zarr` (for the `Codec` base class). Now if the `Codec` base class changes at all without perfectly synchronized compensatory changes in `external.gzip`, we run the risk of introducing subtle bugs when using `external.gzip` in `zarr`. 

This is not a hypothetical scenario: Zarr-Python used to depend on Numcodecs, which depended on Zarr-Python, and it was a fair bit of work to untangle the two: see PRs:
- [numcodecs#780](https://github.com/zarr-developers/numcodecs/pull/780) 
- [zarr#3376](https://github.com/zarr-developers/zarr-python/pull/3376)

Registering an external class using [entrypoints](https://packaging.python.org/en/latest/specifications/entry-points/) instead of an explicit import *weakens* the coupling, but the coupling is still there. The only real solution is to rewrite the dependency tree and break the cycle. 

So I propose we treat the codec API as a separate piece of software that has a version number, and define semantics for that version number. Zarr-Python and any other package can import from the codec API, possibly with an upper bound on the version if we are developing a new version of the codec API.

As a historical note, Zarr Python 2.x did not have a circular dependency problem here because it imported the codec API from Numcodecs. So this problem is a regression.
