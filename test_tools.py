# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Tests for the external tool registry (macros, add-ons, Python modules)."""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import T2GTools as X  # noqa: E402

FAILS = []
TMP = tempfile.mkdtemp(prefix="t2g_tools_")


def check(name, fn):
    try:
        fn()
        print("  ok   %s" % name)
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print("  FAIL %s -> %r" % (name, e))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ---- 1. macros ------------------------------------------------------------
def t_macros_found():
    d = os.path.join(TMP, "Macro")
    write(os.path.join(d, "Bohrbild.FCMacro"),
          '"""Setzt ein Lochbild auf die Auswahl."""\nimport FreeCAD\n')
    write(os.path.join(d, "Alt.py"), "# Zaehlt die Solids im Dokument\nx = 1\n")
    write(os.path.join(d, "notizen.txt"), "kein Makro")
    tools = X.discover_macros([d])
    namen = sorted(t.name for t in tools)
    assert namen == ["Alt", "Bohrbild"], namen
    b = [t for t in tools if t.name == "Bohrbild"][0]
    assert b.description == "Setzt ein Lochbild auf die Auswahl.", b.description
    assert b.kind == "makro" and b.path.endswith(".FCMacro")
    a = [t for t in tools if t.name == "Alt"][0]
    assert a.description == "Zaehlt die Solids im Dokument", a.description


def t_macros_missing_dir():
    assert X.discover_macros([os.path.join(TMP, "gibtsnicht")]) == []


def t_macro_without_doc():
    d = os.path.join(TMP, "Macro2")
    write(os.path.join(d, "Stumm.FCMacro"), "import FreeCAD\nprint(1)\n")
    t = X.discover_macros([d])[0]
    assert t.description == "", t.description


# ---- 2. add-ons -----------------------------------------------------------
def _fake_addon(name, cmds, beschreibung="Ein Testaddon"):
    folder = os.path.join(TMP, "Mod", name)
    write(os.path.join(folder, "package.xml"),
          '<?xml version="1.0"?>\n<package format="1">\n'
          '  <name>%s</name>\n  <description>%s</description>\n</package>\n'
          % (name, beschreibung))
    write(os.path.join(folder, "commands.py"),
          "\n".join('Gui.addCommand("%s", X())' % c for c in cmds))
    return folder


def t_addons_and_commands():
    _fake_addon("freecad.zahnrad", ["ZR_Stirnrad", "ZR_Kegelrad"],
                "Zahnräder für FreeCAD")
    tools = X.discover_addons([os.path.join(TMP, "Mod")])
    addons = [t for t in tools if t.kind == "addon"]
    befehle = [t for t in tools if t.kind == "befehl"]
    assert len(addons) == 1 and addons[0].name == "freecad.zahnrad"
    assert addons[0].description == "Zahnräder für FreeCAD"
    assert sorted(t.name for t in befehle) == ["ZR_Kegelrad", "ZR_Stirnrad"]
    assert befehle[0].command == befehle[0].name


def t_addons_skip_self():
    _fake_addon("TextToGeometry", ["T2G_Panel"])
    tools = X.discover_addons([os.path.join(TMP, "Mod")])
    assert not any(t.name == "TextToGeometry" for t in tools)
    assert not any(t.command == "T2G_Panel" for t in tools)


def t_addon_commands_direct():
    folder = _fake_addon("freecad.probe", ["P_Eins", "P_Zwei", "P_Eins"])
    cmds = X.addon_commands(folder)
    assert cmds == ["P_Eins", "P_Zwei"], cmds


# ---- 3. python tools ------------------------------------------------------
def t_python_file_tool():
    path = write(os.path.join(TMP, "py", "rechner.py"),
                 '"""Kleine Rechenhilfe."""\n'
                 "def flaeche(d):\n    return 3.14 * d * d / 4\n"
                 "def _intern():\n    return 1\n")
    tools = X.discover_python_tools([path])
    assert [t.name for t in tools] == ["rechner.flaeche"], tools
    assert tools[0].description == "Kleine Rechenhilfe."
    assert tools[0].entry == "flaeche" and tools[0].module == "rechner"


def t_python_package_uses_all():
    pkg = os.path.join(TMP, "pkg", "meinpaket")
    write(os.path.join(pkg, "__init__.py"),
          '"""Ein Paket."""\n'
          "from .kern import pruefe, Ding\n\n"
          '__all__ = ["pruefe", "Ding"]\n')
    write(os.path.join(pkg, "kern.py"),
          "def pruefe(x):\n    return x\n\nclass Ding:\n    pass\n")
    tools = X.discover_python_tools([pkg])
    namen = [t.name for t in tools]
    assert namen == ["meinpaket.pruefe"], namen      # Klassen fallen raus
    assert tools[0].module == "meinpaket"


def t_python_tool_runs():
    path = write(os.path.join(TMP, "py2", "werkzeug.py"),
                 "def verdopple(x):\n    return x * 2\n")
    tool = X.discover_python_tools([path])[0]
    assert X.call_python_tool(tool, x=21) == 42


def t_python_tool_bad_entry():
    path = write(os.path.join(TMP, "py3", "leer.py"), "def da():\n    return 1\n")
    tool = X.discover_python_tools([path])[0]
    tool.entry = "gibtsnicht"
    try:
        X.call_python_tool(tool)
    except X.ToolError:
        return
    raise AssertionError("fehlende Funktion akzeptiert")


def t_import_does_not_pollute_syspath():
    path = write(os.path.join(TMP, "py4", "sauber.py"), "def f():\n    return 1\n")
    vorher = list(sys.path)
    X.call_python_tool(X.discover_python_tools([path])[0])
    assert sys.path == vorher, "sys.path verändert"


def t_module_functions():
    path = write(os.path.join(TMP, "py5", "m.py"),
                 "def a():\n    pass\ndef _b():\n    pass\nclass C:\n    pass\n")
    assert X.module_functions(path) == ["a"]
    assert X.module_functions(os.path.join(TMP, "fehlt.py")) == []


# ---- 4. lookup and description -------------------------------------------
def t_find_tool():
    tools = [X.ExternalTool("befehl", "FCGear_InvoluteGear", command="FCGear_InvoluteGear"),
             X.ExternalTool("python", "rechner.flaeche", entry="flaeche")]
    assert X.find_tool(tools, "FCGear_InvoluteGear") is tools[0]
    assert X.find_tool(tools, "fcgear_involutegear") is tools[0]
    assert X.find_tool(tools, "flaeche") is tools[1]      # Suffix
    assert X.find_tool(tools, "") is None
    assert X.find_tool(tools, "unbekannt") is None


def t_describe_tools():
    tools = [X.ExternalTool("makro", "Bohrbild", "Setzt ein Lochbild.")]
    txt = X.describe_tools(tools)
    assert "[Makro] Bohrbild" in txt and "Lochbild" in txt
    assert "Keine externen" in X.describe_tools([])
    viele = [X.ExternalTool("makro", "M%d" % i) for i in range(50)]
    kurz = X.describe_tools(viele, limit=5)
    assert "und 45 weitere" in kurz


print("Running T2G tools tests\n")
check("Makros gefunden", t_macros_found)
check("Makros: fehlendes Verzeichnis", t_macros_missing_dir)
check("Makro ohne Beschreibung", t_macro_without_doc)
check("Add-ons und Befehle", t_addons_and_commands)
check("eigene Workbench uebersprungen", t_addons_skip_self)
check("Befehle direkt auslesen", t_addon_commands_direct)
check("Python-Datei als Werkzeug", t_python_file_tool)
check("Python-Paket nutzt __all__", t_python_package_uses_all)
check("Python-Werkzeug laeuft", t_python_tool_runs)
check("fehlende Funktion gemeldet", t_python_tool_bad_entry)
check("sys.path bleibt sauber", t_import_does_not_pollute_syspath)
check("Funktionen einer Datei", t_module_functions)
check("Werkzeug finden", t_find_tool)
check("Werkzeugliste beschreiben", t_describe_tools)

shutil.rmtree(TMP, ignore_errors=True)
print("\nFAILS:", len(FAILS))
for name, e in FAILS:
    print("  -", name, "->", repr(e))
if FAILS:
    sys.exit(1)
print("ALL TOOLS TESTS PASSED")
