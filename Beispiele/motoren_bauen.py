# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Baut alle Motorvarianten und speichert jede als eigene FCStd-Datei.

    FreeCADCmd Beispiele/motoren_bauen.py
    T2G_MOTOR_AUS=<Ordner> FreeCADCmd Beispiele/motoren_bauen.py
    T2G_MOTOR_NUR=V8       FreeCADCmd Beispiele/motoren_bauen.py

Jede Variante bekommt einen sprechenden Dateinamen, aus dem die Auslegung
abzulesen ist:

    V8_86x86_4V_kette_bank90_ventil12.FCStd

Die Dateien sind **Ausgabe** und gitignoriert (`*.FCStd`) — sie werden neu
gebaut, nicht eingecheckt. Der Ordner ist ``Beispiele/Motoren`` oder was in
``T2G_MOTOR_AUS`` steht.

Geprüft wird jede Variante mit ``kt_motor.pruefe()``, bevor sie gespeichert
wird; eine Variante mit Befund wird trotzdem gespeichert, aber im Bericht
gekennzeichnet — man will sie ja gerade ansehen können.

Eine Auslegung, die sich begründet **nicht** bauen lässt (etwa ein DOHC-Kopf
mit parallelen Ventilen, dessen Kettenräder nicht zwischen die Nockenwellen
passen), wird als solche gemeldet und erzeugt keine Datei.
"""

import os
import sys
import time
import traceback

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(WURZEL, "Skills", "Verbrennungsmotor"))
sys.path.insert(0, os.path.join(WURZEL, "Tools"))

import FreeCAD  # noqa: E402
import Part     # noqa: E402

import kt_motor  # noqa: E402

AUS = os.environ.get("T2G_MOTOR_AUS") or os.path.join(HIER, "Motoren")
BERICHT = os.path.join(AUS, "bericht.txt")

#: Alle Varianten: (Dateiname ohne Endung, Argumente für kt_motor.baue).
#: Der Name trägt die Auslegung, damit eine Datei für sich sprechend ist.
def varianten():
    alle = ("R2", "R3", "R4", "R5", "R6", "V4", "V6", "V8", "V10", "V12")
    v = []
    for bf in alle:
        v.append(("%s_86x86_4V_kette" % bf, dict(bauform=bf)))
    for bf in alle:
        v.append(("%s_86x86_2V_kette" % bf,
                  dict(bauform=bf, ventile_je_zylinder=2)))
    for bf in ("R4", "R6", "V6", "V8"):
        v.append(("%s_86x86_4V_zahnrad" % bf,
                  dict(bauform=bf, steuertrieb="zahnrad")))
    for bf, winkel in (("V4", (60.0, 90.0, 120.0)),
                       ("V6", (60.0, 75.0, 90.0, 120.0)),
                       ("V8", (60.0, 90.0, 120.0)),
                       ("V10", (72.0, 90.0)),
                       ("V12", (60.0, 65.0, 90.0))):
        for w in winkel:
            v.append(("%s_86x86_4V_kette_bank%.0f" % (bf, w),
                      dict(bauform=bf, bankwinkel=w)))
    for bf in ("R4", "V8"):
        for w in (8.0, 10.0, 12.0, 20.0, 28.0):
            v.append(("%s_86x86_4V_kette_ventil%.0f" % (bf, w),
                      dict(bauform=bf, ventilwinkel=w)))
    for bf in ("R4", "V8"):
        for d, h in ((70.0, 66.0), (100.0, 92.0), (120.0, 110.0)):
            v.append(("%s_%.0fx%.0f_4V_kette" % (bf, d, h),
                      dict(bauform=bf, bohrung=d, hub=h)))
    v.append(("R4_86x86_4V_kette_mit_getriebe",
              dict(bauform="R4", mit_getriebe=True)))
    v.append(("V8_86x86_4V_kette_flachebenig",
              dict(bauform="V8", v8_kreuzebene=False)))
    v.append(("R4_86x86_nur_kurbeltrieb",
              dict(bauform="R4", mit_ventiltrieb=False)))
    return v


def speichern(name, teile, ordner):
    """Die Körper als benanntes Dokument ablegen und speichern."""
    doc = FreeCAD.newDocument(name)
    for label, shape in teile:
        obj = doc.addObject("Part::Feature", "T2G")
        obj.Shape = shape
        obj.Label = label
    doc.recompute()
    pfad = os.path.join(ordner, name + ".FCStd")
    doc.saveAs(pfad)
    FreeCAD.closeDocument(doc.Name)
    return pfad


def lauf(ordner=None, nur=None):
    ordner = ordner or AUS
    if not os.path.isdir(ordner):
        os.makedirs(ordner)
    zeilen = []

    def sag(text):
        zeilen.append(text)
        print(text)
        with open(BERICHT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(zeilen) + "\n")

    gut = schlecht = abgelehnt = 0
    sag("Motorvarianten — gebaut, geprueft und gespeichert")
    sag("Ordner: %s\n" % ordner)
    for name, kw in varianten():
        if nur and nur not in name:
            continue
        t0 = time.time()
        bau = FreeCAD.newDocument("Bau")
        try:
            teile, kenn, proben = kt_motor.baue(doc=bau, **kw)
            befunde = kt_motor.pruefe(teile, proben, kenn)
            offen = [t for ok, t in befunde if not ok]
            FreeCAD.closeDocument(bau.Name)
            pfad = speichern(name, teile, ordner)
            groesse = os.path.getsize(pfad) / 1024.0
            if offen:
                schlecht += 1
                sag("BEFUND %-38s %3d Koerper, %6.0f kB, %4.1fs — %s"
                    % (name, len(teile), groesse, time.time() - t0,
                       " | ".join(offen)))
            else:
                gut += 1
                sag("ok     %-38s %3d Koerper, %6.0f kB, %4.1fs"
                    % (name, len(teile), groesse, time.time() - t0))
        except Exception as e:  # noqa: BLE001
            if bau.Name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(bau.Name)
            art = type(e).__name__
            if art in ("VentiltriebFehler", "SteuertriebFehler",
                       "MotorFehler", "AuslegungFehler", "BauformFehler"):
                abgelehnt += 1
                sag("--     %-38s nicht baubar: %s" % (name, e))
            else:
                schlecht += 1
                sag("FEHLER %-38s %s: %s" % (name, art, e))
                sag("       " + traceback.format_exc().splitlines()[-3].strip())

    sag("\n%d gespeichert ohne Befund, %d mit Befund, %d begruendet abgelehnt"
        % (gut, schlecht, abgelehnt))
    sag("Bericht: %s" % BERICHT)
    return schlecht


# FreeCADCmd fuehrt dieses Skript aus, ohne dass ``__name__`` verlaesslich
# "__main__" waere und ohne dass ``sys.argv`` die eigenen Argumente traegt —
# mit einem Waechter darum herum passierte gar nichts, und weil FreeCADCmd
# stdout verschluckt, war auch nicht zu sehen, warum. Deshalb laeuft es
# beim Einlesen, und der Bericht steht in einer Datei.
_NUR = os.environ.get("T2G_MOTOR_NUR") or None
raise SystemExit(1 if lauf(nur=_NUR) else 0)
