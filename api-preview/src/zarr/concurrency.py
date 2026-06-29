"""Typed concurrency budgets for Zarr-Python v4.

Source: [proposals/performance.md](../proposals/performance.md)

Zarr v4 separates CPU-bound parallelism (:class:`ComputeConcurrency`) from
IO-bound parallelism (:class:`IoConcurrency`) so that the two can be tuned and
propagated independently. Budgets are passed explicitly through call trees; a
parent hands a strictly-shrinking child budget to each nested operation via
:meth:`child`, so concurrency can never expand below the level a caller granted.
"""

from __future__ import annotations

__all__ = [
    "ComputeConcurrency",
    "IoConcurrency",
]


class ComputeConcurrency:
    """CPU-bound parallelism cap for a single operation.

    The process-global default is chosen to be dask-safe: when Zarr is invoked
    from within a dask worker (or any already-parallel context) the default is
    conservative so that nested parallelism does not oversubscribe the machine.

    Source: [proposals/performance.md](../proposals/performance.md)
    """

    def __init__(self, max_workers: int | None = None) -> None:
        """Create a compute budget, defaulting to the process-global cap.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    @property
    def max_workers(self) -> int:
        """Maximum number of concurrent CPU-bound workers.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    def child(self, budget: int) -> ComputeConcurrency:
        """Derive a strictly-shrinking per-call child budget. (inferred)

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...


class IoConcurrency:
    """IO-bound parallelism cap for a single operation.

    Unlike :class:`ComputeConcurrency`, the default IO budget is decoupled from
    the host core count (roughly 32) because IO concurrency is limited by store
    latency and bandwidth rather than by CPU.

    Source: [proposals/performance.md](../proposals/performance.md)
    """

    def __init__(self, max_workers: int | None = None) -> None:
        """Create an IO budget, defaulting to the process-global cap (~32).

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    @property
    def max_workers(self) -> int:
        """Maximum number of concurrent IO-bound workers.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    def child(self, budget: int) -> IoConcurrency:
        """Derive a strictly-shrinking per-call child budget. (inferred)

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...
