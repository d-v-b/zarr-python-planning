# Zarr-Python v4 — API Preview

This directory contains a **non-functional, projected snapshot of the Zarr-Python public API** as it would look after the entire [v4 plan](../README.md) has landed. It exists to let reviewers and stakeholders browse the *destination* of the v4 work as a single, coherent API surface — before the code is written.

> [!WARNING]
> **This is a preview of unreleased, projected API.** Nothing here executes real IO; every function body is a stub (`...`). Signatures and names are synthesized from the planning [`proposals/`](../proposals) and will change as the work is designed and implemented. Do not depend on this. Signatures the proposals leave to implementation are flagged `(inferred)` in their docstrings.

## Two versions

- **`src/zarr/`** — **Version 1, the final state.** The public API after `4.0.0`, reshaped around the seven-level "Zarr stack," with deprecated surfaces already removed.
- **`src/zarr_legacy/`** — **Version 2, the removed surfaces.** A mirror of the current-3.x public surfaces that the plan deprecates and then removes in `4.0.0`. Each symbol is annotated with the release it's removed in and its Version-1 replacement. This is the "what's going away" companion and migration map.

## Building the site

```bash
cd api-preview
python -m venv .venv && source .venv/bin/activate
pip install -e ".[docs]"
mkdocs serve      # live preview at http://127.0.0.1:8000
mkdocs build --strict
```

The site is [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/) + [mkdocstrings](https://mkdocstrings.github.io/), the same toolchain the real zarr-python docs use. API pages are thin `::: zarr.<symbol>` directives that mkdocstrings renders from the stubs.

## Importing the stubs

The stub tree imports with only the Python ≥ 3.12 standard library — no `numpy`, `fsspec`, `obstore`, or `ml_dtypes` required:

```bash
PYTHONPATH=src python -c "import zarr, zarr_legacy"
```

All annotations use `from __future__ import annotations`, so cross-module type references are strings and never evaluated at runtime.
