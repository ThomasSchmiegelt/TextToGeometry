# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FreeCAD 1.x workbench add-on ("TextToGeometry"): natural-language text, a 2D SVG
drawing, a variant table, or a deterministic "Skill" is turned into `Part.Shape`
solids that are added to the active FreeCAD document. LLM calls go to a **local**
model (Ollama, default `qwen-gross:latest`) either through the `pi` CLI or over HTTP.

User-facing strings and much of the documentation are German; code, identifiers and
comments are mostly English. Keep that split when editing.

## Commands

```sh
./start.sh              # launch the GUI; starts Ollama if it is not running
./start.sh sync         # copy dev files into the FreeCAD Mod dir (see below)
./start.sh test         # all five suites under FreeCADCmd

python3 test_core.py    # 13 tests: sandbox, NDJSON parse, drawing spec — stdlib only
python3 test_ext.py     # 14 tests: targets, measurement, table readers, sweep, CSV
python3 test_chat.py    # 26 tests: dialog protocol, document context, recorded ops
python3 test_learn.py   # 26 tests: research, skill learning, validation
python3 test_project.py # 61 tests: project layout, AHP maths, matching, params, graph
python3 test_agent.py   # 24 tests: agent protocol, action registry, run budget
FreeCADCmd test_skills.py   # skills engine — needs the REAL Part module (see gotcha)
FreeCADCmd test_bauen.py    # 32 checks: placement, replace, collisions, bearing, tools
FreeCADCmd test_getriebe_makro.py  # 32 checks: mask, DIN 625, housing, FCGear
FreeCADCmd test_kurbeltrieb.py     # 50 checks: parts, docking, R2…V12 (T2G_TEST_LANG=1 for all ten)
FreeCADCmd Beispiele/getriebe_5gang.py   # reference gearbox; exits 1 if a promise breaks
FreeCADCmd test_bauen.py    # 24 checks: placement, replace, collisions, bearing, mesh phase
FreeCADCmd Beispiele/getriebe_5gang.py   # reference gearbox; exits 1 if a promise breaks

T2G_TEST_NET=1 python3 test_learn.py   # also exercises the live Wikipedia call
```

There is no test runner, no lint config and no package install: each `test_*.py` is a
plain script of `assert`s that exits non-zero on failure. To run a single test, edit or
copy the relevant `t_*` function / numbered block — they are not individually selectable.

E2E tests need a running model and real FreeCAD:

```sh
T2G_PI_BIN=/path/to/pi FreeCADCmd e2e_freecad.py
T2G_PI_BIN=/path/to/pi FreeCADCmd e2e_sweep_freecad.py     # -> sweep_result.txt
T2G_PI_BIN=/path/to/pi FreeCADCmd e2e_bridge_drawing.py    # -> $T2G_OUT
```

Env overrides: `FREECAD`, `FREECAD_CMD`, `T2G_PI_BIN`, `OLLAMA_MODEL`,
`T2G_FREECAD_VER` (default `1-1`), `T2G_TEST_OUT`, `T2G_OUT`, `DISPLAY`.

### Editing → running loop

FreeCAD loads the add-on from `~/.local/share/FreeCAD/v1-1/Mod/TextToGeometry`, **not**
from this repo. Edits are invisible until `./start.sh sync` runs. `sync_src()` in
`start.sh` copies an *explicit file list* — a new top-level module must be added there
(and to `CMakeLists.txt`, which is already stale: it omits `T2GSkills.py` and `Skills/`).

FreeCAD/FreeCADCmd swallow stdout, so headless tests and e2e scripts mirror their output
into a file (`T2G_TEST_OUT`, `T2G_OUT`) — read that file, not the terminal.

## Architecture

Three top-level modules, imported flat (`import T2GCore`) because FreeCAD `exec()`s
`Init.py` / `InitGui.py` with the add-on dir on `sys.path`. There is no package; do not
introduce relative imports.

- **`T2GCore.py`** — the whole backend, **standard library only**. It must stay importable
  without FreeCAD (that is what makes `test_core.py` / `test_ext.py` runnable in plain
  CPython with stub `Part`/`FreeCAD` modules injected into `sys.modules`). Never add a
  top-level `import Part` / `import FreeCAD` here.
- **`T2GSkills.py`** — deterministic, LLM-free geometry generators plus their own sandbox
  and check rules.
- **`T2GProject.py`** — project workspace: directory layout, `projekt.json` state,
  `agent.d/*.md` rendering, `PairwiseMatrix` (AHP), skill matching. Stdlib only, like
  `T2GCore`.
- **`T2GCommand.py`** — all PySide6 UI. A single `T2GPanel` lives in a `QDockWidget`
  (module globals `_PANEL` / `_DOCK`, created lazily by `_get_panel()`); the five
  commands registered in `InitGui.py` (`T2G_Panel`, `T2G_Generate`, `T2G_SkillBuild`,
  `T2G_SkillDesign`, `T2G_ApiTest`) all act on that one panel.

### Five ways in

1. **Sweep** (`run_sweep`) — prompt/table in, new solids out. Knows nothing about
   the document.
2. **Dialog** (`ChatSession`, `OpRecorder`) — works *on* the open document.
3. **Learn a skill** (`build_skill_analyse_prompt` → `build_skill_code_prompt` →
   `T2GSkills.validate_skill_source` → `create_skill`) — turns a complex part into
   a deterministic generator, with optional Wikipedia research.
4. **Project** (`T2GProject`) — a directory holding one job: brief, criteria with
   AHP weights, parameters, dependency graph, skills, tools.
5. **Agent** (`T2GAgent` + `T2GPanel._agent_*`) — the main entry: the chat drives
   the other four. This is what users are expected to use.

All five share the backend layer and the import allow-list.

### The generation pipeline (T2GCore)

```
prompt ─► run_backend()  (pi CLI, NDJSON)   ─┐
         run_api()       (OpenAI-compatible / Ollama native, APIConfig)
                                             ├─► extract_code_block()
                                             │   ─► exec_code_in_sandbox() ─► list[Part.Shape]
                                             │      ─► measure_shape() ─► Measurement
                                             │         ─► Target.check() ─► failures
                                             └────────── feedback into build_prompt() ◄┘
```

Key seam: `run_sweep(SweepConfig)` never calls an LLM itself — it invokes the injected
`generate_fn: (prompt) -> (code, shapes)`. Tests pass a fake; the GUI passes
`T2GCore._generate_once` (optionally bound to an `APIConfig`). Add new sweep behaviour
here rather than in the GUI.

`build_prompt()` is the single place where row values, targets, density and the previous
iteration's measurement + failure reasons are composed; targets of `kind == "text"` are
handed to the model verbatim and never checked programmatically.

Two sandboxes, deliberately different:
- LLM code (`exec_code_in_sandbox`): import allow-list `{Part, FreeCAD, math, Units,
  Materials}`, checked both statically (regex over import lines) and dynamically (a
  `sys.meta_path` hook + replaced `__import__`), a minimal `__builtins__`, and a required
  top-level `result` list of shapes.
- Skill code (`T2GSkills._skill_namespace`): only `math` is importable; `Part` and
  `FreeCAD` are *injected* into the namespace instead, and stay absent in pure-Python
  test contexts.

### Dialog mode

`CHAT_SYSTEM_PROMPT` fixes a two-block protocol: the model answers with
either ```` ```frage ```` (a clarifying question — `parse_chat_reply` lets the
question win if both blocks appear) or ```` ```python ````. `ChatSession` keeps
the last turns plus the pending question, and `describe_document()` renders the
document context (plain dicts, so it stays testable without FreeCAD).

The crucial invariant: **generated code never touches the document**. It calls
`OpRecorder` methods (`shape`, `info`, `names`, `selected`, `add`, `replace`,
`part`, `assembly`, `fem`, `note`) which only record dicts; `T2GPanel._apply_ops`
applies them on the GUI thread. Keep it that way — it is what lets the sandbox
stay closed while the model still edits real geometry.

FEM faces are addressed as bounding-box sides (`zmin`, `xmax`, …) and resolved by
`_faces_on_side()`; the model cannot know FreeCAD's face numbering. Meshing uses
`gmsh`, solving CalculiX. `_find_ccx()` locates the binary and writes it into
`BaseApp/Preferences/Mod/Fem/Ccx` — `FemToolsCcx` reads that preference, not our
PATH lookup. ccx 2.21 is installed **user-locally** here (`~/.local/ccx` from the
extracted .deb, wrapper `~/.local/bin/ccx` setting `LD_LIBRARY_PATH` for
libspooles); it is not on the system.

FreeCAD 1.1 spells the maker `makeSolverCalculiXCcxTools` (capital X), the mesh
attribute is `mesh.Shape` (not `.Part`), and `ConstraintForce.Force` accepts
`"500 N"`. FreeCAD creates two identical result objects per solve — `_run_ccx`
de-duplicates by (max stress, max displacement).

Sanity check when touching this path: a 20×20×100 steel column, `fixed="zmin"`,
`load="zmax"`, 500 N must give ≈1.25 MPa and ≈0.000595 mm (σ = F/A, δ = FL/AE).

### The agent loop

`T2GCore.AGENT_SYSTEM_PROMPT` fixes one block per answer: `aktion` | `maske` |
`frage` | `python` | `fertig`. `parse_agent_reply` gives a question or a form
precedence over actions, so a hedging model never half-builds something.

`T2GAgent` holds only protocol and state; every action is implemented in
`T2GPanel._act_*` and registered in `_agent_registry()` — that is where FreeCAD,
the project and the skill engine live. An action that raises becomes an
`Observation` fed back to the model, never an exception.

The three minutes-long actions (`skill_lernen`, `werkzeug_erzeugen`,
`skill_verfeinern`) are not run inline: `_agent_start_job` hands them to the
existing panel flows and sets `_agent_job_done`, which those flows call on
success or final failure (`_job_finished`) to resume the loop.

The loop remembers three different ways, and all three were needed:
- `AgentRun.transcript` — what was said. Without it the model re-asked a list
  the user had typed two turns earlier, over and over.
- `AgentRun.summary` — the older transcript, condensed by the model itself
  (`SUMMARY_PROMPT`) once there is a real backlog (`needs_compression()`:
  more than `compress_at`, *and* at least `min_to_compress` entries behind the
  `keep_raw` newest). Truncating instead would drop exactly the durable facts.
  Condensing a single stray line produced "Zahlen: keine" noise, hence the
  proportionality check and the "leave empty categories out" rule in the prompt.
- `Project` — parameters, criteria, graph, skills, `chat`, `chat_summary`,
  written on every chat line and restored on the next start
  (`_restore_last_project`, pref `last_project`).

Two hard-won details:
- A small model narrates instead of acting ("Projekt angelegt." with no `aktion`
  block). `fertig` is therefore refused while `run.did_work` is False — checking
  "no observations yet" was not enough, because the refusal itself is an
  observation and the second claim slipped through. The refusal carries a
  ready-made action block built from the user's own words (`_agent_example`);
  a generic "use an action block" was ignored five rounds running.
- Qt swallows exceptions in slots. `_agent_step` and `_agent_mask_submit` wrap
  everything, because a raised error there leaves the loop hanging silently —
  which is exactly how the `"%s" % (a, b).strip()` precedence bug (strip applied
  to the tuple) hid for a whole run.

### Placing parts

`skill_bauen` takes `x/y/z` and `dreh_x/y/z` besides the skill parameters, and
`als=` for the label. `_place_shape` copies the shape and sets only its
`Placement` — it must never do anything that changes the volume. Before that
existed the agent moved parts with free-form ```python and fused helper solids
into them instead (a 44 mm gear came back 64 mm with five times the volume),
which is why the prompt now forbids ```python for positioning outright.

Part names and skill names are two namespaces: the project needs `zahnrad_3`,
the registry holds `zahnrad`. `_resolve_skill_name()` goes via
`SkillNeed.source`, then the name stem, and its error lists the skills that do
exist — "unknown skill" alone cost twelve steps in one run.

Building the same part again **replaces** it: `_add_skill_shapes()` removes
every object whose label starts with `T2G <name> [` first. The agent routinely
rebuilds a part after seeing where it landed, and appending left 26 bodies for
17 parts — with the misplaced ones still in the document.

`_describe_build()` reports the resulting bounding box *in document
coordinates*. Without the position the agent cannot tell ten stacked parts from
ten placed ones, and happily reported success on a pile at the origin.

### The reference gearbox

`Beispiele/getriebe_5gang.py` is the versioned form of the gearbox: it builds all
17 parts from the four skills plus `Tools/getriebe_auslegung.py` and checks seven
promises (part count, every part a solid, one centre distance for all five gears,
≥ 3 mm gear-to-wall clearance, tip circles larger than the centre distance so the
teeth actually mesh, outer width = inner + 2 × wall). It exits 1 on any breach, so
it doubles as a regression test over the skills. The `.FCStd` is its *output* and
stays gitignored — regenerate it rather than committing a binary.

### What the agent is told about skills and tools

Both blocks were once nearly content-free, and both cost a whole gearbox run:

- `VERFÜGBARE SKILLS` was `", ".join(names)`. `T2GSkills.describe_skills()` now
  renders description, parameters with defaults and units, and **`achse`** — the
  axis the skill builds along (`T2G_SKILL["achse"]`, default `"z"`). `gehaeuse`
  puts its shaft bores along X; the agent had laid the gearbox out along Z and
  built the housing beside the assembly four times running, because no
  translation can fix a wrong axis. With the axis declared it can turn the part
  with `dreh_x/y/z`.
- Every Python tool showed the *module* docstring, so twelve functions in
  `getriebe_auslegung.py` produced twelve identical lines. `module_signatures()`
  reads each function's own first docstring line and its argument list via AST,
  and `ExternalTool.signature` carries it into the prompt — `achsabstand(modul,
  z1, z2): Achsabstand a = m · (z1 + z2) / 2 [mm]`. The agent had guessed
  `wellen_abstand = 50` with that function sitting unused, and produced gears
  whose tip circles (22 + 22 = 44 mm) never touched.

Hence two prompt rules: derived dimensions come from a tool when one exists, and
several instances of one skill must differ in the parameters that distinguish
them (five gears at the default `zaehne=20` are five identical 1:1 pairs).

### Collisions across the document

`T2GSkills.check_kollision` only ever saw the shapes of **one** skill. Ten gears
built at the same axial position are ten separate builds, each clean on its own,
so nothing ever noticed they were stacked. `T2GPanel._kollisionen()` checks every
solid in the document against every other; `skill_bauen` appends an `ACHTUNG`
line for the part it just built, and the `kollision:` action checks everything.

Every build also reports `uebrige Bauteile liegen bei x …, y …, z …`
(`_ausdehnung()`), and `kollision:` reports the whole assembly's box. That line
goes on **every** build, not only on a collision: a housing placed 300 mm away
overlaps nothing at all, so a collision-only message left exactly that mistake
unreported. "It collides" was not enough to repair a housing — the agent knew it
was wrong and still missed twice, because nothing said where the rest actually
sits.

Two properties that keep it usable:
- `_overlap()` prefilters with `BoundBox.intersect` — 26 bodies are 325 boolean
  commons, minutes of work; the box test rejects nearly all of them and the
  whole-document pass measures 0.13 s.
- `_KOLL_TOL` (2 % of the smaller part) is what separates a fit from a clash.
  Meshing gears genuinely intersect a little — 15/35 teeth at 50 mm centre
  distance must **not** be reported, two gears at the same place (100 %) must.
  Both are tested.

### Tools may build, not only calculate

A gearbox is deterministic: centre distance, tooth counts, part positions and
housing dimensions all follow from a handful of inputs. A model placing
seventeen parts by hand has seventeen chances to get it wrong — and did, run
after run. The division of labour that works is: **the agent reads the request,
a script builds the assembly.**

`Tools/getriebe.py` is that script — `baue()` returns `(label, shape)` pairs for
the complete gearbox, `kennwerte()` the design figures alone, `pruefe()` measures
a result, `selbsttest()` wraps it. `Beispiele/getriebe_5gang.py` is only its
command-line face; the geometry lives in the tool, so there is one source of
truth.

For that to work, `run_external_tool` had to learn that a Python tool can return
geometry. `_shapes_from_result()` accepts a shape, a list of shapes, or a list of
`(label, shape)` pairs — the last is what lets a tool name its own parts — and
anything else stays text, so `achsabstand(...) → 48.0` still works.
`_add_tool_shapes()` puts them in the document under `T2G <entry> · <label>`,
replacing what an earlier call of the same tool left, and runs the collision
check over the result.

Getting the agent to *use* it took two more attempts. Ordering came first:
fourteen FCGear commands stood ahead of the Python tools and the list was cut at
25, so `getriebe.baue` sat at position 15. Callable Python tools now sort first,
the limit is 40, and the header says plainly that a function building the whole
assembly should be called instead of placing parts. That was still not enough —
the model reaches for `skill_bauen` whatever the prompt says. So the builder is
**put where its hand already goes**: `_baugruppen_werkzeug()` lets
`skill_bauen: getriebe;gaenge=5;abstand=3` resolve to the tool when no skill of
that name exists, and assembly builders are listed inside the SKILLS block too.
Fighting the model's habit loses; moving the target wins.

Even that was not enough on its own. What finally lands is an observation **at
the decision point**: `_werkzeug_hinweis()` appends to the result of
`baugruppe:` — the very step where the model commits to seventeen parts — a line
naming the builder and its signature. Advice read earlier in the prompt competes
with everything else in it; a result of what the agent just did does not.

### Ending a run on facts, not on wording

`_agent_finish` had two guards, both keyed on word lists (`_PROMISE_WORDS`,
`_BUILD_WORDS`), and both missed: a run ended after two steps on "Abhängigkeiten
eingetragen. Nächster Schritt: Zahnräder bauen" — the list holds "im nächsten
schritt", not "nächster schritt", and "gebaut", not "eingetragen". Word lists
only ever know the cases that already happened. The check that holds is the
state: parts still `offen` in the project, or no new solid in the document, means
the job is not done however the answer is phrased.

### The macro line: FCGear, DIN bearings, contour housing

A second, independent way to build a gearbox, next to `Tools/getriebe.py` —
that one stays untouched. Logic lives in importable `Tools/*.py` (testable, and
the agent reaches it through `skill_bauen`); the `.FCMacro` files in `Macros/`
are thin starters, because a macro gets no arguments and returns nothing
(`run_external_tool`, `T2GCommand.py:4955`).

- `Tools/t2g_maske.py` — the extensible mask. Fields are appended to a list,
  not coded: `Feld(name, label, einheit, default, min, max, auswahl, gruppe)`.
  Number → `QDoubleSpinBox`, `auswahl` → `QComboBox`, else `QLineEdit`, one tab
  per group. Values are remembered in the FreeCAD preferences. Without a GUI it
  returns the defaults, so tests and the agent path run.
- `Tools/lager_din625.py` — series 60xx/62xx/63xx, d 10…50. **Only d, D, B and
  r are standardised**; ball count and diameter are not, and are estimated from
  the geometric limit `n < pi/asin(r_kugel/r_mitte)` times 0.7 (a 6204 gets 9,
  the real one has 8). A first attempt with a fudge factor packed in 15 balls
  that touched each other.
- `Tools/werkstoff.py` — 100Cr6 is not among FreeCAD's 200 cards, and
  `PropertyMaterial::Save()` stores **only the UUID**, so a material built at
  runtime is gone after reopening. The module writes the card into the user
  library (which sits at `v1-1/Material`, not `FreeCAD/Material`) and falls
  back to `CalculiX-Steel` audibly, never silently.
- `Tools/gehaeuse_kontur.py` — the wall follows the gear contour, **section by
  section**: `abschnitte=[(laenge, [r_innen je Achse]), …]` with final inner
  radii. One section gives two cylinders, which is exactly what the first
  housing looked like. Measured on a five-speed box, the housing now steps
  90 → 86 → 82 → 78 → 74 mm across the gears and narrows to 55 mm at the
  bearing seats. Split in the plane **through both shaft axes**, not midway
  between them: that one is skew, does not halve the bearing seats, and split
  220973 against 66158 mm³. The flange runs along the shaft; its bolts sit on
  the two ears, and `baue()` counts how many holes hit material.

  Sections are built from **3D primitives** (cylinders plus a bridge box),
  not from a 2D contour offset and extruded. Three OCC failures forced that,
  and each one is silent:
  - `removeSplitter()` ate a body: 133775 mm³ became 11762 at five sections,
    while seven sections of the same kind were untouched. `_verfeinern()` keeps
    the refined shape only if the volume survives.
  - `common()` against the half-space returned an empty shape (0 solids,
    infinite bounding box) where `cut()` worked, so the split uses two cuts.
  - Two circles that do not touch (23.5 mm at 48 mm centres, the bearing seat)
    leave the contour in two pieces, and `max(Wires, key=Length)` silently took
    one: 6335 mm³ of wall around one bearing, 656 around the other. `_steg()`
    bridges them — and its winding matters, a face with normal −Z fuses into
    five faces instead of one, at identical area.

  Shaft bores are cut **after** the flange is fused on, or the collar fills
  them in again and the shaft sits inside the end wall.

  A section may also carry explicit outer radii — `(laenge, innen, aussen)` —
  and that is how a **partition wall** is built: its cavity is only the shaft
  bore while its outside matches the neighbouring gear section. Without it the
  bearing sleeve ended in mid-air: 451 mm³ of sleeve per millimetre at
  x 1…13, then nothing from x 15 on. The bearing needs that wall to seat
  against.
- `Tools/getriebe_fcgear.py` — real involute gears, idlers and shift sleeves.

Two facts that cost a measurement each: the idler needs **half a tooth pitch**
of phase (`180/z2`), or gear pair 1 penetrates by 11.8 %; and a helical mating
gear needs the **opposite hand** (`-schraegwinkel`), because two same-hand
helical gears on parallel shafts do not mesh (5.7 % penetration). The housing
also needs shaft bores, or the shaft sits inside the end wall (2.7 %).

FCGear itself: `num_teeth` not `teeth`, `helix_angle` not `beta`, an
`ActiveDocument` must exist, `recompute()` is mandatory before `Shape` or
`pitch_diameter` mean anything. The parameter objects are removed again after
the shape is read — otherwise a dozen of them recompute on every change.

Three workbench commands wrap the same `Tools/` functions as the macros:
`T2G_Getriebe`, `T2G_Lager`, `T2G_Gehaeuse`, registered in `T2GCommand.py` and
listed in the toolbar plus the *Konstruktion* submenu (`InitGui.py`). They share
`_MakroCommand`, which puts `Tools/` on `sys.path`, shows the mask, builds and
logs into the panel. Deliberately **not** threaded: the mask is modal and the
build takes seconds, so a worker would only risk creating geometry off the GUI
thread. The `.FCMacro` files stay — they are what works in a FreeCAD without
this workbench.

### The crank-drive generator: interfaces, not coordinates

`Skills/Verbrennungsmotor/` — one script per part, in four layers, each with
its own `selbsttest()` so a breakage names its own level:

```
Verbrennungsmotor  the skill entry: T2G_SKILL + build(params)
kt_schnittstelle   Punkt / Bauteil / andocke / richte / pruefe_paarung
kt_bauformen       R2…V12: pin angles, firing orders (tables, not formulas)
kt_kinematik       slider-crank, cam lift, block height, bank offset — maths only
kt_auslegung       THE table of shared dimensions (see below)
  ↓
kt_kolben  kt_pleuel  kt_kurbelwelle  kt_einlassventil  kt_auslassventil
kt_ventilfeder  kt_stoessel  kt_nockenwelle  kt_steuertrieb   — one part each
(kt_ventil is the shared blank of the two valves, not a part of the engine)
  ↓
kt_kurbeltrieb     crankshaft + rods + pistons
kt_ventiltrieb     valves, springs, tappets, camshafts, timing drive
  ↓
kt_motor           kennwerte / baue / pruefe, plus the gearbox on the flange
```

`kt_motor.py` computes and draws nothing itself: it fixes the design figures,
calls the two assemblies and measures the result. That split is what lets
`kt_kinematik.selbsttest()` check the slider-crank against known values (TDC 0,
BDC 2·r, full cam lift at 180°) without building a single solid.

**A skill may be a folder of many files.** `load_skill_file()` builds the
namespace with `_sibling_import(skill_dir)`, which admits `math`, `Part`,
`FreeCAD` *and* any `.py` sitting next to the skill's own entry file. Say
what that widens: a sibling imported this way runs with the normal builtins,
so a multi-file skill is trusted code like the add-on itself. It is not a new
hole on the LLM path — `create_skill()` writes a single file and can never
put a sibling beside it. `T2GCommand._MakroCommand.SKILL_PFADE` lists the
folders that also go on `sys.path` for the workbench commands.

**`kt_auslegung` is the one place a shared dimension lives.** The piston pin
diameter appears in the piston *and* in the small rod eye; the crank pin in
the crankshaft *and* in the big eye; the crank nose in the crankshaft *and*
in the sprocket. While each script carried its own default, it fitted at
86 mm bore by coincidence and nowhere else. `auslegen(bohrung, hub, bauform)`
derives every shared dimension from the bore (stroke for the rod length), and
`kt_motor` hands the same entry to both sides. At 86 mm it reproduces exactly
the values this generator was measured with (pin 22, crank pin 48, main
bearing 54, compression height 32) — the gain is that they now scale.

Its `pruefe()` found two real errors the moment it existed, both invisible at
86 mm: the inline crank pin was a fixed 26 mm while a 120 mm-bore rod is
30.7 mm wide, and the piston's slot for the small eye was a fixed 17 mm while
the eye follows the rod width. Anything overriding an entry must pass a real
value — `0.0` means "not given", and a blunt `update()` once wrote a pin
diameter of zero into the table.

**Intake and exhaust valve are two different parts**, and not only in size.
The exhaust valve is the hot one: smaller head (0.31·D against 0.36·D),
*thicker* stem (0.080·D against 0.070·D — measured against the bore, since
measuring against its own smaller head would invert the comparison), a tulip
transition instead of a straight cone, and a closed, sodium-filled hollow
stem. That cavity is a second shell inside one solid, and `removeSplitter()`
leaves it intact (measured: 1 solid, 2 shells, 6832 against 9050 mm³). The
chain stays *one* part although it is seventy rollers — its links are all
alike and its promise is the path, not the link.

Because the two stems differ, the valve train builds **one tappet pattern per
valve type**: with a single pattern the pairing check correctly reported
"Kennmass 6.9 gegen 6.0 mm".

**The bank angle is free.** `daten(bauform, bankwinkel)` overrides the table
value — a V6 exists at 60°, 90° and 55° — and it carries all the way through,
because the split-pin offset is `|720/z − bank|`: a 90° V6 gets 30°, a 60° V6
gets 60°, and V8/90, V10/72, V12/60 need none because their bank angle
equals their firing interval.

Sweeping all ten layouts × 2/4 valves × chain/gear × bank angle 60…120° ×
valve angle 0…28° × bore 70…120 mm found four more of the same kind — two
places computing one dimension differently, invisible at the default size:

- **The crankshaft ignored the cylinder spacing.** Its pin pitch was
  `hauptlager_b + 2·wange_t + hubzapfen_b` — 88 mm at 86 mm bore, where the
  piston is 85.9 mm wide, so it fitted by 2 mm. At 100 mm bore the pitch is
  91.6 mm and the piston 99.9: pistons 2 and 3 overlapped by 4.6 %, at
  120 mm by 14 %. The crank now stretches its main journals to hold the
  given spacing and refuses a spacing below its own minimum; `kt_auslegung`
  raises the spacing to that minimum, which is why a V8 at 86 mm bore now
  spaces its cylinders 110 mm apart, not 101.5 — two rods share one pin.
- **The chain pitch must suit the head.** A 40-tooth 3/8" cam sprocket is
  121 mm across. At 12° valve angle the two camshafts of an R4 stand 118 mm
  apart, at 6° only 78, at 0° only 37 — the sprockets overlapped by 51.9 %.
  `teilung_fuer(z, abstand)` picks the largest standard pitch (12.7 … 4.762)
  whose root circle still fits, and the roller diameter follows the pitch. At
  0° nothing fits, and that is the truth: a DOHC head with parallel valves
  cannot have one chain round both cams. It says so instead of building
  interpenetrating wheels.
- **Valve pockets must follow the valve angle**: a tilted valve's head walks
  `lift·sin(angle)` sideways, and at 28° it ran into the piston beside its
  own pocket (3.7 %).
- **One tappet pattern for two stem diameters** — see above.

### Design research, and what it changed

`Skills/Verbrennungsmotor/Gestaltung/*.md` holds one file per part: what
determines its shape, the published design ratios with their sources, what
the generator does today, and what is still open. The numbers are not
invented — the piston table is MAHLE's *Kolben-Gestaltungsrichtlinien*, the
con-rod I-section is the classic `B = 4t, H = 5t`, the crankpin overlap is
`(main Ø + pin Ø − stroke)/2`, the sprocket pitch circle is `p/sin(π/z)`
checked against a DIN 8187 catalogue value.

Reading them against the code found four dimensions that were simply wrong
at any bore, not just at the extremes:

- The piston's **overall length** was 0.93·D — Diesel territory. A four-stroke
  Otto piston is 0.6–0.7; it is now 0.652. The old value is what made the
  crank web graze the skirt at 70 mm bore.
- **Fire land** was the same value as the crown thickness, and the **first
  ring land** was twice the groove height (0.023·D against a required
  0.040–0.055). Both are now their own dimensions.
- The **small rod eye** was `0.75 · rod width`, which put the piston's boss
  spacing at 0.198·D, just under the 0.20 minimum. It is now measured
  against the bore like everything else.
- The **tappet diameter** came from a ratio to the bore. It actually follows
  from the cam: on a flat follower the contact point walks by `max|dh/dφ|`,
  so the bucket needs `2·` that. For the cosine lobe this is
  `lift·π/(2·flank)` in closed form — 15.0 mm at 10 mm lift and a 60° flank,
  so a 30 mm minimum bucket. `kt_nockenwelle.auswanderung()` computes it
  numerically and the selftest checks it against the closed form.

**Pin offset (Desachsierung) only works together with the kinematics.** The
pin sits off-centre in the piston, so it has to sit off the cylinder axis by
the same amount for the piston itself to run on that axis.
`kt_kinematik.pleuelrichtung()` therefore takes a support point for the line.
Without it the whole piston walked off the bank axis (measured −128.0 | 129.1
instead of |y| = |z|).

**A measured limit, not a bug**: at a 120° bank angle the cylinder axis is
60° off vertical and the inlet valve another 12° inward, so its head sits
96 mm beside the piston centre and dips into the piston *rim* — 25.8 %, and
no valve pocket can cover that. Same for a V10 at 90° (its table value is
72°). Every production bank angle is clean. Flipping the pocket tilt was
tried and made the 28° case worse, so the sign is right; this is the layout,
not the construction.

`Beispiele/motoren_bauen.py` builds all 66 variants and saves each as its own
`.FCStd` named after its design (`V8_86x86_4V_kette_bank90.FCStd`), with a
report next to them. It runs at import time and writes its report to a file,
because FreeCADCmd neither guarantees `__name__ == "__main__"` nor shows
stdout — with a guard around it, nothing happened and nothing said why.

The point of the whole thing is `kt_schnittstelle.py`: every part returns its
bodies **and** its connection points (position, axis, kind, size), and the
assembly docks them instead of computing coordinates. `andocke()` moves bodies
and points together, which is why the interfaces still hold afterwards, and
`pruefe_paarung()` measures that two points really coincide. `richte()` docks
and *then* turns the part about its connection until its other end points
where it belongs — that is how the rod ends up slanted and the piston square.

`kt_bauformen.py` holds the engine knowledge for R2…V12. Crank pin angles and
firing orders are **tables, not formulas**: there is no consistent rule (an I6
is mirror-symmetric for balance, a flat-plane V8 is deliberately uneven at
0-180-180-0, a cross-plane one spans two planes), and deriving the firing order
from the crank gave 1-4-2-3 for an I4 instead of the usual 1-3-4-2 — correctly
computed, but nobody builds it that way. Only the split-pin offset is derived
(`|720/z − bank|`), and the 90° V6 cross-check returns the known 30°.

**An interface check is not enough on its own.** The crank pins were declared
with axis `(0,1,0)` while the pins run along X. The con-rod docked sideways and
lay in the crankshaft plane — 62 mm along the shaft instead of 22 — and the
pairing check said nothing, because both sides were consistently wrong. Only
the interference measurement caught it. The crankshaft selftest now checks the
axis.

Two findings were not model errors but engine design, and both are worth
keeping in mind when something looks like interference:
- Piston at TDC with the inlet valve fully open, 51.7 % interference. That is
  exactly why **valve timing spread** exists — the lobe centre sits ~110° after
  TDC, not at TDC.
- After that, 19.7 % between piston and exhaust valve: **valve overlap** at TDC.
  That is what **valve pockets** are for. With them, 1.1 %.

Three silent arithmetic traps: `Vector.multiply()` scales **in place** (the
valves flew off in powers of ten — 2e5, 1.8e8, 1.65e11); the cam pushes when
its tip points **down**, so the lift was 180° out; and for a **flat follower**
the lift is the largest projection of the lobe profile onto the follower
direction, not the radial distance — the contact point walks sideways.

The engine and the gearbox share one axis in the standard orientation, so
`mit_getriebe=True` needs only a translation: the R4 ends at x = 400 and the
gearbox starts at x = 400.

**The gearbox is sized from the engine, not fixed.** It used to get a 20 mm
input shaft and module 2 whatever stood in front of it — a coincidence at two
litres and wrong everywhere else. What sizes a gearbox is torque, and torque
goes with displacement, so a shaft designed for torsion needs
`d ∝ T^(1/3)`: `getriebe_auslegung()` takes `20 mm · (V_H / 2000 cm³)^(1/3)`,
puts the module at a tenth of that rounded to DIN 780, and the face width at
six modules. It is a rule of thumb and says so — it replaces no tooth-root
calculation, it only stops a big engine getting a toy gearbox.

Scaling the shaft alone was not enough: the **centre distance** stayed at a
fixed 48 mm, which is small even for the two-litre reference (a passenger-car
manual is 70–75). It is now `3.6 · shaft`, so 72 mm at two litres and 103.5
at six, and the tooth sum follows as `2a/m` — that is what actually makes the
gears big. Wall thickness, bolt size and bearing series follow the shaft too.

And that was still not enough, because **what makes a gearbox long is not the
gear but what sits between the gears.** Face width went from `6 · module` to
`8 · module` (vehicle practice is 8–10; six is the lower bound), and the gap
between gear pairs from a fixed 6 mm to `1.8 · face width` — that gap is
where the **synchroniser** lives, it is not clearance. One gear step was
24 mm and the whole six-speed 223 mm against a 728 mm engine; it is now 67 mm
per step and 482 mm overall, two thirds of the engine. `pruefe()` measures
the ratio.

Two things that only showed once the gearbox got real size:

- **The countershaft was beside the input shaft, not perpendicular to it.**
  The gearbox is built with its second shaft at `+Y`, and at a V engine that
  is exactly where the bank stands. `_getriebe_anflanschen` now rotates the
  whole gearbox about the crank axis before translating it — rotate first,
  then move, or the input shaft itself leaves the axis. `DREHUNG` is +90°
  (countershaft above); which way round is an installation choice, so
  `pruefe()` checks only that it is *perpendicular*: `|y| < 1 mm` and
  `|z| = centre distance`.
- **The whole layout was wrong for a longitudinal engine.** It had two
  parallel shafts and one gear pair per gear, so the output came out
  sideways — that is the *transaxle* of a transverse front-wheel drive, where
  the output goes to the differential anyway. A longitudinal engine needs the
  output back on the crank axis, and only the **countershaft gearbox**
  (Vorgelegegetriebe) does that: input shaft and main shaft on **one** axis,
  countershaft offset. Power runs input → constant-mesh pair → countershaft →
  gear pair → main shaft, so the ratio is the **product** of two stages,
  `i = (z_VK/z_AK)·(z_loose/z_fixed)`. The frontmost sleeve bridges the shaft
  joint and couples input to main shaft directly: the **direct gear**, i = 1,
  with the countershaft idling. `getriebe_fcgear.baue` takes
  `bauart="zweiwellen"` (unchanged default) or `"vorgelege"`; the engine uses
  the latter. Two details the interference check found: the pilot spigot
  needs a **bore** in the main shaft (it sat 100 % in solid metal), and the
  input shaft's rear end carries the **coupling teeth, not a bearing seat**
  — a 30 mm seat under a 29 mm sleeve bore overlapped by 4 %, so `_welle()`
  now takes `sitze="beide|vorn|hinten"`.
- **A 12-tooth gear undercuts.** `gangpaare` had `z_min = 12`, which is
  geometrically possible but below the limit for a 20° involute without
  profile shift; the mating tip digs into the root. Measured on a 12/57
  pair: 5.9 % penetration, and none at 17/52. `getriebe_fcgear.baue` now
  takes `z_min` (still 12 by default, so the existing gearbox is unchanged)
  and the engine passes 17.

**A DOHC head has two camshafts per bank, and one chain drives both.** The
chain path (`kt_steuertrieb._kettenbahn`) therefore runs over any number of
sprockets: one external tangent between each neighbouring pair plus the wrap
arc on each wheel, with `_umlauf()` putting them in loop order and
`_bahnlaenge()` measuring the real path — the two-wheel formula stops being
true at the third wheel.

Two axis conventions bit here, both silently:
- The sprocket bores declared axis `-X` like the crank nose they sit on. Two
  `-X` axes do **not** point at each other, so `andocke()` turned the whole
  drive 180° about Z and mirrored it in y — at a V engine one bank's chain
  landed on the other bank. At `kipp = 0` (inline) it never showed.
- The camshaft tilt is `neigung − bankwinkel`, not the sum. The sum is right
  for inline engines (bank angle 0) and 90° wrong for V engines, which is why
  only those showed ~11 % tappet interference.

And a measurement trap: a camshaft's axis is **not** its bounding-box centre —
the lobes stick out on one side and move it 5.5 mm. Take the drive journal at
the −x end, which is a plain cylinder on the axis.

### Clutch and planetary gear

`Tools/kupplung.py` and `Tools/planetengetriebe.py`, with their design notes
in `Tools/Gestaltung/*.md`. Both are sized from formulas, not from taste.

**The clutch.** `M = z·μ·F_N·r_m` with `r_m = (D_a + D_i)/4`, and `z` is the
number of **friction faces** — one disc rubs on *both* sides, so z = 2. Clamp
load goes with area (∝ D²) and the radius with D, so torque goes with **D³**
and the lining diameter with the cube root of it. The same relation settles
the disc count: a second disc doubles z and therefore shrinks the lining by
`2^(1/3) = 0.794`. That is exactly why big engines get two discs instead of
one huge one — measured on the 6-litre V12: 310 mm on one disc against
**246 mm on two**, which is the realistic size. `auslegen()` switches by
itself above 280 mm.

Two pieces of geometry that are obvious in the real part and only show up
when you measure the model: the **damper springs need punched windows** in
the lining carrier (33 % interference without them), and the **flywheel needs
a stepped central recess** for the disc hub (20 %).

**The bell housing belongs to the gearbox.** `getriebe_fcgear` builds a
`Kupplungsglocke` in front of the housing when `glocke_l > 0`, and *extends
the input shaft by the same length* — that is what ties the drivetrain
together: the shaft runs through the bell, carries the clutch disc hubs and
pilots in the flywheel. Before that the gearbox merely stood behind the
clutch. Three dimensions had to follow, and the interference check found each
one: the flywheel's **pilot bore goes through** (a blind bore from 30 % depth
left the shaft in solid metal, 4.0 %); the **hub needs running clearance**
(2.9 % at zero fit — and it must slide axially or the clutch cannot be
released); the input shaft's **bearing seat belongs at the housing wall**,
not at the shaft nose, where the hub ran on the 30 mm shoulder; and the
crankshaft's **flywheel flange needs its spigot bore**, or the shaft nose
ends in solid crankshaft (3.3 %) — that bore is where the pilot bearing sits,
and without it the input shaft would be supported at one end only.

A bell you cannot bolt on is not a bell: it carries **two** flanges — front
to the engine block, rear to the gearbox housing — and the housing carries a
matching **end flange**, split at z = 0 like the housing itself, so each half
gets its half. All three share one bolt circle and twelve holes, and the two
middle ones sit **face to face**, not on top of each other (20 % when laid
over one another; measured now, 775 meets 775).

**The planetary gear.** Four conditions, three of them purely geometric, and
a set that breaks any one of them cannot be built:

```
Achsbedingung    z_ring = z_sun + 2·z_planet
Montagebedingung (z_sun + z_ring) / p  integer
Nachbarbedingung (z_sun + z_planet)·sin(π/p) > z_planet + 2
Willis           i₀ = −z_ring/z_sun, ring fixed → i = 1 − i₀
```

`baue()` refuses a set that violates the assembly or neighbour condition
instead of building overlapping wheels, and `vorschlag(i_soll)` searches only
among sets that hold all three — measured, it hits i = 3, 4, 5 and 6 exactly.
The planet **phase is not free**: a planet at angle φ must mesh with the sun
there, so it stands rotated by `φ·z_sun/z_planet` (measured: 119.9 / 120.0 /
120.1°). And the carrier cheeks need **bores for the planet pins** — without
them the pin sat 21 % inside solid metal, and those bores are precisely what
makes a carrier a carrier.

The ring gear is **really internally toothed** — FCGear's
`CreateInternalInvoluteGear`, the same tooth turned inside out. It used to be
a plain ring with a bore, which is exactly the part that makes a ring gear a
ring gear. Measured at z = 66, m = 2: 39 290 mm³ against 41 620 for the smooth
ring, the difference being the tooth gaps. `pruefe()` now **measures meshing
pairs** instead of skipping them, at the usual 2 % — skipped, a
mis-phased ring could never show up; measured, the planet/ring mesh comes out
at 1.0 %.

### The gearbox, completed

A countershaft gearbox is more than shafts and gears, and what was missing was
exactly what makes it *shiftable*:

- a **needle bearing under every loose gear** — the loose gear runs free on
  the main shaft whenever its gear is not engaged, so something has to carry
  it; the bore grew by `2 · 0.12 · shaft` to make room;
- **two synchroniser rings per sleeve**, which needed the sleeve to stop
  filling the whole gap: it now leaves `0.12 · gap` on each side (before,
  the rings sat inside the neighbouring gears — 37 %);
- a **shift fork per sleeve**, a **boss sliding on its own rail**, and three
  **rails on an arc** above the main shaft.

Three geometry lessons came out of it, each found by measuring:

- The fork has **no build axis of its own** — it belongs where the sleeve is.
  Built along Z like the gears and rotated with them, its arm pointed
  sideways and the rail was somewhere else. It is now built along X directly.
- The fork arms must run **radially** to their own rail. An arm that goes up
  and then across crosses the neighbouring rails (11–13 %). Three rails on an
  arc, three radial arms, no crossings.
- Above the biggest gear there is **no room in the gear chamber** — the gear
  reaches to `r_max` and the rails lie beyond it. That is what a **shift dome**
  is for, and it is fused onto the upper housing half. Its box corners still
  reached into the arc the forks swing on, so a cylindrical relief cut about
  the main-shaft axis clears them.

And a scheduling trap worth remembering: the dome is fused onto
`Gehaeuse Oberteil`, but the housing is created *later* in the function, so
the `for … if label == …: break` found nothing and the dome vanished without
a word. Anything that modifies a part must run after that part exists — the
measurement did not change by one percent, which is what gave it away.

**The flanges belong to the housing, not beside it.** The end flange is fused
into each half, so the gearbox is exactly three housing parts: bell housing,
upper half, lower half. A flange that is its own part could not be bolted to
anything.

### A film of the assembly

`Beispiele/film_motor.py` builds the drivetrain and photographs it part group
by part group, then ffmpeg turns the frames into an MP4. It must run in the
**GUI** — `saveImage` needs an OpenGL context, so FreeCADCmd cannot do it.

Two things that decide whether it is watchable: `fitAll()` after **every**
step (otherwise the drivetrain grows out of frame — the first cut had the
gearbox half outside), and the **housings last**. The order is the order of
assembly, and the point of the film is to see what is inside before it is
covered up.

### Fits, and why they matter to the checks

Nothing in an assembly may be zero-clearance, because a zero fit is
indistinguishable from a real error. `lager` and `zahnrad` therefore take a
`spiel` parameter (default 0.1 mm): the bore comes out `2 × spiel` larger than
the nominal shaft, and the bearing's raceway `spiel` wider than its balls. Before
that, every shaft reported 3–5 % overlap with its own gears and bearings.

`lager` is a real deep-groove ball bearing now — inner ring, outer ring and
`kugeln` balls, **as separate solids**. Skills may return several solids, so
anything filtering by part label must match the prefix `T2G <name> [`, not one
exact label (`_kollisionen(nur=…)`, `_add_skill_shapes`, `_ausdehnung(ohne=…)`).

`zahnrad` has a `phase` parameter (degrees) that turns the teeth without moving
the bore. Two meshing gears need the driven one offset by **half a tooth pitch**
(`180 / z2`); measured on 12/36 teeth at 48 mm centre distance, the penetration
drops from 149.7 mm³ (5.6 %) to 0.6 mm³ (0.0 %). Without it, correct gearboxes
trip the collision check.

The reference gearbox checks penetration relatively (2 % of the smaller part,
matching `_KOLL_TOL`), not absolutely — and that check immediately found a real
error that had been in the hand-built reference all along: the bearings sat on
the 15 mm shank instead of the 12 mm stepped seat, penetrating it by 419 mm³.
Nobody had measured, because bore and seat were exactly equal.

### Parameters and the knowledge graph

`ProjectParam` is one agreed value; the `maske` block is how the model asks for
them and `Project.answer_mask()` how the answers come back. Values out of range
are reported *and* stored — losing what a user typed is worse than an unchecked
value.

`KnowledgeGraph` edges point downstream ("if the source changes, the target must
follow"): `p:ventil_d_ein --nutzt--> s:brennraum`. `impact()` is a BFS over that,
`mark_affected()` flips the affected skills to `zu pruefen`. `passt_an` is stored
in both directions.

`is_count_unit()` in `T2GCore` is the single definition of "this is a count"
(int) versus a measure (float) — `T2GProject.param_from_row` defers to it.
Having two lists made `Stück` an int in one module and a float in the other.

### Projects and the pairwise comparison

`Project` owns `projekt.json` and renders `agent.d/*.md` from it — the markdown is
**output, never the source of truth**; editing it by hand is lost on the next
`write_agent_d()`. `Project.load()` resets `path` to where the project was actually
found, so a moved project keeps working.

`PairwiseMatrix` stores only the upper triangle (`{"i,j": a_ij}`); `a_ji` is the
reciprocal by construction. Weights are the normalised row geometric means,
`consistency_ratio()` is CI/RI against Saaty's random index. Two properties worth
knowing before "fixing" anything:

- For n = 3 a single bad judgement shifts **all three** pairs by the same factor, so
  `worst_pairs()` cannot name a culprit; from n = 4 it can. Both cases are tested.
- `set_criteria()` keeps judgements whose two criteria both survive, matched by name,
  so adding a criterion does not throw away the comparisons already made.

`match_skills()` is deliberately strict about prefixes: plain `SequenceMatcher` rates
`auslasskanal`/`einlasskanal` at 0.75, which once copied the inlet-duct generator and
labelled it as the outlet duct. `name_similarity()` multiplies by 0.7 when the first
three characters differ and neither name contains the other; only `SkillMatch.is_match`
(score ≥ 0.9) may be copied automatically.

### Toolbar command line

`ensure_toolbar_input()` adds a `QLineEdit` to the `T2G` toolbar; FreeCAD builds
toolbars from command names only, so the widget is added afterwards — and again
on every workbench switch, which is why `T2GWorkbench.Activated()` re-runs it
through a `QTimer` (0 ms and 600 ms; the toolbar does not exist yet at 0 ms on a
cold start). `run_toolbar_input()` opens the dock, switches to the Dialog tab and
calls `_chat_send()`, so the answer lands in the panel.

### Sandbox boundary (say it honestly)

The import allow-list plus a reduced `__builtins__` (no `open`/`eval`/`exec`/
`getattr`/`globals`/`vars`) stops accidents, not a hostile model: in CPython any
exposed function leaks its module globals through attribute paths, and no
allow-list fixes that. The docs say so; do not tighten the wording into a
promise the code cannot keep. `hasattr`, `round`, `sum`, `sorted`, `any`, `all`,
`isinstance` are deliberately present — leaving them out cost the agent whole
steps on `name 'hasattr' is not defined`.

### Web research

Opt-in, and off by default. `wikipedia_search()` uses the MediaWiki API;
`web_search()` uses DuckDuckGo's lite endpoint (no key; the target sits in the
`uddg` parameter). `web_fetch()` accepts only http/https, caps the body, routes
Wikipedia URLs through the API, and strips navigation chrome
(`html_to_text(article_only=True)`) — without that, half the model's context was
"Jetzt spenden / Hauptmenü". Every source is shown in the panel. Tests never need
the network unless `T2G_TEST_NET=1`.

### Backends: one call path

`call_model_verbose(prompt, system, cfg, pi)` → `(answer, thinking)` is the only
place that knows how a backend is invoked. Before it existed the pi path
hard-coded `--provider ollama` and the default model, so a configured API was
silently ignored — `cfg.provider`, `cfg.model` and `--api-key` are now threaded
through `run_backend`. `PI_OFFLINE` is only set for the local ollama provider.

`APIConfig.thinking` (default `"low"`) is mapped per backend: `think` for Ollama
(False / "low" / "medium" / "high"), `--thinking` for pi, `reasoning_effort` for
OpenAI-compatible services — and only sent when explicitly chosen, since not
every server accepts the field. Measured on qwen-gross, one agent step: off
1.2 s / low 2.0 s / high 3.9 s / server default 8.4 s. Short agent steps use the
panel setting; `with_thinking(cfg, "high")` overrides it for skill, tool and
sweep code, and `"off"` for transcript compression. Keep that split — turning
the global knob down must not make generated geometry worse.

Reasoning comes from three different places and all three are read:
`message.thinking` (Ollama), `reasoning_content`/`reasoning` (OpenAI-compatible
services), and `thinking` blocks in pi's NDJSON (`extract_thinking`), plus
`<think>` tags (`split_thinking`).

### Show the work, never a frozen panel

`call_model_verbose(..., on_progress=cb)` streams: `_stream_api_call` reads
Ollama's and the OpenAI-style chunked responses and reports every piece, which
`_TextWorker.progress` forwards (throttled to 4/s) to `_on_stream`. The status
line then shows "denkt: …" / "schreibt: …" as the answer forms.

Measured on this machine, same prompt and model: **direct Ollama 14 s with the
first characters after 0.6 s; through pi over 300 s with no output at all**
(pi spawns Node and buffers everything). Hence the warning in the backend
status and the "pi arbeitet – Text kommt erst am Ende" heartbeat; pi cannot be
streamed.

When nothing has arrived after 8 s, `_note_model_loading()` checks
`ollama_loaded_models()` (`/api/ps`) and says the model is being pulled off
disk -- a cold 17 GB model really does take minutes, and that once looked like
a hang for 283 s.

`APIConfig.keep_alive` (default `"30m"`) is sent with every Ollama request.
Ollama's own default evicts a model after five minutes, which is shorter than
the gap between two steps of a long job — the model then reloads 17 GB per
call. Measured: short call 7.2 s cold versus 0.9 s warm; one skill analysis
494 s versus 18 s; a whole skill learned 116 s versus 56 s. It is a per-request
field, so no root and no systemd edit is needed; the panel exposes it under
*Modell im Speicher*.

`_CODE_THINKING` lifts the panel's thinking level by one step for code
generation instead of pinning it to "high": a plain washer took minutes at
"high" and 116 s at "medium".

### The learn queue

`_prj_learn_all` fills `_learn_queue` and `_queue_progress()` drives the
progress bar (`n von m · name · Phase`). Two things it must keep doing:
- **Continue unattended.** `_learn_analyse_done` runs `_learn_build()` when a
  queue or the agent is driving; without that the queue stopped after the
  analysis and waited for a click nobody would make.
- **Never stall silently.** Every early return in the learn path calls
  `_queue_step_failed()`, and `_queue_watchdog` gives up on an item after 20
  minutes. A stuck queue used to show "Analyse" forever with no message.

### Never block the GUI thread

Anything that touches the network or spawns a process runs in a `_CallWorker`
via `T2GPanel._spawn(fn, tag, on_done)`: model listing, connection test, Ollama
start, backend status, and the agent's `recherche` action. A pi call spawns Node
and thinks for minutes; doing that inline froze FreeCAD solid — the user reported
it as a hang.

`_spawn` also keeps every running worker in `self._workers`. Assigning a new
worker over a still-running one frees the QThread and Qt aborts the process
("QThread: Destroyed while thread is still running") — that was a hard crash,
not a warning.

### Keeping the agent out of loops

Three separate brakes, each added after a real transcript went in circles:
- `did_work` gates `fertig` — but a submitted **mask does not count**: it is the
  user's input, not the agent's action. Counting it let a purely narrated
  "Baugruppe angelegt" through with an empty document.
- `_same_question()` (difflib ≥ 0.75 on normalised text) catches the same
  question being asked again and pushes the existing answer back.
- `_MAX_REJECTIONS` (3) ends the run with a concrete suggestion instead of
  nagging nine times.
- `_agent_finish` checks `_doc_solid_count()` against `solids_at_start`: a
  summary claiming geometry with nothing built gets sent back once, with an
  instruction to build and to repair failing code.

### Backends and installing

`detect_backend(saved)` prefers local Ollama, then a saved OpenAI-compatible API,
then the pi CLI — so the add-on also works on a FreeCAD without Ollama.
`openai_models()` reads `/v1/models` and normalises whatever base URL the user
pasted (bare host, `/v1`, even a full `/chat/completions`). Settings live in
`BaseApp/Preferences/Mod/TextToGeometry`; the API key only when *Zugang merken*
is ticked (plain text, hence off by default).

`install.py` is the single source of truth for what the add-on consists of
(`FILES`/`DIRS`); `start.sh sync` and `CMakeLists.txt` follow it. It merges
`Skills/` instead of overwriting, so skills learned on the target machine
survive an update.

### Skills

`Skills/<name>/<name>.py` — the directory name, file name and `T2G_SKILL["name"]` must
match, or `SkillEngine.load_all()` skips it silently (load errors are swallowed per-skill).
The module defines a `T2G_SKILL` dict and `build(params) -> list[Part.Shape]`.

Authoritative metadata keys, as read by `load_skill_file()` and written by `create_skill()`:
`name`, `description`, **`params`** (6-tuples `(name, label, unit, default, min, max)`),
`dependencies`, **`pruefregeln`** (`"kollision"` / `"konnektivitaet"`).
`README.md` and `DOKUMENTATION.md` show `parameters` / `rules` in places — those are wrong;
follow `Skills/bruecke/bruecke.py`.

`SkillEngine.build()` returns `(shapes, validated_params, problems)`; `problems` are
advisory strings from `apply_rules()` (bounding-box overlap and connectivity), never fatal.
The Skill-Designer tab writes new skills via `create_skill()` into the same `Skills/` dir.

`validate_skill_source()` is the gate for *learned* skills: compile, exec, build with
defaults, positive volume, no ignored parameter, then the rules. Its problem strings are
fed straight back to the model for the next attempt.

A skill's parameter kind follows the type of its default, so `parse_param_lines()` makes
anything whose unit is not a count (`-`, `Stk`, …) a float — otherwise a diameter the model
proposed as `45` could never be set to 67.5.

`get_engine()` caches, so after writing a skill the directory must be re-scanned
(`_skills_engine(reload=True)`), or the new skill never shows up in the combo.

### Threading

`_SweepWorker(QtCore.QThread)` runs the sweep; the panel communicates with it only via
signals and `request_stop()`. Cancellation is cooperative — `run_sweep` checks
`should_cancel` between variants and between iterations, so a Stop never interrupts an
in-flight LLM call. Shapes must only be added to the document on the GUI thread
(`_add_results`).

## Licensing

The project is **not** open source: PolyForm Noncommercial 1.0.0 plus an
additional term forbidding military use (`LICENSE`, SPDX
`LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary`). Commits up to `8fc65f9`
were LGPL-2.1-or-later and stay that way for whoever has them.

Consequences to keep in mind: every source file carries the SPDX header, the
generators in `T2GSkills.create_skill` and `Project.write_tool` stamp it into
what they emit, and `package.xml` points at `LICENSE`. Do not pull in code
under a copyleft licence (GPL/LGPL source, not just the FreeCAD API) — it
cannot be combined with these terms. Calling the FreeCAD API is fine; copying
FreeCAD or add-on source into this tree is not.

## Gotchas

- `python3 test_skills.py` reports 2 failures (`'NoneType' object has no attribute
  'rotate'`): its `Part` stub is intentionally incomplete. That suite is only green under
  `FreeCADCmd`. `test_core.py` and `test_ext.py` must pass under plain `python3`.
- **`FreeCADCmd <script>.py` can execute the installed copy, not yours.** The
  Mod dir is on `sys.path` and `start.sh sync` copies the `test_*.py` files
  there, so a test run reported ALLE GRUEN for a section it never executed —
  the synced copy was 30 lines shorter. `test_bauen.py` puts its own directory
  first on `sys.path`; when a test's output does not match its source, check
  `~/.local/share/FreeCAD/v1-1/Mod/TextToGeometry/` first.
- Never write `open(p, "w").write(open(p).read().replace(...))` — the write-mode
  open truncates the file *before* the read runs, and it silently becomes empty.
  That emptied this file once, and the empty version was committed.
- `README.md`'s file table predates the dockable panel and the five commands; treat the
  source as the reference.
- Generated CSV/txt artifacts (`sweep_results.csv`, `sweep_result.txt`, …) are gitignored.
- Learned skills are written next to the **installed** workbench, not into this repo.
- `agent.d/` is generated. Edits belong in `projekt.json` (i.e. in the panel fields),
  not in the markdown.
- A 27B model needs 3–4 minutes for a full parametric part. `APIConfig.timeout_s`
  defaults to 900 s and the Backend tab exposes it; anything near 180 s will time out
  mid-generation.
- The skill sandbox guards imports through `__builtins__["__import__"]` — putting
  `__import__` in the globals dict (as the code used to) has no effect whatsoever.
  The tool sandbox (`T2GProject.validate_tool_source`) does the same, and runs the
  model's own `selbsttest()`; detect its functions by `hasattr(v, "__code__")`,
  since `__module__` follows the namespace and is never None.
- Learned/refined skills keep a timestamped `.py.bak` next to them
  (`T2GSkills.update_skill`); `load_all()` ignores those.
