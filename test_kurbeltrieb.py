# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Der Kurbeltriebsgenerator: Bauteile, Andockpunkte, Zusammenbau.

Braucht das ECHTE Part-Modul, läuft daher nur unter FreeCADCmd:

    FreeCADCmd test_kurbeltrieb.py

Der lange Teil — alle zehn Bauformen zusammenbauen — läuft nur mit
``T2G_TEST_LANG=1``; ohne das werden zwei Bauformen geprüft, damit der
normale Testlauf nicht siebzig Sekunden braucht.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Vorn einfuegen: der installierte Mod-Ordner steht auch auf sys.path und
# enthaelt eine Kopie dieser Datei.
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "Tools"))

import FreeCAD
import FreeCADGui

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *a, **k: None
if not hasattr(FreeCADGui, "SendMsgToActiveView"):
    FreeCADGui.SendMsgToActiveView = lambda *a, **k: None

import kt_bauformen as KB
import kt_kolben
import kt_kurbelwelle
import kt_motor
import kt_nockenwelle
import kt_pleuel
import kt_schnittstelle as KS
import kt_steuertrieb
import kt_stoessel
import kt_ventil
import kt_ventilfeder

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


# --- 1: Selbsttests der Bauteile -----------------------------------------
log("\n--- Die Bauteile einzeln ---")
FreeCAD.newDocument("KurbeltriebTest")
for modul in (KS, KB, kt_kolben, kt_pleuel, kt_kurbelwelle, kt_ventil,
              kt_ventilfeder, kt_stoessel, kt_nockenwelle, kt_steuertrieb):
    name = modul.__name__
    try:
        log("     " + modul.selbsttest())
        pruefe(True, "%s: Selbsttest" % name)
    except Exception as e:  # noqa: BLE001
        pruefe(False, "%s: %s" % (name, e))

# --- 2: Andocken ----------------------------------------------------------
log("\n--- Andocken ---")
kolben = kt_kolben.baue()
pleuel = kt_pleuel.baue()
gesetzt = KS.andocke(pleuel, "kolbenbolzen", kolben.punkt("bolzen"))
ok, text = KS.pruefe_paarung(gesetzt.punkt("kolbenbolzen"),
                             kolben.punkt("bolzen"))
pruefe(ok, "Pleuel an den Kolbenbolzen: " + text)
pruefe(kolben.koerper[0][1].common(gesetzt.koerper[0][1]).Volume < 50.0,
       "das kleine Pleuelauge steckt nicht im Kolben")

# Die Hubzapfenachse ist die Wellenachse — nicht die Augenachse des Pleuels.
kw = kt_kurbelwelle.baue(bauform="R4")
pruefe(abs(kw.punkt("hubzapfen_1").achse.x - 1.0) < 1e-9,
       "die Hubzapfenachse zeigt entlang der Kurbelwelle")

# --- 3: Bauformen ---------------------------------------------------------
log("\n--- Bauformen ---")
pruefe(KB.zapfenzahl("V12") == 6 and KB.zapfenzahl("R6") == 6,
       "V-Motoren teilen sich Hubzapfen")
pruefe(sorted(KB.zapfenwinkel("V8")) == [0.0, 90.0, 180.0, 270.0],
       "kreuzebeniger V8: Zapfen ueber zwei Ebenen")
pruefe(KB.zuendfolge("R6") == [1, 5, 3, 6, 2, 4],
       "R6 zuendet 1-5-3-6-2-4")

# --- 4: Zusammenbau -------------------------------------------------------
log("\n--- Zusammenbau ---")
lang = os.environ.get("T2G_TEST_LANG") == "1"
bauformen = KB.namen() if lang else ("R4", "V8")
if not lang:
    log("     (nur %s; alle zehn mit T2G_TEST_LANG=1)"
        % ", ".join(bauformen))
for bauform in bauformen:
    doc = FreeCAD.newDocument("KT_" + bauform)
    try:
        teile, kenn, proben = kt_motor.baue(bauform=bauform, doc=doc)
        schlecht = [t for ok, t in kt_motor.pruefe(teile, proben, kenn)
                    if not ok]
        pruefe(not schlecht, "%s: %d Koerper, %.0f cm^3%s"
               % (bauform, len(teile), kenn["hubraum_cm3"],
                  "" if not schlecht else " — " + "; ".join(schlecht)[:80]))
    except Exception as e:  # noqa: BLE001
        pruefe(False, "%s: %s" % (bauform, e))
    finally:
        FreeCAD.closeDocument(doc.Name)

# --- 5: Getriebe anflanschen ---------------------------------------------
log("\n--- Getriebe anflanschen ---")
doc = FreeCAD.newDocument("KT_Getriebe")
teile, kenn, _p = kt_motor.baue(bauform="R4", mit_getriebe=True, doc=doc)
motor = [(n, s) for n, s in teile if not n.startswith("Getriebe:")]
getriebe = [(n, s) for n, s in teile if n.startswith("Getriebe:")]
pruefe(len(getriebe) > 20, "das Getriebe ist dabei (%d Koerper)"
       % len(getriebe))
motor_x = max(s.BoundBox.XMax for _n, s in motor)
getriebe_x = min(s.BoundBox.XMin for _n, s in getriebe)
pruefe(abs(getriebe_x - motor_x) < 1.0,
       "das Getriebe schliesst am Flansch an (Motor bis %.1f, Getriebe ab "
       "%.1f)" % (motor_x, getriebe_x))
# Beide auf derselben Achse — das ist die Normallage.
wellen = [s for n, s in getriebe if "welle" in n.lower()]
if wellen:
    b = wellen[0].BoundBox
    pruefe(abs((b.YMin + b.YMax) / 2.0) < 1.0
           and abs((b.ZMin + b.ZMax) / 2.0) < 1.0,
           "die Getriebeeingangswelle liegt auf der Kurbelwellenachse")
FreeCAD.closeDocument(doc.Name)

# --- 6: In der Workbench --------------------------------------------------
log("\n--- Befehl der Workbench ---")
import T2GCommand
befehl = T2GCommand.T2GKurbeltriebCommand()
r = befehl.GetResources()
pruefe(bool(r.get("MenuText")) and os.path.isfile(r.get("Pixmap", "")),
       "T2G_Kurbeltrieb: Menuetext und Symbol")
befehl._tools()
import t2g_maske as TM
felder = befehl.felder(TM)
pruefe(len(felder) >= 12, "Maske mit %d Feldern" % len(felder))
gruppen = {f.gruppe for f in felder}
pruefe(len(gruppen) >= 3, "Felder in %d Gruppen: %s"
       % (len(gruppen), ", ".join(sorted(gruppen))))
namen = {f.name for f in felder}
pruefe({"bauform", "bohrung", "hub", "mit_getriebe"} <= namen,
       "die wichtigen Felder sind da")

log("\nFEHLER: %d" % len(FEHLER))
log("ALLE GRUEN" if not FEHLER else "FEHLGESCHLAGEN")
if FEHLER:
    raise SystemExit(1)
