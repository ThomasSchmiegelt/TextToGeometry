# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Getriebegehäuse, dessen Innenwand der Kontur der Zahnräder folgt.

Ein Quader um einen Radsatz ist in den Ecken voller Luft. Ein echtes
Getriebegehäuse legt sich um die Räder — bei zwei Wellen ergibt das die
bekannte Doppel-Nierenform. Genau die entsteht hier:

    Kreisfläche je Radachse (r_kopf + Freigang)
      -> fuse + removeSplitter   -> ein einziger Umrissdraht
      -> Wires[0].makeOffset2D(wand) -> Außenkontur
      -> Face(außen).cut(innen)  -> Ringfläche = die Wand
      -> extrude(breite)         -> Wandkörper
      -> common/cut gegen einen Halbraum -> Ober- und Unterteil

Jeder dieser Schritte wurde in FreeCAD 1.1 nachgemessen, bevor er hier
aufgeschrieben wurde — ``makeOffset2D`` auf der Vereinigung zweier Kreise
liefert zuverlässig genau einen geschlossenen Draht.

Geteilt wird in der Ebene **durch beide Wellenachsen** — nicht in der Mitte
zwischen ihnen: dort liegt die Trennung schief, halbiert die Lagersitze nicht
und teilt ein Gehäuse mit ungleich großen Rädern 3:1. In dieser Ebene liegt
auch der Flansch; er läuft in Wellenrichtung, und die Durchgangsbohrungen
sitzen an seinen beiden Ohren, über die Länge verteilt.
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector


class GehaeuseFehler(Exception):
    pass


def innenkontur(achsen, radien, luft=3.0):
    """Die Innenkontur als Fläche: ein Kreis je Radachse, verschmolzen.

    ``achsen`` sind (y, z)-Paare in der Radebene, ``radien`` die Kopfradien.
    """
    if len(achsen) != len(radien) or not achsen:
        raise GehaeuseFehler("Zu jeder Achse gehört ein Radius.")
    flaechen = []
    for (y, z), r in zip(achsen, radien):
        kreis = Part.makeCircle(float(r) + float(luft), Vector(float(y),
                                                              float(z), 0))
        flaechen.append(Part.Face(Part.Wire(kreis)))
    innen = flaechen[0]
    for f in flaechen[1:]:
        innen = innen.fuse(f)
    innen = innen.removeSplitter()
    if not innen.Wires:
        raise GehaeuseFehler("Die Innenkontur hat keinen Umriss ergeben.")
    return innen


def _aussenkontur(innen, wand):
    """Der Umriss nach außen versetzt — die Außenwand."""
    umriss = max(innen.Wires, key=lambda w: w.Length)
    return umriss.makeOffset2D(float(wand))


def trennebene(achsen):
    """Punkt, Richtung und Normale der Ebene DURCH die Wellenachsen.

    Nicht die Mitte zwischen den Achsen — die liegt schief und teilt ein
    Gehäuse mit ungleich großen Rädern 3:1. Ein geteiltes Gehäuse trennt in
    der Ebene, die beide Wellen enthält: dort sind die Lagersitze halbiert und
    die Räder lassen sich einlegen.
    """
    p1 = Vector(float(achsen[0][0]), float(achsen[0][1]), 0)
    d = Vector(1, 0, 0)
    if len(achsen) > 1:
        p2 = Vector(float(achsen[-1][0]), float(achsen[-1][1]), 0)
        richtung = p2.sub(p1)
        if richtung.Length > 1e-9:
            d = richtung
    d.normalize()
    return p1, d, Vector(-d.y, d.x, 0)


def _block(punkt, d, z0, hoehe, dicke=None, gross=4000.0):
    """Halbraum (``dicke=None``) oder Scheibe an der Trennebene."""
    if dicke is None:
        kasten = Part.makeBox(gross, gross, hoehe,
                              Vector(-gross / 2.0, 0.0, z0))
    else:
        kasten = Part.makeBox(gross, float(dicke), hoehe,
                              Vector(-gross / 2.0, -float(dicke) / 2.0, z0))
    kasten.rotate(Vector(0, 0, 0), Vector(0, 0, 1),
                  math.degrees(math.atan2(d.y, d.x)))
    kasten.translate(Vector(punkt.x, punkt.y, 0))
    return kasten


def bohrpunkte(laenge, schraube_d, mindestens=2):
    """Gleichmäßig verteilte Positionen längs des Flansches.

    Der Flansch eines geteilten Gehäuses läuft in Wellenrichtung, und dort
    sitzen auch die Schrauben — nicht rundum die Radkontur. Die Teilung ist
    etwa das Achtfache des Schraubendurchmessers.
    """
    teilung = max(8.0 * float(schraube_d), 20.0)
    anzahl = max(int(mindestens), int(round(float(laenge) / teilung)))
    schritt = float(laenge) / anzahl
    return [schritt * (k + 0.5) for k in range(anzahl)]


def baue(achsen, radien, breite=60.0, luft=3.0, wand=4.0, flansch_b=12.0,
         schraube_d=6.0, wellen_d=0.0, x0=0.0, achse="x"):
    """Gehäuseober- und -unterteil als (Bezeichnung, Shape)-Paare.

    achsen      Liste von (y, z) der Radachsen in der Radebene [mm]
    radien      Kopfradien der größten Räder je Achse [mm]
    breite      axiale Länge des Innenraums [mm]
    luft        Freigang Rad -> Innenwand [mm]
    wand        Wandstärke [mm]
    flansch_b   Breite des Flansches am Trennstoß [mm]
    schraube_d  Durchgangsbohrung im Flansch [mm]
    wellen_d    Durchbruch in den Stirnwänden je Achse [mm]; 0 = keiner.
                Sinnvoll ist der Lageraußendurchmesser — dann sitzt das Lager
                im Gehäuse, und die Welle steckt nicht in der Wand.
    achse       Richtung der Wellen: "x" (Vorgabe), "y" oder "z"
    """
    breite, luft, wand = float(breite), float(luft), float(wand)
    flansch_b, schraube_d = float(flansch_b), float(schraube_d)

    innen = innenkontur(achsen, radien, luft)
    aussen_w = _aussenkontur(innen, wand)
    aussen_f = Part.Face(aussen_w)

    # Die Wand ist der Ring zwischen außen und innen, plus zwei Stirnwände.
    ring = aussen_f.cut(innen)
    mantel = ring.extrude(Vector(0, 0, breite + 2.0 * wand))
    stirn_a = aussen_f.extrude(Vector(0, 0, wand))
    stirn_b = aussen_f.copy()
    stirn_b.translate(Vector(0, 0, breite + wand))
    stirn_b = stirn_b.extrude(Vector(0, 0, wand))
    koerper = mantel.fuse(stirn_a).fuse(stirn_b).removeSplitter()

    # Trennebene: die Ebene durch beide Wellenachsen.
    p0, d, n = trennebene(achsen)
    gesamt_h = breite + 2.0 * wand

    # Flansch: eine Scheibe an der Trennebene, seitlich über die Kontur hinaus.
    flansch_w = aussen_w.makeOffset2D(flansch_b)
    flansch = Part.Face(flansch_w).cut(innen)
    scheibe = _block(p0, d, 0.0, gesamt_h, dicke=flansch_b)
    koerper = koerper.fuse(
        flansch.extrude(Vector(0, 0, gesamt_h)).common(scheibe))
    koerper = koerper.removeSplitter()

    # Wo enden die Ohren? An den tatsächlichen Enden der Kontur, nicht
    # symmetrisch um die erste Achse -- bei ungleich großen Rädern liegt die
    # eine Bohrung sonst im Leeren und schneidet nichts.
    lagen = [pt.sub(p0).dot(d) for pt in aussen_w.discretize(Number=96)]
    ohren = (min(lagen) - flansch_b / 2.0, max(lagen) + flansch_b / 2.0)

    # Durchgangsbohrungen: längs der Welle verteilt, auf beiden Ohren.
    # Vector.multiply() skaliert IN PLACE -- jede Richtung frisch bauen, sonst
    # ist sie nach der ersten Bohrung 2*flansch_b lang.
    gebohrt = 0
    for z in bohrpunkte(gesamt_h, schraube_d):
        for lage in ohren:
            laengs = Vector(d.x, d.y, 0)
            laengs.multiply(lage)
            zurueck = Vector(n.x, n.y, 0)
            zurueck.multiply(-2.0 * flansch_b)
            mitte = p0.add(laengs)
            start = Vector(mitte.x, mitte.y, z).add(zurueck)
            bohrung = Part.makeCylinder(schraube_d / 2.0, 4.0 * flansch_b,
                                        start, Vector(n.x, n.y, 0))
            try:
                vorher = koerper.Volume
                geschnitten = koerper.cut(bohrung)
                if vorher - geschnitten.Volume > 1.0:
                    koerper = geschnitten
                    gebohrt += 1
            except Exception:  # noqa: BLE001 - eine Bohrung weniger ist kein Abbruch
                continue

    # Wellendurchbrüche in den Stirnwänden — der Innenraum ist ohnehin hohl,
    # der Schnitt trifft also nur die beiden Stirnwände und bildet zugleich
    # den Lagersitz.
    if float(wellen_d) > 0.0:
        for (ya, za) in achsen:
            durchbruch = Part.makeCylinder(
                float(wellen_d) / 2.0, gesamt_h + 2.0,
                Vector(float(ya), float(za), -1.0))
            try:
                koerper = koerper.cut(durchbruch)
            except Exception:  # noqa: BLE001
                continue

    # Teilen in der Ebene durch die Wellen.
    halbraum = _block(p0, d, -1.0, gesamt_h + 2.0)
    oben = koerper.common(halbraum).removeSplitter()
    unten = koerper.cut(halbraum).removeSplitter()

    if gebohrt < 2:
        raise GehaeuseFehler(
            "Nur %d Flanschbohrungen haben Material getroffen — der Flansch "
            "ist zu schmal (flansch_b=%.1f) fuer Schrauben von %.1f mm."
            % (gebohrt, flansch_b, schraube_d))

    teile = [("Gehaeuse Oberteil", oben), ("Gehaeuse Unterteil", unten)]

    dreh = {"x": (Vector(0, 1, 0), 90.0), "y": (Vector(1, 0, 0), -90.0)}.get(
        str(achse).lower())
    aus = []
    for label, shp in teile:
        s = shp.copy()
        s.translate(Vector(0, 0, -wand))
        if dreh is not None:
            s.rotate(Vector(0, 0, 0), dreh[0], dreh[1])
        s.translate(Vector(float(x0), 0, 0))
        aus.append((label, s))
    return aus


def selbsttest():
    """Prüft die Geometriekette an zwei Wellen mit 48 mm Achsabstand."""
    achsen = [(0.0, 0.0), (0.0, 48.0)]
    radien = [22.0, 30.0]
    luft, wand, breite = 3.0, 4.0, 60.0

    innen = innenkontur(achsen, radien, luft)
    if len(innen.Wires) != 1:
        raise AssertionError("Innenkontur ergab %d Umrisse statt einem"
                             % len(innen.Wires))
    aussen = _aussenkontur(innen, wand)
    if aussen.Length <= innen.Wires[0].Length:
        raise AssertionError("Aussenkontur ist nicht laenger als die innere")

    # Ungedreht geprueft (achse="z"): die Kontur liegt dann in der XY-Ebene,
    # die Wellen laufen entlang Z. Gedreht wird nur zum Schluss, das ist eine
    # Starrkoerperbewegung und aendert nichts an der Passung.
    teile = baue(achsen, radien, breite=breite, luft=luft, wand=wand,
                 achse="z")
    if len(teile) != 2:
        raise AssertionError("erwartet Ober- und Unterteil, bekam %d"
                             % len(teile))
    for name, s in teile:
        if not s.Solids:
            raise AssertionError("%s ist kein Solid" % name)
    oben, unten = teile[0][1], teile[1][1]
    if oben.common(unten).Volume > 1.0:
        raise AssertionError("Ober- und Unterteil durchdringen sich")

    ganz = oben.fuse(unten)
    bb = ganz.BoundBox
    # Gleich groß geteilt: die Ebene durch beide Achsen halbiert das Gehäuse.
    if abs(oben.Volume - unten.Volume) > 0.02 * ganz.Volume:
        raise AssertionError("ungleich geteilt: %.0f gegen %.0f mm^3"
                             % (oben.Volume, unten.Volume))
    if bb.YLength < 2 * max(radien) + 2 * luft:
        raise AssertionError("Gehaeuse ist schmaler als der Radsatz")
    # Das groesste Rad sitzt auf der zweiten Achse und muss frei stehen.
    rad = Part.makeCylinder(radien[1], 10.0, Vector(0.0, 48.0, 5.0))
    durch = ganz.common(rad).Volume
    if durch > 1.0:
        raise AssertionError("das groesste Rad steckt in der Wand (%.0f mm^3)"
                             % durch)
    return ("Gehaeuse-Selbsttest bestanden (%.0f + %.0f mm^3, Huelle "
            "%.0f x %.0f x %.0f)" % (oben.Volume, unten.Volume,
                                     bb.XLength, bb.YLength, bb.ZLength))
