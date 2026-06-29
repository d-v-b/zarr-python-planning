# Zarr-Python v4 — API Preview

!!! warning "Projected, unreleased API"
    This site is a **non-functional preview of the Zarr-Python API as it would look after the entire [v4 plan](https://github.com/d-v-b/zarr-python-planning) has landed** — the post-`4.0.0` end state. Every symbol here is a stub: signatures and docstrings only, no behavior. Names and signatures are synthesized from the planning proposals and **will change**. Signatures the proposals leave to implementation are flagged `(inferred)`.

This preview exists so reviewers and stakeholders can see the *destination* of the v4 work as one browsable API surface, instead of reconstructing it from a dozen proposal documents.

## Two versions

| | What it shows | Where |
|---|---|---|
| **Final state** | The public API after `4.0.0`, reshaped around the Zarr stack, deprecated surfaces removed. | [API reference](api/index.md) |
| **Removed surfaces** | The current-3.x surfaces the plan deprecates and removes in `4.0.0`, each pointing at its replacement. | [Removed in 4.0](removed/index.md) · [Migration map](migration.md) |

## The Zarr stack

The v4 work re-shapes `zarr-python` around a seven-level stack, where each level is something you can depend on, conform to, or replace without buying every level above it. See [The Zarr stack](stack.md) for how the levels map to modules in this preview.

## Proposal map

Each module in this preview is synthesized from one or more planning proposals:

| Area (module) | Proposal |
|---|---|
| Facade, packaging, hierarchy verbs | [functional-core.md](proposals/functional-core.md), [hierarchy-layer.md](proposals/hierarchy-layer.md), [missing-apis.md](proposals/missing-apis.md) |
| `zarr.Array` indexing | [lazy-indexing.md](proposals/lazy-indexing.md) |
| `zarr.store` | [stores.md](proposals/stores.md) (+ `stores-api`, `stores-wrappers`, `stores-caching`, `stores-range-coalescing`, `stores-transactional`, `stores-conformance`) |
| `zarr.codec` | [codecs.md](proposals/codecs.md) |
| `zarr.dtype` | [data-types.md](proposals/data-types.md) |
| Device-agnostic IO (`read_into`/`decode_into`, `to_device`) | [gpu.md](proposals/gpu.md) |
| `zarr.concurrency`, `zarr.engines`, caching | [performance.md](proposals/performance.md) |
| `zarr.observability` | [observability.md](proposals/observability.md) |
| Region writes, resize, append | [coordinated-writes.md](proposals/coordinated-writes.md) |
| `ConsolidatedMetadata` | [consolidated-metadata.md](proposals/consolidated-metadata.md) |
