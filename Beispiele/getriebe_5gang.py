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


def lege_ab(shape, name, label, achse_x=True, pos=(0, 0, 0)):
    """Bauteil ablegen; die Skills bauen entlang Z, das Getriebe laeuft in X."""
    s = shape.copy()
    if achse_x:
        s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0), 90)
    s.translate(FreeCAD.Vector(*pos))
    o = doc.addObject("Part::Feature", name)
    o.Shape = s
    o.Label = label
    asm.addObject(o)
    return o


gebaut = []
# --- Zahnraeder ---------------------------------------------------------
for k, (z1, z2, i) in enumerate(paare):
    x = ABSTAND + k * (BREITE + LUFT)
    oben, _v, _p = eng.build("zahnrad", {"modul": MODUL, "zaehne": z1,
                                         "breite": BREITE, "bohrung": WELLE_D,
                                         "nabe_d": 0.0, "nabe_b": 0.0})
    unten, _v, _p = eng.build("zahnrad", {"modul": MODUL, "zaehne": z2,
                                          "breite": BREITE, "bohrung": WELLE_D,
                                          "nabe_d": 0.0, "nabe_b": 0.0})
    gebaut.append(lege_ab(oben[0], "Rad%dA" % (k + 1),
                          "Gang %d treibend (z=%d)" % (k + 1, z1),
                          pos=(x, Y, Z_OBEN)))
    gebaut.append(lege_ab(unten[0], "Rad%dB" % (k + 1),
                          "Gang %d getrieben (z=%d)" % (k + 1, z2),
                          pos=(x, Y, Z_UNTEN)))

# --- Wellen -------------------------------------------------------------
WL = IL + 2 * WAND + 2 * (LAGER_B + 6.0)
for name, label, z in (("Eingangswelle", "Eingangswelle", Z_OBEN),
                       ("Ausgangswelle", "Ausgangswelle", Z_UNTEN)):
    w, _v, _p = eng.build("welle", {"laenge": WL, "welle_d": WELLE_D,
                                    "sitz_d": SITZ_D, "sitz_l": LAGER_B + 2.0})
    gebaut.append(lege_ab(w[0], name, label,
                          pos=(-(WAND + LAGER_B + 6.0), Y, z)))

# --- Lager --------------------------------------------------------------
for seite, x in (("links", -WAND - LAGER_B / 2.0 - 1.0),
                 ("rechts", IL + WAND - LAGER_B / 2.0 + 1.0)):
    for welle, z in (("Eingang", Z_OBEN), ("Ausgang", Z_UNTEN)):
        l, _v, _p = eng.build("lager", {"innen_d": SITZ_D, "aussen_d": LAGER_A,
                                        "breite": LAGER_B, "nut_t": 1.0})
        gebaut.append(lege_ab(l[0], "Lager_%s_%s" % (welle, seite),
                              "Lager %s %s" % (welle, seite), pos=(x, Y, z)))

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
pruefe(len(gebaut) == 2 * GAENGE + 2 + 4 + 1,
       "Bauteile: %d (erwartet %d)" % (len(gebaut), 2 * GAENGE + 2 + 4 + 1))

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
