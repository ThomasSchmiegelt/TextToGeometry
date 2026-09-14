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


def _mass(shape, reserve=20.0):
    """Eine Kantenlänge, die den Körper sicher umschließt.

    Mit einem festen 4000-mm-Klotz zu schneiden hat OCC an manchen Formen
    fehlschlagen lassen: bei einem Gehäuse aus fünf Abschnitten kamen beide
    Hälften auf derselben Seite heraus. Ein Schnittkörper in der Größe des
    Werkstücks ist numerisch gutmütiger.
    """
    try:
        b = shape.BoundBox
        return max(b.XLength, b.YLength, b.ZLength) * 2.0 + float(reserve)
    except Exception:  # noqa: BLE001
        return 4000.0


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


def _verfeinern(shape):
    """``removeSplitter()``, aber nur wenn es das Volumen nicht auffrisst.

    Gemessen an einem Gehäuse aus fünf Abschnitten: der Schnitt ergibt
    133775 mm³, nach ``removeSplitter()`` sind es 11762 — der Körper ist weg,
    ohne Fehlermeldung, und übrig bleibt der Flansch. Bei sieben Abschnitten
    derselben Bauart passiert nichts dergleichen. Die Vereinfachung ist also
    nicht verlässlich; sie ist Kosmetik und darf nichts kosten.
    """
    try:
        vorher = float(shape.Volume or 0.0)
        verfeinert = shape.removeSplitter()
        nachher = float(verfeinert.Volume or 0.0)
    except Exception:  # noqa: BLE001
        return shape
    if vorher > 0.0 and abs(nachher - vorher) > 1e-3 * vorher:
        return shape
    return verfeinert


def _steg(p1, p2, halbbreite):
    """Ein Verbindungsband zwischen zwei Achsen, als Rechteckfläche."""
    d = p2.sub(p1)
    laenge = d.Length
    if laenge < 1e-9 or halbbreite <= 0.0:
        return None
    d.normalize()
    q = Vector(-d.y, d.x, 0)
    ecken = [p1.add(Vector(q.x * halbbreite, q.y * halbbreite, 0)),
             p2.add(Vector(q.x * halbbreite, q.y * halbbreite, 0)),
             p2.sub(Vector(q.x * halbbreite, q.y * halbbreite, 0)),
             p1.sub(Vector(q.x * halbbreite, q.y * halbbreite, 0))]
    flaeche = Part.Face(Part.makePolygon(ecken + [ecken[0]]))
    # Die Umlaufrichtung entscheidet. Gemessen: mit Normale -Z liefert die
    # Vereinigung mit den Kreisen 5 Flaechen statt einer -- bei exakt gleichem
    # Flaecheninhalt. Danach nimmt max(Wires, key=Length) den falschen Umriss.
    try:
        if flaeche.normalAt(0, 0).z < 0:
            flaeche.reverse()
    except Exception:  # noqa: BLE001
        pass
    return flaeche


def _kontur(achsen, radien):
    """Eine Schnittfläche aus einem Kreis je Achse, bei Bedarf mit Steg.

    Berühren sich zwei Kreise nicht, zerfällt die Fläche — im Lagersitz sind
    es zwei Kreise von 23,5 mm bei 48 mm Achsabstand. Das blieb unbemerkt,
    weil der Aufrufer mit ``max(Wires, key=Length)`` stillschweigend einen der
    beiden nahm: um das eine Lager standen 6335 mm³ Wand, um das andere 656.
    Dann wird ein Steg eingezogen, so wie eine echte Gehäusewand die beiden
    Lageraugen verbindet.

    Vereint wird alles in EINEM ``multiFuse``. Kreise erst zu verschmelzen,
    ``removeSplitter`` zu rufen und den Steg danach anzufügen, hat die Fläche
    in fünf Stücke zerlegt.
    """
    punkte = [Vector(float(a), float(b), 0) for a, b in achsen]
    radien = [float(r) for r in radien]
    stuecke = [Part.Face(Part.Wire(Part.makeCircle(r, p)))
               for p, r in zip(punkte, radien)]
    for i in range(len(punkte) - 1):
        abstand = punkte[i].distanceToPoint(punkte[i + 1])
        if abstand < radien[i] + radien[i + 1] - 1e-6:
            continue                      # die Kreise überlappen schon
        steg = _steg(punkte[i], punkte[i + 1],
                     min(radien[i], radien[i + 1]) * 0.7)
        if steg is not None:
            stuecke.append(steg)
    f = stuecke[0] if len(stuecke) == 1 else stuecke[0].multiFuse(stuecke[1:])
    f = f.removeSplitter()
    if len(f.Faces) > 1:
        raise GehaeuseFehler(
            "Die Kontur zerfaellt in %d Teile — die Wellen liegen zu weit "
            "auseinander fuer die angegebenen Radien." % len(f.Faces))
    return f


def _abschnitt_koerper(achsen, radien, z0, z1, zuschlag=0.0,
                       radien_fest=None):
    """Ein Abschnitt als 3D-Körper: ein Zylinder je Achse, dazu der Steg.

    Bewusst aus Grundkörpern statt aus einer 2D-Kontur mit ``makeOffset2D``:
    Die Kette aus Offset, vielen Prismen und Booleschen Operationen ist in
    OCC brüchig — bei fünf Abschnitten kam ein halbes Gehäuse heraus, bei
    sieben derselben Bauart nicht. Zylinder und Quader zu vereinen ist
    verlässlich. Der Preis ist eine Kante statt einer tangentialen Rundung
    dort, wo die beiden Kreise zusammenlaufen.
    """
    hoehe = float(z1) - float(z0)
    punkte = [Vector(float(ya), float(za), float(z0)) for ya, za in achsen]
    # `radien_fest` gilt unmittelbar, ohne Wandzuschlag — damit kann ein
    # Abschnitt aussen so gross sein wie seine Nachbarn, obwohl sein
    # Hohlraum nur ein Wellendurchlass ist. Genau das ist eine Zwischenwand.
    wirksam = ([float(r) for r in radien_fest] if radien_fest is not None
               else [float(r) + float(zuschlag) for r in radien])
    stuecke = [Part.makeCylinder(r, hoehe, p)
               for p, r in zip(punkte, wirksam)]
    for i in range(len(punkte) - 1):
        r1 = wirksam[i]
        r2 = wirksam[i + 1]
        halb = min(r1, r2) * 0.7
        steg = _steg(Vector(punkte[i].x, punkte[i].y, 0),
                     Vector(punkte[i + 1].x, punkte[i + 1].y, 0), halb)
        if steg is None:
            continue
        k = steg.extrude(Vector(0, 0, hoehe))
        k.translate(Vector(0, 0, float(z0)))
        stuecke.append(k)
    if len(stuecke) == 1:
        return stuecke[0]
    return stuecke[0].multiFuse(stuecke[1:])


def baue(achsen, radien=None, abschnitte=None, breite=60.0, luft=3.0,
         wand=4.0, flansch_b=12.0, schraube_d=6.0, welle_d=0.0, x0=0.0,
         achse="x"):
    """Gehäuseober- und -unterteil als (Bezeichnung, Shape)-Paare.

    achsen      Liste von (a, b) der Wellenachsen in der Querschnittsebene
    abschnitte  Liste von (laenge, [r_innen je Achse]) in Wellenrichtung.
                Die Radien sind ENDGÜLTIGE Innenradien, Freigang schon darin.
                Damit folgt die Wand jedem Radpaar einzeln — mit nur einem
                Abschnitt kämen zwei Zylinder heraus, und genau so sah das
                erste Gehäuse aus.
    radien      Altform: ein Radius je Achse, ergibt EINEN Abschnitt der
                Länge ``breite``; ``luft`` wird dann noch addiert.
    wand        Wandstärke [mm]
    flansch_b   Breite des Flansches am Trennstoß [mm]
    schraube_d  Durchgangsbohrung im Flansch [mm]
    welle_d     Durchlass für die Welle in den Stirnwänden [mm]; 0 = keiner
    achse       Richtung der Wellen: "x" (Vorgabe), "y" oder "z"

    Der Innenraum beginnt bei z = 0 und endet bei der Summe der Abschnitte;
    die Stirnwände liegen davor und dahinter.
    """
    wand = float(wand)
    flansch_b, schraube_d = float(flansch_b), float(schraube_d)

    if abschnitte is None:
        if radien is None:
            raise GehaeuseFehler("Weder abschnitte noch radien angegeben.")
        abschnitte = [(float(breite),
                       [float(r) + float(luft) for r in radien], None)]
    # Ein Abschnitt ist (laenge, innenradien) oder, fuer eine Zwischenwand,
    # (laenge, innenradien, aussenradien).
    normiert = []
    for eintrag in abschnitte:
        if len(eintrag) == 3:
            l, rs, aussen_rs = eintrag
            aussen_rs = [float(r) for r in aussen_rs]
        else:
            l, rs = eintrag
            aussen_rs = None
        normiert.append((float(l), [float(r) for r in rs], aussen_rs))
    abschnitte = normiert
    if any(len(rs) != len(achsen) for _l, rs, _a in abschnitte):
        raise GehaeuseFehler("Zu jeder Achse gehört ein Radius je Abschnitt.")

    laenge = sum(l for l, _rs, _a in abschnitte)
    gesamt_h = laenge + 2.0 * wand

    aussen_teile, innen_teile = [], []
    z = 0.0
    for k, (l, rs, aussen_rs) in enumerate(abschnitte):
        von = z - (wand if k == 0 else 0.0)
        bis = z + l + (wand if k == len(abschnitte) - 1 else 0.0)
        aussen_teile.append(_abschnitt_koerper(achsen, rs, von, bis, wand,
                                               radien_fest=aussen_rs))
        innen_teile.append(_abschnitt_koerper(achsen, rs, z, z + l))
        z += l

    aussen = (aussen_teile[0] if len(aussen_teile) == 1
              else aussen_teile[0].multiFuse(aussen_teile[1:]))
    hohlraum = (innen_teile[0] if len(innen_teile) == 1
                else innen_teile[0].multiFuse(innen_teile[1:]))
    koerper = aussen.cut(hohlraum)

    # Flansch: ein Kragen an der Trennebene, über die Kontur hinaus.
    p0, d, n = trennebene(achsen)
    groesste = [max((a[i] - wand) if a is not None else rs[i]
                    for _l, rs, a in abschnitte) for i in range(len(achsen))]
    kragen = _abschnitt_koerper(achsen, groesste, -wand, laenge + wand,
                                wand + flansch_b)
    scheibe = _block(p0, d, -wand - 1.0, gesamt_h + 2.0, dicke=flansch_b,
                     gross=_mass(kragen))
    koerper = koerper.fuse(kragen.common(scheibe).cut(hohlraum))

    # Wellendurchlass ERST JETZT, nach dem Flansch: vorher hat der Kragen die
    # eben geschnittenen Loecher wieder zugesetzt, und die Welle steckte in
    # der Stirnwand (2,7 % Durchdringung). Der Innenraum ist bereits hohl, der
    # Schnitt trifft also nur die Stirnwaende — und bildet zusammen mit der
    # Aufweitung des ersten Abschnitts den Lagersitz mit Schulter.
    if float(welle_d) > 0.0:
        for (ya, za) in achsen:
            loch = Part.makeCylinder(float(welle_d) / 2.0, gesamt_h + 2.0,
                                     Vector(float(ya), float(za), -wand - 1.0))
            koerper = koerper.cut(loch)

    # Die Ohren enden an den tatsächlichen Enden der Kontur, nicht symmetrisch
    # um die erste Achse — sonst schneidet eine Bohrung ins Leere.
    ecken = koerper.BoundBox
    lagen = [Vector(pt[0], pt[1], 0).sub(p0).dot(d)
             for pt in ((ecken.XMin, ecken.YMin), (ecken.XMin, ecken.YMax),
                        (ecken.XMax, ecken.YMin), (ecken.XMax, ecken.YMax))]
    ohren = (min(lagen) + flansch_b / 2.0, max(lagen) - flansch_b / 2.0)

    # Vector.multiply() skaliert IN PLACE -- jede Richtung frisch bauen.
    gebohrt = 0
    for zb in bohrpunkte(gesamt_h, schraube_d):
        for lage in ohren:
            laengs = Vector(d.x, d.y, 0)
            laengs.multiply(lage)
            zurueck = Vector(n.x, n.y, 0)
            zurueck.multiply(-2.0 * flansch_b)
            mitte = p0.add(laengs)
            start = Vector(mitte.x, mitte.y, zb - wand).add(zurueck)
            bohrung = Part.makeCylinder(schraube_d / 2.0, 4.0 * flansch_b,
                                        start, Vector(n.x, n.y, 0))
            try:
                vorher = koerper.Volume
                geschnitten = koerper.cut(bohrung)
                if vorher - geschnitten.Volume > 1.0:
                    koerper = geschnitten
                    gebohrt += 1
            except Exception:  # noqa: BLE001
                continue
    if gebohrt < 2:
        raise GehaeuseFehler(
            "Nur %d Flanschbohrungen haben Material getroffen — der Flansch "
            "ist zu schmal (flansch_b=%.1f) fuer Schrauben von %.1f mm."
            % (gebohrt, flansch_b, schraube_d))

    # Teilen in der Ebene durch die Wellen — mit ZWEI Schnitten, nicht mit
    # Schnitt und Durchschnitt: `common()` gegen den Halbraum lieferte an
    # manchen Formen einen leeren Koerper, waehrend `cut()` sauber arbeitete.
    weite = _mass(koerper)
    unten = koerper.cut(_block(p0, d, -wand - 1.0, gesamt_h + 2.0,
                               gross=weite))
    oben = koerper.cut(_block(p0, Vector(-d.x, -d.y, 0), -wand - 1.0,
                              gesamt_h + 2.0, gross=weite))
    summe = float(oben.Volume or 0.0) + float(unten.Volume or 0.0)
    if abs(summe - float(koerper.Volume or 0.0)) > 0.02 * float(
            koerper.Volume or 1.0):
        raise GehaeuseFehler(
            "Die Teilung ist fehlgeschlagen: %.0f + %.0f mm^3 ergeben nicht "
            "die %.0f mm^3 des ganzen Gehaeuses."
            % (oben.Volume, unten.Volume, koerper.Volume))

    dreh = {"x": (Vector(0, 1, 0), 90.0), "y": (Vector(1, 0, 0), -90.0)}.get(
        str(achse).lower())
    aus = []
    for label, shp in (("Gehaeuse Oberteil", oben),
                       ("Gehaeuse Unterteil", unten)):
        sh = shp.copy()
        if dreh is not None:
            sh.rotate(Vector(0, 0, 0), dreh[0], dreh[1])
        sh.translate(Vector(float(x0), 0, 0))
        aus.append((label, sh))
    return aus


def selbsttest():
    """Prüft die Geometriekette an zwei Wellen mit 48 mm Achsabstand."""
    achsen = [(0.0, 0.0), (0.0, 48.0)]
    luft, wand = 3.0, 4.0

    innen = innenkontur(achsen, [22.0, 30.0], luft)
    if len(innen.Wires) != 1:
        raise AssertionError("Innenkontur ergab %d Umrisse statt einem"
                             % len(innen.Wires))
    aussen = _aussenkontur(innen, wand)
    if aussen.Length <= innen.Wires[0].Length:
        raise AssertionError("Aussenkontur ist nicht laenger als die innere")

    # Gestuft: Lagersitz, zwei ungleiche Radpaare, Lagersitz.
    sitz_r = 23.5                      # Lager 6204, halber Aussendurchmesser
    abschnitte = [(14.0, [sitz_r, sitz_r]),
                  (20.0, [17.0, 41.0]),
                  (20.0, [25.0, 33.0]),
                  (14.0, [sitz_r, sitz_r])]
    teile = baue(achsen, abschnitte=abschnitte, wand=wand, welle_d=20.4,
                 achse="z")
    if len(teile) != 2:
        raise AssertionError("erwartet Ober- und Unterteil, bekam %d"
                             % len(teile))
    for name, sh in teile:
        if not sh.Solids:
            raise AssertionError("%s ist kein Solid" % name)
    oben, unten = teile[0][1], teile[1][1]
    if oben.common(unten).Volume > 1.0:
        raise AssertionError("Ober- und Unterteil durchdringen sich")
    ganz = oben.fuse(unten)
    if abs(oben.Volume - unten.Volume) > 0.02 * ganz.Volume:
        raise AssertionError("ungleich geteilt: %.0f gegen %.0f mm^3"
                             % (oben.Volume, unten.Volume))

    # Der Querschnitt muss sich ändern — sonst sind es wieder zwei Zylinder.
    def breite_bei(z):
        """Quer zur Achsverbindung gemessen — längs davon liegt der Flansch,
        und dessen Breite ist konstant, sagt also nichts über die Wand aus."""
        ebene = Part.makeBox(600.0, 600.0, 0.5, Vector(-300.0, -300.0, z))
        schnitt = ganz.common(ebene)
        return schnitt.BoundBox.XLength if schnitt.Solids else 0.0

    eng, weit = breite_bei(5.0), breite_bei(25.0)
    if abs(weit - eng) < 2.0:
        raise AssertionError(
            "Querschnitt bleibt gleich (%.1f gegen %.1f mm) — die Wand folgt "
            "den Raedern nicht" % (eng, weit))

    # Im Lagersitz muss Material um das Lager stehen.
    lager = Part.makeCylinder(sitz_r, 14.0, Vector(0, 48.0, 0.0))
    if ganz.common(lager).Volume > 1.0:
        raise AssertionError("der Lagersitz ist zu eng fuer das Lager")
    huelle = Part.makeCylinder(sitz_r + wand - 0.5, 12.0,
                               Vector(0, 48.0, 1.0))
    if ganz.common(huelle).Volume < 100.0:
        raise AssertionError("um den Lagersitz steht kein Material")

    # Die Welle muss durch die Stirnwand passen.
    welle = Part.makeCylinder(10.0, 300.0, Vector(0, 48.0, -100.0))
    if ganz.common(welle).Volume > 1.0:
        raise AssertionError("die Welle kommt nicht durch die Stirnwand")

    return ("Gehaeuse-Selbsttest bestanden (%.0f + %.0f mm^3, Querschnitt "
            "%.0f mm am Lager gegen %.0f mm am Rad)"
            % (oben.Volume, unten.Volume, eng, weit))
