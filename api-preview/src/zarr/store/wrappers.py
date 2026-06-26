"""Composable store wrappers for the Zarr v4 store layer.

Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

Wrappers are generic over an inner store ``S`` and add a single cross-cutting
concern -- read-only enforcement, retries, tracing, sync/async adaptation,
caching, range coalescing, prefixing, or routing -- while forwarding the inner
store's capabilities. They compose freely, so a deployment stacks exactly the
behaviors it needs (for example ``Retry(Caching(ObstoreStore(...)))``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio import AbstractEventLoop
    from concurrent.futures import Executor

    from zarr.store.types import KeyRange

__all__ = [
    "ReadOnly",
    "Retry",
    "Tracing",
    "SyncToAsync",
    "AsyncToSync",
    "Caching",
    "CachingAsync",
    "RangeCoalescing",
    "RangeCoalescingAsync",
    "Prefixed",
    "KvStack",
]


class ReadOnly[S]:
    """Wrapper that strips write capabilities from the inner store.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    The resulting store exposes only read, list, and metadata capabilities (plus
    :class:`~zarr.store.protocols.Transactional`); ``put``, ``delete``, and
    ``copy`` are not forwarded, so writes are impossible by construction rather
    than by runtime check.
    """

    def __init__(self, inner: S) -> None:
        """Wrap ``inner``, exposing only its read-side capabilities.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...


class Retry[S]:
    """Wrapper that retries failing operations with exponential backoff.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    Operations that raise one of ``retry_on`` are retried up to ``max_attempts``
    times, with backoff growing from ``initial_backoff`` by ``backoff_multiplier``
    up to ``max_backoff`` and perturbed by ``jitter``.
    """

    def __init__(
        self,
        inner: S,
        *,
        max_attempts: int = 3,
        retry_on: tuple[type[Exception], ...] = (TimeoutError, ConnectionError),
        initial_backoff: float = 0.1,
        max_backoff: float = 10.0,
        backoff_multiplier: float = 2.0,
        jitter: float = 0.1,
    ) -> None:
        """Wrap ``inner`` with retry-with-backoff semantics.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...


class Tracing[S]:
    """Wrapper that emits OpenTelemetry spans for store operations.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    Zero-cost when ``tracer`` is ``None``: operations are forwarded directly
    without span creation, so the wrapper can be left in place unconditionally.
    """

    def __init__(self, inner: S, *, tracer: Tracer | None = None) -> None:
        """Wrap ``inner``, tracing each operation with ``tracer`` if provided.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...


class SyncToAsync[S]:
    """Wrapper that exposes a synchronous store through the async family.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    Each async method runs the inner store's synchronous operation on
    ``executor`` (a thread pool by default), so a blocking backend can be used
    from async code without blocking the event loop.
    """

    def __init__(self, inner: S, *, executor: Executor | None = None) -> None:
        """Wrap synchronous ``inner``, offloading calls to ``executor``.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...


class AsyncToSync[S]:
    """Wrapper that exposes an asynchronous store through the sync family.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    Each sync method drives the inner store's coroutine on ``loop``. This
    replaces the global ``zarr.core.sync.sync()`` bridge with an explicit,
    per-store adapter.
    """

    def __init__(self, inner: S, *, loop: AbstractEventLoop | None = None) -> None:
        """Wrap asynchronous ``inner``, running its coroutines on ``loop``.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...


class Caching[S]:
    """Wrapper adding a synchronous read cache in front of the inner store.

    Source: [proposals/stores-caching.md](../proposals/stores-caching.md)

    Caches values subject to ``max_bytes`` and ``max_entries`` bounds and an
    optional ``ttl``. When ``cache_negative`` is set, missing keys are cached for
    ``cache_negative_ttl`` seconds. Cached reads are validated against
    generations to stay consistent with the inner store.
    """

    def __init__(
        self,
        inner: S,
        *,
        max_bytes: int = 256 << 20,
        max_entries: int = 4096,
        ttl: float | None = None,
        cache_negative: bool = False,
        cache_negative_ttl: float = 1.0,
    ) -> None:
        """Wrap ``inner`` with a bounded, generation-aware read cache.

        Source: [proposals/stores-caching.md](../proposals/stores-caching.md)
        """
        ...


class CachingAsync[S]:
    """Wrapper adding an asynchronous read cache in front of the inner store.

    Source: [proposals/stores-caching.md](../proposals/stores-caching.md)

    The async counterpart to :class:`Caching`, with identical bounds and
    negative-caching behavior.
    """

    def __init__(
        self,
        inner: S,
        *,
        max_bytes: int = 256 << 20,
        max_entries: int = 4096,
        ttl: float | None = None,
        cache_negative: bool = False,
        cache_negative_ttl: float = 1.0,
    ) -> None:
        """Wrap ``inner`` with a bounded, generation-aware async read cache.

        Source: [proposals/stores-caching.md](../proposals/stores-caching.md)
        """
        ...


class RangeCoalescing[S]:
    """Wrapper that merges nearby byte-range reads into fewer requests.

    Source: [proposals/stores-range-coalescing.md](../proposals/stores-range-coalescing.md)

    Adjacent or near-adjacent ranges separated by no more than ``max_gap`` bytes
    are combined into a single request, subject to a ``max_request`` ceiling, to
    reduce per-request overhead on high-latency stores.
    """

    def __init__(self, inner: S, *, max_gap: int = 1 << 20, max_request: int = 64 << 20) -> None:
        """Wrap ``inner`` with synchronous range coalescing.

        Source: [proposals/stores-range-coalescing.md](../proposals/stores-range-coalescing.md)
        """
        ...


class RangeCoalescingAsync[S]:
    """Wrapper that merges nearby byte-range reads on an async store.

    Source: [proposals/stores-range-coalescing.md](../proposals/stores-range-coalescing.md)

    The async counterpart to :class:`RangeCoalescing`.
    """

    def __init__(self, inner: S, *, max_gap: int = 1 << 20, max_request: int = 64 << 20) -> None:
        """Wrap ``inner`` with asynchronous range coalescing.

        Source: [proposals/stores-range-coalescing.md](../proposals/stores-range-coalescing.md)
        """
        ...


class Prefixed[S]:
    """Wrapper that scopes all operations beneath a fixed key prefix.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    Keys are transparently joined to ``prefix`` on the way in and stripped on
    the way out, so consumers work with relative keys. This replaces
    ``StorePath`` in the user-facing API.
    """

    def __init__(self, inner: S, prefix: str) -> None:
        """Wrap ``inner``, prepending ``prefix`` to every key.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...

    @property
    def bounds(self) -> KeyRange:
        """The key range, relative to ``prefix``, that this view covers.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...

    def __truediv__(self, sub: str) -> Prefixed[S]:
        """Return a further-prefixed view scoped beneath ``sub``.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md) (inferred)
        """
        ...


class KvStack[S]:
    """Routed composite store dispatching keys across disjoint ranges.

    Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)

    Each ``(KeyRange, store)`` layer owns a disjoint slice of the key space;
    operations route to the layer whose range contains the key. The composite's
    capability surface is the intersection of its layers' capabilities.
    """

    def __init__(self, layers: Sequence[tuple[KeyRange, S]]) -> None:
        """Build a composite store from disjoint ``(range, store)`` layers.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...

    @property
    def bounds(self) -> KeyRange:
        """The key range spanning all layers.

        Source: [proposals/stores-wrappers.md](../proposals/stores-wrappers.md)
        """
        ...
