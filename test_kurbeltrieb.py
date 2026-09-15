# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Der Kurbeltriebsgenerator: Bauteile, Andockpunkte, Zusammenbau.

Braucht das ECHTE Part-Modul, läuft daher nur unter FreeCADCmd:

    FreeCADCmd test_kurbeltrieb.py

Der lange Teil — alle zehn Bauformen zusammenbauen — läuft nur mit
``T2G_TEST_LANG=1``; ohne das werden zwei Bauformen geprüft, damit der
normale Testlauf nicht siebzig Sekunden braucht.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Vorn einfuegen: der installierte Mod-Ordner steht auch auf sys.path und
# enthaelt eine Kopie dieser Datei.
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "Tools"))

import Part
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
pruefe({"bauform", "bohrung", "hub", "mit_getriebe", "ventilwinkel",
        "pleuel_breite"} <= namen, "die wichtigen Felder sind da")

# --- 7: Was der Benutzer gemeldet hat ------------------------------------
log("\n--- Die gemeldeten Punkte ---")
doc = FreeCAD.newDocument("KT_Befunde")
teile, kenn, _p = kt_motor.baue(bauform="V8", doc=doc)


def mitte(shape, achse):
    b = shape.BoundBox
    return (getattr(b, achse + "Min") + getattr(b, achse + "Max")) / 2.0


# Zylinder je Bank in einer Reihe: alle Kolben einer Bank auf der Bankachse.
for bank, rest in ((0, 1), (1, 0)):
    kolben = [s for n, s in teile if n.startswith("Kolben ")
              and int(n.split()[1]) % 2 == rest]
    achsen = [(abs(mitte(s, "Y")) - abs(mitte(s, "Z"))) for s in kolben]
    pruefe(max(abs(a) for a in achsen) < 1.0,
           "Bank %d: alle %d Kolben auf der Bankachse (45 Grad, |y| = |z|)"
           % (bank + 1, len(kolben)))

# Bankversatz
pruefe(abs(kenn["bankversatz"] - 22.0) < 0.01,
       "Bankversatz %.1f mm" % kenn["bankversatz"])

# Nockenwellen duerfen sich nicht durchdringen.
nw = [(n, s) for n, s in teile if n.startswith("Nockenwelle")]
pruefe(len(nw) == 4, "vier Nockenwellen beim V8 (%d)" % len(nw))
schlimm = 0.0
for i in range(len(nw)):
    for j in range(i + 1, len(nw)):
        schlimm = max(schlimm, nw[i][1].common(nw[j][1]).Volume)
pruefe(schlimm < 1.0,
       "die Nockenwellen stehen nicht ineinander (%.1f mm^3)" % schlimm)

# Je Bank ein Steuertrieb.
kurbelraeder = [s for n, s in teile if "Kettenrad Kurbel" in n]
pruefe(len(kurbelraeder) == 2, "je Bank ein Steuertrieb (%d Kurbelraeder)"
       % len(kurbelraeder))
if len(kurbelraeder) == 2:
    pruefe(kurbelraeder[0].common(kurbelraeder[1]).Volume < 1.0,
           "die beiden Kurbelraeder sitzen nebeneinander")

# JEDE Nockenwelle braucht ihr Kettenrad — beim V8 sind das vier, zwei je
# Bank. Angetrieben wurde lange nur die erste jeder Bank, die zweite lief
# ueberhaupt nicht mit.
nockenraeder = [(n, s) for n, s in teile if "Kettenrad Nocken" in n]
pruefe(len(nockenraeder) == 4,
       "vier Nockenwellenraeder beim V8 (%d)" % len(nockenraeder))
daneben = []
for n, s in nw:
    # Die Wellenachse NICHT aus der Bounding Box nehmen — die Nocken stehen
    # einseitig heraus und verschieben ihre Mitte um gut 5 mm. Der
    # Antriebszapfen am -x-Ende ist dagegen ein glatter Zylinder auf der
    # Achse; seine Mitte ist die Achse.
    b = s.BoundBox
    scheibe = Part.makeBox(4.0, b.YLength + 20.0, b.ZLength + 20.0,
                           FreeCAD.Vector(b.XMin + 0.5, b.YMin - 10.0,
                                          b.ZMin - 10.0))
    zapfen = s.common(scheibe).BoundBox
    wy = (zapfen.YMin + zapfen.YMax) / 2.0
    wz = (zapfen.ZMin + zapfen.ZMax) / 2.0
    naechstes = min(
        (math.hypot(mitte(r, "Y") - wy, mitte(r, "Z") - wz)
         for _rn, r in nockenraeder), default=999.0)
    if naechstes > 0.5:
        daneben.append("%s (%.1f mm)" % (n, naechstes))
pruefe(not daneben,
       "auf jeder Nockenwelle sitzt ein Kettenrad%s"
       % ("" if not daneben else ": " + "; ".join(daneben)))
pruefe(len(kenn.get("angetrieben", [])) == 4,
       "vier angetriebene Nockenwellen gemeldet (%d)"
       % len(kenn.get("angetrieben", [])))

# Und die Kette muss jedes Rad wirklich umschlingen, nicht nur daneben
# vorbeilaufen.
for bank in (1, 2):
    b_rollen = [s for n, s in teile
                if "Kettenrolle" in n and n.startswith("Bank %d" % bank)]
    b_raeder = [(n, s) for n, s in nockenraeder
                if n.startswith("Bank %d" % bank)]
    pruefe(len(b_raeder) == 2,
           "Bank %d treibt beide Nockenwellen (%d Raeder)"
           % (bank, len(b_raeder)))
    for n, r in b_raeder:
        ry, rz = mitte(r, "Y"), mitte(r, "Z")
        radius = max(r.BoundBox.YLength, r.BoundBox.ZLength) / 2.0
        nah = sum(1 for s in b_rollen
                  if abs(math.hypot(mitte(s, "Y") - ry,
                                    mitte(s, "Z") - rz) - radius) < 4.0)
        pruefe(nah >= 4,
               "%s wird von der Kette umschlungen (%d Rollen)" % (n, nah))

# Ventilwinkel: Ein- und Auslass zeigen in verschiedene Richtungen.
ein = [s for n, s in teile if n.startswith("Einlassventil 1.")]
aus = [s for n, s in teile if n.startswith("Auslassventil 1.")]
if ein and aus:
    neigung_ein = mitte(ein[0], "Y") / max(abs(mitte(ein[0], "Z")), 1e-9)
    neigung_aus = mitte(aus[0], "Y") / max(abs(mitte(aus[0], "Z")), 1e-9)
    pruefe(abs(neigung_ein - neigung_aus) > 0.1,
           "Ein- und Auslassventil stehen im Winkel zueinander")

# Ventiltaschen: flach, nicht 13 mm tief.
kolben1 = [s for n, s in teile if n == "Kolben 1"][0]
voll = kt_kolben.baue(bohrung=kenn["bohrung"],
                      kompressionshoehe=kenn["kompressionshoehe"])
fehlt = voll.koerper[0][1].Volume - kolben1.Volume
pruefe(0.0 < fehlt < 30000.0,
       "die Ventiltaschen nehmen %.0f mm^3 weg (nicht den halben Kolben)"
       % fehlt)

# Kette: gleichmaessige Rollenabstaende.
rollen = [s for n, s in teile if "Kettenrolle" in n and n.startswith("Bank 1")]
if len(rollen) > 4:
    import math as _m
    orte = [(mitte(s, "Y"), mitte(s, "Z")) for s in rollen]
    abst = [_m.hypot(orte[i][0] - orte[i + 1][0], orte[i][1] - orte[i + 1][1])
            for i in range(len(orte) - 1)]
    pruefe(max(abst) < 2.0 * min(abst),
           "die Kettenrollen liegen gleichmaessig (%.2f bis %.2f mm)"
           % (min(abst), max(abst)))
FreeCAD.closeDocument(doc.Name)

log("\nFEHLER: %d" % len(FEHLER))
log("ALLE GRUEN" if not FEHLER else "FEHLGESCHLAGEN")
if FEHLER:
    raise SystemExit(1)
