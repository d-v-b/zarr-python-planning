# Zarr-Python Issue Triage Plan

Living document for triage state, release paths, and priorities — the tactical companion to [`README.md`](./README.md)'s Zarr-Python 4.0 strategy. The README sets direction (what should change, and why); this doc picks which pieces land in which release and tracks near-term issue dispositions. The Tier-3 priorities below are keyed to the README's section taxonomy (Packaging, Codecs, Stores, etc.) so strategy and execution stay in sync.

Edit directly as things change; don't annotate with "since last snapshot" notes. Issue/PR state references may drift — refresh with `bash scripts/check_issue_states.sh` (reads `outputs/refs.txt`, writes `outputs/states.jsonl`).

---

## Executive Summary

The zarr-python repo carries several hundred open issues. A large fraction (~1/3) are pre-v3 and mostly no longer actionable; another large block is unlabeled v3-era noise. The most active clusters are **stores**, **codecs**, **v2/v3 migration**, **documentation**, and **performance** (the latter being the current active workstream).

---

## Path to 3.2.0

**Release tracking issue**: [#3888](https://github.com/zarr-developers/zarr-python/issues/3888) (scheduled April 2026, date TBD).
**Last shipped**: v3.1.6 (2026-03-20). **Current milestone** (#28) has **only PR [#3325](https://github.com/zarr-developers/zarr-python/pull/3325)**.

### Why 3.2.0 and not 3.1.7

Rectilinear chunks ([#3802](https://github.com/zarr-developers/zarr-python/pull/3802)) are opt-in and the only public API change they brought was to the codec-pipeline `validate` signature (which had no known consumers). That alone would justify a patch release. What makes this a minor release is [#3325](https://github.com/zarr-developers/zarr-python/pull/3325) — removing deprecated functions is breaking. If #3325 is dropped from scope, the release should be re-evaluated as 3.1.7.

### Release drivers

Three things in-reach for 3.2.0:

1. **Rectilinear (variable-sized) chunks** — shipped experimental via [#3802](https://github.com/zarr-developers/zarr-python/pull/3802), follow-up [#3909](https://github.com/zarr-developers/zarr-python/pull/3909).
2. **Remove global concurrency limit** — [#3547](https://github.com/zarr-developers/zarr-python/pull/3547) "store-defined concurrency limits." Unblocks throughput on local/memory storage.
3. **Performance improvements from skipping asyncio overhead on local/memory** — the phased codec pipeline workstream. The landing vehicles are [#3885](https://github.com/zarr-developers/zarr-python/pull/3885) (main) and [#3892](https://github.com/zarr-developers/zarr-python/pull/3892) (supporting); precursor [#3715](https://github.com/zarr-developers/zarr-python/pull/3715) has already merged. Davis maintains a design doc at [hackmd](https://hackmd.io/@d-v-b/ryKDvpFdbl).

The deprecation sweep ([#3325](https://github.com/zarr-developers/zarr-python/pull/3325)) is the fourth must-land and the reason the release is minor rather than patch.

### Must-land before cutting the release

| PR / Issue | Status | Action |
|---|---|---|
| [#3325](https://github.com/zarr-developers/zarr-python/pull/3325) "Remove deprecated API" | Draft, **conflicting** | Rebase onto main, un-draft, merge as the **last** PR before tagging (author intent — simplifies 3.1.x backports). Closes [#3317](https://github.com/zarr-developers/zarr-python/issues/3317). |
| [#3547](https://github.com/zarr-developers/zarr-python/pull/3547) "store-defined concurrency limits" | Open, mergeable, needs review | Requested explicitly in the 3.2.0 wish-list. Needs reviewer assignment. |
| [#3888](https://github.com/zarr-developers/zarr-python/issues/3888) release checklist | Open | Fill in "Priority PRs/issues" section once scope is locked. |
| `towncrier build --version 3.2.0` | Not yet run | Run after last merge; commit to release branch. Current `changes/` has 19 entries ready. |
| Downstream smoke tests | Not yet run | xarray upstream-dev, numcodecs, titiler.xarray (per checklist in [#3888](https://github.com/zarr-developers/zarr-python/issues/3888)). |

### Scope decisions needed

Each of the following has an open question — decide **in** or **defer to 3.3** before locking the milestone.

| Candidate | State | Recommendation |
|---|---|---|
| **Perf: phased codec pipeline** — [#3885](https://github.com/zarr-developers/zarr-python/pull/3885) (main), [#3891](https://github.com/zarr-developers/zarr-python/pull/3891) (benchmarks, do-not-merge), [#3892](https://github.com/zarr-developers/zarr-python/pull/3892) (codec classes in array config) | #3885 open/mergeable; #3892 **conflicting**; Ilan actively benchmarking | The big performance lever. Davis's framing: codec pipeline needs a "preparation phase" so IO is separated from compute. Benchmarks show ~33% read_all improvement; bigger wins expected once integrated with the Array class. **Decide**: land #3885 + #3892 and make the new pipeline opt-in (safe), or defer entirely (simpler release). If opt-in, label releases as experimental and don't make it default in 3.2.0. |
| [#3874](https://github.com/zarr-developers/zarr-python/pull/3874) "cast_value and scale_offset codecs" | Open, mergeable, **changes requested** | Replacement for the problematic `numcodecs.fixedscaleoffset` codec in Zarr V3. Davis actively iterating. **Decide**: resolve review feedback and include (closes a known V3 gap), or accept that external package ownership ([#3867](https://github.com/zarr-developers/zarr-python/issues/3867) discussion) is the long-term path. |
| [#3559](https://github.com/zarr-developers/zarr-python/pull/3559) "add bytes dtype" — labeled `v3.2` | Conflicting, no activity since 2026-01-08, depends on zarr-extensions PR #38 | **Decide**: if the extensions PR lands and someone can rebase+review this week, include; otherwise drop the `v3.2` label and defer. Don't block the release on a stale PR. |
| [#3899](https://github.com/zarr-developers/zarr-python/pull/3899) "simplify internal chunk representation" | Open, mergeable, very recent (2026-04-20) | **Decide**: risk vs. value. Refactors during the rectilinear experimental window are attractive but can introduce subtle regressions. Default to defer unless the author flags it as a prerequisite for something shipped. |
| [#3534](https://github.com/zarr-developers/zarr-python/pull/3534) "support rectilinear chunk grid extension" | Conflicting, stale | Likely superseded by merged [#3802](https://github.com/zarr-developers/zarr-python/pull/3802) — close or confirm remaining diff. |
| Remaining deprecation issues: [#3457](https://github.com/zarr-developers/zarr-python/issues/3457) (enums), [#3454](https://github.com/zarr-developers/zarr-python/issues/3454) (`to_dict`), [#3402](https://github.com/zarr-developers/zarr-python/issues/3402) (templated exceptions) | Open, no PRs, no maintainer comments since opening (Aug–Sep 2025) | Land deprecation *warnings* in 3.2.0 or 3.3 ad-hoc, following the same pattern as #3325 → #3900–#3903 (warn in release N, remove in N+1). Don't block on #2924 — see "deprecation policy" note below. Also: [#3499](https://github.com/zarr-developers/zarr-python/issues/3499) (`create_dataset` not removed) is effectively **resolved** by #3902 and should be closed. |
| Unlabeled candidates from recent activity: [#3875](https://github.com/zarr-developers/zarr-python/pull/3875) (codec/dtype subpackage refactor), [#3698](https://github.com/zarr-developers/zarr-python/pull/3698) (obspec generic ObjectStore), [#3906](https://github.com/zarr-developers/zarr-python/pull/3906) (IndexTransform), [#3587](https://github.com/zarr-developers/zarr-python/pull/3587) (subarray dtypes) | Mixed | Apply `v3.2` label if targeted, otherwise leave for 3.3. None are currently in the milestone. |

### Deprecation policy ([#2924](https://github.com/zarr-developers/zarr-python/issues/2924))

Open since March 2025 with zero maintainer comments. Treat this as a **prerequisite for the metadata-dumbening work** ([#3884](https://github.com/zarr-developers/zarr-python/issues/3884)) — that's where a larger deprecation surface actually needs governance. **Don't** treat it as a blocker for the small residual deprecations (#3457, #3454, #3402); those can follow the de-facto pattern that #3325 → #3900–#3903 already established: add a warning in release N, remove in release N+1. Retrofit policy to small things is more friction than it's worth.

### Milestone hygiene

1. **3.1.2 milestone (#27) is stale** — 3.1.6 has shipped. Close it and re-milestone its 4 open PRs:
   - [#3345](https://github.com/zarr-developers/zarr-python/pull/3345) fix non-int 0 fill values → 3.2.0 (bug fix, ready)
   - [#3215](https://github.com/zarr-developers/zarr-python/pull/3215) `refresh_attributes` / `cache_attrs` → 3.2.0 or 3.3
   - [#3511](https://github.com/zarr-developers/zarr-python/pull/3511) backport of #3300 → close unless a 3.1.7 is planned
   - [#2856](https://github.com/zarr-developers/zarr-python/pull/2856) open ZipStore from `.zip` path → 3.2.0 or 3.3
2. **Add `v3.2` label to milestone-#28 items** so the label and milestone stay in sync.
3. **Fill in [#3888](https://github.com/zarr-developers/zarr-python/issues/3888) "Priority PRs" section** with the locked-in list.

### Recommended sequence

1. **This week** — close stale 3.1.2 milestone; re-milestone the 4 PRs; decide on [#3559](https://github.com/zarr-developers/zarr-python/pull/3559) / [#3899](https://github.com/zarr-developers/zarr-python/pull/3899) scope; close [#3534](https://github.com/zarr-developers/zarr-python/pull/3534) if superseded.
2. **Merge window** — land any in-scope features, then [#3345](https://github.com/zarr-developers/zarr-python/pull/3345) bug fix.
3. **Feature freeze** — rebase and land [#3325](https://github.com/zarr-developers/zarr-python/pull/3325) (deprecated API removal) as the last content change.
4. **Release day** — run `towncrier build --version 3.2.0`, execute [#3888](https://github.com/zarr-developers/zarr-python/issues/3888) checklist, tag `v3.2.0`, verify downstreams.

### Codebase TODOs to sweep

Per the [#3888](https://github.com/zarr-developers/zarr-python/issues/3888) checklist (`grep "# TODO" **/*.py`): most TODOs are long-standing type debt or accepted followups. Three clusters warrant a decision before cutting the release.

**Tied to pending deprecation issues (resolve together with the issue decision):**

| TODO | Tied to |
|---|---|
| [`src/zarr/codecs/bytes.py:73`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/codecs/bytes.py#L73) "remove endianness enum in favor of literal union" | [#3457](https://github.com/zarr-developers/zarr-python/issues/3457) deprecate/remove enums |
| [`src/zarr/core/metadata/v3.py:670`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/metadata/v3.py#L670) "replace `to_dict`/`from_dict` on `Metadata` with `to_json`/`from_json`" | [#3454](https://github.com/zarr-developers/zarr-python/issues/3454) deprecate `to_dict` |

If #3457 / #3454 land in 3.2.0, clear these TODOs in the same PR. If deferred, leave them.

**Stale migration notes (sweep regardless — shouldn't ship as-is):**

- [`src/zarr/api/synchronous.py:619`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/api/synchronous.py#L619) `object_codec` "type has changed"
- [`src/zarr/api/synchronous.py:621`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/api/synchronous.py#L621) `write_empty_chunks` "default has changed"
- [`src/zarr/api/asynchronous.py:866`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/api/asynchronous.py#L866) (parallel `object_codec`)
- [`src/zarr/api/asynchronous.py:870`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/api/asynchronous.py#L870) (parallel `meta_array` "need type")

Either fix the signatures or delete the dangling migration comments before 3.2.0.

**Explicitly non-blocking (leave for 3.3+):**

- [`src/zarr/core/chunk_grids.py:140`](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/core/chunk_grids.py#L140) `TODO(perf):` — acceptable because rectilinear ships experimental.
- ~34 `# TODO: add type annotations for kwargs` / `# TODO: type kwargs as valid args to ...` across `api/{synchronous,asynchronous}.py` — long-standing type debt.
- 9 TODOs in `core/indexing.py`, 10 in `core/array.py` — architectural refactors tracked elsewhere.
- GPU zero-copy dlpack path in `core/buffer/gpu.py` — feature work.

---

### What this release is NOT

Punt to 3.3+ / 4.0 to keep 3.2.0 shippable:
- **Full V3 performance parity** — the phased codec pipeline ships opt-in in 3.2.0 if it lands; making it default and reaching parity is 3.3+ work.
- **Array / AsyncArray split rethink** — flagged by Davis as architectural; not concrete enough.
- **Dumber metadata classes** ([#3884](https://github.com/zarr-developers/zarr-python/issues/3884)) — aligned direction, but touches a lot of code. Planning in progress.
- **Codec library separation** ([#3867](https://github.com/zarr-developers/zarr-python/issues/3867)) — package-level decision, needs discussion.
- **Store API redesign** ([#3758](https://github.com/zarr-developers/zarr-python/issues/3758), [#3698](https://github.com/zarr-developers/zarr-python/pull/3698)) — architectural; incremental path is dual-API via protocols.
- **Lazy indexing** — experimental branch, not ready.
- **Structured dtype support** ([#2134](https://github.com/zarr-developers/zarr-python/issues/2134)) — large, design-in-progress.
- **GPU / device support expansion** ([#2658](https://github.com/zarr-developers/zarr-python/issues/2658)).
- **V2 → V3 migration tooling** ([#1798](https://github.com/zarr-developers/zarr-python/issues/1798), [#3076](https://github.com/zarr-developers/zarr-python/issues/3076)).
- **Multi-array codec pipelines** (Justus's exploration) — research-stage.

---

## Most Important Features to Land

### Tier 1: Must-Have (blocking adoption / retention)

#### 1. V3 Performance Parity — **active workstream**
User-side tracking: [#2710](https://github.com/zarr-developers/zarr-python/issues/2710), [#2529](https://github.com/zarr-developers/zarr-python/issues/2529), [#3524](https://github.com/zarr-developers/zarr-python/issues/3524), [#2904](https://github.com/zarr-developers/zarr-python/issues/2904).
Design: Davis's performance plan at [hackmd.io/@d-v-b/ryKDvpFdbl](https://hackmd.io/@d-v-b/ryKDvpFdbl).
Landing PRs: [#3715](https://github.com/zarr-developers/zarr-python/pull/3715) merged (sync codecs + threadpool), [#3885](https://github.com/zarr-developers/zarr-python/pull/3885) phased codec pipeline open, [#3892](https://github.com/zarr-developers/zarr-python/pull/3892) codec classes in array config open, [#3547](https://github.com/zarr-developers/zarr-python/pull/3547) remove global concurrency limit open.

Multiple users report v3 is measurably slower than v2 for indexing, iteration, and codec pipeline operations. The root-cause work is the phased codec pipeline: codecs shouldn't do IO, and the pipeline should have a preparation phase that separates IO from compute. Benchmarks against `zarrs` show the gap closing as the new pipeline lands (~33% read_all improvement observed in Ilan's local benchmarks; integration with the `Array` class is the next step for larger gains).

#### 2. V2 -> V3 Migration Path
[#1798](https://github.com/zarr-developers/zarr-python/issues/1798) (15c, 5 reactions), [#3076](https://github.com/zarr-developers/zarr-python/issues/3076) (8c)

The CLI conversion tool exists but is incomplete ([#3466](https://github.com/zarr-developers/zarr-python/issues/3466), [#3467](https://github.com/zarr-developers/zarr-python/issues/3467), [#3468](https://github.com/zarr-developers/zarr-python/issues/3468)). Users are confused about how to migrate ([#3024](https://github.com/zarr-developers/zarr-python/issues/3024), [#2981](https://github.com/zarr-developers/zarr-python/issues/2981)). This is the #1 practical blocker — people have petabytes of v2 data and need a clear, well-documented, performant migration path.

#### 3. Structured Dtype Support
[#2134](https://github.com/zarr-developers/zarr-python/issues/2134) (25c — highest comment count of any feature issue)

18 months old, 25 comments. Scientific users (climate, bio, remote sensing) depend on structured dtypes. This is the most-discussed dtype gap and blocks real workloads.

### Tier 2: High Impact (significant user demand)

#### 4. GPU / Device Support
[#2658](https://github.com/zarr-developers/zarr-python/issues/2658) (9c, 6 reactions — highest reaction count), [#3640](https://github.com/zarr-developers/zarr-python/issues/3640), [#3271](https://github.com/zarr-developers/zarr-python/issues/3271)

ML/AI is the fastest-growing zarr audience. CuPy/JAX users need zero-copy device arrays. 6 thumbs-up reactions is the strongest user signal in the repo.

#### 5. Batched Store API
[#1806](https://github.com/zarr-developers/zarr-python/issues/1806) (24c), [#1805](https://github.com/zarr-developers/zarr-python/issues/1805) (11c)

23 months old, 24 comments. Batch get/set is essential for efficient cloud I/O — reading 100 chunks should be 1 round of concurrent requests, not 100 sequential ones. This directly impacts performance for every remote store user.

#### 6. Object Array Support
[#2617](https://github.com/zarr-developers/zarr-python/issues/2617) (16c), related: [#2618](https://github.com/zarr-developers/zarr-python/issues/2618) (ragged arrays, 5c)

Object arrays and ragged arrays worked in v2 and are broken/missing in v3. This blocks users with heterogeneous data (strings, nested structures).

#### 7. bfloat16 / Extended Dtype Support
[#2656](https://github.com/zarr-developers/zarr-python/issues/2656) (9c, 3 reactions), [#3665](https://github.com/zarr-developers/zarr-python/issues/3665) (quad-precision)

bfloat16 is standard in ML. 3 thumbs-up. The dtype extension system exists but lacks the types users actually need.

### Tier 3: Important (architecture / ecosystem)

#### 8. Codec Pipeline Redesign — **active, same workstream as #1**
User-side tracking: [#3162](https://github.com/zarr-developers/zarr-python/issues/3162), [#3703](https://github.com/zarr-developers/zarr-python/issues/3703), [#3051](https://github.com/zarr-developers/zarr-python/issues/3051), [#2654](https://github.com/zarr-developers/zarr-python/issues/2654).
Landing PR: [#3885](https://github.com/zarr-developers/zarr-python/pull/3885) phased codec pipeline.

The key insight driving the redesign: codecs do not need to do IO. Some codecs (sharding, nested sharding) require IO to be done on their behalf before they can encode/decode. Formalizing this as a preparation phase at the pipeline level lets the pipeline distinguish a single sharding codec (needs one IO round to fetch the index) from a nested sharding codec (needs multiple). This unblocks user-defined codecs ([#3505](https://github.com/zarr-developers/zarr-python/issues/3505)), numcodecs decoupling ([#3783](https://github.com/zarr-developers/zarr-python/issues/3783), [#3461](https://github.com/zarr-developers/zarr-python/issues/3461)), and the scale_offset/cast_value codecs ([#3874](https://github.com/zarr-developers/zarr-python/pull/3874), replacing [#3772](https://github.com/zarr-developers/zarr-python/issues/3772)).

#### 9. Store API Improvements
User-side tracking: [#3758](https://github.com/zarr-developers/zarr-python/issues/3758) (protocol-based stores), [#3831](https://github.com/zarr-developers/zarr-python/issues/3831), [#3675](https://github.com/zarr-developers/zarr-python/issues/3675) (Store.set takes bytes), [#3637](https://github.com/zarr-developers/zarr-python/issues/3637), [#3429](https://github.com/zarr-developers/zarr-python/issues/3429) (read into buffer), [#2272](https://github.com/zarr-developers/zarr-python/pull/2272).

The store abstraction is the largest issue cluster (~51 open). The async-only v3 Store API is a known source of friction (Davis in discussion: "making all the store methods async vastly degraded user experience"). Because the `Store` class is used by several downstream projects, breaking changes are hard to do incrementally. The proposed path is to define a second store API via **protocols** and add internal logic that handles objects implementing either the old or new API — this lets improvements land without forcing downstream breakage. Related goals: zero-copy reads ([#3429](https://github.com/zarr-developers/zarr-python/issues/3429)), obstore as the cloud default ([#3520](https://github.com/zarr-developers/zarr-python/issues/3520)).

#### 10. Codec Library Separation — **architectural blocker**
[#3867](https://github.com/zarr-developers/zarr-python/issues/3867).

Because zarr-python uses an ABC for codec classes, any external codec library must depend on zarr-python. This means zarr-python can't safely declare external codec libraries as dependencies (circular). Davis is leaning toward moving codec and data-type base class definitions into a separate package (kept in the zarr-python repo as a sub-package, similar to how `zarrs` organizes `zarrs_codec`). Without this, the codec extension ecosystem can't grow cleanly and PRs like [#3874](https://github.com/zarr-developers/zarr-python/pull/3874) face pressure to live outside the tree entirely.

#### 11. Public Metadata API — **architectural, ecosystem leverage**
[#3884](https://github.com/zarr-developers/zarr-python/issues/3884), [#3795](https://github.com/zarr-developers/zarr-python/issues/3795), [#3786](https://github.com/zarr-developers/zarr-python/issues/3786).

Proposal: make `ArrayV3Metadata` "dumber" — every field a JSON-style type (e.g. `codecs: tuple[str | NamedConfig, ...]` instead of instantiated codec objects). This separates document shape from behavior: metadata classes own the shape, consumers own the class creation. This is high-leverage for downstream libs — VirtualiZarr in particular does to_dict → mutate → from_dict as its primary pattern and has to work around getting codec config via 4 different code paths. Max + Davis aligned on direction; Max wants this fast-tracked and has proposed a planning call.

#### 12. Iterative Shard Writing
[#3604](https://github.com/zarr-developers/zarr-python/issues/3604).

Sharding is a headline v3 feature but writing shards chunk-by-chunk is inefficient. TensorStore-style transactional writes would make sharding practical for streaming/append workloads. Related: in discussion, Davis noted that the current "fetch full shard when reading all subchunks" behavior is actually incorrect — the correct approach is per-subchunk byte-range requests coalesced at the store layer (which `zarrs` handles in the codec, not the store; tuning tradeoffs are not yet settled).

#### 13. Lazy Indexing — **experimental direction**
Davis's branch [feat/lazy-indexing](https://github.com/d-v-b/zarr-python/tree/feat/lazy-indexing), PR [#3906](https://github.com/zarr-developers/zarr-python/pull/3906) IndexTransform.

TensorStore-style slicing where `Array.__getitem__` returns a smaller `Array` rather than materializing numpy. Works with dask via silent coercion. Important for reducing memory consumption irrespective of codec-pipeline or Array-class changes. Independent of, but complementary to, the performance workstream.

**Note:** User-Defined Chunk Grids ([#3750](https://github.com/zarr-developers/zarr-python/issues/3750)) was closed — the extensibility question is now addressed by the rectilinear work ([#3802](https://github.com/zarr-developers/zarr-python/pull/3802)).

### Feature Priority Matrix

| Feature | User Pain | Engagement | Strategic Value | Effort | Status |
|---------|-----------|------------|-----------------|--------|--------|
| V3 Performance Parity | Critical | High | Adoption blocker | Large | **Active** (perf workstream) |
| Codec Pipeline Redesign | Medium | Multiplier | Unlocks many issues | Large | **Active** (same PRs) |
| V2 → V3 Migration | Critical | High | Adoption blocker | Medium | Not started |
| Structured Dtypes | High | High | Scientific users | Large | Design-in-progress |
| GPU / Device Support | High | High | ML ecosystem | Large | Incremental |
| Batched Store API | High | High | Cloud perf | Medium | Part of Store API work |
| Object Arrays | High | Medium | v2 compat | Medium | Not started |
| bfloat16 | Medium | Low | ML ecosystem | Small | Not started |
| Store API Protocols | Medium | Largest cluster | Architecture | Medium | Proposed (dual-API via protocols) |
| Codec Library Separation | Medium | Architectural | Ecosystem unblock | Medium | Proposed |
| Public Metadata API | Medium | High (downstream) | Ecosystem unblock | Large | Aligned, planning |
| Iterative Shard Writing | Medium | Medium | Cloud-native | Medium | Not started |
| Lazy Indexing | Medium | New | Memory efficiency | Large | Experimental PR |

The current active workstream is **performance + codec pipeline** (same PRs serve both). The next architectural lifts most frequently cited by maintainers are **store API protocols**, **codec library separation**, and the **public metadata API** — none in 3.2.0 scope, all worth scoping out for subsequent releases.

---

## Recommended Actions

### 1. Quick Wins — Bulk Close/Label

#### Close: V2-Era Issues No Longer Relevant
Issues 3+ years old that reference v2-only APIs (DirectoryStore, LRUStoreCache, ProcessSynchronizer, etc.). Many have been superseded by the v3 rewrite. Candidates:

[#40](https://github.com/zarr-developers/zarr-python/issues/40), [#134](https://github.com/zarr-developers/zarr-python/issues/134), [#149](https://github.com/zarr-developers/zarr-python/issues/149), [#166](https://github.com/zarr-developers/zarr-python/issues/166), [#202](https://github.com/zarr-developers/zarr-python/issues/202), [#216](https://github.com/zarr-developers/zarr-python/issues/216), [#224](https://github.com/zarr-developers/zarr-python/issues/224), [#233](https://github.com/zarr-developers/zarr-python/issues/233), [#247](https://github.com/zarr-developers/zarr-python/issues/247), [#264](https://github.com/zarr-developers/zarr-python/issues/264), [#270](https://github.com/zarr-developers/zarr-python/issues/270), [#297](https://github.com/zarr-developers/zarr-python/issues/297), [#298](https://github.com/zarr-developers/zarr-python/issues/298), [#321](https://github.com/zarr-developers/zarr-python/issues/321), [#328](https://github.com/zarr-developers/zarr-python/issues/328), [#354](https://github.com/zarr-developers/zarr-python/issues/354), [#384](https://github.com/zarr-developers/zarr-python/issues/384), [#389](https://github.com/zarr-developers/zarr-python/issues/389), [#390](https://github.com/zarr-developers/zarr-python/issues/390), [#392](https://github.com/zarr-developers/zarr-python/issues/392), [#415](https://github.com/zarr-developers/zarr-python/issues/415), [#424](https://github.com/zarr-developers/zarr-python/issues/424), [#435](https://github.com/zarr-developers/zarr-python/issues/435), [#438](https://github.com/zarr-developers/zarr-python/issues/438), [#477](https://github.com/zarr-developers/zarr-python/issues/477), [#486](https://github.com/zarr-developers/zarr-python/issues/486), [#487](https://github.com/zarr-developers/zarr-python/issues/487), [#502](https://github.com/zarr-developers/zarr-python/issues/502), [#514](https://github.com/zarr-developers/zarr-python/issues/514), [#543](https://github.com/zarr-developers/zarr-python/issues/543), [#545](https://github.com/zarr-developers/zarr-python/issues/545), [#548](https://github.com/zarr-developers/zarr-python/issues/548), [#555](https://github.com/zarr-developers/zarr-python/issues/555), [#566](https://github.com/zarr-developers/zarr-python/issues/566), [#583](https://github.com/zarr-developers/zarr-python/issues/583), [#587](https://github.com/zarr-developers/zarr-python/issues/587), [#592](https://github.com/zarr-developers/zarr-python/issues/592), [#595](https://github.com/zarr-developers/zarr-python/issues/595), [#605](https://github.com/zarr-developers/zarr-python/issues/605), [#673](https://github.com/zarr-developers/zarr-python/issues/673), [#690](https://github.com/zarr-developers/zarr-python/issues/690), [#736](https://github.com/zarr-developers/zarr-python/issues/736), [#771](https://github.com/zarr-developers/zarr-python/issues/771), [#785](https://github.com/zarr-developers/zarr-python/issues/785), [#804](https://github.com/zarr-developers/zarr-python/issues/804), [#809](https://github.com/zarr-developers/zarr-python/issues/809), [#828](https://github.com/zarr-developers/zarr-python/issues/828), [#857](https://github.com/zarr-developers/zarr-python/issues/857), [#917](https://github.com/zarr-developers/zarr-python/issues/917), [#962](https://github.com/zarr-developers/zarr-python/issues/962), [#980](https://github.com/zarr-developers/zarr-python/issues/980), [#982](https://github.com/zarr-developers/zarr-python/issues/982), [#1017](https://github.com/zarr-developers/zarr-python/issues/1017), [#1018](https://github.com/zarr-developers/zarr-python/issues/1018), [#1113](https://github.com/zarr-developers/zarr-python/issues/1113), [#1118](https://github.com/zarr-developers/zarr-python/issues/1118), [#1125](https://github.com/zarr-developers/zarr-python/issues/1125), [#1140](https://github.com/zarr-developers/zarr-python/issues/1140)

Recommended approach: post a batch comment like "Closing as part of a triage of pre-v3 issues. If this is still relevant in zarr-python v3, please reopen with reproduction steps." and close.

#### Label: Unlabeled V3 Issues
A large fraction of open v3-era issues have no labels. See the label taxonomy below and run a labeling pass.

### 2. High-Priority Issues (Fix Soon)

These are bugs or regressions actively affecting users:

| Issue | Title | Why High Priority |
|-------|-------|-------------------|
| [#3773](https://github.com/zarr-developers/zarr-python/issues/3773) | Memory/LocalStore list_prefix divergence | Bug, 12 comments, store correctness |
| [#3580](https://github.com/zarr-developers/zarr-python/issues/3580) | ZipStore resize creates duplicate entries | Data corruption risk |
| [#3558](https://github.com/zarr-developers/zarr-python/issues/3558) | Wrong array write with F-order string data | Data correctness bug |
| [#3524](https://github.com/zarr-developers/zarr-python/issues/3524) | V3 indexing noticeably slower than V2 | Performance regression, 9 comments |
| [#3516](https://github.com/zarr-developers/zarr-python/issues/3516) | Dask + ZipStore = corrupt zip | Data corruption |
| [#3469](https://github.com/zarr-developers/zarr-python/issues/3469) | Bytes array + ellipsis slicing error | Indexing bug |
| [#3416](https://github.com/zarr-developers/zarr-python/issues/3416) | BytesCodec endian doesn't roundtrip | Data correctness |
| [#3415](https://github.com/zarr-developers/zarr-python/issues/3415) | Iterating 1d array returns dimensionless arrays | Behavior regression |
| [#3387](https://github.com/zarr-developers/zarr-python/issues/3387) | _dereference_path assertion error | Crash |
| [#3313](https://github.com/zarr-developers/zarr-python/issues/3313) | consolidate_metadata doesn't scale | Performance, 6 comments |
| [#3174](https://github.com/zarr-developers/zarr-python/issues/3174) | Segfault reading StringDType | Crash |
| [#3072](https://github.com/zarr-developers/zarr-python/issues/3072) | Column-major arrays returned as row-major | Data correctness |
| [#2710](https://github.com/zarr-developers/zarr-python/issues/2710) | V3 performance regression | 20 comments, major concern |
| [#2529](https://github.com/zarr-developers/zarr-python/issues/2529) | V3 iteration significantly slower | 14 comments |
| [#2904](https://github.com/zarr-developers/zarr-python/issues/2904) | Codec pipeline performance | 14 comments |

### 3. Category-by-Category Triage

---

#### Stores (51 issues)

**Theme**: Store API is the largest issue cluster. Many issues stem from FsspecStore async issues, ZipStore limitations, and unclear store contracts.

**Close candidates**:
- [#1720](https://github.com/zarr-developers/zarr-python/issues/1720) (omit chunks HTTP 400 - likely v2)
- [#1821](https://github.com/zarr-developers/zarr-python/issues/1821) (nullability in Store.get - 0 comments, 4+ years old)
- [#1962](https://github.com/zarr-developers/zarr-python/issues/1962) (skew in store class attributes - 0 comments)
- [#2472](https://github.com/zarr-developers/zarr-python/issues/2472) (widen Store.set value type - superseded by [#3675](https://github.com/zarr-developers/zarr-python/issues/3675))

**Consolidate** (merge related issues):
- ZipStore issues: [#3580](https://github.com/zarr-developers/zarr-python/issues/3580), [#3516](https://github.com/zarr-developers/zarr-python/issues/3516), [#3194](https://github.com/zarr-developers/zarr-python/issues/3194), [#2448](https://github.com/zarr-developers/zarr-python/issues/2448), [#2450](https://github.com/zarr-developers/zarr-python/issues/2450), [#828](https://github.com/zarr-developers/zarr-python/issues/828) -> create a "ZipStore improvements" tracking issue
- FsspecStore issues: [#3196](https://github.com/zarr-developers/zarr-python/issues/3196), [#3185](https://github.com/zarr-developers/zarr-python/issues/3185), [#3487](https://github.com/zarr-developers/zarr-python/issues/3487), [#3471](https://github.com/zarr-developers/zarr-python/issues/3471), [#2988](https://github.com/zarr-developers/zarr-python/issues/2988), [#2808](https://github.com/zarr-developers/zarr-python/issues/2808), [#2793](https://github.com/zarr-developers/zarr-python/issues/2793), [#2946](https://github.com/zarr-developers/zarr-python/issues/2946) -> "FsspecStore improvements" tracking issue
- Store API design: [#3758](https://github.com/zarr-developers/zarr-python/issues/3758), [#3731](https://github.com/zarr-developers/zarr-python/issues/3731), [#3675](https://github.com/zarr-developers/zarr-python/issues/3675), [#3637](https://github.com/zarr-developers/zarr-python/issues/3637), [#3643](https://github.com/zarr-developers/zarr-python/issues/3643), [#3429](https://github.com/zarr-developers/zarr-python/issues/3429), [#2473](https://github.com/zarr-developers/zarr-python/issues/2473) -> consolidate into store API redesign discussion

**Keep & prioritize**:
- [#3773](https://github.com/zarr-developers/zarr-python/issues/3773) (list_prefix divergence - bug)
- [#3520](https://github.com/zarr-developers/zarr-python/issues/3520) (obstore as default - strategic direction)
- [#3358](https://github.com/zarr-developers/zarr-python/issues/3358) (LatencyStore public API - 13 comments, clear demand)

---

#### Codecs (32 issues)

**Theme**: Codec registration, numcodecs interop, and codec API design. Many issues opened by maintainers as design notes.

**Consolidate**:
- Numcodecs future: [#3783](https://github.com/zarr-developers/zarr-python/issues/3783), [#3493](https://github.com/zarr-developers/zarr-python/issues/3493), [#3461](https://github.com/zarr-developers/zarr-python/issues/3461), [#3370](https://github.com/zarr-developers/zarr-python/issues/3370), [#3272](https://github.com/zarr-developers/zarr-python/issues/3272) -> single tracking issue "numcodecs decoupling plan"
- Codec API simplification: [#3703](https://github.com/zarr-developers/zarr-python/issues/3703), [#3339](https://github.com/zarr-developers/zarr-python/issues/3339), [#3316](https://github.com/zarr-developers/zarr-python/issues/3316), [#3162](https://github.com/zarr-developers/zarr-python/issues/3162), [#3051](https://github.com/zarr-developers/zarr-python/issues/3051), [#2928](https://github.com/zarr-developers/zarr-python/issues/2928) -> "codec pipeline redesign" tracking issue
- Codec registration: [#3360](https://github.com/zarr-developers/zarr-python/issues/3360), [#3341](https://github.com/zarr-developers/zarr-python/issues/3341), [#3261](https://github.com/zarr-developers/zarr-python/issues/3261) -> "codec registry improvements"

**Close candidates**:
- [#2952](https://github.com/zarr-developers/zarr-python/issues/2952) (numcodecs to_dict - likely fixed or superseded)

**Keep & prioritize**:
- [#3256](https://github.com/zarr-developers/zarr-python/issues/3256) (Delta filter AttributeError - user-facing bug)
- [#3416](https://github.com/zarr-developers/zarr-python/issues/3416) (BytesCodec endian roundtrip - data correctness)
- [#3548](https://github.com/zarr-developers/zarr-python/issues/3548) (PCodec unknown codec - user-facing error)
- [#2964](https://github.com/zarr-developers/zarr-python/issues/2964) (TypeError with old numcodecs - migration pain)

---

#### Data Types (19 issues)

**Theme**: dtype support gaps, especially structured dtypes, platform-specific dtypes, and new numpy StringDType.

**Keep & prioritize**:
- [#3174](https://github.com/zarr-developers/zarr-python/issues/3174) (StringDType segfault - crash)
- [#3583](https://github.com/zarr-developers/zarr-python/issues/3583) (structured dtype with subarray)
- [#2134](https://github.com/zarr-developers/zarr-python/issues/2134) (structured dtype support - 25 comments, long-standing)
- [#2656](https://github.com/zarr-developers/zarr-python/issues/2656) (bfloat16 - 9 comments, ML ecosystem demand)

**Close candidates**:
- [#1389](https://github.com/zarr-developers/zarr-python/issues/1389) (ragged strings with VLenArray - v2 API)

---

#### Performance (20 issues)

**Theme**: V3 is measurably slower than V2 for many operations. Core issues are codec pipeline overhead, indexing overhead, and store operations.

**Consolidate**:
- V3 vs V2 speed: [#2710](https://github.com/zarr-developers/zarr-python/issues/2710), [#3524](https://github.com/zarr-developers/zarr-python/issues/3524), [#2529](https://github.com/zarr-developers/zarr-python/issues/2529) -> single "V3 performance parity" tracking issue
- Memory issues: [#3650](https://github.com/zarr-developers/zarr-python/issues/3650), [#3164](https://github.com/zarr-developers/zarr-python/issues/3164), [#3641](https://github.com/zarr-developers/zarr-python/issues/3641) -> "memory management improvements"

**Keep & prioritize**:
- [#2904](https://github.com/zarr-developers/zarr-python/issues/2904) (codec pipeline performance - 14 comments, root cause of many perf issues)
- [#3014](https://github.com/zarr-developers/zarr-python/issues/3014) (sharded writes slow)
- [#3085](https://github.com/zarr-developers/zarr-python/issues/3085) (timeouts with large datasets)

---

#### V2/V3 Migration (28 issues)

**Theme**: Migration tooling, API compatibility, and v2 data reading in v3.

**Close candidates**:
- [#1718](https://github.com/zarr-developers/zarr-python/issues/1718) (storage transformer API - 0 comments, 4+ years)
- [#1752](https://github.com/zarr-developers/zarr-python/issues/1752) (internal ChunkGrid API - 0 comments, 4+ years)
- [#1933](https://github.com/zarr-developers/zarr-python/issues/1933) (metadata tests - 0 comments)
- [#2322](https://github.com/zarr-developers/zarr-python/issues/2322) (fill_value bytes encoding - 0 comments)

**Keep & prioritize**:
- [#1798](https://github.com/zarr-developers/zarr-python/issues/1798) (v2 -> v3 data migration - 15 comments, core user need)
- [#3076](https://github.com/zarr-developers/zarr-python/issues/3076) (accelerating migration - 8 comments)

---

#### Documentation (26 issues)

**Label with `good-first-issue`** where appropriate:
- [#2995](https://github.com/zarr-developers/zarr-python/issues/2995) (fsspec auth docs)
- [#2599](https://github.com/zarr-developers/zarr-python/issues/2599) (document kwargs in zarr.create)
- [#2611](https://github.com/zarr-developers/zarr-python/issues/2611) (write_empty_chunks docs)

**Close candidates**:
- [#2294](https://github.com/zarr-developers/zarr-python/issues/2294) (function signature styling - cosmetic, 0 comments)
- [#2666](https://github.com/zarr-developers/zarr-python/issues/2666) (function signature styling - duplicate of [#2294](https://github.com/zarr-developers/zarr-python/issues/2294))

---

#### Sharding (11 issues)

**Keep all** - sharding is a core v3 feature and these are mostly legitimate issues:
- [#3751](https://github.com/zarr-developers/zarr-python/issues/3751) (0-d array with sharding - bug)
- [#3546](https://github.com/zarr-developers/zarr-python/issues/3546) (recarray + auto shards crash - bug)
- [#2834](https://github.com/zarr-developers/zarr-python/issues/2834) (setitem with oindex - bug)
- [#3604](https://github.com/zarr-developers/zarr-python/issues/3604) (iterative shard writing - feature request, 8 comments)

---

#### GPU (4 issues)

**Keep all** - small set, active development area:
- [#2658](https://github.com/zarr-developers/zarr-python/issues/2658) (device support - strategic, 9 comments)
- [#3640](https://github.com/zarr-developers/zarr-python/issues/3640) (fancy indexing GPU - bug)
- [#3271](https://github.com/zarr-developers/zarr-python/issues/3271) (CUDA streams)
- [#3340](https://github.com/zarr-developers/zarr-python/issues/3340) (rename "gpu" - naming cleanup)

---

#### Deprecations/Cleanup

Progress so far is ad-hoc: the original sweep [#3325](https://github.com/zarr-developers/zarr-python/pull/3325) has been largely cherry-picked into main via #3900–#3903 (convenience/creation modules, `zarr_version`, `.create` methods, group methods). See the "Path to 3.2.0" section above for #3325's residual scope.

**Close**:
- [#3499](https://github.com/zarr-developers/zarr-python/issues/3499) (`create_dataset` not removed) — resolved by #3902.

**Advance when there's bandwidth** (add deprecation warning, remove next release):
- [#3457](https://github.com/zarr-developers/zarr-python/issues/3457) (enums)
- [#3454](https://github.com/zarr-developers/zarr-python/issues/3454) (`to_dict`)
- [#3402](https://github.com/zarr-developers/zarr-python/issues/3402) (templated exceptions)

**Tie to bigger work**:
- [#2924](https://github.com/zarr-developers/zarr-python/issues/2924) (define deprecation policy) — scope this against [#3884](https://github.com/zarr-developers/zarr-python/issues/3884) metadata-dumbening, not the small items above.
- [#3317](https://github.com/zarr-developers/zarr-python/issues/3317) (remove deprecated routines) — tracked by [#3325](https://github.com/zarr-developers/zarr-python/pull/3325); will close when that merges.

---

#### API/Types (9 issues)

**Keep & prioritize**:
- [#3795](https://github.com/zarr-developers/zarr-python/issues/3795), [#3786](https://github.com/zarr-developers/zarr-python/issues/3786) (public metadata types/protocols - recent, architectural)
- [#3780](https://github.com/zarr-developers/zarr-python/issues/3780) (NDArrayLike with newer numpy typing)
- [#3352](https://github.com/zarr-developers/zarr-python/issues/3352) (open_like broken - bug)

---

#### Spec Compliance (3 issues)

**Keep all** - important for interop:
- [#3517](https://github.com/zarr-developers/zarr-python/issues/3517) (v3 bytes dtype compatibility)
- [#3523](https://github.com/zarr-developers/zarr-python/issues/3523) (unknown fields rejected)
- [#3513](https://github.com/zarr-developers/zarr-python/issues/3513) (deprecated bytes codec)

---

### 4. Suggested Label Taxonomy

Current labels are sparse. Suggested additions:

| Label | Purpose |
|-------|---------|
| `store` | Store-related issues |
| `codec` | Codec-related issues |
| `dtype` | Data type issues |
| `sharding` | Sharding codec issues |
| `migration` | V2->V3 migration |
| `API` | Public API design |
| `stale` | No activity 1+ year, may close |
| `needs-triage` | New issues awaiting categorization |
| `tracking` | Meta-issue tracking multiple related issues |
| `wontfix` | Intentional behavior / out of scope |

---

### 5. Proposed Tracking Issues

Create these meta-issues to consolidate scattered discussions:

1. **V3 Performance Parity** - tracks [#2710](https://github.com/zarr-developers/zarr-python/issues/2710), [#3524](https://github.com/zarr-developers/zarr-python/issues/3524), [#2529](https://github.com/zarr-developers/zarr-python/issues/2529), [#2904](https://github.com/zarr-developers/zarr-python/issues/2904), [#3014](https://github.com/zarr-developers/zarr-python/issues/3014)
2. **ZipStore Improvements** - tracks [#3580](https://github.com/zarr-developers/zarr-python/issues/3580), [#3516](https://github.com/zarr-developers/zarr-python/issues/3516), [#3194](https://github.com/zarr-developers/zarr-python/issues/3194), [#2448](https://github.com/zarr-developers/zarr-python/issues/2448), [#2450](https://github.com/zarr-developers/zarr-python/issues/2450)
3. **FsspecStore Improvements** - tracks [#3196](https://github.com/zarr-developers/zarr-python/issues/3196), [#3185](https://github.com/zarr-developers/zarr-python/issues/3185), [#3487](https://github.com/zarr-developers/zarr-python/issues/3487), [#2988](https://github.com/zarr-developers/zarr-python/issues/2988), [#2808](https://github.com/zarr-developers/zarr-python/issues/2808)
4. **Numcodecs Decoupling** - tracks [#3783](https://github.com/zarr-developers/zarr-python/issues/3783), [#3493](https://github.com/zarr-developers/zarr-python/issues/3493), [#3461](https://github.com/zarr-developers/zarr-python/issues/3461), [#3370](https://github.com/zarr-developers/zarr-python/issues/3370), [#3272](https://github.com/zarr-developers/zarr-python/issues/3272)
5. **Codec Pipeline Redesign** - tracks [#3703](https://github.com/zarr-developers/zarr-python/issues/3703), [#3162](https://github.com/zarr-developers/zarr-python/issues/3162), [#3051](https://github.com/zarr-developers/zarr-python/issues/3051), [#2928](https://github.com/zarr-developers/zarr-python/issues/2928)
6. **Store API Redesign** - tracks [#3758](https://github.com/zarr-developers/zarr-python/issues/3758), [#3731](https://github.com/zarr-developers/zarr-python/issues/3731), [#3675](https://github.com/zarr-developers/zarr-python/issues/3675), [#3637](https://github.com/zarr-developers/zarr-python/issues/3637), [#3643](https://github.com/zarr-developers/zarr-python/issues/3643)
7. **Structured/Complex Dtype Support** - tracks [#2134](https://github.com/zarr-developers/zarr-python/issues/2134), [#3583](https://github.com/zarr-developers/zarr-python/issues/3583), [#3582](https://github.com/zarr-developers/zarr-python/issues/3582), [#3247](https://github.com/zarr-developers/zarr-python/issues/3247)
8. **V2->V3 Migration Tooling** - tracks [#1798](https://github.com/zarr-developers/zarr-python/issues/1798), [#3076](https://github.com/zarr-developers/zarr-python/issues/3076), [#3466](https://github.com/zarr-developers/zarr-python/issues/3466), [#3467](https://github.com/zarr-developers/zarr-python/issues/3467), [#3468](https://github.com/zarr-developers/zarr-python/issues/3468)

---

### 6. Disposition Summary

Most open issues fall into one of:
- **Close**: pre-v3 / superseded (largest bucket), auto-generated metrics reports
- **Consolidate**: merge into the tracking issues above (store API, codec pipeline, etc.)
- **Label only**: unlabeled but still relevant — apply the taxonomy and leave open
- **Prioritize**: bugs actively affecting users (see section 2)
- **Keep as-is**: well-scoped but not immediately actionable

### 7. Process Recommendations

1. **Triage new issues within 1 week** — apply labels, assign priority
2. **Close stale issues quarterly** — bot or manual pass for issues with no activity in 12+ months
3. **Disable monthly metrics auto-issues** — they accumulate with 0 engagement
4. **Use milestones** — tie issues to upcoming releases
5. **Pin 3–5 tracking issues** — give contributors clear entry points
