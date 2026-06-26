"""Key/path helper functions for the Zarr v4 store layer.

Source: [proposals/stores-api.md](../proposals/stores-api.md)

Small pure helpers for composing and decomposing the string keys used
throughout the store layer. They centralize the prefix-joining and
prefix-stripping rules so that backends and wrappers agree on key shape.
"""

from __future__ import annotations

__all__ = [
    "dereference_path",
    "relativize_path",
]


def dereference_path(root: str, key: str) -> str:
    """Join ``key`` onto ``root`` to form an absolute store key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """
    ...


def relativize_path(*, path: str, prefix: str) -> str:
    """Strip ``prefix`` from ``path`` to recover a relative key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """
    ...
