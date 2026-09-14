# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Bauen ins Dokument: Platzierung, Ersetzen, Kollisionen, Lager.

Braucht das ECHTE Part-Modul und laeuft daher nur unter FreeCADCmd:

    FreeCADCmd test_bauen.py

Geprueft wird ``T2GPanel``s Bau-Pfad ohne Qt. Frueher lag jede dieser
Pruefungen als Wegwerfskript in /tmp und kopierte sich von Hand eine
Teilmenge der Panel-Methoden zusammen; sobald eine Signatur wuchs, brach
das Geruest stumm. Der Stub hier uebernimmt deshalb ALLES aus der
Klasse und ersetzt nur, was Widgets braucht.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Vorn einfuegen: der installierte Mod-Ordner steht bereits auf sys.path und
# enthaelt eine Kopie dieser Datei. Ohne das hier laeuft der Test gegen den
# zuletzt synchronisierten Stand statt gegen die Quelle -- und meldet
# froehlich GRUEN zu Code, den es gar nicht ausgefuehrt hat.
sys.path.insert(0, HERE)

import FreeCAD
import FreeCADGui
import Part

# FreeCADCmd bringt einen FreeCADGui-Stummel mit; T2GCommand meldet beim
# Import Befehle an und zieht die aktive Ansicht.
if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *a, **k: None
if not hasattr(FreeCADGui, "SendMsgToActiveView"):
    FreeCADGui.SendMsgToActiveView = lambda *a, **k: None

import T2GCommand
import T2GSkills

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


_P = T2GCommand.T2GPanel


class Panel(object):
    """Der Bau-Pfad des Panels ohne Qt."""

    _project = None

    def _skills_engine(self, reload=False):
        return T2GSkills.SkillEngine(
            T2GSkills.SkillEngine._default_skills_dir()).load_all()


for _name, _wert in _P.__dict__.items():
    if _name.startswith("__") or _name in ("_skills_engine", "_project"):
        continue
    setattr(Panel, _name, _wert)


class Aktion(object):
    def __init__(self, *args):
        self.args = list(args)

    def arg(self, i):
        return self.args[i] if i < len(self.args) else ""


def mitte(o, achse):
    b = o.Shape.BoundBox
    return (getattr(b, achse + "Min") + getattr(b, achse + "Max")) / 2.0


def koerper(doc):
    return [o for o in doc.Objects
            if getattr(o, "Shape", None) is not None
            and not o.Shape.isNull() and o.Shape.Solids]


# --- 1: Platzierung ------------------------------------------------------
log("\n--- Platzierung ---")
FreeCAD.newDocument("Platz")
p = Panel()
r = p._act_skill_bauen(Aktion("zahnrad", "als=rad_1", "x=48", "z=10"))
doc = FreeCAD.ActiveDocument
o = koerper(doc)[-1]
pruefe(abs(mitte(o, "X") - 48) < 0.6, "x=48 verschiebt wirklich (%.1f)"
       % mitte(o, "X"))
v_platziert = o.Shape.Volume
p._act_skill_bauen(Aktion("zahnrad", "als=rad_2"))
v_roh = koerper(doc)[-1].Shape.Volume
pruefe(abs(v_platziert - v_roh) < 1.0,
       "Platzierung aendert das Volumen nicht (%.0f = %.0f)"
       % (v_platziert, v_roh))
r = p._act_skill_bauen(Aktion("welle", "als=welle_q", "dreh_y=90"))
b = koerper(doc)[-1].Shape.BoundBox
pruefe(b.XLength > b.ZLength, "dreh_y=90 legt die Welle um (%.0f x %.0f x %.0f)"
       % (b.XLength, b.YLength, b.ZLength))

# --- 2: Namensraeume -----------------------------------------------------
log("\n--- Bauteilname gegen Skillname ---")
try:
    p._act_skill_bauen(Aktion("quatsch_9"))
    pruefe(False, "unbekannter Skill wirft einen Fehler")
except T2GSkills.SkillError as e:
    pruefe("zahnrad" in str(e),
           "Fehlermeldung nennt die vorhandenen Skills")
import T2GProject
prj = T2GProject.Project.create(os.environ.get("T2G_TEST_PRJ", "/tmp"),
                                "Bautest %d" % os.getpid())
prj.skills = [T2GProject.SkillNeed(name="zahnrad_3", status="kopiert",
                                   source="zahnrad")]
p._project = prj
r = p._act_skill_bauen(Aktion("zahnrad_3", "als=zahnrad_3", "x=120"))
pruefe("Skill zahnrad" in r, "Bauteilname wird auf den Skill aufgeloest")
p._project = None

# --- 3: Neu bauen ersetzt ------------------------------------------------
log("\n--- Neu bauen ersetzt ---")
vorher = len(koerper(doc))
p._act_skill_bauen(Aktion("zahnrad", "als=rad_1", "x=0"))
nachher = koerper(doc)
pruefe(len(nachher) == vorher, "Teilezahl bleibt gleich (%d)" % len(nachher))
treffer = [o for o in nachher if "rad_1" in o.Label]
pruefe(len(treffer) == 1, "rad_1 genau einmal vorhanden (%d)" % len(treffer))
pruefe(treffer and abs(mitte(treffer[0], "X")) < 0.6,
       "rad_1 steht an der neuen Stelle")
pruefe(any("rad_2" in o.Label for o in nachher),
       "rad_2 wurde nicht mitgeloescht")

# --- 4: Kollisionen ------------------------------------------------------
log("\n--- Kollisionen ---")
FreeCAD.newDocument("Koll")
p = Panel()
p._act_skill_bauen(Aktion("zahnrad", "als=a", "x=0"))
r = p._act_skill_bauen(Aktion("zahnrad", "als=b", "x=0"))
pruefe("ACHTUNG" in r, "gestapelte Raeder werden gemeldet")
r = p._act_skill_bauen(Aktion("zahnrad", "als=b", "x=60"))
pruefe("ACHTUNG" not in r, "gestaffelte Raeder ergeben keinen Fehlalarm")
pruefe("uebrige Bauteile liegen bei" in r,
       "jede Baumeldung nennt die Lage der uebrigen Teile")
# kaemmende Raeder: Kopfradien 17 + 37 bei 50 mm Achsabstand
FreeCAD.newDocument("Kaemmen")
p = Panel()
p._act_skill_bauen(Aktion("zahnrad", "als=klein", "zaehne=15", "dreh_y=90"))
r = p._act_skill_bauen(Aktion("zahnrad", "als=gross", "zaehne=35",
                              "phase=5.14", "z=50", "dreh_y=90"))
pruefe("ACHTUNG" not in r, "kaemmende Raeder sind keine Kollision")
r = p._act_kollision(Aktion())
pruefe("Baugruppe belegt" in r, "Gesamtpruefung nennt die Ausdehnung")

# --- 5: Lager ------------------------------------------------------------
log("\n--- Rillenkugellager ---")
eng = T2GSkills.SkillEngine(T2GSkills.SkillEngine._default_skills_dir()).load_all()
KUGELN = 8
shapes, _v, _p = eng.build("lager", {"innen_d": 15.0, "aussen_d": 35.0,
                                     "breite": 11.0, "kugeln": KUGELN,
                                     "spiel": 0.1})
pruefe(len(shapes) == 2 + KUGELN,
       "Innenring, Aussenring und %d Kugeln (%d Solids)"
       % (KUGELN, len(shapes)))
pruefe(all(s.Volume > 0 for s in shapes), "kein leeres Solid")
schlimm = 0.0
for i in range(len(shapes)):
    for j in range(i + 1, len(shapes)):
        schlimm = max(schlimm, shapes[i].common(shapes[j]).Volume)
pruefe(schlimm < 1e-3,
       "im Lager beruehrt nichts das andere (%.4f mm^3)" % schlimm)
welle = Part.makeCylinder(15.0 / 2.0, 40.0, FreeCAD.Vector(0, 0, -10))
durch = max(s.common(welle).Volume for s in shapes)
pruefe(durch < 1e-3,
       "Bohrung passt spielend auf eine 15-mm-Welle (%.4f mm^3)" % durch)
da = max(shapes[1].BoundBox.XLength, shapes[1].BoundBox.YLength)
pruefe(abs(da - 35.0) < 0.2, "Aussendurchmesser 35 mm eingehalten (%.2f)" % da)
pruefe(abs(shapes[0].BoundBox.ZLength - 11.0) < 0.01, "Breite 11 mm eingehalten")

# --- 6: Zahnphase --------------------------------------------------------
log("\n--- Zahneingriff ---")
M, Z1, Z2 = 2.0, 12, 36
A = M * (Z1 + Z2) / 2.0


def zahnrad(z, phase):
    sh, _v, _p = eng.build("zahnrad", {"modul": M, "zaehne": z, "breite": 10.0,
                                       "bohrung": 15.0, "nabe_d": 0.0,
                                       "nabe_b": 0.0, "spiel": 0.1,
                                       "phase": phase})
    return sh[0]


a = zahnrad(Z1, 0.0)
ohne = zahnrad(Z2, 0.0)
ohne.translate(FreeCAD.Vector(0, A, 0))
mit = zahnrad(Z2, 180.0 / Z2)
mit.translate(FreeCAD.Vector(0, A, 0))
v_ohne = a.common(ohne).Volume
v_mit = a.common(mit).Volume
log("     ohne Phase %.1f mm^3, mit halber Teilung %.1f mm^3" % (v_ohne, v_mit))
pruefe(v_mit < 0.05 * v_ohne,
       "halbe Zahnteilung raeumt den Eingriff frei (%.1f -> %.1f mm^3)"
       % (v_ohne, v_mit))

# --- 7: Werkzeug baut ins Dokument ---------------------------------------
log("\n--- Werkzeug baut die ganze Baugruppe ---")
import T2GTools
FreeCAD.newDocument("Werkzeug")
p = Panel()
p._tools = T2GTools.discover_python_tools([os.path.join(HERE, "Tools")])
werkzeug = T2GTools.find_tool(p._tools, "getriebe.baue")
pruefe(werkzeug is not None, "getriebe.baue wird als Werkzeug gefunden")

# Ein rechnendes Werkzeug bleibt Text, ein bauendes wird Geometrie.
rechner = T2GTools.find_tool(p._tools, "getriebe_auslegung.achsabstand")
r = p.run_external_tool(rechner, "modul=2.0;z1=12;z2=36")
pruefe("48" in r and "Bauteil" not in r,
       "Rechenwerkzeug liefert weiter eine Zahl: %s" % r[-40:])

r = p.run_external_tool(werkzeug, "gaenge=5;abstand=3;wand=4")
log("     %s" % r[:150])
doc = FreeCAD.ActiveDocument
gebaut = koerper(doc)
pruefe(len(gebaut) == 53, "53 Bauteile im Dokument (%d)" % len(gebaut))
pruefe("ACHTUNG" not in r, "das Werkzeug baut kollisionsfrei")
pruefe(any("Gang 1 treibend" in o.Label for o in gebaut),
       "die Bauteile tragen die Namen des Werkzeugs")

# Nochmal aufrufen ersetzt, statt danebenzulegen.
r = p.run_external_tool(werkzeug, "gaenge=3;abstand=5;wand=6")
gebaut = koerper(doc)
pruefe(len(gebaut) == 49, "erneuter Aufruf ersetzt (%d Bauteile)" % len(gebaut))

# --- 8: skill_bauen erreicht auch ein Baugruppen-Werkzeug ----------------
log("\n--- skill_bauen findet das Werkzeug ---")
FreeCAD.newDocument("SkillWerkzeug")
p = Panel()
p._tools = T2GTools.discover_python_tools([os.path.join(HERE, "Tools")])
r = p._act_skill_bauen(Aktion("getriebe", "gaenge=5", "abstand=3", "wand=4"))
log("     %s" % r[:120])
gebaut = koerper(FreeCAD.ActiveDocument)
pruefe(len(gebaut) == 53,
       "skill_bauen: getriebe baut 53 Bauteile (%d)" % len(gebaut))
pruefe("ACHTUNG" not in r, "kollisionsfrei")
# Ein echter Skill bleibt ein Skill.
r = p._act_skill_bauen(Aktion("zahnrad", "als=probe", "x=300"))
pruefe("gebaut" in r and "Bauteil(e)" not in r,
       "ein vorhandener Skill wird weiter als Skill gebaut")

log("\nFEHLER: %d" % len(FEHLER))
log("ALLE GRUEN" if not FEHLER else "FEHLGESCHLAGEN")
if FEHLER:
    raise SystemExit(1)
