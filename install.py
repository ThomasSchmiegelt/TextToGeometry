#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Install the TextToGeometry workbench into a FreeCAD Mod directory.

    python3 install.py            # find FreeCAD, install into every Mod dir found
    python3 install.py --list     # only show what was found
    python3 install.py --target /pfad/zu/FreeCAD/Mod
    python3 install.py --uninstall
    python3 install.py --paket    # ZIP zum Mitnehmen auf einen anderen Rechner
    python3 install.py --paket --mit-skills   # samt der hier gelernten Skills

Works on Linux, macOS and Windows, with FreeCAD 0.20 … 1.x (the versioned
``v1-1`` style directories of 1.1+ included). Needs nothing but Python.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

ADDON = "TextToGeometry"
HERE = os.path.dirname(os.path.abspath(__file__))

#: Everything the add-on needs at runtime. Keep in step with CMakeLists.txt.
FILES = [
    "__init__.py", "Init.py", "InitGui.py",
    "T2GCore.py", "T2GCommand.py", "T2GSkills.py", "T2GProject.py",
    "T2GAgent.py", "T2GTools.py",
    "package.xml", "CMakeLists.txt", "README.md", "DOKUMENTATION.md", "BEDIENUNGSANLEITUNG.md",
    "install.py", "LICENSE",
    "test_core.py", "test_ext.py", "test_skills.py", "test_chat.py",
    "test_learn.py", "test_project.py", "test_agent.py",
    "test_tools.py", "test_bauen.py", "test_getriebe_makro.py",
    "test_kurbeltrieb.py",
]
DIRS = ["Resources", "Skills", "Tools", "Macros"]

#: Directories that belong to the user, not to the add-on -- never overwritten.
KEEP_ON_UPDATE = ("Skills",)


def mod_dir_from_freecad(binary: str | None = None) -> "str | None":
    """Ask FreeCAD itself where its Mod directory is.

    The only reliable source: a portable install, a snap, an AppImage or a
    FREECAD_USER_HOME override all put it somewhere the platform conventions
    below would never guess. Works when this script runs *inside* FreeCAD's
    Python console, or when a FreeCADCmd binary can be found.
    """
    try:
        import FreeCAD  # noqa: F401  -- running inside FreeCAD
        return os.path.join(FreeCAD.getUserAppDataDir(), "Mod")
    except Exception:  # noqa: BLE001
        pass
    candidates = [binary] if binary else []
    candidates += ["FreeCADCmd", "freecadcmd", "freecad-cmd"]
    import subprocess
    import tempfile
    for exe in candidates:
        if not exe:
            continue
        found = exe if os.path.isfile(exe) else shutil.which(exe)
        if not found:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write("import FreeCAD, sys\n"
                     "sys.stderr.write('T2GMOD=' + FreeCAD.getUserAppDataDir() "
                     "+ '\\n')\n")
            script = fh.name
        try:
            proc = subprocess.run([found, script], capture_output=True,
                                  text=True, timeout=120)
            for stream in (proc.stderr or "", proc.stdout or ""):
                m = re.search(r"T2GMOD=(.+)", stream)
                if m:
                    return os.path.join(m.group(1).strip(), "Mod")
        except Exception:  # noqa: BLE001
            continue
        finally:
            try:
                os.unlink(script)
            except OSError:
                pass
    return None


def candidate_mod_dirs() -> list:
    """Every plausible FreeCAD Mod directory on this machine."""
    home = os.path.expanduser("~")
    roots = []
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        roots.append(os.path.join(appdata, "FreeCAD"))
    elif sys.platform == "darwin":
        roots += [os.path.join(home, "Library", "Preferences", "FreeCAD"),
                  os.path.join(home, "Library", "Application Support", "FreeCAD")]
    else:
        roots += [os.path.join(home, ".local", "share", "FreeCAD"),
                  os.path.join(home, ".FreeCAD"),
                  os.path.join(home, "snap", "freecad", "current", ".local",
                               "share", "FreeCAD")]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        direct = os.path.join(root, "Mod")
        if os.path.isdir(direct):
            found.append(direct)
        # FreeCAD 1.1+ keeps a versioned tree: <root>/v1-1/Mod
        for entry in sorted(os.listdir(root)):
            versioned = os.path.join(root, entry, "Mod")
            if entry.startswith("v") and os.path.isdir(versioned):
                found.append(versioned)
    asked = mod_dir_from_freecad()
    if asked:
        found.append(asked)
    # newest version last -> install everywhere, report all
    return sorted(set(found))


def install_into(mod_dir: str, quiet: bool = False) -> str:
    dest = os.path.join(mod_dir, ADDON)
    if os.path.abspath(dest) == HERE or os.path.abspath(mod_dir) == HERE:
        # installing into the source tree leaves a nested copy of everything
        raise SystemExit(
            "Ziel ist der Quellordner selbst (%s) – das würde eine "
            "verschachtelte Kopie anlegen. Bitte ein FreeCAD-Mod-Verzeichnis "
            "angeben." % dest)
    os.makedirs(dest, exist_ok=True)
    copied = 0
    for name in FILES:
        src = os.path.join(HERE, name)
        if not os.path.isfile(src):
            continue
        shutil.copy2(src, os.path.join(dest, name))
        copied += 1
    for name in DIRS:
        src = os.path.join(HERE, name)
        if not os.path.isdir(src):
            continue
        target = os.path.join(dest, name)
        if name in KEEP_ON_UPDATE and os.path.isdir(target):
            # merge: never throw away skills the user learned on this machine
            for entry in os.listdir(src):
                s_sub, t_sub = os.path.join(src, entry), os.path.join(target, entry)
                if os.path.isdir(s_sub):
                    shutil.copytree(s_sub, t_sub, dirs_exist_ok=True)
                else:
                    shutil.copy2(s_sub, t_sub)
        else:
            shutil.copytree(src, target, dirs_exist_ok=True)
        copied += 1
    for root, dirs, _files in os.walk(dest):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                dirs.remove(d)
    makros = kopiere_makros(dest, quiet=quiet)
    if not quiet:
        print("  installiert: %s (%d Einträge)" % (dest, copied))
        if makros:
            print("  Makros im Makro-Menü: %d" % makros)
    return dest


def makro_ordner(mod_dir: str) -> "str | None":
    """FreeCADs Makro-Ordner, abgeleitet aus dem Mod-Verzeichnis.

    ``<AppData>/Mod`` liegt neben ``<AppData>/Macro`` — den Ordner über
    FreeCAD selbst zu erfragen ginge nur aus FreeCAD heraus, und install.py
    läuft auch unter reinem Python.
    """
    basis = os.path.dirname(os.path.abspath(mod_dir))
    kandidat = os.path.join(basis, "Macro")
    if os.path.isdir(kandidat):
        return kandidat
    return None


def kopiere_makros(dest: str, quiet: bool = False) -> int:
    """Die .FCMacro-Dateien zusätzlich in FreeCADs Makro-Ordner legen.

    Ohne das findet sie niemand: ``T2GTools.MACRO_DIRS`` durchsucht nur
    FreeCADs eigene Makro-Ordner, nie das Add-on-Verzeichnis — und FreeCADs
    Makro-Menü erst recht nicht.
    """
    quelle = os.path.join(HERE, "Macros")
    if not os.path.isdir(quelle):
        return 0
    ziel = makro_ordner(os.path.dirname(dest))
    if ziel is None:
        return 0
    n = 0
    for name in sorted(os.listdir(quelle)):
        if not name.endswith((".FCMacro", ".fcmacro")):
            continue
        try:
            shutil.copy2(os.path.join(quelle, name), os.path.join(ziel, name))
            n += 1
        except OSError as e:
            if not quiet:
                print("  Makro %s nicht kopiert: %s" % (name, e))
    return n


def uninstall_from(mod_dir: str) -> bool:
    dest = os.path.join(mod_dir, ADDON)
    if not os.path.isdir(dest):
        return False
    shutil.rmtree(dest)
    print("  entfernt: %s" % dest)
    return True


def collect_skills(extra_from: list | None = None) -> dict:
    """Skill folders to ship: the repo's, plus what was learned on this machine.

    Learned skills live next to the *installed* add-on, not in the source tree,
    so a package built from the source tree alone would silently leave them
    behind.
    """
    out = {}
    local = os.path.join(HERE, "Skills")
    if os.path.isdir(local):
        for entry in sorted(os.listdir(local)):
            if os.path.isdir(os.path.join(local, entry)):
                out[entry] = os.path.join(local, entry)
    for mod_dir in (extra_from or []):
        skills = os.path.join(mod_dir, ADDON, "Skills")
        if not os.path.isdir(skills):
            continue
        for entry in sorted(os.listdir(skills)):
            src = os.path.join(skills, entry)
            if os.path.isdir(src) and entry not in out:
                out[entry] = src
    return out


def make_package(zip_path: str, with_skills: bool = False) -> str:
    """Write a ZIP that unpacks to a ready-to-install TextToGeometry/ folder."""
    import zipfile

    zip_path = os.path.abspath(os.path.expanduser(zip_path))
    skills = collect_skills(candidate_mod_dirs() if with_skills else None)
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in FILES:
            src = os.path.join(HERE, name)
            if os.path.isfile(src):
                zf.write(src, os.path.join(ADDON, name))
                count += 1
        for name in DIRS:
            if name == "Skills":
                continue
            src = os.path.join(HERE, name)
            if not os.path.isdir(src):
                continue
            for root, _dirs, files in os.walk(src):
                if "__pycache__" in root:
                    continue
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, HERE)
                    zf.write(full, os.path.join(ADDON, rel))
                    count += 1
        for skill_name, skill_dir in skills.items():
            for root, _dirs, files in os.walk(skill_dir):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if f.endswith(".bak"):
                        continue        # backups stay on the machine
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, skill_dir)
                    zf.write(full, os.path.join(ADDON, "Skills", skill_name, rel))
                    count += 1
    print("Paket geschrieben: %s" % zip_path)
    print("  %d Datei(en), Skills: %s" % (count, ", ".join(skills) or "keine"))
    print()
    print("Auf dem anderen Rechner:")
    print("  unzip %s -d /tmp/t2g && python3 /tmp/t2g/%s/install.py"
          % (os.path.basename(zip_path), ADDON))
    print("  (oder den entpackten Ordner %s direkt in FreeCADs Mod/ legen)" % ADDON)
    return zip_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", action="append", default=[],
                    help="Mod-Verzeichnis (mehrfach möglich)")
    ap.add_argument("--list", action="store_true", help="nur suchen und anzeigen")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--paket", nargs="?", const="TextToGeometry.zip",
                    metavar="DATEI.zip",
                    help="ZIP zum Mitnehmen erzeugen statt zu installieren")
    ap.add_argument("--mit-skills", dest="mit_skills", action="store_true",
                    help="gelernte Skills aus den Installationen mitpacken")
    ap.add_argument("--freecad", metavar="BINARY",
                    help="FreeCAD/FreeCADCmd fragen, wo sein Mod-Ordner liegt")
    args = ap.parse_args(argv)

    if args.paket:
        make_package(args.paket, with_skills=args.mit_skills)
        return 0

    targets = [os.path.abspath(os.path.expanduser(t)) for t in args.target]
    if not targets and args.freecad:
        asked = mod_dir_from_freecad(args.freecad)
        if asked:
            targets = [asked]
        else:
            print("FreeCAD (%s) konnte nicht befragt werden." % args.freecad)
    if not targets:
        targets = candidate_mod_dirs()

    if not targets:
        print("Kein FreeCAD-Mod-Verzeichnis gefunden.")
        print("Drei Wege:")
        print("  python3 install.py --freecad /pfad/zu/FreeCADCmd")
        print("  python3 install.py --target /pfad/zu/FreeCAD/Mod")
        print("  oder in FreeCADs Python-Konsole:")
        print("     exec(open('%s/install.py').read())" % HERE)
        print("     main([])")
        return 1

    print("Gefundene Mod-Verzeichnisse:")
    for t in targets:
        print("  " + t)
    if args.list:
        return 0

    print()
    if args.uninstall:
        done = sum(1 for t in targets if uninstall_from(t))
        print("%d Installation(en) entfernt." % done)
        return 0

    for t in targets:
        os.makedirs(t, exist_ok=True)
        install_into(t, quiet=args.quiet)
    print()
    print("Fertig. FreeCAD neu starten; die Workbench heißt „TextToGeometry“.")
    print("Ohne lokales Ollama: Tab „Backend“ → API-Adresse und Schlüssel "
          "eintragen, „Modelle laden“, „Verbindung testen“.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
