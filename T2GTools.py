# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""External tools the workbench can call: macros, add-ons and Python modules.

Not everything has to be generated. A FreeCAD installation usually already
carries a lot of capability -- recorded macros, installed add-ons such as
``freecad.gears``, and plain Python packages like ``connection_detection``.
This module finds them and describes them uniformly so the agent can use them
the same way it uses its own skills.

Discovery is standard library only, so it is testable without FreeCAD; running
a tool needs FreeCAD and lives in the panel.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import sys
from dataclasses import asdict, dataclass, field

#: Where FreeCAD keeps macros, per platform and version layout.
MACRO_DIRS = (
    "~/.local/share/FreeCAD/Macro",
    "~/.local/share/FreeCAD/*/Macro",
    "~/.FreeCAD/Macro",
    "~/Library/Preferences/FreeCAD/Macro",
    "~/AppData/Roaming/FreeCAD/Macro",
)

MACRO_SUFFIXES = (".FCMacro", ".fcmacro", ".py")


class ToolError(Exception):
    pass


@dataclass
class ExternalTool:
    """One callable thing that already exists on this machine."""

    kind: str                 # makro | addon | python | befehl
    name: str
    description: str = ""
    path: str = ""            # file or directory
    module: str = ""          # importable module, for kind="python"
    entry: str = ""           # function inside that module
    command: str = ""         # FreeCAD command id, for kind="befehl"
    signature: str = ""       # "(modul, z1, z2)", for kind="python"
    source: str = ""          # where it was found

    def label(self) -> str:
        art = {"makro": "Makro", "addon": "Add-on", "python": "Python",
               "befehl": "Befehl"}.get(self.kind, self.kind)
        return f"[{art}] {self.name}"

    def as_line(self) -> str:
        rest = self.description.strip().splitlines()
        kopf = self.label() + (self.signature or "")
        return f"{kopf}: {rest[0] if rest else ''}".rstrip(": ")

    def entry_label(self) -> str:
        """Short name for what this tool produces, used to label its objects."""
        return self.entry or self.name.split(".")[-1] or self.name

    def to_dict(self) -> dict:
        return asdict(self)


def _expand(patterns) -> list:
    import glob

    out = []
    for pat in patterns:
        for path in glob.glob(os.path.expanduser(pat)):
            if os.path.isdir(path):
                out.append(path)
    return sorted(set(out))


def _first_doc(path: str) -> str:
    """The first docstring or comment block of a script, as its description."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(4000)
    except OSError:
        return ""
    try:
        tree = ast.parse(text)
        doc = ast.get_docstring(tree)
        if doc:
            return doc.strip().splitlines()[0][:200]
    except SyntaxError:
        pass
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") and len(line) > 3:
            return line.lstrip("# ").strip()[:200]
        if line and not line.startswith(("#", '"', "'")):
            break
    return ""


def discover_macros(dirs=None) -> list:
    """Every macro FreeCAD would offer in its macro menu."""
    out = []
    for folder in (dirs if dirs is not None else _expand(MACRO_DIRS)):
        if not os.path.isdir(folder):
            continue
        for entry in sorted(os.listdir(folder)):
            if not entry.endswith(MACRO_SUFFIXES):
                continue
            path = os.path.join(folder, entry)
            if not os.path.isfile(path):
                continue
            out.append(ExternalTool(
                kind="makro", name=os.path.splitext(entry)[0],
                description=_first_doc(path), path=path, source=folder))
    return out


def _addon_meta(folder: str) -> tuple:
    """(name, description) from package.xml or metadata.txt, else the folder."""
    name = os.path.basename(folder)
    desc = ""
    pkg = os.path.join(folder, "package.xml")
    if os.path.isfile(pkg):
        try:
            import xml.etree.ElementTree as ET

            root = ET.parse(pkg).getroot()

            def _text(tag):
                for el in root.iter():
                    if el.tag.split("}")[-1] == tag and (el.text or "").strip():
                        return el.text.strip()
                return ""

            name = _text("name") or name
            desc = _text("description")
        except Exception:  # noqa: BLE001
            pass
    if not desc:
        meta = os.path.join(folder, "metadata.txt")
        if os.path.isfile(meta):
            try:
                with open(meta, encoding="utf-8", errors="replace") as fh:
                    desc = fh.readline().strip()
            except OSError:
                pass
    return name, desc[:300]


def addon_commands(folder: str, limit: int = 40) -> list:
    """FreeCAD command ids an add-on registers, read from its source."""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "tests", "docs", "examples")]
        for f in files:
            if not f.endswith(".py"):
                continue
            try:
                with open(os.path.join(root, f), encoding="utf-8",
                          errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for m in re.finditer(r"addCommand\(\s*[\"']([A-Za-z0-9_.]+)[\"']",
                                 text):
                if m.group(1) not in found:
                    found.append(m.group(1))
                    if len(found) >= limit:
                        return found
    return found


def discover_addons(mod_dirs=None, skip=("TextToGeometry",)) -> list:
    """Installed add-ons, with the commands they register."""
    if mod_dirs is None:
        mod_dirs = _expand(("~/.local/share/FreeCAD/Mod",
                            "~/.local/share/FreeCAD/*/Mod",
                            "~/.FreeCAD/Mod",
                            "~/Library/Preferences/FreeCAD/Mod",
                            "~/AppData/Roaming/FreeCAD/Mod"))
    out, seen = [], set()
    for mod in mod_dirs:
        if not os.path.isdir(mod):
            continue
        for entry in sorted(os.listdir(mod)):
            folder = os.path.join(mod, entry)
            if not os.path.isdir(folder) or entry in skip or entry in seen:
                continue
            seen.add(entry)
            name, desc = _addon_meta(folder)
            cmds = addon_commands(folder)
            out.append(ExternalTool(
                kind="addon", name=name, description=desc, path=folder,
                source=mod, command=",".join(cmds)))
            for cmd in cmds:
                out.append(ExternalTool(
                    kind="befehl", name=cmd,
                    description="Befehl aus %s" % name,
                    path=folder, command=cmd, source=name))
    return out


def module_functions(path: str) -> list:
    """Top-level function names of a Python file, without importing it."""
    return [sig["name"] for sig in module_signatures(path)]


def module_signatures(path: str) -> list:
    """Name, argument list and own docstring of each public function.

    The prompt used to show the *module* docstring for every function, so a
    file with twelve helpers produced twelve identical lines and the agent
    could not tell `achsabstand` from `selbsttest`. Reading the signature
    costs nothing here -- it is the same AST walk.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return []
    out = []
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef) or n.name.startswith("_"):
            continue
        args = []
        stellen = list(n.args.posonlyargs) + list(n.args.args)
        vorgaben = list(n.args.defaults)
        ohne = len(stellen) - len(vorgaben)
        for i, a in enumerate(stellen):
            if i < ohne:
                args.append(a.arg)
            else:
                try:
                    args.append("%s=%s" % (a.arg,
                                           ast.unparse(vorgaben[i - ohne])))
                except Exception:  # noqa: BLE001 - a name is better than none
                    args.append(a.arg + "=…")
        if n.args.vararg:
            args.append("*" + n.args.vararg.arg)
        for a in n.args.kwonlyargs:
            args.append(a.arg + "=…")
        if n.args.kwarg:
            args.append("**" + n.args.kwarg.arg)
        doc = (ast.get_docstring(n) or "").strip().splitlines()
        out.append({"name": n.name, "args": args,
                    "doc": doc[0].strip() if doc else ""})
    return out


def discover_python_tools(paths) -> list:
    """Python files or packages offered as tools.

    A directory with an ``__init__.py`` counts as a package: its ``__all__``
    (or public functions) become the callable entries.
    """
    out = []
    for raw in (paths or []):
        path = os.path.abspath(os.path.expanduser(str(raw)))
        if os.path.isfile(path) and path.endswith(".py"):
            modul = os.path.splitext(os.path.basename(path))[0]
            for sig in module_signatures(path):
                out.append(ExternalTool(
                    kind="python", name="%s.%s" % (modul, sig["name"]),
                    description=sig["doc"] or _first_doc(path), path=path,
                    entry=sig["name"], module=modul,
                    signature="(%s)" % ", ".join(sig["args"]),
                    source=os.path.dirname(path)))
        elif os.path.isdir(path):
            init = os.path.join(path, "__init__.py")
            pkg = os.path.basename(path)
            if os.path.isfile(init):
                names = []
                try:
                    with open(init, encoding="utf-8", errors="replace") as fh:
                        tree = ast.parse(fh.read())
                    for node in tree.body:
                        if isinstance(node, ast.Assign):
                            for t in node.targets:
                                if getattr(t, "id", "") == "__all__":
                                    names = [el.value for el in node.value.elts
                                             if isinstance(el, ast.Constant)]
                except (OSError, SyntaxError, AttributeError):
                    names = []
                sigs = {g["name"]: g for g in module_signatures(init)}
                names = names or list(sigs)
                for fn in names:
                    if fn[:1].isupper():       # classes: not callable as tools
                        continue
                    sig = sigs.get(fn) or {}
                    out.append(ExternalTool(
                        kind="python", name="%s.%s" % (pkg, fn),
                        description=sig.get("doc") or _first_doc(init),
                        path=path, entry=fn, module=pkg,
                        signature=("(%s)" % ", ".join(sig["args"]))
                                  if sig.get("args") is not None else "",
                        source=os.path.dirname(path)))
            else:
                for entry in sorted(os.listdir(path)):
                    if entry.endswith(".py") and not entry.startswith("_"):
                        out.extend(discover_python_tools(
                            [os.path.join(path, entry)]))
    return out


def import_from_path(module: str, folder: str):
    """Import ``module`` with ``folder`` on sys.path, without polluting it."""
    folder = os.path.abspath(os.path.expanduser(folder))
    added = folder not in sys.path
    if added:
        sys.path.insert(0, folder)
    try:
        if module in sys.modules:
            return importlib.reload(sys.modules[module])
        return importlib.import_module(module)
    finally:
        if added and sys.path and sys.path[0] == folder:
            sys.path.pop(0)


def call_python_tool(tool: "ExternalTool", **kwargs):
    """Import the module and call the entry function."""
    if tool.kind != "python" or not tool.entry:
        raise ToolError("Kein aufrufbares Python-Werkzeug: %s" % tool.name)
    folder = tool.source or os.path.dirname(tool.path)
    mod = import_from_path(tool.module, folder)
    fn = getattr(mod, tool.entry, None)
    if not callable(fn):
        raise ToolError("%s hat keine Funktion %r" % (tool.module, tool.entry))
    return fn(**kwargs)


def describe_tools(tools: list, limit: int = 40) -> str:
    """A compact list for the prompt."""
    if not tools:
        return "Keine externen Werkzeuge gefunden."
    lines = []
    for t in tools[:limit]:
        lines.append("- " + t.as_line())
    if len(tools) > limit:
        lines.append("… und %d weitere" % (len(tools) - limit))
    return "\n".join(lines)


def find_tool(tools: list, name: str) -> "ExternalTool | None":
    """Match by exact name, then case-insensitively, then by suffix."""
    if not name:
        return None
    for t in tools:
        if t.name == name:
            return t
    low = name.lower()
    for t in tools:
        if t.name.lower() == low:
            return t
    for t in tools:
        if t.name.lower().endswith("." + low) or t.command.lower() == low:
            return t
    return None


__all__ = [
    "ExternalTool", "ToolError", "discover_macros", "discover_addons",
    "discover_python_tools", "addon_commands", "module_functions",
    "import_from_path", "call_python_tool", "describe_tools", "find_tool",
    "MACRO_DIRS",
]
