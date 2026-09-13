# SPDX-License-Identifier: LGPL-2.1-or-later

"""TextToGeometry core.

Non-GUI backend and code-extraction / execution helpers.
Uses only the Python standard library so it can be imported and exercised
outside of FreeCAD (unit tests, CI, FreeCADCmd).

Parts 1-5: single-prompt generation pipeline (backend, sandbox, exec).
Parts 6-10: variant sweeps - tables (csv/xlsx/spreadsheet/paste), targets
and measurements, feedback-controlled loop, CSV export.
"""

from __future__ import annotations

import base64
import csv
import json
import math
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
import textwrap
import urllib.request
import urllib.error
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

# A generator that, given a prompt, returns (code, shapes). The sweep engine
# receives one of these.  GUI code passes T2GCore._generate_once.
GenerateFn = Callable[[str], "tuple[str, object]"]

# ---------------------------------------------------------------------------
# Part 1: shared helpers (unchanged API)
# ---------------------------------------------------------------------------

T2G_MASS_DENSITY_DEFAULT = 7850.0  # kg/m^3 (steel), fallback


# ---------------------------------------------------------------------------
# Part 2: backend (unchanged API)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a precise 3D CAD geometry engineer for FreeCAD.
The user describes a solid object in natural language. You translate it into a short FreeCAD/Python script that builds it with the Part API.

STRICT OUTPUT RULES
- Reply with exactly one fenced ```python code block and nothing else. No prose, no explanation, no second block.
- The code must be self-contained, deterministic, and must NOT create a document, show anything, print, or read any input.
- The code must end with a single top-level statement:
    result = [<shape1>, <shape2>, ...]
  where every entry is a Part.Shape (a solid). A single-object answer is the one-element list [shape].
- Do not assign to any other name called `result`.

ALLOWED IMPORTS (ONLY these — any other import line is FORBIDDEN and will crash)
- import Part
- import math
- import FreeCAD          # for FreeCAD.Vector / FreeCAD.Placement
- import Units            # for length units, e.g. Units.mm

ALLOWED BUILDING BLOCKS (prefer these, keep it simple and boolean-safe)
- Primitives: Part.makeBox, Part.makeCone, Part.makeCylinder, Part.makeSphere, Part.makeTorus, Part.makeTetrahedron
- Booleans: shape.fuse(o), shape.cut(o), shape.common(o)
- Placement: shape.translate(Vector), shape.rotate(Vector, Vector, angleDeg)
- Faces and extrusion: Part.Face(Part.makePolygon([FreeCAD.Vector(...), ...])).extrude(FreeCAD.Vector(...))
- Lengths are in millimetres. Angles for rotate() are degrees.
- Do NOT use Part.show, App.ActiveDocument, FreeCAD.newDocument, print, or any module outside the allowed imports.

STYLE
- 2-space indent, short local variable names (body, arm, hole, ...).
- No comments or at most one short comment per solid.
- If the request is ambiguous, pick the most standard interpretation; never ask a question.

EXAMPLES

User: "A cube 40 mm on a side"
```python
import Part

result = [Part.makeBox(40, 40, 40)]
```

User: "A hex head 16 mm across flats, 5 mm tall"
```python
import Part
import math
import FreeCAD

r = 8.0 / math.cos(math.pi / 6)
pts = [FreeCAD.Vector(r * math.cos(2 * math.pi * i / 6), r * math.sin(2 * math.pi * i / 6), 0) for i in range(6)]
pts.append(pts[0])
face = Part.Face(Part.makePolygon(pts))
result = [face.extrude(FreeCAD.Vector(0, 0, 5))]
```

User: "A 20 mm cube with a centered 8 mm through-hole along the Z axis"
```python
import Part
import FreeCAD

box = Part.makeBox(20, 20, 20)
hole = Part.makeCylinder(4, 20, FreeCAD.Vector(10, 10, 0))
result = [box.cut(hole)]
```

Now respond to the user's request with only the Python code block.
"""

# Feedback prompt (used when a variant missed a target).
FEEDBACK_SECTION = """\

--- VARIANT {row_idx} (iteration {itr}/{max_itr}) ---
Targets (mm, g):
{targets_block}

Current state (measured from previous code):
  volume:      {volume_mm} mm^3
  mass:        {mass_g} g
  x range:     {x_lo} .. {x_hi} mm
  y range:     {y_lo} .. {y_hi} mm
  z range:     {z_lo} .. {z_hi} mm
Criteria feedback (previous code):
{feedback_lines}
"""


# ---------------------------------------------------------------------------
# Part 2b: external LLM API (OpenAI-compatible / Ollama endpoints)
# ---------------------------------------------------------------------------

@dataclass
class APIConfig:
    """Settings for calling an LLM directly over HTTP (bypasses the `pi` CLI).

    Compatible with every OpenAI-style endpoint (OpenAI, OpenRouter,
    LM Studio, vLLM, llama.cpp server, ...) and with Ollama's native
    ``/api/chat`` endpoint when ``kind="ollama"``.
    """

    kind: str = "openai"            # "openai" | "ollama" | "pi"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen-gross:latest"
    api_key: str = ""
    #: For kind="pi": which provider the CLI should talk to (ollama, openai,
    #: anthropic, google, …). pi has no base URL of its own -- it knows its
    #: providers -- but it does take --api-key.
    provider: str = "ollama"
    #: How hard the model should think. Measured on qwen-gross for one agent
    #: step: off 1.2 s, low 2.0 s, high 3.9 s -- so short steps get "low" and
    #: only geometry code is worth the wait.
    thinking: str = "low"
    temperature: float = 0.2
    max_tokens: int = 8192
    # A 27B model writing a full parametric part needs minutes, not seconds.
    timeout_s: int = 900

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "base_url": self.base_url,
            "model": self.model, "api_key": self.api_key,
            "provider": self.provider, "thinking": self.thinking,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens, "timeout_s": self.timeout_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "APIConfig":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in (d or {}).items() if k in valid})

    def describe(self) -> str:
        key = self.api_key
        masked = (key[:4] + "…" + key[-2:]) if len(key) > 8 else ("***" if key else "")
        return (f"{self.kind} {self.base_url} model={self.model} key={masked or '-'}")


#: What the panel offers; "auto" sends nothing and leaves it to the server.
THINKING_LEVELS = ("auto", "off", "minimal", "low", "medium", "high")


def _thinking_for_ollama(level: str):
    """Ollama's ``think``: False, True or a level string. None = send nothing."""
    lvl = (level or "auto").strip().lower()
    if lvl in ("", "auto"):
        return None
    if lvl in ("off", "aus", "false", "none"):
        return False
    if lvl in ("minimal", "low", "medium", "high"):
        return lvl if lvl != "minimal" else "low"
    return True


def _thinking_for_pi(level: str) -> str:
    """pi's --thinking: off, minimal, low, medium, high, xhigh, max."""
    lvl = (level or "auto").strip().lower()
    if lvl in ("", "auto"):
        return ""
    if lvl in ("aus", "false", "none"):
        return "off"
    return lvl if lvl in ("off", "minimal", "low", "medium", "high",
                          "xhigh", "max") else ""


def _t2g_api_call(cfg: APIConfig, system_prompt: str, user_prompt: str,
                  thoughts: list | None = None,
                  thinking: str | None = None) -> str:
    """Call the HTTP backend. Reasoning, if the model sends any, is appended
    to ``thoughts`` -- Ollama returns it in ``message.thinking`` and several
    OpenAI-compatible services in ``reasoning_content``; ignoring those fields
    is why the panel showed no thinking at all."""
    if cfg.kind == "ollama":
        base = cfg.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        url = base + "/api/chat"
        body = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": cfg.temperature},
        }
        think = _thinking_for_ollama(
            cfg.thinking if thinking is None else thinking)
        if think is not None:
            body["think"] = think
        headers = {"Content-Type": "application/json"}
    else:
        url = cfg.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = url + "/chat/completions"
        body = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": cfg.temperature,
        }
        if cfg.max_tokens > 0:
            body["max_tokens"] = cfg.max_tokens
        effort = (cfg.thinking if thinking is None else thinking or "").lower()
        if effort in ("low", "medium", "high"):
            # only sent when explicitly chosen: not every OpenAI-compatible
            # server accepts the field
            body["reasoning_effort"] = effort
        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = "Bearer " + cfg.api_key

    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            pass
        raise BackendError(f"API failed: HTTP {e.code} from {url} {detail}", "", int(e.code))
    except urllib.error.URLError as e:
        raise BackendError(f"API unreachable: {url} ({e.reason})", "", -1)

    if cfg.kind == "ollama":
        msg = payload.get("message") or {}
        text = msg.get("content", "")
        denken = (msg.get("thinking") or "").strip()
    else:
        choices = payload.get("choices") or []
        if not choices:
            raise T2GError(f"API returned no choices: {str(payload)[:300]}")
        message = choices[0].get("message") or {}
        text = message.get("content", "")
        denken = (message.get("reasoning_content")
                  or message.get("reasoning") or "").strip()
    if denken and thoughts is not None:
        thoughts.append(denken)
    if not text or not text.strip():
        raise T2GError("API returned an empty message.")
    return text


class _CodeStream:
    """Wraps a plain code string as the pi NDJSON stream structure so
    ``extract_code_block`` / ``_strip_fenced_python`` work unchanged."""

    def __init__(self, code: str) -> None:
        self._doc = json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "```python\n" + code + "\n```"}],
            },
        })


def run_api(prompt: str, *, cfg: APIConfig | None = None,
            system_prompt: str = SYSTEM_PROMPT) -> str:
    """Call an external LLM API (code block is extracted by callers
    through the standard ``extract_code_block`` path)."""
    if not (prompt or "").strip():
        raise BackendError("Empty prompt.")
    cfg = cfg or APIConfig()
    text = _t2g_api_call(cfg, system_prompt, prompt)
    code = _strip_fenced_python(text)
    return json.dumps({
        "type": "message_end",
        "message": {"role": "assistant",
                    "content": [{"type": "text",
                                 "text": "```python\n" + code + "\n```"}]},
    })


def generate_via_api(prompt: str, *, cfg: APIConfig | None = None) -> tuple[str, list]:
    """Single-prompt generation through the external API (code, shapes)."""
    raw = run_api(prompt, cfg=cfg)
    code = extract_code_block(raw)
    shapes = exec_code_in_sandbox(code)
    return code, shapes


# ---------------------------------------------------------------------------
# Part 3: Target (dataclass, check, prompt)
# ---------------------------------------------------------------------------

@dataclass
class Target:
    """One measurable goal, either a mass/volume/dimension constraint
    (with tolerance) or a free-text criterion the LLM should respect.

    kind:   "mass" | "volume" | "dim_x" | "dim_y" | "dim_z" | "text"
    mode:   "==" | "<=" | ">="     (ignored for "text")
    value:  number (mm / g depending on kind) or text
    tol:    absolute tolerance for "=="; relative tolerance otherwise
    """

    kind: str
    mode: str = ""
    value: object = None
    tol: float | None = None
    note: str = ""

    # -- convenience constructors --------------------------------------------

    @staticmethod
    def mass(value_g: float, tol: float | None = None) -> "Target":
        return Target("mass", "==", value_g, tol)

    @staticmethod
    def volume(value_mm3: float, tol: float | None = None) -> "Target":
        return Target("volume", "==", value_mm3, tol)

    @staticmethod
    def dim(axis: str, value_mm: float, tol: float | None = None,
            mode: str = "==") -> "Target":
        assert axis in ("x", "y", "z"), axis
        return Target(f"dim_{axis}", mode, value_mm, tol)

    @staticmethod
    def text(text: str) -> "Target":
        return Target("text", "", text, None)

    # -- render ------------------------------------------------------------

    def render(self) -> str:
        if self.kind == "text":
            return f"[free-text criterion] {self.value!r}" + (f" ({self.note})" if self.note else "")
        unit = "g" if self.kind == "mass" else ("mm^3" if self.kind == "volume" else "mm")
        label = self.kind.replace("dim_", "")
        if self.mode == "==":
            s = f"{label} == {self.value:g} {unit}"
            if self.tol:
                s += f" (±{self.tol:g})"
        else:
            s = f"{label} {self.mode} {self.value:g} {unit}"
        if self.note:
            s += f" ({self.note})"
        return s

    def check(self, measurement: "Measurement") -> tuple[bool, str]:
        """Return (satisfied, human explanation) for a given measurement."""
        m = measurement
        if self.kind == "text":
            return True, "free-text (LLM responsibility, not measured here)"

        if self.kind == "mass":
            v = m.mass_g
            unit = "g"
        elif self.kind == "volume":
            v = m.volume_mm3
            unit = "mm^3"
        elif self.kind in ("dim_x", "dim_y", "dim_z"):
            v = getattr(m, self.kind.replace("dim_", "") + "_range")[1] - getattr(m, self.kind.replace("dim_", "") + "_range")[0]
            unit = "mm"
        else:
            raise T2GError(f"Unknown target kind: {self.kind!r}")

        if self.mode == "==":
            limit = self.tol if self.tol is not None else 0.05 * abs(self.value)
            ok = abs(v - self.value) <= limit
            msg = f"{self.kind}: {v:g} vs {self.value:g} (tol {limit:g}) -> {'ok' if ok else 'miss'}"
        elif self.mode == "<=":
            ok = v <= self.value
            msg = f"{self.kind}: {v:g} <= {self.value:g} -> {'ok' if ok else 'miss'}"
        elif self.mode == ">=":
            ok = v >= self.value
            msg = f"{self.kind}: {v:g} >= {self.value:g} -> {'ok' if ok else 'miss'}"
        else:
            raise T2GError(f"Unknown target mode: {self.mode!r}")
        return ok, msg


# ---------------------------------------------------------------------------
# Part 4: Measurement
# ---------------------------------------------------------------------------

@dataclass
class Measurement:
    volume_mm3: float
    mass_g: float
    x_range: tuple
    y_range: tuple
    z_range: tuple
    n_solids: int
    n_faces: int

    @property
    def x_size(self) -> float:
        return self.x_range[1] - self.x_range[0]

    @property
    def y_size(self) -> float:
        return self.y_range[1] - self.y_range[0]

    @property
    def z_size(self) -> float:
        return self.z_range[1] - self.z_range[0]


def measure_shape(shape, density_kg_m3: float = T2G_MASS_DENSITY_DEFAULT) -> Measurement:
    """Measure a Part.Shape (or a list/Compound of shapes).

    Returns a :class:`Measurement` with volume, mass, bounding box and counts.
    """
    if shape is None:
        raise T2GError("Cannot measure None.")
    if isinstance(shape, (list, tuple)):
        shape = list(shape)
        if not shape:
            raise T2GError("Cannot measure an empty list of shapes.")
        if len(shape) == 1:
            shape = shape[0]
        else:
            import Part
            shape = Part.makeCompound(shape)
    b = shape.BoundBox
    vol = float(shape.Volume)
    # mm^3 -> m^3 (1e-9); kg/m^3 -> g/mm^3 via *1e-9 kg -> *1000 g
    mass = vol * 1e-9 * density_kg_m3 * 1000
    solids = len(shape.Solids) if hasattr(shape, "Solids") else 1
    faces = len(shape.Faces) if hasattr(shape, "Faces") else 0
    return Measurement(
        volume_mm3=vol,
        mass_g=mass,
        x_range=(float(b.XMin), float(b.XMax)),
        y_range=(float(b.YMin), float(b.YMax)),
        z_range=(float(b.ZMin), float(b.ZMax)),
        n_solids=solids,
        n_faces=faces,
    )


# ---------------------------------------------------------------------------
# Part 5: Prompt builders
# ---------------------------------------------------------------------------

def build_prompt(base_prompt: str,
                 row: dict,
                 targets: list[Target],
                 density_kg_m3: float,
                 itr: int = 1,
                 max_itr: int = 1,
                 feedbacks: list[str] | None = None,
                 previous_measurement: Measurement | None = None) -> str:
    """Assemble a full prompt for one variant/iteration.

    `row`            dict from the variant table (e.g. {"laenge": 40, ...})
    `targets`        list[Target]
    `density_kg_m3`  material density for mass targets
    `itr`, `max_itr` iteration index / total (for feedback)
    `feedbacks`      list of human-readable reasons from the previous attempt
    """
    if not base_prompt:
        raise T2GError("base_prompt is empty.")
    out = [base_prompt.strip()]
    if row:
        out.append("\n--- VARIATION DATA (apply all values below) ---")
        for k, v in row.items():
            out.append(f"{k} = {v!r}")
    out.append("\n--- TARGETS ---")
    for t in targets:
        out.append("* " + t.render())
    out.append(f"\nMaterial density: {density_kg_m3:g} kg/m^3 (for mass target).")
    if itr > 1 and feedbacks:
        out.append(FEEDBACK_SECTION.format(
            row_idx=None,
            itr=itr,
            max_itr=max_itr,
            targets_block="\n".join("   * " + t.render() for t in targets),
            volume_mm=previous_measurement.volume_mm3 if previous_measurement else 0.0,
            mass_g=previous_measurement.mass_g if previous_measurement else 0.0,
            x_lo=getattr(previous_measurement, "x_range", (-1,))[0] if previous_measurement else -1,
            x_hi=getattr(previous_measurement, "x_range", (-1, 1))[1] if previous_measurement else 1,
            y_lo=getattr(previous_measurement, "y_range", (-1, -1))[0] if previous_measurement else -1,
            y_hi=getattr(previous_measurement, "y_range", (-1, 1))[1] if previous_measurement else 1,
            z_lo=getattr(previous_measurement, "z_range", (-1, -1))[0] if previous_measurement else -1,
            z_hi=getattr(previous_measurement, "z_range", (-1, 1))[1] if previous_measurement else 1,
            feedback_lines="\n".join("   - " + f for f in feedbacks),
        ))
    out.append("\nReturn only the Python code block, exactly as before.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Part 5b: 2D drawing (SVG) -> 3D pipeline
# ---------------------------------------------------------------------------

def load_drawing_spec(svg_path: str) -> str:
    """Return the text of the <desc> element of an SVG drawing.

    The <desc> block is the machine-readable part of the drawing: it must
    contain units, coordinate conventions and every element with its
    coordinates (see Resources/drawings/bridge.svg for the reference layout).
    Namespaced and plain <desc> are both accepted; a missing/empty block is
    an error.
    """
    if not os.path.isfile(svg_path):
        raise T2GError(f"Drawing file not found: {svg_path}")
    try:
        tree = ET.parse(svg_path)
    except ET.ParseError as e:
        raise T2GError(f"Drawing is not valid XML/SVG: {e}") from e
    desc_el = tree.find("{http://www.w3.org/2000/svg}desc")
    if desc_el is None:
        desc_el = tree.find("desc")
    if desc_el is None or not (desc_el.text or "").strip():
        raise T2GError(
            f"Drawing has no <desc> specification block: {svg_path}\n"
            "<desc> must describe units, coordinate mapping and all elements "
            "with their coordinates (see Resources/drawings/bridge.svg).")
    return desc_el.text.strip()


DRAWING_3D_RULES = """\
3D INTERPRETATION (STRICT)
- Coordinate mapping: drawing X -> FreeCAD X; drawing height H -> FreeCAD Z (ground at Z=0); depth (into the page) -> FreeCAD Y.
- Axis-aligned elements (piars, deck, verticals, chords, walls, ...):
  Part.makeBox(x_to - x_from, depth, h_to - h_from) placed at (x_from, y_from, h_from).
- Put the total depth range at Y 0..<depth from the spec>; centre bars in Y where a section depth is given.
- Diagonals are square bars. Use exactly this helper (a def is allowed):
    def bar(x1, h1, x2, h2, t, yc):
      import math
      dx = x2 - x1
      dz = h2 - h1
      L = math.hypot(dx, dz)
      a = math.degrees(math.atan2(dx, dz))
      b = Part.makeBox(t, t, L)
      b.translate(FreeCAD.Vector(-0.5 * t, -0.5 * t, 0))
      b.translate(FreeCAD.Vector(x1, yc, h1))
      b.rotate(FreeCAD.Vector(x1, yc, h1), FreeCAD.Vector(0, 1, 0), a)
      return b
  (it starts at (x1, yc, h1) and ends at (x2, yc, h2) with square section t).
- Build exactly the element list given in the spec, one solid per element.
- Return one code block; end with: result = [all solids]
"""


def build_drawing_prompt(spec: str) -> str:
    """Build the prompt that turns a 2D elevation spec into 3D solids."""
    if not spec or not spec.strip():
        raise T2GError("Drawing spec is empty.")
    return (
        "Build this structure as 3D solids in FreeCAD, from its 2D front-elevation spec.\n\n"
        "DRAWING SPEC (2D elevation):\n" + spec.strip() + "\n\n"
        + DRAWING_3D_RULES
    )


# ---------------------------------------------------------------------------
# Part 6: table readers  (csv, xlsx, spreadsheet, paste)
# ---------------------------------------------------------------------------

def read_table_csv(path: str) -> "tuple[list[str], list[list]]":
    """Read a CSV file into (header, rows). Empty header cells are filled."""
    if not os.path.isfile(path):
        raise T2GError(f"CSV file not found: {path}")
    with open(path, "r", encoding="utf-8", newline="") as fh:
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(fh.read(4096), delimiters=";,\t")
            fh.seek(0)
        except csv.Error:
            dialect = "excel"
        rdr = csv.reader(fh, dialect)
        all_rows = [r for r in rdr if r and any(str(c).strip() for c in r)]
    if not all_rows:
        raise T2GError(f"CSV file is empty: {path}")
    header, rows = _normalise(all_rows)
    return header, rows


def _normalise(all_rows: list[list]) -> tuple[list[str], list[list]]:
    header = [str(c).strip() if c else f"col_{i}" for i, c in enumerate(all_rows[0])]
    width = len(header)
    rows: list[list] = []
    for r in all_rows[1:]:
        r = list(r)
        r = [("" if c is None else str(c).strip()) for c in r]
        if len(r) < width:
            r = r + [""] * (width - len(r))
        if len(r) > width:
            r = r[:width]
        rows.append(r)
    if not rows:
        # single-line header-only file: treat that header as a one-row table
        rows = [list(all_rows[0])]
    return header, rows


def read_table_xlsx(path: str, sheet: str | None = None) -> tuple[list[str], list[list]]:
    """Read a .xlsx file WITHOUT openpyxl (uses zipfile + xml.etree)."""
    if not os.path.isfile(path):
        raise T2GError(f"XLSX file not found: {path}")
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise T2GError(f"Not a valid .xlsx zip: {path}") from e

    shared: list[str] = []
    try:
        with zf.open("xl/sharedStrings.xml") as fh:
            root = ET.parse(fh).getroot()
            ns = {"s": root.tag.split("}")[0].lstrip("{")}
            for si in root.findall("s:si", ns):
                text = "".join(t.text or "" for t in si.iter(f"{{{ns['s']}}}t"))
                shared.append(text)
    except KeyError:
        pass  # no sharedStrings

    # find target sheet id
    target = "xl/worksheets/sheet1.xml"
    if sheet is not None:
        wb_root = None
        with zf.open("xl/workbook.xml") as fh:
            wb_root = ET.parse(fh).getroot()
        ns = {"s": wb_root.tag.split("}")[0].lstrip("{")}
        rel_ns = {"r": "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"}
        for i, s in enumerate(wb_root.findall(f"{{{ns['s']}}}sheets/{{{ns['s']}}}sheet", ), start=1):
            if str(s.get("name")) == sheet:
                target = f"xl/worksheets/sheet{i}.xml"
                break
        else:
            raise T2GError(f"Sheet {sheet!r} not found in {path}")

    # map relationships rId -> target path if needed
    with zf.open(target) as fh:
        ws = ET.parse(fh).getroot()
    ns = {"s": ws.tag.split("}")[0].lstrip("{")}
    rows_data: list[list] = []
    for row_el in ws.findall(f"{{{ns['s']}}}sheetData/{{{ns['s']}}}row"):
        cells: list = []
        for c in row_el.findall(f"{{{ns['s']}}}c"):
            t = c.get("t")
            v_el = c.find(f"{{{ns['s']}}}v")
            if v_el is None:
                cells.append("")
                continue
            raw = v_el.text or ""
            if t == "s":
                try:
                    cells.append(shared[int(raw)])
                except (ValueError, IndexError):
                    cells.append("")
            elif t == "inlineStr":
                is_el = c.find(f"{{{ns['s']}}}is")
                cells.append("".join(tt.text or "" for tt in is_el.iter(f"{{{ns['s']}}}t")) if is_el is not None else "")
            else:
                cells.append(raw)
        rows_data.append(cells)
    # drop fully-empty rows
    rows_data = [r for r in rows_data if any(str(x).strip() for x in r)]
    if not rows_data:
        raise T2GError(f"XLSX {path} has no data")
    header, rows = _normalise(rows_data)
    return header, rows


def read_table_ssheet(sheet_obj) -> tuple[list[str], list[list]]:
    """Read from a FreeCAD Spreadsheet sheet object (Spreadsheet::Sheet).

    Uses `getNonEmptyRange()` / `getUsedRange()` to discover bounds, then
    `sheet.get("A1")` per cell. Works headless (FreeCADCmd) since the
    Spreadsheet module is part of the App (not Gui).
    """
    if sheet_obj is None:
        raise T2GError("No spreadsheet object.")
    top_s, bot_s = _sheet_range(sheet_obj)
    if not top_s or not bot_s:
        raise T2GError("Could not determine spreadsheet used range.")
    c0, r0 = _ref_to_idx(top_s)
    c1, r1 = _ref_to_idx(bot_s)
    all_rows: list[list] = []
    for r in range(r0, r1 + 1):
        row = []
        for c in range(c0, c1 + 1):
            try:
                v = sheet_obj.get(_colname(c) + str(r + 1))
                row.append("" if v is None else str(v))
            except Exception:
                row.append("")
        if any(str(x).strip() for x in row):
            all_rows.append(row)
    if not all_rows:
        raise T2GError("Spreadsheet has no data")
    return _normalise(all_rows)


def _sheet_range(sheet_obj) -> tuple:
    """Return (top, bottom) cell refs via range APIs, None if unavailable."""
    for attr in ("getNonEmptyRange", "getUsedRange"):
        fn = getattr(sheet_obj, attr, None)
        if callable(fn):
            try:
                rng = fn()
            except Exception:
                continue
            if isinstance(rng, tuple) and len(rng) >= 2 and rng[0] and rng[-1]:
                return str(rng[0]), str(rng[-1])
    return None, None


def _colname(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _ref_to_idx(ref: str) -> tuple[int, int]:
    """Parse a cell ref like 'B3' into (0-based col, 0-based row)."""
    m = re.match(r"\s*([A-Za-z]+)([0-9]+)\s*$", ref)
    if not m:
        raise T2GError(f"Bad cell reference: {ref!r}")
    col = 0
    for ch in m.group(1).upper():
        col = col * 26 + (ord(ch) - 64)
    return col - 1, int(m.group(2)) - 1


def read_table_paste(text: str) -> tuple[list[str], list[list]]:
    """Parse pasted table text. Supports CSV / TSV / aligned lines."""
    if not text or not text.strip():
        raise T2GError("Pasted table is empty.")
    first = text.splitlines()[0]
    if "\t" in first:
        delim = "\t"
    elif ";" in first and "," not in first:
        delim = ";"
    else:
        delim = ","
    lines = [ln for ln in text.splitlines() if ln.strip()]
    parsed: list[list] = []
    for ln in lines:
        parsed.append([c.strip() for c in ln.split(delim)])
    if not parsed:
        raise T2GError("No rows in pasted table.")
    return _normalise(parsed)


# ---------------------------------------------------------------------------
# Part 7: sweep engine
# ---------------------------------------------------------------------------

@dataclass
class VariantResult:
    label: str
    row: dict
    ok: bool
    iterations: int
    code: str
    shapes: object
    measurement: Optional[Measurement]
    failures: list
    duration_s: float


@dataclass
class SweepConfig:
    base_prompt: str
    rows: list
    targets: list
    density_kg_m3: float
    max_iterations: int
    generate_fn: GenerateFn
    on_row_start: Callable | None = None
    on_row_done: Callable | None = None
    on_iteration: Callable | None = None
    should_cancel: Callable | None = None
    # label_fn(idx, row) -> str  (optional)
    label_fn: Callable | None = None


def run_sweep(cfg: SweepConfig) -> list:
    """Execute the sweep: for each variant, call generate_fn with the built
    prompt, measure, check targets, feed back on failure up to
    `max_iterations` times.

    Emits:
      on_row_start(idx, row, label)
      on_iteration(idx, row, label, itr, code, measurement, failures, ok)
      on_row_done(idx, row, label, result)

    Returns list[VariantResult] (final state after the last iteration).
    """
    time = __import__("time")
    results: list = []
    targets = cfg.targets or []
    for idx, row in enumerate(cfg.rows):
        if cfg.should_cancel and cfg.should_cancel():
            break
        label = (cfg.label_fn(idx, row) if cfg.label_fn else f"variant_{idx}")
        if cfg.on_row_start:
            cfg.on_row_start(idx, row, label)
        row_start = time.time()
        code = ""
        shapes = None
        measurement = None
        failures: list = []
        ok = False
        used_itr = 0
        for itr in range(1, cfg.max_iterations + 1):
            used_itr = itr
            if cfg.should_cancel and cfg.should_cancel():
                break
            prompt = build_prompt(
                cfg.base_prompt,
                row,
                targets,
                cfg.density_kg_m3,
                itr=itr,
                max_itr=cfg.max_iterations,
                feedbacks=failures if failures else None,
                previous_measurement=measurement,
            )
            code, shapes = cfg.generate_fn(prompt)
            measurement = measure_shape(shapes, cfg.density_kg_m3)
            failures = []
            for t in targets:
                o, msg = t.check(measurement)
                if t.kind == "text":
                    continue  # free-text handled by LLM
                if not o:
                    failures.append(msg)
            ok = not failures
            if cfg.on_iteration:
                cfg.on_iteration(idx, row, label, itr, code, measurement, failures, ok)
            if ok:
                break
        if cfg.on_row_done:
            cfg.on_row_done(idx, row, label, None)
        results.append(VariantResult(
            label=label,
            row=dict(row),
            ok=ok,
            iterations=used_itr,
            code=code,
            shapes=shapes,
            measurement=measurement,
            failures=list(failures),
            duration_s=time.time() - row_start,
        ))
    return results


# ---------------------------------------------------------------------------
# Part 8: export CSV
# ---------------------------------------------------------------------------

def export_results_csv(results: list, out_path: str,
                       measurement_keys=("volume_mm3", "mass_g",
                                         "x_range", "y_range", "z_range")) -> None:
    if not out_path:
        raise T2GError("Empty output path.")
    header = ["label", "ok", "iterations", "duration_s"]
    row_keys = sorted({k for r in results for k in (r.row or {}).keys()}) if results else []
    header.extend(row_keys)
    header.extend(["volume_mm3", "mass_g",
                   "x_size_mm", "y_size_mm", "z_size_mm",
                   "failures"])
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in results:
            m = r.measurement
            vals = [r.label, r.ok, r.iterations, f"{r.duration_s:.2f}"]
            for k in row_keys:
                vals.append((r.row or {}).get(k, ""))
            if m:
                vals.extend([
                    f"{m.volume_mm3:.3f}", f"{m.mass_g:.3f}",
                    f"{m.x_size:.3f}", f"{m.y_size:.3f}", f"{m.z_size:.3f}",
                ])
            else:
                vals.extend([""] * 5)
            vals.append("; ".join(r.failures or []))
            w.writerow(vals)


# ---------------------------------------------------------------------------
# Part 9: backend call (kept at the end of the file so it can use SYSTEM_PROMPT)
# ---------------------------------------------------------------------------

class T2GError(Exception):
    """Base error for TextToGeometry."""


class BackendError(T2GError):
    def __init__(self, msg, stderr: str = "", returncode: int = -1):
        super().__init__(msg)
        self.msg = msg
        self.stderr = stderr
        self.returncode = returncode


OLLAMA_DEFAULT_URL = "http://localhost:11434"

# Where `pi` usually ends up when installed with npm -g / pipx / a user prefix.
_PI_EXTRA_DIRS = (
    "~/.npm-global/bin",
    "~/.local/bin",
    "~/node_modules/.bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
)


def find_pi_binary(preferred: str | None = None) -> str:
    """Locate the `pi` CLI: explicit argument, T2G_PI_BIN, PATH, common dirs."""
    if preferred:
        return preferred
    env = os.environ.get("T2G_PI_BIN")
    if env:
        exe = os.path.expanduser(env)
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
        raise BackendError(f"T2G_PI_BIN points to a non-executable: {env}")
    which = shutil.which("pi")
    if which:
        return which
    for d in _PI_EXTRA_DIRS:
        exe = os.path.join(os.path.expanduser(d), "pi")
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    raise BackendError(
        "pi-CLI nicht gefunden (weder in PATH noch in "
        + ", ".join(_PI_EXTRA_DIRS)
        + "). Installation: `npm install -g --ignore-scripts "
        "@earendil-works/pi-coding-agent`, oder T2G_PI_BIN auf die Binary setzen, "
        "oder im Panel das Backend `Ollama (nativ)` wählen."
    )


def find_pi_binary_or_none(preferred: str | None = None) -> "str | None":
    """Like :func:`find_pi_binary` but returns None instead of raising."""
    try:
        return find_pi_binary(preferred)
    except BackendError:
        return None


# ---------------------------------------------------------------------------
# Ollama server: probe / autostart
# ---------------------------------------------------------------------------

def _ollama_root(base_url: str | None = None) -> str:
    """Normalise any Ollama/OpenAI base URL to the plain server root."""
    base = (base_url or OLLAMA_DEFAULT_URL).strip().rstrip("/")
    if not base:
        base = OLLAMA_DEFAULT_URL
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    if "://" not in base:
        base = "http://" + base
    return base


def probe_ollama(base_url: str | None = None, timeout_s: float = 3.0) -> list:
    """Return the model names the Ollama server offers.

    Raises :class:`BackendError` when the server cannot be reached — the
    message is meant to be shown to the user as-is.
    """
    url = _ollama_root(base_url) + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise BackendError(f"Ollama antwortet mit HTTP {e.code} ({url}).",
                           "", int(e.code)) from e
    except Exception as e:  # URLError, socket.timeout, JSON errors
        raise BackendError(
            f"Ollama ist unter {url} nicht erreichbar ({e}). "
            "Server starten mit `ollama serve` bzw. "
            "`systemctl --user start ollama`.", "", -1) from e
    return [m.get("name") or m.get("model") or ""
            for m in (payload.get("models") or [])]


def ollama_running(base_url: str | None = None, timeout_s: float = 2.0) -> bool:
    try:
        probe_ollama(base_url, timeout_s=timeout_s)
        return True
    except BackendError:
        return False


def start_ollama(base_url: str | None = None, timeout_s: float = 25.0) -> str:
    """Start a local Ollama server if it is not already listening.

    Tries, in order: the running server, the systemd user unit, the system
    unit, then a detached ``ollama serve``. Returns a short status line;
    raises :class:`BackendError` if the server is still unreachable.
    """
    root = _ollama_root(base_url)
    if ollama_running(root):
        return f"Ollama läuft bereits ({root})."

    host = root.split("://", 1)[-1].split("/")[0].split(":")[0]
    if host not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise BackendError(
            f"Ollama unter {root} ist nicht erreichbar und kann von hier aus "
            "nicht gestartet werden (kein lokaler Host).", "", -1)

    time = __import__("time")
    attempts: list = []

    def _wait(label: str, deadline: float) -> "str | None":
        while time.time() < deadline:
            if ollama_running(root, timeout_s=1.5):
                return f"Ollama gestartet ({label}, {root})."
            time.sleep(0.7)
        return None

    for cmd, label in (
        (["systemctl", "--user", "start", "ollama"], "systemd --user"),
        (["systemctl", "start", "ollama"], "systemd"),
    ):
        if not shutil.which(cmd[0]):
            continue
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=15, check=False)
        except Exception as e:  # noqa: BLE001
            attempts.append(f"{label}: {e}")
            continue
        if proc.returncode == 0:
            msg = _wait(label, time.time() + min(timeout_s, 15))
            if msg:
                return msg
            attempts.append(f"{label}: Unit gestartet, Port bleibt zu")
        else:
            attempts.append(f"{label}: rc={proc.returncode} "
                            f"{(proc.stderr or '').strip()[:120]}")

    exe = shutil.which("ollama")
    if exe:
        try:
            subprocess.Popen(
                [exe, "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:  # noqa: BLE001
            attempts.append(f"ollama serve: {e}")
        else:
            msg = _wait("ollama serve", time.time() + timeout_s)
            if msg:
                return msg
            attempts.append("ollama serve: Port bleibt zu")
    else:
        attempts.append("ollama-Binary nicht gefunden")

    raise BackendError(
        f"Ollama konnte nicht gestartet werden ({root}). Versuche: "
        + " | ".join(attempts or ["keine"]), "", -1)


def pi_models(pi_binary: str, provider: str = "", search: str = "",
              timeout_s: int = 120) -> list:
    """Models the pi CLI offers -- ``pi --list-models`` in table form."""
    cmd = [pi_binary]
    if provider:
        cmd += ["--provider", provider]
    cmd += ["--list-models"]
    if search:
        cmd.append(search)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s, check=False)
    except Exception as e:  # noqa: BLE001
        raise BackendError(f"pi --list-models fehlgeschlagen: {e}", "", -1) from e
    if proc.returncode != 0:
        raise BackendError(
            "pi --list-models: " + (proc.stderr or proc.stdout or "").strip()[:300],
            "", proc.returncode)
    out = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] in ("provider", "Provider"):
            continue
        if provider and parts[0] != provider:
            continue
        out.append(parts[1])
    return sorted(set(out))


def openai_models(cfg: "APIConfig" , timeout_s: float = 15.0) -> list:
    """Model ids an OpenAI-compatible endpoint offers (GET /v1/models).

    Works for OpenAI itself and for every service that copies its API
    (OpenRouter, Groq, Mistral, DeepSeek, LM Studio, vLLM, llama.cpp ...).
    """
    base = (cfg.base_url or "").strip().rstrip("/")
    if not base:
        raise BackendError("Keine Base-URL angegeben.")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if not re.search(r"/v\d+$", base):
        base = base + "/v1"
    url = base + "/models"
    headers = {"Accept": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = "Bearer " + cfg.api_key
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        hint = " (API-Schlüssel prüfen)" if e.code in (401, 403) else ""
        raise BackendError(f"HTTP {e.code} von {url}{hint} {detail}",
                           "", int(e.code)) from e
    except Exception as e:  # noqa: BLE001
        raise BackendError(f"{url} nicht erreichbar ({e})", "", -1) from e
    data = payload.get("data")
    if isinstance(data, list):
        names = [d.get("id") or d.get("name") for d in data if isinstance(d, dict)]
    elif isinstance(payload.get("models"), list):
        names = [d.get("id") or d.get("name") if isinstance(d, dict) else str(d)
                 for d in payload["models"]]
    else:
        names = []
    return sorted(n for n in names if n)


def list_models(cfg: "APIConfig", pi_binary: str | None = None) -> list:
    """Model list for whichever backend ``cfg`` describes."""
    if cfg is None:
        return []
    if cfg.kind == "ollama":
        return probe_ollama(cfg.base_url)
    if cfg.kind == "openai":
        return openai_models(cfg)
    if cfg.kind == "pi":
        return pi_models(pi_binary or find_pi_binary(), cfg.provider)
    return []


def call_model_verbose(prompt: str, system_prompt: str,
                       cfg: "APIConfig | None" = None,
                       pi_binary: str | None = None,
                       timeout_s: int | None = None,
                       thinking: str | None = None) -> "tuple[str, str]":
    """One model call -> ``(answer, thinking)``.

    The single place that knows how each backend is invoked; before this, the
    pi path silently ignored the configured provider, model and key.
    """
    if cfg is not None and cfg.kind in ("openai", "ollama"):
        thoughts: list = []
        raw = _t2g_api_call(cfg, system_prompt, prompt, thoughts, thinking)
        thinking, answer = split_thinking(raw)
        if thoughts:
            thinking = "\n".join(t for t in thoughts + [thinking] if t)
        return answer or raw, thinking
    pi = find_pi_binary(pi_binary)
    stream = run_backend(
        prompt, pi_binary=pi, system_prompt=system_prompt,
        provider=(cfg.provider if cfg else "") or "ollama",
        model=(cfg.model if cfg else "") or "qwen-gross:latest",
        api_key=(cfg.api_key if cfg else ""),
        thinking=(thinking if thinking is not None
                  else (cfg.thinking if cfg else "")),
        timeout_s=int(timeout_s or (cfg.timeout_s if cfg else 900)))
    text = extract_message_text(stream)
    thinking = extract_thinking(stream)
    if not thinking:
        thinking, text2 = split_thinking(text)
        text = text2 or text
    return text, thinking


def call_model(prompt: str, system_prompt: str,
               cfg: "APIConfig | None" = None,
               pi_binary: str | None = None,
               timeout_s: int | None = None,
               thinking: str | None = None) -> str:
    return call_model_verbose(prompt, system_prompt, cfg, pi_binary,
                              timeout_s, thinking)[0]


def with_thinking(cfg: "APIConfig | None", level: str) -> "APIConfig | None":
    """A copy of ``cfg`` that thinks harder (or less) for one kind of job."""
    if cfg is None:
        return None
    import dataclasses
    return dataclasses.replace(cfg, thinking=level)


def backend_status(cfg: "APIConfig | None" = None) -> str:
    """One-line, user-facing status of the configured backend."""
    kind = (cfg.kind if cfg else "pi")
    if kind == "pi":
        exe = find_pi_binary_or_none()
        if not exe:
            return "pi-CLI nicht gefunden — Backend auf „Ollama (nativ)“ umstellen."
        base = OLLAMA_DEFAULT_URL
        return (f"pi-CLI: {exe} · Ollama {'erreichbar' if ollama_running(base) else 'NICHT erreichbar'}"
                f" ({base})")
    base = cfg.base_url if cfg else OLLAMA_DEFAULT_URL
    model = cfg.model if cfg else ""
    if kind == "ollama":
        try:
            models = probe_ollama(base)
        except BackendError as e:
            return str(e.msg if hasattr(e, "msg") else e)
        have = "" if not model else (" · Modell vorhanden"
                                     if model in models else
                                     f" · Modell {model!r} NICHT geladen")
        return f"Ollama erreichbar: {len(models)} Modell(e){have} ({_ollama_root(base)})"
    try:
        models = openai_models(cfg)
    except BackendError as e:
        return f"API {base}: {e.msg if hasattr(e, 'msg') else e}"
    have = "" if not model else (" · Modell vorhanden" if model in models
                                 else f" · Modell {model!r} nicht in der Liste")
    key = "mit Schlüssel" if (cfg and cfg.api_key) else "ohne Schlüssel"
    return f"API erreichbar ({key}): {len(models)} Modell(e){have} – {base}"


def detect_backend(saved: "APIConfig | None" = None) -> "tuple[str, str]":
    """Pick a backend that actually works here -> (kind, status message).

    Local Ollama first (nothing to configure, nothing leaves the machine); a
    configured HTTP API second, so the add-on also works on a FreeCAD
    installation without Ollama; the pi CLI last.
    """
    if ollama_running(OLLAMA_DEFAULT_URL):
        return "ollama", (f"Ollama erreichbar ({OLLAMA_DEFAULT_URL}) — "
                          "Backend: Ollama (nativ).")
    if saved is not None and saved.kind == "openai" and saved.base_url.strip():
        try:
            models = openai_models(saved)
        except BackendError as e:
            return "openai", (f"Ollama nicht erreichbar; gespeicherte API "
                              f"{saved.base_url} antwortet nicht: "
                              f"{e.msg if hasattr(e, 'msg') else e}")
        return "openai", (f"Ollama nicht erreichbar — nutze API "
                          f"{saved.base_url} ({len(models)} Modelle).")
    exe = find_pi_binary_or_none()
    if exe:
        return "pi", f"Ollama nicht erreichbar, nutze pi-CLI ({exe})."
    return "openai", ("Kein lokales Ollama gefunden — im Tab „Backend“ eine "
                      "API-Adresse und einen Schlüssel eintragen.")


def run_backend(
    prompt: str,
    *,
    pi_binary: str,
    provider: str = "ollama",
    model: str = "qwen-gross:latest",
    system_prompt: str = SYSTEM_PROMPT,
    timeout_s: int = 120,
    api_key: str = "",
    thinking: str = "",
    env_extra: dict | None = None,
) -> str:
    """Invoke `pi -p --mode json` and return the raw NDJSON stream.

    ``provider`` is a pi provider name (ollama, openai, anthropic, google, …),
    so the CLI reaches a hosted API just as well as a local model -- it only
    needs the key passed on.
    """
    if not prompt or not prompt.strip():
        raise BackendError("Empty prompt.")
    cmd = [
        pi_binary,
        "--provider", provider or "ollama",
        "--model", model or "qwen-gross:latest",
        "--system-prompt", system_prompt,
        "--no-tools", "--no-extensions", "--no-skills", "--no-themes",
        "--no-prompt-templates", "--no-context-files", "--no-session",
        "-p", "--mode", "json",
    ]
    if api_key:
        cmd += ["--api-key", api_key]
    level = _thinking_for_pi(thinking)
    if level:
        cmd += ["--thinking", level]
    cmd += ["--", prompt]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # a hosted provider needs the network; only the local path stays offline
    if (provider or "ollama") == "ollama":
        env.setdefault("PI_OFFLINE", "1")
    env.setdefault("PI_TELEMETRY", "0")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout_s, env=env, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise BackendError(f"pi timed out after {timeout_s}s.", str(e) or "", -1) from e
    except FileNotFoundError as e:
        raise BackendError(f"pi binary not found at {pi_binary!r}", "", -1) from e
    if proc.returncode != 0:
        raise BackendError(f"pi exited with code {proc.returncode}",
                           proc.stderr or "", proc.returncode)
    return proc.stdout or ""


def extract_thinking(stream: str) -> str:
    """The model's reasoning out of a pi NDJSON stream, if it emitted any."""
    if not stream:
        return ""
    parts = []
    for line in stream.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message")
        blocks = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "thinking":
                t = (block.get("thinking") or "").strip()
                if t and t not in parts:
                    parts.append(t)
    return "\n".join(parts)


def split_thinking(text: str) -> "tuple[str, str]":
    """(thinking, answer) -- many models wrap reasoning in <think> tags."""
    if not text:
        return "", ""
    thoughts = []

    def _take(m):
        thoughts.append(m.group(1).strip())
        return ""

    rest = re.sub(r"(?is)<think(?:ing)?>(.*?)</think(?:ing)?>", _take, text)
    return "\n".join(t for t in thoughts if t), rest.strip()


def extract_message_text(stream: str) -> str:
    """Return the assistant's last text message from a pi NDJSON stream.

    Falls back to the raw string when it is not NDJSON (e.g. an HTTP backend
    answer that was passed through unchanged).
    """
    if not stream:
        return ""
    best = ""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "message_end":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text", "")
                    if t:
                        best = t
        elif isinstance(content, str) and content:
            best = content
    return best or stream


def extract_code_block(stream: str) -> str:
    """Parse the pi NDJSON stream and return the assistant code block."""
    if not stream:
        raise T2GError("Empty response from backend.")
    best = extract_message_text(stream)
    if best:
        code = _strip_fenced_python(best)
        if code:
            return code
    m = re.search(r"```(?:python)?\s*\n(.*?)\n\s*```", stream, re.DOTALL)
    if m:
        return m.group(1).strip()
    raise T2GError("Could not find a Python code block in the model response.")


def _strip_fenced_python(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    stripped = text.strip()
    if stripped.startswith("import ") or stripped.startswith("#"):
        return stripped
    return ""


# ---------------------------------------------------------------------------
# Part 11: conversational mode (document-aware, with clarifying questions)
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """\
Du bist ein CAD-Assistent in FreeCAD. Der Benutzer beschreibt auf Deutsch oder
Englisch, was am *aktuellen Dokument* geschehen soll. Du antwortest mit genau
EINEM Codeblock - entweder einer Rueckfrage oder Python-Code.

RUECKFRAGE
Wenn eine Angabe fehlt, die die Geometrie wesentlich veraendert (Durchmesser,
Position, Bauteil, Lastwert), stelle GENAU EINE kurze Rueckfrage:

```frage
Welchen Durchmesser soll die Bohrung haben und wo soll sie sitzen?
```

Frage nur, wenn es wirklich noetig ist. Kleinere Details waehlst du selbst und
schreibst die Annahme als Kommentar in den Code.

CODE
Sonst antwortest du mit genau einem ```python-Block. Dir stehen zur Verfuegung:

  Part, FreeCAD, math                Standard-Geometrie (wie gewohnt)
  names()                            -> Liste der Objektnamen im Dokument
  selected()                         -> Liste der aktuell ausgewaehlten Namen
  shape(name)                        -> Part.Shape des Objekts (Kopie)
  info(name)                         -> dict: label, type, volume, bbox, ...
  add(shape, name=None, label=None)  legt ein NEUES Objekt an
  replace(name, shape)               ersetzt die Geometrie eines Objekts
  part(name, members)                fasst Objekte in einem Bauteil (App::Part) zusammen
  assembly(name, members)            legt eine Baugruppe an und bindet die Objekte ein
  fem(target, fixed=..., load=..., force_n=..., material=...)  Festigkeitsanalyse
  note(text)                         schreibt eine Zeile ins Protokoll

REGELN
- Kein Zugriff auf App/FreeCAD.ActiveDocument, kein print, kein Import ausser
  Part, FreeCAD, math.
- Aenderungen an bestehenden Objekten IMMER ueber replace(), neue Koerper ueber
  add(). Ein `result`-Array ist nicht noetig.
- Bezug auf "das Bauteil"/"dieses Teil" ohne Namen: nimm selected(), sonst das
  einzige bzw. zuletzt angelegte Objekt.
- Koordinaten in mm, Winkel in Grad. Bohrungen sind Zylinder, die mit .cut()
  abgezogen werden; bohre durch das ganze Bauteil (Zylinder laenger als das
  Material, Startpunkt ausserhalb).
- Fuer fem(): Flaechen werden ueber Bounding-Box-Seiten benannt:
  "xmin","xmax","ymin","ymax","zmin","zmax".

BEISPIELE

Benutzer: "Ergaenze eine Bohrung mit 10 mm Durchmesser in der Mitte von oben."
```python
import Part, FreeCAD
n = selected()[0] if selected() else names()[-1]
s = shape(n)
bb = info(n)["bbox"]
cx = (bb["xmin"] + bb["xmax"]) / 2.0
cy = (bb["ymin"] + bb["ymax"]) / 2.0
# durchgehende Bohrung, 1 mm Ueberstand oben und unten
bohr = Part.makeCylinder(5.0, bb["zmax"] - bb["zmin"] + 2,
                         FreeCAD.Vector(cx, cy, bb["zmin"] - 1))
replace(n, s.cut(bohr))
```

Benutzer: "Lege ein neues Bauteil mit dem Namen Grundplatte an, 100x60x8."
```python
import Part
add(Part.makeBox(100, 60, 8), name="Grundplatte")
```

Benutzer: "Baue diese beiden Bauteile in eine Baugruppe ein."
```python
assembly("Baugruppe", selected() or names()[:2])
```

Benutzer: "Fuehre eine Festigkeitsanalyse durch, unten fest, oben 500 N."
```python
fem(selected()[0] if selected() else names()[-1],
    fixed="zmin", load="zmax", force_n=500.0, material="Stahl")
```

Antworte jetzt mit genau einem Block - ```frage oder ```python.
"""


def describe_document(objects: list, selection: list | None = None) -> str:
    """Render the document contents as prompt context.

    ``objects`` are plain dicts (see :func:`T2GCommand._doc_objects`) so this
    stays importable and testable without FreeCAD.
    """
    if not objects:
        return "Das aktive Dokument ist leer (noch keine Objekte)."
    lines = [f"Objekte im aktiven Dokument ({len(objects)}):"]
    for o in objects:
        bb = o.get("bbox") or {}
        pos = ""
        if bb:
            pos = ("  bbox x %.1f..%.1f, y %.1f..%.1f, z %.1f..%.1f"
                   % (bb.get("xmin", 0), bb.get("xmax", 0),
                      bb.get("ymin", 0), bb.get("ymax", 0),
                      bb.get("zmin", 0), bb.get("zmax", 0)))
        vol = o.get("volume")
        volpart = f"  Volumen {vol:.1f} mm^3" if isinstance(vol, (int, float)) else ""
        label = o.get("label") or ""
        lab = f' Label "{label}"' if label and label != o.get("name") else ""
        lines.append(f"- {o.get('name')} ({o.get('type', '?')}{lab}):"
                     f"{volpart}{pos}"
                     + (f"  Solids {o['solids']}" if o.get("solids") else ""))
    sel = [x for x in (selection or []) if x]
    lines.append("Auswahl: " + (", ".join(sel) if sel else "nichts ausgewählt"))
    return "\n".join(lines)


@dataclass
class ChatTurn:
    role: str          # "user" | "assistant"
    text: str


@dataclass
class ChatReply:
    kind: str          # "question" | "code"
    text: str          # question text or python code


class ChatSession:
    """Conversation state for the document-aware mode.

    Keeps the last ``max_turns`` turns so a follow-up ("mach sie 12 mm")
    still has the earlier request in view, and builds the per-turn prompt
    from history + live document context.
    """

    def __init__(self, max_turns: int = 12) -> None:
        self.history: list = []
        self.max_turns = max_turns
        self.pending_question: str | None = None

    def reset(self) -> None:
        self.history = []
        self.pending_question = None

    def add_user(self, text: str) -> None:
        self.history.append(ChatTurn("user", text))
        self._trim()

    def add_assistant(self, text: str) -> None:
        self.history.append(ChatTurn("assistant", text))
        self._trim()

    def _trim(self) -> None:
        if len(self.history) > self.max_turns:
            self.history = self.history[-self.max_turns:]

    def build_prompt(self, user_msg: str, doc_context: str) -> str:
        parts = ["AKTUELLER ZUSTAND", doc_context, ""]
        if self.history:
            parts.append("BISHERIGER VERLAUF")
            for t in self.history:
                who = "Benutzer" if t.role == "user" else "Assistent"
                parts.append(f"{who}: {t.text.strip()}")
            parts.append("")
        if self.pending_question:
            parts.append("Deine letzte Rückfrage war: " + self.pending_question)
            parts.append("Der Benutzer antwortet darauf jetzt.")
            parts.append("")
        parts.append("AUFTRAG")
        parts.append(user_msg.strip())
        return "\n".join(parts)


def parse_chat_reply(raw: str) -> ChatReply:
    """Turn the model's answer into a question or a code block."""
    if not raw or not raw.strip():
        raise T2GError("Leere Antwort vom Modell.")
    m = re.search(r"```(frage|question)\s*\n(.*?)\n\s*```", raw, re.DOTALL | re.I)
    if m:
        q = m.group(2).strip()
        if q:
            return ChatReply("question", q)
    m = re.search(r"```(?:python|py)?\s*\n(.*?)\n\s*```", raw, re.DOTALL)
    if m:
        code = m.group(1).strip()
        if code:
            return ChatReply("code", code)
    txt = raw.strip()
    # A model that forgot the fence but clearly asked something.
    if "?" in txt and "=" not in txt and len(txt) < 400:
        return ChatReply("question", txt)
    raise T2GError("Antwort enthielt weder ```frage noch ```python:\n"
                   + txt[:300])


def chat_backend(prompt: str, *, cfg: "APIConfig | None" = None,
                 pi_binary: str | None = None, timeout_s: int = 300) -> str:
    """One conversational turn -> the model's raw answer text."""
    return call_model(prompt, CHAT_SYSTEM_PROMPT, cfg, pi_binary, timeout_s)


class OpRecorder:
    """Collects the document changes requested by generated code.

    The sandbox never touches the document itself: it records operations,
    and the GUI thread applies them (see ``T2GCommand._apply_ops``).
    """

    def __init__(self, objects: list | None = None,
                 selection: list | None = None,
                 shape_lookup: Callable | None = None) -> None:
        self._objects = {o["name"]: o for o in (objects or [])}
        self._order = [o["name"] for o in (objects or [])]
        self._selection = list(selection or [])
        self._shape_lookup = shape_lookup
        self.ops: list = []
        self.notes: list = []

    # -- read side (exposed to generated code) ------------------------------
    def names(self) -> list:
        return list(self._order)

    def selected(self) -> list:
        return list(self._selection)

    def info(self, name: str) -> dict:
        o = self._objects.get(name)
        if o is None:
            raise T2GError(f"Unbekanntes Objekt: {name!r}. Vorhanden: "
                           + (", ".join(self._order) or "-"))
        return dict(o)

    def shape(self, name: str):
        if self._shape_lookup is None:
            raise T2GError("Kein Zugriff auf Geometrie in diesem Kontext.")
        if name not in self._objects:
            raise T2GError(f"Unbekanntes Objekt: {name!r}. Vorhanden: "
                           + (", ".join(self._order) or "-"))
        return self._shape_lookup(name)

    # -- write side (recorded, applied later) -------------------------------
    def add(self, shape, name: str | None = None, label: str | None = None):
        if shape is None:
            raise T2GError("add() ohne Shape aufgerufen.")
        self.ops.append({"op": "add", "shape": shape,
                         "name": name, "label": label or name})
        return name

    def replace(self, name: str, shape):
        if shape is None:
            raise T2GError(f"replace({name!r}) ohne Shape aufgerufen.")
        if name not in self._objects:
            raise T2GError(f"replace(): unbekanntes Objekt {name!r}. Vorhanden: "
                           + (", ".join(self._order) or "-"))
        self.ops.append({"op": "replace", "name": name, "shape": shape})

    def part(self, name: str, members: list | None = None):
        self.ops.append({"op": "part", "name": name,
                         "members": list(members or [])})

    def assembly(self, name: str, members: list | None = None):
        self.ops.append({"op": "assembly", "name": name,
                         "members": list(members or [])})

    def fem(self, target: str, fixed: str = "zmin", load: str | None = None,
            force_n: float = 0.0, material: str = "Stahl",
            name: str = "Festigkeitsanalyse"):
        self.ops.append({"op": "fem", "name": name, "target": target,
                         "fixed": fixed, "load": load,
                         "force_n": float(force_n or 0.0),
                         "material": material})

    def note(self, text: str):
        self.notes.append(str(text))

    def namespace(self) -> dict:
        return {
            "names": self.names, "selected": self.selected,
            "info": self.info, "shape": self.shape,
            "add": self.add, "replace": self.replace,
            "part": self.part, "assembly": self.assembly,
            "fem": self.fem, "note": self.note,
        }

    def summary(self) -> str:
        if not self.ops and not self.notes:
            return "Keine Änderung angefordert."
        words = {"add": "neues Objekt", "replace": "Geometrie ersetzt",
                 "part": "Bauteil", "assembly": "Baugruppe",
                 "fem": "Festigkeitsanalyse"}
        out = []
        for o in self.ops:
            out.append(f"{words.get(o['op'], o['op'])}: {o.get('name') or o.get('target') or ''}".strip())
        return "; ".join(out + self.notes)


def exec_chat_code(code: str, recorder: OpRecorder) -> OpRecorder:
    """Run model code with the document API bound, return the recorder."""
    _exec_restricted(code, recorder.namespace())
    return recorder


# ---------------------------------------------------------------------------
# Part 12: web research (opt-in) + learning a new skill
# ---------------------------------------------------------------------------

WEB_USER_AGENT = "TextToGeometry/0.1 (FreeCAD add-on)"
WEB_MAX_BYTES = 400_000
WEB_MAX_TEXT = 6000


@dataclass
class ResearchResult:
    """What a research run found: plain text plus the sources it came from."""

    query: str = ""
    text: str = ""
    sources: list = field(default_factory=list)   # list[(title, url)]
    errors: list = field(default_factory=list)

    def as_prompt_block(self) -> str:
        if not self.text.strip():
            return "Keine Recherche-Ergebnisse (Webrecherche aus oder ohne Treffer)."
        src = "\n".join(f"- {t}: {u}" for t, u in self.sources)
        return (f"RECHERCHE zu {self.query!r}\n{self.text.strip()}\n\n"
                f"Quellen:\n{src}")


def _main_content(html: str) -> str:
    """The part of a page that carries the article, if it can be found."""
    for pattern in (r'(?is)<div[^>]+id="mw-content-text".*?>(.*)',      # MediaWiki
                    r"(?is)<article[^>]*>(.*?)</article>",
                    r"(?is)<main[^>]*>(.*?)</main>",
                    r'(?is)<div[^>]+(?:id|class)="(?:content|main|post|entry)[^"]*"[^>]*>(.*)'):
        m = re.search(pattern, html)
        if m and len(m.group(1)) > 400:
            return m.group(1)
    return html


def _drop_boilerplate(text: str) -> str:
    """Throw away navigation leftovers: short, verb-less menu lines."""
    keep, skipped = [], 0
    noise = ("hauptmenü", "navigation", "anmelden", "jetzt spenden",
             "benutzerkonto", "suche", "suchen", "inhaltsverzeichnis",
             "zum inhalt springen", "seitenleiste", "werkzeuge", "impressum",
             "datenschutz", "cookie", "newsletter", "weblinks",
             "einzelnachweise", "erscheinungsbild", "mitmachen",
             "sprachen", "drucken/exportieren", "menu", "skip to content")
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        low = ln.lower()
        if any(low == n or low.startswith(n) for n in noise):
            skipped += 1
            continue
        # a real sentence is long or ends in punctuation; menu entries are not
        if len(ln) < 35 and not ln.rstrip().endswith((".", ":", "!", "?")):
            skipped += 1
            continue
        keep.append(ln)
    return "\n".join(keep)


def html_to_text(html: str, article_only: bool = False) -> str:
    """Small HTML -> text reduction (no external dependency).

    ``article_only`` additionally narrows to the main content and drops
    navigation chrome -- worth it for fetched web pages, wrong for a short
    snippet where every line counts.
    """
    if not html:
        return ""
    if article_only:
        html = _main_content(html)
    txt = re.sub(r"(?is)<(script|style|noscript|head|nav|header|footer|aside|"
                 r"form|menu|template)[^>]*>.*?</\1>", " ", html)
    txt = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", txt)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    replacements = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
                    "&quot;": '"', "&#39;": "'", "&auml;": "ä", "&ouml;": "ö",
                    "&uuml;": "ü", "&szlig;": "ß", "&Auml;": "Ä",
                    "&Ouml;": "Ö", "&Uuml;": "Ü"}
    for a, b in replacements.items():
        txt = txt.replace(a, b)
    txt = re.sub(r"&#\d+;", " ", txt)
    txt = re.sub(r"[ \t\r\f\v]+", " ", txt)
    txt = re.sub(r"\n\s*\n\s*\n+", "\n\n", txt)
    txt = txt.strip()
    return _drop_boilerplate(txt) if article_only else txt


def _web_get(url: str, timeout_s: float = 12.0, max_bytes: int = WEB_MAX_BYTES) -> bytes:
    """Fetch a http(s) URL with a size cap. Other schemes are refused."""
    if not re.match(r"^https?://", url or "", re.I):
        raise T2GError(f"Nur http/https erlaubt, nicht: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": WEB_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.read(max_bytes)
    except urllib.error.HTTPError as e:
        raise T2GError(f"HTTP {e.code} bei {url}") from e
    except Exception as e:  # URLError, timeout, ...
        raise T2GError(f"Abruf fehlgeschlagen ({url}): {e}") from e


def web_fetch(url: str, timeout_s: float = 12.0,
              article_only: bool = True) -> str:
    """Fetch one page and return its readable text.

    A Wikipedia article is taken through the API instead: the same content
    without the navigation, and a fraction of the bytes.
    """
    m = re.match(r"https?://([a-z\-]+)\.wikipedia\.org/wiki/(.+)$", url or "",
                 re.I)
    if m:
        lang, title = m.group(1), urllib.parse.unquote(m.group(2))
        try:
            params = urllib.parse.urlencode({
                "action": "query", "prop": "extracts", "explaintext": 1,
                "titles": title.replace("_", " "), "format": "json"})
            data = json.loads(_web_get(
                f"https://{lang}.wikipedia.org/w/api.php?" + params,
                timeout_s).decode("utf-8"))
            for page in (data.get("query", {}).get("pages", {}) or {}).values():
                extract = (page.get("extract") or "").strip()
                if extract:
                    return extract
        except Exception:  # noqa: BLE001  -- fall back to the HTML below
            pass
    raw = _web_get(url, timeout_s=timeout_s)
    return html_to_text(raw.decode("utf-8", "replace"),
                        article_only=article_only)


def web_search(query: str, limit: int = 5, timeout_s: float = 12.0) -> list:
    """General web search -> ``[(title, url)]``.

    Uses DuckDuckGo's lite endpoint: no key, no JavaScript, and the result
    links carry the target in a ``uddg`` parameter we can decode. Returns an
    empty list rather than raising when the engine is unreachable.
    """
    if not (query or "").strip():
        return []
    url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode(
        {"q": query})
    try:
        html = _web_get(url, timeout_s=timeout_s).decode("utf-8", "replace")
    except T2GError:
        return []
    out, seen = [], set()
    for href, text in re.findall(
            r"<a[^>]+href=\"([^\"]+)\"[^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>",
            html, re.DOTALL | re.I):
        m = re.search(r"[?&]uddg=([^&]+)", href)
        target = urllib.parse.unquote(m.group(1)) if m else href
        if not target.startswith("http"):
            continue
        host = target.split("/")[2].lower()
        if "duckduckgo" in host or host in seen:
            continue
        title = html_to_text(text).strip()
        if not title:
            continue
        seen.add(host)
        out.append((title, target))
        if len(out) >= max(1, int(limit)):
            break
    return out


def wikipedia_search(query: str, lang: str = "de", limit: int = 3,
                     timeout_s: float = 12.0) -> ResearchResult:
    """Search Wikipedia and return the intro texts of the best hits.

    The MediaWiki API needs no key and is reachable where general web search
    engines are often blocked, which makes it the default research source.
    """
    out = ResearchResult(query=query)
    base = f"https://{lang}.wikipedia.org/w/api.php?"
    try:
        params = urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "srlimit": max(1, min(int(limit), 10))})
        data = json.loads(_web_get(base + params, timeout_s).decode("utf-8"))
        titles = [h["title"] for h in data.get("query", {}).get("search", [])]
    except Exception as e:  # noqa: BLE001
        out.errors.append(f"Wikipedia-Suche fehlgeschlagen: {e}")
        return out
    if not titles:
        out.errors.append(f"Keine Wikipedia-Treffer für {query!r}.")
        return out
    try:
        params = urllib.parse.urlencode({
            "action": "query", "prop": "extracts", "explaintext": 1,
            "exintro": 1, "titles": "|".join(titles), "format": "json"})
        data = json.loads(_web_get(base + params, timeout_s).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        out.errors.append(f"Wikipedia-Abruf fehlgeschlagen: {e}")
        return out
    chunks = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        title = page.get("title", "")
        extract = (page.get("extract") or "").strip()
        if not extract:
            continue
        url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(
            title.replace(" ", "_"))
        out.sources.append((title, url))
        chunks.append(f"## {title}\n{extract}")
    out.text = "\n\n".join(chunks)[:WEB_MAX_TEXT]
    return out


def research_topic(topic: str, urls: list | None = None, lang: str = "de",
                   use_wikipedia: bool = True, limit: int = 3,
                   use_web: bool = False, web_pages: int = 2,
                   per_page_chars: int = 2500) -> ResearchResult:
    """Collect background material for ``topic`` from the allowed sources.

    ``use_wikipedia`` gives the encyclopaedic framing, ``use_web`` searches the
    open web and reads the first ``web_pages`` hits. Both are opt-in; with
    neither set and no explicit URL nothing leaves the machine.
    """
    out = ResearchResult(query=topic)
    if use_wikipedia:
        wiki = wikipedia_search(topic, lang=lang, limit=limit)
        out.text = wiki.text
        out.sources.extend(wiki.sources)
        out.errors.extend(wiki.errors)
    if use_web:
        hits = web_search(topic, limit=max(web_pages, limit))
        if not hits:
            out.errors.append("Websuche lieferte keine Treffer "
                              "(Engine nicht erreichbar oder blockiert).")
        read = 0
        for title, url in hits:
            if read >= max(1, int(web_pages)):
                break
            try:
                txt = web_fetch(url)
            except T2GError as e:
                out.errors.append(str(e))
                continue
            if len(txt) < 200:
                continue
            out.sources.append((title, url))
            out.text = (out.text + f"\n\n## {title} ({url})\n"
                        + txt[:per_page_chars]).strip()
            read += 1
    for url in (urls or []):
        url = (url or "").strip()
        if not url:
            continue
        try:
            txt = web_fetch(url)
        except T2GError as e:
            out.errors.append(str(e))
            continue
        out.sources.append((url.split("//")[-1][:60], url))
        out.text = (out.text + "\n\n## " + url + "\n" + txt)[:WEB_MAX_TEXT * 2]
    return out


# --- learning a skill ------------------------------------------------------

SKILL_ANALYSE_PROMPT = """\
Du planst einen neuen parametrischen FreeCAD-Generator ("Skill") für ein
Bauteil, das der Benutzer benennt. Du baust noch NICHTS - du klärst zuerst,
welche Maße das Bauteil überhaupt beschreiben.

Antworte mit ZWEI Blöcken:

```fragen
<offene Fragen an den Benutzer, eine pro Zeile, höchstens 5;
 nur was die Geometrie wirklich bestimmt. Keine Fragen, die der
 Parameterblock schon beantwortet. Darf leer bleiben.>
```

```parameter
<eine Zeile je Parameter: name;label;einheit;default;min;max>
```

REGELN für den Parameterblock
- name: klein, ohne Umlaute, gültiger Python-Bezeichner (laenge, d_ein, wand_t).
- default/min/max: Zahlen, plausibel für das reale Bauteil, min <= default <= max.
- 4 bis 12 Parameter, die zusammen die Form vollständig beschreiben.
- Einheit meist mm oder Grad, "-" für Stückzahlen.
"""

SKILL_CODE_PROMPT = """\
Du schreibst jetzt die build-Funktion eines FreeCAD-Skills.

Antworte mit genau EINEM ```python-Block, der NUR die Funktion enthält:

```python
def build(params):
    import Part, FreeCAD, math
    laenge = float(params["laenge"])
    ...
    return [solid1, solid2]
```

REGELN
- Signatur exakt `def build(params):`, Rückgabe: Liste von Part.Shape (Solids).
- Alle Werte ausschließlich aus `params` lesen - keine festen Maße, die ein
  Parameter abdeckt.
- Erlaubte Importe: Part, FreeCAD, math. Kein Dokumentzugriff, kein print.
- Millimeter, Grad. Robust für den gesamten min..max-Bereich jedes Parameters.
- Lieber wenige saubere Volumenkörper als viele fragile Booleans. Rohre/Kanäle:
  äußeren Körper bauen und den inneren mit .cut() abziehen.
- Keine Erklärung, kein Text ausserhalb des Codeblocks.
"""


def build_skill_analyse_prompt(topic: str, research: "ResearchResult | None" = None,
                               user_notes: str = "") -> str:
    parts = [f"BAUTEIL: {topic.strip()}"]
    if user_notes.strip():
        parts += ["", "ANGABEN DES BENUTZERS", user_notes.strip()]
    if research is not None:
        parts += ["", research.as_prompt_block()]
    parts += ["", "Nenne die offenen Fragen und den Parametersatz."]
    return "\n".join(parts)


def build_skill_code_prompt(topic: str, params: list, answers: str = "",
                            research: "ResearchResult | None" = None,
                            previous_code: str = "", problems: list | None = None) -> str:
    lines = [f"BAUTEIL: {topic.strip()}", "", "PARAMETER (genau diese Namen benutzen)"]
    for p in params:
        name, label, unit, default, lo, hi = p[:6]
        lines.append(f"- {name}: {label} [{unit}], default {default}, "
                     f"Bereich {lo} .. {hi}")
    if answers.strip():
        lines += ["", "ANTWORTEN DES BENUTZERS", answers.strip()]
    if research is not None and research.text.strip():
        lines += ["", research.as_prompt_block()]
    if previous_code and problems:
        lines += ["", "DEIN LETZTER VERSUCH SCHLUG FEHL", previous_code.strip(),
                  "", "FEHLER", *[f"- {p}" for p in problems],
                  "", "Korrigiere das und gib die vollständige Funktion erneut aus."]
    return "\n".join(lines)


def parse_skill_analysis(raw: str) -> "tuple[list, list]":
    """Split the analysis answer into (questions, parameter tuples)."""
    text = extract_message_text(raw) if raw.lstrip().startswith("{") else raw
    questions: list = []
    m = re.search(r"```(?:fragen|questions)\s*\n(.*?)\n?\s*```", text,
                  re.DOTALL | re.I)
    if m:
        for ln in m.group(1).splitlines():
            ln = ln.strip().lstrip("-*0123456789. ").strip()
            if ln:
                questions.append(ln)
    m = re.search(r"```(?:parameter|params)\s*\n(.*?)\n?\s*```", text,
                  re.DOTALL | re.I)
    if not m:
        raise T2GError("Antwort enthielt keinen ```parameter-Block:\n"
                       + text[:300])
    params = parse_param_lines(m.group(1))
    if not params:
        raise T2GError("Der ```parameter-Block enthielt keine gültige Zeile.")
    return questions, params


#: Units that mark a genuine count -- those stay integer, everything else
#: (mm, Grad, kg ...) becomes a float so it can be adjusted continuously.
COUNT_UNITS = ("", "-", "stk", "st", "stueck", "stück", "stk.", "st.",
               "anzahl", "x", "pcs", "count")


def is_count_unit(unit: str) -> bool:
    return (unit or "").strip().lower().rstrip(".") in \
        tuple(u.rstrip(".") for u in COUNT_UNITS)


def parse_param_lines(block: str) -> list:
    """Parse ``name;label;einheit;default;min;max`` lines into tuples."""
    out = []
    for ln in (block or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = [c.strip() for c in ln.split(";")]
        if len(parts) < 4:
            continue
        name = re.sub(r"[^A-Za-z0-9_]", "_", parts[0]).strip("_")
        if not name or name[0].isdigit():
            continue

        def _num(v, fallback=None):
            try:
                return int(v) if re.fullmatch(r"[+-]?\d+", v or "") else float(v)
            except (TypeError, ValueError):
                return fallback

        default = _num(parts[3], 0)
        lo = _num(parts[4]) if len(parts) > 4 else None
        hi = _num(parts[5]) if len(parts) > 5 else None
        # A length the model wrote as "45" must stay adjustable to 67.5 later:
        # only genuine counts ("-", "Stk") become integer parameters.
        if not is_count_unit(parts[2]):
            default = float(default) if default is not None else None
            lo = float(lo) if lo is not None else None
            hi = float(hi) if hi is not None else None
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        if lo is not None and default is not None and default < lo:
            default = lo
        if hi is not None and default is not None and default > hi:
            default = hi
        out.append((name, parts[1] or name, parts[2] or "", default, lo, hi))
    return out


def parse_skill_code(raw: str) -> str:
    """Extract the build() function from the model's answer."""
    return _code_from_answer(raw, "def build(",
                             "Der Code enthält keine Funktion "
                             "`def build(params):`.")


def _code_from_answer(raw: str, must_contain: str, error: str) -> str:
    """Pull a python block out of an answer that may hold several blocks.

    A tagged ```python block wins. Only if there is none do we fall back to an
    untagged fence -- otherwise the *closing* fence of a preceding ```parameter
    block reads as the opening fence of the code, and the tag ends up inside
    the captured text.
    """
    text = raw or ""
    m = re.search(r"```(?:python|py)[ \t]*\n(.*?)\n[ \t]*```", text, re.DOTALL | re.I)
    if not m:
        m = re.search(r"```[ \t]*\n(?!```)(.*?)\n[ \t]*```", text, re.DOTALL)
    code = (m.group(1) if m else text).strip()
    if code.startswith("```"):          # never hand a fence on as code
        code = re.sub(r"^```[A-Za-z]*[ \t]*\n?", "", code).strip()
    if must_contain not in code:
        raise T2GError(error + "\n" + code[:200])
    return code


# ---------------------------------------------------------------------------
# Part 13: project planning (brief, skills, tools, criteria)
# ---------------------------------------------------------------------------

PROJECT_PLAN_PROMPT = """\
Du planst ein Konstruktionsprojekt in FreeCAD. Der Benutzer sagt, was gebaut
werden soll; du gliederst das Vorhaben. Du konstruierst noch nichts.

Antworte mit genau diesen fünf Blöcken, in dieser Reihenfolge:

```auftrag
<3-8 Sätze: was gebaut wird, wofür, welche Baugruppen dazugehören.
 Nur was aus der Beschreibung folgt - nichts dazuerfinden.>
```

```fragen
<offene Fragen an den Benutzer, eine pro Zeile, höchstens 6.
 Nur solche, die die Konstruktion wirklich verändern. Darf leer bleiben.>
```

```skills
<ein parametrisches Bauteil pro Zeile: name;zweck
 name: klein, ohne Umlaute, gültiger Bezeichner (z. B. einlasskanal).
 3 bis 8 Zeilen - die Bauteile, die wiederverwendbar erzeugt werden sollen.>
```

```werkzeuge
<Hilfsprogramme, die für die Auslegung gebraucht werden: name;zweck
 Nur Rechen-/Prüfhilfen (z. B. querschnitt_rechner;Strömungsquerschnitt aus
 Durchmesser und Ovalität). Keine Geometrie. Darf leer bleiben.>
```

```kriterien
<Bewertungskriterien, die miteinander in Konflikt stehen können:
 name;bedeutung
 4 bis 7 Zeilen, z. B. Wandstaerke;Gussgrenze, darf nicht unterschritten werden.
 Genau die Kriterien, zwischen denen später abgewogen werden muss.>
```
"""

PROJECT_PAIRS_PROMPT = """\
Du schlägst Paarvergleiche nach Saaty vor: Für jedes Kriterienpaar, wie viel
wichtiger ist A gegenüber B?

Skala: 9 = A absolut wichtiger, 7 = sehr viel, 5 = deutlich, 3 = etwas,
1 = gleich wichtig; 1/3, 1/5, 1/7, 1/9 entsprechend zugunsten von B.

Antworte mit genau einem Block, eine Zeile je Paar:

```paare
KriteriumA;KriteriumB;Wert;kurze Begründung
```

REGELN
- Genau die vorgegebenen Kriterien und jedes Paar genau einmal.
- Wert als Zahl (9, 7, 5, 3, 1) oder Bruch (1/3, 1/5, 1/7, 1/9).
- Bleib in dir schlüssig: Ist A > B und B > C, dann muss A > C sein, und der
  Wert für A/C ungefähr das Produkt der beiden anderen.
- Das ist ein Vorschlag; der Benutzer entscheidet.
"""


def _fenced(tag: str, text: str) -> str:
    m = re.search(r"```" + tag + r"\s*\n(.*?)\n?\s*```", text, re.DOTALL | re.I)
    return m.group(1) if m else ""


def _semicolon_rows(block: str, fields: int = 2) -> list:
    out = []
    for ln in (block or "").splitlines():
        ln = ln.strip().lstrip("-*").strip()
        if not ln or ln.startswith("#"):
            continue
        parts = [c.strip() for c in ln.split(";")]
        if len(parts) < fields:
            parts += [""] * (fields - len(parts))
        out.append(parts[:max(fields, len(parts))])
    return out


def parse_project_plan(raw: str) -> dict:
    """Split the planning answer into brief, questions, skills, tools, criteria."""
    text = raw or ""
    auftrag = _fenced("auftrag", text).strip()
    if not auftrag:
        raise T2GError("Antwort enthielt keinen ```auftrag-Block:\n" + text[:300])
    fragen = [ln.strip().lstrip("-*0123456789. ").strip()
              for ln in _fenced("fragen", text).splitlines() if ln.strip()]
    skills = [{"name": re.sub(r"[^a-z0-9_]", "_", r[0].lower()).strip("_"),
               "description": r[1]}
              for r in _semicolon_rows(_fenced("skills", text))
              if r[0]]
    tools = [{"name": r[0], "purpose": r[1]}
             for r in _semicolon_rows(_fenced("werkzeuge", text)) if r[0]]
    criteria = [{"name": r[0], "description": r[1]}
                for r in _semicolon_rows(_fenced("kriterien", text)) if r[0]]
    return {"auftrag": auftrag, "fragen": fragen, "skills": skills,
            "tools": tools, "criteria": criteria}


def _parse_ratio(text: str) -> "float | None":
    """`3`, `1/5`, `0.2` -> float; anything else -> None."""
    t = (text or "").strip().replace(",", ".")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[/:]\s*(\d+(?:\.\d+)?)", t)
    if m:
        try:
            den = float(m.group(2))
            return float(m.group(1)) / den if den else None
        except ValueError:
            return None
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def parse_pair_suggestions(raw: str, criteria: list) -> list:
    """[(i, j, value, reason)] for the criteria given, in their own order."""
    index = {}
    for i, c in enumerate(criteria):
        name = c["name"] if isinstance(c, dict) else str(c)
        index[re.sub(r"[^a-z0-9]", "", name.lower())] = i
    out = []
    seen = set()
    for row in _semicolon_rows(_fenced("paare", raw), fields=3):
        a = index.get(re.sub(r"[^a-z0-9]", "", (row[0] or "").lower()))
        b = index.get(re.sub(r"[^a-z0-9]", "", (row[1] or "").lower()))
        val = _parse_ratio(row[2])
        if a is None or b is None or a == b or val is None:
            continue
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        reason = row[3] if len(row) > 3 else ""
        out.append((a, b, val, reason))
    return out


def build_project_plan_prompt(title: str, description: str,
                              research: "ResearchResult | None" = None,
                              existing_skills: list | None = None) -> str:
    parts = [f"PROJEKT: {title.strip()}", "", "BESCHREIBUNG DES BENUTZERS",
             description.strip() or "(keine)"]
    if existing_skills:
        parts += ["", "BEREITS VORHANDENE SKILLS (nimm diese Namen, wenn sie passen)",
                  ", ".join(existing_skills)]
    if research is not None and research.text.strip():
        parts += ["", research.as_prompt_block()]
    parts += ["", "Gliedere das Vorhaben."]
    return "\n".join(parts)


def build_project_pairs_prompt(project_block: str, criteria: list) -> str:
    names = [c["name"] if isinstance(c, dict) else str(c) for c in criteria]
    lines = [project_block, "", "KRITERIEN"]
    for c in criteria:
        if isinstance(c, dict):
            lines.append(f"- {c['name']}: {c.get('description', '')}")
        else:
            lines.append(f"- {c}")
    pairs = [(names[i], names[j])
             for i in range(len(names)) for j in range(i + 1, len(names))]
    lines += ["", f"ZU BEWERTENDE PAARE ({len(pairs)})"]
    lines += [f"- {a} vs. {b}" for a, b in pairs]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Part 14: helper tools and skill refinement
# ---------------------------------------------------------------------------

TOOL_CODE_PROMPT = """\
Du schreibst ein kleines Rechenwerkzeug als reines Python-Modul. Es rechnet,
es konstruiert nicht.

Antworte mit genau EINEM ```python-Block, der enthält:

1. eine oder mehrere Funktionen mit sprechenden Namen und Docstring,
2. zum Schluss eine Funktion `selbsttest()`, die die Funktionen mit
   Beispielwerten aufruft, die Ergebnisse mit `assert` gegen von Hand
   nachgerechnete Werte prüft und `True` zurückgibt.

```python
import math


def querschnitt(d_mm, ovalitaet=1.0):
    \"\"\"Strömungsquerschnitt einer ovalen Bohrung in mm^2.\"\"\"
    a = d_mm / 2.0 * ovalitaet
    b = d_mm / 2.0 / ovalitaet
    return math.pi * a * b


def selbsttest():
    # Kreis: A = pi/4 * d^2 = 78.54 mm^2 bei d = 10
    assert abs(querschnitt(10.0) - 78.5398) < 1e-3
    # Ovalität ändert die Fläche nicht, nur die Form
    assert abs(querschnitt(10.0, 1.5) - querschnitt(10.0)) < 1e-6
    return True
```

REGELN
- Nur Standardbibliothek (`math`, `statistics`, `fractions`, `decimal`,
  `itertools`). Kein FreeCAD, keine Datei-, Netz- oder Prozesszugriffe.
- Keine Eingabeaufforderungen, kein `print`, kein Code auf Modulebene ausser
  den Definitionen und dem Import.
- Die Prüfwerte im Selbsttest müssen stimmen - sie werden wirklich ausgeführt.
- SI-nahe Einheiten wie im Rest des Projekts: mm, mm^2, Grad, g.
"""

SKILL_REFINE_PROMPT = """\
Du überarbeitest die build-Funktion eines vorhandenen FreeCAD-Skills. Das
Bauteil existiert bereits und funktioniert - du verbesserst es gezielt.

Antworte mit einem ```python-Block (die vollständige neue build-Funktion) und
optional davor einem ```parameter-Block, wenn du Parameter ergänzen oder
Grenzen ändern musst:

```parameter
name;label;einheit;default;min;max
```

REGELN
- Signatur exakt `def build(params):`, Rückgabe: Liste von Part.Shape.
- Vorhandene Parameternamen behalten. Neue nur, wenn die Verbesserung sie
  wirklich braucht - dann im ```parameter-Block ALLE Parameter auflisten,
  die alten unverändert.
- Erlaubte Importe: Part, FreeCAD, math. Kein Dokumentzugriff, kein print.
- Richte dich nach den gewichteten Kriterien: Bei einem Zielkonflikt
  entscheidet das höher gewichtete Kriterium.
- Robust über den ganzen min..max-Bereich bleiben.
- Keine Erklärung ausserhalb der Blöcke.
"""


def build_tool_prompt(name: str, purpose: str, project_block: str = "",
                      previous_code: str = "", problems: list | None = None) -> str:
    parts = [f"WERKZEUG: {name}", f"ZWECK: {purpose or '(nicht näher beschrieben)'}"]
    if project_block.strip():
        parts += ["", "PROJEKTZUSAMMENHANG", project_block.strip()]
    if previous_code and problems:
        parts += ["", "DEIN LETZTER VERSUCH SCHLUG FEHL", previous_code.strip(),
                  "", "FEHLER", *[f"- {p}" for p in problems],
                  "", "Korrigiere das und gib das vollständige Modul erneut aus."]
    return "\n".join(parts)


def parse_tool_code(raw: str) -> str:
    """Extract the tool module from the model's answer."""
    code = _code_from_answer(raw, "def ",
                             "Die Antwort enthält keine Funktionsdefinition.")
    if "def selbsttest(" not in code:
        raise T2GError("Dem Modul fehlt die Funktion `selbsttest()`.")
    return code


def build_skill_refine_prompt(name: str, params: list, current_code: str,
                              goal: str = "", project_block: str = "",
                              measurements: str = "",
                              previous_code: str = "",
                              problems: list | None = None) -> str:
    lines = [f"SKILL: {name}", "", "AKTUELLE PARAMETER"]
    for p in params:
        pname, label, unit, default, lo, hi = p[:6]
        lines.append(f"- {pname}: {label} [{unit}], default {default}, "
                     f"Bereich {lo} .. {hi}")
    lines += ["", "AKTUELLE build-FUNKTION", current_code.strip()]
    if measurements.strip():
        lines += ["", "SO BAUT SIE HEUTE", measurements.strip()]
    if project_block.strip():
        lines += ["", "PROJEKTZUSAMMENHANG (Gewichte beachten)", project_block.strip()]
    lines += ["", "VERBESSERUNGSAUFTRAG",
              goal.strip() or "Mach das Bauteil realistischer und robuster, "
                              "ohne die bestehende Schnittstelle zu brechen."]
    if previous_code and problems:
        lines += ["", "DEIN LETZTER VERSUCH SCHLUG FEHL", previous_code.strip(),
                  "", "FEHLER", *[f"- {p}" for p in problems],
                  "", "Korrigiere das und gib die vollständige Funktion erneut aus."]
    return "\n".join(lines)


def parse_skill_refinement(raw: str) -> "tuple[str, list]":
    """(code, params) -- params is empty when the model kept the interface."""
    text = raw or ""
    params: list = []
    m = re.search(r"```(?:parameter|params)[ \t]*\n(.*?)\n?[ \t]*```", text,
                  re.DOTALL | re.I)
    if m:
        params = parse_param_lines(m.group(1))
        text = text[:m.start()] + text[m.end():]   # keep it out of the code hunt
    code = parse_skill_code(text)
    return code, params


# ---------------------------------------------------------------------------
# Part 15: the agent behind the chat window
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """\
Du bist der Konstruktionsagent einer FreeCAD-Workbench. Der Benutzer sagt im
Chat, was er vorhat ("neues Zylinderkopfprojekt"). Du arbeitest das in kleinen,
überprüfbaren Schritten ab und legst dabei Projekt, Parameter, Abhängigkeiten,
Skills und Werkzeuge an.

Jede Antwort besteht aus GENAU EINEM Block:

```aktion
<eine Aktion pro Zeile - siehe Liste unten>
```

```maske
<Parameter, die der Benutzer ausfüllen soll, einer pro Zeile:
 name;Label;Einheit;Vorschlag;min;max
 Nimm das für alles Zahlenmäßige - Durchmesser, Winkel, Stückzahlen.
 Der Benutzer bekommt dafür eine Eingabemaske.>
```

```frage
<eine einzelne Verständnisfrage, nur wenn keine Zahl gefragt ist>
```

```python
<Code, der Geometrie im offenen FreeCAD-Dokument erzeugt oder ändert>
```

REGELN FÜR DEN ```python-BLOCK
- Erlaubt sind NUR: `import Part`, `import FreeCAD`, `import math`.
  Kein PartGui, kein Draft, kein Mesh, kein os - jeder andere Import bricht ab.
- Kein Zugriff auf FreeCAD.ActiveDocument, kein Part.show, kein print.
- Änderungen laufen ausschliesslich über diese Funktionen:
    names()        Namen der Objekte      selected()  aktuelle Auswahl
    shape(name)    Part.Shape einer Kopie info(name)  dict mit bbox, volume …
    add(shape, name="X")     neuen Körper anlegen
    replace(name, shape)     Geometrie eines vorhandenen Körpers ersetzen
    note(text)               Zeile ins Protokoll
- Rotationskörper: Profil aus Punkten -> `Part.makePolygon` -> `Part.Face`
  -> `.revolve(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), 360)`.
  Oder mehrere `Part.makeCone(r1, r2, h, FreeCAD.Vector(...))` verschmelzen
  (`.fuse`) und innen mit `.cut` aushöhlen.
- Beispiel:
```python
import Part, FreeCAD
aussen = Part.makeCone(10, 5, 40).fuse(
    Part.makeCone(5, 20, 60, FreeCAD.Vector(0, 0, 40)))
innen = Part.makeCone(8, 3, 40).fuse(
    Part.makeCone(3, 18, 60, FreeCAD.Vector(0, 0, 40)))
add(aussen.cut(innen), name="Duese")
```

```fertig
<kurze Zusammenfassung, wenn der Auftrag erledigt ist oder du auf den
 Benutzer wartest>
```

AKTIONEN
  projekt_anlegen: Titel
  baugruppe: Name;Teil1;Teil2;…   legt die Baugruppe mit Platzhaltern an
  auftrag: <Freitext, was gebaut wird - 3 bis 8 Sätze>
  recherche: Suchbegriff; wiki|web|beides
  parameter: name;Label;Einheit;Wert oder leer;min;max
  kriterium: name;Bedeutung
  skill_bedarf: name;Zweck
  werkzeug_bedarf: name;Zweck
  abhaengigkeit: Quelle;Ziel;nutzt|abgeleitet|passt_an;Anmerkung
  skills_kopieren:
  paarvergleich_vorschlagen:
  agent_d:
  skill_lernen: name
  werkzeug_erzeugen: name
  skill_bauen: name;param=wert;param=wert
  makro: Name                     ein vorhandenes FreeCAD-Makro ausführen
  befehl: FCGear_InvoluteGear     einen Add-on-Befehl auslösen
  werkzeug_aufrufen: modul.funktion;arg=wert
  verbindungen:                   Verbindungen im Dokument erkennen
  skill_verfeinern: name;Auftrag

ZU DEN ABHÄNGIGKEITEN
- `nutzt`: Parameter -> Bauteil ("ventil_d_ein;brennraum;nutzt;Ventilfenster").
- `abgeleitet`: Parameter -> Parameter ("ventil_d_ein;sitz_d;abgeleitet;0,88x").
- `passt_an`: Bauteil -> Bauteil, gilt in beide Richtungen.
Sie sind der Kern: Daraus weiß das System später, was nachzuziehen ist, wenn
sich ein Maß ändert. Trage sie ein, sobald du ein Bauteil oder einen Parameter
nennst.

WICHTIG: NUR DER ```aktion-BLOCK BEWIRKT ETWAS
Prosa bewirkt nichts. Schreibe nie, du habest etwas angelegt, wenn du es nicht
im selben Schritt als Aktion ausgegeben hast. ```fertig ist ausschliesslich für
den Schluss, wenn die Arbeit getan ist oder du auf den Benutzer wartest.

BEISPIEL für den ersten Schritt bei "neues Zylinderkopfprojekt":

```aktion
projekt_anlegen: Zylinderkopf
recherche: Zylinderkopf Ottomotor Aufbau Einlasskanal; beides
```

Im nächsten Schritt bekommst du das Rechercheergebnis zurück und schreibst dann
`auftrag:`, die `parameter:`, `kriterium:`, `skill_bedarf:` und die
`abhaengigkeit:`-Zeilen. Fehlende Maße erfragst du mit ```maske.

ARBEITSWEISE
- Erst denken, dann wenige Aktionen pro Schritt (höchstens 8).
- Reihenfolge: `projekt_anlegen` -> bei einer Baugruppe sofort `baugruppe:`
  mit allen genannten Teilen (die Struktur steht zuerst, gefüllt wird später)
  -> recherchieren -> `auftrag` -> globale `parameter` und `kriterium`
  -> `skill_bedarf`/`werkzeug_bedarf` -> `abhaengigkeit` -> `agent_d`.
- Sobald ein Skill fertig ist, ihn mit `skill_bauen` ins Dokument setzen -
  was man nicht sieht, kann der Benutzer nicht beurteilen.
- Nach dem Bauen prüfen, was die Rückmeldung sagt: Zahl der Solids, Volumen,
  Hinweise. Schlägt etwas fehl, den Fehler lesen und im nächsten Schritt
  beheben (Parameter korrigieren, `skill_verfeinern`, oder einen berichtigten
  ```python-Block) - nicht einfach weitermachen und nicht behaupten, es sei
  gebaut.
- Der GESPRÄCHSVERLAUF steht im Prompt. Frage nie nach etwas, das dort schon
  beantwortet ist - nenne stattdessen, was du verstanden hast, und handle.
- Was du nicht sicher weißt und was eine Zahl ist: ```maske. Keine erfundenen
  Maße als gesetzt ausgeben - offene Felder leer lassen.
- `skill_lernen`, `werkzeug_erzeugen`, `skill_verfeinern` dauern Minuten.
  Frage vorher nach, statt mehrere davon ungefragt hintereinander zu starten.
- Vorhandene Skills wiederverwenden (`skills_kopieren`), statt alles neu zu
  lernen. Dasselbe gilt für die Werkzeuge dieser Installation: Zahnräder macht
  das Add-on besser als ein neuer Skill (`befehl: FCGear_InvoluteGear`), und
  `verbindungen:` prüft die Baugruppe, statt das nachzubauen. Die verfügbaren
  Werkzeuge stehen im Prompt unter WERKZEUGE.
- Nach jedem Schritt bekommst du die Ergebnisse zurück. Reagiere darauf;
  wiederhole keine Aktion, die schon OK gemeldet hat.
- Deutsche Bezeichner ohne Umlaute für Namen (einlasskanal, ventil_d_ein).
"""


SUMMARY_PROMPT = """\
Du verdichtest den bisherigen Gesprächsverlauf einer Konstruktionssitzung.

Gib nur die Dinge zurück, die für die weitere Arbeit noch gebraucht werden -
knapp, als Stichpunkte, höchstens 12 Zeilen:

- Was gebaut werden soll (ein Satz).
- Festgelegte Namen und Listen (Bauteile einer Baugruppe, Skill-Namen).
- Zugesagte Zahlen mit Einheit.
- Entscheidungen ("Auslasskanal kürzer als Einlasskanal").
- Offene Punkte, die noch geklärt werden müssen.

Weglassen: Höflichkeiten, Wiederholungen, bereits erledigte Schritte,
Fehlermeldungen, alles was ohnehin im Projektzustand steht.

WICHTIG: Punkte, zu denen es nichts zu sagen gibt, LÄSST DU WEG. Schreibe
niemals Zeilen wie "Zahlen: keine" oder "Entscheidungen: keine" - eine kurze
Liste ist besser als eine vollständige mit Leermeldungen. Gibt es gar nichts
Erhaltenswertes, antworte mit einer einzigen Zeile: "- nichts Offenes".

Antworte ohne Vorrede mit den Stichpunkten selbst.
"""


def build_summary_prompt(transcript: str, previous: str = "") -> str:
    parts = []
    if previous.strip():
        parts += ["BISHERIGE ZUSAMMENFASSUNG (einarbeiten, nichts verlieren)",
                  previous.strip(), ""]
    parts += ["ZU VERDICHTENDER VERLAUF", transcript.strip()]
    return "\n".join(parts)


def build_agent_system_prompt(action_help: str = "") -> str:
    """The system prompt, optionally with the live action list appended."""
    if not action_help.strip():
        return AGENT_SYSTEM_PROMPT
    return (AGENT_SYSTEM_PROMPT
            + "\nIN DIESER SITZUNG VERFÜGBAR\n" + action_help.rstrip() + "\n")


# ---------------------------------------------------------------------------
# Part 10: sandbox exec
# ---------------------------------------------------------------------------

_ALLOWED_MODULES = frozenset({"Part", "FreeCAD", "math", "Units", "Materials"})


class _RestrictedImporter:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _ALLOWED_MODULES:
            return None
        raise ImportError(f"T2G sandbox: module {fullname!r} not allowed")


def _exec_restricted(code: str, extra_ns: dict | None = None) -> dict:
    """Compile and run model code under the import allow-list.

    Returns the namespace it ran in. ``extra_ns`` adds callables the code may
    use (the document API of the conversational mode); it never gives access
    to the document itself -- those functions only record what to do.
    """
    if not code or not code.strip():
        raise T2GError("Empty code block.")
    for name in _iter_import_names(code):
        if name.split(".")[0] not in _ALLOWED_MODULES:
            raise T2GError(f"Disallowed import in generated code: {name!r}")
    ns: dict = {}
    # Deliberately absent: open, eval, exec, compile, input, globals, locals,
    # vars, dir, type, getattr, setattr. Generated geometry code has no use for
    # them, and leaving them out keeps ordinary mistakes from touching the
    # system. See the note on the sandbox boundary in DOKUMENTATION.md.
    ns["__builtins__"] = {
        "abs": abs, "min": min, "max": max, "len": len, "range": range,
        "enumerate": enumerate, "zip": zip, "list": list, "tuple": tuple,
        "set": set, "dict": dict, "str": str, "int": int, "float": float,
        "bool": bool, "True": True, "False": False, "None": None,
        "round": round, "sum": sum, "sorted": sorted, "reversed": reversed,
        "any": any, "all": all, "map": map, "filter": filter,
        "divmod": divmod, "pow": pow, "hasattr": hasattr,
        "isinstance": isinstance, "repr": repr, "format": format,
        "slice": slice, "frozenset": frozenset,
        "print": lambda *a, **k: None,
        "Exception": Exception, "ValueError": ValueError,
        "TypeError": TypeError, "ImportError": ImportError,
        "ZeroDivisionError": ZeroDivisionError, "IndexError": IndexError,
        "KeyError": KeyError, "AttributeError": AttributeError,
        "ArithmeticError": ArithmeticError, "RuntimeError": RuntimeError,
        "StopIteration": StopIteration, "AssertionError": AssertionError,
        "__import__": _make_import(),
    }
    if extra_ns:
        ns.update(extra_ns)
    try:
        compiled = compile(code, "<t2g-generated>", "exec")
    except SyntaxError as e:
        raise T2GError(f"Syntax error in generated code: {e}") from e
    hook = _RestrictedImporter()
    import sys
    meta = sys.meta_path
    meta.insert(0, hook)
    try:
        exec(compiled, ns)
    finally:
        try:
            meta.remove(hook)
        except ValueError:
            pass
    return ns


def exec_code_in_sandbox(code: str) -> list:
    """Execute model code in a restricted namespace; return list of shapes."""
    ns = _exec_restricted(code)
    if "result" not in ns:
        raise T2GError("Generated code did not define a top-level `result` variable.")
    result = ns["result"]
    if result is None:
        raise T2GError("Generated code set `result` to None.")
    if isinstance(result, (list, tuple)):
        return list(result)
    return [result]


def _make_import():
    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0:
            raise ImportError("Relative imports are not allowed in T2G sandbox.")
        top = name.split(".")[0]
        if top not in _ALLOWED_MODULES:
            raise ImportError(f"Module {name!r} is not in the T2G allow-list.")
        return __import__(name, globals, locals, fromlist, level)
    return _import


def _iter_import_names(code: str):
    yield from re.findall(r"^\s*import\s+([A-Za-z_][A-Za-z_0-9\.]*)", code, re.M)
    for m in re.finditer(r"^\s*from\s+([A-Za-z_][A-Za-z_0-9\.]*)\s+import\b", code, re.M):
        yield m.group(1)


# ---------------------------------------------------------------------------
# Convenience single-shot
# ---------------------------------------------------------------------------

def _generate_once(prompt: str, *, api_config: APIConfig | None = None
                   ) -> tuple[str, object]:
    """One prompt -> (code, shapes). Used as generate_fn for run_sweep()."""
    if api_config is not None:
        return generate_via_api(prompt, cfg=api_config)
    pi = find_pi_binary()
    raw = run_backend(prompt, pi_binary=pi)
    code = extract_code_block(raw)
    shapes = exec_code_in_sandbox(code)
    return code, shapes


def generate(prompt: str, *, pi_binary: str | None = None,
             provider: str = "ollama", model: str = "qwen-gross:latest",
             timeout_s: int = 120,
             api_config: APIConfig | None = None) -> tuple[str, list]:
    """Backwards-compatible single-prompt generation (code, shapes).

    Pass ``api_config`` to route the prompt through an external
    LLM API endpoint (OpenAI-compatible or Ollama) instead of the
    ``pi`` CLI.
    """
    if api_config is not None:
        return generate_via_api(prompt, cfg=api_config)
    pi = pi_binary or find_pi_binary()
    raw = run_backend(prompt, pi_binary=pi, provider=provider,
                      model=model, timeout_s=timeout_s)
    code = extract_code_block(raw)
    shapes = exec_code_in_sandbox(code)
    return code, shapes


__all__ = [
    "T2GError", "BackendError",
    "SYSTEM_PROMPT",
    "find_pi_binary", "find_pi_binary_or_none", "run_backend",
    "extract_code_block", "extract_message_text",
    "AGENT_SYSTEM_PROMPT", "build_agent_system_prompt",
    "SUMMARY_PROMPT", "build_summary_prompt",
    "TOOL_CODE_PROMPT", "build_tool_prompt", "parse_tool_code",
    "SKILL_REFINE_PROMPT", "build_skill_refine_prompt", "parse_skill_refinement",
    "PROJECT_PLAN_PROMPT", "PROJECT_PAIRS_PROMPT", "parse_project_plan",
    "parse_pair_suggestions", "build_project_plan_prompt",
    "build_project_pairs_prompt",
    "html_to_text", "web_fetch", "web_search", "wikipedia_search",
    "is_count_unit", "COUNT_UNITS",
    "research_topic",
    "ResearchResult", "SKILL_ANALYSE_PROMPT", "SKILL_CODE_PROMPT",
    "build_skill_analyse_prompt", "build_skill_code_prompt",
    "parse_skill_analysis", "parse_skill_code", "parse_param_lines",
    "CHAT_SYSTEM_PROMPT", "describe_document", "ChatSession", "ChatTurn",
    "ChatReply", "parse_chat_reply", "OpRecorder", "exec_chat_code",
    "chat_backend",
    "OLLAMA_DEFAULT_URL", "probe_ollama", "ollama_running", "start_ollama",
    "openai_models", "pi_models", "list_models", "call_model",
    "call_model_verbose", "extract_thinking", "split_thinking",
    "THINKING_LEVELS", "with_thinking",
    "backend_status", "detect_backend",
    "exec_code_in_sandbox", "generate",
    "Target", "Measurement", "measure_shape", "build_prompt",
    "read_table_csv", "read_table_xlsx", "read_table_ssheet", "read_table_paste",
    "VariantResult", "SweepConfig", "run_sweep",
    "export_results_csv",
    "APIConfig", "run_api", "generate_via_api",
]
