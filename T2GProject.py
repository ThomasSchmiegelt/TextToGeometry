# SPDX-License-Identifier: LGPL-2.1-or-later
"""Project workspace for TextToGeometry.

A *project* is a directory that keeps everything belonging to one construction
job together: the brief (what is to be built), the weighted criteria it has to
satisfy, the skills that build its parts and the helper tools it needs.

Layout::

    <projekt>/
        projekt.json            machine-readable state (this module owns it)
        agent.d/                the brief, split into numbered markdown files
            00-auftrag.md       what is to be built (from the dialogue)
            10-anforderungen.md criteria + weights from the pairwise comparison
            20-skills.md        which skills exist, which must be built
            30-werkzeuge.md     helper tools
        skills/<name>/<name>.py project-local skills (copied or learned)
        tools/<name>.py         helper code
        bewertung/paarvergleich.csv   the comparison matrix, spreadsheet-readable

Standard library only: importable and testable without FreeCAD.
"""

from __future__ import annotations

import csv
import datetime
import difflib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field

PROJECT_FILE = "projekt.json"
AGENT_DIR = "agent.d"
SKILLS_DIR = "skills"
TOOLS_DIR = "tools"
EVAL_DIR = "bewertung"
MATRIX_FILE = "paarvergleich.csv"

#: Saaty's comparison scale: label plus the a_ij it stands for.
SAATY_SCALE = [
    ("A absolut wichtiger", 9.0),
    ("A sehr viel wichtiger", 7.0),
    ("A deutlich wichtiger", 5.0),
    ("A etwas wichtiger", 3.0),
    ("gleich wichtig", 1.0),
    ("B etwas wichtiger", 1.0 / 3.0),
    ("B deutlich wichtiger", 1.0 / 5.0),
    ("B sehr viel wichtiger", 1.0 / 7.0),
    ("B absolut wichtiger", 1.0 / 9.0),
]

#: Saaty's random index, for the consistency ratio.
_RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24,
                 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49, 11: 1.51, 12: 1.48,
                 13: 1.56, 14: 1.57, 15: 1.59}


class ProjectError(Exception):
    """Raised for anything the caller can fix (bad name, missing project)."""


def slugify(text: str, fallback: str = "projekt") -> str:
    """Directory/identifier-safe name from a German title."""
    umlaut = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
              "Ä": "ae", "Ö": "oe", "Ü": "ue"}
    out = "".join(umlaut.get(c, c) for c in (text or "").strip().lower())
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in out)
    out = "_".join(filter(None, out.split("_")))[:48]
    if not out or out[0].isdigit():
        out = fallback if not out else fallback + "_" + out
    return out


# ---------------------------------------------------------------------------
# Pairwise comparison (AHP)
# ---------------------------------------------------------------------------

def pair_indices(n: int) -> list:
    """Every unordered pair (i, j) with i < j -- n*(n-1)/2 of them."""
    return [(i, j) for i in range(n) for j in range(i + 1, n)]


@dataclass
class PairwiseMatrix:
    """Which criterion beats which, and by how much.

    Only the upper triangle is stored; ``a_ji`` is the reciprocal by
    definition, which is what makes the matrix consistent by construction in
    that respect. The interesting part is *transitive* consistency, reported
    as the consistency ratio.
    """

    criteria: list = field(default_factory=list)
    #: {"i,j": a_ij} for i < j
    judgements: dict = field(default_factory=dict)

    # -- editing ------------------------------------------------------------
    def set_pair(self, i: int, j: int, value: float) -> None:
        n = len(self.criteria)
        if not (0 <= i < n and 0 <= j < n):
            raise ProjectError(f"Kriterium ausserhalb des Bereichs: {i}, {j}")
        if i == j:
            raise ProjectError("Ein Kriterium wird nicht mit sich verglichen.")
        value = float(value)
        if value <= 0:
            raise ProjectError("Bewertung muss positiv sein.")
        if i > j:
            i, j, value = j, i, 1.0 / value
        self.judgements[f"{i},{j}"] = value

    def get_pair(self, i: int, j: int) -> float:
        if i == j:
            return 1.0
        if i < j:
            return float(self.judgements.get(f"{i},{j}", 1.0))
        return 1.0 / float(self.judgements.get(f"{j},{i}", 1.0))

    def missing_pairs(self) -> list:
        return [(i, j) for i, j in pair_indices(len(self.criteria))
                if f"{i},{j}" not in self.judgements]

    def matrix(self) -> list:
        n = len(self.criteria)
        return [[self.get_pair(i, j) for j in range(n)] for i in range(n)]

    # -- evaluation ---------------------------------------------------------
    def weights(self) -> list:
        """Normalised priorities via the geometric mean of each row."""
        n = len(self.criteria)
        if n == 0:
            return []
        if n == 1:
            return [1.0]
        geo = []
        for i in range(n):
            prod = 1.0
            for j in range(n):
                prod *= self.get_pair(i, j)
            geo.append(prod ** (1.0 / n))
        total = sum(geo)
        if total <= 0:
            return [1.0 / n] * n
        return [g / total for g in geo]

    def lambda_max(self) -> float:
        n = len(self.criteria)
        w = self.weights()
        if n < 2 or min(w) <= 0:
            return float(n)
        acc = 0.0
        for i in range(n):
            row = sum(self.get_pair(i, j) * w[j] for j in range(n))
            acc += row / w[i]
        return acc / n

    def consistency_index(self) -> float:
        n = len(self.criteria)
        if n < 3:
            return 0.0
        return (self.lambda_max() - n) / (n - 1)

    def consistency_ratio(self) -> float:
        """CR <= 0.10 counts as consistent enough (Saaty)."""
        n = len(self.criteria)
        ri = _RANDOM_INDEX.get(n, 1.59)
        if n < 3 or ri <= 0:
            return 0.0
        return self.consistency_index() / ri

    def is_consistent(self, limit: float = 0.10) -> bool:
        return self.consistency_ratio() <= limit

    def ranking(self) -> list:
        """[(criterion, weight)] sorted by weight, descending."""
        return sorted(zip(self.criteria, self.weights()),
                      key=lambda kv: kv[1], reverse=True)

    def worst_pairs(self, count: int = 3) -> list:
        """Judgements that fit the derived weights worst.

        Shows the user *where* an inconsistent matrix hurts, instead of only
        telling them that it is inconsistent.

        Note for n = 3: a 3x3 matrix has a single degree of inconsistency, so
        one bad judgement shifts all three pairs by the very same factor and
        no culprit can be singled out. From n = 4 the outlier stands out.
        """
        w = self.weights()
        out = []
        for i, j in pair_indices(len(self.criteria)):
            if w[j] <= 0:
                continue
            said = self.get_pair(i, j)
            implied = w[i] / w[j]
            if said <= 0 or implied <= 0:
                continue
            # symmetric log deviation
            dev = abs((said / implied) if said > implied else (implied / said))
            out.append((dev, self.criteria[i], self.criteria[j], said, implied))
        out.sort(reverse=True)
        return [(a, b, said, implied) for _, a, b, said, implied in out[:count]]

    # -- persistence --------------------------------------------------------
    def to_csv(self, path: str) -> str:
        n = len(self.criteria)
        w = self.weights()
        with open(path, "w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["Kriterium"] + list(self.criteria) + ["Gewicht", "Rang"])
            order = {name: r for r, (name, _) in enumerate(self.ranking(), 1)}
            for i in range(n):
                wr.writerow([self.criteria[i]]
                            + ["%.4f" % self.get_pair(i, j) for j in range(n)]
                            + ["%.4f" % w[i], order.get(self.criteria[i], "")])
            wr.writerow([])
            wr.writerow(["lambda_max", "%.4f" % self.lambda_max()])
            wr.writerow(["Konsistenzindex", "%.4f" % self.consistency_index()])
            wr.writerow(["Konsistenzverhaeltnis", "%.4f" % self.consistency_ratio()])
            wr.writerow(["konsistent (<= 0.10)", "ja" if self.is_consistent() else "nein"])
        return path

    @classmethod
    def from_csv(cls, path: str) -> "PairwiseMatrix":
        with open(path, "r", encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.reader(fh)]
        if not rows:
            raise ProjectError(f"Leere Matrixdatei: {path}")
        header = rows[0]
        # The number of criteria is the number of data rows before the blank
        # separator -- reading it off the header would break as soon as a
        # criterion is itself called "Gewicht".
        n = 0
        for row in rows[1:]:
            if not row or not (row[0] or "").strip():
                break
            n += 1
        criteria = header[1:1 + n]
        m = cls(criteria=list(criteria))
        for r, row in enumerate(rows[1:1 + len(criteria)]):
            for c in range(len(criteria)):
                if c <= r:
                    continue
                try:
                    m.set_pair(r, c, float(row[1 + c]))
                except (ValueError, IndexError):
                    continue
        return m


def scale_label(value: float) -> str:
    """Nearest Saaty label for a raw a_ij (for display)."""
    best, best_d = SAATY_SCALE[4][0], None
    for label, v in SAATY_SCALE:
        d = abs((value / v) if value > v else (v / value)) if v and value else 1e9
        if best_d is None or d < best_d:
            best, best_d = label, d
    return best


# ---------------------------------------------------------------------------
# Skills and tools needed by a project
# ---------------------------------------------------------------------------

@dataclass
class SkillNeed:
    """One part the project needs a generator for."""

    name: str
    description: str = ""
    status: str = "offen"        # offen | vorhanden | kopiert | gelernt
    source: str = ""             # where a copied skill came from


@dataclass
class SkillMatch:
    """How well an existing skill covers one need."""

    need: "SkillNeed"
    candidate: "str | None" = None     # closest existing skill, whatever the score
    score: float = 0.0
    cutoff: float = 0.9

    @property
    def is_match(self) -> bool:
        """Close enough to copy without asking."""
        return bool(self.candidate) and self.score >= self.cutoff

    @property
    def is_hint(self) -> bool:
        """Similar, but not close enough to act on by itself."""
        return bool(self.candidate) and 0.6 <= self.score < self.cutoff


def _norm_skill_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def name_similarity(a: str, b: str) -> float:
    """Similarity of two skill names, 0..1.

    Deliberately harsh on a differing first syllable: in German part names the
    distinguishing bit is usually the prefix -- *Ein*lasskanal vs
    *Aus*lasskanal, *Innen*ring vs *Aussen*ring -- and a plain string ratio
    rates those 0.75, which is high enough to copy the wrong generator.
    """
    x, y = _norm_skill_name(a), _norm_skill_name(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    score = difflib.SequenceMatcher(None, x, y).ratio()
    contained = x in y or y in x
    if contained:
        score = max(score, 0.9)
    elif x[:3] != y[:3]:
        score *= 0.7
    return score


def match_skills(needed: list, available: list, cutoff: float = 0.9) -> list:
    """Pair each need with the closest existing skill.

    Returns ``[SkillMatch]``. Only ``is_match`` entries are safe to copy;
    everything else is a hint for the user to judge.
    """
    out = []
    for need in needed:
        best, score = None, 0.0
        for other in available:
            s = name_similarity(need.name, other)
            if s > score:
                best, score = other, s
        out.append(SkillMatch(need=need, candidate=best,
                              score=round(score, 3), cutoff=cutoff))
    return out


# ---------------------------------------------------------------------------
# Project parameters: the answers, kept where every step can reach them
# ---------------------------------------------------------------------------

PARAM_KINDS = ("float", "int", "text", "auswahl")


@dataclass
class ProjectParam:
    """One agreed value of the project -- a valve diameter, a wall thickness.

    These are what the question masks fill in, and what skills read instead of
    inventing their own numbers.
    """

    name: str
    label: str = ""
    unit: str = ""
    value: object = None
    kind: str = "float"
    minimum: object = None
    maximum: object = None
    choices: list = field(default_factory=list)
    source: str = "benutzer"       # benutzer | modell | recherche | abgeleitet
    note: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.name or ""):
            raise ProjectError(f"Ungültiger Parametername: {self.name!r}")
        if self.kind not in PARAM_KINDS:
            self.kind = "float"
        self.label = self.label or self.name
        if self.value is not None:
            self.value = self.cast(self.value)

    def cast(self, value):
        if self.kind == "int":
            try:
                return int(round(float(value)))
            except (TypeError, ValueError):
                raise ProjectError(
                    f"{self.name}: {value!r} ist keine ganze Zahl") from None
        if self.kind == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                raise ProjectError(
                    f"{self.name}: {value!r} ist keine Zahl") from None
        return str(value)

    def range_error(self, value=None) -> "str | None":
        v = self.value if value is None else value
        if v is None or self.kind not in ("int", "float"):
            return None
        if self.minimum is not None and v < self.minimum:
            return f"{self.name} = {v} liegt unter dem Minimum {self.minimum}"
        if self.maximum is not None and v > self.maximum:
            return f"{self.name} = {v} liegt über dem Maximum {self.maximum}"
        return None

    def display(self) -> str:
        v = "–" if self.value is None else self.value
        return f"{self.label}: {v} {self.unit}".strip()


def _is_count_unit(unit: str) -> bool:
    try:
        import T2GCore
        return T2GCore.is_count_unit(unit)
    except Exception:  # noqa: BLE001  -- keep T2GProject usable on its own
        return (unit or "").strip().lower().rstrip(".") in (
            "", "-", "stk", "st", "stueck", "stück", "anzahl", "x")


def param_from_row(row) -> ProjectParam:
    """Build a parameter from a ``name;label;einheit;default;min;max`` row."""
    if isinstance(row, ProjectParam):
        return row
    if isinstance(row, dict):
        return ProjectParam(**{k: v for k, v in row.items()
                               if k in ProjectParam.__dataclass_fields__})
    name, label, unit, default, lo, hi = (list(row) + [None] * 6)[:6]
    kind = "float"
    if isinstance(default, str):
        kind = "text"
    elif isinstance(default, int) and not isinstance(default, bool):
        # one definition of "this is a count", shared with T2GCore -- having
        # two lists made "Stück" a float here and an int there.
        kind = "int" if _is_count_unit(unit) else "float"
    return ProjectParam(name=str(name), label=str(label or name),
                        unit=str(unit or ""), value=default, kind=kind,
                        minimum=lo, maximum=hi, source="modell")


# ---------------------------------------------------------------------------
# Knowledge graph: which parameter drives which part
# ---------------------------------------------------------------------------

EDGE_KINDS = ("nutzt", "abgeleitet", "passt_an", "gehoert_zu")


def pnode(name: str) -> str:
    return "p:" + name


def snode(name: str) -> str:
    return "s:" + name


def node_label(node: str) -> str:
    return node.split(":", 1)[1] if ":" in node else node


@dataclass
class KnowledgeGraph:
    """What depends on what.

    Edges point *downstream*: from the thing that changes to the thing that
    has to follow. ``ventil_d --nutzt--> brennraum`` therefore means "if
    ventil_d changes, brennraum must be rebuilt".
    """

    edges: list = field(default_factory=list)   # [{src, dst, kind, note}]

    def add(self, src: str, dst: str, kind: str = "nutzt", note: str = "") -> None:
        if kind not in EDGE_KINDS:
            raise ProjectError(f"Unbekannte Kantenart: {kind!r}")
        if src == dst:
            return
        for e in self.edges:
            if e["src"] == src and e["dst"] == dst and e["kind"] == kind:
                if note and not e.get("note"):
                    e["note"] = note
                return
        self.edges.append({"src": src, "dst": dst, "kind": kind, "note": note})
        if kind == "passt_an":          # fitting is mutual
            self.add(dst, src, "passt_an", note)

    def param_used_by(self, param: str, skill: str, note: str = "") -> None:
        self.add(pnode(param), snode(skill), "nutzt", note)

    def param_derived(self, source_param: str, derived: str, note: str = "") -> None:
        self.add(pnode(source_param), pnode(derived), "abgeleitet", note)

    def skills_fit(self, a: str, b: str, note: str = "") -> None:
        self.add(snode(a), snode(b), "passt_an", note)

    def remove_node(self, node: str) -> None:
        self.edges = [e for e in self.edges
                      if e["src"] != node and e["dst"] != node]

    def nodes(self) -> list:
        out = []
        for e in self.edges:
            for n in (e["src"], e["dst"]):
                if n not in out:
                    out.append(n)
        return out

    def successors(self, node: str) -> list:
        return [e["dst"] for e in self.edges if e["src"] == node]

    def predecessors(self, node: str) -> list:
        return [e["src"] for e in self.edges if e["dst"] == node]

    def params_of(self, skill: str) -> list:
        """Parameters a skill reads (directly)."""
        return [node_label(n) for n in self.predecessors(snode(skill))
                if n.startswith("p:")]

    def impact(self, changed: list) -> dict:
        """What has to be revisited when these parameters/skills change.

        Returns ``{"params": [...], "skills": [...]}`` -- everything reachable
        downstream, the starting points excluded.
        """
        start = []
        for c in changed or []:
            start.append(c if ":" in c else pnode(c))
        seen = set(start)
        queue = list(start)
        params, skills = [], []
        while queue:
            node = queue.pop(0)
            for nxt in self.successors(node):
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)
                (params if nxt.startswith("p:") else skills).append(node_label(nxt))
        return {"params": params, "skills": skills}

    def to_mermaid(self) -> str:
        """A diagram that renders in any markdown viewer that knows mermaid."""
        if not self.edges:
            return ""
        arrow = {"nutzt": "-->", "abgeleitet": "-.->", "passt_an": "---",
                 "gehoert_zu": "-->"}
        lines = ["```mermaid", "graph LR"]
        drawn = set()
        for n in self.nodes():
            safe = re.sub(r"[^A-Za-z0-9_]", "_", n)
            shape = ("([%s])" if n.startswith("p:") else "[%s]") % node_label(n)
            lines.append(f"    {safe}{shape}")
        for e in self.edges:
            if e["kind"] == "passt_an":
                key = tuple(sorted((e["src"], e["dst"])))
                if key in drawn:
                    continue
                drawn.add(key)
            a = re.sub(r"[^A-Za-z0-9_]", "_", e["src"])
            b = re.sub(r"[^A-Za-z0-9_]", "_", e["dst"])
            label = f"|{e['kind']}|" if e["kind"] != "nutzt" else ""
            lines.append(f"    {a} {arrow[e['kind']]}{label} {b}")
        lines.append("```")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper tools: validate before writing them into the project
# ---------------------------------------------------------------------------

#: A tool calculates. It has no business touching files, the network or FreeCAD.
_TOOL_ALLOWED_IMPORTS = ("math", "statistics", "fractions", "decimal",
                         "itertools", "functools", "cmath")

_TOOL_BUILTINS = {
    "abs": abs, "min": min, "max": max, "len": len, "range": range,
    "enumerate": enumerate, "zip": zip, "list": list, "tuple": tuple,
    "set": set, "dict": dict, "str": str, "int": int, "float": float,
    "bool": bool, "round": round, "sum": sum, "sorted": sorted, "any": any,
    "all": all, "map": map, "filter": filter, "reversed": reversed,
    "divmod": divmod, "pow": pow, "isinstance": isinstance,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError, "AssertionError": AssertionError,
    "ArithmeticError": ArithmeticError, "RuntimeError": RuntimeError,
    "print": lambda *a, **k: None,
}


def _tool_import(name, *a, **k):
    if name.split(".")[0] in _TOOL_ALLOWED_IMPORTS:
        return __import__(name, *a, **k)
    raise ImportError(f"import von {name!r} ist in einem Werkzeug nicht erlaubt")


def _tool_namespace() -> dict:
    # As in the skill sandbox: the guard only bites from inside __builtins__.
    guarded = dict(_TOOL_BUILTINS)
    guarded["__import__"] = _tool_import
    ns = dict(_TOOL_BUILTINS)
    ns["__builtins__"] = guarded
    ns["__import__"] = _tool_import
    ns["__name__"] = "t2g_werkzeug"
    return ns


def validate_tool_source(code: str, run_selftest: bool = True) -> tuple:
    """Check a generated tool module. Returns ``(problems, function_names)``.

    The model ships its own ``selbsttest()`` with hand-checked values; running
    it is what turns "looks like Python" into "computes the right thing".
    """
    problems: list = []
    if not (code or "").strip():
        return ["Leerer Code."], []
    forbidden = re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z_0-9.]*)",
                           code, re.M)
    for mod in forbidden:
        if mod.split(".")[0] not in _TOOL_ALLOWED_IMPORTS:
            problems.append(f"Nicht erlaubter Import: {mod}")
    if problems:
        return problems, []
    try:
        compiled = compile(code, "<werkzeug>", "exec")
    except SyntaxError as e:
        return [f"Syntaxfehler: {e}"], []

    ns = _tool_namespace()
    try:
        exec(compiled, ns)
    except Exception as e:  # noqa: BLE001
        return [f"Modul liess sich nicht laden: {type(e).__name__}: {e}"], []

    # Functions defined by the exec'd code carry a __code__ object; the
    # builtins we injected do not. (__module__ is no discriminator here: it
    # follows the namespace's __name__, so it is never None.)
    funcs = sorted(n for n, v in ns.items()
                   if n not in _TOOL_BUILTINS and not n.startswith("_")
                   and callable(v) and hasattr(v, "__code__"))
    if not funcs:
        problems.append("Das Modul definiert keine Funktion.")
        return problems, []
    if "selbsttest" not in funcs:
        problems.append("Es fehlt die Funktion `selbsttest()`.")
        return problems, funcs

    if run_selftest:
        try:
            ok = ns["selbsttest"]()
        except AssertionError as e:
            problems.append(f"Selbsttest fehlgeschlagen: {e or 'assert'}")
        except Exception as e:  # noqa: BLE001
            problems.append(f"Selbsttest brach ab: {type(e).__name__}: {e}")
        else:
            if ok is not True:
                problems.append("selbsttest() hat nicht True zurückgegeben "
                                f"(sondern {ok!r}).")
    return problems, [f for f in funcs if f != "selbsttest"]


# ---------------------------------------------------------------------------
# The project itself
# ---------------------------------------------------------------------------

@dataclass
class Project:
    path: str
    name: str = ""
    title: str = ""
    brief: str = ""                      # what is to be built, in prose
    questions: list = field(default_factory=list)
    answers: str = ""
    criteria: list = field(default_factory=list)        # [{name, description}]
    matrix: PairwiseMatrix = field(default_factory=PairwiseMatrix)
    params: list = field(default_factory=list)          # [ProjectParam]
    graph: KnowledgeGraph = field(default_factory=KnowledgeGraph)
    skills: list = field(default_factory=list)          # [SkillNeed]
    tools: list = field(default_factory=list)           # [{name, purpose, file}]
    notes: list = field(default_factory=list)
    #: The conversation, so a restart does not start from nothing.
    chat: list = field(default_factory=list)          # [[rolle, text]]
    #: Condensed history -- what still matters from everything said so far.
    chat_summary: str = ""
    created: str = ""
    updated: str = ""

    # -- directories --------------------------------------------------------
    @property
    def agent_dir(self) -> str:
        return os.path.join(self.path, AGENT_DIR)

    @property
    def skills_dir(self) -> str:
        return os.path.join(self.path, SKILLS_DIR)

    @property
    def tools_dir(self) -> str:
        return os.path.join(self.path, TOOLS_DIR)

    @property
    def eval_dir(self) -> str:
        return os.path.join(self.path, EVAL_DIR)

    # -- lifecycle ----------------------------------------------------------
    @classmethod
    def create(cls, base_dir: str, title: str) -> "Project":
        name = slugify(title)
        if not base_dir:
            raise ProjectError("Kein Projektverzeichnis angegeben.")
        path = os.path.join(base_dir, name)
        if os.path.exists(os.path.join(path, PROJECT_FILE)):
            raise ProjectError(f"Projekt existiert bereits: {path}")
        now = datetime.datetime.now().isoformat(timespec="seconds")
        p = cls(path=path, name=name, title=title.strip() or name,
                created=now, updated=now)
        for d in (p.agent_dir, p.skills_dir, p.tools_dir, p.eval_dir):
            os.makedirs(d, exist_ok=True)
        p.save()
        return p

    @classmethod
    def load(cls, path: str) -> "Project":
        f = os.path.join(path, PROJECT_FILE)
        if not os.path.isfile(f):
            raise ProjectError(f"Kein Projekt in {path} (es fehlt {PROJECT_FILE}).")
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        m = data.pop("matrix", {}) or {}
        skills = data.pop("skills", []) or []
        params = data.pop("params", []) or []
        graph = data.pop("graph", {}) or {}
        p = cls(**{k: v for k, v in data.items()
                   if k in cls.__dataclass_fields__
                   and k not in ("matrix", "params", "graph")})
        p.path = path                     # a moved project keeps working
        p.matrix = PairwiseMatrix(criteria=list(m.get("criteria", [])),
                                  judgements=dict(m.get("judgements", {})))
        p.skills = [SkillNeed(**s) if isinstance(s, dict) else s for s in skills]
        p.params = [param_from_row(x) for x in params]
        p.graph = KnowledgeGraph(edges=[dict(e) for e in graph.get("edges", [])])
        return p

    def save(self) -> str:
        self.updated = datetime.datetime.now().isoformat(timespec="seconds")
        os.makedirs(self.path, exist_ok=True)
        data = asdict(self)
        data["matrix"] = {"criteria": list(self.matrix.criteria),
                          "judgements": dict(self.matrix.judgements)}
        data["params"] = [asdict(x) for x in self.params]
        data["graph"] = {"edges": [dict(e) for e in self.graph.edges]}
        f = os.path.join(self.path, PROJECT_FILE)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return f

    # -- content ------------------------------------------------------------
    def set_criteria(self, criteria: list) -> None:
        """Replace the criteria, keeping judgements that still apply."""
        names = [c["name"] if isinstance(c, dict) else str(c) for c in criteria]
        old = self.matrix
        old_names = list(old.criteria)
        new = PairwiseMatrix(criteria=names)
        for i, a in enumerate(names):
            for j, b in enumerate(names):
                if j <= i or a not in old_names or b not in old_names:
                    continue
                oi, oj = old_names.index(a), old_names.index(b)
                key = f"{min(oi, oj)},{max(oi, oj)}"
                if key in old.judgements:
                    new.set_pair(i, j, old.get_pair(oi, oj))
        self.criteria = [c if isinstance(c, dict) else {"name": str(c),
                                                        "description": ""}
                         for c in criteria]
        self.matrix = new

    # -- parameters ---------------------------------------------------------

    def add_chat(self, role: str, text: str, limit: int = 400) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.chat.append([str(role), text])
        if len(self.chat) > limit:
            self.chat = self.chat[-limit:]

    def chat_transcript(self, count: int = 20) -> list:
        """The last exchanges as (role, text) -- to seed a new agent run."""
        return [(r, t) for r, t in self.chat[-count:]]

    def param(self, name: str) -> "ProjectParam | None":
        for p in self.params:
            if p.name == name:
                return p
        return None

    def param_values(self) -> dict:
        """``{name: value}`` for every parameter that has one."""
        return {p.name: p.value for p in self.params if p.value is not None}

    def set_param(self, param) -> "ProjectParam":
        """Add or update one parameter, keeping the existing order."""
        new = param_from_row(param)
        for i, old in enumerate(self.params):
            if old.name == new.name:
                # a re-asked question must not silently drop the answer
                if new.value is None:
                    new.value = old.value
                self.params[i] = new
                return new
        self.params.append(new)
        return new

    def set_params(self, rows: list) -> list:
        return [self.set_param(r) for r in (rows or [])]

    def answer_mask(self, answers: dict, source: str = "benutzer") -> list:
        """Take ``{name: value}`` from a filled-in question mask.

        Returns the problems found (out-of-range, wrong type); values that
        parse are stored either way so nothing typed is lost.
        """
        problems = []
        for name, value in (answers or {}).items():
            p = self.param(name)
            if p is None:
                p = self.set_param(ProjectParam(name=name, value=value,
                                                kind="text", source=source))
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            try:
                p.value = p.cast(value)
            except ProjectError as e:
                problems.append(str(e))
                continue
            p.source = source
            err = p.range_error()
            if err:
                problems.append(err)
        return problems

    def open_questions(self) -> list:
        """Parameters that still have no value."""
        return [p for p in self.params if p.value is None]

    def impact_of(self, changed: list) -> dict:
        return self.graph.impact(changed)

    def mark_affected(self, changed: list) -> list:
        """Flag every skill downstream of a change as needing a rebuild."""
        hit = self.impact_of(changed)["skills"]
        touched = []
        for s in self.skills:
            if s.name in hit and s.status in ("kopiert", "gelernt", "gebaut"):
                s.status = "zu pruefen"
                touched.append(s.name)
        return touched

    def copy_skill(self, src_file: str, need: "SkillNeed | None" = None) -> str:
        """Copy an existing skill into the project (skills are reused, not rewritten)."""
        if not os.path.isfile(src_file):
            raise ProjectError(f"Skill-Datei nicht gefunden: {src_file}")
        name = os.path.splitext(os.path.basename(src_file))[0]
        dest_dir = os.path.join(self.skills_dir, name)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, name + ".py")
        shutil.copyfile(src_file, dest)
        if need is not None:
            need.status = "kopiert"
            need.source = src_file
        return dest

    def write_tool(self, name: str, code: str, purpose: str = "") -> str:
        safe = slugify(name, fallback="werkzeug")
        os.makedirs(self.tools_dir, exist_ok=True)
        path = os.path.join(self.tools_dir, safe + ".py")
        header = (f"# SPDX-License-Identifier: LGPL-2.1-or-later\n"
                  f'"""{purpose or name}"""\n\n')
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + code.strip() + "\n")
        entry = {"name": safe, "purpose": purpose, "file": path}
        self.tools = [t for t in self.tools if t.get("name") != safe] + [entry]
        return path

    def write_matrix_csv(self) -> str:
        os.makedirs(self.eval_dir, exist_ok=True)
        return self.matrix.to_csv(os.path.join(self.eval_dir, MATRIX_FILE))

    # -- agent.d ------------------------------------------------------------
    def write_agent_d(self) -> list:
        """Render agent.d/*.md from the current state; returns the files written."""
        os.makedirs(self.agent_dir, exist_ok=True)
        written = []

        def _write(fname: str, text: str) -> None:
            p = os.path.join(self.agent_dir, fname)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text.rstrip() + "\n")
            written.append(p)

        _write("00-auftrag.md", self._render_auftrag())
        _write("10-anforderungen.md", self._render_anforderungen())
        _write("20-skills.md", self._render_skills())
        _write("30-werkzeuge.md", self._render_werkzeuge())
        _write("40-parameter.md", self._render_parameter())
        _write("50-abhaengigkeiten.md", self._render_graph())
        return written

    def _render_auftrag(self) -> str:
        lines = [f"# Auftrag – {self.title}", "",
                 f"*Projekt `{self.name}`, angelegt {self.created}, "
                 f"zuletzt geändert {self.updated}.*", "",
                 "## Was gebaut werden soll", "",
                 self.brief.strip() or "_(noch nicht beschrieben)_"]
        if self.questions:
            lines += ["", "## Geklärte Rückfragen", ""]
            lines += [f"- {q}" for q in self.questions]
        if self.answers.strip():
            lines += ["", "### Antworten", "", self.answers.strip()]
        if self.notes:
            lines += ["", "## Notizen", ""] + [f"- {n}" for n in self.notes]
        return "\n".join(lines)

    def _render_anforderungen(self) -> str:
        lines = ["# Anforderungen und Gewichtung", ""]
        if not self.criteria:
            return "\n".join(lines + ["_(noch keine Kriterien)_"])
        lines += ["## Kriterien", ""]
        by_name = {c["name"]: c.get("description", "") for c in self.criteria}
        ranking = self.matrix.ranking()
        if ranking:
            lines += ["| Rang | Kriterium | Gewicht | Bedeutung |",
                      "|-----:|-----------|--------:|-----------|"]
            for rank, (name, w) in enumerate(ranking, 1):
                lines.append(f"| {rank} | {name} | {w * 100:.1f} % | "
                             f"{by_name.get(name, '')} |")
        else:
            lines += [f"- {c['name']}: {c.get('description', '')}"
                      for c in self.criteria]
        cr = self.matrix.consistency_ratio()
        missing = self.matrix.missing_pairs()
        lines += ["", "## Paarvergleich", "",
                  f"- Vergleiche: {len(pair_indices(len(self.matrix.criteria)))}"
                  f", davon offen: {len(missing)}",
                  f"- Konsistenzverhältnis: {cr:.3f} "
                  f"({'in Ordnung' if self.matrix.is_consistent() else 'zu hoch, Urteile prüfen'})",
                  f"- Matrix: `{EVAL_DIR}/{MATRIX_FILE}`"]
        if not self.matrix.is_consistent():
            worst = self.matrix.worst_pairs()
            if worst:
                lines += ["", "Am stärksten abweichende Urteile:", ""]
                for a, b, said, implied in worst:
                    lines.append(f"- {a} vs. {b}: bewertet {said:.2f}, "
                                 f"aus den Gewichten folgt {implied:.2f}")
        lines += ["", "## Wie die Gewichte zu benutzen sind", "",
                  "Bei Zielkonflikten entscheidet das höher gewichtete Kriterium.",
                  "Die Gewichte stammen aus dem Paarvergleich des Anwenders,",
                  "nicht aus einer Schätzung des Modells."]
        return "\n".join(lines)

    def _render_skills(self) -> str:
        lines = ["# Skills", ""]
        if not self.skills:
            return "\n".join(lines + ["_(noch keine Skills ermittelt)_"])
        lines += ["| Skill | Zweck | Status | Herkunft |",
                  "|-------|-------|--------|----------|"]
        for s in self.skills:
            lines.append(f"| {s.name} | {s.description} | {s.status} | "
                         f"{os.path.basename(s.source) if s.source else ''} |")
        lines += ["", f"Projektlokale Skills liegen in `{SKILLS_DIR}/`."]
        return "\n".join(lines)

    def _render_werkzeuge(self) -> str:
        lines = ["# Werkzeuge", ""]
        if not self.tools:
            return "\n".join(lines + ["_(keine Werkzeuge nötig)_"])
        for t in self.tools:
            lines += [f"## {t['name']}", "", t.get("purpose", ""), "",
                      f"Datei: `{TOOLS_DIR}/{t['name']}.py`", ""]
        return "\n".join(lines)

    def _render_parameter(self) -> str:
        lines = ["# Parameter", ""]
        if not self.params:
            return "\n".join(lines + ["_(noch keine Parameter vereinbart)_"])
        lines += ["| Parameter | Bedeutung | Wert | Einheit | Grenzen | Herkunft |",
                  "|-----------|-----------|-----:|---------|---------|----------|"]
        for p in self.params:
            grenzen = ""
            if p.minimum is not None or p.maximum is not None:
                grenzen = f"{p.minimum if p.minimum is not None else ''} … " \
                          f"{p.maximum if p.maximum is not None else ''}"
            wert = "**offen**" if p.value is None else p.value
            lines.append(f"| `{p.name}` | {p.label} | {wert} | {p.unit} | "
                         f"{grenzen} | {p.source} |")
        offen = self.open_questions()
        if offen:
            lines += ["", "Noch offen: " + ", ".join(f"`{p.name}`" for p in offen)]
        lines += ["", "Diese Werte gelten projektweit. Ein Skill, der einen davon "
                  "braucht, liest ihn hier und erfindet keinen eigenen."]
        return "\n".join(lines)

    def _render_graph(self) -> str:
        lines = ["# Abhängigkeiten", ""]
        if not self.graph.edges:
            return "\n".join(lines + ["_(noch keine Abhängigkeiten erfasst)_"])
        lines += ["Kanten zeigen flussabwärts: Ändert sich die Quelle, muss das "
                  "Ziel nachgezogen werden.", ""]
        lines += ["| Wenn sich ändert | dann betrifft das | Art | Anmerkung |",
                  "|------------------|-------------------|-----|-----------|"]
        for e in self.graph.edges:
            if e["kind"] == "passt_an" and e["src"] > e["dst"]:
                continue       # mutual edge, list it once
            lines.append(f"| {node_label(e['src'])} | {node_label(e['dst'])} | "
                         f"{e['kind']} | {e.get('note', '')} |")
        mer = self.graph.to_mermaid()
        if mer:
            lines += ["", "## Diagramm", "", mer]
        lines += ["", "## Wirkung einzelner Änderungen", ""]
        for p in self.params:
            hit = self.impact_of([p.name])
            if hit["skills"] or hit["params"]:
                lines.append(f"- `{p.name}` ändern → "
                             + ", ".join(hit["skills"] + [f"`{x}`" for x in hit["params"]]))
        return "\n".join(lines)

    # -- prompt context -----------------------------------------------------
    def as_prompt_block(self) -> str:
        """The project state, compact enough to prefix a prompt with."""
        parts = [f"PROJEKT: {self.title}"]
        if self.brief.strip():
            parts += ["", "Auftrag:", self.brief.strip()]
        if self.answers.strip():
            parts += ["", "Geklärte Punkte:", self.answers.strip()]
        if self.params:
            parts += ["", "Vereinbarte Parameter (projektweit gültig):"]
            for p in self.params:
                wert = "offen" if p.value is None else f"{p.value} {p.unit}".strip()
                parts.append(f"- {p.name} ({p.label}): {wert}")
        ranking = self.matrix.ranking()
        if ranking:
            parts += ["", "Gewichtete Kriterien (aus dem Paarvergleich):"]
            parts += [f"- {n}: {w * 100:.1f} %" for n, w in ranking]
        if self.graph.edges:
            parts += ["", "Abhängigkeiten (Quelle ändert sich -> Ziel nachziehen):"]
            for e in self.graph.edges:
                if e["kind"] == "passt_an" and e["src"] > e["dst"]:
                    continue
                parts.append(f"- {node_label(e['src'])} -> {node_label(e['dst'])}"
                             f" ({e['kind']})")
        if self.skills:
            parts += ["", "Skills:"]
            parts += [f"- {s.name} ({s.status}): {s.description}"
                      for s in self.skills]
        if self.tools:
            parts += ["", "Werkzeuge:"]
            parts += [f"- {t['name']}: {t.get('purpose', '')}" for t in self.tools]
        return "\n".join(parts)


def list_projects(base_dir: str) -> list:
    """Every project directory directly below ``base_dir``."""
    out = []
    if not os.path.isdir(base_dir):
        return out
    for entry in sorted(os.listdir(base_dir)):
        cand = os.path.join(base_dir, entry)
        if os.path.isfile(os.path.join(cand, PROJECT_FILE)):
            out.append(cand)
    return out


__all__ = [
    "Project", "ProjectError", "PairwiseMatrix", "SkillNeed", "SkillMatch",
    "ProjectParam", "param_from_row", "KnowledgeGraph", "pnode", "snode",
    "node_label", "PARAM_KINDS", "EDGE_KINDS",
    "SAATY_SCALE", "pair_indices", "match_skills", "name_similarity", "slugify",
    "validate_tool_source",
    "scale_label", "list_projects",
    "PROJECT_FILE", "AGENT_DIR", "SKILLS_DIR", "TOOLS_DIR", "EVAL_DIR",
    "MATRIX_FILE",
]
