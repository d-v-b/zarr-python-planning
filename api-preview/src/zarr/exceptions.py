"""Exception hierarchy for Zarr-Python v4.

Source: [proposals/missing-apis.md](../proposals/missing-apis.md)

All Zarr-specific errors derive from :class:`ZarrError`, giving callers a single
base class to catch. Note that ``TransactionFailed`` is defined in
``zarr.store`` (it is intrinsic to the store transaction protocol) and is
re-exported by the top-level ``zarr`` package alongside the exceptions here.
"""

from __future__ import annotations

__all__ = [
    "ZarrError",
    "PathExistsError",
    "PathNotFoundError",
    "InvalidMetadataError",
    "ChunkAlignmentError",
]


class ZarrError(Exception):
    """Base class for all Zarr-specific exceptions.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """


class PathExistsError(ZarrError):
    """Raised when creating a node at a path that is already occupied.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """


class PathNotFoundError(ZarrError):
    """Raised when a node is expected at a path but none exists.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """


class InvalidMetadataError(ZarrError):
    """Raised when metadata fails to parse or violates the Zarr format.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """


class ChunkAlignmentError(ZarrError):
    """Raised when a write region is not aligned to chunk boundaries.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
