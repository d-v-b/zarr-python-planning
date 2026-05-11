# Proposed smaller wrappers: `ReadOnly`, `Retry`, `Tracing`, `SyncToAsync`, `AsyncToSync`

This document specifies the wrappers introduced in the [Stores API proposal](./stores-api.md) that are too small to deserve a dedicated proposal but too load-bearing to leave as one-line stubs. The two larger wrappers, `Caching[S]` and `RangeCoalescing[S]`, have their own proposals ([stores-caching.md](./stores-caching.md), [stores-range-coalescing.md](./stores-range-coalescing.md)). `Prefixed[S]` is specified inline in [stores-api.md](./stores-api.md#path-ownership-and-prefixed-wrapper) because it anchors the StorePath migration.

The load-bearing claims:

1. Every wrapper here uses the self-type narrowing pattern verified in [stores-api.md](./stores-api.md#path-ownership-and-prefixed-wrapper) so capability preservation is enforced statically. Methods declare `self: Wrapper[Capability]` and the type checker rejects calls to capabilities the inner store does not advertise.
2. Wrappers are independent: composing any two in any order produces a well-defined result, with three documented exceptions (`Caching` × `Transactional`, ordering matters for `Caching` × `RangeCoalescing`, ordering matters for `Tracing`).
3. Defaults are conservative: no wrapper changes observable behavior in the common case unless the user opts into the wrapper deliberately.

## `ReadOnly[S]`

```python
class ReadOnly[S]:
    """Strips Put, Delete, Copy, Transactional from S's capability set.
    Read capabilities pass through. The type checker rejects writes at
    compile time; the runtime instance simply does not define the
    stripped methods, so attribute access fails with AttributeError if
    a caller bypasses the type checker."""

    def __init__(self, inner: S) -> None:
        self._inner = inner

    def get(self: "ReadOnly[Get]", key: str) -> memoryview:
        return self._inner.get(key)

    def get_range(
        self: "ReadOnly[GetRange]",
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> memoryview:
        return self._inner.get_range(key, start=start, end=end, length=length)

    # ... and so on for every read capability. Notably, `put`, `delete`,
    # `copy`, and `transaction` are NOT defined on `ReadOnly[S]` regardless
    # of what S advertises. This is the entire point: the wrapper strips
    # the write surface.
```

Replaces today's `Store.with_read_only(read_only=True)` clone-based pattern. Migration path is documented in [stores-api.md migration shims](./stores-api.md#migration-shims-and-deprecation-surface).

`ReadOnly[ReadOnly[S]]` is `ReadOnly[S]` semantically (idempotent); the implementation does not need to special-case it.

## `Retry[S]`

```python
class Retry[S]:
    """Retries transient failures on every method with exponential
    backoff and jitter. The set of retryable exception types is
    configurable. Per-call retry budget is enforced; a single get()
    cannot consume more than `max_attempts` underlying calls."""

    def __init__(
        self,
        inner: S,
        *,
        max_attempts: int = 3,
        retry_on: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
        ),
        initial_backoff: float = 0.1,           # 100 ms
        max_backoff: float = 10.0,
        backoff_multiplier: float = 2.0,
        jitter: float = 0.1,                    # 0..1, fraction of backoff
    ) -> None: ...

    def get(self: "Retry[Get]", key: str) -> memoryview: ...
    # ... and so on for every capability of S, each wrapped in the same
    # retry loop.
```

### Retry semantics

- **What gets retried.** Calls that raise an exception in `retry_on`. Other exceptions propagate immediately.
- **What does not get retried.** `Transactional.transaction()` itself does not retry (committing a transaction has its own concurrency-control story; see the [transactional proposal](./stores-transactional.md#composition-with-other-wrappers)). `OCCTransactionContext.commit()` raising `ConflictError` propagates without retry; the retry loop is caller-side.
- **Backoff schedule.** Attempt N (1-indexed) waits `min(initial_backoff * backoff_multiplier^(N-1), max_backoff)` seconds before retrying, with `± jitter * delay` added uniformly. Default: 100 ms, 200 ms, 400 ms with up to 10% jitter, capped at 10 s.
- **Per-call budget.** `max_attempts` is per call, not per store. A burst of failing calls each gets its own retry budget.
- **Idempotency.** All read operations are idempotent. Writes are idempotent in the put-by-key model that every supported backend implements (no append, no atomic-counter increment). So retrying a `put` after a transient failure is safe; the worst case is two writes of the same value.

### Defaults rationale

- **`max_attempts = 3`.** A single retry catches most transient blips; a third attempt catches longer-lived flaps. Beyond three, the failure is more likely a permanent issue (auth, rate limiting, bad endpoint) and continuing makes things worse.
- **`retry_on = (TimeoutError, ConnectionError)`.** Only retry on signals that look transient. Backends that surface 5xx or 429 as more specific exception types should override the default to include them; the wrapper does not bake in cloud-specific exception hierarchies.
- **`initial_backoff = 100 ms`, `max_backoff = 10 s`, `multiplier = 2.0`.** Standard exponential schedule. Caps prevent runaway backoff on persistent failure.
- **`jitter = 0.1`.** Avoids thundering-herd retries when many concurrent callers hit the same transient failure. Conservative default; can be raised to 0.5 for high-contention workloads.

## `Tracing[S]`

```python
class Tracing[S]:
    """Wraps every method in an OpenTelemetry span. Zero-cost when no
    tracer is set: the wrapper returns the inner store directly via
    the same __new__ short-circuit pattern as RangeCoalescing."""

    def __new__(cls, inner: S, *, tracer: "Tracer | None" = None) -> Self:
        if tracer is None:
            return inner  # type: ignore[return-value]
        return super().__new__(cls)

    def __init__(self, inner: S, *, tracer: "Tracer | None" = None) -> None:
        self._inner = inner
        self._tracer = tracer

    def get(self: "Tracing[Get]", key: str) -> memoryview:
        with self._tracer.start_as_current_span("zarr.store.get") as span:
            span.set_attribute("zarr.store.key", key)
            try:
                result = self._inner.get(key)
                span.set_attribute("zarr.store.bytes", len(result))
                return result
            except Exception as e:
                span.record_exception(e)
                raise
    # ... and so on for every capability.
```

### Tracing semantics

- **Span naming.** `zarr.store.{method}` for every call. Customizable via a `span_namespace` constructor arg if a user wants `myapp.zarr.{method}`.
- **Standard attributes.** `zarr.store.key` for any method that takes a key. `zarr.store.bytes` for read methods (size of the returned data). `zarr.store.start` / `zarr.store.end` for `get_range`. `zarr.store.range_count` for `get_ranges`.
- **Exceptions.** Every span records exceptions via `span.record_exception(e)` before re-raising.
- **Zero-cost when off.** The `__new__` short-circuit returns the inner store directly when `tracer is None`, so a `Tracing(store)` with no tracer is equivalent to `store` at runtime with no per-call overhead. Same pattern as `RangeCoalescing` for native `GetRanges` backends.

### OpenTelemetry, not zarr-specific

The wrapper takes a `Tracer` from the OpenTelemetry API by structural typing. Users who prefer a different observability framework (Datadog, Honeycomb, internal) can pass a duck-typed object that implements `start_as_current_span`. The wrapper does not import OpenTelemetry directly; it imports lazily from the user-provided tracer.

## `SyncToAsync[S]`

```python
class SyncToAsync[S]:
    """Adapts a sync-only store to advertise async protocols by
    running each call in a thread pool. The inner store's methods are
    invoked synchronously inside `asyncio.to_thread` (or
    `loop.run_in_executor` if a custom executor is provided)."""

    def __init__(
        self,
        inner: S,
        *,
        executor: "Executor | None" = None,
    ) -> None: ...

    async def get_async(self: "SyncToAsync[Get]", key: str) -> memoryview:
        return await asyncio.to_thread(self._inner.get, key)

    async def get_range_async(
        self: "SyncToAsync[GetRange]",
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> memoryview:
        return await asyncio.to_thread(
            self._inner.get_range, key, start=start, end=end, length=length
        )
    # ... async variants for every sync capability of S.
```

### Sync-to-async semantics

- **One thread per call.** Each method invocation goes through `asyncio.to_thread` (or a user-provided executor). Multiple concurrent calls fan out across the thread pool.
- **No native async surface promotion.** `SyncToAsync[S]` advertises `GetAsync`, `GetRangeAsync`, etc., based on what `S` advertises (`Get`, `GetRange`). It does not advertise sync protocols even though `inner` does; callers that want both should use `inner` directly for sync access and `SyncToAsync(inner)` for async access. Composition: `inner` is shared between the two.
- **Executor choice.** Default is `asyncio.to_thread` which uses the default event loop's executor. A custom `Executor` (typically a `ThreadPoolExecutor`) gives the caller control over concurrency limits. Pass `None` to use the default; pass a per-store executor for isolation.
- **Performance characteristics.** Adds a thread-pool round trip per call. Acceptable for workloads where the inner sync call dominates (filesystem I/O, in-process state). Not appropriate for hot tight loops over `MemoryStore`, where the sync version is faster than going through a thread.

## `AsyncToSync[S]`

```python
class AsyncToSync[S]:
    """Adapts an async-only store to advertise sync protocols by
    driving an event loop. Replaces today's global
    `zarr.core.sync.sync()` bridge with an explicit per-store choice."""

    def __init__(
        self,
        inner: S,
        *,
        loop: "asyncio.AbstractEventLoop | None" = None,
    ) -> None: ...

    def get(self: "AsyncToSync[GetAsync]", key: str) -> memoryview:
        return _run_sync(self._inner.get_async(key), loop=self._loop)
    # ... sync variants for every async capability of S.
```

### Async-to-sync semantics

- **Event loop policy.** Each call drives the event loop until the coroutine resolves. Default loop is the per-store loop (created lazily on first call); pass an explicit `loop` to share with other code. Driving a loop that is already running raises `RuntimeError` (the documented `asyncio` rule).
- **Reentrancy.** Calling `AsyncToSync(s).get(...)` from inside a coroutine that is itself running on the same loop deadlocks. The wrapper does not detect this and does not try to recover; the contract is "use this in sync contexts only."
- **Replaces `zarr.core.sync.sync()`.** During the deprecation window, the global helper is reimplemented in terms of `AsyncToSync` so existing code continues to work. Direct callers of `zarr.core.sync.sync()` get a deprecation warning pointing at the wrapper.
- **Per-store cost.** Each call pays the event-loop driving overhead (one round trip through `loop.run_until_complete` or equivalent). Acceptable for the user-facing zarr API where calls are infrequent; expensive for inner loops, where direct async usage is appropriate.

## Composition rules

| Inside ↓ \ Outside → | `ReadOnly` | `Retry` | `Tracing` | `SyncToAsync` | `AsyncToSync` | `Caching` | `RangeCoalescing` | `Prefixed` | `Transactional` |
|---|---|---|---|---|---|---|---|---|---|
| `ReadOnly` | idempotent | OK | OK | OK | OK | OK | OK | OK | strips writes |
| `Retry` | OK | flatten | OK | OK | OK | OK | OK | OK | see [transactional](./stores-transactional.md#composition-with-other-wrappers) |
| `Tracing` | OK | OK | flatten | OK | OK | OK | OK | OK | OK |
| `SyncToAsync` | OK | OK | OK | absurd | OK (round trip) | OK | OK | OK | depends |
| `AsyncToSync` | OK | OK | OK | OK (round trip) | absurd | OK | OK | OK | depends |
| `Caching` | OK | OK | OK | OK | OK | flatten | order matters | OK | refused |
| `RangeCoalescing` | OK | OK | OK | OK | OK | order matters | flatten | OK | OK |
| `Prefixed` | OK | OK | OK | OK | OK | OK | OK | flatten | OK |
| `Transactional` | strips | retry-then-commit caveat | OK | depends | depends | refused | OK | OK | nested? |

Recommended ordering for cloud-Zarr workloads, outside in:

```python
store = Tracing(
    Caching(
        RangeCoalescing(
            Retry(
                ObstoreStore(S3Store(bucket="...", region="..."))
            )
        )
    ),
    tracer=otel_tracer,
)
```

- **`Tracing` outermost** so cache hits are still traced.
- **`Caching` next** so cached results short-circuit the rest of the stack.
- **`RangeCoalescing` next** so coalesced fetches are what's cached.
- **`Retry` innermost** so a transient failure on a coalesced fetch is retried as one operation.

Composing in different orders produces well-defined but suboptimal behavior. The conformance suite's `CapabilityPreservationSpec` ensures the compositions all preserve capability surfaces; per-wrapper specs ensure they preserve semantics.

## Test plan

Each wrapper has its own spec in the conformance suite (see [stores-conformance.md](./stores-conformance.md#wrapper-preservation-specs)).

- **`ReadOnlySpec`**. `ReadOnly[s].put(...)` is a static type error; runtime `AttributeError`. Reads pass through unchanged.
- **`RetrySpec`**. Counter-mock that fails N times then succeeds; assert wrapper retries up to `max_attempts`. Counter-mock that fails with non-retryable; assert wrapper does not retry. Backoff schedule asserted via timing measurements (with tolerance) or via mocked `time.sleep`.
- **`TracingSpec`**. Mock tracer; assert one span per method call, correct span name and attributes, exceptions recorded. Zero-tracer case: assert `Tracing(store, tracer=None) is store`.
- **`SyncToAsyncSpec`** / **`AsyncToSyncSpec`**. Round-trip test: `AsyncToSync(SyncToAsync(memory_store))` behaves identically to `memory_store` for every capability. Concurrency test: multiple `asyncio.gather`'d calls on `SyncToAsync(slow_sync_store)` complete in less wall time than serialized calls.

`CapabilityPreservationSpec` runs across every wrapper to assert composition with each capability is preserved per the table above.

## Open questions

- **`Retry` jitter strategy.** The current proposal uses additive jitter. Multiplicative jitter (`delay * uniform(1 - jitter, 1 + jitter)`) is mathematically cleaner but produces similar behavior; pick one and document.
- **`Tracing` integration with `Caching` cache-hit attributes.** Should a cache hit emit a span at all? Or just an attribute on the parent span? The first is more visible; the second is cheaper. Defer to first user feedback.
- **`SyncToAsync` GIL contention.** If multiple sync calls fan out across a thread pool but all hit a Python-side bottleneck (e.g., decoding bytes into a numpy array), the GIL serializes them and the parallelism is fictional. Free-threaded CPython (no-GIL) eliminates this; in the meantime, the wrapper documentation should note that sync stores doing CPU-bound work in their methods will not parallelize via this wrapper.
- **`AsyncToSync` reentrancy detection.** Adding a runtime check that raises a clearer error than the `asyncio` default is a small win; not in scope for the initial wrapper.
- **A `Compose` helper.** The recommended ordering above is verbose. A `Compose(inner, [Tracing, Caching, RangeCoalescing, Retry])` helper that builds the stack in one call would be useful syntactic sugar. Out of scope for the initial proposal.
