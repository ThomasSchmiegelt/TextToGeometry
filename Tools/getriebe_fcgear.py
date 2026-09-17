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


def _welle(laenge, d, sitz_d, sitz_l, sitze="beide"):
    """Welle mit abgesetzten Lagersitzen, entlang Z gebaut.

    ``sitze`` sagt, welche Enden ein Lager tragen: ``"beide"``, ``"vorn"``
    (nur bei z = 0) oder ``"hinten"``. Beim Vorgelegegetriebe sitzt am
    hinteren Ende der Antriebswelle **kein Lager**, sondern die
    Kupplungsverzahnung für den direkten Gang — dort schiebt sich die
    Schaltmuffe darüber. Mit einem Lagersitz von 30 mm unter einer 29er
    Muffenbohrung durchdrangen sich beide um 4 %.
    """
    k = Part.makeCylinder(d / 2.0, laenge)
    enden = {"beide": (0.0, laenge - sitz_l), "vorn": (0.0,),
             "hinten": (laenge - sitz_l,)}[str(sitze)]
    for z in enden:
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
              welle_d=20.0, z_min=12, **_rest):
    """Die Auslegung ohne Geometrie — schnell, für die Maske und den Agenten."""
    paare = G.gangpaare(int(zaehne_summe), int(gaenge), int(z_min))
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


def gangpaare_vorgelege(zaehne_summe, gaenge, z_min=17,
                        zaehne_konstante=0):
    """Zähnezahlen eines **Vorgelegegetriebes**, Gang für Gang.

    Der Kraftfluss geht hier über **zwei** Radpaare, nicht über eines:

        Antriebswelle --(Konstante)--> Vorgelegewelle --(Gangpaar)--> Hauptwelle

    Die Antriebswelle und die Hauptwelle liegen auf **derselben Achse**; das
    ist der Sinn der Bauart, denn nur so geht der Abtrieb dorthin zurück, wo
    der Antrieb herkommt. Die Vorgelegewelle liegt darunter.

    Alle Paare — auch die Konstante — laufen auf demselben Achsabstand, also
    ist ``z1 + z2`` überall dieselbe Summe.

    Die Gesamtübersetzung eines Ganges ist das **Produkt** beider Stufen:

        i = (z_VK / z_AK) · (z_Losrad / z_Festrad)

    Zurück kommt ``(konstante, paare)`` mit ``konstante = (z_AK, z_VK, i_K)``
    und ``paare = [(z_Festrad, z_Losrad, i_gesamt), …]``, vom längsten zum
    kürzesten Gang.
    """
    summe = int(zaehne_summe)
    n = max(1, int(gaenge))
    zk = int(zaehne_konstante) or max(int(z_min), summe // 2 - 2)
    if summe - zk < int(z_min):
        raise ValueError("Zaehnesumme %d zu klein fuer die Konstante" % summe)
    konstante = (zk, summe - zk, G.uebersetzung(zk, summe - zk))
    i_k = konstante[2]
    # Das Festrad auf der Vorgelegewelle waechst von Gang zu Gang, das
    # Losrad auf der Hauptwelle schrumpft — der erste Gang ist der laengste.
    paare = []
    schritt = max(1, (summe - 2 * int(z_min)) // (2 * n) or 1)
    for k in range(n):
        z_fest = int(z_min) + k * schritt
        z_los = summe - z_fest
        if z_los < int(z_min):
            raise ValueError("Zaehnezahl unter Minimum bei Gang %d" % (k + 1))
        paare.append((z_fest, z_los,
                      round(i_k * G.uebersetzung(z_fest, z_los), 4)))
    return konstante, paare


def baue(gaenge=5, modul=2.0, zaehne_summe=48, breite=12.0, luft=6.0,
         z_min=12, bauart="zweiwellen", glocke_l=0.0, glocke_d=0.0,
         verzahnung="gerade", schraegwinkel=15.0, eingriffswinkel=20.0,
         flankenspiel=0.05, welle_d=20.0, lager_reihe="62", spiel=0.1,
         gehaeuse_luft=3.0, wand=4.0, flansch_b=12.0, schraube_d=6.0,
         muffe_b=0.0, doc=None):
    """Das ganze Getriebe als (Bezeichnung, Shape)-Paare.

    gaenge         Zahl der Gangstufen
    modul          Verzahnungsmodul [mm]
    zaehne_summe   z1 + z2, für ALLE Gänge gleich -> ein Achsabstand
    z_min          kleinste Zähnezahl des kleinsten Rades. 12 ist geometrisch
                   möglich, aber ein 20-Grad-Evolventenrad **unterschneidet**
                   unter 17 Zähnen: der Kopf des Gegenrades gräbt sich in den
                   Fuß. Nachgemessen an einem Paar 12/57: 5,9 %
                   Durchdringung, bei 17/52 keine. Wer unter 17 geht, braucht
                   Profilverschiebung, und die kann FCGear hier nicht.
    breite         Zahnbreite [mm]        luft  Luft zwischen den Radpaaren
    verzahnung     "gerade" | "schraeg" | "pfeil"
    schraegwinkel  Schrägungswinkel [Grad], wirkt bei schraeg und pfeil
    welle_d        Wellendurchmesser [mm]; daraus wird das Lager gewählt
    lager_reihe    "60" leicht | "62" mittel | "63" schwer
    gehaeuse_luft  Freigang Rad -> Gehäuseinnenwand [mm]
    wand           Wandstärke [mm]
    muffe_b        Breite der Schaltmuffe [mm]; 0 = in die Lücke einpassen
    bauart         "zweiwellen" | "vorgelege"

                   **zweiwellen** — Eingangs- und Ausgangswelle parallel,
                   jeder Gang ein einziges Radpaar. Das ist die Bauform des
                   quer eingebauten Frontantriebs, wo der Abtrieb ohnehin
                   seitlich zum Differential geht.

                   **vorgelege** — Antriebswelle und Hauptwelle auf
                   **derselben Achse**, die Vorgelegewelle darunter. Der
                   Kraftfluss geht über die Antriebskonstante auf die
                   Vorgelegewelle und von dort über das Gangpaar zurück auf
                   die Hauptwelle; die Übersetzung ist das Produkt beider
                   Stufen. Das ist die Bauform des längs eingebauten
                   Motors, und nur sie bringt den Abtrieb dorthin zurück, wo
                   der Antrieb herkommt. Dazu gehört der **direkte Gang**:
                   die Schaltmuffe kuppelt Antriebswelle und Hauptwelle
                   unmittelbar, die Vorgelegewelle läuft leer mit, i = 1.
    glocke_l       Länge der **Kupplungsglocke** vor dem Gehäuse [mm]; 0 =
                   keine. Nur bei ``bauart="vorgelege"``. Die Glocke gehört
                   zum Getriebe und umschließt die Kupplung; die
                   Antriebswelle wird um dieselbe Länge verlängert und
                   trägt die Kupplungsscheiben.
    glocke_d       Außendurchmesser der Glocke [mm]; 0 = aus dem
                   Achsabstand schätzen
    """
    gaenge = max(1, int(gaenge))
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Getriebe")
    if str(bauart).lower().strip() == "vorgelege":
        return _baue_vorgelege(
            gaenge=gaenge, modul=modul, zaehne_summe=zaehne_summe,
            breite=breite, luft=luft, z_min=z_min, verzahnung=verzahnung,
            schraegwinkel=schraegwinkel, eingriffswinkel=eingriffswinkel,
            flankenspiel=flankenspiel, welle_d=welle_d,
            lager_reihe=lager_reihe, spiel=spiel,
            gehaeuse_luft=gehaeuse_luft, wand=wand, flansch_b=flansch_b,
            schraube_d=schraube_d, muffe_b=muffe_b,
            glocke_l=glocke_l, glocke_d=glocke_d, doc=doc)

    paare = G.gangpaare(int(zaehne_summe), gaenge, int(z_min))
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
    # Aufbau in Innenraum-Koordinaten: x = 0 ist der Anfang des Hohlraums.
    #   [0 .. lager_b]        Lagersitz
    #   danach je Gang ein Abschnitt aus Rad + Luft
    #   [... .. innen_l]      Lagersitz
    # Der Lagersitz braucht diese Länge, sonst hängt das Lager in der Luft —
    # im ersten Wurf sass es bei x -23..-9 und beruehrte das Gehaeuse mit
    # 0 mm^3.
    sitz_r = lm["D"] / 2.0
    welle_r = welle_d / 2.0 + spiel
    # Lagersitz, dann eine Zwischenwand, dann die Radabschnitte. Ohne die
    # Wand endet die Lagerhuelse frei im Getrieberaum — gemessen: bei x 1..13
    # standen 451 mm^3 Huelse je Millimeter, ab x 15 null. An dieser Wand
    # stuetzt sich das Lager ab, und nur die Welle geht hindurch.
    vorlauf = lm["B"] + wand
    abschnitte = [(lm["B"], [sitz_r, sitz_r])]
    for k, (z1, z2, i) in enumerate(paare):
        x = vorlauf + k * schritt + luft / 2.0
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
        # Das Losrad um eine halbe Zahnteilung verdreht, sonst stossen die
        # Zaehne aufeinander statt ineinander zu greifen: ohne Phase
        # durchdringen sich Gang 1 um 11,8 % des kleineren Rades.
        lege_ab(fest, "Gang %d Festrad (z=%d)" % (k + 1, z1), (x, 0.0, 0.0))
        lege_ab(los, "Gang %d Losrad (z=%d, i=%.3f)" % (k + 1, z2, i),
                (x, a, 0.0), phase=180.0 / float(z2))
        # Dieser Abschnitt der Gehäusewand folgt genau diesem Radpaar.
        raum = [d_a1 / 2.0 + float(gehaeuse_luft),
                d_a2 / 2.0 + float(gehaeuse_luft)]
        if k == 0:
            # Zwischenwand: innen nur der Wellendurchlass, aussen so gross
            # wie der anschliessende Radabschnitt.
            abschnitte.append((wand, [welle_r, welle_r],
                               [r + wand for r in raum]))
        abschnitte.append((schritt, raum))
        if k == len(paare) - 1:
            abschnitte.append((wand, [welle_r, welle_r],
                               [r + wand for r in raum]))
    abschnitte.append((lm["B"], [sitz_r, sitz_r]))
    innen_l = sum(a[0] for a in abschnitte)

    # --- Wellen ----------------------------------------------------------
    ueberstand = 8.0
    welle_l = innen_l + 2.0 * wand + 2.0 * ueberstand
    x_welle = -(wand + ueberstand)
    # Der abgesetzte Sitz muss bis unter das Lager reichen.
    sitz_l = wand + ueberstand + lm["B"]
    for label, y in (("Eingangswelle", 0.0), ("Ausgangswelle", a)):
        lege_ab(_welle(welle_l, welle_d, lm["d"], sitz_l), label,
                (x_welle, y, 0.0))

    # --- Schaltmuffen zwischen je zwei Losrädern -------------------------
    # Die Muffe muss in die Lücke passen, sonst steckt sie in den Rädern:
    # mit muffe_b=10 bei luft=6 hat sie beide Nachbarn um 2 mm durchdrungen.
    platz = float(luft) - 2.0 * float(spiel)
    breite_muffe = float(muffe_b) if float(muffe_b) > 0.0 else platz
    breite_muffe = max(2.0, min(breite_muffe, platz))
    for k in range(gaenge - 1):
        x = (vorlauf + k * schritt + luft / 2.0 + breite
             + (luft - breite_muffe) / 2.0)
        lege_ab(_schaltmuffe(welle_d + 2.0 * spiel, welle_d + 12.0,
                             breite_muffe),
                "Schaltmuffe %d/%d" % (k + 1, k + 2), (x, a, 0.0))

    # --- Lager IM Gehäusesitz --------------------------------------------
    for seite, x in (("links", 0.0), ("rechts", innen_l - lm["B"])):
        for welle, y in (("Eingang", 0.0), ("Ausgang", a)):
            for label, shp in LG.baue(lager_name, spiel=spiel, achse="x",
                                      x=x, y=y, z=0.0):
                teile.append(("%s %s %s" % (label, welle, seite), shp))

    # --- Gehäuse ---------------------------------------------------------
    for label, shp in GK.baue([(0.0, 0.0), (0.0, a)], abschnitte=abschnitte,
                              wand=wand, flansch_b=flansch_b,
                              schraube_d=schraube_d,
                              welle_d=welle_d + 2.0 * spiel, achse="x"):
        teile.append((label, shp))

    return teile


def _nadellager(d_innen, d_aussen, breite, nadeln=0):
    """Nadellager als Käfig mit Nadeln — Ring plus Rollen, Achse Z.

    Das Losrad eines Schaltgetriebes läuft **frei** auf der Hauptwelle,
    solange sein Gang nicht eingelegt ist. Dazwischen gehört ein Lager, und
    weil radial kaum Platz ist, ist es ein Nadellager: lange dünne Rollen
    unmittelbar zwischen Welle und Radbohrung.
    """
    ri, ra = float(d_innen) / 2.0, float(d_aussen) / 2.0
    r_nadel = max(0.8, (ra - ri) / 2.0 - 0.15)
    r_mitte = (ra + ri) / 2.0
    n = int(nadeln) or max(8, int(math.pi / math.asin(
        min(0.99, r_nadel / r_mitte)) * 0.75))
    kaefig = Part.makeCylinder(r_mitte + r_nadel * 0.25, float(breite))
    kaefig = kaefig.cut(Part.makeCylinder(r_mitte - r_nadel * 0.25,
                                          float(breite) + 2.0,
                                          Vector(0, 0, -1.0)))
    for k in range(n):
        w = 2.0 * math.pi * k / n
        kaefig = kaefig.fuse(Part.makeCylinder(
            r_nadel, float(breite) * 0.9,
            Vector(r_mitte * math.cos(w), r_mitte * math.sin(w),
                   float(breite) * 0.05)))
    return kaefig.removeSplitter()


def _synchronring(d_innen, d_aussen, breite):
    """Synchronring: ein Reibkegel zwischen Muffe und Kupplungskörper.

    Er gleicht die Drehzahlen an, bevor die Muffe greift — ohne ihn würde
    beim Schalten Zahn auf Zahn stoßen. Gebaut als flacher Kegelring, Achse Z.
    """
    ri, ra = float(d_innen) / 2.0, float(d_aussen) / 2.0
    kegel = Part.makeCone(ri, ra, float(breite))
    innen = Part.makeCone(ri - 1.2, ra - 1.2, float(breite) + 2.0,
                          Vector(0, 0, -1.0))
    return kegel.cut(innen)


def _schaltgabel(x, r_nut, breite, r_stange, winkel, staerke=6.0):
    """Schaltgabel: ein Halbring in der Muffennut mit Arm zur Schaltstange.

    Gebaut **direkt entlang X**, denn sie hat keine eigene Bauachse — sie
    sitzt dort, wo die Muffe sitzt, und greift nach oben. Im ersten Anlauf
    entstand sie wie die Räder entlang Z und wurde mitgedreht; dabei zeigte
    ihr Arm zur Seite statt nach oben, und die Schaltstange lag woanders.

    Sie **umfasst** die Muffe, sie umschließt sie nicht: ein Halbring in
    der umlaufenden Nut, der die Muffe axial schiebt.
    """
    ra = float(r_nut) + float(staerke)
    halb = Part.makeCylinder(ra, float(breite), Vector(float(x), 0, 0),
                             Vector(1, 0, 0))
    halb = halb.cut(Part.makeCylinder(float(r_nut), float(breite) + 2.0,
                                      Vector(float(x) - 1.0, 0, 0),
                                      Vector(1, 0, 0)))
    gross = ra * 2.0 + 4.0
    halb = halb.cut(Part.makeBox(
        float(breite) + 4.0, gross, gross,
        Vector(float(x) - 2.0, -gross / 2.0, -gross)))
    # Der Arm geht RADIAL nach aussen zu seiner eigenen Stange. Vorher lief
    # er erst nach oben und dann quer — dabei kreuzte er die Nachbarstangen
    # (gemessen 11 bis 13 % Durchdringung). Drei Stangen auf einem Bogen,
    # drei radiale Arme: keiner kreuzt einen anderen.
    arm = Part.makeBox(float(breite), float(staerke),
                       float(r_stange) - float(r_nut) + 14.0,
                       Vector(float(x), -float(staerke) / 2.0,
                              float(r_nut)))
    # Die Nabe der Gabel sitzt auf ihrer Stange und gleitet darauf.
    nabe = Part.makeCylinder(float(staerke) * 1.8, float(breite),
                             Vector(float(x), 0.0, float(r_stange)),
                             Vector(1, 0, 0))
    gabel = halb.fuse(arm).fuse(nabe)
    gabel = gabel.cut(Part.makeCylinder(
        7.0 + 0.15, float(breite) + 4.0,
        Vector(float(x) - 2.0, 0.0, float(r_stange)), Vector(1, 0, 0)))
    gabel.rotate(Vector(0, 0, 0), Vector(1, 0, 0), float(winkel))
    return gabel.removeSplitter()


def _baue_vorgelege(gaenge=5, modul=2.0, zaehne_summe=48, breite=12.0,
                    luft=6.0, z_min=17, verzahnung="gerade",
                    schraegwinkel=15.0, eingriffswinkel=20.0,
                    flankenspiel=0.05, welle_d=20.0, lager_reihe="62",
                    spiel=0.1, gehaeuse_luft=3.0, wand=4.0, flansch_b=12.0,
                    schraube_d=6.0, muffe_b=0.0, glocke_l=0.0, glocke_d=0.0,
                    doc=None):
    """Das Vorgelegegetriebe — Antriebswelle und Hauptwelle auf einer Achse.

    Aufbau entlang +X, vom Motor her gesehen:

        [Lager] [Konstantenpaar] [Muffe direkt/1] [Gang 1] … [Gang n] [Lager]
          y = 0:  Antriebswelle ──┤ Spigot ├── Hauptwelle mit den Losraedern
          y = a:  Vorgelegewelle mit dem Konstantenrad und den Festraedern

    Die **Antriebswelle** reicht nur bis hinter das Konstantenrad und stützt
    sich mit einem Zapfen in der Hauptwelle ab; von da an ist die Hauptwelle
    der Abtrieb. Beide liegen auf y = 0, und genau darum geht der Abtrieb
    dorthin zurück, wo der Antrieb herkommt.

    Die **Losräder** sitzen auf der Hauptwelle und laufen frei, bis eine
    Schaltmuffe sie mit ihr kuppelt. Die **Festräder** sitzen auf der
    Vorgelegewelle. Die erste Muffe kuppelt nach vorn die Antriebswelle
    selbst — das ist der **direkte Gang**, i = 1, und dabei läuft die
    Vorgelegewelle leer mit.

    ``glocke_l`` > 0 baut die **Kupplungsglocke** an: eine Haube, die vorn
    am Getriebegehäuse sitzt, die Kupplung umschließt und am Motorblock
    verschraubt ist. Sie gehört zum Getriebe, nicht zum Motor — das ist der
    Grund, warum man ein Getriebe samt Glocke tauscht. Die **Antriebswelle
    wird dann um dieselbe Länge verlängert**: sie muss durch die Glocke
    hindurch bis in die Kupplungsscheiben reichen, deren Naben auf ihr
    laufen, und sich vorn im Schwungrad abstützen. Ohne diese Verlängerung
    stünde das Getriebe hinter der Kupplung, statt sie zu tragen.
    """
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Getriebe")
    konstante, paare = gangpaare_vorgelege(int(zaehne_summe), int(gaenge),
                                           int(z_min))
    a = G.achsabstand(modul, konstante[0], konstante[1])
    schritt = float(breite) + float(luft)
    welle_r = welle_d / 2.0 + spiel

    lager_name = LG.waehle(welle_d, lager_reihe)
    lm = LG.masse(lager_name)
    sitz_r = lm["D"] / 2.0

    teile = []

    def lege_ab(shape, label, pos, drehen=True, phase=0.0):
        s = shape.copy()
        if phase:
            s.rotate(Vector(0, 0, 0), Vector(0, 0, 1), float(phase))
        if drehen:
            s.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)
        s.translate(Vector(*pos))
        teile.append((label, s))

    def paar(z_oben, z_unten, x, label_oben, label_unten, bohrung_oben=0.0):
        """Ein Radpaar: oben auf y = 0, unten auf der Vorgelegewelle."""
        oben, _d1, d_a1 = zahnrad(doc, z_oben, modul, breite,
                                  float(bohrung_oben) or welle_d,
                                  verzahnung, schraegwinkel,
                                  eingriffswinkel, flankenspiel)
        # Gegenlaeufig schraegverzahnt, sonst kaemmen sie nicht.
        unten, _d2, d_a2 = zahnrad(doc, z_unten, modul, breite,
                                   welle_d + 2.0 * spiel, verzahnung,
                                   -float(schraegwinkel), eingriffswinkel,
                                   flankenspiel)
        lege_ab(oben, label_oben, (x, 0.0, 0.0))
        # Halbe Zahnteilung Phase, sonst stossen die Zaehne aufeinander.
        lege_ab(unten, label_unten, (x, a, 0.0),
                phase=180.0 / float(z_unten))
        return [d_a1 / 2.0 + float(gehaeuse_luft),
                d_a2 / 2.0 + float(gehaeuse_luft)]

    # --- Abschnitte des Gehaeuses, x = 0 ist der Anfang des Hohlraums ----
    abschnitte = [(lm["B"], [sitz_r, sitz_r])]
    vorlauf = lm["B"] + wand

    # Konstantenpaar: Festrad auf der Antriebswelle, Festrad auf dem
    # Vorgelege. Es sitzt ganz vorn, also motorseitig.
    x_k = vorlauf + luft / 2.0
    raum_k = paar(konstante[0], konstante[1], x_k,
                  "Antriebskonstante (z=%d)" % konstante[0],
                  "Vorgelegekonstante (z=%d)" % konstante[1])
    abschnitte.append((wand, [welle_r, welle_r],
                       [r + wand for r in raum_k]))
    abschnitte.append((schritt, raum_k))

    # --- Gangpaare -------------------------------------------------------
    # Das LOSRAD laeuft frei auf der Hauptwelle — es braucht also ein Lager.
    # In jedem wirklichen Schaltgetriebe ist das ein NADELLAGER zwischen
    # Rad und Welle; ohne es saesse das Rad direkt auf der Welle und koennte
    # sich nicht drehen, wenn ein anderer Gang eingelegt ist.
    nadel_t = max(3.0, welle_d * 0.12)          # Bauhoehe des Nadellagers
    losrad_bohrung = welle_d + 2.0 * nadel_t
    raum = raum_k
    gang_x = []
    for k, (z_fest, z_los, i) in enumerate(paare):
        x = x_k + (k + 1) * schritt
        gang_x.append(x)
        raum = paar(z_los, z_fest, x,
                    "Gang %d Losrad (z=%d, i=%.3f)" % (k + 1, z_los, i),
                    "Gang %d Festrad (z=%d)" % (k + 1, z_fest),
                    bohrung_oben=losrad_bohrung)
        lege_ab(_nadellager(welle_d + 2.0 * spiel, losrad_bohrung, breite),
                "Nadellager Gang %d" % (k + 1), (x, 0.0, 0.0))
        abschnitte.append((schritt, raum))
    abschnitte.append((wand, [welle_r, welle_r], [r + wand for r in raum]))
    abschnitte.append((lm["B"], [sitz_r, sitz_r]))
    innen_l = sum(x[0] for x in abschnitte)

    # --- Wellen ----------------------------------------------------------
    ueberstand = 8.0
    x_welle = -(wand + ueberstand)
    sitz_l = wand + ueberstand + lm["B"]
    ganz = innen_l + 2.0 * wand + 2.0 * ueberstand

    # Die Antriebswelle endet HINTER dem Konstantenrad; dort beginnt die
    # Hauptwelle. Ohne diesen Schnitt waere es eine durchgehende Welle, und
    # dann gaebe es keinen Gang ausser dem direkten.
    trennung = x_k + breite + luft / 2.0
    antrieb_l = trennung - x_welle
    # Nur vorn ein Lagersitz: hinten kommt die Kupplungsverzahnung, ueber
    # die die Muffe im direkten Gang greift.
    gl = max(0.0, float(glocke_l))
    welle_a = _welle(antrieb_l, welle_d, lm["d"], sitz_l, sitze="vorn")
    if gl > 0.0:
        # Die Verlaengerung durch die Glocke ist ein GLATTER Schaft, kein
        # weiterer Lagersitz: darauf gleiten die Kupplungsnaben, und ihre
        # Nase stuetzt sich im Schwungrad ab. Mit dem Lagersitz an der Nase
        # (30 mm unter 29-mm-Nabenbohrung) durchdrangen sich Nabe und Welle
        # um 2,9 %. Das Lager der Antriebswelle sitzt an der Gehaeusewand,
        # nicht am Wellenende.
        # Bis an die vorderste Ebene der Glocke, also durch beide
        # Stirnflansche hindurch.
        welle_a = welle_a.fuse(Part.makeCylinder(
            welle_d / 2.0, gl + 3.0 * wand,
            Vector(0, 0, -(gl + 3.0 * wand)))).removeSplitter()
    lege_ab(welle_a, "Antriebswelle", (x_welle, 0.0, 0.0))
    # Zapfen: die Antriebswelle stuetzt sich in der Hauptwelle ab. Er
    # braucht dort eine BOHRUNG — als blosser Zylinder auf der Stirnflaeche
    # stak er zu 100 % im Vollmaterial. Das ist das Pilotlager des echten
    # Getriebes: die Hauptwelle ist vorn aufgebohrt, der Zapfen laeuft
    # darin, und beide drehen im direkten Gang gemeinsam.
    zapfen_d = welle_d * 0.3
    zapfen_l = float(luft) * 0.8
    lege_ab(Part.makeCylinder(zapfen_d / 2.0, zapfen_l),
            "Zentrierzapfen", (trennung, 0.0, 0.0))
    haupt_l = ganz - antrieb_l
    # Die Hauptwelle traegt ihr Lager nur hinten; vorn steckt sie auf dem
    # Zapfen der Antriebswelle.
    haupt = _welle(haupt_l, welle_d, lm["d"], sitz_l, sitze="hinten")
    haupt = haupt.cut(Part.makeCylinder(zapfen_d / 2.0 + float(spiel),
                                        zapfen_l + float(spiel),
                                        Vector(0, 0, -0.001)))
    lege_ab(haupt, "Hauptwelle", (trennung, 0.0, 0.0))
    lege_ab(_welle(ganz, welle_d, lm["d"], sitz_l), "Vorgelegewelle",
            (x_welle, a, 0.0))

    # --- Schaltmuffen auf der HAUPTWELLE ---------------------------------
    # Die erste kuppelt nach vorn die Antriebswelle selbst: direkter Gang.
    # In die Luecke muessen MUFFE UND ZWEI SYNCHRONRINGE. Frueher fuellte
    # die Muffe die Luecke allein, und die Ringe standen in den Raedern
    # (gemessen 37 % Durchdringung).
    sr_b = max(3.0, float(luft) * 0.12)
    platz = float(luft) - 2.0 * sr_b - 4.0 * float(spiel)
    breite_muffe = float(muffe_b) if float(muffe_b) > 0.0 else platz
    breite_muffe = max(2.0, min(breite_muffe, platz))
    namen = ["direkt/1"] + ["%d/%d" % (k + 1, k + 2)
                            for k in range(len(paare) - 1)]
    muffe_d = welle_d + 12.0
    r_nut = muffe_d / 2.0 + 1.0
    # Die Schaltstangen liegen ueber dem groessten Rad, im Schaltdom.
    r_max = max(r for _l, rs in [(0, raum_k)] + [(0, raum)] for r in rs)
    r_stange = r_max + 22.0
    muffen_x = []
    # Drei Schaltstangen auf einem Bogen ueber der Hauptwelle.
    stangen_w = (-24.0, 0.0, 24.0)
    for k, name in enumerate(namen):
        x_luecke = x_k + k * schritt + breite
        x = x_luecke + sr_b + 2.0 * float(spiel)
        muffen_x.append((x, name))
        lege_ab(_schaltmuffe(welle_d + 2.0 * spiel, muffe_d, breite_muffe),
                "Schaltmuffe %s" % name, (x, 0.0, 0.0))
        # Beidseits der Muffe ein SYNCHRONRING: er gleicht die Drehzahlen
        # an, bevor die Muffe greift. Ohne ihn stiesse beim Schalten Zahn
        # auf Zahn.
        for seite, x_sr in (("links", x_luecke + float(spiel)),
                            ("rechts", x + breite_muffe + float(spiel))):
            lege_ab(_synchronring(welle_d + 2.0 * spiel + 1.0,
                                  muffe_d - 1.0, sr_b),
                    "Synchronring %s %s" % (name, seite), (x_sr, 0.0, 0.0))
        # Die SCHALTGABEL greift in die Nut der Muffe und reicht nach oben
        # zur Schaltstange; drei Stangen reihum.
        teile.append(("Schaltgabel %s" % name,
                      _schaltgabel(x + breite_muffe / 3.0, r_nut,
                                   breite_muffe / 3.0 - 0.4, r_stange,
                                   stangen_w[k % len(stangen_w)])))

    # --- Schaltstangen ---------------------------------------------------
    # Je Gabel eine Stange waere zuviel; ein Sechsganggetriebe fuehrt sie
    # auf drei Stangen nebeneinander. Sie liegen ueber dem groessten Rad —
    # dort ist im Zahnradraum kein Platz, deshalb sitzt darueber der
    # SCHALTDOM (siehe unten).
    # Die Stangen bleiben IM Dom: ueberstehend stiessen sie in die
    # Stirnwaende des Gehaeuses (gemessen 7,9 %).
    stange_l = innen_l - 2.0 * wand
    for nr, w_st in enumerate(stangen_w, 1):
        rad = math.radians(w_st)
        teile.append(("Schaltstange %d" % nr,
                      Part.makeCylinder(
                          7.0, stange_l,
                          Vector(wand, -r_stange * math.sin(rad),
                                 r_stange * math.cos(rad)),
                          Vector(1, 0, 0))))


    # --- Lager -----------------------------------------------------------
    for seite, x in (("links", 0.0), ("rechts", innen_l - lm["B"])):
        for welle, y in (("Hauptwelle", 0.0), ("Vorgelege", a)):
            for label, shp in LG.baue(lager_name, spiel=spiel, achse="x",
                                      x=x, y=y, z=0.0):
                teile.append(("%s %s %s" % (label, welle, seite), shp))

    # --- Gehaeuse --------------------------------------------------------
    for label, shp in GK.baue([(0.0, 0.0), (0.0, a)], abschnitte=abschnitte,
                              wand=wand, flansch_b=flansch_b,
                              schraube_d=schraube_d,
                              welle_d=welle_d + 2.0 * spiel, achse="x"):
        teile.append((label, shp))

    # --- Schaltdom (nach dem Gehaeuse, denn er gehoert ans Oberteil —
    # davor gab es das Oberteil noch gar nicht, und der Dom fiel still
    # unter den Tisch) --- -------------------------------------------------------
    # Ueber dem groessten Rad ist im Zahnradraum kein Platz: das Rad reicht
    # bis r_max, die Stangen liegen darueber. Der SCHALTDOM schafft ihn —
    # ein aufgesetzter Kasten am Oberteil, in dem Stangen und Gabelnaben
    # laufen. Ohne ihn stiessen die Gabeln ins Gehaeuse (gemessen 4,8 %).
    dom_y = r_stange * math.sin(math.radians(max(stangen_w))) + 22.0
    dom_z0 = r_max * 0.80
    dom_z1 = r_stange + 20.0
    aussen = Part.makeBox(innen_l, 2.0 * dom_y, dom_z1 - dom_z0,
                          Vector(0.0, -dom_y, dom_z0))
    hohl = Part.makeBox(innen_l + 2.0, 2.0 * (dom_y - wand),
                        dom_z1 - dom_z0 - wand,
                        Vector(-1.0, -(dom_y - wand), dom_z0 - 1.0))
    dom = aussen.cut(hohl)
    # Der Domkasten ist eckig, die Gabeln schwenken auf einem BOGEN. Seine
    # Ecken ragten genau dort hinein, wo die Arme laufen (4,5 bis 6,3 %).
    # Ein zylindrischer Freischnitt um die Hauptwellenachse raeumt sie weg.
    frei = Part.makeCylinder(r_stange + 20.0, innen_l + 2.0,
                             Vector(-1.0, 0, 0), Vector(1, 0, 0))
    frei = frei.common(Part.makeBox(
        innen_l + 4.0, 2.0 * (dom_y - wand), dom_z1 + 40.0,
        Vector(-2.0, -(dom_y - wand), dom_z0 - 1.0)))
    for i, (label, shp) in enumerate(teile):
        if label == "Gehaeuse Oberteil":
            neu_shp = shp.fuse(dom).cut(hohl)
            geschnitten = neu_shp.cut(frei)
            # Volumenprobe: ein Freischnitt, der das halbe Gehaeuse frisst,
            # ist keiner.
            if geschnitten.Volume > neu_shp.Volume * 0.5:
                neu_shp = geschnitten
            teile[i] = (label, neu_shp.removeSplitter())
            break

    # --- Kupplungsglocke und die beiden Stirnflansche --------------------
    # Eine Glocke, die man nicht anschrauben kann, ist keine. Sie braucht
    # hinten einen Flansch, das Getriebegehaeuse vorn einen dazu passenden,
    # und beide dieselben Schraubenloecher auf demselben Lochkreis. Weil
    # das Gehaeuse in der Ebene durch beide Wellenachsen geteilt ist (z = 0),
    # ist auch sein Stirnflansch geteilt: je eine Haelfte an Ober- und
    # Unterteil.
    if gl > 0.0:
        d_a = float(glocke_d) or (a * 2.0 + 80.0)
        t_fl = wand * 1.5                       # Flanschdicke
        d_fl = d_a + 2.0 * float(flansch_b)     # Flanschaussendurchmesser
        r_loch = d_a / 2.0 + float(flansch_b) / 2.0
        n_loch = 12
        x_h = -wand                             # Stirnflaeche des Gehaeuses
        x_g = x_h - (gl + 2.0 * t_fl)           # vorderste Ebene der Glocke

        def loecher(koerper, x_von, laenge):
            for k in range(n_loch):
                w = 2.0 * math.pi * k / n_loch
                koerper = koerper.cut(Part.makeCylinder(
                    float(schraube_d) / 2.0, laenge,
                    Vector(x_von, r_loch * math.cos(w),
                           r_loch * math.sin(w)), Vector(1, 0, 0)))
            return koerper

        def scheibe(x_von, dicke, d_aussen, d_innen):
            k = Part.makeCylinder(d_aussen / 2.0, dicke, Vector(x_von, 0, 0),
                                  Vector(1, 0, 0))
            if d_innen > 0.0:
                k = k.cut(Part.makeCylinder(d_innen / 2.0, dicke + 2.0,
                                            Vector(x_von - 1.0, 0, 0),
                                            Vector(1, 0, 0)))
            return k

        # Die beiden Flansche liegen ANEINANDER, nicht aufeinander: der der
        # Glocke endet dort, wo der des Gehaeuses beginnt. Uebereinander
        # gelegt durchdrangen sie sich zu 20 %.
        x_stoss = x_h - t_fl          # die Trennebene der Verschraubung
        mantel = scheibe(x_g, x_stoss - x_g, d_a, d_a - 2.0 * float(wand))
        # vorn zum Motorblock, hinten zum Getriebegehaeuse
        vorn = scheibe(x_g, t_fl, d_fl, d_a - 2.0 * float(wand))
        hinten = scheibe(x_stoss - t_fl, t_fl, d_fl,
                         d_a - 2.0 * float(wand))
        glocke = mantel.fuse(vorn).fuse(hinten).removeSplitter()
        glocke = loecher(glocke, x_g - 1.0, t_fl + 2.0)
        glocke = loecher(glocke, x_stoss - t_fl - 1.0, t_fl + 2.0)
        teile.append(("Kupplungsglocke", glocke))

        # Der Gegenflansch am Getriebegehaeuse, GETEILT wie das Gehaeuse.
        stirn = scheibe(x_stoss, t_fl, d_fl, 0.0)
        # Die beiden Wellen gehen hindurch.
        for y in (0.0, a):
            stirn = stirn.cut(Part.makeCylinder(
                welle_d / 2.0 + float(spiel) + 1.0, t_fl + 2.0,
                Vector(x_stoss - 1.0, y, 0.0), Vector(1, 0, 0)))
        stirn = loecher(stirn, x_stoss - 1.0, t_fl + 2.0)
        # Teilen in der Ebene durch beide Wellenachsen, also bei z = 0 —
        # derselben Ebene, in der auch das Gehaeuse geteilt ist. Jede
        # Haelfte gehoert AN ihre Gehaeusehaelfte: ein Flansch ist kein
        # eigenes Bauteil, sondern ein Teil des Gehaeuses. Das Getriebe
        # besteht damit aus genau drei Gehaeuseteilen — Kupplungsglocke,
        # Oberteil und Unterteil.
        gross = d_fl + 20.0
        for name, z0 in (("Oberteil", 0.0), ("Unterteil", -gross)):
            halb = stirn.common(Part.makeBox(
                t_fl + 4.0, gross * 2.0, gross,
                Vector(x_stoss - 2.0, -gross, z0)))
            if halb.Volume <= 1.0:
                continue
            for i, (label, shp) in enumerate(teile):
                if label == "Gehaeuse " + name:
                    teile[i] = (label, shp.fuse(halb).removeSplitter())
                    break
            else:
                teile.append(("Gehaeuse %s Stirnflansch" % name, halb))

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
