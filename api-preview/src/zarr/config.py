"""Runtime configuration for Zarr-Python v4.

Source: [proposals/missing-apis.md](../proposals/missing-apis.md)

The v4 :class:`Config` replaces the donfig-based configuration used in earlier
releases. Keys are namespaced dotted strings (e.g.
``"concurrency.compute_max_workers"``) and every key may be overridden from the
environment with a ``ZARR_*`` variable. A module-level :data:`config` instance
holds the process-global configuration.

This module also exposes :func:`to_sync`, the public synchronous bridge that
replaces the former private ``zarr.core.sync.sync()``.
"""

from __future__ import annotations

from typing import Any, Awaitable, TypeVar

__all__ = [
    "Config",
    "config",
    "to_sync",
]

T = TypeVar("T")


class Config:
    """Namespaced runtime configuration with environment overrides.

    Keys are dotted strings such as ``"concurrency.compute_max_workers"``. Any
    key may be overridden by a corresponding ``ZARR_*`` environment variable.
    Presets bundle a coherent set of values for common scenarios.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key``, or ``default`` if it is unset.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def set(self, key: str, value: Any) -> None:
        """Set the value for a namespaced configuration ``key``.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def preset(self, name: str) -> None:
        """Apply a named bundle of configuration values. (inferred)

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...


config: Config = Config()
"""Process-global configuration instance.

Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
"""


def to_sync(coro: Awaitable[T]) -> T:
    """Run an awaitable to completion, returning its result synchronously.

    Public sync bridge replacing the private ``zarr.core.sync.sync()``.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...
