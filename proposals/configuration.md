# Configuration, registries, and plugins

> Theme proposal. For the high-level pitch, see the [parent README](../README.md). This proposal owns the configuration-substrate replacement that earlier drafts tracked as a sub-section of [missing-apis.md](./missing-apis.md); the performance-lever defaults the substrate has to host (concurrency pools, the cache policy, engine/preset selection) live in [performance.md](./performance.md).

*A design review of zarr-python's configuration, registry, and plugin machinery — with a comparison to TensorStore, zarrs, and zarrita, and a concrete sequence of PRs to make our model simpler, more declarative, and more useful to users.*

**Scope:** `zarr.config`, the codec/pipeline/buffer/dtype registries, the entry-point plugin system, and array-scoped runtime configuration.

## 1. TL;DR

zarr-python's runtime configuration grew organically into three loosely-coupled mechanisms — a Donfig-backed global config dict, a set of global mutable registries, and an entry-point plugin system — that users must operate *in combination* to do anything non-default. The result is powerful and uniquely extensible (entry-point plugins are best-in-class among our peers), but it is **untyped, global-mutable, and indirect**: selecting a custom codec means registering a class *and* mutating a global string dict, while deep internals read that mutable global at runtime.

The fix is not to throw any of this away. It is to **move configuration from "global mutable state read implicitly" to "typed data passed explicitly"**, following the direction our peers have already validated:

- **TensorStore** proves the value of *configuration-as-data*: an immutable, serializable `Spec` (what the array is) plus an explicit `Context` (which resources to use), resolved by an explicit `bind` step. No global mutable state.
- **zarrs** proves the value of a *typed* config object plus a *layered override scope* (global → per-array → per-call), and shows the cost of all-or-nothing global pipeline swapping (its Python binding silently falls back to pure Python on unsupported access patterns).
- **zarrita** proves how far *pure explicitness* can go: no global config at all, a single opt-in codec registry, everything passed at call time.

Good news: **this work is already underway.** [#4101](https://github.com/zarr-developers/zarr-python/pull/4101) replaces Donfig with a typed config; [#3892](https://github.com/zarr-developers/zarr-python/pull/3892) moves codec classes and the pipeline into array-scoped config with `with_config`; [#4063](https://github.com/zarr-developers/zarr-python/pull/4063) builds a unified runtime validator. This proposal places those PRs into a single roadmap and adds the missing pieces: a unified runtime context, **a stable addressing scheme that stops using Python qualnames as external references**, a **collect-then-resolve registry that manages plugin name conflicts**, named profiles to replace `enable_gpu`, a metadata/execution split, and removal of the two-step codec dance.

One concern deserves to be called out up front, because it is the load-bearing constraint on everything else: **the more we open registration to external plugins, the more we need to manage conflicts between them.** Two installed packages will eventually claim the same codec or data-type name. We cannot resolve that by picking one arbitrarily (which is what we do today). The answer is to make *discovery* and *selection* two distinct stages — collect every provider first, then build a config that resolves conflicts deliberately. This depends on a prior question that is just as load-bearing: **how do we name the things being configured?** Today we refer to implementations by their Python module path (`"zarr.codecs.gzip.GzipCodec"`), which welds our config and on-disk references to our internal file tree. These two ideas — *addressability* (§5) and *conflict resolution* (§6) — run together through principles 8–9 and the roadmap.

## 2. Where zarr-python is today

We have **three** configuration mechanisms. Most real customization requires using two or three of them together.

### 2.1 The global config dict (Donfig)

`zarr.config` is a [Donfig](https://github.com/pytroll/donfig) `Config` — an **untyped nested dict** populated from defaults, `ZARR_*` environment variables, and YAML files. It holds a grab-bag of concerns: array defaults (`array.order`, `array.write_empty_chunks`), concurrency (`async.concurrency`, `threading.max_workers`), the codec pipeline path, the buffer/ndbuffer class paths, and a `codecs` map from codec name → fully-qualified class string. The concurrency and cache knobs in that grab-bag are exactly the defaults the [performance.md](./performance.md) levers need a typed home for, which is why this substrate has to land before them (see [Sequencing](#8-sequencing-within-the-v4-streams)).

```python
zarr.config.set({'array.order': 'F'})
zarr.config.get('array.order')   # -> 'F', typed `Any`
```

Drawbacks (all called out in [#3538](https://github.com/zarr-developers/zarr-python/issues/3538)):

- **Untyped.** Every value is `Any`. No IDE autocomplete, no static checking.
- **No validation.** A typo in a key (`array.oder`) is silently accepted and silently ignored.
- **Global and mutable.** Internals read the live global at call time, so behavior depends on process-wide state set anywhere, anytime — including from inside library code.

### 2.2 The registries

Six module-level mutable singletons in `zarr/registry.py` and `zarr/core/dtype/registry.py`:

```
_codec_registries: dict[str, Registry[Codec]]   # one Registry per codec name
_pipeline_registry, _buffer_registry, _ndbuffer_registry,
_chunk_key_encoding_registry, data_type_registry
```

A `Registry` is a `dict[str, type]` keyed by fully-qualified class name, plus a lazy entry-point load list. Lookups (`get_codec_class`, `get_pipeline_class`, …) consult **both** the registry **and** the config: e.g. `get_codec_class("gzip")` returns the class whose qualified name matches `config["codecs"]["gzip"]`. If multiple implementations are registered and none is selected in config, it **warns and picks one arbitrarily** — a silent-ambiguity footgun.

### 2.3 The entry-point plugin system

Third parties register implementations declaratively via packaging metadata — this is genuinely good and is our **strongest** feature relative to peers (TensorStore and zarrs both require recompilation to add a driver/codec):

```toml
[project.entry-points."zarr.codecs"]
"custompackage.fancy_codec" = "custompackage:FancyCodec"
```

Groups exist for `zarr.codecs`, `zarr.codecs.<name>`, `zarr.buffer`, `zarr.ndbuffer`, `zarr.data_type`, `zarr.chunk_key_encoding`, and `zarr.codec_pipeline`. Discovery is lazy.

### 2.4 The three pain points (in the maintainers' own words)

1. **Untyped, unvalidated config** — [#3538](https://github.com/zarr-developers/zarr-python/issues/3538), [#3400](https://github.com/zarr-developers/zarr-python/issues/3400).
2. **Selecting a non-default implementation is indirect and global.** To read an array with a custom codec you must (a) register the class, *and* (b) mutate `zarr.config`'s `codecs` dict with its qualified name. Internals then read that mutable global deep in the call stack — [#3341](https://github.com/zarr-developers/zarr-python/issues/3341) (pipelines), [#3360](https://github.com/zarr-developers/zarr-python/issues/3360) (codecs):

   ```python
   from your.module import NewBytesCodec
   from zarr.core.config import register_codec, config
   register_codec("bytes", NewBytesCodec)            # step 1: registry
   config.set({"codecs.bytes": "your.module.NewBytesCodec"})  # step 2: global config
   open_array(...)                                   # reads the global, indirectly
   ```

   There is **no way to say "open this array with these codec classes"** as a local, explicit argument. Comparing two codec implementations on the same data means open → mutate global → open again.

3. **Codec config stores qualified-name strings, not metadata.** The `codecs` map conflates "which Python class implements gzip" with "how is gzip configured," and can't express data-dependent defaults like the `bytes` codec's `endian` — [#2928](https://github.com/zarr-developers/zarr-python/issues/2928), [#3884](https://github.com/zarr-developers/zarr-python/issues/3884).

A telling case study is the **zarrs Python binding** ([#4064](https://github.com/zarr-developers/zarr-python/pull/4064), [zarrs-python](https://github.com/zarrs/zarrs-python)): the only way to use the Rust pipeline is to globally swap `codec_pipeline.path`. It's all-or-nothing per process, and unsupported access patterns / stores / codecs **silently fall back** to the Python pipeline — so a user can believe they have Rust acceleration that a given call quietly isn't using. That's the global-swap model's coarseness made visible. The [performance.md engine-wrapping work](./performance.md#wrapping-zarrs-and-tensorstore-as-alternative-engines) needs per-array engine selection precisely to avoid this trap.

### 2.5 What we already have right

- **Entry-point discovery** — keep and lean into it.
- **`BufferPrototype` is already passed as an argument**, not read from a global — the model we want everywhere already exists for buffers.
- **`ArrayConfig`** (`zarr/core/array_spec.py`) is a frozen dataclass already attached per-array. It is the natural home for array-scoped runtime config, and [#3892](https://github.com/zarr-developers/zarr-python/pull/3892) is already extending it.

## 3. What our peers do

### 3.1 TensorStore — configuration as data, resolved by binding

TensorStore has **essentially no global mutable configuration.** Everything is expressed as data on two axes and resolved by an explicit step:

- **Spec** — an immutable, serializable JSON object describing *what* to open: the `driver`, the nested `kvstore`, the `metadata`/`schema` (including the per-array `codecs` chain), transforms. A Spec is a recipe you can serialize, diff, hash, and ship across machines.
- **Context** — a separate object holding *which shared resources* to use: `cache_pool`, `data_copy_concurrency`, `file_io_concurrency`, credentials. Resources are shared by **naming** (`cache_pool#remote`), opt-in and visible in the data — never via a process singleton.
- **Bind** — `ts.open(spec, context=ctx)` resolves context references into live resources and returns a bound store. Conceptually `TensorStore = bind(Spec, Context)`. `store.spec()` recovers the fully-explicit Spec to reproduce the view elsewhere.

```python
dataset = ts.open({
    'driver': 'zarr3',
    'kvstore': {'driver': 'gcs', 'bucket': 'my-bucket', 'path': 'array/'},
    'metadata': {'codecs': [{'name': 'blosc',
                             'configuration': {'cname': 'zstd', 'clevel': 5}}]},
    'context': {'cache_pool': {'total_bytes_limit': 100_000_000}},
}).result()
```

**Lessons:** configuration-as-data gives reproducibility, testability, and multi-tenant isolation; codecs are per-array data, not global; `schema` (partial *constraints*) vs `metadata` (resolved values) is a clean split. **Costs:** verbose JSON; a two-axis (Spec/Context) + two-phase (unbound/bound) mental model; and — critically — **no runtime plugins**: drivers/codecs are registered at link time, so you cannot `pip install` a new codec. *That last point is exactly where zarr-python is stronger.*

### 3.2 zarrs — typed config + layered override scope

zarrs (Rust) has a **typed** global `Config` struct (`validate_checksums`, `store_empty_chunks`, `codec_concurrent_target`, metadata-version conversion knobs, …) with named getters/setters — misconfiguration is a compile error, not a `KeyError`. Crucially, config has a **layered override scope**:

> **global `Config` → projected to per-operation `CodecOptions` → per-call `_opt` override wins.**

Most array methods come in pairs — `retrieve_chunk(idx)` and `retrieve_chunk_opt(idx, &CodecOptions)` — so you can override one operation's behavior *locally* without touching global state. Plugin registration is compile-time (`inventory::submit!`, self-registering on link) plus a newer runtime registry; codec-name aliasing (`impl_extension_aliases!`) lets it read many spellings and write one canonical name. Experimental codecs are gated by **Cargo features** (compile-time), not runtime toggles.

**Lessons:** a typed config and an explicit *global → array → per-call* override hierarchy are the right ergonomics. **Costs:** compile-time feature gating is rigid (no `pip install` equivalent); the global config still hands out live lock guards (deadlock footguns); and the API has churned (the 0.22→0.23 change to whether `CodecOptions::default()` reads global config is a silent behavior change). The **all-or-nothing global pipeline swap** in the Python binding (§2.4) is the cautionary tale for us.

### 3.3 zarrita — radical explicitness

zarrita.js has **no global config object at all.** The only shared mutable state is a single exported codec `registry` — a plain `Map<string, () => Promise<Codec>>` of lazy loaders — and it governs *only* name→implementation resolution, nothing else. Everything else (store, dtype, chunk shape, codecs, fill value) is passed explicitly at `open`/`create` time. Free functions over stateful methods enable tree-shaking; heavy WASM codecs are pulled in via lazy dynamic `import()`.

```ts
zarr.registry.set("my-codec", () => import("./my-codec.js").then(m => m.MyCodec));
const arr = await zarr.create(root.resolve("/t"), {
  shape: [100, 200], chunkShape: [20, 20], dtype: "float32",
  codecs: [{ name: "bytes", configuration: { endian: "little" } },
           { name: "gzip",  configuration: { level: 1 } }],
});
```

The original Python `zarrita` (Norman Rzepka; the prototype that seeded zarr-python 3) was the same: explicit codec factory lists, no global config, no registry. **The config + registry machinery is something zarr-python 3 added on top of an originally-explicit design** — which is precisely why it feels bolted-on, and why returning toward explicitness is natural.

**Lessons:** explicit beats global; an opt-in registry as the *only* shared state is a clean minimum; lazy loading keeps optional codecs cheap. **Costs:** no defaults means more boilerplate; runtime-Map registration has no declarative discovery (our entry points are better).

### 3.4 Comparison at a glance

| Dimension | zarr-python (today) | TensorStore | zarrs | zarrita |
|---|---|---|---|---|
| Global mutable config | **Yes** (Donfig dict) | No | Yes (typed struct) | **No** |
| Config typed / validated | No | N/A (schema'd JSON) | **Yes** | N/A (explicit args) |
| Per-array runtime config | Partial (`ArrayConfig`) | **Yes** (Spec) | Via metadata | **Yes** (call args) |
| Per-call override | No | Via re-open | **Yes** (`_opt`) | Via call args |
| Codec selection | Register **+** global dict | Per-array data | Registry + per-call | Registry Map |
| Plugin discovery | **Entry points** ✅ | Link-time only | Link-time + runtime | Runtime `Map.set` |
| Config serializable | Partially | **Yes** (Spec) | Partially | N/A |
| Resource sharing model | Global singletons | **Named Context resources** | Global config | None (explicit) |

## 4. Design principles to adopt

1. **Configuration is data, passed explicitly — not global state, read implicitly.** Internals should declare what they need in their signatures. The global config is only a source of *defaults at the API boundary* ([#3892](https://github.com/zarr-developers/zarr-python/pull/3892) rationale). *(TensorStore, zarrita)*
2. **Type the config; validate at the boundary.** A typed schema gives autocomplete and turns typos into errors. Validate programmatic input strictly; tolerate unknown keys from env/YAML so a stray var can't break `import zarr`. *(zarrs, [#4101](https://github.com/zarr-developers/zarr-python/pull/4101))*
3. **Layer the override scope: global default → per-array → per-call.** Local always wins, and a local override never mutates global state. *(zarrs)*
4. **Separate "what" from "how."** Array *metadata* (the spec) is distinct from the *implementations* used to service it (codec classes, pipeline, buffer). Make the implementation set an immutable, array-scoped value. *(TensorStore Spec vs Context; [#3854](https://github.com/zarr-developers/zarr-python/issues/3854), [#3884](https://github.com/zarr-developers/zarr-python/issues/3884))*
5. **Keep entry points; remove the second step.** Registration should be sufficient to *use* a plugin. Selection should be an explicit argument, not a second mutation of a global dict. *(our strength + [#3360](https://github.com/zarr-developers/zarr-python/issues/3360))*
6. **No silent ambiguity, no silent fallback.** Picking an arbitrary implementation, or quietly degrading to a slower path, should be an explicit choice or a loud error. *(zarrs-python lesson)*
7. **Make it introspectable.** Users should be able to ask "what codecs/dtypes/stores are available?" and "how was this array opened?" and get answers. *(TensorStore `spec()`)*
8. **Discovery is not selection: collect, then resolve.** Discovering the universe of installed providers (a permissive step that never fails) must be separate from choosing which one wins for a given name (a deliberate step with an explicit conflict policy). With open plugin registration, two packages *will* claim the same name; resolving that arbitrarily and lazily at lookup time — as we do now — is a latent correctness bug. *(TensorStore registry → bind; zarrs collection → "runtime wins over compiled" precedence)*
9. **Address by stable identity, not by location.** An implementation's external address must be a declared identity — its format/spec name, or a package-controlled provider id — never its Python module path. Qualnames couple the format and config to our internal file layout and are not a safe serialization contract. Refer to class *objects* internally; convert to/from stable identity strings only at the API and serialization boundaries. zarr-python need never *construct or store* its own qualnames as identity; it may still *resolve* a user-authored import-path string at the config boundary as a deliberate escape hatch (necessary so env vars / YAML can address any importable class — §5). *(TensorStore driver `id`; zarrs `impl_extension_aliases!`)*

## 5. Addressability: identity vs. location

Before we can collect, resolve (§6), or serialize anything, we have to answer a prior question: **how do we name the things being configured?** Today we use at least three naming schemes, partly conflated — and one of them is the brittleness you feel when you write a config string.

**The three namespaces in play today**

1. **Spec names** — the `name` field inside array metadata: `"gzip"`, `"blosc"`, `"sharding_indexed"`, `"numcodecs.zstd"`, and data-type names like `"uint8"`. These are defined by the *Zarr format and its extension conventions*, not by us. They are an **interoperability contract** every implementation must agree on — the address that travels *in the data*.
2. **Python qualified names** — `"zarr.codecs.gzip.GzipCodec"`, `"zarr.core.codec_pipeline.BatchedCodecPipeline"`. We use these as registry keys *and* as the way config selects an implementation (`codecs.gzip = "zarr.codecs.gzip.GzipCodec"`, `codec_pipeline.path = "…"`).
3. **Entry-point names** — the left-hand side of `"mypkg.fancy" = "mypkg:FancyCodec"`. Declared by the plugin author and decoupled from module layout — but today, for codecs, this name is largely *discarded*: lazy loading registers the class under its qualname, not the entry-point name it was given.

The brittleness lives entirely in #2: **we use a Python *location* as an external *address*.**

**Why location-as-address is brittle**

- **Coupled to module layout.** Move `GzipCodec` to a new module, or rename it, and every config string, env var, and serialized reference pointing at `zarr.codecs.gzip.GzipCodec` silently stops matching. The on-disk format hasn't changed — only our internal file tree did — yet references break.
- **Dual, confusing semantics.** `codec_pipeline.path` *looks* like an import path but is actually a registry-key lookup with no `importlib` fallback (a point the zarrs binding made concrete). Users reasonably assume they can point it at any importable class; today they can't — the string lies about what it does. (The fix is not to ban the string but to honor both meanings; see below.)
- **Unvalidated and unfriendly.** A qualname string is `Any`-typed, has no autocomplete, and fails only at lookup — with a `KeyError`/`BadConfigError` far from where the typo was made.
- **Not a stable serialization contract.** The moment we serialize *how an array was opened* (provenance, or PR 10's open-spec), qualnames become a forward-compatibility hazard: they bake our private module tree into other people's files.

**What our peers do** — the common thread is that an implementation's address is a *declared identity*, never its source-code location:

- **TensorStore** gives every driver an explicit, stable string `id` (`constexpr static const char id[]`) that is the address in specs — deliberately *not* the C++ type name.
- **zarrs** declares stable aliases per codec via `impl_extension_aliases!` (a canonical `default_name` plus recognized aliases), decoupled from the Rust type path.
- **zarrita** passes class objects internally and uses only the *spec name* as a string key in its registry Map.

**The model to adopt** — separate the two axes explicitly, and choose the *carrier* by context:

- **Format identity (spec name).** What goes in metadata, what resolution keys on, the interop contract: `"gzip"`, `"uint8"`, `"numcodecs.zstd"`. We don't own these — the spec does.
- **Implementation identity (provider id).** A stable string naming a *specific* implementation, decoupled from its module path — sourced from the **entry-point name** the plugin author already declares (package-scoped, refactor-safe, and the namespace §6 manages for collisions): `"zarr:gzip"`, `"zarrs:gzip"`, `"mypkg:fast-gzip"`.

Addressability then has a clear rule per layer:

| Layer | Address by | Rationale |
|---|---|---|
| **Internal routines** | the class / instance **object** | refactor-safe, typed, no lookup — the [#3892](https://github.com/zarr-developers/zarr-python/pull/3892)/[#3884](https://github.com/zarr-developers/zarr-python/issues/3884) direction |
| **Python API boundary** | object *or* provider-id *or* spec-name | accept all three; resolve to an object once |
| **Serialized config / env / YAML / provenance** | **provider-id** string (stable); import path as escape hatch | survives refactors; travels between machines |
| **Array metadata (on disk)** | **spec name** (format-defined) | interoperability; never our qualnames |

The concrete deprecation target is the qualname-as-config-value pattern (`codecs.gzip = "zarr.codecs.gzip.GzipCodec"`, `codec_pipeline.path = "…"`). Replace it with: pass the **class object** (Python), or a **provider id** (serialized). Internally, stop keying registries by qualname — key by `(spec-name, provider-id)`, honoring the entry-point name the author already gave us rather than discarding it.

**Do we ever need a fully-qualified import path? Only as a string escape hatch — never as zarr's own identity.**

There's a crucial distinction between zarr *emitting* qualnames — baking its private module layout into registry keys, config defaults, and on-disk references, which we eliminate — and zarr *accepting* a user-authored import path at its string-config boundary, which we must keep. In Python, implementations reach the registry as live objects:

- **Built-ins** register their own imported class objects directly, under `(spec-name, "zarr")`. No string indirection at all.
- **Third-party plugins** are resolved to objects by the entry-point machinery at collection time. The one module-path string in this path — the right-hand side of `"mypkg.fast" = "mypkg.codecs:FastGzip"` — lives in the *provider's own* `pyproject.toml`, alongside the code it points at, and is resolved to an object once. zarr never stores or compares it.
- **In-process user classes** are passed as objects (`codec_class_map={"gzip": MyGzip}`) — no name needed.

The canonical identity zarr *keeps* is packaging-level (the entry-point name, disambiguated by distribution as `dist:name` when two packages collide — §6), never a module path: a package can refactor its module tree freely and stored references keep resolving.

**But strings are first-class, because env vars and YAML are string-only channels.** You cannot put a Python object in `ZARR_CODECS__GZIP`. So selecting an implementation *must* also work from a string — otherwise there is no way to configure the registry from `ZARR_*` variables or a YAML file, exactly the container / 12-factor / CI surface we can't drop. The string-config boundary therefore accepts **two** address forms, tried in order:

1. **Provider-id** — `ZARR_CODECS__GZIP="zarrs:gzip"`. Looked up in the collected registry (§6). Preferred, and the natural way to choose among a *set of installed providers*: stable and refactor-safe.
2. **Import path** — `ZARR_CODECS__GZIP="mypkg.codecs:FastGzip"`. Resolved via `importlib`, validated against the expected ABC, and registered on the fly. The escape hatch for an importable class that hasn't declared an entry point.

This also fixes the `codec_pipeline.path` footgun the *right* way: today the string looks importable but is a registry-key lookup with no `importlib` fallback. The fix is to make the dual semantics real — try the registry, then fall back to import — so the string does what it appears to do.

The point is *who owns the brittleness*. zarr never writes its own qualnames anywhere, so zarr's refactors never break a user's stored config. A user may still deliberately write an import path to point at *their own* class — taking on exactly the responsibility a plugin author takes writing the right-hand side of an entry point. It's their path to their code; they own its stability. A trade they opt into, not a default we impose. This sharpens the boundary into three tiers:

| Tier | Addressed by | Serializable from a string? |
|---|---|---|
| **Registered** (entry point or runtime registration) | provider-id — `zarrs:gzip` | ✅ stable, refactor-safe |
| **Importable but unregistered** | import path — `mypkg.codecs:FastGzip` | ✅ but brittle — the user owns the path |
| **Anonymous / local** (defined in `__main__`, a notebook) | the object only | ❌ nothing stable to write |

For the middle tier, a user who wants stability can instead mint a provider-id via lightweight runtime registration (`zarr.register_codec("me:fast-gzip", MyGzip)`, mirroring zarrs' runtime registry) — promoting their class to tier 1 without a packaged distribution. Internally none of this changes: zarr resolves any form to an **object** once, at the boundary, and never retains the string as a canonical key.

Qualnames-as-zarr's-own-identity survive for exactly one purpose: **human-readable diagnostics** (reprs; errors like *"two providers for 'gzip': zarr.codecs… and mypkg.codecs…"*). That is display, never a key we store or a reference we emit.

This is the naming scheme that §6's collection/resolution operates on, and the stable-identity contract that a serializable open-spec (PR 10) requires — it emits provider-ids, falling back to an import path only for the importable-but-unregistered tier.

## 6. Managing plugin conflicts: collect, then resolve

Open plugin registration is our best feature — but it has a consequence we don't currently handle: **two plugins can register the same name.** Two installed packages may both provide a `gzip` codec, both claim the `uint8` data type, or both register a `default` chunk-key encoding. Data types are especially exposed, because the Zarr v3 names they bind to (`uint8`, `float32`, …) are not namespaced the way codec ids can be (`numcodecs.*`) — the [data-types.md](./data-types.md) work that adds ML dtypes widens exactly this surface. As the ecosystem grows, name collisions are not an edge case — they are inevitable.

Today we resolve this badly. `get_codec_class` consults the registry lazily, per lookup, and when several implementations are registered with none selected in config it **warns and returns an arbitrary one** (`list(...)[-1]`). That is conflict resolution that is silent, lazy, order-dependent, and decided *without a view of all the candidates*. It is a latent correctness bug, and it gets worse with every plugin added.

The fix is to split the registry into two explicit stages — the same data-vs-resolution split TensorStore draws between its driver registry and `bind`, and that zarrs draws between its `inventory` collection and its "runtime registry wins over compiled" precedence:

**Stage 1 — Collection (discovery).** Walk every source — entry points and manual `register_*` calls — and record *all* providers into a multimap: `name -> [(provider, origin)]`, where `origin` is the distribution/module that supplied it. This stage is **permissive and never fails**: duplicates are data, not errors. The output is the universe of what's installed, with provenance.

**Stage 2 — Resolution (config build).** From the collected candidates, build the immutable, conflict-free mapping that the default RuntimeContext (PR 4) is constructed from. Resolution follows an explicit, deterministic policy — never an arbitrary pick:

1. **Explicit selection wins.** A name chosen in `config`, or passed per-array (PR 3–4), is authoritative.
2. **Configured precedence breaks ties.** A user-settable priority list (e.g. `config.plugins.priority = ["mypkg", "numcodecs", "zarr"]`) resolves contested names deterministically. A *single* third-party provider intentionally replacing a built-in is allowed and unambiguous — that is how a GPU codec overrides the CPU one; the genuinely contested case is two non-built-in providers for one name.
3. **Otherwise, error at the point of use.** If a contested name is actually requested with no way to disambiguate, raise — listing the candidates and how to choose between them. An *unused* conflict never breaks `import zarr` or opening an unrelated array; only resolving the contested name itself fails, and it fails loudly (principles 6, 8).

Two further benefits fall out of making the stages explicit:

- **Introspection.** Because collection has a global view, we can answer "what's contested?" — `zarr.registry.conflicts()` and a section in `config.describe()` (PR 9) — turning a silent footgun into a debuggable report.
- **Decoupling and cost.** Discovery is paid once into an inspectable structure, rather than smeared across lazy per-lookup resolution that re-decides ambiguity every time a name is requested.

This two-stage model is the backbone of the registry redesign: **PR 5 builds it, PR 4's default context consumes its output, and PR 7's one-step selection relies on its resolution policy.**

## 7. Recommended roadmap (a sequence of PRs)

Ordered so each builds on the last. **Phase A** is largely in flight; **B** is the core declarative shift; **C** is deeper cleanup; **D** is ergonomics. Each item notes its anchor issue/PR. The mapping from these phases onto the README's release streams is in [Sequencing](#8-sequencing-within-the-v4-streams) below.

### Phase A — Typed, validated foundations *(in flight)*

**PR 1 — Land the typed config object.** *(= [#4101](https://github.com/zarr-developers/zarr-python/pull/4101))*
Replace the Donfig dict with frozen, slotted dataclasses as the single source of truth, exposing both attribute (`zarr.config.array.order`) and string (`config.get("array.order")`) access with precise static types. Strict validation on programmatic `set`/`get`; tolerant ingest for env/YAML. Preserve the public surface during transition.
*Outcome:* principles 1–2. *Risk:* low–medium (compat surface is broad but covered by the PR's consumer audit).

**PR 2 — Unified runtime validator.** *(= [#4063](https://github.com/zarr-developers/zarr-python/pull/4063) / [#3285](https://github.com/zarr-developers/zarr-python/issues/3285))*
Consolidate the ~42 scattered `parse_*` helpers into one `parse_json(value, type)` checker. This is the shared validation primitive for both config values and metadata, and underpins clean error messages everywhere downstream.
*Outcome:* principle 2/6. *Risk:* low (mechanical, incremental migration).

### Phase B — Array-scoped, declarative runtime config *(the core shift)*

**PR 3 — Codec classes and pipeline in array config.** *(= [#3892](https://github.com/zarr-developers/zarr-python/pull/3892))*
Put `codec_class_map` and `codec_pipeline_class` in the array-scoped `ArrayConfig`, thread them through the internal routines that currently read the global config, and add `config=` to `open_array`/`create_array` plus `Array.with_config(...)`. This delivers the headline user-facing win:

```python
# open the SAME array with a different gzip implementation — no global mutation
arr2 = zarr.open_array(store, config={
    "codec_class_map": {**arr.config.codec_class_map, "gzip": MyFastGzip}})
# or swap on an existing array
arr3 = arr.with_config({"codec_pipeline_class": ZarrsCodecPipeline})
```

*Outcome:* principles 1, 3, 4 for codecs/pipelines; directly closes [#3341](https://github.com/zarr-developers/zarr-python/issues/3341), [#3854](https://github.com/zarr-developers/zarr-python/issues/3854). *Risk:* medium (touches metadata v2/v3, sharding, array creation). *Depends on:* PR 1.

**PR 4 — Generalize to a single immutable RuntimeContext.**
Extend PR 3's pattern to *all* implementation registries — data types, buffer, ndbuffer, chunk-key-encoding — collected into one immutable, array-scoped object passed as a single `config`/`context` argument (cf. TensorStore's Context; proposed in [#3538](https://github.com/zarr-developers/zarr-python/issues/3538), [#3360](https://github.com/zarr-developers/zarr-python/issues/3360)). Its default is derived from the global registries + config at the API boundary, so existing code is unaffected.

```python
arr = zarr.open_array(store, config={
    "data_type_classes": {"uint8": MyUint8},
    "codec_class_map":   {"gzip": MyGzip},
    "buffer": GpuBuffer,
})
```

*Outcome:* one explicit knob replaces N global lookups; enables mixing CPU/GPU implementations per array. *Risk:* medium. *Depends on:* PR 3.

### Phase C — Registry redesign and removing indirections

**PR 5 — Registry redesign: stable addressing + collect-then-resolve.** *(hardens [#3360](https://github.com/zarr-developers/zarr-python/issues/3360), [#3538](https://github.com/zarr-developers/zarr-python/issues/3538); fixes the warn-and-pick-arbitrarily footgun in `get_codec_class`)*
Two coupled changes (splittable into 5a/5b). **(a) Addressing (§5):** drop `fully_qualified_name` as a registry key entirely; key by `(spec-name, provider-id)`, where the provider-id is the package-controlled entry-point name (currently discarded). Built-ins register objects directly; third-party plugins resolve to objects via entry points; accept class objects, provider-ids, or spec names at the API. Resolve string config (env/YAML) as **provider-id first, import path second** (importlib fallback, validated + auto-registered) — demoting qualname-as-config-value from canonical key to escape hatch, and fixing the `codec_pipeline.path` "looks importable but isn't" footgun. Emit provider-ids when serializing. Add lightweight runtime registration to mint a provider-id for unpackaged classes. **(b) Collect → resolve (§6):** split each registry (codecs, data types, chunk-key encodings, buffers, pipelines) into a permissive **collection** pass — discover every provider into a provenance-keyed multimap, never failing on duplicates — and a deterministic **resolution** pass that builds the immutable, conflict-free mapping the default RuntimeContext is constructed from. Resolution policy: explicit selection → configured precedence list → loud error at point of use, never an arbitrary pick. Add `zarr.registry.conflicts()`.
*Outcome:* principles 6, 8, 9; makes open plugin registration safe and refactor-proof at ecosystem scale. *Risk:* medium. *Depends on:* PR 1; feeds PR 4's default context and PR 7.

**PR 6 — Separate codec metadata from codec execution.** *(= [#3884](https://github.com/zarr-developers/zarr-python/issues/3884))*
Stop materializing executable codec instances on the metadata classes (`ArrayV2Metadata`/`ArrayV3Metadata`). Introduce lightweight `CodecMetadata` (and eventually a generic fallback) so metadata is narrowly about *representation*, and executable codecs are created only when chunk-encoding machinery is built (owned by the `Array`/RuntimeContext, per PR 4). A generic fallback lets us **open an array whose codecs we can't decode** and still read attributes — a real usability win. This is the configuration-side of the metadata/execution split that [codecs.md](./codecs.md) and the [functional-core.md](./functional-core.md) data-model work also depend on.
*Outcome:* principle 4 fully; unblocks the same treatment for `ZDType`. *Risk:* high (core refactor). *Depends on:* PR 3–4.

**PR 7 — One-step codec selection; retire the register-and-configure dance.** *(= [#3360](https://github.com/zarr-developers/zarr-python/issues/3360), [#2928](https://github.com/zarr-developers/zarr-python/issues/2928), [#3341](https://github.com/zarr-developers/zarr-python/issues/3341))*
With selection now an explicit argument (PR 3–4), make **registration alone sufficient to use** an implementation, and replace the `codecs` string-map's dual role: store *configuration*, not class qualnames, and let array creation fill data-dependent params (e.g. `bytes` `endian`) dynamically. Inherit the "→ clear error, never arbitrary pick" resolution policy from PR 5 (principles 6, 8). Deprecate the global `codecs.<name>` selection in favor of the array-scoped map, keeping a shim for a release or two.
*Outcome:* principles 5–6; the §2.4 three-line dance becomes one explicit argument. *Risk:* medium. *Depends on:* PR 4, PR 5.

### Phase D — Ergonomics and accessibility

**PR 8 — Named profiles; replace `enable_gpu()`.** *(generalizes [#3360](https://github.com/zarr-developers/zarr-python/issues/3360)'s `"default"`/`"cupy"` idea)*
Define named, immutable runtime profiles — `"default"`, `"gpu"`, `"zarrs"` — that bundle a coherent set of implementations (cf. TensorStore named context resources). `config=` accepts a profile name or an explicit object. `zarr.config.enable_gpu()` (which mutates global buffer/ndbuffer) becomes `config="gpu"` passed per array, with the global mutator deprecated — the per-array, no-global-mutation surface the [gpu.md](./gpu.md) device-agnostic work wants. The `"interactive"` caching preset in [performance.md](./performance.md#default-caching-policy) is the same mechanism applied to cache defaults.

```python
arr = zarr.open_array(store, config="gpu")     # no global mutation
arr = zarr.open_array(store, config="zarrs")   # opt into the Rust pipeline, per array
```

*Outcome:* discoverable presets without global state; fixes the zarrs all-or-nothing problem. *Risk:* low–medium. *Depends on:* PR 4.

**PR 9 — Introspection and discovery.**
Add `zarr.config.describe()` (schema + current values + sources), registry-listing helpers (`zarr.list_codecs()`, `list_data_types()`, `list_stores()`), and `zarr.registry.conflicts()` (surfacing the contested names from PR 5), so users can answer "what's available, how is it set, and what collides?" Pairs naturally with a docs pass folding the three mechanisms into one mental model.
*Outcome:* principles 7, 8. *Risk:* low. *Depends on:* PR 5.

**PR 10 (stretch) — A serializable open-spec.**
Building on PR 4, let an array report how it was opened as serializable data (`arr.spec()` → JSON), and accept that data to reproduce the view elsewhere — the reproducibility property that makes TensorStore Specs valuable, now available in zarr-python. Requires PR 5's stable provider-ids: the spec must address implementations by identity, never qualname (§5). Natural fit with the ZEP 8 URL syntax work ([#3369](https://github.com/zarr-developers/zarr-python/pull/3369), tracked in [missing-apis.md § 5](./missing-apis.md)).
*Outcome:* configuration-as-data, end to end. *Risk:* medium; do last. *Depends on:* PR 4, PR 5.

### Dependency graph

```
PR1 (typed config) ─┬─> PR3 (codecs in array config) ─┐
PR2 (parse_json) ───┘                                  ├─> PR4 (RuntimeContext) ─┬─> PR6  (meta/exec split)
PR1 ────────────────> PR5 (collect→resolve registry) ──┘   (PR5 builds PR4's      ├─> PR7  (one-step selection)
                              │                             default mapping)       ├─> PR8  (named profiles)
                              └──────────────────────────────────────────────────>├─> PR9  (introspection: conflicts)
                                                                                   └─> PR10 (serializable spec)
```

## 8. Sequencing within the v4 streams

This work maps onto the [README roadmap](../README.md#roadmap) as part of **Stream 1** (additive value, shipping as EffVer 3.x minors). Nothing here needs a breaking release: every step ships its old surface as a shim first and removes later, with the `codecs.<name>` selection and `enable_gpu()` deprecations accumulating in **Stream 2** and the eventual removals landing only in the single late major (**Stream 3**).

**The substrate is a prerequisite, not a peer.** The typed config object (Phase A) is the first thing in the **M1 foundation** tier, ahead of the performance-lever defaults it has to host: the dask-safe concurrency default, the cache default policy, preset selection, and engine selection in [performance.md](./performance.md) all need a typed place to live. So Phase A lands early in M1, before those levers' defaults are wired. Phases B–C (array-scoped config, the registry redesign) are the rest of the M1 foundation work; Phase D's ergonomics (named profiles, introspection, the serializable open-spec) are **M2 user-facing surface**, built on the M1 substrate and dovetailing with the engine-wrapping and ZEP 8 URL work there.

The PR sequence above is a recommendation, not a commitment — the phases are independently valuable and can be reordered or split. The hard ordering constraints are the ones in the dependency graph: typed config (PR 1) before everything, and the registry redesign (PR 5) before one-step selection (PR 7) and the serializable spec (PR 10).

## 9. Guardrails

- **Backwards compatibility.** `zarr.config`'s public surface, env-var/YAML ingest, and `enable_gpu()` stay working through a deprecation window; PR 1 already verifies this against every in-repo consumer. Every step ships its old API as a shim first, removes later.
- **Keep entry points central.** None of this weakens plugin *discovery* — our best feature versus all three peers. We are improving *selection*, not discovery.
- **Don't recreate the silent-fallback trap.** When an array-scoped implementation can't service a request, raise — don't quietly drop to another path (the zarrs-python lesson). If we ever auto-fall-back, it must be opt-in and logged. The same rule governs plugin conflicts: never silently pick one of two providers for a contested name (§6).
- **Serialize identities, not locations.** Anything *zarr itself* writes to config, provenance, or an open-spec addresses implementations by stable identity (spec name / provider id), never by Python qualname (§5) — so our internal refactors never break users' stored references. (zarr still *accepts* a user-authored import path as a string escape hatch on input; it just never *emits* one.)
- **One mental model in the docs.** The end state should be teachable in one page: *global config sets defaults; pass `config=` to override per array; everything you pass is typed, validated, immutable data.*

## 10. Appendix — primary sources

**zarr-python**
- Issues: [#3538](https://github.com/zarr-developers/zarr-python/issues/3538) (config model), [#3360](https://github.com/zarr-developers/zarr-python/issues/3360) (codec registry kwarg), [#3341](https://github.com/zarr-developers/zarr-python/issues/3341) (pipeline selection), [#3854](https://github.com/zarr-developers/zarr-python/issues/3854) (codec classes in array config), [#3884](https://github.com/zarr-developers/zarr-python/issues/3884) (metadata vs execution), [#2928](https://github.com/zarr-developers/zarr-python/issues/2928) (codecs in config), [#3400](https://github.com/zarr-developers/zarr-python/issues/3400) (runtime type checks), [#3285](https://github.com/zarr-developers/zarr-python/issues/3285).
- PRs: [#4101](https://github.com/zarr-developers/zarr-python/pull/4101) (typed config), [#3892](https://github.com/zarr-developers/zarr-python/pull/3892) (codec classes in array config), [#4063](https://github.com/zarr-developers/zarr-python/pull/4063) (parse_json), [#4064](https://github.com/zarr-developers/zarr-python/pull/4064) (zarrs bindings).
- Source: `src/zarr/core/config.py`, `src/zarr/registry.py`, `src/zarr/core/array_spec.py`, `src/zarr/core/dtype/registry.py`.

**TensorStore** — [Spec](https://google.github.io/tensorstore/spec.html) · [Context](https://google.github.io/tensorstore/context.html) · [Drivers](https://google.github.io/tensorstore/driver/index.html) · [zarr3 driver/codecs](https://google.github.io/tensorstore/driver/zarr3/index.html) · [driver registry source](https://github.com/google/tensorstore/blob/master/tensorstore/driver/registry.h).

**zarrs** — [repo](https://github.com/zarrs/zarrs) (`zarrs/src/config.rs`, `zarrs_plugin/`, `zarrs_codec/src/options.rs`) · [docs.rs/zarrs](https://docs.rs/zarrs/latest/zarrs/) · [the zarrs Book](https://book.zarrs.dev/) · [zarrs-python](https://github.com/zarrs/zarrs-python).

**zarrita** — [zarrita.js](https://github.com/manzt/zarrita.js) (`packages/zarrita/src/codecs.ts`) · [zarrita.dev](https://zarrita.dev/what-is-zarrita.html) · original [scalableminds/zarrita](https://github.com/scalableminds/zarrita) (archived).

---

*Adapted from a standalone design review; the peer-library findings (TensorStore, zarrs, zarrita) were gathered and source-verified against upstream repositories and docs. The PR sequence is a recommendation, not a commitment — the phases are independently valuable and can be reordered or split.*
