# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless E2E test: runs inside FreeCADCmd.

Pipeline exactly as the dialog does it:
  run_backend -> extract_code_block -> exec_code_in_sandbox -> addObject("Part::Feature") -> recompute
"""
import os
import sys

_here = (os.path.dirname(os.path.abspath(__file__))
         if "__file__" in globals() else os.getcwd())
if _here and os.path.isdir(_here):
    sys.path.insert(0, _here)

ok = True


def fail(msg):
    global ok
    ok = False
    print(f"FAIL: {msg}")


def main(prompt):
    import FreeCAD

    print("== FreeCAD", FreeCAD.Version())

    import T2GCore

    pi = T2GCore.find_pi_binary()
    print("== pi:", pi)

    raw = T2GCore.run_backend(prompt, pi_binary=pi, timeout_s=120)
    code = T2GCore.extract_code_block(raw)
    print("== generated code:\n" + code)

    shapes = T2GCore.exec_code_in_sandbox(code)
    print(f"== sandbox produced {len(shapes)} shape(s)")

    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("T2G_E2E")
    created = []
    for i, shp in enumerate(shapes):
        name = f"T2G_{i:02d}"
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shp
        created.append(obj)
    doc.recompute()

    for obj in created:
        print(f"== doc object {obj.Name}: Shape valid={obj.Shape.isValid()} "
              f"Solids={obj.Shape.Solids.__len__()} Vol={obj.Shape.Volume} mm^3 "
              f"Bounds=[{obj.Shape.BoundBox}]")
        if not obj.Shape.isValid():
            fail(f"shape of {obj.Name} is invalid")

    print("== doc objects:", [o.Name for o in doc.Objects])
    if ok:
        print("ALL E2E TESTS PASSED IN FREECAD")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    prompt = sys.argv[-1] if len(sys.argv) > 1 else "A hollow tube: outer diameter 40, inner diameter 20, length 100."
    main(prompt)
