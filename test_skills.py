# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Tests for T2GSkills (Skills engine + bridge skill).

Run headless:
    FreeCADCmd test_skills.py
or with the system interpreter plus Part/FreeCAD stubs:
    python3 test_skills.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# FreeCADCmd runs scripts but swallows stdout; redirect prints to a file so the
# harness can still capture results (and so plain python works unchanged).
_OUT_PATH = os.environ.get("T2G_TEST_OUT") or "/tmp/opencode/test_skills_out.txt"
if os.path.exists(_OUT_PATH):
    try:
        os.remove(_OUT_PATH)
    except OSError:
        pass
_out_fh = None
def _open_out():
    global _out_fh
    if _out_fh is None:
        d = os.path.dirname(_OUT_PATH)
        if d:
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass
        _out_fh = open(_OUT_PATH, "a", encoding="utf-8")
    return _out_fh

_orig_print = print
def print(*a, **k):
    _open_out().write((" ".join(str(x) for x in a) + "\n"))
    try:
        _out_fh.flush()
    except Exception:
        pass

FAILS = []


def check(name, fn):
    try:
        fn()
        print("  ok   " + name)
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print("  FAIL " + name + " -> " + repr(e))


# ---------------------------------------------------------------------------
# Ensure Part / FreeCAD are available (use real FreeCAD modules when running
# under FreeCADCmd, install lightweight stubs under plain python).
# ---------------------------------------------------------------------------
def _ensure_fc():
    try:
        import Part  # noqa: F401
        import FreeCAD  # noqa: F401
        return
    except Exception:
        pass
    import types as _t
    if "FreeCAD" not in sys.modules:
        fc = _t.ModuleType("FreeCAD")
        class _V:
            def __init__(self, x=0.0, y=0.0, z=0.0):
                self.x, self.y, self.z = x, y, z
        fc.Vector = _V
        sys.modules["FreeCAD"] = fc
    if "Part" not in sys.modules:
        P = _t.ModuleType("Part")
        class _Shape:
            pass
        P.Shape = _Shape
        P.makeBox = lambda *a, **k: None
        sys.modules["Part"] = P


_ensure_fc()

import T2GSkills as S  # noqa: E402
from T2GSkills import (  # noqa: E402
    SkillParam, SkillDefinition, SkillEngine, SkillError,
    validate_params, apply_rules, create_skill, load_skill_file,
    check_konnektivitaet,
)

SKILLS_DIR = os.path.join(HERE, "Skills")


def t_param_cast_range():
    p = SkillParam("span", "Span", "mm", 2000, 100, 10000)
    assert p.cast("2500") == 2500.0
    assert p.cast(2000) == 2000.0
    assert p.range_error(2000) is None
    assert p.range_error(50) is not None
    ip = SkillParam("n", "N", "", 5, 3, 50, kind="int")
    assert ip.cast(7) == 7 and isinstance(ip.cast("7"), int)
    # validate_params enforces bounds and raises
    try:
        validate_params(SkillDefinition(name="x", params=[p]), {"span": 99999})
        raise AssertionError("should raise")
    except SkillError:
        pass


def t_param_bad_name():
    try:
        SkillParam("1bad", "x")
        raise AssertionError("should raise")
    except SkillError:
        pass


def t_skillparam_bounds():
    try:
        SkillParam("x", "x", "", 1, 10, 5)
        raise AssertionError("should raise (min>max)")
    except SkillError:
        pass


def t_validate_defaults_and_unknown():
    d = SkillDefinition(
        name="x",
        params=[SkillParam("a", "A", "mm", 10, 1, 100),
                SkillParam("n", "N", "", 4, 1, 9, kind="int")],
    )
    v = validate_params(d, {"a": 5})
    assert v == {"a": 5, "n": 4}
    # unknown keys ignored
    v2 = validate_params(d, {"a": 3, "zzz": 1})
    assert v2 == {"a": 3, "n": 4}
    # out of range raises
    try:
        validate_params(d, {"a": 200})
        raise AssertionError("should raise")
    except SkillError:
        pass


def t_bridge_load():
    skill = load_skill_file(os.path.join(SKILLS_DIR, "bruecke", "bruecke.py"))
    assert skill.name == "bruecke"
    names = {p.name: p for p in skill.definition.params}
    assert set(names) == {
        "span", "depth", "pier_h", "pier_w", "deck_t",
        "n_vert", "truss_h", "chord_t", "bar_w", "dia_w"}
    assert "kollision" in skill.definition.pruefregeln
    assert "konnektivitaet" in skill.definition.pruefregeln


def t_bridge_build_default():
    eng = SkillEngine(SKILLS_DIR).load_all()
    assert "bruecke" in eng.registry.names()
    shapes, vals, probs = eng.build("bruecke", {})
    assert len(shapes) == 13, len(shapes)
    assert vals["span"] == 2000
    # bounding box of the compound
    import Part, FreeCAD
    comp = Part.makeCompound(shapes)
    b = comp.BoundBox
    assert abs(b.XMax - 2000) < 1
    assert abs(b.YMax - 400) < 1
    assert abs(b.ZMax - 1180) < 1
    assert probs == [], probs
    # volume sanity
    assert 1_000_000 < comp.Volume < 500_000_000


def t_bridge_variant():
    eng = SkillEngine(SKILLS_DIR).load_all()
    shapes, vals, probs = eng.build("bruecke", {"span": 5000, "n_vert": 7})
    # 2 piers + 1 deck + n_vert verticals + 1 chord + (n_vert-1) diagonals
    assert len(shapes) == 2 + 1 + 7 + 1 + (7 - 1), len(shapes)
    assert vals["n_vert"] == 7


def t_bridge_min_enforced():
    eng = SkillEngine(SKILLS_DIR).load_all()
    try:
        eng.build("bruecke", {"span": 10})
        raise AssertionError("should raise")
    except SkillError as e:
        assert "span" in str(e)


def t_unknown_rule_ignored():
    d = SkillDefinition(name="x", pruefregeln=["nichtexistent"])
    assert apply_rules(d, []) == []


def t_create_skill_roundtrip():
    import shutil
    tmpdir = _mk_tmp()
    path = create_skill(
        "probe",
        "Test-Skill",
        [("w", "Breite", "mm", 100, 10, 1000), ("h", "Hoehe", "mm", 50, 10, 500)],
        "def build(params):\n    w = params['w']\n    "
        "return [Part.makeBox(w, 10, 10, FreeCAD.Vector(0,0,0))]\n",
        out_dir=tmpdir,
    )
    assert os.path.isfile(path)
    sk = load_skill_file(path)
    assert sk.name == "probe"
    assert [p.name for p in sk.definition.params] == ["w", "h"]
    vals = validate_params(sk.definition, {})
    shapes = sk.build(vals)
    assert isinstance(shapes, list)
    shutil.rmtree(tmpdir, ignore_errors=True)


def _mk_tmp():
    import tempfile
    return tempfile.mkdtemp(prefix="t2g_skill_")


def t_get_engine_lazy():
    e = S.get_engine(SKILLS_DIR)
    assert isinstance(e, SkillEngine)
    assert "bruecke" in e.registry.names()


def t_konnektivitaet_empty():
    assert check_konnektivitaet([]) != []


def _have_real_part():
    import Part
    try:
        s = Part.makeBox(1, 1, 1)
        return hasattr(s, "BoundBox")
    except Exception:
        return False


def t_konnektivitaet_connected():
    if not _have_real_part():
        return  # needs real Part
    import Part, FreeCAD
    a = Part.makeBox(10, 10, 10, FreeCAD.Vector(0, 0, 0))
    b = Part.makeBox(10, 10, 10, FreeCAD.Vector(10, 0, 0))  # touches at x=10
    assert check_konnektivitaet([a, b]) == []
    c = Part.makeBox(10, 10, 10, FreeCAD.Vector(100, 100, 100))  # far away
    assert check_konnektivitaet([a, b, c]) != []


def t_bridge_build_real():
    if not _have_real_part():
        return  # needs real Part
    eng = SkillEngine(SKILLS_DIR).load_all()
    shapes, vals, probs = eng.build("bruecke", {})
    assert len(shapes) == 13
    assert probs == [], probs


print("Running T2GSkills tests\n")
check("param cast+range", t_param_cast_range)
check("param bad name", t_param_bad_name)
check("param bounds order", t_skillparam_bounds)
check("validate defaults/unknown", t_validate_defaults_and_unknown)
check("bridge loads", t_bridge_load)
check("bridge build default (13 solids)", t_bridge_build_default)
check("bridge parametric variant", t_bridge_variant)
check("bridge min enforced", t_bridge_min_enforced)
check("unknown rule ignored", t_unknown_rule_ignored)
check("create_skill roundtrip", t_create_skill_roundtrip)
check("get_engine lazy", t_get_engine_lazy)
check("konnektivitaet empty", t_konnektivitaet_empty)
check("konnektivitaet connected", t_konnektivitaet_connected)
check("bridge build (real Part)", t_bridge_build_real)

print("\nFAILS:", len(FAILS))
for name, e in FAILS:
    print("  -", name, "->", repr(e))
if FAILS:
    sys.exit(1)
print("ALL PASS")
