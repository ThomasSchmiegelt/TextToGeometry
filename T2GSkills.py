# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary

"""TextToGeometry – Skills engine.

A *Skill* is a deterministic, parameterized geometry generator: a small
Python module that exposes

    T2G_SKILL = {
        "name":         str,
        "description":  str,
        "params":       [ (name, label, unit, default, min, max), ... ],
        "dependencies": [ "Part", ... ],
        "pruefregeln":  [ "kollision", "konnektivitaet", ... ],
    }

    def build(params: dict) -> list:
        # Return a list of Part.Shape solids built purely from ``params``.
        ...

Skills live in ``<addon>/Skills/<name>/<name>.py``.  This module scans that
directory (or an arbitrary one), loads each module in a restricted namespace
(Part / FreeCAD / math), validates parameters and calls ``build()``.

No GUI code here; the dialog in T2GCommand.py uses this module.
"""

from __future__ import annotations

import builtins as _py_builtins
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

__all__ = [
    "SkillError",
    "SkillParam",
    "SkillDefinition",
    "LoadedSkill",
    "SkillRegistry",
    "SkillEngine",
    "describe_skills",
    "validate_params",
    "apply_rules",
    "check_kollision",
    "check_konnektivitaet",
    "create_skill",
    "delete_skill",
    "get_engine",
    "load_skill_file",
]


class SkillError(Exception):
    """Raised for invalid parameters or failed skill loading/building."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SkillParam:
    """One named, ranged, unit-tagged parameter of a skill.

    ``min`` / ``max`` are inclusive. ``kind`` is ``"int"`` or ``"float"`` and
    is inferred from the default value unless overridden.
    """

    name: str
    label: str
    unit: str = ""
    default: object = 0
    min: object = None
    max: object = None
    kind: str = "float"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name or ""):
            raise SkillError(f"Bad parameter name: {self.name!r}")
        if self.kind not in ("int", "float"):
            raise SkillError(f"Bad parameter kind: {self.kind!r}")
        if self.kind == "int" and isinstance(self.default, int):
            pass
        if self.min is not None and self.max is not None:
            if self.min > self.max:
                raise SkillError(f"param {self.name}: min {self.min} > max {self.max}")

    def cast(self, value: object) -> object:
        try:
            if self.kind == "int":
                f = float(value)
                if abs(f - round(f)) > 1e-9:
                    raise ValueError(f"{self.name} must be an integer")
                return int(round(f))
            return float(value)
        except (TypeError, ValueError) as e:
            raise SkillError(f"param {self.name}: {e}") from e

    def range_error(self, value: object) -> Optional[str]:
        if self.min is not None and value < self.min:
            return f"{self.name}={value} < min {self.min}"
        if self.max is not None and value > self.max:
            return f"{self.name}={value} > max {self.max}"
        return None


def _param_from_tuple(p) -> SkillParam:
    name, label, unit, default = p[0], p[1], p[2], p[3]
    lo = p[4] if len(p) > 4 else None
    hi = p[5] if len(p) > 5 else None
    kind = "int" if isinstance(default, int) else "float"
    return SkillParam(name=name, label=label, unit=unit or "",
                      default=default, min=lo, max=hi, kind=kind)


@dataclass
class SkillDefinition:
    name: str
    description: str = ""
    params: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    pruefregeln: list = field(default_factory=list)
    achse: str = "z"        # axis the part is built along: x | y | z
    path: str = ""          # absolute path of the skill .py file
    file: str = ""          # file name (e.g. "bruecke.py")


@dataclass
class LoadedSkill:
    definition: SkillDefinition
    build: Callable[[dict], list]     # (params dict) -> list[Shape]
    namespace: dict = field(repr=False, default_factory=dict)
    source: str = field(default="", repr=False)

    @property
    def name(self) -> str:
        return self.definition.name


# ---------------------------------------------------------------------------
# Restricted namespace for skill modules
# ---------------------------------------------------------------------------

_SKILL_BUILTINS = {
    "abs": abs, "min": min, "max": max, "len": len, "range": range,
    "enumerate": enumerate, "zip": zip, "list": list, "tuple": tuple,
    "set": set, "dict": dict, "str": str, "int": int, "float": float,
    "bool": bool, "round": round, "sum": sum, "sorted": sorted, "print": lambda *a, **k: None,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "RuntimeError": RuntimeError,
    "AttributeError": AttributeError,
}


#: Modules a skill may import. Part/FreeCAD are what the geometry needs;
#: everything else (os, subprocess, socket, ...) is refused.
_ALLOWED_IMPORTS = ("math", "Part", "FreeCAD")


def _safe_import(name, *a, **k):
    if name.split(".")[0] in _ALLOWED_IMPORTS:
        return _py_builtins.__import__(name, *a, **k)
    raise ImportError(f"import of {name!r} is not allowed inside a skill")


def _skill_namespace() -> dict:
    # `import x` resolves __import__ through __builtins__, never through the
    # globals dict -- so the guard has to live in __builtins__ to have any
    # effect at all.
    guarded_builtins = dict(_SKILL_BUILTINS)
    guarded_builtins["__import__"] = _safe_import
    ns = dict(_SKILL_BUILTINS)
    ns["__builtins__"] = guarded_builtins
    ns["__import__"] = _safe_import
    try:
        ns["math"] = _py_builtins.__import__("math")
    except Exception:
        pass
    for name in ("Part", "FreeCAD"):
        try:
            mod = sys.modules.get(name)
            if mod is None:
                mod = _py_builtins.__import__(name)
            ns[name] = mod
        except Exception:
            # Part / FreeCAD are optional in pure-python test contexts; a skill
            # that actually needs them will fail at build() time with a clear
            # message, not at import time.
            pass
    return ns


def load_skill_file(path: str) -> LoadedSkill:
    """Load one skill module from ``path`` (a ``<name>.py`` file)."""
    if not os.path.isfile(path):
        raise SkillError(f"Skill file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()
    ns = _skill_namespace()
    try:
        code = compile(source, path, "exec")
    except SyntaxError as e:
        raise SkillError(f"Syntax error in {os.path.basename(path)}: {e}") from e
    try:
        exec(code, ns)
    except Exception as e:
        raise SkillError(f"Error loading skill {os.path.basename(path)}: {e}") from e

    meta = ns.get("T2G_SKILL")
    if not isinstance(meta, dict):
        raise SkillError(f"{os.path.basename(path)}: missing T2G_SKILL dict")
    build = ns.get("build")
    if not callable(build):
        raise SkillError(f"{os.path.basename(path)}: missing callable build(params)")

    name = str(meta.get("name") or os.path.splitext(os.path.basename(path))[0])
    params = [_param_from_tuple(p) for p in (meta.get("params") or [])]
    seen = set()
    for p in params:
        if p.name in seen:
            raise SkillError(f"{name}: duplicate parameter {p.name!r}")
        seen.add(p.name)

    definition = SkillDefinition(
        name=name,
        description=str(meta.get("description") or "").strip(),
        params=params,
        dependencies=list(meta.get("dependencies") or []),
        pruefregeln=list(meta.get("pruefregeln") or []),
        achse=str(meta.get("achse") or "z").strip().lower()[:1] or "z",
        path=os.path.abspath(path),
        file=os.path.basename(path),
    )
    return LoadedSkill(definition=definition, build=build,
                       namespace=ns, source=source)


def describe_skills(skills, limit_params: int = 8) -> str:
    """What a skill builds, along which axis, and with which parameters.

    The agent used to get bare names. It then had no way to know that
    ``gehaeuse`` places its shaft bores along X while it had laid the gearbox
    out along Z -- no amount of translating can fix that, and four builds in a
    row landed beside the assembly.
    """
    zeilen = []
    for sk in skills:
        d = sk.definition if hasattr(sk, "definition") else sk
        kopf = "- %s (Achse %s)" % (d.name, d.achse.upper())
        if d.description:
            kopf += ": " + d.description.strip().splitlines()[0]
        zeilen.append(kopf)
        for q in d.params[:limit_params]:
            einheit = ("" if q.unit in ("", "-") else " " + q.unit)
            zeile = "    %s = %s%s" % (q.name, q.default, einheit)
            # The label says which direction a measure runs in
            # ("Innenlaenge (Wellenachse)") -- without it the agent guessed,
            # and built a 24 mm housing around a 100 mm gearbox.
            if q.label and q.label.lower() != q.name.lower():
                zeile += "  — " + q.label
            zeilen.append(zeile)
        if len(d.params) > limit_params:
            zeilen.append("    … %d weitere Parameter"
                          % (len(d.params) - limit_params))
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_params(definition: SkillDefinition,
                    values: dict | None = None) -> dict:
    """Fill in defaults, enforce ranges, and cast to the declared kind."""
    values = dict(values or {})
    out: dict = {}
    for p in definition.params:
        raw = values.get(p.name, p.default)
        v = p.cast(raw)
        err = p.range_error(v)
        if err:
            raise SkillError(err)
        out[p.name] = v
    # ignore unknown keys rather than hard-failing (robustness for LLM input)
    return out


# ---------------------------------------------------------------------------
# Pruefregeln (deterministic checks on the produced solids)
# ---------------------------------------------------------------------------

def _bounds(shp):
    b = shp.BoundBox
    return (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)


#: An overlap counts as a genuine collision only when it is larger than this
#: fraction of the *thinner* of the two solids.  Truss members share their
#: end-caps at the nodes they meet (that is what connects the frame), so a
#: small cap overlap is expected and must not be reported.
_NODE_TOL_RATIO = 0.25


def check_kollision(shapes: list) -> list:
    """Report genuine pairwise collisions (substantive volume overlap).

    Small overlaps at shared nodes (<= :data:`_NODE_TOL_RATIO` of the thinner
    member) are treated as legitimate connections and ignored.
    """
    problems = []
    n = len(shapes)
    vols = [float(getattr(s, "Volume", 0.0) or 0.0) for s in shapes]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = shapes[i], shapes[j]
            try:
                ov = a.common(b)
                vol = float(getattr(ov, "Volume", 0.0) or 0.0)
            except Exception:
                vol = 0.0
            if vol <= 1e-6:
                continue
            thinner = min(vols[i], vols[j])
            if thinner > 0 and vol / thinner > _NODE_TOL_RATIO:
                problems.append(
                    f"kollision: solids {i} & {j} overlap {vol:.0f} mm^3 "
                    f"({vol / thinner * 100:.0f}% of thinner)")
    return problems


def _connected_by_bounds(shapes: list) -> bool:
    """Bounding-box intersection graph must be a single connected component."""
    n = len(shapes)
    if n <= 1:
        return True
    boxes = [_bounds(s) for s in shapes]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if (a[0] <= b[3] and a[3] >= b[0] and
                    a[1] <= b[4] and a[4] >= b[1] and
                    a[2] <= b[5] and a[5] >= b[2]):
                union(i, j)
    root = find(0)
    return all(find(k) == root for k in range(n))


def check_konnektivitaet(shapes: list) -> list:
    problems = []
    if not shapes:
        problems.append("konnektivitaet: keine Solids")
        return problems
    if not _connected_by_bounds(shapes):
        problems.append("konnektivitaet: Baugruppe nicht zusammenhaengend")
    return problems


def apply_rules(definition: SkillDefinition, shapes: list) -> list:
    """Run every declared prüfgregel and return the concatenated problems."""
    problems = []
    for rule in definition.pruefregeln:
        if rule == "kollision":
            problems.extend(check_kollision(shapes))
        elif rule == "konnektivitaet":
            problems.extend(check_konnektivitaet(shapes))
        # unknown rules are ignored (forward compatible)
    return problems


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    def __init__(self) -> None:
        self._skills: "Dict[str, LoadedSkill]" = {}

    def add(self, skill: LoadedSkill, replace: bool = True) -> None:
        key = skill.definition.name
        if key not in self._skills or replace:
            self._skills[key] = skill

    def get(self, name: str) -> LoadedSkill:
        try:
            return self._skills[name]
        except KeyError:
            raise SkillError(f"unknown skill: {name!r}") from None

    def names(self) -> list:
        return list(self._skills.keys())

    def items(self):
        return list(self._skills.values())

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name) -> bool:
        return name in self._skills


# ---------------------------------------------------------------------------
# Engine (registry + directory loading + build)
# ---------------------------------------------------------------------------

class SkillEngine:
    """Loads skills from a directory and builds geometry from parameters."""

    def __init__(self, skills_dir: str | None = None) -> None:
        self.skills_dir = skills_dir or self._default_skills_dir()
        self.registry = SkillRegistry()

    @staticmethod
    def _default_skills_dir() -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Skills")

    def load_all(self) -> "SkillEngine":
        self.registry = SkillRegistry()
        if not os.path.isdir(self.skills_dir):
            return self
        for entry in sorted(os.listdir(self.skills_dir)):
            sub = os.path.join(self.skills_dir, entry)
            if not os.path.isdir(sub):
                continue
            candidate = os.path.join(sub, entry + ".py")
            if os.path.isfile(candidate):
                try:
                    self.load(candidate)
                except SkillError:
                    continue
        return self

    def load(self, path: str) -> LoadedSkill:
        skill = load_skill_file(path)
        self.registry.add(skill)
        return skill

    def build(self, name: str, values: dict | None = None) -> tuple[list, dict, list]:
        """Build geometry for ``name`` with given values.

        Returns ``(shapes, validated_params, problems)``.
        """
        skill = self.registry.get(name)
        vals = validate_params(skill.definition, values)
        shapes = skill.build(vals)
        if not isinstance(shapes, (list, tuple)):
            shapes = [shapes]
        problems = apply_rules(skill.definition, list(shapes))
        return list(shapes), vals, problems


# convenience module-level engine (lazy)
_DEFAULT_ENGINE: Optional[SkillEngine] = None


def get_engine(skills_dir: str | None = None) -> SkillEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None or (skills_dir and
                                  _DEFAULT_ENGINE.skills_dir != skills_dir):
        _DEFAULT_ENGINE = SkillEngine(skills_dir).load_all()
    return _DEFAULT_ENGINE


# ---------------------------------------------------------------------------
# Validating a generated skill before it is written to disk
# ---------------------------------------------------------------------------

def validate_skill_source(name: str, params: list, build_code: str,
                          pruefregeln: list | None = None,
                          run_build: bool = True) -> tuple:
    """Check a generated skill without saving it.

    Returns ``(problems, shapes)``: ``problems`` is empty when the skill
    compiled, ran with its default parameters and produced solids. Used by the
    learn-a-skill loop to feed real errors back to the model.
    """
    problems: list = []
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        problems.append(f"Ungültiger Skill-Name: {name!r}")
    if "def build(" not in (build_code or ""):
        problems.append("Der Code enthält keine Funktion `def build(params):`.")
        return problems, []
    try:
        norm = [p if isinstance(p, SkillParam) else _param_from_tuple(p)
                for p in (params or [])]
    except Exception as e:  # noqa: BLE001
        problems.append(f"Parameterliste fehlerhaft: {e}")
        return problems, []
    if not norm:
        problems.append("Kein einziger Parameter definiert.")
        return problems, []
    for p in norm:
        if p.min is not None and p.max is not None and p.min > p.max:
            problems.append(f"Parameter {p.name}: min > max")

    ns = _skill_namespace()
    try:
        code = compile(build_code, "<gelernter-skill>", "exec")
        exec(code, ns)
    except SyntaxError as e:
        problems.append(f"Syntaxfehler: {e}")
        return problems, []
    except Exception as e:  # noqa: BLE001
        problems.append(f"Code ließ sich nicht laden: {type(e).__name__}: {e}")
        return problems, []

    build = ns.get("build")
    if not callable(build):
        problems.append("`build` ist keine Funktion.")
        return problems, []

    definition = SkillDefinition(
        name=name or "skill", description="", params=norm,
        dependencies=["Part"], pruefregeln=list(pruefregeln or []))

    if not run_build:
        return problems, []

    # Unused parameters are a strong hint the geometry ignores the inputs.
    used = [p.name for p in norm if p.name in build_code]
    missing = [p.name for p in norm if p.name not in used]
    if missing:
        problems.append("Diese Parameter kommen im Code nicht vor: "
                        + ", ".join(missing))

    try:
        values = validate_params(definition, {})
        shapes = build(values)
    except Exception as e:  # noqa: BLE001
        problems.append(f"build() mit Standardwerten scheiterte: "
                        f"{type(e).__name__}: {e}")
        return problems, []

    if not isinstance(shapes, (list, tuple)):
        shapes = [shapes]
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        problems.append("build() lieferte keine Solids zurück.")
        return problems, []
    for i, shp in enumerate(shapes):
        vol = getattr(shp, "Volume", None)
        if vol is not None and vol <= 0:
            problems.append(f"Solid {i + 1} hat kein positives Volumen ({vol}).")
    try:
        problems.extend(apply_rules(definition, list(shapes)))
    except Exception as e:  # noqa: BLE001
        problems.append(f"Prüfregeln fehlgeschlagen: {e}")
    return problems, list(shapes)


# ---------------------------------------------------------------------------
# Skill creator (writes a new skill module)
# ---------------------------------------------------------------------------

_HEADER = '''# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
'''


def _param_lines(params: list) -> str:
    lines = []
    for p in params:
        if isinstance(p, SkillParam):
            name, label, unit, default, lo, hi = p.name, p.label, p.unit, p.default, p.min, p.max
        else:
            name, label, unit, default, lo, hi = p[:6]
        lines.append(f"        ({name!r}, {label!r}, {unit!r}, {default!r}, "
                     f"{lo!r}, {hi!r}),")
    return "\n".join(lines)


def create_skill(name: str, description: str, params: list,
                 build_code: str, pruefregeln: list = ("kollision", "konnektivitaet"),
                 out_dir: str | None = None) -> str:
    """Write a new skill module into ``<out_dir>/<name>/<name>.py``.

    Returns the absolute path of the created file.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise SkillError(f"Invalid skill name: {name!r}")
    norm = [p if isinstance(p, SkillParam) else _param_from_tuple(p) for p in params]
    for p in norm:
        if p.min is not None and p.max is not None and p.min > p.max:
            raise SkillError(f"param {p.name}: min > max")
    if "def build(" not in build_code:
        raise SkillError("build_code must define `def build(params)`.")

    try:
        compile(build_code, "<build>", "exec")
    except SyntaxError as e:
        raise SkillError(f"build_code has a syntax error: {e}") from e

    rules = ", ".join(repr(r) for r in list(pruefregeln))
    meta = (
        "\nT2G_SKILL = {\n"
        f'    "name": {name!r},\n'
        f'    "description": {description!r},\n'
        "    \"params\": [\n"
        + _param_lines(norm) + "\n"
        "    ],\n"
        f'    "dependencies": ["Part"],\n'
        f'    "pruefregeln": [{rules}],\n'
        "}\n\n"
    )
    out = os.path.join(out_dir or _default_skills_dir_static(), name)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name + ".py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_HEADER + meta + "\n" + build_code.strip() + "\n")
    return path


def skill_path(name: str, out_dir: str | None = None) -> str:
    """Where a skill's module lives (whether or not it exists yet)."""
    base = out_dir or _default_skills_dir_static()
    return os.path.join(base, name, name + ".py")


def build_source(skill: "LoadedSkill | str") -> str:
    """Just the build() part of a skill module -- what a refinement rewrites."""
    src = skill if isinstance(skill, str) else skill.source
    i = src.find("def build(")
    return src[i:].strip() if i >= 0 else src.strip()


def backup_skill(name: str, out_dir: str | None = None) -> "str | None":
    """Copy a skill aside before it is overwritten; returns the backup path."""
    path = skill_path(name, out_dir)
    if not os.path.isfile(path):
        return None
    import time
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(os.path.dirname(path), f"{name}.{stamp}.py.bak")
    shutil_ = __import__("shutil")
    shutil_.copyfile(path, dest)
    return dest


def update_skill(name: str, description: str, params: list, build_code: str,
                 pruefregeln: list = ("kollision", "konnektivitaet"),
                 out_dir: str | None = None) -> tuple:
    """Replace an existing skill, keeping the previous version as a backup.

    Returns ``(path, backup_path_or_None)``.
    """
    backup = backup_skill(name, out_dir)
    try:
        path = create_skill(name, description, params, build_code,
                            pruefregeln=pruefregeln, out_dir=out_dir)
    except Exception:
        if backup:  # put the old one back rather than leaving a hole
            shutil_ = __import__("shutil")
            shutil_.copyfile(backup, skill_path(name, out_dir))
        raise
    return path, backup


def _default_skills_dir_static() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "Skills")


def list_backups(name: str, out_dir: str | None = None) -> list:
    """Previous versions of a skill, newest first."""
    d = os.path.dirname(skill_path(name, out_dir))
    if not os.path.isdir(d):
        return []
    return sorted((os.path.join(d, f) for f in os.listdir(d)
                   if f.startswith(name + ".") and f.endswith(".py.bak")),
                  reverse=True)


def delete_skill(name: str, out_dir: str | None = None) -> bool:
    out = os.path.join(out_dir or _default_skills_dir_static(), name)
    if not os.path.isdir(out):
        return False
    import shutil
    shutil.rmtree(out)
    return True
