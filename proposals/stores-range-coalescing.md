# Proposed `RangeCoalescing[S]` wrapper

This document specifies the `RangeCoalescing[S]` wrapper introduced in the [Stores API proposal](./stores-api.md) and tested by the `RangeCoalescingSpec` in the [conformance suite proposal](./stores-conformance.md). It is concrete enough to argue about and to point [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) reviewers at; the load-bearing claims are:

1. The wrapper synthesizes `GetRanges` for an inner store that only implements `GetRange`, by issuing one underlying `get_range` call per coalesced group and slicing the result.
2. The coalescing decision is bounded by two parameters with documented defaults: a `max_gap` (how many wasted bytes are tolerable between ranges) and a `max_request` (how large a single coalesced request can grow).
3. Output order matches input order regardless of internal reordering.
4. Partial failures bubble up as a single exception covering the affected coalesced group; per-range partial-success semantics are out of scope for the initial wrapper.
5. The wrapper is a no-op pass-through when the inner store already implements `GetRanges` natively.

## Motivation

Sharded Zarr arrays store many small chunks inside one larger shard object. Reading a slice that touches N chunks today produces N independent byte-range requests against the shard, even when the chunks are adjacent or near-adjacent in the shard's payload. Over remote storage with 50-100ms per-request latency, this is the dominant cost for small-to-medium read patterns: actual byte transfer time is dwarfed by request setup time.

Coalescing the N ranges into one underlying request that spans them all (and slicing the result locally) replaces N round trips with 1, at the cost of fetching the gap bytes between the requested ranges. For typical Zarr shard layouts where chunks are tightly packed, the gap bytes are small or zero and the win is the full N-to-1 reduction.

Two backends already implement batch range fetching natively: S3 via `cat_ranges` (exposed by `s3fs`) and obstore via `get_ranges`. Wrapping these would be wasteful, so the wrapper detects native support and short-circuits.

[zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) is the in-flight PR adding this wrapper. The motivating use case is sharded reads from cloud storage, where the speedup is large and visible.

## Algorithm

Given a `get_ranges(key, *, starts, ends=None, lengths=None)` call on the wrapper, with N input ranges:

1. **Convert inputs to `(start, length)` pairs.** `end` and `length` are mutually exclusive at the obspec layer; the wrapper accepts whichever the caller provides and normalizes to `(start, length)` for internal use. `length=None` means "to end of object" and is handled separately (see below).
2. **Sort by `start`, remembering original index.** The coalescing decision is made on sorted order; the slicing-out step recovers original order.
3. **Walk sorted ranges and form coalesced groups.** Two adjacent (in sorted order) ranges with starts `s1, s2` and lengths `l1, l2` are coalesced into one group when:
   - `s2 - (s1 + l1) <= max_gap` (the gap is small enough that fetching it wastes acceptable bytes), and
   - `(s2 + l2) - group_start <= max_request` (adding this range would not exceed the per-request size budget).
   Otherwise, this range starts a new group.
4. **Issue one `inner.get_range(key, start=group_start, length=group_length)` per group.** The wrapper does not parallelize across groups by default; that is the responsibility of the caller (e.g., the codec pipeline, which already issues concurrent fetches across keys).
5. **Slice each coalesced result into per-range views and assemble the output in original input order.** Each output is a `ReadResult` whose `value` is a `memoryview` over the relevant slice of the coalesced fetch; all results in one batch share the same `generation` (they came from one underlying object read). Per-range slicing is zero-copy on `memoryview`.

```python
# Pseudocode for the coalescing core. Real implementation lives in
# zarr/storage/wrappers/range_coalescing.py.

def get_ranges(self, key, *, starts, ends=None, lengths=None):
    n = len(starts)
    pairs = _normalize(starts, ends, lengths)             # list of (start, length) of size n
    indexed = sorted(enumerate(pairs), key=lambda t: t[1][0])

    groups: list[list[tuple[int, tuple[int, int]]]] = []  # [(orig_idx, (start, length)), ...]
    for orig_idx, (start, length) in indexed:
        if not groups:
            groups.append([(orig_idx, (start, length))])
            continue
        cur = groups[-1]
        cur_start = cur[0][1][0]
        cur_end = max(s + l for _, (s, l) in cur)
        gap = start - cur_end
        new_end = max(cur_end, start + length)
        if gap <= self.max_gap and (new_end - cur_start) <= self.max_request:
            cur.append((orig_idx, (start, length)))
        else:
            groups.append([(orig_idx, (start, length))])

    out: list[ReadResult | None] = [None] * n
    for group in groups:
        group_start = group[0][1][0]
        group_end = max(s + l for _, (s, l) in group)
        coalesced = self._inner.get_range(
            key, start=group_start, length=group_end - group_start
        )
        for orig_idx, (s, l) in group:
            offset = s - group_start
            out[orig_idx] = ReadResult(
                value=coalesced.value[offset : offset + l],
                generation=coalesced.generation,
            )

    return out  # type: ignore[return-value]  # no None left after the loop
```

## Defaults

```python
class RangeCoalescing[S]:
    """Synthesizes GetRanges for stores that only implement GetRange,
    by coalescing nearby ranges into single underlying requests."""

    def __init__(
        self,
        inner: S,
        *,
        max_gap: int = 1 << 20,            # 1 MiB
        max_request: int = 64 << 20,       # 64 MiB
    ) -> None: ...
```

- **`max_gap = 1 MiB`.** The gap is the number of "wasted" bytes pulled between one requested range and the next. At a typical cloud-object-storage latency of 50-100 ms per request and 100 MB/s of downstream bandwidth, a single round-trip costs the equivalent of ~5-10 MiB of transfer time, so coalescing across gaps up to 1 MiB is unconditionally faster. Larger gaps risk pulling more wasted bytes than the round-trip-cost savings; smaller gaps miss obvious coalescing opportunities. 1 MiB is a midpoint that errs toward including more chunks in a coalesced group, which is the typical shape of sharded Zarr reads. Tunable per call site if shard layouts diverge from this assumption.
- **`max_request = 64 MiB`.** Caps the size of a single underlying `get_range` request, which bounds the in-memory buffer and the time-to-first-byte. Cloud backends usually do not hard-cap range size at this scale, but a runaway coalescing strategy that pulls the entire shard for a small slice request would defeat the point. 64 MiB is large enough that real shards (typically tens of MiB) fit in one request when fully read, and small enough that a "read 100 bytes from the start and 100 bytes from the end of a 100 MiB shard" pattern issues two requests instead of one.

Both defaults match the order of magnitude of obstore's own `get_ranges` coalescing parameters (which sit at 1 MiB / 100 MiB respectively as of writing). Aligning the defaults reduces surprise for users who run benchmark comparisons across the two backends.

## Capability advertisement

`RangeCoalescing[S]` advertises the same capability surface as `S` plus `GetRanges`. Specifically, when `S` already implements `GetRanges`, the wrapper short-circuits at construction and the synthesized `GetRanges` method is never invoked:

```python
class RangeCoalescing[S]:
    def __new__(cls, inner: S, **kwargs) -> Self:
        if isinstance(inner, GetRanges):
            # No-op: return the inner store unchanged. Skips __init__
            # per Python's documented __new__ semantics. The runtime
            # instance is `inner`, but the type checker sees
            # `RangeCoalescing[S]` because of the explicit `-> Self`
            # return annotation.
            return inner  # type: ignore[return-value]
        return super().__new__(cls)
```

This pattern lets call sites unconditionally wrap with `RangeCoalescing` without paying any cost for backends that have native batch fetching. The type checker still sees `RangeCoalescing[S]`; the runtime sees `S` directly when `S` already implements `GetRanges`.

**Verified empirically on pyright and mypy --strict.** Without the explicit `-> Self` return annotation, pyright performs flow-analysis through `__new__` and infers the constructor's return type as `GetRanges* | RangeCoalescing[S]`, which breaks every subsequent method call on the wrapped value. The annotation hides the conditional from pyright's flow analysis. mypy is more conservative and accepts the pattern with or without the annotation, but writing the annotation is the load-bearing requirement for cross-checker compatibility. The `# type: ignore[return-value]` comment is necessary because the actual returned object is `S`, not `Self`; this is the one place where type-system honesty is traded for ergonomics, and the trade-off is local to one line.

**Caveat for users who poke at `_inner`.** Code that accesses `wrapper._inner` directly fails at runtime with `AttributeError` when the short-circuit fires (because the runtime instance is `S`, which has no `_inner`). The wrapper's public methods are safe because runtime dispatch goes to the inner store's own methods rather than to the wrapper's. Users should treat `_inner` as private; the leading underscore makes this explicit.

For the async family, `RangeCoalescingAsync[S]` follows the same shape, calling `await inner.get_range_async(...)` per group. The async version is the one that matters for [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925), since cloud reads happen in async context. The naming follows obspec's `Async`-suffix convention; see the [sync-by-default subsection](../README.md#sync-by-default-with-async-as-an-opt-in-protocol-family) for the per-backend mapping.

## Failure semantics

Three failure modes:

1. **Inner `get_range` returns fewer bytes than requested.** Possible if the key is shorter than the requested end, or if the backend signals truncation. The wrapper raises a documented `ValueError` covering the affected coalesced group, with detail listing which input range indices were in the group. The raise is the simpler contract; per-range partial success is out of scope for the initial wrapper and can be added later if a use case justifies it.
2. **Inner `get_range` raises mid-batch.** The wrapper does not catch the exception. The exception propagates with the group context attached so the caller can identify which input ranges were affected. Subsequent groups in the same `get_ranges` call are not attempted; this matches the all-or-nothing semantic of the obstore `get_ranges` native call.
3. **Caller passes invalid input.** Negative `start`, `start > end`, parallel sequences of mismatched length, etc. The wrapper validates at the top of the method and raises before issuing any underlying calls. This makes input bugs cheap to detect and avoids partial side effects on backends that don't have transactional reads.

These semantics are pinned in `RangeCoalescingSpec` and any backend-specific `GetRangesSpec`. A future "best-effort" mode could be added behind a constructor flag if real call sites benefit from per-range partial success, but the design does not commit to it now.

## Test plan

The `RangeCoalescingSpec` in [proposals/stores-conformance.md](./stores-conformance.md#wrapper-preservation-specs) covers:

- `test_synthesizes_get_ranges_from_get_range`: a `RangeCoalescing` wrapping a `GetRange`-only store satisfies `GetRanges`. Counter the underlying `get_range` calls during the spec's example scenario and assert the count matches the expected coalesced-group count.
- `test_coalesces_within_max_gap`: input ranges separated by less than `max_gap` are fetched in a single underlying `get_range` call. The "exactly one underlying call" assertion is the most cited claim and the one [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925) reviewers should be able to point at.
- `test_does_not_coalesce_beyond_max_gap`: input ranges separated by more than `max_gap` produce separate calls.
- `test_does_not_coalesce_beyond_max_request`: when the union of two adjacent groups exceeds `max_request`, they remain separate even if the gap is small.
- `test_preserves_input_order`: outputs match input order even when coalescing reorders internally.
- `test_no_op_when_inner_implements_get_ranges`: `RangeCoalescing(s)` returns `s` directly when `s: GetRanges`. Counter `s.get_ranges` and `s.get_range` to confirm the synthesized path is not used.
- `test_partial_failure_raises_with_group_context`: a synthetic `GetRange`-only store that raises on a specific offset; assert the exception propagates with detail listing the group's input indices.
- `test_short_read_raises`: synthetic store that returns truncated bytes; assert `ValueError` with the same group context.
- `test_invalid_input_raises_before_calling_inner`: counter inner store; pass parallel sequences of mismatched length; assert exception and zero inner calls.

## Implication for [zarr#3925](https://github.com/zarr-developers/zarr-python/pull/3925)

The PR's range-coalescing logic should be reviewable against this proposal as the end-state. Specifically:

- **Method names and signatures.** The PR is async and would land into the eventual `GetRangesAsync` protocol with method `get_ranges_async`. The coalescing logic itself is async-flavored; the algorithm above translates verbatim with `await`.
- **Defaults.** Whatever the PR ships should match (or document divergence from) the `1 MiB / 64 MiB` defaults proposed here. Wildly different defaults invite future churn when the wrapper protocol lands and someone notices the inconsistency.
- **Return type.** The result is `Sequence[ReadResult]` per the [stores-api.md protocol surface](./stores-api.md#capability-protocols); each `ReadResult.value` is a `memoryview` over the relevant slice of the coalesced fetch (zero-copy), and all results share the same `generation`. If the PR currently returns zarr `Buffer` objects, that is the one decision the migration plan flips later.
- **Native `get_ranges` short-circuit.** The PR should either (a) not wrap stores that already implement native batch fetching, or (b) detect the inner capability and short-circuit. Wrapping `ObstoreStore` (which has native `get_ranges`) and paying the coalescing logic's per-call overhead would be a net loss.
- **Failure semantics.** The PR's behavior on partial backend errors should match the all-or-nothing contract spelled out above. Per-range partial success is a follow-up, not initial scope.
- **Conformance test inheritance.** The PR adds a backend-specific test file that subclasses `RangeCoalescingSpec` (once the conformance suite ships) and provides fixtures that exercise the wrapper against a `GetRange`-only mock. Until the conformance suite lands, the PR's tests should at least include the load-bearing assertions (single underlying call when ranges are within `max_gap`, ordering preservation, partial-failure raise) so future migration to the spec is mechanical.

## Open questions

- **Cross-key coalescing.** This proposal coalesces only within one `key` per call. A request that spans multiple keys (rare but possible in some sharded layouts) would need a different mechanism. Out of scope; revisit if real workloads need it.
- **Backpressure / per-call concurrency cap.** The wrapper issues one underlying request per coalesced group. For workloads with many groups, the caller-side concurrency strategy (asyncio.gather, etc.) determines how many in-flight requests there are. The wrapper does not impose its own cap. If real workloads see overload, a `max_concurrency` parameter could be added in a follow-up.
- **Per-call override of defaults.** Currently `max_gap` and `max_request` are constructor-time. Some callers might want per-call overrides (e.g., a sharding codec that knows the shard layout). Adding a per-call override is additive and can be done later.
- **Best-effort partial success mode.** As noted in the failure-semantics section, a future flag could enable per-range partial success. Out of scope for the initial wrapper.
- **Interaction with `Caching[S]`.** A `Caching` wrapper above `RangeCoalescing` caches coalesced fetches. A `Caching` wrapper below `RangeCoalescing` caches per-range slices. These are different and the docs should make the recommended ordering clear once `Caching` is specified. Tracked for the caching wrapper proposal.
