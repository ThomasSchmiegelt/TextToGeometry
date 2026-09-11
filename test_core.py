"""Headless tests for T2GCore (no real FreeCAD needed)."""
import sys, types, os, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---- Stub Part + FreeCAD so the sandbox can exec generated code headlessly ----
fake_part = types.ModuleType("Part")
class _S:
    def __init__(self, k, a): self.k, self.a = k, a
    def cut(self, o):   return _S(self.k, self.a)
    def fuse(self, o):  return _S(self.k, self.a)
    def common(self, o):return _S(self.k, self.a)
    def translate(self, v): pass
    def rotate(self, a, v, d): pass
def _mk(k): 
    def f(*a, **kw): return _S(k, a)
    return f
for nm in ("makeBox","makeCone","makeCylinder","makeSphere","makeTorus","makeTetrahedron"):
    setattr(fake_part, nm, _mk(nm))
def makePolygon(pts): return "polygon"
def Face(w): return _S("face", w)
def _extr(self, v): return _S(self.k + "+ex", v)
_S.extrude = _extr
fake_part.makePolygon = makePolygon
fake_part.Face = Face
sys.modules["Part"] = fake_part

fake_fc = types.ModuleType("FreeCAD")
class Vector:
    def __init__(self, x=0, y=0, z=0): self.x, self.y, self.z = x, y, z
fake_fc.Vector = Vector
sys.modules["FreeCAD"] = fake_fc

import T2GCore as T

# ---- 1. code-block extraction from recorded pi NDJSON streams ----
sample = '''
{"type":"session","version":3}
{"type":"agent_start"}
{"type":"message_start","message":{"role":"assistant","content":[{"type":"thinking","thinking":"x"}]}}
{"type":"message_end","message":{"role":"assistant","content":[{"type":"thinking","thinking":"x"},{"type":"text","text":"```python\\nimport Part\\n\\nresult = [Part.makeBox(40, 40, 40)]\\n```"}]}}
'''
code = T.extract_code_block(sample)
assert "makeBox(40" in code, code
print("[1] parse OK ->", repr(code))

# ---- 2. sandbox exec ----
shapes = T.exec_code_in_sandbox(code)
assert isinstance(shapes, list) and len(shapes) == 1, shapes
print("[2] sandbox exec OK ->", shapes)

# ---- 3. disallowed import rejected ----
try:
    T.exec_code_in_sandbox("import os\nresult = [None]")
except T.T2GError as e:
    print("[3] disallowed import OK ->", e)
else:
    raise AssertionError("os import was (wrongly) allowed")

# ---- 4. disallowed *runtime* import via __import__ ----
try:
    T.exec_code_in_sandbox("x = __import__('subprocess')\nresult = [None]")
except (T.T2GError, ImportError) as e:
    print("[4] runtime import blocked OK ->", type(e).__name__, str(e)[:80])
else:
    raise AssertionError("runtime __import__('subprocess') was (wrongly) allowed")

# ---- 5. multi-part result (hex prism list) ----
hexcode = '''
import Part
import math
import FreeCAD

r = 8.0 / math.cos(math.pi / 6)
pts = [FreeCAD.Vector(r * math.cos(2 * math.pi * i / 6), r * math.sin(2 * math.pi * i / 6), 0) for i in range(6)]
face = Part.Face(Part.makePolygon(pts))
result = [face.extrude(FreeCAD.Vector(0, 0, 5))]
'''
shapes = T.exec_code_in_sandbox(hexcode)
assert len(shapes) == 1
print("[5] hex prism OK ->", shapes)

# ---- 6. boolean (cube with hole) ----
holecode = '''
import Part
import FreeCAD

box = Part.makeBox(20, 20, 20)
hole = Part.makeCylinder(4, 20, FreeCAD.Vector(10, 10, 0))
result = [box.cut(hole)]
'''
shapes = T.exec_code_in_sandbox(holecode)
print("[6] cube-with-hole OK ->", shapes)

# ---- 7. missing result ----
try:
    T.exec_code_in_sandbox("import Part\nx = 5")
except T.T2GError as e:
    print("[7] missing result detected OK ->", e)
else:
    raise AssertionError("missing result was not caught")

# ---- 8. load_drawing_spec (namespaced + plain <desc>) ----
import xml.etree.ElementTree as _ET
def _write_svg(path, ns, body):
    attr = f' xmlns="{ns}"' if ns else ""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"<svg{attr}>{body}</svg>")
tmp_ok = os.path.join(tempfile.gettempdir(), "t2g_test_ok.svg")
_write_svg(tmp_ok, "http://www.w3.org/2000/svg",
           "<desc>UNITS mm\npiar x 0..100 H 0..200</desc>")
spec = T.load_drawing_spec(tmp_ok)
assert "mm" in spec and "piar" in spec, spec
print("[8] load_drawing_spec namespaced OK ->", spec[:40].replace("\n"," "))

tmp_plain = os.path.join(tempfile.gettempdir(), "t2g_test_plain.svg")
_write_svg(tmp_plain, "", "<desc>PLAIN spec text</desc>")
assert T.load_drawing_spec(tmp_plain) == "PLAIN spec text"
print("[9] load_drawing_spec plain OK")

# ---- 8b. load_drawing_spec errors ----
tmp_nodesc = os.path.join(tempfile.gettempdir(), "t2g_test_nodesc.svg")
_write_svg(tmp_nodesc, "http://www.w3.org/2000/svg", "<rect x='0'/>")
try:
    T.load_drawing_spec(tmp_nodesc)
except T.T2GError as e:
    print("[10] no <desc> rejected OK ->", str(e)[:60])
else:
    raise AssertionError("svg without <desc> was (wrongly) accepted")
try:
    T.load_drawing_spec(os.path.join(tempfile.gettempdir(), "no_such_file.svg"))
except T.T2GError as e:
    print("[11] missing file rejected OK")
else:
    raise AssertionError("missing file was (wrongly) accepted")

# ---- 12. build_drawing_prompt ----
prompt = T.build_drawing_prompt(spec)
assert "DRAWING SPEC" in prompt and "3D INTERPRETATION" in prompt, prompt[:120]
assert "result = [all solids]" in prompt
print("[12] build_drawing_prompt OK  len=", len(prompt))
try:
    T.build_drawing_prompt("   ")
except T.T2GError:
    print("[13] empty spec rejected OK")
else:
    raise AssertionError("empty spec was (wrongly) accepted")

print("ALL CORE TESTS PASSED")
