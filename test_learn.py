# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for web research + learning a skill.

Network access is only exercised when T2G_TEST_NET=1; everything else runs
offline against recorded payloads.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---- Part / FreeCAD stubs (enough for skill validation) -------------------
if "Part" not in sys.modules:
    fake_part = types.ModuleType("Part")

    class _S:
        def __init__(self, vol=1000.0):
            self.Volume = vol
            self.BoundBox = _BB()

        def cut(self, o):
            return _S(max(1.0, self.Volume - getattr(o, "Volume", 0.0)))

        def fuse(self, o):
            return _S(self.Volume + getattr(o, "Volume", 0.0))

        def translate(self, v):
            pass

        def rotate(self, *a):
            pass

    class _BB:
        XMin = YMin = ZMin = 0.0
        XMax = YMax = ZMax = 10.0
        XLength = YLength = ZLength = 10.0

    def _box(l=10, w=10, h=10, *a, **k):
        return _S(float(l) * float(w) * float(h))

    def _cyl(r=5, h=10, *a, **k):
        return _S(3.14159 * float(r) ** 2 * float(h))

    fake_part.makeBox = _box
    fake_part.makeCylinder = _cyl
    fake_part.makeCone = _cyl
    fake_part.makeSphere = lambda r=5, *a, **k: _S(4.18 * float(r) ** 3)
    fake_part.makeTorus = _cyl
    sys.modules["Part"] = fake_part

if "FreeCAD" not in sys.modules:
    fake_fc = types.ModuleType("FreeCAD")

    class Vector:
        def __init__(self, x=0, y=0, z=0):
            self.x, self.y, self.z = x, y, z

    fake_fc.Vector = Vector
    sys.modules["FreeCAD"] = fake_fc

import T2GCore as T        # noqa: E402
import T2GSkills as S      # noqa: E402

FAILS = []


def check(name, fn):
    try:
        fn()
        print("  ok   %s" % name)
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print("  FAIL %s -> %r" % (name, e))


# ---- 1. HTML reduction ----------------------------------------------------
def t_html_to_text():
    html = ("<html><head><style>b{x}</style></head><body><h1>Kanal</h1>"
            "<script>evil()</script><p>Ein Einlasskanal f&uuml;hrt Luft.</p>"
            "<ul><li>rund</li><li>oval</li></ul></body></html>")
    txt = T.html_to_text(html)
    assert "evil" not in txt and "{x}" not in txt, txt
    assert "Einlasskanal führt Luft" in txt, txt
    assert "rund" in txt and "oval" in txt, txt


def t_html_article_only():
    """Navigation chrome must not reach the model's context."""
    html = ("<html><body><nav>Hauptmenü</nav><header>Jetzt spenden</header>"
            "<main><p>Der Einlasskanal fuehrt das Gemisch vom Ansaugflansch "
            "zum Ventilsitz und bestimmt den Fuellungsgrad.</p>"
            "<ul><li>Anmelden</li><li>Suche</li></ul></main>"
            "<footer>Impressum</footer></body></html>")
    txt = T.html_to_text(html, article_only=True)
    assert "Einlasskanal fuehrt das Gemisch" in txt, txt
    for junk in ("Hauptmenü", "Jetzt spenden", "Anmelden", "Impressum"):
        assert junk not in txt, (junk, txt)


def t_html_keeps_short_text_when_not_article():
    txt = T.html_to_text("<p>rund</p><p>oval</p>")
    assert "rund" in txt and "oval" in txt


def t_count_units_shared():
    """T2GCore and T2GProject must agree on what a count is."""
    import T2GProject as PJ
    for unit, want in (("Stück", "int"), ("stk", "int"), ("-", "int"),
                       ("Anzahl", "int"), ("mm", "float"), ("Grad", "float")):
        row = T.parse_param_lines("n;N;%s;4;1;8" % unit)[0]
        assert PJ.param_from_row(row).kind == want, (unit, row)


def t_html_empty():
    assert T.html_to_text("") == ""


# ---- 2. URL guard ---------------------------------------------------------
def t_scheme_guard():
    for bad in ("file:///etc/passwd", "ftp://example.invalid/x", "javascript:1",
                "/etc/passwd", ""):
        try:
            T.web_fetch(bad)
        except T.T2GError as e:
            assert "http" in str(e).lower(), (bad, e)
        else:
            raise AssertionError("Schema akzeptiert: %r" % bad)


# ---- 3. research result formatting ---------------------------------------
def t_research_block():
    r = T.ResearchResult(query="Einlasskanal", text="Ein Kanal.",
                         sources=[("Ansaugstutzen", "https://de.wikipedia.org/wiki/X")])
    b = r.as_prompt_block()
    assert "Einlasskanal" in b and "Ansaugstutzen" in b and "Ein Kanal." in b, b


def t_research_empty_block():
    assert "Keine Recherche" in T.ResearchResult(query="x").as_prompt_block()


def t_research_disabled_does_not_call_net():
    def boom(*a, **k):
        raise AssertionError("Netzzugriff trotz deaktivierter Recherche")
    orig = T._web_get
    T._web_get = boom
    try:
        r = T.research_topic("Einlasskanal", urls=[], use_wikipedia=False)
        assert r.text == "" and r.sources == []
    finally:
        T._web_get = orig


# ---- 4. parsing the analysis answer --------------------------------------
ANALYSE = """Gerne.

```fragen
Sind die Kanäle rund oder oval?
- Wie viele Kanäle pro Zylinder?
```

```parameter
laenge;Kanallänge;mm;120;40;400
d_ein;Einlassdurchmesser;mm;32;10;80
wand;Wandstärke;mm;4;1;20
winkel;Neigung;Grad;30;0;80
```
"""


def t_parse_analysis():
    q, params = T.parse_skill_analysis(ANALYSE)
    assert len(q) == 2 and q[1].startswith("Wie viele"), q
    assert len(params) == 4, params
    assert params[0] == ("laenge", "Kanallänge", "mm", 120, 40, 400), params[0]
    assert params[3][2] == "Grad"


def t_parse_analysis_without_questions():
    q, params = T.parse_skill_analysis("```parameter\na;A;mm;5;1;10\n```")
    assert q == [] and len(params) == 1


def t_parse_analysis_missing_params():
    try:
        T.parse_skill_analysis("```fragen\nWas denn?\n```")
    except T.T2GError:
        return
    raise AssertionError("fehlender Parameterblock akzeptiert")


def t_param_lines_repairs():
    rows = T.parse_param_lines(
        "2bad;X;mm;1;0;2\n"          # invalid name -> dropped
        "ok wert;Label;mm;5;10;2\n"  # min>max -> swapped, name cleaned
        "zu;kurz\n"                  # too few fields -> dropped
        "d;D;mm;99;1;10\n")          # default above max -> clamped
    names = [r[0] for r in rows]
    assert names == ["ok_wert", "d"], rows
    assert rows[0][4] == 2 and rows[0][5] == 10, rows[0]
    assert rows[1][3] == 10, rows[1]


def t_param_kind_by_unit():
    """Lengths/angles must stay continuous; only counts become integers."""
    rows = T.parse_param_lines(
        "d;Durchmesser;mm;45;20;80\n"
        "w;Winkel;Grad;30;0;90\n"
        "n;Anzahl Schrauben;-;4;2;8\n")
    d, w, n = rows
    assert isinstance(d[3], float) and isinstance(d[4], float), d
    assert isinstance(w[3], float), w
    assert isinstance(n[3], int), n
    # and the resulting skill parameter accepts a fractional value
    sp = S._param_from_tuple(d)
    assert sp.kind == "float", sp
    assert sp.range_error(sp.cast(67.5)) is None


def t_parse_code():
    code = T.parse_skill_code("Hier:\n```python\ndef build(params):\n    return []\n```")
    assert code.startswith("def build(params):"), code


def t_parse_code_without_fence():
    assert T.parse_skill_code("def build(params):\n    return []").startswith("def build")


def t_parse_code_rejects_prose():
    try:
        T.parse_skill_code("Ich würde das so bauen: nimm ein Rohr.")
    except T.T2GError:
        return
    raise AssertionError("Prosa als Code akzeptiert")


# ---- 5. prompt building ---------------------------------------------------
def t_analyse_prompt():
    r = T.ResearchResult(query="Einlasskanal", text="Fakten.",
                         sources=[("W", "https://x/y")])
    p = T.build_skill_analyse_prompt("Einlasskanal", r, "Für einen 4-Zylinder.")
    assert "Einlasskanal" in p and "Fakten." in p and "4-Zylinder" in p, p


def t_code_prompt_with_feedback():
    params = [("laenge", "Länge", "mm", 100, 10, 500)]
    p = T.build_skill_code_prompt("Kanal", params, answers="rund",
                                  previous_code="def build(params): pass",
                                  problems=["build() lieferte keine Solids"])
    assert "laenge" in p and "keine Solids" in p and "SCHLUG FEHL" in p, p


# ---- 6. validating a generated skill -------------------------------------
GOOD = '''def build(params):
    import Part
    laenge = float(params["laenge"])
    d_ein = float(params["d_ein"])
    wand = float(params["wand"])
    aussen = Part.makeCylinder(d_ein / 2.0 + wand, laenge)
    innen = Part.makeCylinder(d_ein / 2.0, laenge)
    return [aussen.cut(innen)]
'''
PARAMS = [("laenge", "Länge", "mm", 120, 40, 400),
          ("d_ein", "Durchmesser", "mm", 32, 10, 80),
          ("wand", "Wandstärke", "mm", 4, 1, 20)]


def t_validate_good():
    problems, shapes = S.validate_skill_source("einlasskanal", PARAMS, GOOD)
    assert problems == [], problems
    assert len(shapes) == 1


def t_validate_syntax_error():
    problems, _ = S.validate_skill_source("x", PARAMS, "def build(params):\n  return [")
    assert problems and "Syntax" in problems[0], problems


def t_validate_no_build():
    problems, _ = S.validate_skill_source("x", PARAMS, "def baue(p): return []")
    assert problems and "build" in problems[0], problems


def t_validate_runtime_error():
    problems, _ = S.validate_skill_source(
        "x", PARAMS, 'def build(params):\n    import Part\n'
                     '    laenge = params["laenge"]\n    d_ein = params["d_ein"]\n'
                     '    wand = params["wand"]\n    return [1 / 0]')
    assert any("scheiterte" in p for p in problems), problems


def t_validate_empty_result():
    problems, _ = S.validate_skill_source(
        "x", PARAMS, 'def build(params):\n    laenge = params["laenge"]\n'
                     '    d_ein = params["d_ein"]\n    wand = params["wand"]\n'
                     '    return []')
    assert any("keine Solids" in p for p in problems), problems


def t_validate_unused_params():
    problems, _ = S.validate_skill_source(
        "x", PARAMS, 'def build(params):\n    import Part\n'
                     '    return [Part.makeBox(10, 10, 10)]')
    assert any("kommen im Code nicht vor" in p for p in problems), problems


def t_validate_import_blocked():
    """A learned skill must not be able to import anything it likes."""
    code = ('def build(params):\n    import os\n'
            '    laenge = params["laenge"]\n    d_ein = params["d_ein"]\n'
            '    wand = params["wand"]\n    return [os.getcwd()]\n')
    problems, _ = S.validate_skill_source("x", PARAMS, code)
    assert any("os" in p and ("nicht erlaubt" in p or "not allowed" in p)
               for p in problems), problems


def t_validate_allows_part():
    problems, shapes = S.validate_skill_source("x", PARAMS, GOOD)
    assert problems == [] and shapes, problems


def t_validate_bad_name():
    problems, _ = S.validate_skill_source("2kanal", PARAMS, GOOD)
    assert any("Name" in p for p in problems), problems


def t_learned_skill_roundtrip():
    import tempfile
    out = tempfile.mkdtemp(prefix="t2g_learn_")
    problems, _ = S.validate_skill_source("einlasskanal", PARAMS, GOOD)
    assert problems == [], problems
    path = S.create_skill("einlasskanal", "Gelernter Einlasskanal", PARAMS,
                          GOOD, out_dir=out)
    eng = S.SkillEngine(out).load_all()
    assert "einlasskanal" in eng.registry.names(), eng.registry.names()
    shapes, vals, issues = eng.build("einlasskanal", {"laenge": 200})
    assert len(shapes) == 1 and vals["laenge"] == 200, (vals, issues)
    assert os.path.isfile(path)


# ---- 7. optional: live network -------------------------------------------
def t_live_wikipedia():
    if os.environ.get("T2G_TEST_NET") != "1":
        raise NotImplementedError("übersprungen (T2G_TEST_NET != 1)")
    r = T.wikipedia_search("Ansaugstutzen", limit=2)
    assert r.text and r.sources, (r.text[:100], r.errors)


# ---- 8. refining an existing skill ---------------------------------------
def t_refine_prompt():
    pr = T.build_skill_refine_prompt(
        "einlasskanal", PARAMS, GOOD,
        goal="Uebergang zum Ventilsitz kegelig ausfuehren",
        project_block="Gewichtete Kriterien:\n- Wandstaerke: 40 %",
        measurements="1 Solid, 68489 mm^3")
    assert "einlasskanal" in pr and "kegelig" in pr
    assert "Wandstaerke: 40 %" in pr and "68489" in pr
    assert "def build(params):" in pr


def t_refine_prompt_with_feedback():
    pr = T.build_skill_refine_prompt("x", PARAMS, GOOD, previous_code="def build(p): pass",
                                     problems=["build() lieferte keine Solids"])
    assert "SCHLUG FEHL" in pr and "keine Solids" in pr


def t_parse_refinement_code_only():
    code, params = T.parse_skill_refinement(
        "```python\ndef build(params):\n    return []\n```")
    assert code.startswith("def build(params):")
    assert params == [], params


def t_parse_refinement_with_params():
    raw = ("```parameter\nlaenge;Laenge;mm;120;40;400\nneu;Neuer Wert;mm;5;1;20\n```\n"
           "```python\ndef build(params):\n    return []\n```")
    code, params = T.parse_skill_refinement(raw)
    assert len(params) == 2 and params[1][0] == "neu", params
    assert isinstance(params[0][3], float), params[0]
    assert code.startswith("def build")


def t_parse_refinement_rejects_prose():
    try:
        T.parse_skill_refinement("Ich wuerde den Kanal kegelig auslaufen lassen.")
    except T.T2GError:
        return
    raise AssertionError("Prosa als Verfeinerung akzeptiert")


def t_parse_tool_code():
    code = T.parse_tool_code(
        "Hier:\n```python\ndef f():\n    return 1\ndef selbsttest():\n    return True\n```")
    assert code.startswith("def f():")


def t_parse_tool_code_needs_selftest():
    try:
        T.parse_tool_code("```python\ndef f():\n    return 1\n```")
    except T.T2GError as e:
        assert "selbsttest" in str(e), e
        return
    raise AssertionError("Werkzeug ohne Selbsttest akzeptiert")


def t_thinking_levels_map():
    """Panel level -> what each backend actually understands."""
    assert T._thinking_for_ollama("auto") is None       # nichts senden
    assert T._thinking_for_ollama("off") is False
    assert T._thinking_for_ollama("low") == "low"
    assert T._thinking_for_ollama("minimal") == "low"   # Ollama kennt kein minimal
    assert T._thinking_for_pi("auto") == ""
    assert T._thinking_for_pi("off") == "off"
    assert T._thinking_for_pi("high") == "high"
    assert T._thinking_for_pi("quatsch") == ""


def t_with_thinking_copies():
    cfg = T.APIConfig(kind="ollama", model="m", thinking="low")
    hoch = T.with_thinking(cfg, "high")
    assert hoch.thinking == "high" and cfg.thinking == "low", "Original geändert"
    assert hoch.model == "m" and hoch.kind == "ollama"
    assert T.with_thinking(None, "high") is None


def t_tool_prompt():
    pr = T.build_tool_prompt("querschnitt_rechner", "Flaeche aus Durchmesser",
                             project_block="PROJEKT: Zylinderkopf")
    assert "querschnitt_rechner" in pr and "Zylinderkopf" in pr


def t_skill_versioning():
    """Refining must keep the previous version recoverable."""
    import tempfile
    out = tempfile.mkdtemp(prefix="t2g_ver_")
    v1 = 'def build(params):\n    return ["v1"]\n'
    v2 = 'def build(params):\n    return ["v2"]\n'
    S.create_skill("demo", "erste Fassung", PARAMS, v1, out_dir=out)
    path, backup = S.update_skill("demo", "zweite Fassung", PARAMS, v2, out_dir=out)
    assert backup and os.path.isfile(backup), backup
    assert '"v2"' in open(path, encoding="utf-8").read()
    assert '"v1"' in open(backup, encoding="utf-8").read()
    assert len(S.list_backups("demo", out)) == 1
    # the backup must not be picked up as a skill of its own
    eng = S.SkillEngine(out).load_all()
    assert eng.registry.names() == ["demo"], eng.registry.names()


def t_update_skill_restores_on_failure():
    import tempfile
    out = tempfile.mkdtemp(prefix="t2g_ver2_")
    v1 = 'def build(params):\n    return ["v1"]\n'
    path = S.create_skill("demo", "erste Fassung", PARAMS, v1, out_dir=out)
    try:
        S.update_skill("demo", "kaputt", PARAMS, "def build(params:\n", out_dir=out)
    except S.SkillError:
        pass
    else:
        raise AssertionError("kaputter Code wurde gespeichert")
    assert '"v1"' in open(path, encoding="utf-8").read(), "alte Fassung verloren"


def t_build_source_extract():
    module = ('# Kopf\nT2G_SKILL = {"name": "x"}\n\n'
              'def build(params):\n    return []\n')
    assert S.build_source(module).startswith("def build(params):")
    assert "T2G_SKILL" not in S.build_source(module)


print("Running T2G learn/web tests\n")
check("html -> text", t_html_to_text)
check("html: nur Artikeltext", t_html_article_only)
check("html: kurze Schnipsel bleiben", t_html_keeps_short_text_when_not_article)
check("Einheitenregel gemeinsam", t_count_units_shared)
check("html leer", t_html_empty)
check("nur http/https", t_scheme_guard)
check("Recherche-Block", t_research_block)
check("Recherche leer", t_research_empty_block)
check("Recherche aus = kein Netz", t_research_disabled_does_not_call_net)
check("Analyse parsen", t_parse_analysis)
check("Analyse ohne Fragen", t_parse_analysis_without_questions)
check("Analyse ohne Parameter", t_parse_analysis_missing_params)
check("Parameterzeilen reparieren", t_param_lines_repairs)
check("Parametertyp nach Einheit", t_param_kind_by_unit)
check("Code parsen", t_parse_code)
check("Code ohne Fence", t_parse_code_without_fence)
check("Prosa ist kein Code", t_parse_code_rejects_prose)
check("Analyse-Prompt", t_analyse_prompt)
check("Code-Prompt mit Feedback", t_code_prompt_with_feedback)
check("Validierung: gut", t_validate_good)
check("Validierung: Syntaxfehler", t_validate_syntax_error)
check("Validierung: kein build", t_validate_no_build)
check("Validierung: Laufzeitfehler", t_validate_runtime_error)
check("Validierung: leeres Ergebnis", t_validate_empty_result)
check("Validierung: Parameter ignoriert", t_validate_unused_params)
check("Validierung: Import gesperrt", t_validate_import_blocked)
check("Validierung: Part erlaubt", t_validate_allows_part)
check("Validierung: schlechter Name", t_validate_bad_name)
check("gelernter Skill: Roundtrip", t_learned_skill_roundtrip)
check("Verfeinerungs-Prompt", t_refine_prompt)
check("Verfeinerung mit Fehlermeldung", t_refine_prompt_with_feedback)
check("Verfeinerung: nur Code", t_parse_refinement_code_only)
check("Verfeinerung: mit Parametern", t_parse_refinement_with_params)
check("Verfeinerung: Prosa abgelehnt", t_parse_refinement_rejects_prose)
check("Werkzeug-Code parsen", t_parse_tool_code)
check("Werkzeug braucht Selbsttest", t_parse_tool_code_needs_selftest)
check("Denktiefe: Abbildung", t_thinking_levels_map)
check("Denktiefe: Kopie statt Aenderung", t_with_thinking_copies)
check("Werkzeug-Prompt", t_tool_prompt)
check("Skill-Versionierung", t_skill_versioning)
check("Verfeinerung schlaegt fehl -> alte Fassung bleibt", t_update_skill_restores_on_failure)
check("build_source extrahiert", t_build_source_extract)

try:
    t_live_wikipedia()
    print("  ok   Wikipedia live")
except NotImplementedError as e:
    print("  --   Wikipedia live %s" % e)
except Exception as e:  # noqa: BLE001
    FAILS.append(("Wikipedia live", e))
    print("  FAIL Wikipedia live -> %r" % e)

print("\nFAILS:", len(FAILS))
for name, e in FAILS:
    print("  -", name, "->", repr(e))
if FAILS:
    sys.exit(1)
print("ALL LEARN TESTS PASSED")
