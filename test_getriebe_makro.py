# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Die Getriebe-Makros: Maske, Lager nach DIN 625, Gehäuse, FCGear.

Braucht das ECHTE Part-Modul und das Add-on freecad.gears, läuft daher nur
unter FreeCADCmd:

    FreeCADCmd test_getriebe_makro.py

Fehlt FCGear, werden nur die Teile geprüft, die ohne es auskommen — dann sagt
der Lauf das und endet trotzdem grün, statt eine fremde Installation zu
beschuldigen.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Vorn einfuegen: der installierte Mod-Ordner steht auch auf sys.path und
# enthaelt eine Kopie dieser Datei; sonst laeuft der Test gegen den zuletzt
# synchronisierten Stand statt gegen die Quelle.
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "Tools"))

import FreeCAD
import FreeCADGui
import Part

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *a, **k: None
if not hasattr(FreeCADGui, "SendMsgToActiveView"):
    FreeCADGui.SendMsgToActiveView = lambda *a, **k: None

import gehaeuse_kontur as GK
import lager_din625 as LG
import t2g_maske as M
import werkstoff as W

OUT = os.environ.get("T2G_TEST_OUT", "")
ZEILEN, FEHLER = [], []


def log(m):
    ZEILEN.append(str(m))
    print(m)
    if OUT:
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(ZEILEN) + "\n")


def pruefe(bedingung, text):
    log("%s %s" % ("ok  " if bedingung else "FEHL", text))
    if not bedingung:
        FEHLER.append(text)


def koerper(doc):
    return [o for o in doc.Objects
            if getattr(o, "Shape", None) is not None
            and not o.Shape.isNull() and o.Shape.Solids]


# --- 1: Maske ------------------------------------------------------------
log("\n--- Eingabemaske ---")
log("     " + M.selbsttest())
felder = [M.Feld("a", "A", "mm", 1.5), M.Feld("b", "B", "Stk", 3),
          M.Feld("c", "C", "", "x", auswahl=["x", "y"])]
pruefe([f.art for f in felder] == ["float", "int", "auswahl"],
       "Feldarten aus dem Vorgabewert erkannt")
pruefe(M.vorgaben(felder) == {"a": 1.5, "b": 3, "c": "x"},
       "Vorgaben ohne GUI")
# Gemerkte Werte ueberleben den naechsten Aufruf.
M.merke(felder, {"a": 2.5, "b": 7, "c": "y"}, "t2g_selbsttest")
zurueck = M.gemerkt(felder, "t2g_selbsttest")
pruefe(zurueck["a"] == 2.5 and zurueck["b"] == 7 and zurueck["c"] == "y",
       "Eingaben werden gemerkt und wieder vorgelegt")

# --- 2: Lager nach DIN 625 ----------------------------------------------
log("\n--- Rillenkugellager DIN 625-1 ---")
log("     " + LG.selbsttest())
for name, d, D, B in (("6204", 20.0, 47.0, 14.0), ("6304", 20.0, 52.0, 15.0),
                      ("6000", 10.0, 26.0, 8.0), ("6210", 50.0, 90.0, 20.0)):
    m = LG.masse(name)
    pruefe(m["d"] == d and m["D"] == D and m["B"] == B,
           "%s: d %.0f / D %.0f / B %.0f" % (name, m["d"], m["D"], m["B"]))
pruefe(LG.waehle(20.0, "62") == "6204" and LG.waehle(20.0, "63") == "6304",
       "Auswahl nach Wellendurchmesser und Reihe")
pruefe(LG.waehle(19.0, "62") == "6204",
       "eine 19-mm-Welle bekommt das naechstgroessere Lager")

# --- 3: Werkstoff --------------------------------------------------------
log("\n--- Werkstoff ---")
log("     " + W.selbsttest())
doc = FreeCAD.newDocument("WerkstoffDauer")
objekte, meldung = LG.baue_mit_werkstoff(doc=doc, bezeichnung="6204")
pruefe("von %d" % len(objekte) in meldung,
       "Werkstoff an alle Lagerteile: %s" % meldung)
pfad = os.path.join(os.environ.get("T2G_TEST_TMP", "/tmp"),
                    "t2g_werkstoff_probe.FCStd")
doc.saveAs(pfad)
name = doc.Name
FreeCAD.closeDocument(name)
wieder = FreeCAD.openDocument(pfad)
erste = koerper(wieder)[0]
# Der eigentliche Fallstrick: PropertyMaterial speichert nur die UUID.
pruefe(getattr(erste.ShapeMaterial, "Name", "") not in ("", "None", None),
       "Werkstoff ueberlebt Speichern und Oeffnen (%s)"
       % getattr(erste.ShapeMaterial, "Name", "-"))
FreeCAD.closeDocument(wieder.Name)

# --- 4: Konturgehaeuse ---------------------------------------------------
log("\n--- Geteiltes Konturgehaeuse ---")
log("     " + GK.selbsttest())
# Gestuft: Lagersitz, drei ungleiche Radpaare, Lagersitz.
sitz_r = 23.5
abschnitte = [(14.0, [sitz_r, sitz_r]),
              (18.0, [17.0, 41.0]),
              (18.0, [21.0, 37.0]),
              (18.0, [25.0, 33.0]),
              (14.0, [sitz_r, sitz_r])]
teile = GK.baue([(0.0, 0.0), (0.0, 48.0)], abschnitte=abschnitte, wand=4.0,
                welle_d=20.4, achse="z")
pruefe(len(teile) == 2, "Ober- und Unterteil (%d)" % len(teile))
oben, unten = teile[0][1], teile[1][1]
pruefe(abs(oben.Volume - unten.Volume) < 0.02 * (oben.Volume + unten.Volume),
       "haelftig geteilt (%.0f gegen %.0f mm^3)" % (oben.Volume, unten.Volume))
pruefe(oben.common(unten).Volume < 1.0, "die Haelften ueberlappen nicht")
ganz = oben.fuse(unten)
bo, bu = oben.BoundBox, unten.BoundBox
pruefe((bo.XMax <= 0.01 and bu.XMin >= -0.01)
       or (bu.XMax <= 0.01 and bo.XMin >= -0.01),
       "die Haelften liegen auf verschiedenen Seiten der Trennebene")


def quer_bei(z):
    """Quer zur Achsverbindung — längs davon liegt der Flansch."""
    ebene = Part.makeBox(600.0, 600.0, 0.5,
                         FreeCAD.Vector(-300.0, -300.0, z))
    t = ganz.common(ebene)
    return t.BoundBox.XLength if t.Solids else 0.0


eng, weit = quer_bei(5.0), quer_bei(25.0)
pruefe(weit - eng > 2.0,
       "die Wand folgt den Raedern (%.0f mm am Lager, %.0f mm am Rad)"
       % (eng, weit))
# Um den Lagersitz muss Material stehen, im Sitz selbst keines.
lager = Part.makeCylinder(sitz_r, 14.0, FreeCAD.Vector(0, 48.0, 0.0))
pruefe(ganz.common(lager).Volume < 1.0, "der Lagersitz ist frei fuer das Lager")
huelle = Part.makeCylinder(sitz_r + 3.5, 12.0, FreeCAD.Vector(0, 48.0, 1.0))
pruefe(ganz.common(huelle).Volume > 100.0,
       "um den Lagersitz steht Material (%.0f mm^3)"
       % ganz.common(huelle).Volume)
# Der Durchbruch muss die Welle durchlassen.
welle = Part.makeCylinder(10.0, 300.0, FreeCAD.Vector(0, 48.0, -100.0))
pruefe(ganz.common(welle).Volume < 1.0,
       "der Wellendurchbruch laesst die Welle durch")

# --- 5: Getriebe mit FCGear ---------------------------------------------
log("\n--- Schaltgetriebe mit FCGear ---")
try:
    import getriebe_fcgear as GF
    hat_fcgear = True
except Exception as e:  # noqa: BLE001
    log("     FCGear nicht verfuegbar (%s) -- Abschnitt uebersprungen." % e)
    hat_fcgear = False

if hat_fcgear:
    doc = FreeCAD.newDocument("GetriebeDauer")
    k = GF.kennwerte(gaenge=5, zaehne_summe=48, modul=2.0)
    pruefe(abs(k["achsabstand"] - 48.0) < 1e-6,
           "Achsabstand %.1f mm aus m*(z1+z2)/2" % k["achsabstand"])
    pruefe(len({z1 + z2 for z1, z2, _i in k["gangpaare"]}) == 1,
           "alle Gaenge auf einer Zaehnesumme")
    pruefe(k["lager"] == "6204", "Lager aus der Welle gewaehlt: %s" % k["lager"])

    # FCGear liefert echte Evolvente: d = m*z und d_a = m*(z+2).
    shp, d_w, d_a = GF.zahnrad(doc, 20, 2.0, 10.0, 0.0)
    pruefe(abs(d_w - 40.0) < 1e-6 and abs(d_a - 44.0) < 1e-6,
           "Teilkreis %.2f und Kopfkreis %.2f wie gerechnet" % (d_w, d_a))
    pruefe(len(shp.Solids) == 1, "ein Solid je Rad")

    for art in ("gerade", "schraeg", "pfeil"):
        teile = GF.baue(doc=doc, gaenge=3, verzahnung=art, schraegwinkel=15.0)
        schlecht = [t for ok, t in GF.pruefe(teile) if not ok]
        pruefe(not schlecht, "%s: %s"
               % (art, "alle Zusagen" if not schlecht else "; ".join(schlecht)))

    teile = GF.baue(doc=doc, gaenge=5)
    namen = [n for n, _s in teile]
    pruefe(sum(1 for n in namen if "Festrad" in n) == 5
           and sum(1 for n in namen if "Losrad" in n) == 5,
           "fuenf Festraeder und fuenf Losraeder")
    pruefe(sum(1 for n in namen if n.startswith("Schaltmuffe")) == 4,
           "vier Schaltmuffen zwischen den Losraedern")
    pruefe(sum(1 for n in namen if n.startswith("Gehaeuse")) == 2,
           "Gehaeuse ist geteilt")
    # Die Lager muessen IM Gehaeuse sitzen, nicht davor in der Luft: im
    # ersten Wurf lagen sie bei x -23..-9, das Gehaeuse bei -7..103.
    gh = [s for n, s in teile if n.startswith("Gehaeuse")]
    huelle = gh[0].fuse(gh[1]).BoundBox
    lagerteile = [s for n, s in teile if n[:1].isdigit()]
    pruefe(all(huelle.XMin <= s.BoundBox.XMin and huelle.XMax >= s.BoundBox.XMax
               for s in lagerteile),
           "alle %d Lagerteile liegen im Gehaeuse" % len(lagerteile))
    FreeCAD.closeDocument(doc.Name)

log("\nFEHLER: %d" % len(FEHLER))
log("ALLE GRUEN" if not FEHLER else "FEHLGESCHLAGEN")
if FEHLER:
    raise SystemExit(1)
