# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Pleuel — kleines Auge, Schaft, großes Auge mit Deckel.

Gebaut wird in der **XZ-Ebene**, Augenachsen parallel zu **Y**. Der Ursprung
liegt im **großen Auge** (Hubzapfenmitte), das kleine Auge liegt bei
``z = +stichmass``.

Das Stichmaß ist der Abstand der beiden Augenmitten und damit die einzige
Länge, die den Kurbeltrieb wirklich bestimmt — aus ihm, dem Hub und der
Kompressionshöhe folgt die Blockhöhe. Es ist deshalb Eingabewert und wird
als Anschlussmaß wieder ausgegeben, nicht aus der Geometrie zurückgemessen.

Anschlusspunkte
    ``hubzapfen``    Mitte großes Auge, Achse +Y, Art *bohrung*
    ``kolbenbolzen`` Mitte kleines Auge, Achse +Y, Art *bohrung*
"""

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def stichmass_aus_hub(hub, faktor=1.75):
    """Übliches Stichmaß: das 1,6- bis 1,9-fache des Hubs.

    Das Verhältnis Stichmaß/Kurbelradius (λ = r/l) bestimmt die
    Kolbenbeschleunigung; übliche Motoren liegen bei λ ≈ 0,25…0,31, also
    Stichmaß ≈ 1,6…1,9 · Hub.
    """
    return round(float(hub) * float(faktor), 1)


def kennwerte(stichmass=150.0, hub=86.0, **_rest):
    l = float(stichmass)
    r = float(hub) / 2.0
    return {
        "stichmass": l,
        "kurbelradius": r,
        "lambda": round(r / l, 4) if l else 0.0,
    }


def baue(stichmass=150.0, hubzapfen_d=48.0, bolzen_d=22.0, breite=22.0,
         schaft_b=16.0, schaft_t=12.0, auge_wand=7.0, klein_wand=5.0,
         spiel=0.06, name="Pleuel"):
    """Ein Pleuel als :class:`Bauteil`.

    stichmass     Abstand der Augenmitten [mm]
    hubzapfen_d   Bohrung des großen Auges [mm]
    bolzen_d      Bohrung des kleinen Auges [mm]
    breite        Breite des großen Auges [mm]
    schaft_b      Breite des Schafts [mm]   schaft_t  Dicke des Schafts [mm]
    auge_wand     Wandstärke am großen Auge [mm]
    klein_wand    Wandstärke am kleinen Auge [mm]
    spiel         Lagerspiel je Auge [mm]. Ohne Spiel sind Auge und Zapfen
                  exakt gleich groß, und das ist geometrisch nicht von einer
                  Durchdringung zu unterscheiden: der Zusammenbau meldete
                  38,5 % zwischen Kurbelwelle und Pleuel.
    """
    l = float(stichmass)
    r_gross = float(hubzapfen_d) / 2.0 + float(auge_wand)
    r_klein = float(bolzen_d) / 2.0 + float(klein_wand)
    if l <= r_gross + r_klein:
        raise ValueError(
            "Stichmass %.1f mm ist kleiner als die beiden Augen zusammen "
            "(%.1f + %.1f mm)." % (l, r_gross, r_klein))

    def scheibe(radius, dicke, z):
        k = Part.makeCylinder(radius, dicke, Vector(0, -dicke / 2.0, z),
                              Vector(0, 1, 0))
        return k

    gross = scheibe(r_gross, float(breite), 0.0)
    klein = scheibe(r_klein, float(breite) * 0.75, l)

    # Schaft: ein Quader zwischen den Augen, als I-Profil angedeutet.
    schaft = Part.makeBox(float(schaft_t), float(schaft_b), l,
                          Vector(-float(schaft_t) / 2.0,
                                 -float(schaft_b) / 2.0, 0.0))
    steg = Part.makeBox(float(schaft_t) * 0.45, float(schaft_b) + 2.0, l - 4.0,
                        Vector(-float(schaft_t) * 0.225,
                               -float(schaft_b) / 2.0 - 1.0, 2.0))
    kern = Part.makeBox(float(schaft_t) * 0.45, float(schaft_b) * 0.55,
                        l - 4.0,
                        Vector(-float(schaft_t) * 0.225,
                               -float(schaft_b) * 0.275, 2.0))
    schaft = schaft.cut(steg.cut(kern))

    sp = max(0.0, float(spiel))
    koerper = gross.fuse(klein).fuse(schaft)
    koerper = koerper.cut(scheibe(float(hubzapfen_d) / 2.0 + sp,
                                  float(breite) + 4.0, 0.0))
    koerper = koerper.cut(scheibe(float(bolzen_d) / 2.0 + sp,
                                  float(breite) + 4.0, l))

    return Bauteil(
        name,
        koerper=[(name, koerper.removeSplitter())],
        punkte=[
            Punkt("hubzapfen", (0, 0, 0), (0, 1, 0), "bohrung",
                  float(hubzapfen_d), "grosses Auge – sitzt auf dem Hubzapfen"),
            Punkt("kolbenbolzen", (0, 0, l), (0, 1, 0), "bohrung",
                  float(bolzen_d), "kleines Auge – nimmt den Kolbenbolzen auf"),
        ],
        kennwerte=kennwerte(l))


def selbsttest():
    """Prüft Stichmaß, Bohrungen und Anschlusspunkte."""
    from kt_schnittstelle import pruefe_paarung

    l = 150.0
    t = baue(stichmass=l, hubzapfen_d=48.0, bolzen_d=22.0)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Pleuel ist kein Solid")

    # Das Stichmass muss exakt der Abstand der Anschlusspunkte sein.
    ab = t.punkt("hubzapfen").ort.distanceToPoint(t.punkt("kolbenbolzen").ort)
    if abs(ab - l) > 1e-9:
        raise AssertionError("Stichmass %.3f statt %.1f mm" % (ab, l))

    # Beide Bohrungen muessen den Zapfen spielend aufnehmen — mit seinem
    # vollen Nenndurchmesser, nicht mit einem abgezogenen Probenmass.
    for z, d, wie in ((0.0, 48.0, "grosses Auge"), (l, 22.0, "kleines Auge")):
        zapfen = Part.makeCylinder(d / 2.0, 300.0, Vector(0, -150.0, z),
                                   Vector(0, 1, 0))
        durch = shp.common(zapfen).Volume
        if durch > 1.0:
            raise AssertionError("%s klemmt auf dem Zapfen (%.1f mm^3)"
                                 % (wie, durch))

    # Die Augen muessen Material haben, sonst ist es kein Auge.
    ring = Part.makeCylinder(48.0 / 2.0 + 5.0, 10.0, Vector(0, -5.0, 0),
                             Vector(0, 1, 0)).cut(
        Part.makeCylinder(48.0 / 2.0, 12.0, Vector(0, -6.0, 0),
                          Vector(0, 1, 0)))
    if shp.common(ring).Volume < 500.0:
        raise AssertionError("um das grosse Auge steht zu wenig Material")

    # Die Achsen beider Augen zeigen in dieselbe Richtung.
    if abs(t.punkt("hubzapfen").achse.dot(
            t.punkt("kolbenbolzen").achse) - 1.0) > 1e-9:
        raise AssertionError("die Augenachsen sind nicht parallel")

    ok, text = pruefe_paarung(
        t.punkt("kolbenbolzen"),
        Punkt("probe", (0, 0, l), (0, -1, 0), "welle", 22.0))
    if not ok:
        raise AssertionError("kleines Auge paart nicht: " + text)

    # Zu kurzes Stichmass muss auffallen.
    try:
        baue(stichmass=30.0, hubzapfen_d=48.0, bolzen_d=22.0)
        raise AssertionError("zu kurzes Stichmass blieb unbemerkt")
    except ValueError:
        pass

    if abs(stichmass_aus_hub(86.0) - 150.5) > 0.1:
        raise AssertionError("Stichmassvorschlag falsch: %.1f"
                             % stichmass_aus_hub(86.0))
    return ("Pleuel-Selbsttest bestanden (Stichmass %.0f mm, lambda %.3f, "
            "%.0f mm^3)" % (l, t.kennwerte["lambda"], shp.Volume))
