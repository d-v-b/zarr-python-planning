# Proposed Conformance Suite for the Stores API

This document is a scaffolding for a per-capability conformance test suite that backends and wrappers in the [proposed Stores API](./stores-api.md) parameterize. The intent is to make protocol-shaped claims falsifiable: a PR that adds a backend, adds a wrapper, or modifies an existing one points at concrete test classes that have to pass, rather than at prose. Names, module layout, and exact signatures are all up for revision; the load-bearing claims are:

1. There is exactly one place that defines what each capability means.
2. Every backend declares the capabilities it implements by subclassing the corresponding test specs and providing fixtures.
3. Every wrapper additionally declares which capabilities it preserves by running the same specs against an inner store, plus a small set of wrapper-specific tests.
4. Zero-copy and concurrency-safety claims are testable, not just asserted in prose.
5. The suite is importable from outside the zarr repo so external backends (Icechunk, custom user backends) can run it on their own implementations.

## Motivation

Today's tests in `tests/storage/` are organized per backend: `test_local.py`, `test_memory.py`, `test_fsspec.py`, etc. Each file independently asserts what its backend should do. There is overlap (every file tests round-trip Put/Get) but no shared contract: when a wrapper PR like [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) lands, a reviewer cannot point at a single test class and ask "does your wrapper still satisfy this?". The proposed protocol-first redesign makes capability advertisement a load-bearing claim, but without a shared test contract that claim can drift between protocol prose and actual backend behavior.

A conformance suite turns the protocol surface into a runnable contract. Each capability protocol gets a corresponding `Spec` class with abstract fixtures and a fixed set of behavioral assertions. A backend that claims `Get & GetRange & List` subclasses `GetSpec`, `GetRangeSpec`, `ListSpec` in its test file and provides fixtures; the suite runs the matching assertions automatically. A wrapper that claims to preserve those capabilities does the same against an inner-store fixture, plus a wrapper-specific test class that exercises the wrapper's own behavior (cache hits, range coalescing, retry on transient errors, etc.).

This makes three workflows concrete:

- **Adding a backend.** PR adds `tests/storage/test_<backend>_conformance.py` that subclasses the relevant specs. The diff is "I claim these capabilities, here are my fixtures." Reviewer checks that the claimed capabilities match the backend's protocol declarations and that the file imports the right specs.
- **Adding a wrapper.** PR adds `tests/storage/test_<wrapper>_conformance.py` with two parts: subclasses of every spec the wrapper preserves (run against an inner store fixture wrapped by the new wrapper), and a wrapper-specific test class for its own additions. Reviewer checks both halves.
- **Adding a method to an existing backend.** PR extends the backend's protocol surface and adds the corresponding spec subclass to the backend's test file. The conformance suite runs the new spec against the backend automatically.

## Structure

The suite lives at `src/zarr/storage/testing/` so external projects can import it. Backends in zarr-python itself, plus Icechunk, custom user backends, and any `obspec`-typed store wrapped through `ObstoreStore` can all subclass the same spec classes.

```
src/zarr/storage/testing/
    __init__.py            # re-exports every Spec class
    fixtures.py            # shared helper fixtures (tmp populated stores, etc.)
    sync/
        get.py             # GetSpec
        get_range.py       # GetRangeSpec
        get_ranges.py      # GetRangesSpec
        put.py             # PutSpec
        delete.py          # DeleteSpec
        list.py            # ListSpec, ListWithDelimiterSpec
        head.py            # HeadSpec
        copy.py            # CopySpec
        transactional.py   # TransactionalSpec, TransactionalOCCSpec
    asynchronous/          # mirrors `sync/` with async fixtures and `_async` method names
        get.py             # GetAsyncSpec
        ...
    wrappers.py            # CapabilityPreservationSpec, plus per-wrapper specs:
                           # ReadOnlySpec, CachingSpec, RangeCoalescingSpec,
                           # RetrySpec, TracingSpec, SyncToAsyncSpec, AsyncToSyncSpec,
                           # PrefixedSpec
    properties.py          # zero-copy and concurrency-safety property tests
```

Each spec is a pytest-style mixin class with abstract fixtures:

```python
# src/zarr/storage/testing/sync/get.py

import pytest
from zarr.storage.protocols import Get


class GetSpec:
    """Conformance tests for the `Get` protocol. Backends and wrappers
    that claim to implement `Get` subclass this and provide the
    `store` and `populated` fixtures."""

    @pytest.fixture
    def store(self) -> Get:
        raise NotImplementedError("subclasses must provide a `store` fixture")

    @pytest.fixture
    def populated(self, store: Get) -> tuple[str, bytes]:
        """Return a `(key, value)` pair where `key` is present in `store`
        with contents `value`. Backends that also implement `Put` can use
        the default implementation; backends that don't (HTTP-only) must
        override and pre-populate their backing some other way."""
        raise NotImplementedError("subclasses must provide a `populated` fixture")

    def test_get_returns_memoryview(self, store: Get, populated: tuple[str, bytes]) -> None:
        key, value = populated
        result = store.get(key)
        assert isinstance(result, memoryview)
        assert bytes(result) == value

    def test_get_missing_key_raises_keyerror(self, store: Get) -> None:
        with pytest.raises(KeyError):
            store.get("definitely-not-a-real-key-7e7c4a")

    def test_get_does_not_mutate_store(self, store: Get, populated: tuple[str, bytes]) -> None:
        key, _ = populated
        first = bytes(store.get(key))
        second = bytes(store.get(key))
        assert first == second
```

A backend test file then declares what it satisfies and provides fixtures:

```python
# tests/storage/test_local_conformance.py

import pytest
from zarr.storage.testing.sync import (
    GetSpec, GetRangeSpec, GetRangesSpec,
    PutSpec, DeleteSpec, ListSpec, ListWithDelimiterSpec,
    HeadSpec, CopySpec, TransactionalSpec,
)
from zarr.storage.stores.local import LocalStore


class _LocalFixtures:
    @pytest.fixture
    def store(self, tmp_path) -> LocalStore:
        return LocalStore(tmp_path, mkdir=True)

    @pytest.fixture
    def populated(self, store: LocalStore) -> tuple[str, bytes]:
        store.put("key", b"value")
        return ("key", b"value")


class TestLocalGet(_LocalFixtures, GetSpec): pass
class TestLocalGetRange(_LocalFixtures, GetRangeSpec): pass
class TestLocalGetRanges(_LocalFixtures, GetRangesSpec): pass
class TestLocalPut(_LocalFixtures, PutSpec): pass
class TestLocalDelete(_LocalFixtures, DeleteSpec): pass
class TestLocalList(_LocalFixtures, ListSpec): pass
class TestLocalListWithDelimiter(_LocalFixtures, ListWithDelimiterSpec): pass
class TestLocalHead(_LocalFixtures, HeadSpec): pass
class TestLocalCopy(_LocalFixtures, CopySpec): pass
class TestLocalTransactional(_LocalFixtures, TransactionalSpec): pass
```

The diff for a new backend or a backend that grows a capability is exactly this set of declarations; the assertions live in the spec classes.

## Per-capability spec sketches

This section enumerates the spec classes and lists the assertions each one makes. Tests not yet written get one-line descriptions; tests with subtle semantics get a brief code sketch.

### `GetSpec`

- `test_get_returns_memoryview` (sketched above).
- `test_get_missing_key_raises_keyerror`.
- `test_get_does_not_mutate_store`.
- `test_get_supports_nested_keys`. Uses keys with `/` separators.
- `test_get_after_put_round_trip`. Skipped if the backend does not also implement `Put`; uses `pytest.importorskip`-style capability gating.

### `GetRangeSpec`

- `test_get_range_with_start_only`.
- `test_get_range_with_start_and_end`.
- `test_get_range_with_start_and_length`.
- `test_get_range_end_and_length_mutually_exclusive`. Either both raise or one is preferred; the spec pins the choice.
- `test_get_range_zero_length`. Returns an empty `memoryview`, not `None`.
- `test_get_range_past_end_truncates_or_raises`. Backends document which; the spec asserts whichever they declare.
- `test_get_range_negative_indices_raise`. Negative indices are not allowed in obspec's signature; we follow.
- `test_get_range_missing_key_raises_keyerror`.

### `GetRangesSpec`

- `test_get_ranges_returns_sequence_of_memoryview`.
- `test_get_ranges_preserves_order`. Output order matches input order even if the backend reorders internally for coalescing.
- `test_get_ranges_empty_input_returns_empty_output`.
- `test_get_ranges_single_range_matches_get_range`. Calling `get_ranges(key, starts=[s], ends=[e])` returns the same bytes as `[get_range(key, start=s, end=e)]`.
- `test_get_ranges_partial_failure_isolated`. If one range is invalid (out of bounds), only that range fails; others succeed. Exact failure semantics (per-range exception, sentinel, or whole-call raise) are pinned by the spec.

### `PutSpec`

- `test_put_round_trip` against `Get`.
- `test_put_overwrite`. Putting the same key twice replaces.
- `test_put_accepts_bytes_and_memoryview`. Both input types succeed; result identical.
- `test_put_with_nested_key_creates_intermediate_structure`. For backends with directory semantics; no-op for others.

### `DeleteSpec`

- `test_delete_round_trip`. Put, delete, get raises KeyError.
- `test_delete_missing_key`. Either succeeds silently or raises; spec pins the choice.
- `test_delete_does_not_affect_other_keys`.

### `ListSpec`

- `test_list_returns_iterator_of_str`.
- `test_list_with_no_prefix_returns_all_keys`.
- `test_list_with_prefix_returns_matching_keys_only`.
- `test_list_offset_skips_keys_before_offset`. Mirrors obspec's `offset` semantic.
- `test_list_after_delete_excludes_deleted`.

### `ListWithDelimiterSpec`

- `test_list_with_delimiter_returns_listresult_shape`. Pins `ListResult`'s field set.
- `test_list_with_delimiter_at_root`.
- `test_list_with_delimiter_with_prefix`.
- `test_list_with_delimiter_does_not_recurse`.

### `HeadSpec`

- `test_head_returns_objectmetadata`. Pins `ObjectMetadata`'s field set.
- `test_head_size_matches_get`.
- `test_head_missing_key_raises_keyerror`.

### `CopySpec`

- `test_copy_round_trip`.
- `test_copy_overwrites_existing_dst_or_raises`. Spec pins behavior.
- `test_copy_missing_src_raises_keyerror`.

### `TransactionalSpec`

The full eight-test sketch and the four-test extension for OCC backends are in [stores-transactional.md](./stores-transactional.md#test-plan). Highlights:

- `test_transaction_commit_persists`.
- `test_transaction_abort_discards`.
- `test_transaction_isolation`. Reads through the parent store do not see in-flight writes until commit completes.
- `test_read_your_own_writes`. Reads through the transaction context see in-progress writes from the same transaction.
- `test_atomic_multi_key`. A multi-`put` transaction either commits all keys or none.
- `test_per_key_atomicity_no_torn_write`. Single-key writes are observed as either old or new value, never a partial. Skipped on backends that document the limitation (`ZipStore`).

A separate `TransactionalOCCSpec` extends `TransactionalSpec` for backends that advertise `TransactionalOCC` (Icechunk and similar). It tests `ConflictError` semantics, version round-trip, and that conflict-failed transactions do not leak writes.

### Async specs

`GetAsyncSpec`, `GetRangeAsyncSpec`, etc. mirror the sync specs with `async def` test bodies, awaiting the corresponding `_async` method on the store. Each pair of sync/async specs shares assertions; only the dispatch differs. Code generation is tempting but probably not worth it for under a hundred tests.

## Wrapper preservation specs

Two layers.

### `CapabilityPreservationSpec`

A wrapper-agnostic spec that asserts the wrapped store advertises the same capability surface as its inner store. Run for every wrapper.

```python
class CapabilityPreservationSpec:
    @pytest.fixture
    def inner(self):
        raise NotImplementedError

    @pytest.fixture
    def wrapped(self, inner):
        raise NotImplementedError

    @pytest.mark.parametrize("cap", ALL_CAPABILITIES)
    def test_wrapped_preserves_capability(self, inner, wrapped, cap) -> None:
        assert isinstance(wrapped, cap) == isinstance(inner, cap)
```

`ALL_CAPABILITIES` is the tuple of every protocol class in `zarr.storage.protocols`. The test parametrizes over all of them and asserts the wrapper's surface matches the inner store's, except for capabilities the wrapper documents itself as adding or removing (e.g., `ReadOnly[S]` removes `Put`/`Delete`/`Copy`/`Transactional` and the spec is given a class-level `removed: set[type]` to subtract).

### Per-wrapper specs

Each wrapper has its own spec class with wrapper-specific assertions. These extend the conformance specs (so the wrapped store must still satisfy `GetSpec`, `GetRangeSpec`, etc. when the underlying store does) and add wrapper-specific tests.

- **`ReadOnlySpec`**. `wrapped.put(...)` raises a documented exception type at runtime; `isinstance(wrapped, Put)` is `False`; type-checker rejection is asserted via a separate `mypy --strict` test fixture.
- **`CachingSpec`**. Cold read fetches from inner; warm read does not (asserted via a counting inner-store mock); writes invalidate the cache; eviction by `max_bytes` and `max_entries` and `ttl` each have a dedicated test. The full algorithm, defaults, write-invalidation contract, negative-caching semantics, and the fourteen specific tests this spec runs are specified in [stores-caching.md](./stores-caching.md), including the recommended composition order with `RangeCoalescing` (caching outermost, coalescing below) and the migration plan from `experimental.cache_store`.
- **`RangeCoalescingSpec`**. The most important one for #3925: `RangeCoalescing[S]` synthesizes `GetRanges` for an `S` that only implements `GetRange`; the test asserts that calling `wrapped.get_ranges(key, starts=[0, 100], ends=[50, 150])` issues exactly one underlying `get_range(key, start=0, end=150)` call and slices the result, when `max_gap >= 50` and `max_request >= 150`. Negative cases assert non-coalescable inputs do issue separate calls. The full algorithm, defaults, failure semantics, and the nine specific tests this spec runs are specified in [stores-range-coalescing.md](./stores-range-coalescing.md), including the empirically-verified `__new__` short-circuit pattern that lets the wrapper be a no-op when `S` already implements `GetRanges` natively.
- **`SyncToAsyncSpec`** / **`AsyncToSyncSpec`**. Each capability the inner store advertises gets a sync/async mirror on the wrapped store; round-trip semantics match.
- **`RetrySpec`**. Retries on documented transient exception types up to `max_attempts`; gives up afterward; passes other exceptions through unmodified.
- **`TracingSpec`**. Every method emits an OpenTelemetry span when a tracer is configured; zero-cost when no tracer is set.

## Zero-copy and concurrency property tests

`src/zarr/storage/testing/properties.py` collects tests that backends opt into via class-level flags. These tests verify claims that the per-capability specs cannot easily express.

### Zero-copy

```python
class ZeroCopySpec:
    @pytest.fixture
    def store(self):
        raise NotImplementedError

    @pytest.fixture
    def known_backing(self, store) -> tuple[str, bytearray]:
        """Return a `(key, mutable_backing)` pair where `mutable_backing`
        is the actual underlying buffer that `store.get(key)` returns a
        view of. Only backends that can guarantee zero-copy are required
        to override this; the rest skip the spec."""
        raise NotImplementedError

    def test_get_returns_view_not_copy(self, store, known_backing) -> None:
        key, backing = known_backing
        view = store.get(key)
        backing[0] = (backing[0] + 1) % 256
        assert view[0] == backing[0]
```

Backends like `MemoryStore` (where the dict holds the literal bytes), mmap-backed `LocalStore`, and `ObstoreStore` (where obstore's `Buffer` exposes Rust-side memory) opt in. Backends that go through a copy path (`bytes`-returning fsspec implementations, for instance) do not.

### Concurrency-safety

A separate spec asserts the backend behaves correctly under concurrent access at whichever level it advertises (thread-safe, async-safe, neither). The spec is parameterized by the advertised guarantee and runs the appropriate stress test (threading.Thread fan-out, asyncio.gather fan-out, or skips). The protocol surface needs to grow a capability marker to express this advertisement; that question is tracked in the [README's "missing basic idioms" section](../README.md#the-store-api-is-missing-basic-idioms-necessary-for-high-performance).

## Workflow for PR reviews

The conformance suite is the artifact a reviewer points at when they want a falsifiable check.

- **PR adds a backend.** Reviewer asks: "What capabilities does it claim? Does the test file inherit from each corresponding spec? Are the fixtures sensible?". The diff to `tests/storage/test_<backend>_conformance.py` is the answer.
- **PR adds a wrapper.** Reviewer asks: "Does it claim to preserve capabilities? Does the test file include `CapabilityPreservationSpec`? Does it include the wrapper-specific spec from `src/zarr/storage/testing/wrappers.py`?". For [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) specifically: does the new `RangeCoalescing` wrapper satisfy `RangeCoalescingSpec`, including the "exactly one underlying `get_range` call" assertion?
- **PR modifies an existing backend.** If the change is a bug fix, the regression test goes in the conformance spec, not the backend's test file. That way every other backend that satisfies the same spec is also exercised against the regression. If the change is a behavioral break (e.g., changing partial-failure semantics in `GetRanges`), the spec changes too and every backend's matching test class re-runs against the new contract.
- **PR claims a perf improvement.** Conformance tests verify correctness; benchmarks verify the perf claim. The conformance suite stays neutral on performance and exists alongside `tests/benchmarks/`.

## Migration from today's tests

The current `tests/storage/test_<backend>.py` files contain a mix of generic round-trip tests (which become spec assertions) and backend-specific tests (which stay in the backend's file). The migration is:

1. Land the spec classes empty and let backends subclass them; CI is unchanged because the specs assert nothing yet.
2. Move generic assertions from individual `test_<backend>.py` files into the matching specs one capability at a time. After each move, run the full suite to confirm every backend still passes.
3. Backend-specific tests (e.g., `LocalStore`'s mkdir behavior, `FsspecStore`'s `validate_path` hook) stay in the backend's file. There is no pressure to move everything; the specs are for shared semantics, not for everything a backend does.
4. As capabilities get added (`ListWithDelimiter`, `Transactional`), the corresponding specs land alongside the protocol additions and every backend that implements them subclasses on the same PR.

The migration can run concurrently with the rest of the storage redesign; it does not block any of the protocol work.

## Open questions

- **Publishing.** Should `zarr.storage.testing` ship as part of `zarr-python` or as a separate package (`zarr-storage-testing`)? Separate packaging makes external backends easier to depend on it without a full zarr-python install, but adds release coordination overhead.
- **Property-based tests.** `Hypothesis` strategies for keys, prefixes, byte values, and range tuples would catch more edge cases than fixed examples but cost more to write and maintain. Likely a follow-up rather than part of the initial suite.
- **Performance baselines.** Per-spec test budgets (max wall-clock per test, max IO operations per test) would prevent backends from regressing without anyone noticing. Useful but not in scope for the initial suite.
- **Async test runner choice.** `pytest-asyncio` versus `anyio` versus a custom runner. obspec uses `pytest-asyncio`; matching is easiest.
- **Reusing obspec's tests, if any.** As of writing, obspec does not publish a conformance suite separately from its package tests. If they do, lifting the reusable parts is preferable to rewriting; if they don't, this proposal stays self-contained.
- **Marker for "fundamentally cannot satisfy this spec."** Some backends cannot satisfy some assertions (HTTP-only stores cannot test `Put`-then-`Get` round-trip). The current sketch uses `NotImplementedError` from the fixture to skip; an explicit `pytest.mark.skip` with a documented reason is cleaner. Pick one.
