"""Pure-data metadata model for Zarr-Python v4.

Source: [proposals/functional-core.md](../proposals/functional-core.md)

This package is the functional core's metadata layer: immutable, dependency-light
value objects describing arrays, groups, chunk grids, chunk key encodings, codec
configuration, and selections. Instances carry no IO and no array data, so they
can be parsed, validated, transformed, and serialized in isolation. In the v4
packaging split these classes ship in the standalone ``zarr-metadata`` package,
which depends only on the standard library and (for typing) numpy.

Consolidated metadata (:class:`ConsolidatedMetadata`) is a flat mapping from node
path to that node's metadata, used to materialize an entire hierarchy from a
single document. See proposals/consolidated-metadata.md and
proposals/data-types.md for the data-type model referenced by ``data_type``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from zarr.codec import Codec
    from zarr.dtype import DType

__all__ = [
    "ArrayMetadata",
    "ArrayV3Metadata",
    "GroupMetadata",
    "ConsolidatedMetadata",
    "ChunkGrid",
    "RegularChunkGrid",
    "RectilinearChunkGrid",
    "ChunkKeyEncoding",
    "DefaultChunkKeyEncoding",
    "V2ChunkKeyEncoding",
    "CodecConfig",
    "Selection",
    "chunk_key",
    "chunk_grid_shape",
]


@dataclass(frozen=True)
class ChunkGrid:
    """Base class for chunk grids describing how an array is partitioned.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]:
        """Serialize this chunk grid to a JSON-compatible dict. (inferred)

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct a chunk grid from its serialized form. (inferred)

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...


@dataclass(frozen=True)
class RegularChunkGrid(ChunkGrid):
    """Chunk grid with a uniform chunk shape across each dimension.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    chunk_shape: tuple[int, ...]


@dataclass(frozen=True)
class RectilinearChunkGrid(ChunkGrid):
    """Chunk grid with per-dimension variable chunk extents. (inferred)

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    chunk_shapes: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class ChunkKeyEncoding:
    """Base class for encoding chunk coordinates into store keys.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    def encode(self, coords: tuple[int, ...]) -> str:
        """Encode chunk coordinates into a store key. (inferred)

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...

    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]:
        """Serialize this chunk key encoding to a dict. (inferred)

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct a chunk key encoding from its serialized form. (inferred)

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...


@dataclass(frozen=True)
class DefaultChunkKeyEncoding(ChunkKeyEncoding):
    """Zarr v3 default chunk key encoding (``c/0/0`` style). (inferred)

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    separator: str = "/"


@dataclass(frozen=True)
class V2ChunkKeyEncoding(ChunkKeyEncoding):
    """Zarr v2 chunk key encoding (``0.0`` style). (inferred)

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    separator: str = "."


@dataclass(frozen=True)
class CodecConfig:
    """Serializable configuration for a single codec in the pipeline. (inferred)

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    name: str
    configuration: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Selection:
    """A normalized selection over an array's index space. (inferred)

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    indexer: Any


@dataclass(frozen=True)
class ArrayMetadata:
    """Base class for array metadata, independent of Zarr format version.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]:
        """Serialize this metadata to a JSON-compatible dict.

        When ``deterministic`` is true, keys are emitted in a stable order so
        the output is byte-reproducible.

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct array metadata from its serialized form.

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...


@dataclass(frozen=True)
class ArrayV3Metadata(ArrayMetadata):
    """Metadata for a Zarr v3 array.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    shape: tuple[int, ...]
    data_type: DType
    chunk_grid: ChunkGrid
    chunk_key_encoding: ChunkKeyEncoding
    fill_value: Any
    codecs: tuple[Codec, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    dimension_names: tuple[str | None, ...] | None = None
    node_type: str = "array"
    zarr_format: int = 3


@dataclass(frozen=True)
class GroupMetadata:
    """Metadata for a Zarr group.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """

    attributes: dict[str, Any] = field(default_factory=dict)
    node_type: str = "group"
    zarr_format: int = 3

    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]:
        """Serialize this group metadata to a JSON-compatible dict.

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct group metadata from its serialized form.

        Source: [proposals/functional-core.md](../proposals/functional-core.md)
        """
        ...


@dataclass(frozen=True)
class ConsolidatedMetadata:
    """A flat mapping from node path to that node's metadata.

    Materializes an entire hierarchy from a single consolidated document.

    Source: [proposals/consolidated-metadata.md](../proposals/consolidated-metadata.md)
    """

    metadata: dict[str, ArrayMetadata | GroupMetadata] = field(default_factory=dict)

    def to_dict(self, *, deterministic: bool = False) -> dict[str, Any]:
        """Serialize the consolidated metadata to a JSON-compatible dict.

        Source: [proposals/consolidated-metadata.md](../proposals/consolidated-metadata.md)
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Construct consolidated metadata from its serialized form.

        Source: [proposals/consolidated-metadata.md](../proposals/consolidated-metadata.md)
        """
        ...


def chunk_key(metadata: ArrayMetadata, coords: tuple[int, ...]) -> str:
    """Compute the store key for the chunk at ``coords``.

    Pure function; ships in the ``zarr-metadata`` package.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """
    ...


def chunk_grid_shape(metadata: ArrayMetadata) -> tuple[int, ...]:
    """Compute the number of chunks along each dimension.

    Pure function; ships in the ``zarr-metadata`` package.

    Source: [proposals/functional-core.md](../proposals/functional-core.md)
    """
    ...
