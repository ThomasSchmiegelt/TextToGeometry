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
FreeCADCmd test_bauen.py    # 30 checks: placement, replace, collisions, bearing, tools
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
