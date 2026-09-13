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

- **Agent in the chat** — the main way in. Say *"neues Zylinderkopfprojekt"* and
  the agent works in steps: research (Wikipedia and the open web), create the
  project, ask for the numbers it needs **as a form**, record parameters,
  criteria, dependencies, skill and tool needs. It asks before starting anything
  that takes minutes.
- **Parameters and a dependency graph** — the answers are kept project-wide, and
  the graph knows which part has to follow when a value changes: change
  `ventil_d_ein` and the inlet duct, the combustion chamber and everything
  derived from it are flagged.
- **Project workspace** — for a job bigger than one part: a project directory
  with the brief in `agent.d/`, the skills it needs (existing ones copied, the
  rest learned), helper tools, and its criteria **weighted by pairwise
  comparison** (AHP) — wall thickness vs. clearance vs. mass, with a consistency
  check.
- **Dialog on the open document** — say what should happen to the model you
  already have: *"ergänze eine Bohrung"*, *"lege ein neues Bauteil mit dem Namen
  Grundplatte an"*, *"baue diese beiden Bauteile in eine Baugruppe ein"*,
  *"führe eine Festigkeitsanalyse durch"*. The model sees the document contents
  and the current selection, and **asks back** when something essential is
  missing (diameter, position, load).
- **Learn a skill** — for parts too complex for one prompt (*"bau einen
  Einlasskanal"*): the workbench researches the topic (optional, Wikipedia),
  lets the model propose a parameter set and open questions, takes your answers,
  writes `build(params)`, **validates it by actually building it** and saves it
  as a reusable skill.
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
- **Configurable backend** — Ollama-nativ (Standard, wird beim Start automatisch
  erkannt), OpenAI-kompatibler HTTP-Endpunkt oder pi-CLI; Base-URL, Modell (aus dem
  Server geladen) und API-Key im Panel einstellbar, inkl. „Verbindung testen“- und
  „Ollama starten“-Button.

## The panel

The dockable panel splits the work across four tabs, so a panel docked at its
usual ~420 px width stays readable:

| Tab | Contents |
|-----|----------|
| **Dialog** | the agent (and single instructions on the open document) |
| **Projekt** | project directory, brief + `agent.d`, skill inventory, pairwise weighting |
| **Eingabe** | variant source: free text, 2D drawing (SVG), CSV, XLSX, Spreadsheet, pasted table |
| **Ziele** | targets/tolerances, material density, feedback loop, CSV export |
| **Skills** | deterministic skill build, **learn a skill**, Skill-Designer |
| **Backend** | LLM backend, model, timeout, connection test, Ollama start |

Below the tabs sit the **Protokoll** log (draggable splitter), a status line and the
**Generieren** / **Stop** / **Schließen** buttons.

## How it works

```
You type a prompt / load a 2D drawing (SVG) / load a variant table
    │
    ▼
Ollama HTTP /api/chat  (model: qwen-gross:latest)
    │  (oder pi CLI)           • 27B, Q4_K_M, 256k ctx
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

- **Backend**: Ollama's native HTTP API by default (nothing to install beyond
  Ollama itself). The [`pi`](https://github.com/earendil-works/pi-coding-agent)
  coding-agent CLI in non-interactive (`-p`) JSON mode is an optional
  alternative; the workbench picks whatever is actually available at start-up.
- **Model**: any Ollama model; `qwen-gross:latest` by default.
- **Sandbox**: generated code can only `import` from `{Part, FreeCAD, math,
  Units, Materials}` and runs without `open`/`eval`/`exec`/`getattr`; the code
  must define a top-level `result` list of `Part.Shape` (a single shape is also
  accepted and several shapes are combined into a compound for measurement).
  This reliably stops *mistakes*; it is not a defence against a deliberately
  hostile model — see the note in `DOKUMENTATION.md`.

## Requirements

| Component | Version | Required? |
|-----------|---------|-----------|
| FreeCAD   | 1.0+    | yes |
| Ollama    | `qwen-gross:latest` pulled | yes (the default backend) |
| Node.js   | 22+     | only for the pi CLI |
| pi CLI    | `npm install -g --ignore-scripts @earendil-works/pi-coding-agent` | optional |

The server does not have to be running beforehand: `./start.sh` starts it, and the
panel's **Backend** tab has an **Ollama starten** button.

Check the backend is reachable:

```sh
ollama list                       # should show qwen-gross:latest
curl -s localhost:11434/api/tags  # the endpoint the workbench uses
pi --list-models ollama           # only when using the pi backend
```

## Install

**Option A — the installer (any FreeCAD, any platform)**

```sh
python3 install.py                 # find the Mod directories and install
python3 install.py --list          # only show what was found
python3 install.py --freecad /pfad/zu/FreeCADCmd   # ask FreeCAD itself
python3 install.py --target /pfad/zu/FreeCAD/Mod
python3 install.py --uninstall
```

It knows the Linux, macOS and Windows locations and the versioned `v1-1` style
directories of FreeCAD 1.1+, and `--freecad` asks a FreeCAD binary directly —
the only way that also covers AppImages, snaps, portable installs and a
`FREECAD_USER_HOME` override. Learned skills already in the target are merged,
not overwritten.

From inside FreeCAD's Python console it needs no arguments at all, because it
can ask the running FreeCAD:

```python
exec(open("/pfad/zu/TextToGeometry/install.py").read()); main([])
```

**Option B — take it to another machine**

```sh
python3 install.py --paket                 # -> TextToGeometry.zip
python3 install.py --paket --mit-skills    # including the skills learned here
python3 install.py --paket /tmp/T2G.zip --mit-skills
```

The ZIP unpacks to a ready-to-install `TextToGeometry/` folder. On the other
machine:

```sh
unzip TextToGeometry.zip -d /tmp/t2g
python3 /tmp/t2g/TextToGeometry/install.py
```

— or simply drop the unpacked `TextToGeometry` folder into that FreeCAD's `Mod/`
directory. Nothing but Python is required: no Ollama, no pi. Without a local
model the add-on runs on an API key (see *Backend configuration*).

Note that skills you learn are stored next to the **installed** add-on, not in
the source tree — that is why `--mit-skills` exists; it collects them from the
installations found on this machine.

Then start FreeCAD. The **TextToGeometry** tab appears under *Workbenches*.

**Option C — as part of a FreeCAD build**

Add this directory to `src/Mod/` (it ships a `CMakeLists.txt`) and rebuild.

### start.sh — one-stop helper

```sh
./start.sh            # GUI starten (prüft FreeCAD, startet Ollama bei Bedarf)
./start.sh sync       # Entwicklung -> FreeCAD-Mod-Pfad (v1-1) kopieren
./start.sh test       # alle Test-Suites (core, ext, skills) mit FreeCADCmd
./start.sh help
```

Environment-Uberschreibungen: `FREECAD`, `FREECAD_CMD`, `T2G_PI_BIN`,
`OLLAMA_MODEL`, `T2G_FREECAD_VER` (Default `1-1`), `DISPLAY`.

## Use — the agent (start here)

Tab **Dialog**, *Agent* ticked. Type what you want:

```
neues Zylinderkopfprojekt
```

The agent then works in steps and shows each one:

```
OK projekt_anlegen: Projekt angelegt: ~/T2G-Projekte/zylinderkopf
OK recherche: 3 Quelle(n): Zylinderkopf <de.wikipedia.org/...>, ...
Agent bittet um Angaben: Bohrungsdurchmesser, Ventile pro Zylinder,
                         Einlassventil-Ø, Auslassventil-Ø, Ventilwinkel
```

The form appears right in the chat, pre-filled with the agent's proposals. What
you enter becomes a **project parameter**, visible to every later step, and the
`abhaengigkeit:` lines the agent records make the knowledge graph:

```
ventil_d_ein -> einlasskanal (nutzt)      bohrung_d -> brennraum (nutzt)
```

Change a value later and the panel says which parts must be rebuilt.

The actions available to it: `projekt_anlegen`, `auftrag`, `recherche`,
`parameter`, `kriterium`, `skill_bedarf`, `werkzeug_bedarf`, `abhaengigkeit`,
`skills_kopieren`, `paarvergleich`, `agent_d`, `skill_bauen`, and the
minutes-long `skill_lernen`, `werkzeug_erzeugen`, `skill_verfeinern` — for which
it asks first. **Stop** halts after the running step; *max. N Schritte* caps the
budget. Everything it produces is editable in the other tabs: that is what they
are for.

Untick *Agent* for the old one-shot mode ("ergänze eine Bohrung").

## Use — project

Tab **Projekt** (or the folder icon). A project keeps one construction job
together on disk:

```
<projekt>/
    projekt.json                  state (owned by T2GProject)
    agent.d/00-auftrag.md         what is to be built, from the dialogue
            10-anforderungen.md   criteria, weights, consistency
            20-skills.md          which skill exists, which must be built
            30-werkzeuge.md       helper tools
    skills/<name>/<name>.py       copied or learned generators
    tools/<name>.py               helper code
    bewertung/paarvergleich.csv   the comparison matrix, spreadsheet-readable
```

1. **Neu anlegen** — directory, title, layout.
2. Describe the job, then **Projekt planen**. In one call the model returns the
   brief, its open questions, the **skills** the job needs, the **tools** it
   wants, and the **criteria** that will conflict with each other. Every field
   stays editable — it is a proposal, not a verdict.
3. **Übernehmen + agent.d schreiben** — state saved, `agent.d/` rendered.
4. **Skills**: each need is matched against the installed skills.
   **Vorhandene kopieren** copies the ones that genuinely match into the
   project; **Fehlenden lernen →** hands the first open one to the learn box
   with the whole project as context. Matching is deliberately strict about
   prefixes: `auslasskanal` does *not* count as `einlasskanal`.
5. **Paarvergleich**: for every pair of criteria, how much more important is A
   than B (Saaty 9…1…1/9)? **Vorschlag vom Modell** pre-fills the rows with a
   rationale in the log, you correct them, **Auswerten** computes the weights.

   Weights come from the geometric mean of the rows; the **consistency ratio**
   (CR = CI/RI) says whether the judgements contradict each other — CR ≤ 0.10 is
   the usual limit, and above it the panel names the judgements that fit worst.
   Note that with exactly three criteria one contradiction spreads evenly over
   all three pairs, so no single culprit can be named; from four on it can.

The weighted criteria and the brief become the context (`as_prompt_block()`) for
the learn and dialog steps — that is what makes the project more than a folder.

## Use — dialog on the open document

Tab **Dialog** (or the toolbar's speech-bubble icon). Type an instruction; the
model receives the document contents (names, labels, volumes, bounding boxes)
plus the current selection and answers with either a question or code.

| You say | What happens |
|---------|--------------|
| *Ergänze eine Bohrung mit 10 mm Durchmesser in der Mitte.* | the selected solid's shape is replaced by the cut version |
| *Ergänze eine Bohrung.* | **Rückfrage**: "Welchen Durchmesser … und wo?" — answer in the same box |
| *Lege ein neues Bauteil mit dem Namen Grundplatte an, 100×60×8.* | a new `Part::Feature` named Grundplatte |
| *Baue Klotz und Grundplatte in eine Baugruppe ein.* | an `Assembly::AssemblyObject` holding `App::Link`s to both |
| *Führe eine Festigkeitsanalyse durch: unten fest, oben 500 N.* | FEM analysis, CalculiX solver, material, constraints, gmsh mesh |

The generated code never touches the document itself. It calls a small recorded
API (`shape()`, `replace()`, `add()`, `part()`, `assembly()`, `fem()`, `note()`)
and the workbench applies those operations on the GUI thread — the import
allow-list of the sandbox stays in force.

Faces for FEM are addressed by bounding-box side (`zmin`, `xmax`, …) because the
model cannot know FreeCAD's face numbering; the workbench resolves them to real
faces.

**Solver**: meshing needs `gmsh`, solving needs CalculiX (`ccx`). The workbench
locates `ccx` (PATH, `~/.local/bin`, `~/.local/ccx/usr/bin`, `/usr/bin`) and
writes the path into FreeCAD's FEM preferences, so the FEM workbench uses the
same binary. Two ways to install it:

```sh
sudo apt install calculix-ccx                       # system-wide
# or without root:
apt-get download calculix-ccx libspooles2.2t64
dpkg -x calculix-ccx_*.deb  ~/.local/ccx
dpkg -x libspooles2.2t64_*.deb ~/.local/ccx
printf '#!/bin/sh\nLD_LIBRARY_PATH="$HOME/.local/ccx/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH" \
exec "$HOME/.local/ccx/usr/bin/ccx" "$@"\n' > ~/.local/bin/ccx && chmod +x ~/.local/bin/ccx
```

If `ccx` is missing, the analysis is still built and meshed and the panel says so,
rather than pretending to have computed anything.

Verified against the closed-form solution — a 20×20×100 steel column, fixed at
`zmin`, 500 N on `zmax`: CalculiX gives 1.258 MPa / 0.000589 mm against
σ = F/A = 1.250 MPa and δ = FL/(AE) = 0.000595 mm (0.6 % / 1.0 %), and doubling
the load doubles both.

## Use — learn a skill (complex parts)

Tab **Skills → Skill lernen**, for parts that one prompt will not get right:

1. **Bauteil**: e.g. `Einlasskanal`. **Angaben**: what you already know.
2. **Recherche** (optional, off by default): with the checkbox on, the part name
   goes to the Wikipedia API; every source used is listed in the panel. A single
   extra URL can be added. With it off, nothing leaves the machine.
3. **1. Analysieren** → the model proposes a **parameter table**
   (`name;label;einheit;default;min;max`, editable) and **open questions**.
4. Answer the questions, adjust the table.
5. **2. Skill erzeugen** → the model writes `build(params)`. The workbench
   compiles it, runs it with the default values, checks that solids with positive
   volume come out, that no parameter is ignored, and applies the kollision /
   konnektivität rules. On failure the error goes back to the model (up to
   *Versuche* attempts).
6. The skill is saved to `Skills/<name>/<name>.py` and appears in the skill combo
   — from then on it is deterministic and needs no LLM.

Note: learned skills are written next to the **installed** workbench
(`~/.local/share/FreeCAD/v1-1/Mod/TextToGeometry/Skills/`), not into this repo.
Copy them over if you want to keep them under version control.

A 27B model needs several minutes for a part like this — the **Zeitlimit** in the
Backend tab defaults to 900 s and the status line counts the seconds.

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

Dialog (tab **Skills**):

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

**Skill-Designer** (same tab, below): Name, description, one row per parameter
(namens;label;einheit;default;min;max), and the full `build(params)` code —
then **Speichern unter …**. New skills appear immediately in the combo box.

## Use — Backend configuration (Ollama / OpenAI-kompatibel)

Under the **Backend** tab:

| Backend | URL pattern | Example |
|---------|-------------|---------|
| `ollama` (default) | `…/api/chat` | `http://localhost:11434` |
| `openai` | `…/v1/chat/completions` | `http://localhost:11434/v1` (Ollama OpenAI mode) |
| `pi` | CLI binary (`T2G_PI_BIN`) | `~/.npm-global/bin/pi` |

On start-up the panel probes the machine (`T2GCore.detect_backend()`) and preselects
native Ollama when its server answers, otherwise the pi CLI when that binary exists —
so a FreeCAD started from the desktop (no `T2G_PI_BIN`, `pi` not on `PATH`) still works.

Fields: Base-URL, Modell (filled from the server by **Modelle laden** — Ollama's
`/api/tags` or the API's `/v1/models`), API-Key, and **Zugang merken**, which
stores address, model and key in FreeCAD's preferences so they survive a restart.
The key is kept in plain text there, which is why the box is off by default.

Buttons: **Verbindung testen** (reachability + a minimal prompt, for *every*
backend), **Ollama starten**, **Modelle laden**, **Zeitlimit**.

**On a machine without Ollama** the add-on runs entirely on an API: enter the
address (`https://api.openai.com/v1`, OpenRouter, Groq, Mistral, a company
endpoint, …) and the key, press **Modelle laden**, pick a model. Backend
detection prefers local Ollama, falls back to the saved API, then the pi CLI.

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
| `test_chat.py` | 26 headless tests for the dialog mode (context, protocol, recorded ops). |
| `test_learn.py` | 26 headless tests for research + skill learning (`T2G_TEST_NET=1` also hits Wikipedia). |
| `test_project.py` | 39 headless tests: project layout, AHP maths, skill matching, plan parsing. |
| `T2GProject.py` | Project workspace: layout, state, `agent.d` rendering, `PairwiseMatrix` (AHP), skill matching. Stdlib-only. |
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
| `Resources/icons/text-to-geometry.svg` | Workbench icon. |
| `Resources/icons/t2g-*.svg` | One distinct toolbar icon per command (panel, dialog, generate, skill build, skill learn, skill designer, backend). |
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
