# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Baut das Fünfgang-Getriebe mit ``Tools/getriebe.py`` und prüft es nach.

Referenzmodell und Regressionstest zugleich. Die Geometrie steckt im
Werkzeug, nicht hier — dasselbe Werkzeug, das der Agent bedient:

    werkzeug_aufrufen: getriebe.baue;gaenge=5;abstand=3;wand=4

Dieses Skript ist nur die Fassung für die Kommandozeile:

    FreeCADCmd Beispiele/getriebe_5gang.py

Schreibt den Bericht nach ``$T2G_OUT`` (Vorgabe: ``getriebe_bau.txt``), das
Dokument nach ``$T2G_GETRIEBE_FCSTD`` (Vorgabe:
``~/T2G-Projekte/Getriebe_5Gang.FCStd``). Bricht eine Zusage, endet es mit
Exit-Code 1.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "Tools"))

import FreeCAD
import getriebe

#: Geforderte Maße aus der Aufgabenstellung.
GAENGE, ABSTAND, WAND = 5, 3.0, 4.0

OUT = os.environ.get("T2G_OUT", "getriebe_bau.txt")
FCSTD = os.environ.get(
    "T2G_GETRIEBE_FCSTD",
    os.path.expanduser("~/T2G-Projekte/Getriebe_5Gang.FCStd"))

ZEILEN = []


def log(m):
    ZEILEN.append(str(m))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(ZEILEN) + "\n")


log("=== Auslegung ===")
werte = getriebe.kennwerte(gaenge=GAENGE, abstand=ABSTAND, wand=WAND)
log("Achsabstand %.0f mm · Gehaeuse innen %s · aussen %s"
    % (werte["achsabstand"], werte["gehaeuse_innen"], werte["gehaeuse_aussen"]))
for k, (z1, z2, i) in enumerate(werte["gangpaare"], 1):
    log("  Gang %d: %2d/%2d Zaehne · i = %.3f" % (k, z1, z2, i))

teile = getriebe.baue(gaenge=GAENGE, abstand=ABSTAND, wand=WAND)

doc = FreeCAD.newDocument("Getriebe_5Gang")
try:
    asm = doc.addObject("Assembly::AssemblyObject", "Getriebe")
except Exception:  # noqa: BLE001 - ohne Assembly-Workbench reicht App::Part
    asm = doc.addObject("App::Part", "Getriebe")
asm.Label = "Getriebe %d Gang" % GAENGE
for i, (label, shape) in enumerate(teile):
    o = doc.addObject("Part::Feature", "Teil%03d" % i)
    o.Shape = shape
    o.Label = label
    asm.addObject(o)
doc.recompute()

log("\n=== Pruefung ===")
befunde = getriebe.pruefe(teile, abstand=ABSTAND, wand=WAND)
for ok, text in befunde:
    log("%s %s" % ("ok  " if ok else "FEHL", text))
gesamt = sum(s.Volume for _n, s in teile)
log("     Gesamtvolumen %.0f mm^3 (%.2f kg bei 7.85 g/cm^3)"
    % (gesamt, gesamt * 7.85e-6))

os.makedirs(os.path.dirname(FCSTD), exist_ok=True)
doc.saveAs(FCSTD)
log("\ngespeichert: %s (%.0f kB)" % (FCSTD, os.path.getsize(FCSTD) / 1024.0))

schlecht = [t for ok, t in befunde if not ok]
if schlecht:
    log("\nPRUEFUNG FEHLGESCHLAGEN: %d" % len(schlecht))
    raise SystemExit(1)
log("\nALLE ZUSAGEN EINGEHALTEN")
