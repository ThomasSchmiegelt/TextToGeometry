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

    kind: str = "openai"            # "openai" | "ollama"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen-gross:latest"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 8192
    timeout_s: int = 180

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "base_url": self.base_url,
            "model": self.model, "api_key": self.api_key,
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


def _t2g_api_call(cfg: APIConfig, system_prompt: str, user_prompt: str) -> str:
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
    else:
        choices = payload.get("choices") or []
        if not choices:
            raise T2GError(f"API returned no choices: {str(payload)[:300]}")
        text = (choices[0].get("message") or {}).get("content", "")
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


def find_pi_binary(preferred: str | None = None) -> str:
    """Locate the `pi` CLI. Honors T2G_PI_BIN, then PATH."""
    if preferred:
        return preferred
    env = os.environ.get("T2G_PI_BIN")
    if env:
        if os.path.isfile(env) and os.access(env, os.X_OK):
            return env
        raise BackendError(f"T2G_PI_BIN points to a non-executable: {env}")
    which = shutil.which("pi")
    if not which:
        raise BackendError(
            "Could not find `pi` on PATH. Install with "
            "`npm install -g --ignore-scripts @earendil-works/pi-coding-agent` "
            "or set T2G_PI_BIN to the binary."
        )
    return which


def run_backend(
    prompt: str,
    *,
    pi_binary: str,
    provider: str = "ollama",
    model: str = "qwen-gross:latest",
    system_prompt: str = SYSTEM_PROMPT,
    timeout_s: int = 120,
    env_extra: dict | None = None,
) -> str:
    """Invoke `pi -p --mode json` and return the raw NDJSON stream."""
    if not prompt or not prompt.strip():
        raise BackendError("Empty prompt.")
    cmd = [
        pi_binary,
        "--provider", provider,
        "--model", model,
        "--system-prompt", system_prompt,
        "--no-tools", "--no-extensions", "--no-skills", "--no-themes",
        "--no-prompt-templates", "--no-context-files", "--no-session",
        "-p", "--mode", "json",
        "--", prompt,
    ]
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
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


def extract_code_block(stream: str) -> str:
    """Parse the pi NDJSON stream and return the assistant code block."""
    if not stream:
        raise T2GError("Empty response from backend.")
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
# Part 10: sandbox exec
# ---------------------------------------------------------------------------

_ALLOWED_MODULES = frozenset({"Part", "FreeCAD", "math", "Units", "Materials"})


class _RestrictedImporter:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _ALLOWED_MODULES:
            return None
        raise ImportError(f"T2G sandbox: module {fullname!r} not allowed")


def exec_code_in_sandbox(code: str) -> list:
    """Execute model code in a restricted namespace; return list of shapes."""
    if not code or not code.strip():
        raise T2GError("Empty code block.")
    for name in _iter_import_names(code):
        if name.split(".")[0] not in _ALLOWED_MODULES:
            raise T2GError(f"Disallowed import in generated code: {name!r}")
    ns: dict = {}
    ns["__builtins__"] = {
        "abs": abs, "min": min, "max": max, "len": len, "range": range,
        "enumerate": enumerate, "zip": zip, "list": list, "tuple": tuple,
        "set": set, "dict": dict, "str": str, "int": int, "float": float,
        "bool": bool, "True": True, "False": False, "None": None,
        "print": lambda *a, **k: None,
        "Exception": Exception, "ValueError": ValueError,
        "TypeError": TypeError, "ImportError": ImportError,
        "__import__": _make_import(),
    }
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
    "find_pi_binary", "run_backend", "extract_code_block",
    "exec_code_in_sandbox", "generate",
    "Target", "Measurement", "measure_shape", "build_prompt",
    "read_table_csv", "read_table_xlsx", "read_table_ssheet", "read_table_paste",
    "VariantResult", "SweepConfig", "run_sweep",
    "export_results_csv",
    "APIConfig", "run_api", "generate_via_api",
]
