"""Tests for the extended T2GCore (tables, targets, sweep)."""
import sys, types, os, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---- minimal Part/FreeCAD stubs (same as test_core) with a measurable shape ----
fake_part = types.ModuleType("Part")
class _Shape:
    def __init__(self, vol, bb, solids=1, faces=6):
        self.Volume = vol
        self.BoundBox = bb
        self.Solids = ["s"] * solids
        self.Faces = ["f"] * faces
class _BB:
    def __init__(self, lo, hi):
        self.XMin, self.XMax = lo[0], hi[0]
        self.YMin, self.YMax = lo[1], hi[1]
        self.ZMin, self.ZMax = lo[2], hi[2]
def _mk(k):
    def f(*a, **kw): raise NotImplementedError
    return f
for nm in ("makeBox","makeCone","makeCylinder","makeSphere","makeTorus","makeTetrahedron"):
    setattr(fake_part, nm, _mk(nm))
fake_part.makePolygon = _mk("makePolygon")
fake_part.Face = _mk("Face")
def _mkcompound(shapes):
    vol = sum(s.Volume for s in shapes)
    lo = (min(s.BoundBox.XMin for s in shapes),
          min(s.BoundBox.YMin for s in shapes),
          min(s.BoundBox.ZMin for s in shapes))
    hi = (max(s.BoundBox.XMax for s in shapes),
          max(s.BoundBox.YMax for s in shapes),
          max(s.BoundBox.ZMax for s in shapes))
    return _Shape(vol, _BB(lo, hi), solids=sum(len(s.Solids) for s in shapes),
                  faces=sum(len(s.Faces) for s in shapes))
fake_part.makeCompound = _mkcompound
sys.modules["Part"] = fake_part

fake_fc = types.ModuleType("FreeCAD")
class Vector:
    def __init__(self, x=0, y=0, z=0): self.x, self.y, self.z = x, y, z
fake_fc.Vector = Vector
sys.modules["FreeCAD"] = fake_fc

import T2GCore as T

def mk_shape(vol=1000.0, lo=(0.0,0.0,0.0), hi=(10.0,10.0,10.0)):
    return _Shape(vol, _BB(lo, hi), solids=1, faces=6)

print("== measure_shape ==")
m = T.measure_shape(mk_shape(8000.0, (0,0,0), (40,20,10)), density_kg_m3=7850.0)
assert abs(m.volume_mm3 - 8000.0) < 1e-6
# mass: 8000 mm^3 *1e-9 m^3 *7850 kg/m^3 *1000 g/kg = 62.8 g
assert abs(m.mass_g - 62.8) < 1e-6, m.mass_g
assert abs(m.x_size - 40) < 1e-9 and abs(m.y_size - 20) < 1e-9 and abs(m.z_size - 10) < 1e-9
print("    OK vol/mass/bbox:", m.volume_mm3, m.mass_g, m.x_size, m.y_size, m.z_size)

print("== measure_shape (list of shapes -> compound) ==")
s1 = mk_shape(500.0, (0,0,0), (10,10,5))
s2 = mk_shape(500.0, (0,0,5), (10,10,10))
ml = T.measure_shape([s1, s2], density_kg_m3=7850.0)
assert abs(ml.n_solids - 2) < 1e-9, ml.n_solids
assert abs(ml.volume_mm3 - 1000.0) < 1e-6, ml.volume_mm3
assert abs(ml.x_size - 10) < 1e-9 and abs(ml.z_size - 10) < 1e-9, (ml.x_size, ml.z_size)
# single-element list unwraps to the same as the bare shape
m1 = T.measure_shape([s1], density_kg_m3=7850.0)
assert abs(m1.volume_mm3 - 500.0) < 1e-6 and abs(m1.n_solids - 1) < 1e-9
print("    OK list -> compound:", ml.volume_mm3, ml.n_solids, "single-list vol:", m1.volume_mm3)

print("== Target.check ==")
t_mass = T.Target.mass(62.8, tol=1.0)
ok, msg = t_mass.check(m); assert ok, msg
t_vol_miss = T.Target.volume(5000.0, tol=1.0)
ok2, msg2 = t_vol_miss.check(m); assert not ok2
t_dim = T.Target.dim("x", 40.0, tol=1.0)
ok3, msg3 = t_dim.check(m); assert ok3, msg3
t_dim_le = T.Target.dim("z", 12.0, mode="<=")
ok4, msg4 = t_dim_le.check(m); assert ok4
print("    OK", [msg, msg2, msg3, msg4])

print("== render ==")
r = T.Target.mass(50).render(); assert "g" in r
rt = T.Target.text("must be watertight").render(); assert "free-text" in rt
print("    OK", r, "|", rt)

print("== build_prompt ==")
row = {"laenge": 40, "breite": 20}
p = T.build_prompt("Ein Quader", row, [T.Target.mass(50)], 7850.0, itr=1, max_itr=3)
assert "laenge = 40" in p and "Ein Quader" in p and "Material density" in p
p2 = T.build_prompt("Ein Quader", row, [T.Target.mass(50)], 7850.0,
                    itr=2, max_itr=3, feedbacks=["mass miss"], previous_measurement=m)
assert "iteration 2/3" in p2 and "mass" in p2.lower()
print("    OK base + feedback")

print("== read_table_csv ==")
with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
    f.write("a,b,c\n1,2,3\n4,5,6\n")
    csvpath = f.name
hdr, rows = T.read_table_csv(csvpath)
assert hdr == ["a","b","c"], hdr
assert rows == [["1","2","3"],["4","5","6"]], rows
print("    OK", hdr, rows)

print("== read_table_paste ==")
hdr, rows = T.read_table_paste("x,y\n1,2\n3,4")
assert hdr == ["x","y"] and rows[0] == ["1","2"]
hdr, rows = T.read_table_paste("a\tb\n1\t2\n3\t4")
assert hdr == ["a","b"] and rows == [["1","2"],["3","4"]]
hdr, rows = T.read_table_paste("a;b\n1;2")
assert hdr == ["a","b"]
print("    OK csv/tsv/semicolon")

print("== read_table_ssheet (fake object) ==")
class FakeSheet:
    def getNonEmptyRange(self): return ("A1", "C3")
    _data = {("A",1):"a",("B",1):"b",("C",1):"c",
             ("A",2):"1",("B",2):"2",("C",2):"3",
             ("A",3):"4",("B",3):"5",("C",3):"6"}
    def get(self, ref):
        col = T._ref_to_idx(ref)[0]; row = T._ref_to_idx(ref)[1]
        key = (T._colname(col), row+1)
        if key in self._data: return str(self._data[key])
        raise KeyError(ref)
fs = FakeSheet()
hdr, rows = T.read_table_ssheet(fs)
assert hdr == ["a","b","c"], hdr
assert rows == [["1","2","3"],["4","5","6"]], rows
print("    OK", hdr, rows)

print("== _ref_to_idx / _colname ==")
assert T._ref_to_idx("A1") == (0,0); assert T._ref_to_idx("B3") == (1,2)
assert T._ref_to_idx("AA10") == (26,9)
assert T._colname(0)=="A" and T._colname(25)=="Z" and T._colname(26)=="AA"
print("    OK")

print("== read_table_xlsx (hand-built file) ==")
def build_xlsx(path):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sharedstrings = (f'<?xml version="1.0" encoding="UTF-8"?>'
                     f'<sst xmlns="{ns}" count="9" uniqueCount="9">'
                     '<si><t>a</t></si><si><t>b</t></si><si><t>c</t></si>'
                     '<si><t>1</t></si><si><t>2</t></si><si><t>3</t></si>'
                     '<si><t>4</t></si><si><t>5</t></si><si><t>6</t></si></sst>')
    sheet = (f'<?xml version="1.0" encoding="UTF-8"?>'
             f'<worksheet xmlns="{ns}"><sheetData>'
             '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>'
             '<row r="2"><c r="A2" t="s"><v>3</v></c><c r="B2" t="s"><v>4</v></c><c r="C2" t="s"><v>5</v></c></row>'
             '<row r="3"><c r="A3" t="s"><v>6</v></c><c r="B3" t="s"><v>7</v></c><c r="C3" t="s"><v>8</v></c></row>'
             '</sheetData></worksheet>')
    workbook = (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<workbook xmlns="{ns}"><sheets><sheet name="Variants" sheetId="1"/></sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
              '</Relationships>')
    ct = ('<?xml version="1.0" encoding="UTF-8"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '</Types>')
    rootrels = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rootrels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wbrels)
        zf.writestr("xl/sharedStrings.xml", sharedstrings)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)

with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
    xlsxpath = f.name
build_xlsx(xlsxpath)
hdr, rows = T.read_table_xlsx(xlsxpath)
assert hdr == ["a","b","c"], hdr
assert rows == [["1","2","3"],["4","5","6"]], rows
print("    OK", hdr, rows)
# named sheet
hdr2, rows2 = T.read_table_xlsx(xlsxpath, sheet="Variants")
assert hdr2 == ["a","b","c"]
print("    OK named sheet")

print("== run_sweep (mock generate_fn) ==")
shape_cache = {}
def gen(prompt):
    # crude: return a shape sized 40x20x10, vol 8000
    return (prompt, mk_shape(8000.0, (0,0,0), (40,20,10)))

rows_in = [[("v1", 1), ("v2", 2)]]  # will use dict rows
cfg = T.SweepConfig(
    base_prompt="Ein Quader",
    rows=[{"laenge": 40, "breite": 20}, {"laenge": 40, "breite": 30}],
    targets=[T.Target.mass(62.8, tol=5.0)],
    density_kg_m3=7850.0,
    max_iterations=3,
    generate_fn=gen,
)
results = T.run_sweep(cfg)
assert len(results) == 2
assert results[0].ok and results[0].iterations == 1, (results[0].ok, results[0].iterations)
assert results[1].ok
print("    OK", [(r.label, r.ok, r.iterations) for r in results])

print("== run_sweep with failure (mass target impossible) ==")
cfg2 = T.SweepConfig(
    base_prompt="x",
    rows=[{"a": 1}],
    targets=[T.Target.mass(1e9, tol=1.0)],
    density_kg_m3=7850.0,
    max_iterations=2,
    generate_fn=gen,
)
res2 = T.run_sweep(cfg2)
assert res2[0].ok is False
assert res2[0].iterations == 2   # used up both iterations
print("    OK fail path iterations:", res2[0].iterations)

print("== cancel ==")
called = {"n":0}
def gen2(prompt):
    called["n"] += 1
    return (prompt, mk_shape())
cfg3 = T.SweepConfig(base_prompt="x",
    rows=[{"a":1},{"b":2},{"c":3}],
    targets=[], density_kg_m3=7850.0, max_iterations=1,
    generate_fn=gen2,
    should_cancel=lambda: called["n"] >= 2)
res3 = T.run_sweep(cfg3)
assert len(res3) <= 2, len(res3)
print("    OK", len(res3), "rows completed, cancel called")

print("== export_results_csv ==")
with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
    outcsv = f.name
T.export_results_csv(results, outcsv)
import csv as _csv
with open(outcsv) as fh:
    r2 = list(_csv.reader(fh))
assert r2[0][:3] == ["label","ok","iterations"], r2[0][:3]
assert "volume_mm3" in r2[0] and "mass_g" in r2[0]
print("    OK header:", r2[0])
print("    row:", r2[1])

print("ALL EXTENDED TESTS PASSED")
