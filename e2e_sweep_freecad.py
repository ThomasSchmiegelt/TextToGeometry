# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Headless E2E sweep test (FreeCADCmd) using the REAL LLM pipeline.

Runs the exact path the dialog uses:
  SweepConfig(generate_fn=...) -> _generate_once(run_backend -> extract_code_block
  -> exec_code_in_sandbox[list of shapes]) -> measure_shape(list) -> Target.check

Two variants, one measurable volume target both should satisfy.
"""
import os
import sys

_HERE = (os.path.dirname(os.path.abspath(__file__))
         if "__file__" in globals() else os.getcwd())
if os.path.isdir(_HERE):
    sys.path.insert(0, _HERE)

ok = True
_RLOG = open("/tmp/opencode/sweep_result.txt", "w", encoding="utf-8")


def _log(msg=""):
    _RLOG.write(str(msg) + "\n")
    _RLOG.flush()
    print(msg)


def _fail(msg):
    global ok
    ok = False
    _log("FAIL: " + str(msg))


def _verdict():
    _RLOG.write(("VERDICT=PASS" if ok else "VERDICT=FAIL") + "\n")
    _RLOG.flush()


def main():
    import FreeCAD
    import T2GCore
    import inspect

    pi = T2GCore.find_pi_binary()
    _log("== FreeCAD " + str(FreeCAD.Version()))
    _log("== pi: " + str(pi))
    _log("== T2GCore: " + T2GCore.__file__)
    _has_list = "isinstance(shape, (list, tuple))" in inspect.getsource(T2GCore.measure_shape)
    _log("== measure_shape list-handling: " + str(_has_list))
    if not _has_list:
        _fail("installed T2GCore.measure_shape lacks list handling (stale copy)")

    base = ("Baue einen einfachen Quader mit den Maessungen laenge (L/mm), "
            "breite (W/mm), hoehe (H/mm), die unten als VARIATION DATA angegeben "
            "werden. Verwende import Part. "
            "Letzte Zeile: result = [quader]")
    rows = [
        {"laenge": 40, "breite": 20, "hoehe": 10},   # 8000 mm^3
        {"laenge": 30, "breite": 30, "hoehe": 15},   # 13500 mm^3
    ]
    targets = [T2GCore.Target("volume", "<=", 15000.0, None)]

    events = {"rows": 0, "iters": 0}

    def _on_row(i, row, label):
        events["rows"] += 1
        _log("  row %d: %s %s" % (i, label, row))

    def _on_iter(i, row, label, itr, code, meas, fails, all_ok):
        events["iters"] += 1
        _log("    iter %d: vol=%.1f ok=%s fails=%s" % (itr, meas.volume_mm3, all_ok, fails))

    cfg = T2GCore.SweepConfig(
        base_prompt=base,
        rows=rows,
        targets=targets,
        density_kg_m3=7850.0,
        max_iterations=2,
        generate_fn=T2GCore._generate_once,
        on_row_start=_on_row,
        on_iteration=_on_iter,
    )
    results = T2GCore.run_sweep(cfg)

    _log("== rows seen: %d  iterations: %d" % (events["rows"], events["iters"]))
    if events["rows"] != 2:
        _fail("expected 2 rows, saw %d" % events["rows"])

    for r in results:
        nsh = len(r.shapes) if isinstance(r.shapes, (list, tuple)) else (1 if r.shapes is not None else 0)
        _log("  %s: ok=%s vol=%.1f iter=%d n_shapes=%d" % (
            r.label, r.ok, r.measurement.volume_mm3 if r.measurement else -1,
            r.iterations, nsh))
        if not r.ok:
            _fail("variant %s missed the volume target: %s" % (r.label, r.failures))
        if nsh < 1:
            _fail("variant %s produced no shapes" % r.label)

    # Drop the shapes into a doc to confirm they are valid Part.Shape objects.
    doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument("T2G_SWEEP")
    made = 0
    for r in results:
        shapes = r.shapes if isinstance(r.shapes, (list, tuple)) else [r.shapes]
        for shp in shapes:
            obj = doc.addObject("Part::Feature", "T2G_%02d" % made)
            obj.Shape = shp
            made += 1
    doc.recompute()
    for o in doc.Objects:
        _log("  doc %s: valid=%s vol=%.1f solids=%d" % (
            o.Name, o.Shape.isValid(), o.Shape.Volume, len(o.Shape.Solids)))
        if not o.Shape.isValid():
            _fail("shape %s invalid" % o.Name)

    # CSV export must run without error.
    outcsv = "/tmp/opencode/sweep_results.csv"
    T2GCore.export_results_csv(results, outcsv)
    with open(outcsv) as fh:
        _log("== csv header: " + fh.readline().strip())

    _log("== total verdict: " + ("PASS" if ok else "FAIL"))


try:
    main()
except Exception as exc:  # noqa: BLE001
    import traceback
    try:
        _RLOG.write("EXCEPTION: %r\n%s\n" % (exc, traceback.format_exc()))
    except Exception:
        pass
    raise
finally:
    _verdict()
