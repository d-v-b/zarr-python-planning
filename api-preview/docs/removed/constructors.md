# mode= constructors (removed in 4.0)

The `mode=`-taking `open` / `open_group` / `open_array` (and `save` / `load`). **Replaced by** [explicit constructors](../api/open.md) that name their intent: `open_for_read`, `create`, `create_or_overwrite`, `open_or_create`. Source: [missing-apis.md](../proposals/missing-apis.md).

::: zarr_legacy.api
