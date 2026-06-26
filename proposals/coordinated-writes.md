# Coordinated and Distributed Writes

> Theme proposal. For the high-level pitch, see the [parent README](../README.md).

## Summary

The rest of this proposal set develops the read path in depth — lazy indexing, a query planner, range coalescing, a caching substrate, the engine boundary — while leaving the write path *user-coordinated*: the library assumes a single process holds the array open and the caller handles not-clobbering, create-before-write, and cleanup. The two patterns that actually produce large Zarr archives — **parallel disjoint-region writes** (a coordinator creates the array, N workers each fill a non-overlapping slab) and **append-along-axis growth** (a recurring job extends an array and writes the new chunks) — have no design home yet. This proposal is the write-path theme that gives them one.

It does so by drawing a single line: between what Zarr-Python provides directly on the plain v3 format, and what it cannot provide there but instead *enables* — exposing the primitives a transactional engine builds coordination on, so that coordination extends the Zarr hierarchy rather than living in a parallel format.

- **On plain v3, Zarr-Python provides** disjoint chunk-aligned region writes, a first-class create-then-hand-out-regions primitive with chunk-alignment *checked* rather than assumed, and single-writer resize/append. None of this needs a format change. Most of it exists informally today; what is missing is that it is named, documented, and checked.
- **On plain v3, Zarr-Python cannot provide** atomicity, reader isolation, partial-failure recovery, concurrent appenders, or conflict resolution. These require a transactional substrate ([Icechunk](https://github.com/earth-mover/icechunk), OCDBT, or a future zarr-native equivalent). Zarr-Python's contribution is the *seam*: the chunk- and metadata-level primitives such an engine composes against, so it builds on top of Zarr rather than reimplementing the hierarchy beside it.

## Motivation

The rest of the proposal set covers the read path well: lazy indexing plus a query planner, range coalescing, request dedup, a caching substrate, ETag revalidation, and an engine boundary for `zarrs` / TensorStore. The write path it does not yet cover. The implicit assumption — one process, opened once, coordinating its own writes — holds for `zarr.save(...)` of a whole array. It does not match how petabyte-scale archives are produced, where no single process holds the array open and many workers (or many sequential jobs) mutate one logical array.

This is the workhorse pattern behind `xarray.to_zarr(region=...)` under Dask, [Pangeo Forge](https://pangeo-forge.readthedocs.io/) recipes, operational pipelines at NOAA and ECMWF, and sharded ML checkpointing. Without a position on it, the v4 work would scale Zarr-Python for its largest *consumers* while leaving the part of the data lifecycle that decides whether it scales for its largest *producers* undesigned. Taking that position is what this proposal is for.

The key observation is that "distributed writes" are not one thing. Disjoint, chunk-aligned region writes are already safe on plain v3: their safety comes from a coordinator partitioning work at chunk granularity so no two writers touch the same key — not from the format. They are lock-free, but they are coordinated. What plain v3 genuinely cannot provide is the *transactional* envelope — atomicity, isolation, recovery, and conflict resolution for writes that overlap or that couple a chunk write to a metadata change. A transactional engine supplies that envelope through optimistic concurrency: writers proceed independently, conflicts are detected at commit, the loser rebases. That relocates coordination into a storage layer; it does not remove it. So the design question is where that layer attaches — and the answer this proposal commits to is that it attaches to Zarr's own hierarchy primitives, not to a format that stands apart from them.

## The two patterns

### Parallel disjoint-region writes

A coordinator creates the array once. N workers then each write a non-overlapping slab, lock-free. Three things are unhandled today:

- **Create vs. write.** There is no first-class "create the array, then hand out write regions" primitive, and no guard against writing into an uninitialized array or racing to initialize it.
- **Chunk alignment.** Regions are only safe if disjoint *at the chunk level*. A region boundary that falls inside a chunk means two workers read-modify-write that chunk and one update is silently lost. Nothing surfaces or checks this — it is silent data loss, not an error.
- **Partial failure.** A write that dies halfway leaves the array torn: some chunks present, metadata claiming the full shape. With no transaction boundary there is no clean roll-back or resume.

### Append / time-series growth

A recurring job extends an array along a time axis. An append is a **coupled metadata-update + chunk-write** — resize `shape`, then write the new chunks — which is what makes it harder than a region write:

- **Metadata races.** Resize mutates array metadata; concurrent appenders race on it. There is no atomic "extend and claim the new region."
- **Partial-edge chunks.** If the axis length is not a chunk multiple, the last chunk is partially filled, so appending becomes a read-modify-write on an existing chunk — more dangerous than a fresh write and bad for concurrent readers.
- **Read-during-append.** A reader mid-append may see resized metadata before its chunks exist, or vice versa.

## What Zarr-Python provides on plain v3

These are format-agnostic primitives. They live at the [hierarchy layer](./hierarchy-layer.md) as named verbs over the store API, are composed by thin `Array` facades, and are implemented end-to-end by alternative engines.

- **A create / region-handout primitive.** A first-class "create the array, then hand out disjoint write regions" operation, distinct from "open and write," giving the coordinator/worker split an actual API instead of an informal convention.
- **Chunk-alignment checking.** A region write validates that its bounds are chunk-aligned — or that any unaligned edge is written by exactly one writer — and *surfaces* misalignment instead of silently clobbering. This is pure library logic and needs no spec support. It is the highest-value item here because it converts today's silent lost-update into a loud error.
- **Single-writer resize / append.** A named op coupling resize and new-chunk writes for the single-coordinator case, which is safe on plain v3 today and only lacks a first-class spelling.
- **A documented disjoint-write contract.** The semantics the `zarrs` / TensorStore engine boundary needs in order to behave consistently — what a region write guarantees, what alignment it requires, and what it does at unaligned edges.

## What Zarr-Python enables, but does not provide

These require a transactional substrate. Zarr-Python does not implement them; it exposes the primitives so an engine builds coordination on top of the hierarchy.

- **Atomicity** — all-or-nothing visibility of a multi-chunk-plus-metadata write.
- **Reader isolation** — a defined answer to what a reader may assume mid-write, rather than "undefined."
- **Partial-failure recovery** — resumable, roll-back-able distributed writes.
- **Concurrent appenders** — atomic "extend shape and claim the new region" under contention.
- **Conflict resolution** — optimistic-concurrency conflict detection and rebase for overlapping or metadata-coupled writes.

The [transactional layer](./stores-transactional.md) supplies the *store-level* foundation for all of this — per-key OCC via `Generation`, multi-key atomicity via `Transactional`, the manifest-swap adapter pattern — while leaving array-level coordination unspecified. This proposal closes that by naming the *array-level* seam on top of it: the hierarchy-layer verbs a transactional engine must be able to intercept — region write, resize, append, and the create/handout primitive — so the coordination layer is a clean extension of Zarr rather than a reimplementation of the hierarchy beside it.

## Append is the boundary case

Append is where the line is not clean, and treating "atomic append" as a single feature is the trap to avoid. **Single-coordinator append is a plain-v3 primitive** that just needs a name. **Concurrent-appender append needs the transactional substrate**, because the metadata race on `shape` cannot be made atomic without it. The single-writer op ships now; the concurrent case attaches to the seam rather than blocking it.

## The division at a glance

| Capability | Provided on plain v3 | Enabled via the transactional seam |
|---|---|---|
| Disjoint chunk-aligned region write | ✓ | |
| Create + region handout, alignment checked | ✓ | |
| Single-writer resize / append | ✓ | |
| Documented disjoint-write contract | ✓ | |
| Atomicity (multi-chunk + metadata) | | ✓ |
| Reader isolation mid-write | | ✓ |
| Partial-failure recovery | | ✓ |
| Concurrent appenders | | ✓ |
| Conflict resolution for overlapping writes | | ✓ |

## Spec implications

Most of the plain-v3 work needs no format change: disjoint chunk-aligned region writes, alignment checking, and single-writer append are all implementation on the existing v3 format. Only edge cases plausibly reach the spec — a partial-shard-rewrite convention, or an in-progress / torn-write metadata marker a reader could key off of — and those belong to the transactional layer, which may encode them in its own metadata rather than in the core v3 spec. The default position is **no core-spec change**, with any format-level need raised explicitly per-feature against [zarr-specs](https://github.com/zarr-developers/zarr-specs) rather than assumed.

## Relationship to the rest of the plan

- [hierarchy-layer.md](./hierarchy-layer.md) — where the plain-v3 verbs live (`write_chunk`, `write_selection`, resize, and the new create/region-handout primitive), and the engine-pluggability surface a transactional engine intercepts.
- [stores-transactional.md](./stores-transactional.md) — the store-level foundation (per-key OCC, multi-key atomicity, the transactional-adapter pattern) the enabled capabilities build on.
- [performance.md](./performance.md) — typed concurrency covers IO *within* one process; this theme covers coordination *across* processes and jobs.

## Roadmap placement

The plain-v3 work is additive and ships in **Stream 1** alongside the hierarchy-layer work — no migration, no major version. The chunk-alignment guard is a near-term, no-API-change correctness fix: an **M0** ship-now item, sibling to the LocalStore atomic-rename guard it sits next to in [stores.md](./stores.md). The create/region-handout primitive and single-writer append land in **M1** as the hierarchy layer is formalized, since they are spellings of hierarchy-layer verbs. The seam itself is a *definition* deliverable rather than implementation work — the documented set of hierarchy-layer verbs and store-level guarantees an external transactional engine composes against — and ships with the transactional substrate in M1.
