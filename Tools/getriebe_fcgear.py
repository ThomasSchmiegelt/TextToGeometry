# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Vollständiges Schaltgetriebe — Zahnräder vom FCGear-Add-on.

Der Unterschied zu ``Tools/getriebe.py``: dort kommen die Räder aus einem
eigenen Skill, der die Zahnflanken als Trapez annähert. Hier erzeugt das
installierte Add-on ``freecad.gears`` echte Evolventenverzahnung, wahlweise
gerade, schräg oder als Pfeilverzahnung.

    teile = baue(gaenge=5, modul=2.0, verzahnung="schraeg", schraegwinkel=15)

Kinematisch ist es ein Vorgelege mit **Losrädern und Schaltmuffen**: die
kleinen Räder sitzen fest auf der Eingangswelle, die großen laufen lose auf der
Ausgangswelle, dazwischen sitzen Schaltmuffen. Fünf dauernd kämmende Paare auf
zwei Wellen wären blockiert — das ist der Zustand, den dieses Modul ablöst.

Was fehlt und bewusst fehlt: Synchronringe und Schaltgabeln. Auf diesem
Detaillierungsgrad wären sie Geometrie ohne Aussage. Die Schaltmuffen stehen
alle in Neutralstellung.

FCGear-Eigenheiten, die hier gekapselt sind: die Property heißt ``num_teeth``
und nicht ``teeth``, der Schrägungswinkel ``helix_angle`` und nicht ``beta``,
ein ``ActiveDocument`` muss existieren, und ohne ``recompute()`` ist ``Shape``
leer.
"""

import math
import os
import sys

_HIER = os.path.dirname(os.path.abspath(__file__))
_WURZEL = os.path.dirname(_HIER)
for _p in (_WURZEL, _HIER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FreeCAD                                            # noqa: E402
import Part                                               # noqa: E402
from FreeCAD import Vector                                # noqa: E402

import gehaeuse_kontur as GK                              # noqa: E402
import getriebe_auslegung as G                            # noqa: E402
import lager_din625 as LG                                 # noqa: E402

#: Verzahnungsarten, die die Maske anbietet.
VERZAHNUNG = ("gerade", "schraeg", "pfeil")


class GetriebeFehler(Exception):
    pass


def _gear_modul():
    try:
        import freecad.gears.commands as gc
    except ImportError as e:
        raise GetriebeFehler(
            "Das Add-on freecad.gears (FCGear) ist nicht installiert: %s" % e)
    return gc


def zahnrad(doc, zaehne, modul, breite, bohrung, verzahnung="gerade",
            schraegwinkel=0.0, eingriffswinkel=20.0, flankenspiel=0.05):
    """Ein Evolventenrad von FCGear; liefert (Shape, Teilkreis, Kopfkreis).

    Das erzeugte DocumentObject wird nach dem Auslesen wieder entfernt — im
    Dokument sollen die fertigen Körper stehen, nicht ein Dutzend
    FCGear-Parameterobjekte, die beim nächsten Recompute alles neu rechnen.
    """
    gc = _gear_modul()
    vorher = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    g = gc.CreateInvoluteGear.create()
    try:
        g.num_teeth = int(zaehne)
        g.module = "%f mm" % float(modul)
        g.height = "%f mm" % float(breite)
        g.pressure_angle = "%f deg" % float(eingriffswinkel)
        g.backlash = "%f mm" % float(flankenspiel)
        art = str(verzahnung).lower()
        if art in ("schraeg", "pfeil"):
            g.helix_angle = "%f deg" % float(schraegwinkel)
            g.double_helix = (art == "pfeil")
        if float(bohrung) > 0.0:
            g.axle_hole = True
            g.axle_holesize = "%f mm" % float(bohrung)
        doc.recompute()
        if g.Shape.isNull() or not g.Shape.Solids:
            raise GetriebeFehler(
                "FCGear hat fuer z=%d kein Solid geliefert." % int(zaehne))
        return (g.Shape.copy(), g.pitch_diameter.Value,
                g.addendum_diameter.Value)
    finally:
        try:
            doc.removeObject(g.Name)
        except Exception:  # noqa: BLE001
            pass
        if vorher is not None and vorher.Name != doc.Name:
            FreeCAD.setActiveDocument(vorher.Name)


def _welle(laenge, d, sitz_d, sitz_l):
    """Welle mit abgesetzten Lagersitzen, entlang Z gebaut."""
    k = Part.makeCylinder(d / 2.0, laenge)
    for z in (0.0, laenge - sitz_l):
        absatz = Part.makeCylinder(d / 2.0 + 1.0, sitz_l, Vector(0, 0, z))
        sitz = Part.makeCylinder(sitz_d / 2.0, sitz_l, Vector(0, 0, z))
        k = k.cut(absatz).fuse(sitz)
    return k.removeSplitter()


def _schaltmuffe(d_innen, d_aussen, breite, nut_t=1.5):
    """Schaltmuffe: Ring mit umlaufender Schaltnut für die Gabel."""
    k = Part.makeCylinder(d_aussen / 2.0, breite)
    k = k.cut(Part.makeCylinder(d_innen / 2.0, breite + 2.0,
                                Vector(0, 0, -1.0)))
    nut_b = breite / 3.0
    aussen = Part.makeCylinder(d_aussen / 2.0 + 1.0, nut_b,
                               Vector(0, 0, (breite - nut_b) / 2.0))
    innen = Part.makeCylinder(d_aussen / 2.0 - nut_t, nut_b + 2.0,
                              Vector(0, 0, (breite - nut_b) / 2.0 - 1.0))
    return k.cut(aussen.cut(innen)).removeSplitter()


def kennwerte(gaenge=5, modul=2.0, zaehne_summe=48, breite=12.0, luft=6.0,
              welle_d=20.0, **_rest):
    """Die Auslegung ohne Geometrie — schnell, für die Maske und den Agenten."""
    paare = G.gangpaare(int(zaehne_summe), int(gaenge))
    a = G.achsabstand(modul, *paare[0][:2])
    schritt = float(breite) + float(luft)
    return {
        "achsabstand": a,
        "gangpaare": [(z1, z2, round(i, 4)) for z1, z2, i in paare],
        "baulaenge": round(schritt * int(gaenge) + float(luft), 2),
        "kopfkreis_max": round(G.kopfkreis(modul, max(z for _a, z, _i in paare)),
                               2),
        "lager": LG.waehle(welle_d),
    }


def baue(gaenge=5, modul=2.0, zaehne_summe=48, breite=12.0, luft=6.0,
         verzahnung="gerade", schraegwinkel=15.0, eingriffswinkel=20.0,
         flankenspiel=0.05, welle_d=20.0, lager_reihe="62", spiel=0.1,
         gehaeuse_luft=3.0, wand=4.0, flansch_b=12.0, schraube_d=6.0,
         muffe_b=0.0, doc=None):
    """Das ganze Getriebe als (Bezeichnung, Shape)-Paare.

    gaenge         Zahl der Gangstufen
    modul          Verzahnungsmodul [mm]
    zaehne_summe   z1 + z2, für ALLE Gänge gleich -> ein Achsabstand
    breite         Zahnbreite [mm]        luft  Luft zwischen den Radpaaren
    verzahnung     "gerade" | "schraeg" | "pfeil"
    schraegwinkel  Schrägungswinkel [Grad], wirkt bei schraeg und pfeil
    welle_d        Wellendurchmesser [mm]; daraus wird das Lager gewählt
    lager_reihe    "60" leicht | "62" mittel | "63" schwer
    gehaeuse_luft  Freigang Rad -> Gehäuseinnenwand [mm]
    wand           Wandstärke [mm]
    muffe_b        Breite der Schaltmuffe [mm]; 0 = in die Lücke einpassen
    """
    gaenge = max(1, int(gaenge))
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Getriebe")

    paare = G.gangpaare(int(zaehne_summe), gaenge)
    a = G.achsabstand(modul, *paare[0][:2])
    schritt = float(breite) + float(luft)

    lager_name = LG.waehle(welle_d, lager_reihe)
    lm = LG.masse(lager_name)
    sitz_d = lm["d"]

    teile = []

    def lege_ab(shape, label, pos, drehen=True, phase=0.0):
        """Die Bauteile entstehen entlang Z, das Getriebe läuft entlang X.

        ``phase`` dreht das Teil zuerst um seine EIGENE Achse — dafür ist die
        Reihenfolge wichtig: erst um Z, dann die 90 Grad um Y.
        """
        s = shape.copy()
        if phase:
            s.rotate(Vector(0, 0, 0), Vector(0, 0, 1), float(phase))
        if drehen:
            s.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)
        s.translate(Vector(*pos))
        teile.append((label, s))

    # --- Zahnräder -------------------------------------------------------
    kopf_ein, kopf_aus = 0.0, 0.0
    for k, (z1, z2, i) in enumerate(paare):
        x = float(gehaeuse_luft) + luft / 2.0 + k * schritt
        fest, d_w1, d_a1 = zahnrad(doc, z1, modul, breite, welle_d,
                                   verzahnung, schraegwinkel,
                                   eingriffswinkel, flankenspiel)
        # Gegenlaeufig: zwei gleichsinnig schraegverzahnte Raeder auf
        # parallelen Wellen kaemmen nicht. Das Gegenrad braucht die
        # entgegengesetzte Steigungsrichtung, sonst stossen die Flanken
        # aufeinander (gemessen: 5,7 % Durchdringung bei gleichem Vorzeichen).
        los, d_w2, d_a2 = zahnrad(doc, z2, modul, breite,
                                  welle_d + 2.0 * spiel, verzahnung,
                                  -float(schraegwinkel), eingriffswinkel,
                                  flankenspiel)
        kopf_ein = max(kopf_ein, d_a1 / 2.0)
        kopf_aus = max(kopf_aus, d_a2 / 2.0)
        # Das Losrad um eine halbe Zahnteilung verdreht, sonst stossen die
        # Zaehne aufeinander statt ineinander zu greifen: ohne Phase
        # durchdringen sich Gang 1 um 11,8 % des kleineren Rades.
        lege_ab(fest, "Gang %d Festrad (z=%d)" % (k + 1, z1), (x, 0.0, 0.0))
        lege_ab(los, "Gang %d Losrad (z=%d, i=%.3f)" % (k + 1, z2, i),
                (x, a, 0.0), phase=180.0 / float(z2))

    baulaenge = schritt * gaenge + luft
    innen_l = baulaenge + 2.0 * float(gehaeuse_luft)

    # --- Wellen ----------------------------------------------------------
    sitz_l = lm["B"] + 2.0
    welle_l = innen_l + 2.0 * wand + 2.0 * (lm["B"] + 6.0)
    x0 = -(wand + lm["B"] + 6.0)
    for label, y in (("Eingangswelle", 0.0), ("Ausgangswelle", a)):
        lege_ab(_welle(welle_l, welle_d, sitz_d, sitz_l), label, (x0, y, 0.0))

    # --- Schaltmuffen zwischen je zwei Losrädern -------------------------
    # Die Muffe muss in die Lücke passen, sonst steckt sie in den Rädern:
    # mit muffe_b=10 bei luft=6 hat sie beide Nachbarn um 2 mm durchdrungen.
    platz = float(luft) - 2.0 * float(spiel)
    breite_muffe = float(muffe_b) if float(muffe_b) > 0.0 else platz
    breite_muffe = max(2.0, min(breite_muffe, platz))
    for k in range(gaenge - 1):
        x = (float(gehaeuse_luft) + luft / 2.0 + k * schritt + breite
             + (luft - breite_muffe) / 2.0)
        lege_ab(_schaltmuffe(welle_d + 2.0 * spiel, welle_d + 12.0,
                             breite_muffe),
                "Schaltmuffe %d/%d" % (k + 1, k + 2), (x, a, 0.0))

    # --- Lager auf den abgesetzten Sitzen --------------------------------
    rand = (sitz_l - lm["B"]) / 2.0
    for seite, x in (("links", x0 + rand),
                     ("rechts", x0 + welle_l - sitz_l + rand)):
        for welle, y in (("Eingang", 0.0), ("Ausgang", a)):
            for label, shp in LG.baue(lager_name, spiel=spiel, achse="x",
                                      x=x, y=y, z=0.0):
                teile.append(("%s %s %s" % (label, welle, seite), shp))

    # --- Gehäuse ---------------------------------------------------------
    for label, shp in GK.baue([(0.0, 0.0), (0.0, a)],
                              [kopf_ein, kopf_aus],
                              breite=innen_l, luft=float(gehaeuse_luft),
                              wand=wand, flansch_b=flansch_b,
                              schraube_d=schraube_d,
                              wellen_d=lm["D"] + 0.4, achse="x",
                              x0=-float(gehaeuse_luft)):
        teile.append((label, shp))

    return teile


def baue_mit_werkstoff(doc=None, **kw):
    """Wie ``baue``, legt aber ins Dokument und hinterlegt die Werkstoffe."""
    import werkstoff as W

    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Getriebe")
    teile = baue(doc=doc, **kw)
    lager, rest = [], []
    for label, shp in teile:
        o = doc.addObject("Part::Feature", "Bauteil")
        o.Shape = shp
        o.Label = label
        (lager if label[:1].isdigit() else rest).append(o)
    doc.recompute()
    meldungen = []
    if lager:
        meldungen.append(W.zuweisen(lager, "lagerstahl"))
    if rest:
        meldungen.append(W.zuweisen(rest, "stahl"))
    return lager + rest, " · ".join(meldungen)


def pruefe(teile=None, gehaeuse_luft=3.0, toleranz=0.02, **kw):
    """Misst ein gebautes Getriebe nach; liefert [(ok, Text), ...]."""
    if teile is None:
        teile = baue(gehaeuse_luft=gehaeuse_luft, **kw)
    befunde = []

    def sag(ok, text):
        befunde.append((bool(ok), text))

    raeder = [(n, s) for n, s in teile if "rad " in n.lower()]
    gehaeuse = [(n, s) for n, s in teile if n.startswith("Gehaeuse")]
    muffen = [(n, s) for n, s in teile if n.startswith("Schaltmuffe")]

    sag(len(gehaeuse) == 2, "Gehaeuse ist geteilt (%d Teile)" % len(gehaeuse))
    sag(all(s.Solids for _n, s in teile),
        "alle %d Koerper sind Solids" % len(teile))
    sag(len(muffen) >= 1, "%d Schaltmuffe(n)" % len(muffen))

    fest = [(n, s) for n, s in raeder if "Festrad" in n]
    los = [(n, s) for n, s in raeder if "Losrad" in n]
    sag(len(fest) == len(los) and fest,
        "%d Festraeder und %d Losraeder" % (len(fest), len(los)))

    if fest and los:
        greifen = 0
        for (_n1, s1), (_n2, s2) in zip(fest, los):
            b1, b2 = s1.BoundBox, s2.BoundBox
            r1 = max(b1.YLength, b1.ZLength) / 2.0
            r2 = max(b2.YLength, b2.ZLength) / 2.0
            abstand = abs((b2.YMin + b2.YMax) / 2.0 - (b1.YMin + b1.YMax) / 2.0)
            if r1 + r2 > abstand:
                greifen += 1
        sag(greifen == len(fest),
            "%d von %d Radpaaren greifen ineinander" % (greifen, len(fest)))

    # Durchdringung, relativ zum kleineren Teil
    schlimm, wo = 0.0, ""
    for i in range(len(teile)):
        bi = teile[i][1].BoundBox
        for j in range(i + 1, len(teile)):
            if not bi.intersect(teile[j][1].BoundBox):
                continue
            try:
                v = float(teile[i][1].common(teile[j][1]).Volume or 0.0)
            except Exception:  # noqa: BLE001
                v = 0.0
            kleiner = min(teile[i][1].Volume, teile[j][1].Volume)
            anteil = v / kleiner if kleiner > 0 else 0.0
            if anteil > schlimm:
                schlimm, wo = anteil, "%s / %s" % (teile[i][0], teile[j][0])
    sag(schlimm < toleranz,
        "groesste Durchdringung %.1f %% (erlaubt %.0f %%)%s"
        % (schlimm * 100, toleranz * 100, (" bei " + wo) if wo else ""))

    if gehaeuse and raeder:
        huelle = gehaeuse[0][1].fuse(gehaeuse[1][1]).BoundBox
        drin = all(huelle.XMin <= s.BoundBox.XMin
                   and huelle.XMax >= s.BoundBox.XMax
                   and huelle.YMin <= s.BoundBox.YMin
                   and huelle.YMax >= s.BoundBox.YMax
                   and huelle.ZMin <= s.BoundBox.ZMin
                   and huelle.ZMax >= s.BoundBox.ZMax
                   for _n, s in raeder)
        sag(drin, "das Gehaeuse umschliesst alle Raeder")
    return befunde


def selbsttest():
    """Baut mit den Vorgaben und prüft; wirft bei einem Befund."""
    schlecht = [t for ok, t in pruefe() if not ok]
    if schlecht:
        raise AssertionError("; ".join(schlecht))
    return "Getriebe-Selbsttest (FCGear) bestanden"
