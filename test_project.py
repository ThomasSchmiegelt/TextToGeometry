# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for the project workspace and the pairwise comparison (no FreeCAD)."""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import T2GProject as P  # noqa: E402
import T2GCore as C        # noqa: E402  (stdlib only, no FreeCAD needed)

FAILS = []
TMP = tempfile.mkdtemp(prefix="t2g_proj_")


def check(name, fn):
    try:
        fn()
        print("  ok   %s" % name)
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print("  FAIL %s -> %r" % (name, e))


def close(a, b, tol=1e-3):
    assert abs(a - b) <= tol, "%r != %r (Toleranz %r)" % (a, b, tol)


# ---- 1. names -------------------------------------------------------------
def t_slugify():
    assert P.slugify("Zylinderkopf Größe 2") == "zylinderkopf_groesse_2"
    assert P.slugify("  ") == "projekt"
    assert P.slugify("3er Motor").startswith("projekt"), P.slugify("3er Motor")


def t_pair_indices():
    assert P.pair_indices(4) == [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    assert len(P.pair_indices(6)) == 15
    assert P.pair_indices(1) == []


# ---- 2. the matrix --------------------------------------------------------
def _m3():
    m = P.PairwiseMatrix(criteria=["Wandstaerke", "Freigang", "Gewicht"])
    m.set_pair(0, 1, 3)      # Wandstärke etwas wichtiger als Freigang
    m.set_pair(0, 2, 5)
    m.set_pair(1, 2, 3)
    return m


def t_reciprocal():
    m = _m3()
    close(m.get_pair(0, 1), 3.0)
    close(m.get_pair(1, 0), 1 / 3.0)
    close(m.get_pair(2, 2), 1.0)


def t_set_pair_reversed():
    """set_pair(j, i, v) must store the reciprocal, not a second judgement."""
    m = P.PairwiseMatrix(criteria=["a", "b"])
    m.set_pair(1, 0, 4.0)
    close(m.get_pair(0, 1), 0.25)
    close(m.get_pair(1, 0), 4.0)
    assert list(m.judgements) == ["0,1"], m.judgements


def t_known_example():
    """Saaty's textbook 3x3: weights .637/.258/.105, CR ~ .033."""
    m = _m3()
    w = m.weights()
    close(w[0], 0.637, 2e-3)
    close(w[1], 0.258, 2e-3)
    close(w[2], 0.105, 2e-3)
    close(sum(w), 1.0, 1e-9)
    close(m.lambda_max(), 3.0385, 2e-3)
    close(m.consistency_ratio(), 0.033, 3e-3)
    assert m.is_consistent()


def t_perfectly_consistent():
    """A matrix built as a_ij = w_i/w_j must come out with CR = 0."""
    truth = [0.5, 0.3, 0.15, 0.05]
    m = P.PairwiseMatrix(criteria=list("abcd"))
    for i, j in P.pair_indices(4):
        m.set_pair(i, j, truth[i] / truth[j])
    for got, want in zip(m.weights(), truth):
        close(got, want, 1e-6)
    close(m.consistency_ratio(), 0.0, 1e-6)
    assert m.is_consistent()


def t_inconsistent_detected():
    """a>b, b>c, but c>a -- the classic circle must be flagged."""
    m = P.PairwiseMatrix(criteria=["a", "b", "c"])
    m.set_pair(0, 1, 9)
    m.set_pair(1, 2, 9)
    m.set_pair(0, 2, 1 / 9.0)
    assert not m.is_consistent(), m.consistency_ratio()
    assert m.consistency_ratio() > 0.10


def t_worst_pairs():
    """From n = 4 on, a single bad judgement must be named first."""
    truth = [0.5, 0.25, 0.15, 0.10]
    m = P.PairwiseMatrix(criteria=["a", "b", "c", "d"])
    for i, j in P.pair_indices(4):
        m.set_pair(i, j, truth[i] / truth[j])
    m.set_pair(2, 3, 1 / 9.0)          # outlier: should have been 1.5
    assert not m.is_consistent()
    worst = m.worst_pairs(1)
    assert worst and worst[0][0] == "c" and worst[0][1] == "d", worst
    said, implied = worst[0][2], worst[0][3]
    assert said < implied, worst


def t_worst_pairs_three_criteria_share_the_blame():
    """A 3x3 has one degree of inconsistency: all pairs deviate equally."""
    m = P.PairwiseMatrix(criteria=["a", "b", "c"])
    m.set_pair(0, 1, 2)
    m.set_pair(0, 2, 6)
    m.set_pair(1, 2, 1 / 5.0)
    worst = m.worst_pairs(3)
    factors = [max(said / implied, implied / said) for _, _, said, implied in worst]
    assert len(factors) == 3, worst
    for f in factors[1:]:
        close(f, factors[0], 1e-6)


def t_equal_when_empty():
    m = P.PairwiseMatrix(criteria=["a", "b", "c"])
    w = m.weights()
    for x in w:
        close(x, 1 / 3.0)
    assert len(m.missing_pairs()) == 3


def t_single_and_empty():
    assert P.PairwiseMatrix().weights() == []
    assert P.PairwiseMatrix(criteria=["x"]).weights() == [1.0]
    close(P.PairwiseMatrix(criteria=["x"]).consistency_ratio(), 0.0)


def t_bad_input():
    m = _m3()
    for args in ((0, 0, 3), (0, 9, 3), (0, 1, 0), (0, 1, -2)):
        try:
            m.set_pair(*args)
        except P.ProjectError:
            continue
        raise AssertionError("ungültige Eingabe akzeptiert: %r" % (args,))


def t_csv_roundtrip():
    m = _m3()
    path = os.path.join(TMP, "matrix.csv")
    m.to_csv(path)
    back = P.PairwiseMatrix.from_csv(path)
    assert back.criteria == m.criteria, back.criteria
    for i, j in P.pair_indices(3):
        close(back.get_pair(i, j), m.get_pair(i, j), 1e-3)
    text = open(path, encoding="utf-8").read()
    assert "Konsistenzverhaeltnis" in text and "Gewicht" in text


def t_scale_label():
    assert P.scale_label(9.0).startswith("A absolut")
    assert P.scale_label(1.0) == "gleich wichtig"
    assert P.scale_label(1 / 5.0).startswith("B deutlich")


# ---- 3. skill matching ----------------------------------------------------
def t_match_skills():
    needs = [P.SkillNeed("einlass_kanal"), P.SkillNeed("bruecke"),
             P.SkillNeed("kurbelwelle")]
    res = P.match_skills(needs, ["einlasskanal", "bruecke", "diag_kiste"])
    assert res[0].is_match and res[0].candidate == "einlasskanal", res[0]
    assert res[1].is_match and res[1].score == 1.0, res[1]
    assert not res[2].is_match and not res[2].is_hint, res[2]


def t_opposites_are_not_matches():
    """Ein-/Auslass, Innen-/Aussen: the prefix carries the meaning."""
    pairs = [("auslasskanal", "einlasskanal"), ("innenring", "aussenring"),
             ("oberschale", "unterschale")]
    for want, have in pairs:
        m = P.match_skills([P.SkillNeed(want)], [have])[0]
        assert not m.is_match, (want, have, m.score)


def t_similarity_shapes():
    close(P.name_similarity("einlasskanal", "einlasskanal"), 1.0)
    close(P.name_similarity("Einlass Kanal", "einlasskanal"), 1.0)
    assert P.name_similarity("kanal", "einlasskanal") >= 0.9      # contained
    assert P.name_similarity("auslasskanal", "einlasskanal") < 0.9
    assert P.name_similarity("", "x") == 0.0


# ---- 4. the project -------------------------------------------------------
def _new(title="Zylinderkopf V2"):
    return P.Project.create(TMP, title)


def t_create_layout():
    p = _new("Testprojekt A")
    for d in (p.agent_dir, p.skills_dir, p.tools_dir, p.eval_dir):
        assert os.path.isdir(d), d
    assert os.path.isfile(os.path.join(p.path, P.PROJECT_FILE))
    assert p.name == "testprojekt_a"


def t_create_twice_refused():
    _new("Doppelt")
    try:
        _new("Doppelt")
    except P.ProjectError:
        return
    raise AssertionError("zweites Projekt gleichen Namens angelegt")


def t_save_load_roundtrip():
    p = _new("Roundtrip")
    p.brief = "Ein Zylinderkopf mit vier Ventilen."
    p.questions = ["Wie viele Zylinder?"]
    p.answers = "Vier."
    p.set_criteria([{"name": "Wandstaerke", "description": "Gussgrenze"},
                    {"name": "Freigang", "description": "zum Ventil"}])
    p.matrix.set_pair(0, 1, 5)
    p.skills = [P.SkillNeed("einlasskanal", "Kanal", "offen")]
    p.notes = ["Guss AlSi"]
    p.save()

    q = P.Project.load(p.path)
    assert q.title == "Roundtrip" and q.brief == p.brief
    assert q.questions == p.questions and q.answers == "Vier."
    assert q.matrix.criteria == ["Wandstaerke", "Freigang"]
    close(q.matrix.get_pair(0, 1), 5.0)
    assert isinstance(q.skills[0], P.SkillNeed) and q.skills[0].name == "einlasskanal"
    assert q.notes == ["Guss AlSi"]


def t_load_missing():
    try:
        P.Project.load(os.path.join(TMP, "gibtsnicht"))
    except P.ProjectError:
        return
    raise AssertionError("fehlendes Projekt geladen")


def t_set_criteria_keeps_judgements():
    """Adding a criterion must not throw away what was already compared."""
    p = _new("Kriterien")
    p.set_criteria(["Wandstaerke", "Freigang"])
    p.matrix.set_pair(0, 1, 7)
    p.set_criteria(["Freigang", "Wandstaerke", "Gewicht"])   # reordered + new
    close(p.matrix.get_pair(1, 0), 7.0)     # Wandstärke vs Freigang survived
    assert len(p.matrix.missing_pairs()) == 2


def t_copy_skill():
    p = _new("Kopieren")
    src_dir = os.path.join(TMP, "quelle", "bruecke")
    os.makedirs(src_dir, exist_ok=True)
    src = os.path.join(src_dir, "bruecke.py")
    open(src, "w", encoding="utf-8").write("T2G_SKILL = {}\ndef build(p):\n    return []\n")
    need = P.SkillNeed("bruecke")
    dest = p.copy_skill(src, need)
    assert os.path.isfile(dest) and dest.endswith(os.path.join("bruecke", "bruecke.py"))
    assert need.status == "kopiert" and need.source == src
    assert "def build" in open(dest, encoding="utf-8").read()


def t_copy_skill_missing():
    p = _new("KopierenFehler")
    try:
        p.copy_skill(os.path.join(TMP, "nichts.py"))
    except P.ProjectError:
        return
    raise AssertionError("fehlende Skill-Datei kopiert")


def t_write_tool():
    p = _new("Werkzeug")
    path = p.write_tool("Kanal Rechner", "def flaeche(d):\n    return 3.14159 * d * d / 4\n",
                        purpose="Querschnittsflaeche")
    assert os.path.isfile(path) and path.endswith("kanal_rechner.py")
    src = open(path, encoding="utf-8").read()
    assert "Querschnittsflaeche" in src and "def flaeche" in src
    assert p.tools[0]["name"] == "kanal_rechner"
    p.write_tool("Kanal Rechner", "def flaeche(d):\n    return 1.0\n")
    assert len(p.tools) == 1, p.tools     # replaced, not duplicated


def t_agent_d_rendered():
    p = _new("AgentD")
    p.brief = "Einlasskanal für einen Vierzylinder."
    p.questions = ["Rund oder oval?"]
    p.answers = "Rund."
    p.set_criteria([{"name": "Wandstaerke", "description": "min. 4 mm"},
                    {"name": "Freigang", "description": "zum Ventilschaft"},
                    {"name": "Gewicht", "description": "so leicht wie möglich"}])
    p.matrix.set_pair(0, 1, 3)
    p.matrix.set_pair(0, 2, 5)
    p.matrix.set_pair(1, 2, 3)
    p.skills = [P.SkillNeed("einlasskanal", "der Kanal selbst", "gelernt")]
    p.write_tool("pruefer", "def f():\n    pass\n", "prüft Wandstärken")
    files = p.write_agent_d()
    assert len(files) == 6, files
    names = sorted(os.path.basename(f) for f in files)
    assert names == ["00-auftrag.md", "10-anforderungen.md",
                     "20-skills.md", "30-werkzeuge.md",
                     "40-parameter.md", "50-abhaengigkeiten.md"], names
    auftrag = open(files[0], encoding="utf-8").read()
    assert "Einlasskanal für einen Vierzylinder." in auftrag
    assert "Rund oder oval?" in auftrag
    anf = open(files[1], encoding="utf-8").read()
    assert "63.7 %" in anf, anf          # weight of Wandstärke
    assert "Konsistenzverhältnis" in anf
    skills = open(files[2], encoding="utf-8").read()
    assert "einlasskanal" in skills and "gelernt" in skills
    tools = open(files[3], encoding="utf-8").read()
    assert "pruefer" in tools and "prüft Wandstärken" in tools


def t_agent_d_empty_project():
    p = _new("Leer")
    files = p.write_agent_d()
    assert len(files) == 6
    assert "noch nicht beschrieben" in open(files[0], encoding="utf-8").read()
    assert "noch keine Kriterien" in open(files[1], encoding="utf-8").read()


def t_matrix_csv_in_project():
    p = _new("MatrixDatei")
    p.set_criteria(["a", "b", "c"])
    p.matrix.set_pair(0, 1, 3)
    path = p.write_matrix_csv()
    assert os.path.isfile(path) and path.endswith(P.MATRIX_FILE)


def t_prompt_block():
    p = _new("Promptblock")
    p.brief = "Ein Lagerbock."
    p.set_criteria(["Steifigkeit", "Gewicht"])
    p.matrix.set_pair(0, 1, 5)
    p.skills = [P.SkillNeed("lagerbock", "Grundkörper", "offen")]
    b = p.as_prompt_block()
    assert "Ein Lagerbock." in b and "Steifigkeit" in b and "%" in b
    assert "lagerbock" in b


def t_list_projects():
    base = os.path.join(TMP, "sammlung")
    os.makedirs(base, exist_ok=True)
    P.Project.create(base, "Eins")
    P.Project.create(base, "Zwei")
    os.makedirs(os.path.join(base, "kein_projekt"), exist_ok=True)
    found = P.list_projects(base)
    assert len(found) == 2, found
    assert P.list_projects(os.path.join(base, "gibtsnicht")) == []


def t_moved_project_loads():
    p = P.Project.create(TMP, "Umzug")
    p.brief = "x"
    p.save()
    neu = os.path.join(TMP, "umgezogen")
    shutil.move(p.path, neu)
    q = P.Project.load(neu)
    assert q.path == neu and q.brief == "x"


# ---- 5. parsing the planning answer --------------------------------------
PLAN = """Klar, hier der Plan.

```auftrag
Ein Zylinderkopf fuer einen Vierzylinder-Ottomotor, Guss.
```

```fragen
Wie viele Ventile pro Zylinder?
- Guss oder gefraest?
```

```skills
Einlass Kanal;Kanal vom Flansch zum Ventilsitz
brennraum;Brennraumkalotte
```

```werkzeuge
querschnitt_rechner;Stroemungsquerschnitt
```

```kriterien
Wandstaerke;Gussgrenze
Freigang;zum Ventilschaft
Gewicht;moeglichst leicht
```
"""


def t_parse_plan():
    plan = C.parse_project_plan(PLAN)
    assert plan["auftrag"].startswith("Ein Zylinderkopf")
    assert plan["fragen"] == ["Wie viele Ventile pro Zylinder?",
                              "Guss oder gefraest?"], plan["fragen"]
    assert plan["skills"][0]["name"] == "einlass_kanal", plan["skills"]
    assert plan["skills"][0]["description"].startswith("Kanal vom")
    assert plan["tools"][0]["name"] == "querschnitt_rechner"
    assert [c["name"] for c in plan["criteria"]] == ["Wandstaerke", "Freigang",
                                                     "Gewicht"]


def t_parse_plan_minimal():
    plan = C.parse_project_plan("```auftrag\nNur der Auftrag.\n```")
    assert plan["auftrag"] == "Nur der Auftrag."
    assert plan["fragen"] == [] and plan["skills"] == []
    assert plan["tools"] == [] and plan["criteria"] == []


def t_parse_plan_without_auftrag():
    try:
        C.parse_project_plan("```skills\na;b\n```")
    except C.T2GError:
        return
    raise AssertionError("Plan ohne Auftrag akzeptiert")


def t_parse_ratio():
    assert C._parse_ratio("3") == 3.0
    close(C._parse_ratio("1/5"), 0.2)
    close(C._parse_ratio("0,2"), 0.2)
    close(C._parse_ratio("1:7"), 1 / 7.0)
    for bad in ("abc", "", "0", "-3", "1/0"):
        assert C._parse_ratio(bad) is None, bad


def t_parse_pairs():
    crit = [{"name": "Wandstaerke"}, {"name": "Freigang"}, {"name": "Gewicht"}]
    raw = ("```paare\n"
           "Wandstaerke;Freigang;3;Guss zuerst\n"
           "wand staerke;gewicht;5;egal wie geschrieben\n"
           "Freigang;Freigang;9;Unsinn, sich selbst\n"
           "Freigang;Unbekannt;9;gibt es nicht\n"
           "Freigang;Wandstaerke;7;Dublette, wird verworfen\n"
           "Freigang;Gewicht;1/3;\n```")
    pairs = C.parse_pair_suggestions(raw, crit)
    assert len(pairs) == 3, pairs
    assert pairs[0][:3] == (0, 1, 3.0), pairs[0]
    assert pairs[1][:3] == (0, 2, 5.0), pairs[1]
    close(pairs[2][2], 1 / 3.0)
    assert pairs[0][3] == "Guss zuerst"


def t_pairs_feed_the_matrix():
    """The suggestions must drop straight into a matrix and rank sensibly."""
    crit = [{"name": "Wandstaerke"}, {"name": "Freigang"}, {"name": "Gewicht"}]
    raw = ("```paare\nWandstaerke;Freigang;3;\nWandstaerke;Gewicht;5;\n"
           "Freigang;Gewicht;3;\n```")
    m = P.PairwiseMatrix(criteria=[c["name"] for c in crit])
    for i, j, v, _ in C.parse_pair_suggestions(raw, crit):
        m.set_pair(i, j, v)
    assert m.missing_pairs() == []
    assert m.ranking()[0][0] == "Wandstaerke"
    assert m.is_consistent()


def t_plan_prompt():
    pr = C.build_project_plan_prompt("Zylinderkopf", "Vierzylinder, Guss",
                                     existing_skills=["bruecke", "einlasskanal"])
    assert "Zylinderkopf" in pr and "Vierzylinder" in pr and "einlasskanal" in pr


def t_pairs_prompt():
    crit = [{"name": "a", "description": "A"}, {"name": "b", "description": "B"},
            {"name": "c", "description": "C"}]
    pr = C.build_project_pairs_prompt("PROJEKT: X", crit)
    assert "a vs. b" in pr and "a vs. c" in pr and "b vs. c" in pr
    assert "ZU BEWERTENDE PAARE (3)" in pr


# ---- 6. helper tools ------------------------------------------------------
TOOL_OK = """import math


def querschnitt(d_mm, ovalitaet=1.0):
    \"\"\"Stroemungsquerschnitt in mm^2.\"\"\"
    a = d_mm / 2.0 * ovalitaet
    b = d_mm / 2.0 / ovalitaet
    return math.pi * a * b


def selbsttest():
    assert abs(querschnitt(10.0) - 78.5398) < 1e-3
    assert abs(querschnitt(10.0, 1.5) - querschnitt(10.0)) < 1e-6
    return True
"""


def t_tool_ok():
    problems, funcs = P.validate_tool_source(TOOL_OK)
    assert problems == [], problems
    assert funcs == ["querschnitt"], funcs


def t_tool_wrong_maths():
    """The model's own assert is what catches a wrong formula."""
    bad = TOOL_OK.replace("78.5398", "99.0")
    problems, _ = P.validate_tool_source(bad)
    assert any("Selbsttest fehlgeschlagen" in x for x in problems), problems


def t_tool_import_blocked():
    for mod in ("os", "subprocess", "socket", "urllib.request"):
        code = "import %s\ndef f():\n    return 1\ndef selbsttest():\n    return True\n" % mod
        problems, _ = P.validate_tool_source(code)
        assert any("Nicht erlaubter Import" in x for x in problems), (mod, problems)


def t_tool_no_file_access():
    code = ("def lies():\n    return open('/etc/passwd').read()\n"
            "def selbsttest():\n    lies()\n    return True\n")
    problems, _ = P.validate_tool_source(code)
    assert problems and "open" in problems[0], problems


def t_tool_without_selftest():
    problems, _ = P.validate_tool_source("def f(x):\n    return x\n")
    assert any("selbsttest" in x for x in problems), problems


def t_tool_selftest_must_return_true():
    code = "def f():\n    return 1\ndef selbsttest():\n    return 42\n"
    problems, _ = P.validate_tool_source(code)
    assert any("nicht True" in x for x in problems), problems


def t_tool_syntax_error():
    problems, _ = P.validate_tool_source("def f(:\n    pass\n")
    assert problems and "Syntax" in problems[0], problems


def t_tool_math_allowed():
    code = ("import math\ndef f(x):\n    return math.sqrt(x)\n"
            "def selbsttest():\n    assert f(9) == 3\n    return True\n")
    problems, funcs = P.validate_tool_source(code)
    assert problems == [] and funcs == ["f"], (problems, funcs)


def t_tool_written_into_project():
    p = _new("WerkzeugSchreiben")
    problems, funcs = P.validate_tool_source(TOOL_OK)
    assert problems == []
    path = p.write_tool("querschnitt_rechner", TOOL_OK, "Stroemungsquerschnitt")
    assert os.path.isfile(path)
    assert p.tools[0]["file"] == path
    # and it is still valid after the round trip through the file
    again, _ = P.validate_tool_source(open(path, encoding="utf-8").read())
    assert again == [], again


# ---- 7. project parameters -----------------------------------------------
def t_param_kinds_and_cast():
    f = P.ProjectParam("ventil_d", "Ventildurchmesser", "mm", 33, "float")
    assert isinstance(f.value, float) and f.value == 33.0
    i = P.ProjectParam("n_ventile", "Ventile je Zylinder", "-", 4.0, "int")
    assert i.value == 4 and isinstance(i.value, int)
    t = P.ProjectParam("werkstoff", "Werkstoff", "", "AlSi10Mg", "text")
    assert t.value == "AlSi10Mg"


def t_param_bad_name():
    for bad in ("2d", "mit leer", "", "a-b"):
        try:
            P.ProjectParam(bad)
        except P.ProjectError:
            continue
        raise AssertionError("ungültiger Name akzeptiert: %r" % bad)


def t_param_range():
    p = P.ProjectParam("d", "D", "mm", 33, "float", minimum=20, maximum=50)
    assert p.range_error() is None
    assert "über" in P.ProjectParam("d", "D", "mm", 60, "float", maximum=50).range_error()
    assert "unter" in P.ProjectParam("d", "D", "mm", 5, "float", minimum=20).range_error()


def t_param_from_row():
    p = P.param_from_row(("ventil_d", "Ventildurchmesser", "mm", 33.0, 20.0, 50.0))
    assert p.kind == "float" and p.value == 33.0 and p.maximum == 50.0
    n = P.param_from_row(("n_ventile", "Anzahl", "-", 4, 2, 8))
    assert n.kind == "int", n.kind


def t_set_param_keeps_answer():
    """Re-asking a question must not wipe the answer already given."""
    p = _new("ParamErhalt")
    p.set_param(P.ProjectParam("ventil_d", "Ventil", "mm", None, "float"))
    p.answer_mask({"ventil_d": 33})
    assert p.param("ventil_d").value == 33.0
    p.set_param(P.ProjectParam("ventil_d", "Ventil (Einlass)", "mm", None, "float"))
    assert p.param("ventil_d").value == 33.0, "Antwort verloren"
    assert p.param("ventil_d").label == "Ventil (Einlass)"


def t_answer_mask_reports_problems():
    p = _new("Maske")
    p.set_params([P.ProjectParam("d", "D", "mm", None, "float", minimum=20, maximum=50),
                  P.ProjectParam("n", "N", "-", None, "int")])
    problems = p.answer_mask({"d": 80, "n": "drei"})
    assert any("über" in x for x in problems), problems
    assert any("keine ganze Zahl" in x for x in problems), problems
    assert p.param("d").value == 80.0      # stored anyway, flagged not lost


def t_open_questions():
    p = _new("Offen")
    p.set_params([P.ProjectParam("a", value=1), P.ProjectParam("b")])
    assert [x.name for x in p.open_questions()] == ["b"]
    p.answer_mask({"b": 2})
    assert p.open_questions() == []


def t_param_values_for_skills():
    p = _new("Werte")
    p.set_params([P.ProjectParam("ventil_d", value=33.0),
                  P.ProjectParam("offen")])
    assert p.param_values() == {"ventil_d": 33.0}


# ---- 8. knowledge graph ---------------------------------------------------
def _graph_project():
    p = _new("Graph%d" % len(P.list_projects(TMP)))
    p.set_params([P.ProjectParam("ventil_d_ein", "Einlassventil", "mm", 33.0),
                  P.ProjectParam("sitz_d", "Sitzdurchmesser", "mm", 29.0,
                                 source="abgeleitet")])
    p.skills = [P.SkillNeed("einlasskanal", status="gelernt"),
                P.SkillNeed("brennraum", status="gelernt"),
                P.SkillNeed("ventilfuehrung", status="kopiert"),
                P.SkillNeed("wassermantel", status="offen")]
    g = p.graph
    g.param_used_by("ventil_d_ein", "einlasskanal")
    g.param_used_by("ventil_d_ein", "brennraum")
    g.param_derived("ventil_d_ein", "sitz_d", "Sitz = 0,88 x Ventil")
    g.param_used_by("sitz_d", "ventilfuehrung")
    g.skills_fit("brennraum", "einlasskanal", "gemeinsame Sitzflaeche")
    return p


def t_graph_impact():
    p = _graph_project()
    hit = p.impact_of(["ventil_d_ein"])
    assert hit["params"] == ["sitz_d"], hit
    assert sorted(hit["skills"]) == ["brennraum", "einlasskanal",
                                     "ventilfuehrung"], hit


def t_graph_impact_narrow():
    p = _graph_project()
    hit = p.impact_of(["sitz_d"])
    assert hit["params"] == [] and hit["skills"] == ["ventilfuehrung"], hit


def t_graph_unknown_param_no_impact():
    p = _graph_project()
    assert p.impact_of(["gibtsnicht"]) == {"params": [], "skills": []}


def t_graph_mutual_fit():
    p = _graph_project()
    # fitting is mutual: touching either part puts the other on the list
    assert "einlasskanal" in p.impact_of(["s:brennraum"])["skills"]
    assert "brennraum" in p.impact_of(["s:einlasskanal"])["skills"]


def t_graph_cycle_terminates():
    g = P.KnowledgeGraph()
    g.add(P.pnode("a"), P.pnode("b"), "abgeleitet")
    g.add(P.pnode("b"), P.pnode("c"), "abgeleitet")
    g.add(P.pnode("c"), P.pnode("a"), "abgeleitet")   # circle
    hit = g.impact(["a"])
    assert sorted(hit["params"]) == ["b", "c"], hit


def t_graph_no_duplicate_edges():
    g = P.KnowledgeGraph()
    for _ in range(3):
        g.param_used_by("d", "kanal")
    assert len(g.edges) == 1, g.edges


def t_graph_params_of_skill():
    p = _graph_project()
    assert p.graph.params_of("brennraum") == ["ventil_d_ein"]
    assert p.graph.params_of("ventilfuehrung") == ["sitz_d"]
    assert p.graph.params_of("wassermantel") == []


def t_graph_bad_kind():
    try:
        P.KnowledgeGraph().add("p:a", "s:b", "quatsch")
    except P.ProjectError:
        return
    raise AssertionError("unbekannte Kantenart akzeptiert")


def t_mark_affected():
    p = _graph_project()
    touched = p.mark_affected(["ventil_d_ein"])
    assert sorted(touched) == ["brennraum", "einlasskanal", "ventilfuehrung"], touched
    assert {s.name: s.status for s in p.skills}["brennraum"] == "zu pruefen"
    assert {s.name: s.status for s in p.skills}["wassermantel"] == "offen"


def t_mermaid():
    p = _graph_project()
    mer = p.graph.to_mermaid()
    assert mer.startswith("```mermaid") and "graph LR" in mer
    assert "p_ventil_d_ein([ventil_d_ein])" in mer, mer
    assert mer.count("---|passt_an|") == 1, "gegenseitige Kante doppelt gezeichnet"


def t_graph_persists():
    p = _graph_project()
    p.save()
    q = P.Project.load(p.path)
    assert len(q.graph.edges) == len(p.graph.edges)
    assert q.impact_of(["ventil_d_ein"])["skills"], q.graph.edges
    assert [x.name for x in q.params] == ["ventil_d_ein", "sitz_d"]
    assert q.param("ventil_d_ein").value == 33.0
    assert q.param("sitz_d").source == "abgeleitet"


def t_agent_d_parameter_and_graph():
    p = _graph_project()
    files = p.write_agent_d()
    par = open(files[4], encoding="utf-8").read()
    assert "ventil_d_ein" in par and "33.0" in par and "Einlassventil" in par
    dep = open(files[5], encoding="utf-8").read()
    assert "mermaid" in dep and "ventilfuehrung" in dep
    assert "ändern →" in dep, dep


def t_prompt_block_has_params_and_graph():
    p = _graph_project()
    b = p.as_prompt_block()
    assert "ventil_d_ein" in b and "33.0 mm" in b
    assert "Abhängigkeiten" in b and "->" in b


# ---- 9. the conversation survives a restart ------------------------------
def t_chat_persists():
    p = _new("ChatSpeicher")
    p.add_chat("Du", "bitte lege eine baugruppe mit 6 modellen an")
    p.add_chat("Agent", "Baugruppe angelegt.")
    p.set_param(P.ProjectParam("bohrung", "Bohrung", "mm", 86.0))
    p.save()
    q = P.Project.load(p.path)
    assert len(q.chat) == 2, q.chat
    assert q.chat[0][1].startswith("bitte lege")
    assert q.chat_transcript()[1] == ("Agent", "Baugruppe angelegt.")
    assert q.param("bohrung").value == 86.0


def t_chat_trimmed():
    p = _new("ChatKuerzung")
    for i in range(30):
        p.add_chat("Du", "zeile %d" % i, limit=10)
    assert len(p.chat) == 10 and p.chat[-1][1] == "zeile 29"


def t_chat_ignores_empty():
    p = _new("ChatLeer")
    p.add_chat("Du", "   ")
    p.add_chat("Du", "")
    assert p.chat == []


print("Running T2G project tests\n")
check("slugify", t_slugify)
check("Paarliste", t_pair_indices)
check("Kehrwert", t_reciprocal)
check("set_pair umgedreht", t_set_pair_reversed)
check("Lehrbuchbeispiel (Saaty)", t_known_example)
check("perfekt konsistent -> CR 0", t_perfectly_consistent)
check("Widerspruch erkannt", t_inconsistent_detected)
check("schlechteste Urteile", t_worst_pairs)
check("3 Kriterien: Schuld verteilt sich", t_worst_pairs_three_criteria_share_the_blame)
check("ohne Urteile: Gleichgewicht", t_equal_when_empty)
check("leer / ein Kriterium", t_single_and_empty)
check("ungültige Eingaben", t_bad_input)
check("CSV hin und zurück", t_csv_roundtrip)
check("Skalenbeschriftung", t_scale_label)
check("Skill-Zuordnung", t_match_skills)
check("Gegenteile sind kein Treffer", t_opposites_are_not_matches)
check("Namensaehnlichkeit", t_similarity_shapes)
check("Projekt anlegen", t_create_layout)
check("Projekt nicht doppelt", t_create_twice_refused)
check("speichern/laden", t_save_load_roundtrip)
check("fehlendes Projekt", t_load_missing)
check("Kriterienwechsel erhält Urteile", t_set_criteria_keeps_judgements)
check("Skill kopieren", t_copy_skill)
check("Skill kopieren: Fehler", t_copy_skill_missing)
check("Werkzeug schreiben", t_write_tool)
check("agent.d erzeugen", t_agent_d_rendered)
check("agent.d bei leerem Projekt", t_agent_d_empty_project)
check("Matrix-CSV im Projekt", t_matrix_csv_in_project)
check("Prompt-Block", t_prompt_block)
check("Projekte auflisten", t_list_projects)
check("verschobenes Projekt", t_moved_project_loads)
check("Plan parsen", t_parse_plan)
check("Plan minimal", t_parse_plan_minimal)
check("Plan ohne Auftrag", t_parse_plan_without_auftrag)
check("Verhaeltniszahlen", t_parse_ratio)
check("Paarvorschlaege parsen", t_parse_pairs)
check("Vorschlaege -> Matrix", t_pairs_feed_the_matrix)
check("Plan-Prompt", t_plan_prompt)
check("Paar-Prompt", t_pairs_prompt)
check("Werkzeug: gueltig", t_tool_ok)
check("Werkzeug: falsche Formel faellt auf", t_tool_wrong_maths)
check("Werkzeug: Importe gesperrt", t_tool_import_blocked)
check("Werkzeug: kein Dateizugriff", t_tool_no_file_access)
check("Werkzeug: Selbsttest verlangt", t_tool_without_selftest)
check("Werkzeug: Selbsttest muss True liefern", t_tool_selftest_must_return_true)
check("Werkzeug: Syntaxfehler", t_tool_syntax_error)
check("Werkzeug: math erlaubt", t_tool_math_allowed)
check("Werkzeug ins Projekt geschrieben", t_tool_written_into_project)
check("Parameter: Typen", t_param_kinds_and_cast)
check("Parameter: schlechter Name", t_param_bad_name)
check("Parameter: Grenzen", t_param_range)
check("Parameter aus Zeile", t_param_from_row)
check("Parameter: Antwort bleibt erhalten", t_set_param_keeps_answer)
check("Eingabemaske meldet Probleme", t_answer_mask_reports_problems)
check("offene Fragen", t_open_questions)
check("Werte fuer Skills", t_param_values_for_skills)
check("Graph: Wirkung einer Aenderung", t_graph_impact)
check("Graph: enge Wirkung", t_graph_impact_narrow)
check("Graph: unbekannter Parameter", t_graph_unknown_param_no_impact)
check("Graph: passt_an wirkt beidseitig", t_graph_mutual_fit)
check("Graph: Zyklus terminiert", t_graph_cycle_terminates)
check("Graph: keine Doppelkanten", t_graph_no_duplicate_edges)
check("Graph: Parameter eines Bauteils", t_graph_params_of_skill)
check("Graph: unbekannte Kantenart", t_graph_bad_kind)
check("betroffene Bauteile markieren", t_mark_affected)
check("Mermaid-Diagramm", t_mermaid)
check("Graph bleibt erhalten", t_graph_persists)
check("agent.d: Parameter + Graph", t_agent_d_parameter_and_graph)
check("Prompt-Block: Parameter + Graph", t_prompt_block_has_params_and_graph)
check("Chat ueberlebt Neustart", t_chat_persists)
check("Chat wird gekuerzt", t_chat_trimmed)
check("Chat ignoriert Leerzeilen", t_chat_ignores_empty)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILS:", len(FAILS))
for name, e in FAILS:
    print("  -", name, "->", repr(e))
if FAILS:
    sys.exit(1)
print("ALL PROJECT TESTS PASSED")
