# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Baut das Fünfgang-Getriebe aus den vier Skills und prüft das Ergebnis.

Referenzmodell und zugleich Regressionstest: 17 Bauteile, Gehäuse mit 3 mm
Freiraum zu den Rädern und 4 mm Wandstärke. Das Skript ist die versionierte
Fassung des Getriebes — das ``.FCStd`` ist nur sein Abfall und daher
gitignored; wer das Modell braucht, erzeugt es hier neu.

    FreeCADCmd Beispiele/getriebe_5gang.py

Schreibt den Bericht nach ``$T2G_OUT`` (Vorgabe: ``getriebe_bau.txt`` im
aktuellen Verzeichnis), das Dokument nach ``$T2G_GETRIEBE_FCSTD``
(Vorgabe: ``~/T2G-Projekte/Getriebe_5Gang.FCStd``). Stimmt eine der geprüften
Zusagen nicht, endet es mit ``PRUEFUNG FEHLGESCHLAGEN`` und Exit-Code 1.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "Tools"))

import FreeCAD
import Part
import T2GSkills as S
import getriebe_auslegung as G

#: Geforderte Maße aus der Aufgabenstellung.
ABSTAND = 3.0          # Freiraum Rad -> Gehäuseinnenwand
WAND = 4.0             # Wandstärke des Gehäuses
GAENGE = 5

MODUL, BREITE, LUFT = 2.0, 10.0, 2.0
WELLE_D, SITZ_D, LAGER_A, LAGER_B = 15.0, 12.0, 28.0, 8.0
KUGELN, SPIEL = 8, 0.1     # Waelzkoerper je Lager, Passungsspiel [mm]
ZAEHNE_SUMME = 48      # z1 + z2, für alle Gänge gleich (siehe gangpaare)

OUT = os.environ.get("T2G_OUT", "getriebe_bau.txt")
FCSTD = os.environ.get(
    "T2G_GETRIEBE_FCSTD",
    os.path.expanduser("~/T2G-Projekte/Getriebe_5Gang.FCStd"))

ZEILEN = []
FEHLER = []


def log(m):
    ZEILEN.append(str(m))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(ZEILEN) + "\n")


def pruefe(bedingung, text):
    """Eine Zusage, die das Modell einhalten muss."""
    log("%s %s" % ("ok  " if bedingung else "FEHL", text))
    if not bedingung:
        FEHLER.append(text)


# --- Auslegung ----------------------------------------------------------
paare = G.gangpaare(ZAEHNE_SUMME, GAENGE)
A = G.achsabstand(MODUL, *paare[0][:2])
IL, IB, IH, ACHS_Z = G.gehaeuse_aus_raedern(MODUL, paare, BREITE, LUFT,
                                            ABSTAND, A)
Y = IB / 2.0
Z_UNTEN, Z_OBEN = ACHS_Z, ACHS_Z + A

log("=== Auslegung ===")
log("Modul %.1f · Achsabstand %.0f mm · Gehaeuse innen %.0f x %.0f x %.0f mm"
    % (MODUL, A, IL, IB, IH))
for k, (z1, z2, i) in enumerate(paare, 1):
    log("  Gang %d: %2d/%2d Zaehne · i = %.3f" % (k, z1, z2, i))

eng = S.SkillEngine(os.path.join(HERE, "Skills")).load_all()
fehlend = [n for n in ("zahnrad", "welle", "lager", "gehaeuse")
           if n not in eng.registry.names()]
if fehlend:
    log("Skills fehlen: %s" % ", ".join(fehlend))
    raise SystemExit(1)

doc = FreeCAD.newDocument("Getriebe_5Gang")
try:
    asm = doc.addObject("Assembly::AssemblyObject", "Getriebe")
except Exception:  # noqa: BLE001 - ohne Assembly-Workbench reicht App::Part
    asm = doc.addObject("App::Part", "Getriebe")
asm.Label = "Getriebe 5 Gang"


def lege_ab(shapes, name, label, achse_x=True, pos=(0, 0, 0)):
    """Bauteil ablegen; die Skills bauen entlang Z, das Getriebe laeuft in X.

    Ein Bauteil kann aus mehreren Solids bestehen -- das Lager bringt
    Innenring, Aussenring und acht Kugeln mit. Die gehoeren alle an dieselbe
    Stelle und werden einzeln abgelegt, damit sie sichtbar bleiben.
    """
    if not isinstance(shapes, (list, tuple)):
        shapes = [shapes]
    aus = []
    for k, shape in enumerate(shapes):
        s = shape.copy()
        if achse_x:
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0), 90)
        s.translate(FreeCAD.Vector(*pos))
        o = doc.addObject("Part::Feature",
                          name if k == 0 else "%s_%d" % (name, k))
        o.Shape = s
        o.Label = label if len(shapes) == 1 else "%s (%d/%d)" % (
            label, k + 1, len(shapes))
        asm.addObject(o)
        aus.append(o)
    return aus


gebaut = []
# --- Zahnraeder ---------------------------------------------------------
for k, (z1, z2, i) in enumerate(paare):
    x = ABSTAND + k * (BREITE + LUFT)
    oben, _v, _p = eng.build("zahnrad", {"modul": MODUL, "zaehne": z1,
                                         "breite": BREITE, "bohrung": WELLE_D,
                                         "nabe_d": 0.0, "nabe_b": 0.0,
                                         "spiel": SPIEL})
    # Das getriebene Rad wird um eine halbe Zahnteilung verdreht, damit sein
    # Zahn in die Luecke des treibenden greift. Gemessen: ohne Phase
    # durchdringen sich 12/36 Zaehne um 150 mm^3 (5,6 %), mit 180/z2 Grad
    # bleiben 0,6 mm^3 (0,0 %).
    unten, _v, _p = eng.build("zahnrad", {"modul": MODUL, "zaehne": z2,
                                          "breite": BREITE, "bohrung": WELLE_D,
                                          "nabe_d": 0.0, "nabe_b": 0.0,
                                          "spiel": SPIEL,
                                          "phase": 180.0 / z2})
    gebaut += lege_ab(oben, "Rad%dA" % (k + 1),
                      "Gang %d treibend (z=%d)" % (k + 1, z1),
                      pos=(x, Y, Z_OBEN))
    gebaut += lege_ab(unten, "Rad%dB" % (k + 1),
                      "Gang %d getrieben (z=%d)" % (k + 1, z2),
                      pos=(x, Y, Z_UNTEN))

# --- Wellen -------------------------------------------------------------
WL = IL + 2 * WAND + 2 * (LAGER_B + 6.0)
for name, label, z in (("Eingangswelle", "Eingangswelle", Z_OBEN),
                       ("Ausgangswelle", "Ausgangswelle", Z_UNTEN)):
    w, _v, _p = eng.build("welle", {"laenge": WL, "welle_d": WELLE_D,
                                    "sitz_d": SITZ_D, "sitz_l": LAGER_B + 2.0})
    gebaut += lege_ab(w, name, label,
                      pos=(-(WAND + LAGER_B + 6.0), Y, z))

# --- Lager --------------------------------------------------------------
# Auf die abgesetzten Sitze, nicht auf den vollen Schaft: der Sitz hat
# SITZ_D, der Schaft WELLE_D. Vorher sassen die Lager zur Haelfte auf dem
# dickeren Teil und durchdrangen ihn um 419 mm^3 -- unsichtbar, solange
# Bohrung und Sitz exakt gleich gross waren und niemand nachmass.
X0 = -(WAND + LAGER_B + 6.0)          # linkes Wellenende
SITZ_L = LAGER_B + 2.0
for seite, x in (("links", X0 + (SITZ_L - LAGER_B) / 2.0),
                 ("rechts", X0 + WL - SITZ_L + (SITZ_L - LAGER_B) / 2.0)):
    for welle, z in (("Eingang", Z_OBEN), ("Ausgang", Z_UNTEN)):
        l, _v, _p = eng.build("lager", {"innen_d": SITZ_D, "aussen_d": LAGER_A,
                                        "breite": LAGER_B, "kugeln": KUGELN,
                                        "spiel": SPIEL})
        gebaut += lege_ab(l, "Lager_%s_%s" % (welle, seite),
                          "Lager %s %s" % (welle, seite), pos=(x, Y, z))

# --- Gehaeuse -----------------------------------------------------------
g, _v, _p = eng.build("gehaeuse", {"innen_l": IL, "innen_b": IB, "innen_h": IH,
                                   "wand": WAND, "welle_d": LAGER_A + 1.0,
                                   "achsabstand": A, "achs_z": ACHS_Z})
gh = doc.addObject("Part::Feature", "Gehaeuse")
gh.Shape = g[0]
gh.Label = "Gehaeuse"
asm.addObject(gh)
gebaut.append(gh)
doc.recompute()

# --- Pruefung -----------------------------------------------------------
log("\n=== Pruefung ===")
# Ein Lager besteht aus Innenring, Aussenring und den Waelzkoerpern.
LAGER_SOLIDS = 2 + KUGELN
erwartet = 2 * GAENGE + 2 + 4 * LAGER_SOLIDS + 1
pruefe(len(gebaut) == erwartet,
       "Solids: %d (erwartet %d: %d Raeder, 2 Wellen, 4 Lager a %d, 1 Gehaeuse)"
       % (len(gebaut), erwartet, 2 * GAENGE, LAGER_SOLIDS))

gesamt = sum(o.Shape.Volume for o in gebaut)
log("     Gesamtvolumen %.0f mm^3 (%.2f kg bei 7.85 g/cm^3)"
    % (gesamt, gesamt * 7.85e-6))
pruefe(all(o.Shape.Solids for o in gebaut),
       "jedes Bauteil ist ein Solid")

achsabstaende = {round(G.achsabstand(MODUL, z1, z2), 6) for z1, z2, _i in paare}
pruefe(len(achsabstaende) == 1,
       "alle %d Gaenge auf einem Achsabstand (%s mm)"
       % (GAENGE, ", ".join("%.1f" % a for a in sorted(achsabstaende))))

raeder = [o for o in gebaut if o.Label.startswith("Gang")]
mind = min(min(bb.XMin, IL - bb.XMax, bb.YMin, IB - bb.YMax,
               bb.ZMin, IH - bb.ZMax)
           for bb in (o.Shape.BoundBox for o in raeder))
pruefe(mind >= ABSTAND - 1e-6,
       "kleinster Abstand Rad->Innenwand %.2f mm (gefordert %.0f)"
       % (mind, ABSTAND))

# Passung: nach dem Spiel in Bohrung und Laufrille darf sich nichts mehr
# durchdringen. Ohne das meldete jede Welle 3-5 %% Ueberschneidung mit ihren
# Raedern und Lagern -- geometrisch eine Nullpassung, nicht zu unterscheiden
# von einem echten Fehler.
# Gemessen wird der Anteil am kleineren Teil, wie in der Kollisionsregel der
# Workbench (_KOLL_TOL): kaemmende Zahnraeder durchdringen sich zwangslaeufig
# ein wenig, solange ihre Zaehne nicht in Eingriffsphase gedreht sind. Ein
# Lager auf dem falschen Wellenabsatz liegt eine Groessenordnung darueber.
KOLL_TOL = 0.02
schlimmste, wo, abs_wert = 0.0, "", 0.0
for i in range(len(gebaut)):
    bi = gebaut[i].Shape.BoundBox
    for j in range(i + 1, len(gebaut)):
        bj = gebaut[j].Shape.BoundBox
        if not bi.intersect(bj):
            continue
        try:
            v = float(gebaut[i].Shape.common(gebaut[j].Shape).Volume or 0.0)
        except Exception:  # noqa: BLE001
            v = 0.0
        kleiner = min(gebaut[i].Shape.Volume, gebaut[j].Shape.Volume)
        anteil = v / kleiner if kleiner > 0 else 0.0
        if anteil > schlimmste:
            schlimmste, abs_wert = anteil, v
            wo = "%s / %s" % (gebaut[i].Label, gebaut[j].Label)
pruefe(schlimmste < KOLL_TOL,
       "groesste Durchdringung %.1f %% (%.0f mm^3)%s, erlaubt %.0f %%"
       % (schlimmste * 100, abs_wert, (" bei " + wo) if wo else "",
          KOLL_TOL * 100))

r1 = G.kopfkreis(MODUL, paare[0][0]) / 2.0
r2 = G.kopfkreis(MODUL, paare[0][1]) / 2.0
pruefe(r1 + r2 > A,
       "Kopfkreise Gang 1: %.0f + %.0f = %.0f mm > Achsabstand %.0f mm "
       "(Zaehne greifen ineinander)" % (r1, r2, r1 + r2, A))

bb_g = gh.Shape.BoundBox
pruefe(abs(bb_g.YLength - (IB + 2 * WAND)) < 1e-6,
       "Gehaeuse aussen %.0f mm breit = innen %.0f + 2 x %.0f Wand"
       % (bb_g.YLength, IB, WAND))

# --- Speichern ----------------------------------------------------------
os.makedirs(os.path.dirname(FCSTD), exist_ok=True)
doc.saveAs(FCSTD)
log("\ngespeichert: %s (%.0f kB)" % (FCSTD, os.path.getsize(FCSTD) / 1024.0))

if FEHLER:
    log("\nPRUEFUNG FEHLGESCHLAGEN: %d" % len(FEHLER))
    raise SystemExit(1)
log("\nALLE ZUSAGEN EINGEHALTEN")
