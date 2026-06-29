"""Data-type model and registry for Zarr-Python v4.

Source: [proposals/data-types.md](../proposals/data-types.md)

Zarr v4 models data types as first-class objects implementing :class:`DType`,
each able to serialize itself to and from the Zarr v3 ``data_type`` document. A
process-global registry maps type identifiers to :class:`DType` instances; new
types (including extension types) register themselves via :func:`register_dtype`.

The machine-learning dtype singletons exported here (``bfloat16``, the
``float8_*`` family, ``int4``, ``uint4``) are backed by the ``ml_dtypes``
package, an optional dependency shipped as ``zarr-ml-dtypes``. Their identifiers
match the names registered in the zarr-extensions registry exactly. In
particular, ``float8_e4m3fn`` must be registered in zarr-extensions for arrays
using it to be portable across implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = [
    "DType",
    "register_dtype",
    "get_dtype",
    "list_dtypes",
    "bfloat16",
    "float8_e4m3fn",
    "float8_e5m2",
    "float8_e4m3b11fnuz",
    "float8_e5m2fnuz",
    "int4",
    "uint4",
]


class DType(ABC):
    """Abstract base for a Zarr data type.

    Source: [proposals/data-types.md](../proposals/data-types.md)
    """

    name: str
    """The registered identifier for this data type."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize this data type to its Zarr ``data_type`` document.

        Source: [proposals/data-types.md](../proposals/data-types.md)
        """
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> DType:
        """Construct a data type from its serialized form.

        Source: [proposals/data-types.md](../proposals/data-types.md)
        """
        ...


def register_dtype(dtype: DType) -> None:
    """Register a data type in the process-global registry.

    Source: [proposals/data-types.md](../proposals/data-types.md)
    """
    ...


def get_dtype(name: str) -> DType:
    """Look up a registered data type by its identifier.

    Source: [proposals/data-types.md](../proposals/data-types.md)
    """
    ...


def list_dtypes() -> list[str]:
    """List the identifiers of all registered data types.

    Source: [proposals/data-types.md](../proposals/data-types.md)
    """
    ...


class _MLDType(DType):
    """Concrete :class:`DType` for an ``ml_dtypes``-backed type. (inferred)

    Source: [proposals/data-types.md](../proposals/data-types.md)
    """

    def __init__(self, name: str) -> None:
        """Create an ML dtype singleton bound to an identifier. (inferred)

        Source: [proposals/data-types.md](../proposals/data-types.md)
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize this ML data type to its ``data_type`` document. (inferred)

        Source: [proposals/data-types.md](../proposals/data-types.md)
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DType:
        """Construct an ML data type from its serialized form. (inferred)

        Source: [proposals/data-types.md](../proposals/data-types.md)
        """
        ...


bfloat16: DType = _MLDType("bfloat16")
"""Brain floating-point 16-bit type (from ``ml_dtypes``).

Source: [proposals/data-types.md](../proposals/data-types.md)
"""

float8_e4m3fn: DType = _MLDType("float8_e4m3fn")
"""8-bit float, 4 exponent / 3 mantissa bits, finite-only (no inf).

Backed by ``ml_dtypes``; must be registered in zarr-extensions for portability.

Source: [proposals/data-types.md](../proposals/data-types.md)
"""

float8_e5m2: DType = _MLDType("float8_e5m2")
"""8-bit float, 5 exponent / 2 mantissa bits (from ``ml_dtypes``).

Source: [proposals/data-types.md](../proposals/data-types.md)
"""

float8_e4m3b11fnuz: DType = _MLDType("float8_e4m3b11fnuz")
"""8-bit float, 4e/3m, bias 11, finite-only, no signed zero (from ``ml_dtypes``).

Source: [proposals/data-types.md](../proposals/data-types.md)
"""

float8_e5m2fnuz: DType = _MLDType("float8_e5m2fnuz")
"""8-bit float, 5e/2m, finite-only, no signed zero (from ``ml_dtypes``).

Source: [proposals/data-types.md](../proposals/data-types.md)
"""

int4: DType = _MLDType("int4")
"""Signed 4-bit integer type (from ``ml_dtypes``).

Source: [proposals/data-types.md](../proposals/data-types.md)
"""

uint4: DType = _MLDType("uint4")
"""Unsigned 4-bit integer type (from ``ml_dtypes``).

Source: [proposals/data-types.md](../proposals/data-types.md)
"""
