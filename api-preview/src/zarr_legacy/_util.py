"""Deprecation-marking helpers for the ``zarr_legacy`` preview package.

This module provides :func:`_legacy`, a decorator factory used to annotate the
3.x public symbols that are deprecated in 3.x and removed in zarr-python 4.0.0.
It is intentionally stdlib-only and attaches metadata without altering runtime
behavior, so the symbols remain readable by mkdocstrings/griffe.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

__all__ = ["_legacy"]

T = TypeVar("T")


def _legacy(
    *,
    replaced_by: str,
    migration: str,
    deprecated_in: str = "3.x",
    removed_in: str = "4.0.0",
) -> Callable[[T], T]:
    """Mark a class or function as legacy (deprecated in 3.x, removed in 4.0.0).

    The returned decorator attaches ``__deprecated__`` plus ``__replaced_by__``,
    ``__removed_in__``, ``__deprecated_in__`` and ``__migration__`` attributes to
    the wrapped object and returns it unchanged. It introduces no runtime
    behavior.

    Parameters
    ----------
    replaced_by:
        Dotted path to the v4 replacement.
    migration:
        One concise sentence describing how to migrate.
    deprecated_in:
        Version in which the symbol was deprecated. Defaults to ``"3.x"``.
    removed_in:
        Version in which the symbol is removed. Defaults to ``"4.0.0"``.
    """

    def decorator(obj: T) -> T:
        obj.__deprecated__ = True
        obj.__replaced_by__ = replaced_by
        obj.__removed_in__ = removed_in
        obj.__deprecated_in__ = deprecated_in
        obj.__migration__ = migration
        return obj

    return decorator
