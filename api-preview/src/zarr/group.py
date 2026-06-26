"""Group API surface for Zarr-Python v4 (projected final state).

Non-functional stubs: signatures and docstrings only. Annotations are strings at
runtime; types owned elsewhere (GroupMetadata, Array, etc.) are referenced by bare
name without importing.

Sources: [proposals/missing-apis.md](../proposals/missing-apis.md), [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from collections.abc import AsyncIterator, Hashable, Iterator

if TYPE_CHECKING:
    from zarr.array import Array
    from zarr.metadata import GroupMetadata

__all__ = [
    "Group",
]


class Group:
    """A Zarr group: a named node holding child arrays and sub-groups.

    Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
    """

    @property
    def name(self) -> str:
        """The node name (final path component) of the group.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def path(self) -> str:
        """The full path of the group within its store hierarchy.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def metadata(self) -> GroupMetadata:
        """The group metadata document.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    @property
    def attrs(self) -> dict[str, Any]:
        """The user-defined attributes of the group.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __getitem__(self, key: str) -> Array | Group:
        """Look up a child node by ``key``.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def __setitem__(self, key: str, value: Array | Group) -> None:
        """Assign a child node at ``key``.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def __contains__(self, key: str) -> bool:
        """Return whether a child node named ``key`` exists.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def __iter__(self) -> Iterator[str]:
        """Iterate over the names of direct child nodes.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def __truediv__(self, name: str) -> Array | Group:
        """Hierarchy traversal: ``group / "a" / "b"``.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def list_children(self) -> Iterator[str]:
        """Iterate over the names of direct child nodes.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def node_exists(self, path: str) -> bool:
        """Return whether a node exists at ``path`` relative to this group.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def node_kind(self, path: str) -> Literal["array", "group", "absent"]:
        """Return the kind of node at ``path`` relative to this group.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def walk(self) -> Iterator[str]:
        """Recursively iterate over all descendant node paths.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def delete(self, path: str) -> None:
        """Delete the node at ``path`` relative to this group.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md)
        """
        ...

    def create_array(self, name: str, **kwargs: Any) -> Array:
        """Create a child array named ``name`` and return it.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def create_group(self, name: str, **kwargs: Any) -> Group:
        """Create a child group named ``name`` and return it.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __repr__(self) -> str:
        """Return a concise text representation of the group.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def _repr_html_(self) -> str:
        """Return a rich HTML representation for notebook display.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def tree(self, *, meta: bool = True) -> str:
        """Return a tree rendering of the group hierarchy.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def with_caching(
        self,
        *,
        metadata: bool = True,
        chunks: bool | str = False,
        negative: bool = False,
    ) -> Group:
        """Return a view of this group with the given caching behavior enabled.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
        """
        ...

    def __enter__(self) -> Group:
        """Enter a context manager scope for the group.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __exit__(self, *exc: object) -> None:
        """Exit the context manager scope, releasing resources.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    def __dask_tokenize__(self) -> Hashable:
        """Return a deterministic token identifying this group for Dask.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
        """
        ...

    # ------------------------------------------------------------------ #
    # Async twins.
    #
    # There is no separate ``AsyncGroup`` class: a single ``Group`` holds all
    # the code, and async is exposed *selectively* via ``*_async`` methods on
    # only the IO-bound traversal and creation operations. Property access and
    # display helpers stay pure-sync.
    #
    # Source: proposals/functional-core.md (single-class direction), and the
    # discussion on zarr-developers/zarr-python#4049.
    # ------------------------------------------------------------------ #
    async def getitem_async(self, key: str) -> Array | Group:
        """Awaitable variant of :meth:`__getitem__` (child-node lookup).

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md) (inferred)
        """
        ...

    async def list_children_async(self) -> AsyncIterator[str]:
        """Awaitable variant of :meth:`list_children`.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md) (inferred)
        """
        ...

    async def walk_async(self) -> AsyncIterator[str]:
        """Awaitable variant of :meth:`walk`.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md) (inferred)
        """
        ...

    async def create_array_async(self, name: str, **kwargs: Any) -> Array:
        """Awaitable variant of :meth:`create_array`.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
        """
        ...

    async def create_group_async(self, name: str, **kwargs: Any) -> Group:
        """Awaitable variant of :meth:`create_group`.

        Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
        """
        ...

    async def delete_async(self, path: str) -> None:
        """Awaitable variant of :meth:`delete`.

        Source: [proposals/hierarchy-layer.md](../proposals/hierarchy-layer.md) (inferred)
        """
        ...
