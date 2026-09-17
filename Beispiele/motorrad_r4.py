# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Ein Motorrad-Vierzylinder mit parallel liegendem Sechsganggetriebe.

    FreeCADCmd Beispiele/motorrad_r4.py
    T2G_MOTOR_AUS=<Ordner> FreeCADCmd Beispiele/motorrad_r4.py

Der Unterschied zum Automotor liegt nicht im Motor, sondern darin, **wo das
Getriebe steht**. Längs eingebaut sitzt es hinter dem Motor auf derselben
Achse; quer im Motorradrahmen ginge das nicht, denn die Kurbelwellenachse
ist dort die *Breite* des Fahrzeugs, und was axial hinausragt, ragt seitlich
heraus. Das Getriebe liegt deshalb **parallel daneben**, hinter und unter
der Kurbelwelle, und muss vollständig im Schatten des Motors bleiben.

Daraus folgt die ganze Antriebskette:

    Kurbelwelle ─(Primärritzel/Primärrad = Vorgelege)─► Eingangswelle
    Eingangswelle ─(ein Radpaar je Gang)─► Abtriebswelle ─► Kettenrad

Das Primärradpaar ist zugleich die Vorgelegestufe — ein Zweiwellengetriebe
genügt, eine eigene Antriebskonstante wie beim Vorgelegegetriebe des
Längsmotors braucht es nicht. Die Gesamtübersetzung ist
``i = i_primär · (z_Losrad / z_Festrad)``.

Ausgabe ist ``R4_Motorrad_600_6gang.FCStd``; die Datei ist gitignoriert und
wird neu gebaut, nicht eingecheckt.
"""

import os
import sys
import time
import traceback

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
for _p in (os.path.join(WURZEL, "Skills", "Verbrennungsmotor"),
           os.path.join(WURZEL, "Tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FreeCAD                                             # noqa: E402

AUS = os.environ.get("T2G_MOTOR_AUS") or os.path.join(HIER, "Motoren")
# FreeCADCmd schluckt stdout — der Bericht geht in eine Datei daneben.
BERICHT = os.path.join(AUS, "motorrad_r4.txt")

_zeilen = []


def sag(text=""):
    _zeilen.append(str(text))
    try:
        with open(BERICHT, "w", encoding="utf-8") as f:
            f.write("\n".join(_zeilen) + "\n")
    except OSError:
        pass


def baue():
    import kt_motor

    t0 = time.time()
    doc = FreeCAD.newDocument("MotorradR4")
    teile, kenn, proben = kt_motor.baue(
        bauform="R4", bohrung=67.0, hub=42.5, ventile_je_zylinder=4,
        mit_getriebe=True, getriebe_lage="parallel", getriebe_gaenge=6,
        doc=doc)
    g = kenn["getriebe"]

    sag("Motorrad-R4: %d Koerper in %.1f s" % (len(teile), time.time() - t0))
    sag("  Hubraum %.0f cm^3, Bohrung x Hub %.0f x %.1f"
        % (kenn["hubraum_cm3"], kenn["bohrung"], kenn["hub"]))
    sag()
    sag("--- Antrieb ---")
    sag("  Primaertrieb   z %d/%d, i = %.3f, Modul %.2f, Achsabstand %.1f mm"
        % (g["primaer"]["zaehne"][0], g["primaer"]["zaehne"][1],
           g["primaer"]["i"], g["primaer"]["modul"],
           g["primaer"]["achsabstand"]))
    sag("                 mindestens %.1f mm, weil die Kurbelwange %.1f misst"
        % (g["primaer"]["mindestabstand"], g["primaer"]["wangenradius"]))
    sag("  Lage           %.0f Grad von +Z nach +Y (hinten/unten)"
        % g["primaer"]["winkel"])
    sag("  Getriebe       %d Gaenge, Welle %.1f, Modul %.2f, Achsabstand %.1f"
        % (g["gaenge"], g["welle_d"], g["modul"], g["achsabstand"]))
    sag("  Uebersetzungen %s"
        % ", ".join("%.2f" % i for i in g["uebersetzungen"]))
    sag("  Kettenrad      z=%d, Teilung %.3f, Teilkreis %.1f mm"
        % (g["kettenrad"]["zaehne"], g["kettenrad"]["teilung"],
           g["kettenrad"]["teilkreis"]))

    motor = [s for n, s in teile
             if not n.startswith(("Getriebe", "Primaertrieb", "Abtrieb"))]
    antrieb = [s for n, s in teile
               if n.startswith(("Getriebe", "Primaertrieb", "Abtrieb"))]
    bm = motor[0].BoundBox
    for s in motor[1:]:
        bm.add(s.BoundBox)
    bg = antrieb[0].BoundBox
    for s in antrieb[1:]:
        bg.add(s.BoundBox)
    sag()
    sag("  Motor     x %7.1f…%7.1f   y %7.1f…%7.1f   z %7.1f…%7.1f"
        % (bm.XMin, bm.XMax, bm.YMin, bm.YMax, bm.ZMin, bm.ZMax))
    sag("  Getriebe  x %7.1f…%7.1f   y %7.1f…%7.1f   z %7.1f…%7.1f"
        % (bg.XMin, bg.XMax, bg.YMin, bg.YMax, bg.ZMin, bg.ZMax))
    sag()

    offen = 0
    for ok, text in kt_motor.pruefe(teile, proben, kenn):
        sag("  %s %s" % ("ok  " if ok else "FEHL", text))
        offen += 0 if ok else 1
    sag("ALLE ZUSAGEN" if not offen else "%d BEFUNDE" % offen)

    for label, shape in teile:
        o = doc.addObject("Part::Feature", "T2G")
        o.Shape = shape
        o.Label = label
    doc.recompute()
    if not os.path.isdir(AUS):
        os.makedirs(AUS)
    pfad = os.path.join(AUS, "R4_Motorrad_600_6gang.FCStd")
    doc.saveAs(pfad)
    sag("Abgelegt: %s (%.1f MB)"
        % (os.path.basename(pfad), os.path.getsize(pfad) / 1048576.0))
    return offen


# Kein __main__-Schutz: FreeCADCmd garantiert den Namen nicht.
try:
    if not os.path.isdir(AUS):
        os.makedirs(AUS)
    _offen = baue()
except Exception:
    sag(traceback.format_exc())
    raise
if _offen:
    sys.exit(1)
