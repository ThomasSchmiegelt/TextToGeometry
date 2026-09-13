# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless tests for the conversational mode (no FreeCAD needed)."""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---- Part / FreeCAD stubs -------------------------------------------------
fake_part = types.ModuleType("Part")


class _S:
    def __init__(self, kind, args=()):
        self.kind, self.args = kind, args

    def cut(self, o):
        return _S(self.kind + "-cut", (self, o))

    def fuse(self, o):
        return _S(self.kind + "+fuse", (self, o))

    def translate(self, v):
        pass


def _mk(kind):
    def f(*a, **kw):
        return _S(kind, a)
    return f


for nm in ("makeBox", "makeCylinder", "makeSphere", "makeCone", "makeTorus"):
    setattr(fake_part, nm, _mk(nm))
sys.modules["Part"] = fake_part

fake_fc = types.ModuleType("FreeCAD")


class Vector:
    def __init__(self, x=0, y=0, z=0):
        self.x, self.y, self.z = x, y, z


fake_fc.Vector = Vector
sys.modules["FreeCAD"] = fake_fc

import T2GCore as T  # noqa: E402

FAILS = []


def check(name, fn):
    try:
        fn()
        print("  ok   %s" % name)
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print("  FAIL %s -> %r" % (name, e))


OBJS = [
    {"name": "Box", "type": "Part::Feature", "label": "Grundplatte",
     "volume": 64000.0, "solids": 1,
     "bbox": {"xmin": 0, "xmax": 40, "ymin": 0, "ymax": 40, "zmin": 0, "zmax": 40}},
    {"name": "Cyl", "type": "Part::Feature", "label": "Cyl",
     "volume": 1000.0, "solids": 1,
     "bbox": {"xmin": 0, "xmax": 10, "ymin": 0, "ymax": 10, "zmin": 0, "zmax": 20}},
]


def _rec(sel=None):
    return T.OpRecorder(OBJS, sel or [], shape_lookup=lambda n: _S("shape:" + n))


# ---- 1. document context --------------------------------------------------
def t_describe_empty():
    txt = T.describe_document([], [])
    assert "leer" in txt, txt


def t_describe_objects():
    txt = T.describe_document(OBJS, ["Box"])
    assert "Box" in txt and "Cyl" in txt, txt
    assert "Grundplatte" in txt, txt
    assert "64000" in txt, txt
    assert "Auswahl: Box" in txt, txt


def t_describe_no_selection():
    assert "nichts ausgewählt" in T.describe_document(OBJS, [])


# ---- 2. reply parsing -----------------------------------------------------
def t_parse_question():
    r = T.parse_chat_reply("```frage\nWelcher Durchmesser?\n```")
    assert r.kind == "question" and "Durchmesser" in r.text, r


def t_parse_question_english_tag():
    r = T.parse_chat_reply("```question\nWhich face?\n```")
    assert r.kind == "question", r


def t_parse_code():
    r = T.parse_chat_reply("bla\n```python\nadd(1)\n```\nblub")
    assert r.kind == "code" and r.text == "add(1)", r


def t_parse_bare_question():
    r = T.parse_chat_reply("Wie tief soll die Bohrung sein?")
    assert r.kind == "question", r


def t_parse_garbage():
    try:
        T.parse_chat_reply("hier ist x = 1 ohne alles")
    except T.T2GError:
        return
    raise AssertionError("Müll wurde akzeptiert")


def t_parse_question_wins_over_code():
    # a model that asks AND guesses: the question must win, nothing is built
    raw = "```frage\nDurchmesser?\n```\n```python\nadd(1)\n```"
    assert T.parse_chat_reply(raw).kind == "question"


# ---- 3. session prompt ----------------------------------------------------
def t_prompt_has_context():
    s = T.ChatSession()
    p = s.build_prompt("Ergänze eine Bohrung", T.describe_document(OBJS, ["Box"]))
    assert "Box" in p and "Ergänze eine Bohrung" in p, p


def t_prompt_has_history():
    s = T.ChatSession()
    s.add_user("Mach eine Platte")
    s.add_assistant("add(Part.makeBox(10,10,10))")
    p = s.build_prompt("mach sie dicker", "kontext")
    assert "Mach eine Platte" in p and "VERLAUF" in p, p


def t_prompt_pending_question():
    s = T.ChatSession()
    s.pending_question = "Welcher Durchmesser?"
    p = s.build_prompt("10 mm", "kontext")
    assert "Welcher Durchmesser?" in p and "antwortet" in p, p


def t_history_trim():
    s = T.ChatSession(max_turns=4)
    for i in range(10):
        s.add_user("u%d" % i)
    assert len(s.history) == 4, len(s.history)
    assert s.history[-1].text == "u9"


def t_reset():
    s = T.ChatSession()
    s.add_user("x")
    s.pending_question = "y"
    s.reset()
    assert s.history == [] and s.pending_question is None


# ---- 4. op recorder -------------------------------------------------------
def t_names_and_selection():
    r = _rec(["Box"])
    assert r.names() == ["Box", "Cyl"], r.names()
    assert r.selected() == ["Box"]


def t_info_unknown():
    try:
        _rec().info("Nix")
    except T.T2GError as e:
        assert "Nix" in str(e) and "Box" in str(e), e
        return
    raise AssertionError("unbekanntes Objekt akzeptiert")


def t_replace_unknown_rejected():
    try:
        _rec().replace("Nix", _S("s"))
    except T.T2GError:
        return
    raise AssertionError("replace auf unbekanntes Objekt akzeptiert")


def t_record_all_ops():
    r = _rec()
    r.add(_S("neu"), name="Grundplatte")
    r.replace("Box", _S("x"))
    r.part("Bauteil1", ["Box"])
    r.assembly("Baugruppe", ["Box", "Cyl"])
    r.fem("Box", fixed="zmin", load="zmax", force_n=500)
    r.note("Annahme: Stahl")
    kinds = [o["op"] for o in r.ops]
    assert kinds == ["add", "replace", "part", "assembly", "fem"], kinds
    assert r.ops[4]["force_n"] == 500.0
    assert r.notes == ["Annahme: Stahl"]
    assert "Baugruppe" in r.summary()


# ---- 5. executing model code ---------------------------------------------
BOHRUNG = """
import Part, FreeCAD
n = selected()[0] if selected() else names()[-1]
s = shape(n)
bb = info(n)["bbox"]
cx = (bb["xmin"] + bb["xmax"]) / 2.0
cy = (bb["ymin"] + bb["ymax"]) / 2.0
bohr = Part.makeCylinder(5.0, bb["zmax"] - bb["zmin"] + 2,
                         FreeCAD.Vector(cx, cy, bb["zmin"] - 1))
replace(n, s.cut(bohr))
"""


def t_exec_bohrung():
    r = T.exec_chat_code(BOHRUNG, _rec(["Box"]))
    assert len(r.ops) == 1 and r.ops[0]["op"] == "replace", r.ops
    assert r.ops[0]["name"] == "Box"
    assert r.ops[0]["shape"].kind.endswith("-cut")


def t_exec_uses_last_without_selection():
    r = T.exec_chat_code(BOHRUNG, _rec([]))
    assert r.ops[0]["name"] == "Cyl", r.ops


def t_exec_new_part():
    r = T.exec_chat_code(
        'import Part\nadd(Part.makeBox(100, 60, 8), name="Grundplatte")', _rec())
    assert r.ops[0]["op"] == "add" and r.ops[0]["name"] == "Grundplatte"


def t_exec_assembly():
    r = T.exec_chat_code('assembly("BG", selected() or names()[:2])', _rec())
    assert r.ops[0]["members"] == ["Box", "Cyl"], r.ops


def t_exec_fem():
    r = T.exec_chat_code(
        'fem(names()[0], fixed="zmin", load="zmax", force_n=500.0)', _rec())
    o = r.ops[0]
    assert o["op"] == "fem" and o["target"] == "Box" and o["force_n"] == 500.0


def t_exec_common_builtins_available():
    """Code that uses hasattr/round/sum must run -- it did not, and cost steps."""
    code = ("werte = [1.0, 2.0, 3.5]\n"
            "n = len(werte)\n"
            "s = round(sum(werte), 2)\n"
            "ok = all(isinstance(w, float) for w in werte)\n"
            "grosse = sorted(werte, reverse=True)\n"
            "hat = hasattr(werte, 'append')\n"
            "note('%d Werte, Summe %.2f, ok=%s, groesstes %.1f, hasattr=%s'\n"
            "     % (n, s, ok, grosse[0], hat))\n")
    r = T.exec_chat_code(code, _rec())
    assert r.notes == ["3 Werte, Summe 6.50, ok=True, groesstes 3.5, hasattr=True"], r.notes


def t_exec_dangerous_builtins_absent():
    """open/eval/exec stay out of reach."""
    for snippet in ("open('/etc/passwd')", "eval('1+1')", "exec('x=1')",
                    "compile('1', 'x', 'eval')", "globals()", "vars()"):
        try:
            T.exec_chat_code(snippet, _rec())
        except Exception as e:  # noqa: BLE001
            assert "not defined" in str(e) or isinstance(e, T.T2GError), (snippet, e)
            continue
        raise AssertionError("erlaubt: %s" % snippet)


def t_exec_import_blocked():
    try:
        T.exec_chat_code("import os\nadd(1)", _rec())
    except T.T2GError as e:
        assert "os" in str(e), e
        return
    raise AssertionError("os-Import wurde erlaubt")


def t_exec_no_document_access():
    try:
        T.exec_chat_code("FreeCAD.ActiveDocument.removeObject('Box')", _rec())
    except Exception:
        return  # AttributeError on the stub / T2GError -- both fine
    raise AssertionError("Dokumentzugriff wurde erlaubt")


def t_exec_shape_of_unknown():
    try:
        T.exec_chat_code('shape("Nix")', _rec())
    except T.T2GError:
        return
    raise AssertionError("shape() auf unbekanntes Objekt akzeptiert")


print("Running T2G chat tests\n")
check("describe: leeres Dokument", t_describe_empty)
check("describe: Objekte + Auswahl", t_describe_objects)
check("describe: ohne Auswahl", t_describe_no_selection)
check("parse: Rückfrage", t_parse_question)
check("parse: question-Tag", t_parse_question_english_tag)
check("parse: Code", t_parse_code)
check("parse: Frage ohne Fence", t_parse_bare_question)
check("parse: Müll abgelehnt", t_parse_garbage)
check("parse: Frage schlägt Code", t_parse_question_wins_over_code)
check("prompt: enthält Kontext", t_prompt_has_context)
check("prompt: enthält Verlauf", t_prompt_has_history)
check("prompt: offene Rückfrage", t_prompt_pending_question)
check("session: Verlauf gekürzt", t_history_trim)
check("session: reset", t_reset)
check("recorder: names/selection", t_names_and_selection)
check("recorder: info unbekannt", t_info_unknown)
check("recorder: replace unbekannt", t_replace_unknown_rejected)
check("recorder: alle Ops", t_record_all_ops)
check("exec: Bohrung -> replace", t_exec_bohrung)
check("exec: ohne Auswahl letztes Objekt", t_exec_uses_last_without_selection)
check("exec: neues Bauteil", t_exec_new_part)
check("exec: Baugruppe", t_exec_assembly)
check("exec: FEM", t_exec_fem)
check("exec: uebliche builtins da", t_exec_common_builtins_available)
check("exec: gefaehrliche builtins fehlen", t_exec_dangerous_builtins_absent)
check("exec: Import blockiert", t_exec_import_blocked)
check("exec: kein Dokumentzugriff", t_exec_no_document_access)
check("exec: shape() unbekannt", t_exec_shape_of_unknown)

print("\nFAILS:", len(FAILS))
for name, e in FAILS:
    print("  -", name, "->", repr(e))
if FAILS:
    sys.exit(1)
print("ALL CHAT TESTS PASSED")
