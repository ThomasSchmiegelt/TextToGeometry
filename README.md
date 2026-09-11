# SPDX-License-Identifier: LGPL-2.1-or-later

# Text to Geometry — FreeCAD Workbench

A natural-language **text → 3D geometry** workbench for FreeCAD. Type a plain
description of a solid (or feed it a table of *variants*) — e.g.
*"a flange 80 mm outer, 40 mm bore, 12 mm thick, 4×M8 holes on a 60 mm bolt
circle"* — and the workbench asks a **local** large language model to write FreeCAD
`Part`-API code, sandbox-executes it, and adds the resulting solid(s) straight
into your active document.

No cloud, no API key. Everything runs on your machine.

## Features

- **Free text → one variant** — the original mode, described by an English/German
  prompt.
- **Variant tables** — build *many* variants from a single base geometry via one of:
  - a **CSV** file (row 1 = headers),
  - an **XLSX** file (row 1 = headers, optional sheet name),
  - a **FreeCAD Spreadsheet** object in the active document, or
  - **pasted** table text (comma / tab / semicolon delimited).
- **Targets (Ziele)** — optional per-variant constraints the shape must satisfy:
  mass (g), volume (mm³), or edge x/y/z (mm), each with `==` / `<=` / `>=` and an
  optional tolerance, **plus** a free-text criterion handed straight to the model
  (e.g. *"kantenübergänge entgraten"*).
- **Sweep + feedback loop** — for every variant the LLM generates code; FreeCAD
  measures the shape (volume / mass / bounding box) and checks each target. On a
  miss the measurement and failure reasons are fed back into the next prompt, up
  to **N iterations** per variant. A **Stop** button interrupts the sweep
  between iterations.
- **Material density** — preset densities (Stahl, Aluminium, Kupfer, Kunststoff,
  Holz, Titan) or a custom value; this drives the mass target.
- **CSV export** — variant results + measured values + failures to a CSV file.

## How it works

```
You type a prompt / load a variant table
    │
    ▼
pi (CLI harness) ──► Ollama  (model: qwen-gross:latest)
    │                          • 27B, Q4_K_M, 256k ctx
    │                          • runs locally on http://localhost:11434
    ▼
a single ```python``` block (imports: Part, FreeCAD, math)
    │
    ▼
T2GCore.exec_code_in_sandbox()   ← restricted, import-allow-list, no I/O
    │
    ▼
result = [ <Part.Shape>, ... ]   ← added to your document
    │
    ▼
measure (vol/mass/bbox)  ──►  check targets
    │                            │  fail  ──►  feedback loop (up to N times)
    ▼                            ▼
done / miss
```

- **Backend**: the [`pi`](https://github.com/earendil-works/pi-coding-agent)
  coding-agent CLI in non-interactive (`-p`) JSON mode.
- **Model**: any Ollama model; `qwen-gross:latest` by default.
- **Sandbox**: generated code can only `import` from `{Part, FreeCAD, math}`;
  network / file / subprocess access is blocked, and the code must define a
  top-level `result` list of `Part.Shape` (a single shape is also accepted and
  several shapes are combined into a compound for measurement).

## Requirements

| Component | Version |
|-----------|---------|
| FreeCAD   | 1.0+    |
| Node.js   | 22+     |
| Ollama    | running, `qwen-gross:latest` pulled |
| pi CLI    | `npm install -g --ignore-scripts @earendil-works/pi-coding-agent` |

Check the backend is reachable:

```sh
ollama list                       # should show qwen-gross:latest
pi --list-models ollama           # should list the model
```

## Install

**Option A — manual (recommended for local use)**

Copy the directory into FreeCAD's Mod folder and restart FreeCAD:

```sh
cp -r TextToGeometry ~/.local/share/FreeCAD/Mod/
# on some systems:  cp -r TextToGeometry /path/to/FreeCAD/Mod/
# (FreeCAD 1.1 uses the versioned path:  ~/.local/share/FreeCAD/v1-1/Mod/)
```

Then start FreeCAD. The **TextToGeometry** tab appears under *Workbenches*.

**Option B — as part of a FreeCAD build**

Add this directory to `src/Mod/` (it ships a `CMakeLists.txt`) and rebuild.

## Use — basic (one variant)

1. Open any document (or none — one is created for you).
2. Click the **TextToGeometry** workbench tab, then the **Generate geometry**
   toolbar icon (or menu *TextToGeometry → Generate geometry*).
3. Under *Varianten-Quelle* leave **Freitext** selected and type your prompt.
4. (Optional) Add a **Ziel** and/or pick a **Material**.
5. Click **Generieren**.
6. After a few seconds (the LLM call) the resulting solid(s) appear in the 3D view,
   labelled `T2G_nnn [OK]` (or `[MISS]` if a target was not met).

### Example free-text prompts

- *A hollow tube: outer diameter 40, inner diameter 20, length 100.*
- *An L-bracket 60×40×10 with a 12 mm rib.*
- *A conical frustum, base radius 25, top radius 15, height 40.*
- *A sphere of radius 30 with a 10 mm through-hole down the Z axis.*
- *A hex bolt head: 19 mm across flats, 10 mm tall, on an M8 shank 40 mm long.*
- *A flange 80 mm outer, 40 mm bore, 12 mm thick, 4×M8 holes on a 60 mm bolt circle.*

## Use — variant table + targets + feedback

1. Under *Varianten-Quelle* pick one of **CSV**, **XLSX**, **Spreadsheet** or
   **Einfügen** and point it at your data:

   ```csv
   laenge,breite,hoehe
   40,20,10
   60,25,12
   ```

2. Add as many **Ziele** as you like, e.g. *Volumen (mm³) `<=` 15000* or a
   free-text goal *kantenübergänge entgraten*.
3. Pick a **Material** (the density feeds the mass target) — or pick
   **Eigene Dichte…** and enter a value.
4. Set **Max. Feedback-Iterationen pro Variante** (default 3) and leave
   *Zielverfehlungen + Messwerte als Feedback an das Modell zurückgeben* ticked.
5. Optional: enable *Ergebnisse + Messwerte als CSV exportieren* and choose a path.
6. Click **Generieren**. Each variant is generated, measured and checked; on a
   miss the values are fed back for up to the configured number of iterations.
   **Stop** aborts the sweep after the current iteration.

## Files

| File | Purpose |
|------|---------|
| `Init.py` | FreeCAD package marker (headless init). |
| `InitGui.py` | GUI init — registers the workbench + command. |
| `T2GCommand.py` | Workbench class, command, dialog (source/target/material/sweep UI), worker thread. |
| `T2GCore.py` | Backend: pi invocation, NDJSON parse, prompt build, code extraction, sandbox, measurement, table readers, sweep engine, CSV export. Stdlib-only. |
| `test_core.py` | 7 headless unit tests (sandbox / parse). No FreeCAD needed. |
| `test_ext.py` | 14 headless unit tests (targets, measurement, table readers, sweep engine, CSV). Fake-`Part` only — no FreeCAD/model needed. |
| `e2e_freecad.py` | End-to-end single-prompt test in a real FreeCAD (model required). |
| `e2e_sweep_freecad.py` | End-to-end **sweep** test in real FreeCAD with the **real** LLM pipeline (model required). |
| `Resources/icons/text-to-geometry.svg` | Toolbar icon. |
| `Resources/licenses/LGPL-2.1-or-later.txt` | License. |
| `package.xml` | Addon Manager metadata. |
| `CMakeLists.txt` | FreeCAD-build integration. |

## Development / testing

The core backend is pure stdlib and has **no FreeCAD dependency**, so it can be
tested directly in plain CPython:

```sh
cd TextToGeometry
python3 test_core.py   # 7 headless sandbox / parse tests
python3 test_ext.py    # 14 headless target / measure / table / sweep / csv tests
```

A quick live round-trip (requires a running model):

```sh
export T2G_PI_BIN=/path/to/pi      # or have pi on PATH
python3 - <<'PY'
import T2GCore as T
raw  = T.run_backend("A solid 50 mm cube.", pi_binary=T.find_pi_binary())
print(T.extract_code_block(raw))
PY
```

Execution of generated solids (`Part.makeBox`, …) and the end-to-end tests
(`e2e_freecad.py`, `e2e_sweep_freecad.py`) only run inside a FreeCAD, where the
`Part` module is provided:

```sh
T2G_PI_BIN=/path/to/pi FreeCADCmd e2e_sweep_freecad.py   # writes sweep_result.txt
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Could not find 'pi' on PATH` | `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`, or set `T2G_PI_BIN`. |
| `pi exited with code …` | Check `ollama list`; confirm the Ollama server is up. |
| `Disallowed import …` | The model tried to import outside `{Part, FreeCAD, math}` — rephrase the prompt. |
| `Generated code did not define a top-level 'result'` | Model returned unusable code; retry with a more explicit prompt. |
| A variant shows `[MISS]` | A target was not met even after the feedback iterations — inspect the exported CSV / raise the iteration count. |

## License

LGPL-2.1-or-later (see `Resources/licenses/LGPL-2.1-or-later.txt`).
