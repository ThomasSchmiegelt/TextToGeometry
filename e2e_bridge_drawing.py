# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Headless E2E: 2D bridge drawing (SVG) -> LLM decomposition -> 3D Part model.

Runs inside FreeCADCmd:
  svg <desc> spec -> prompt -> run_backend -> code -> sandbox -> checks

Checks: solid count, validity, bbox ~ X 2000 / Z 1180 / Y 400 mm, volume.
Result written to file (FreeCADCmd print buffering) and to stdout.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else None
if _here and os.path.isdir(_here):
    sys.path.insert(0, _here)

HERE = _here or os.getcwd()
SVG = os.path.join(HERE, "Resources/drawings/bridge.svg")
OUT = os.environ.get("T2G_OUT", "/tmp/opencode/t2g_bridge_out.txt")

lines = []


def log(msg=""):
    print(msg)
    lines.append(msg)


def finish(ok: bool, verdict: str):
    txt = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(txt + "\n\nVERDICT=" + verdict + "\n")
    sys.exit(0 if ok else 1)


def main():
    import FreeCAD
    log("== FreeCAD " + " ".join(str(x) for x in FreeCAD.Version()))
    log("== __name__ = " + repr(__name__))

    import T2GCore

    # ---- read drawing spec (via T2GCore) ----------------------------------
    spec = T2GCore.load_drawing_spec(SVG)
    log("== drawing spec:\n" + spec + "\n")

    # ---- build prompt (via T2GCore) ----------------------------------------
    prompt = T2GCore.build_drawing_prompt(spec)
    log("== prompt length: " + str(len(prompt)) + " chars")

    # ---- backend call ------------------------------------------------------
    pi = T2GCore.find_pi_binary()
    log("== pi: " + pi)
    raw = T2GCore.run_backend(prompt, pi_binary=pi, timeout_s=300)
    code = T2GCore.extract_code_block(raw)
    log("== generated code:\n" + code + "\n")

    # ---- sandbox -----------------------------------------------------------
    shapes = T2GCore.exec_code_in_sandbox(code)
    log("== sandbox produced " + str(len(shapes)) + " shape(s)")

    # ---- checks ------------------------------------------------------------
    problems = []
    import Part
    comp = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
    b = comp.BoundBox
    m = T2GCore.measure_shape(comp)
    log("== bounds  X " + repr(b.XMin) + ".." + repr(b.XMax))
    log("==          Y " + repr(b.YMin) + ".." + repr(b.YMax))
    log("==          Z " + repr(b.ZMin) + ".." + repr(b.ZMax))
    log("== volume  " + repr(m.volume_mm3) + " mm^3")
    log("== solids  " + str(m.n_solids) + "   faces " + str(m.n_faces))

    def close(got, want, rel):
        return abs(got - want) <= rel * abs(want)

    if not close(m.x_size, 2000.0, 0.05):
        problems.append("x_size %.1f vs 2000 (+/-5%%)" % m.x_size)
    if not close(m.z_size, 1180.0, 0.05):
        problems.append("z_size %.1f vs 1180 (+/-5%%)" % m.z_size)
    if not close(m.y_size, 400.0, 0.10):
        problems.append("y_size %.1f vs 400 (+/-10%%)" % m.y_size)
    if abs(m.z_range[0]) > 5.0:
        problems.append(f"z_min {m.z_range[0]:.1f} should be ~0 (ground)")
    if len(shapes) < 10:
        problems.append(f"expected >=10 solids, got {len(shapes)}")
    if m.volume_mm3 < 500000:
        problems.append(f"volume {m.volume_mm3:.0f} too small")
    for i, s in enumerate(shapes):
        if not s.isValid():
            problems.append("solid %d invalid" % i)

    if problems:
        for p in problems:
            log("PROBLEM: " + p)
        finish(False, "FAIL")

    # ---- add to a document (proof it enters a real model) --------------------
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("T2G_Bridge")
    for i, s in enumerate(shapes):
        obj = doc.addObject("Part::Feature", "Bridge_%02d" % i)
        obj.Shape = s
    doc.recompute()
    log("== document objects: " + str([o.Name for o in doc.Objects]))
    log(f"PASS: bridge drawing -> 3D model OK ({len(shapes)} solids, bounds match spec)")
    finish(True, "PASS")


if _here is not None:
    import traceback
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        log("EXCEPTION:\n" + traceback.format_exc())
        finish(False, "FAIL")
