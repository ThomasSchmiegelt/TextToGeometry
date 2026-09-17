# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Baut den V12-Antriebsstrang Schritt fuer Schritt und nimmt Bilder auf.

Laeuft in der **FreeCAD-GUI**, nicht unter FreeCADCmd — nur die kann
rendern (``saveImage`` braucht einen OpenGL-Kontext):

    DISPLAY=:1 FreeCAD Beispiele/film_motor.py
    ffmpeg -framerate 24 -i Beispiele/Film/bilder/f%05d.png \
           -c:v libx264 -pix_fmt yuv420p -crf 20 Beispiele/Film/V12_Aufbau.mp4

Die Bilder landen in ``Beispiele/Film/bilder`` (gitignoriert), der Film
daneben. ``T2G_FILM_AUS`` verlegt beides.

Die Reihenfolge ist die des Zusammenbaus, und die GEHAEUSE kommen zuletzt —
erst sieht man, was drin ist, dann wird es zugedeckt.
"""
import os, sys, time

HIER = os.environ.get("T2G_FILM_AUS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "Film")
BILDER = os.path.join(HIER, "bilder")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "Skills", "Verbrennungsmotor"))
sys.path.insert(0, os.path.join(HERE, "Tools"))
PROT = os.path.join(HIER, "film.txt")
L = []
def log(m):
    L.append(str(m))
    open(PROT, "w", encoding="utf-8").write("\n".join(L) + "\n")

import FreeCAD, FreeCADGui, Part
import kt_motor

if not os.path.isdir(BILDER):
    os.makedirs(BILDER)
for f in os.listdir(BILDER):
    os.remove(os.path.join(BILDER, f))

t0 = time.time()
bau = FreeCAD.newDocument("Bau")
teile, kenn, proben = kt_motor.baue(bauform="V12", mit_kupplung=True,
                                    mit_getriebe=True, getriebe_gaenge=6,
                                    doc=bau)
log("gebaut: %d Koerper in %.1f s" % (len(teile), time.time() - t0))

# --- Reihenfolge des Zusammenbaus ---------------------------------------
# (Titel, Praedikat auf dem Bauteilnamen). Zuerst was sich dreht, dann was
# steuert, dann Kupplung und Getriebeinneres — und erst ganz am Schluss die
# Gehaeuse: Kupplungsglocke, Getriebe unten, Getriebe oben.
def ist(*woerter):
    return lambda n: any(w in n for w in woerter)

SCHRITTE = [
    ("Kurbelwelle",            lambda n: n == "Kurbelwelle"),
    ("Pleuel",                 ist("Pleuel")),
    ("Kolben",                 lambda n: n.startswith("Kolben")),
    ("Ventile",                ist("Einlassventil", "Auslassventil")),
    ("Ventilfedern",           ist("Ventilfeder", "Federteller")),
    ("Tassenstoessel mit HVA", ist("Tassenstoessel", "HVA")),
    ("Nockenwellen",           ist("Nockenwelle")),
    ("Steuerkette",            ist("Kettenrad", "Kettenrolle")),
    ("Schwungrad",             ist("Kupplung: Schwungrad",
                                   "Kupplung: Anlasser")),
    ("Kupplungsscheiben",      ist("Reibbelag", "Belagtraeger",
                                   "Scheibennabe", "Daempferfeder",
                                   "Zwischenplatte")),
    ("Druckplatte und Membranfeder",
                               ist("Druckplatte", "Membranfeder",
                                   "Kupplungsdeckel", "Ausruecklager")),
    ("Getriebewellen",         ist("Antriebswelle", "Hauptwelle",
                                   "Vorgelegewelle", "Zentrierzapfen")),
    ("Zahnraeder",             ist("Festrad", "Losrad", "konstante")),
    ("Nadellager",             ist("Nadellager")),
    ("Waelzlager",             lambda n: "6306" in n),
    ("Synchronringe und Schaltmuffen",
                               ist("Synchronring", "Schaltmuffe")),
    ("Schaltgabeln und Gestaenge",
                               ist("Schaltgabel", "Schaltstange")),
    ("Kupplungsglocke",        ist("Kupplungsglocke")),
    ("Getriebegehaeuse unten", ist("Gehaeuse Unterteil")),
    ("Getriebegehaeuse oben",  ist("Gehaeuse Oberteil")),
]

doc = FreeCAD.newDocument("V12")
FreeCADGui.showMainWindow() if not FreeCADGui.getMainWindow() else None
gui = FreeCADGui.getDocument(doc.Name)
view = FreeCADGui.ActiveDocument.ActiveView
view.viewIsometric()
try:
    view.setAnimationEnabled(False)
except Exception:
    pass

FARBEN = {
    "Kurbelwelle": (0.75, 0.75, 0.80), "Pleuel": (0.70, 0.72, 0.78),
    "Kolben": (0.85, 0.85, 0.88), "Ventile": (0.80, 0.45, 0.25),
    "Ventilfedern": (0.55, 0.60, 0.70),
    "Tassenstoessel mit HVA": (0.65, 0.68, 0.75),
    "Nockenwellen": (0.70, 0.70, 0.75), "Steuerkette": (0.45, 0.48, 0.55),
    "Schwungrad": (0.60, 0.62, 0.68),
    "Kupplungsscheiben": (0.55, 0.40, 0.30),
    "Druckplatte und Membranfeder": (0.65, 0.66, 0.70),
    "Getriebewellen": (0.72, 0.74, 0.80), "Zahnraeder": (0.80, 0.78, 0.60),
    "Nadellager": (0.50, 0.55, 0.62), "Waelzlager": (0.50, 0.55, 0.62),
    "Synchronringe und Schaltmuffen": (0.75, 0.65, 0.45),
    "Schaltgabeln und Gestaenge": (0.60, 0.70, 0.60),
    "Kupplungsglocke": (0.40, 0.45, 0.52),
    "Getriebegehaeuse unten": (0.38, 0.43, 0.50),
    "Getriebegehaeuse oben": (0.42, 0.47, 0.54),
}

BREITE, HOEHE = 1920, 1080
HALTEN = 14            # Bilder je Schritt (Standzeit)
nummer = [0]

def bild():
    nummer[0] += 1
    view.saveImage(os.path.join(BILDER, "f%05d.png" % nummer[0]),
                   BREITE, HOEHE, "White")

vergeben = set()
for schritt, (titel, passt) in enumerate(SCHRITTE, 1):
    dran = [(n, s) for n, s in teile
            if n not in vergeben and passt(n)]
    for n, _s in dran:
        vergeben.add(n)
    if not dran:
        log("  %-32s (nichts)" % titel)
        continue
    for n, shp in dran:
        o = doc.addObject("Part::Feature", "T")
        o.Shape = shp
        o.Label = n
        o.ViewObject.ShapeColor = FARBEN.get(titel, (0.7, 0.7, 0.7))
    doc.recompute()
    # Nach JEDEM Schritt neu einpassen: sonst waechst der Antriebsstrang
    # aus dem Bild heraus — im ersten Versuch stand das Getriebe halb
    # ausserhalb des Rahmens.
    view.viewIsometric()
    view.fitAll()
    FreeCADGui.updateGui()
    for _ in range(HALTEN):
        bild()
    log("  %2d. %-32s %3d Teile  ->  Bild %d"
        % (schritt, titel, len(dran), nummer[0]))

# Zum Schluss einmal herumdrehen: die Kamera um die Hochachse schwenken.
view.fitAll()
for k in range(90):
    dreh = (FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), k * 4.0)
            .multiply(FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 60.0)))
    try:
        view.setCameraOrientation(dreh.Q)
    except Exception:
        view.viewIsometric()
    FreeCADGui.updateGui()
    bild()

rest = [n for n, _s in teile if n not in vergeben]
log("\nnicht zugeordnet: %d %s" % (len(rest), rest[:5]))
log("%d Bilder in %s" % (nummer[0], BILDER))
log("fertig nach %.0f s" % (time.time() - t0))
