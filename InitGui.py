# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
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
        # Grouped by what they do: panel | LLM | skills | backend.
        self.appendToolbar("T2G", [
            "T2G_Panel",
            "Separator",
            "T2G_Project",
            "T2G_Chat",
            "T2G_Generate",
            "Separator",
            "T2G_SkillBuild",
            "T2G_SkillLearn",
            "T2G_SkillDesign",
            "Separator",
            "T2G_ApiTest",
        ])
        self.appendMenu(["TextToGeometry"], [
            "T2G_Panel",
            "Separator",
            "T2G_Project",
            "T2G_Chat",
            "T2G_Generate",
            "Separator",
            "T2G_SkillBuild",
            "T2G_SkillLearn",
            "T2G_SkillDesign",
            "Separator",
            "T2G_ApiTest",
        ])

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Activated(self):
        FreeCAD.Console.PrintMessage("TextToGeometry workbench activated\n")
        # The toolbar exists only after FreeCAD has built it, and it is rebuilt
        # on every workbench switch -- so ask again each time, deferred.
        try:
            from PySide6 import QtCore

            import T2GCommand as _t2g
            QtCore.QTimer.singleShot(0, _t2g.ensure_toolbar_input)
            QtCore.QTimer.singleShot(600, _t2g.ensure_toolbar_input)
        except Exception as e:  # noqa: BLE001
            FreeCAD.Console.PrintWarning(
                "TextToGeometry: Eingabefeld in der Leiste nicht moeglich: "
                "%s\n" % e)

    def Deactivated(self):
        FreeCAD.Console.PrintMessage("TextToGeometry workbench deactivated\n")


FreeCADGui.addWorkbench(T2GWorkbench)
