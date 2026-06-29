"""Legacy 3.x configuration substrate.

Mirrors the ``donfig``-backed configuration objects from ``zarr.core.config``:
the ``BadConfigError`` exception, the ``Config`` object, and the module-level
``config`` singleton. In 4.0.0 donfig is retired in favor of a new namespaced
config substrate in ``zarr.config``.

Real 3.x location: ``zarr.core.config``
Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
"""

from __future__ import annotations

from typing import Any

from ._util import _legacy

__all__ = ["BadConfigError", "Config", "config"]


@_legacy(
    replaced_by="zarr.config (namespaced config errors)",
    migration="Catch the new config error type from zarr.config instead.",
)
class BadConfigError(ValueError):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.config` namespaced config errors
        **Migration:** Catch the new config error type from zarr.config instead.

    Raised when a configuration value is invalid.

    Real 3.x location: `zarr.core.config.BadConfigError`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
    """


@_legacy(
    replaced_by="zarr.config",
    migration="Read and set configuration via the new namespaced zarr.config substrate.",
)
class Config:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.config`
        **Migration:** Read and set configuration via the new namespaced zarr.config substrate.

    A ``donfig.Config`` subclass holding zarr's runtime configuration.

    Real 3.x location: `zarr.core.config.Config`
    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
    """

    def get(self, key: str, default: Any = None) -> Any:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.config`
            **Migration:** Read configuration through zarr.config.

        Return the configuration value for ``key``.

        Real 3.x location: `zarr.core.config.Config.get`
        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
        """
        ...

    def set(self, *args: Any, **kwargs: Any) -> Any:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.config`
            **Migration:** Set configuration through zarr.config.

        Set one or more configuration values.

        Real 3.x location: `zarr.core.config.Config.set`
        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
        """
        ...

    def set_in_context(self, *args: Any, **kwargs: Any) -> Any:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.config`
            **Migration:** Use the context-manager form of zarr.config.

        Temporarily set configuration values within a context.

        Real 3.x location: `zarr.core.config.Config.set_in_context`
        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
        """
        ...


config: Config = ...
"""!!! warning "Removed in 4.0.0"
    **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
    **Replaced by:** `zarr.config`
    **Migration:** Use the module-level config object exposed by zarr.config.

The module-level configuration singleton.

Real 3.x location: `zarr.core.config.config`
Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §6
"""
