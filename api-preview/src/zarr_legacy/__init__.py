"""Legacy (removed) 3.x public surfaces — zarr-python v4 API preview.

This package mirrors the public surfaces of zarr-python 3.x that are
**deprecated in 3.x and removed in 4.0.0**. The symbols here are non-functional
stubs: their signatures and docstrings document the shape of the 3.x API so that
mkdocstrings/griffe can render the "removed" tree alongside the v4 replacement
tree. Every symbol is decorated with :func:`zarr_legacy._util._legacy`, which
attaches ``__deprecated__`` and replacement metadata, and every docstring opens
with the version/replacement/migration admonition.

Each symbol names its v4 replacement. The compact OLD → NEW migration map:

| Old (3.x, removed in 4.0.0) | New (4.0.0) |
| --- | --- |
| `zarr.abc.store.Store` | `zarr.store` capability protocols (Get/GetRange/Put/Delete/List/...) + ReadResult/Generation |
| `zarr.abc.store.RangeByteRequest` / `OffsetByteRequest` / `SuffixByteRequest` | `zarr.store.RangeByteRequest` / `OffsetByteRequest` / `SuffixByteRequest` |
| `zarr.abc.store.ByteGetter` / `ByteSetter` | `zarr.store` read/write protocols |
| `zarr.abc.codec.BaseCodec` (async, batched) | `zarr.codec.Codec` (sync-first, single-element, `decode_into`) |
| `zarr.abc.codec.ArrayArrayCodec` / `ArrayBytesCodec` / `BytesBytesCodec` | single `zarr.codec.Codec` bundle (array/bytes split dropped) |
| `zarr.abc.codec.ArrayBytesCodecPartial{Decode,Encode}Mixin` | `zarr.codec.PartialDecodeCapability` flags |
| `zarr.abc.codec.CodecPipeline` | `zarr.codec` slim invocation path |
| `zarr.core.buffer.Buffer` / `NDBuffer` / `BufferPrototype` | `ReadResult`/`memoryview` contract + `read_into`/`decode_into` + Array-API namespace selection |
| `zarr.core.sync.sync` | `zarr.store.AsyncToSync` / `zarr.to_sync` |
| `zarr.api.synchronous.open` / `open_group` / `open_array` (`mode=`) | `zarr.open_for_read` / `zarr.create` / `zarr.create_or_overwrite` / `zarr.open_or_create` |
| `zarr.api.synchronous.save` / `load` | `zarr.create_or_overwrite` / `zarr.open_for_read` |
| `zarr.core.array.Array` eager `__getitem__` | lazy default + `array.eager[...]` escape hatch |
| `zarr.storage._common.StorePath` | `zarr.store.Prefixed[S]` |
| `zarr.core.config.Config` / `config` / `BadConfigError` | `zarr.config` namespaced substrate (donfig retired) |
"""

from __future__ import annotations

from .abc_buffer import Buffer, BufferPrototype, NDBuffer, default_buffer_prototype
from .abc_codec import (
    ArrayArrayCodec,
    ArrayBytesCodec,
    ArrayBytesCodecPartialDecodeMixin,
    ArrayBytesCodecPartialEncodeMixin,
    BaseCodec,
    BytesBytesCodec,
    CodecPipeline,
)
from .abc_store import (
    ByteGetter,
    ByteSetter,
    OffsetByteRequest,
    RangeByteRequest,
    Store,
    SuffixByteRequest,
)
from .api import load, open, open_array, open_group, save
from .array import Array
from .config import BadConfigError, Config, config
from .storage import StorePath
from .sync import sync

__all__ = [
    # abc_store
    "Store",
    "RangeByteRequest",
    "OffsetByteRequest",
    "SuffixByteRequest",
    "ByteGetter",
    "ByteSetter",
    # abc_codec
    "BaseCodec",
    "ArrayArrayCodec",
    "ArrayBytesCodec",
    "BytesBytesCodec",
    "ArrayBytesCodecPartialDecodeMixin",
    "ArrayBytesCodecPartialEncodeMixin",
    "CodecPipeline",
    # abc_buffer
    "Buffer",
    "NDBuffer",
    "BufferPrototype",
    "default_buffer_prototype",
    # sync
    "sync",
    # api
    "open",
    "open_group",
    "open_array",
    "save",
    "load",
    # array
    "Array",
    # storage
    "StorePath",
    # config
    "BadConfigError",
    "Config",
    "config",
]
