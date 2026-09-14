# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kolben — Boden, Ringpartie, Schaft, Bolzenaugen.

Bewusst grob: ein Zylinder mit Ringnuten, ausgehöhltem Schaft und einer
Querbohrung für den Kolbenbolzen. Was zählt, sind die Anschlusspunkte.

Gebaut wird entlang **+Z**, mit dem Bolzen auf der **Y-Achse**. Der Ursprung
liegt in der Kolbenbolzenmitte — nicht am Boden. Das ist die Stelle, an der
der Kolben am Pleuel hängt, und damit die einzige, die beim Zusammenbau
zählt. Die Kompressionshöhe (Abstand Bolzenmitte bis Boden) ist ein
Eingabewert, kein Nebenprodukt.

Anschlusspunkte
    ``bolzen``   Bolzenmitte, Achse +Y, Art *welle*  (das Pleuelauge kommt
                 hier drauf)
    ``boden``    Kolbenbodenmitte, Achse +Z, Art *flaeche*
    ``laufbahn`` Mitte der Ringpartie, Achse +Z, Art *gleitbahn* (die
                 Zylinderlaufbahn dockt hier an)
"""

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def kennwerte(bohrung=86.0, kompressionshoehe=32.0, bolzen_d=22.0,
              schafthoehe=48.0, **_rest):
    """Maße, die andere Bauteile brauchen — ohne Geometrie."""
    d = float(bohrung)
    return {
        "bohrung": d,
        "kolben_d": round(d - 0.12, 3),        # Laufspiel
        "kompressionshoehe": float(kompressionshoehe),
        "bolzen_d": float(bolzen_d),
        "gesamthoehe": float(kompressionshoehe) + float(schafthoehe),
    }


def baue(bohrung=86.0, kompressionshoehe=32.0, bolzen_d=22.0,
         schafthoehe=48.0, boden_t=7.0, ringe=3, ringnut_h=1.5,
         ringnut_t=2.0, laufspiel=0.12, pleuel_b=17.0, pleuel_spiel=0.5,
         ventiltaschen=None, name="Kolben"):
    """Ein Kolben als :class:`Bauteil`.

    bohrung            Zylinderbohrung [mm]; der Kolben ist um das Laufspiel
                       kleiner
    kompressionshoehe  Bolzenmitte bis Kolbenboden [mm]
    bolzen_d           Kolbenbolzendurchmesser [mm]
    schafthoehe        Bolzenmitte bis Schaftende [mm]
    boden_t            Dicke des Kolbenbodens [mm]
    ringe              Zahl der Kolbenringe
    pleuel_b           Breite des kleinen Pleuelauges [mm] — dafür bleibt
                       zwischen den Bolzennaben ein Schlitz frei
    ventiltaschen      Liste von (x, y, d, tiefe) im Kolbenkoordinatensystem:
                       Mulden im Boden, damit die Ventile bei der
                       Überschneidung am oberen Totpunkt nicht anschlagen.
                       Ohne sie durchdringen sich Kolben und Ventil — real
                       ist genau das der Grund, warum es Ventiltaschen gibt.
    """
    d = float(bohrung) - float(laufspiel)
    r = d / 2.0
    kh = float(kompressionshoehe)
    sh = float(schafthoehe)
    bd = float(bolzen_d)

    if kh <= float(boden_t) + bd / 2.0:
        raise ValueError(
            "Kompressionshoehe %.1f mm ist zu klein: Boden (%.1f) und halber "
            "Bolzen (%.1f) passen nicht darunter."
            % (kh, float(boden_t), bd / 2.0))

    # Grundkoerper: von -sh (Schaftende) bis +kh (Boden), Ursprung = Bolzen.
    koerper = Part.makeCylinder(r, kh + sh, Vector(0, 0, -sh))

    # Ringnuten, von oben nach unten unter dem Boden.
    z = kh - float(boden_t)
    for _i in range(max(0, int(ringe))):
        z -= float(ringnut_h)
        nut = Part.makeCylinder(r + 1.0, float(ringnut_h), Vector(0, 0, z))
        kern = Part.makeCylinder(r - float(ringnut_t), float(ringnut_h) + 2.0,
                                 Vector(0, 0, z - 1.0))
        koerper = koerper.cut(nut.cut(kern))
        z -= 2.0 * float(ringnut_h)

    # Schaft aushoehlen: von unten bis knapp unter den Boden.
    hohl_r = r - 4.0
    hohl_h = kh - float(boden_t) - 2.0 + sh
    if hohl_r > bd and hohl_h > 0:
        koerper = koerper.cut(Part.makeCylinder(hohl_r, hohl_h,
                                                Vector(0, 0, -sh)))
        # Die Bolzennaben bleiben stehen — aber NUR aussen. In der Mitte
        # muss das kleine Pleuelauge Platz haben; ein durchgehender
        # Nabenzylinder hat es um 7936 mm^3 durchdrungen.
        nabe = Part.makeCylinder(bd, d, Vector(0, -d / 2.0, 0),
                                 Vector(0, 1, 0))
        schlitz_b = float(pleuel_b) + 2.0 * float(pleuel_spiel)
        schlitz = Part.makeBox(d + 4.0, schlitz_b, d + 4.0,
                               Vector(-d / 2.0 - 2.0, -schlitz_b / 2.0,
                                      -d / 2.0 - 2.0))
        nabe = nabe.cut(schlitz)
        koerper = koerper.fuse(nabe.common(
            Part.makeCylinder(r, kh + sh, Vector(0, 0, -sh))))

    # Ventiltaschen im Boden.
    for tasche in (ventiltaschen or []):
        tx, ty, td, tt = (float(v) for v in tasche)
        if td <= 0.0 or tt <= 0.0:
            continue
        mulde = Part.makeCylinder(td / 2.0, tt + 1.0,
                                  Vector(tx, ty, kh - tt))
        koerper = koerper.cut(mulde)

    # Bolzenbohrung quer durch.
    koerper = koerper.cut(Part.makeCylinder(bd / 2.0, d + 4.0,
                                            Vector(0, -d / 2.0 - 2.0, 0),
                                            Vector(0, 1, 0)))

    return Bauteil(
        name,
        koerper=[(name, koerper.removeSplitter())],
        punkte=[
            Punkt("bolzen", (0, 0, 0), (0, 1, 0), "welle", bd,
                  "Kolbenbolzenmitte – hier haengt das Pleuel"),
            Punkt("boden", (0, 0, kh), (0, 0, 1), "flaeche", d,
                  "Kolbenboden – begrenzt den Brennraum"),
            Punkt("laufbahn", (0, 0, kh - float(boden_t)), (0, 0, 1),
                  "gleitbahn", d, "Ringpartie – laeuft in der Zylinderbohrung"),
        ],
        kennwerte=kennwerte(bohrung, kh, bd, sh))


def selbsttest():
    """Prüft Maße und Anschlusspunkte gegen die Eingaben."""
    from kt_schnittstelle import pruefe_paarung

    t = baue(bohrung=86.0, kompressionshoehe=32.0, bolzen_d=22.0,
             schafthoehe=48.0)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Kolben ist kein Solid")
    b = shp.BoundBox
    if abs(max(b.XLength, b.ZLength) - 0.0) < 0:
        pass
    # Durchmesser = Bohrung minus Laufspiel.
    if abs(b.XLength - (86.0 - 0.12)) > 0.2:
        raise AssertionError("Kolbendurchmesser %.2f statt %.2f"
                             % (b.XLength, 86.0 - 0.12))
    # Hoehe = Kompressionshoehe + Schafthoehe, Ursprung in der Bolzenmitte.
    if abs(b.ZMax - 32.0) > 0.01 or abs(b.ZMin + 48.0) > 0.01:
        raise AssertionError("Kolben steht falsch: z %.2f..%.2f, erwartet "
                             "-48..32" % (b.ZMin, b.ZMax))
    # Der Bolzen muss wirklich durchgehen.
    stift = Part.makeCylinder(22.0 / 2.0 - 0.2, 200.0,
                              Vector(0, -100.0, 0), Vector(0, 1, 0))
    if shp.common(stift).Volume > 1.0:
        raise AssertionError("die Bolzenbohrung ist nicht frei")
    # Anschlusspunkte.
    for name in ("bolzen", "boden", "laufbahn"):
        t.punkt(name)
    if abs(t.punkt("boden").ort.z - 32.0) > 1e-9:
        raise AssertionError("Bodenpunkt sitzt nicht auf der "
                             "Kompressionshoehe")
    ok, text = pruefe_paarung(t.punkt("bolzen"),
                              Punkt("probe", (0, 0, 0), (0, -1, 0),
                                    "bohrung", 22.0))
    if not ok:
        raise AssertionError("Bolzenpunkt paart nicht: " + text)
    # Das kleine Pleuelauge muss zwischen die Naben passen.
    import kt_pleuel as P
    pleuel = P.baue(stichmass=150.0, bolzen_d=22.0, breite=22.0)
    import kt_schnittstelle as S
    gesetzt = S.andocke(pleuel, "kolbenbolzen", t.punkt("bolzen"))
    durch = shp.common(gesetzt.koerper[0][1]).Volume
    if durch > 50.0:
        raise AssertionError(
            "das kleine Pleuelauge steckt im Kolben (%.0f mm^3) — der "
            "Pleuelschlitz fehlt oder ist zu schmal" % durch)

    # Zu kleine Kompressionshoehe muss auffallen.
    try:
        baue(bohrung=86.0, kompressionshoehe=12.0, bolzen_d=22.0)
        raise AssertionError("zu kleine Kompressionshoehe blieb unbemerkt")
    except ValueError:
        pass
    return ("Kolben-Selbsttest bestanden (d %.2f mm, %.0f mm hoch, %.0f mm^3)"
            % (b.XLength, b.ZLength, shp.Volume))
