# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD GUI init for the TextToGeometry add-on.

FreeCAD exec()s this file at start-up in a namespace that already exposes
FreeCAD, FreeCADGui and Workbench (the C++ workbench base class).
"""

import T2GCommand  # noqa: F401  -- registers T2G_Generate with FreeCADGui


class T2GWorkbench(Workbench):

    MenuText = "TextToGeometry"
    ToolTip = "Natural-language text -> 3D FreeCAD geometry (local LLM)"
    AboutText = (
        "Type a description of the solid and TextToGeometry builds it "
        "with FreeCAD's Part API via the local Ollama model "
        "(qwen-gross:latest) through the pi CLI harness."
    )

    def __init__(self):
        import os

        import T2GCommand as _t2g

        _dir = os.path.dirname(os.path.abspath(_t2g.__file__))
        self.__class__.Icon = os.path.join(
            _dir, "Resources", "icons", "text-to-geometry.svg"
        )
        try:
            FreeCADGui.addIconPath(os.path.join(_dir, "Resources", "icons"))
        except Exception:
            pass

    def Initialize(self):
        self.appendToolbar("T2G", ["T2G_Generate"])
        self.appendMenu(["TextToGeometry"], ["T2G_Generate"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Activated(self):
        FreeCAD.Console.PrintMessage("TextToGeometry workbench activated\n")

    def Deactivated(self):
        FreeCAD.Console.PrintMessage("TextToGeometry workbench deactivated\n")


FreeCADGui.addWorkbench(T2GWorkbench)
