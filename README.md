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
- **2D drawing (SVG) → 3D** — give the workbench a 2D front-elevation SVG whose
  `<desc>` element carries a machine-readable spec (units, coordinate mapping,
  element list with coordinates); the LLM decomposes the drawing into structural
  elements and builds the 3D model (reference: `Resources/drawings/bridge.svg`).
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
- **Skills (deterministic generators)** — parameterized Python build-functions lived
  under `Skills/<name>/<name>.py`; no LLM needed, exact reproducibility, with
  built-in check rules (kollision, Konnektivität). Reference skill:
  `Skills/bruecke/bruecke.py` (parametrisierte Fachwerkbrücke, 13 Solids).
- **Skill-Designer** — create new skills dialogisch (Name, Beschreibung,
  Parameter-Tabellenzeilen, `build(params)`) code, speichern unter …).
- **Configurable backend** — pi-CLI (Standard), OpenAI-kompatibler HTTP-Endpunkt
  oder Ollama-nativ; Base-URL, Modell und API-Key im Dialog einstellbar, inkl.
  „Verbindung testen“-Button.

## How it works

```
You type a prompt / load a 2D drawing (SVG) / load a variant table
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
./start.sh sync      # kopiert alle Dateien inkl. Skills/ in den FreeCAD-Mod-Pfad
# oder manuell:
cp -r TextToGeometry ~/.local/share/FreeCAD/Mod/
# on some systems:  cp -r TextToGeometry /path/to/FreeCAD/Mod/
# (FreeCAD 1.1 uses the versioned path:  ~/.local/share/FreeCAD/v1-1/Mod/)
```

Then start FreeCAD. The **TextToGeometry** tab appears under *Workbenches*.

**Option B — as part of a FreeCAD build**

Add this directory to `src/Mod/` (it ships a `CMakeLists.txt`) and rebuild.

### start.sh — one-stop helper

```sh
./start.sh            # GUI starten (prüft FreeCAD, pi-CLI, Ollama)
./start.sh sync       # Entwicklung -> FreeCAD-Mod-Pfad (v1-1) kopieren
./start.sh test       # alle Test-Suites (core, ext, skills) mit FreeCADCmd
./start.sh help
```

Environment-Uberschreibungen: `FREECAD`, `FREECAD_CMD`, `T2G_PI_BIN`,
`OLLAMA_MODEL`, `T2G_FREECAD_VER` (Default `1-1`), `DISPLAY`.

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

## Use — 2D drawing (SVG) → 3D

1. Prepare a 2D front elevation as an SVG file whose `<desc>` element contains a
   machine-readable spec (this is what the LLM actually reads — the graphics are
   just for humans/tools):
   - **units**,
   - the **coordinate mapping** (e.g. drawing X → FreeCAD X, height H → Z,
     depth → Y),
   - the **element list** with coordinates and section sizes
     (e.g. `piar 1: x 175..325, H 0..1100, depth 400, section 150x150`).

   `Resources/drawings/bridge.svg` is a complete reference: a truss bridge with
   piers, deck, verticals, top chord and diagonals — all listed in its `<desc>`.

2. In the dialog pick **2D-Zeichnung (SVG)** under *Varianten-Quelle*.
3. Point the path at your SVG and click **Zeichnung laden** — the `<desc>` spec
   is displayed for review.
4. (Optional) add **Ziele** and pick a **Material** as with the other modes.
5. Click **Generieren**. The spec is turned into a build prompt (coordinate
   mapping, axis-aligned boxes, `bar()` helper for diagonals), sent to the LLM,
   executed in the sandbox and the solids are added to the document.

Programmatic use (no GUI needed):

```python
import T2GCore
spec   = T2GCore.load_drawing_spec("mybridge.svg")     # <desc> text, validated
prompt = T2GCore.build_drawing_prompt(spec)            # full build prompt
raw    = T2GCore.run_backend(prompt, pi_binary=...)
code   = T2GCore.extract_code_block(raw)
shapes = T2GCore.exec_code_in_sandbox(code)            # list of Part.Shape
```

## Use — Skill (deterministischer Generator)

Skills are parameterized Python build functions. No LLM, fully reproducible,
fast. Files: `Skills/<name>/<name>.py`.

```python
T2G_SKILL = {
    "name": "bruecke",
    "description": "...",
    "parameters": [
        ("span", "Gesamltes", "mm", 2000, 100, 50000),
        ("deck_t", "Fahrbahn-Dicke", "mm", 100, 10, 500),
        ...
    ],
    "dependencies": ["Part", "FreeCAD", "math"],
    "rules": ["collision", "connectivity"],
}

def build(params):
    span = params["span"]
    ...
    return [Part.makeBox(...), bar(...), ...]
```

Dialog (tab **Skill & Backend**):

1. Select a skill (e.g., `bruecke`) — the parameter form is filled in with
   defaults, min/max is enforced.
2. Adjust the parameters as needed.
3. **Build** → all solids are added to the active document, and test warnings
   (kollisionen, disconnects) are shown in the log.

Programmatic:

```python
import T2GSkills
eng = T2GSkills.get_engine("Skills")          # load all skills
shapes, vals, issues = eng.build("bruecke", {"span": 2500})
shapes   # list[Part.Shape]
vals     # normalized parameter dict (default values applied)
issues   # list[str] — kollision/konnektivitaet violations if any
```

**Skill-Designer** (same tab): Name, description, one row per parameter
(namens;label;einheit;default;min;max), and the full `build(params)` code —
then **Speichern unter …**. New skills appear immediately in the combo box.

## Use — Backend configuration (Ollama / OpenAI-kompatibel)

Under **Skill & Backend → LLM / Backend**:

| Backend | URL pattern | Example |
|---------|-------------|---------|
| `pi` | CLI binary (`T2G_PI_BIN`) | `~/.npm-global/bin/pi` |
| `openai` | `…/v1/chat/completions` | `http://localhost:11434/v1` (Ollama OpenAI mode) |
| `ollama` | `…/api/chat` | `http://localhost:11434` |

Fields: Base-URL (auto-switching between OpenAI mode and native Ollama mode),
Modell, API-Key (password field). **Verbindung testen** sends a minimal prompt
without touching the document.

Programmatic:

```python
import T2GCore
cfg  = T2GCore.APIConfig(kind="ollama",
                         base_url="http://localhost:11434",
                         model="qwen-gross:latest")
code, shapes = T2GCore.generate_via_api("a 10x10x10 box", cfg=cfg)
```

## Files

| File | Purpose |
|------|---------|
| `Init.py` | FreeCAD package marker (headless init). |
| `InitGui.py` | GUI init — registers the workbench + command. |
| `T2GCommand.py` | Workbench class, command, dialog (source/target/material/sweep UI), worker thread. |
| `T2GCore.py` | Backend: pi invocation, NDJSON parse, prompt build, **drawing-spec loading (`load_drawing_spec`) + drawing prompt build (`build_drawing_prompt`)**, code extraction, sandbox, measurement, table readers, sweep engine, CSV export. Stdlib-only. |
| `test_core.py` | 13 headless unit tests (sandbox / parse / drawing spec). No FreeCAD needed. |
| `test_ext.py` | 14 headless unit tests (targets, measurement, table readers, sweep engine, CSV). Fake-`Part` only — no FreeCAD/model needed. |
| `test_skills.py` | 14 tests for the skill engine (params, validation, load/build, `create_skill` roundtrip, rules). |
| `T2GSkills.py` | Skill engine: `SkillParam`/`SkillDefinition`, sandboxed exec (`_safe_import` Whitelist), `SkillRegistry`, `SkillEngine`, `apply_rules` (kollision/konnektivitaet), `create_skill`. |
| `Skills/bruecke/bruecke.py` | Reference skill: parametrische Fachwerkbrücke (10 Parameter, 13 Solids at defaults). |
| `start.sh` | Helfer: `gui`/`sync`/`test` + Dependency-Checks. |
| `DOKUMENTATION.md` | Anwender-Dokumentation auf Deutsch (Zwecke, Workflows, Skills, Backends). |
| `e2e_freecad.py` | End-to-end single-prompt test in a real FreeCAD (model required). |
| `e2e_sweep_freecad.py` | End-to-end **sweep** test in real FreeCAD with the **real** LLM pipeline (model required). |
| `e2e_bridge_drawing.py` | End-to-end **2D drawing → 3D** test: `bridge.svg` `<desc>` → LLM → 13 solids (model required). |
| `Resources/drawings/bridge.svg` | Reference 2D truss-bridge elevation with a machine-readable `<desc>` spec (units, mapping, elements). |
| `Resources/icons/text-to-geometry.svg` | Toolbar icon. |
| `Resources/licenses/LGPL-2.1-or-later.txt` | License. |
| `package.xml` | Addon Manager metadata. |
| `CMakeLists.txt` | FreeCAD-build integration. |

## Development / testing

The core backend is pure stdlib and has **no FreeCAD dependency**, so it can be
tested directly in plain CPython:

```sh
cd TextToGeometry
python3 test_core.py   # 13 headless sandbox / parse / drawing-spec tests
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
(`e2e_freecad.py`, `e2e_sweep_freecad.py`, `e2e_bridge_drawing.py`) only run
inside a FreeCAD, where the `Part` module is provided:

```sh
T2G_PI_BIN=/path/to/pi FreeCADCmd e2e_sweep_freecad.py    # writes sweep_result.txt
T2G_PI_BIN=/path/to/pi FreeCADCmd e2e_bridge_drawing.py   # writes T2G_OUT (bridge 2D->3D)
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
