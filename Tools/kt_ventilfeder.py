# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Ventilfeder mit Federteller — als echte Schraubenlinie.

Gebaut wird entlang **+Z**. Der Ursprung liegt **unten**, auf der Auflage im
Zylinderkopf; der Federteller sitzt oben am Ventilschaftende.

Die Feder ist eine gewendelte Helix, kein angedeuteter Zylinder: nur so
stimmen Windungszahl, Drahtdurchmesser und Blocklänge zueinander, und nur so
lässt sich prüfen, dass sie bei vollem Ventilhub nicht auf Block geht. Genau
das ist hier die Zusage — eine Feder, die bei maximalem Hub blockiert, zerlegt
den Ventiltrieb.

Anschlusspunkte
    ``unten``   Auflage im Zylinderkopf, Achse -Z, Art *flaeche*
    ``oben``    Federteller am Schaftende, Achse +Z, Art *flaeche*
    ``schaft``  Durchgang für den Ventilschaft, Achse +Z, Art *bohrung*
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def blocklaenge(windungen, draht_d):
    """Länge der auf Block gedrückten Feder [mm].

    Die tragenden Windungen plus die beiden angelegten Endwindungen.
    """
    return (float(windungen) + 2.0) * float(draht_d)


def kennwerte(einbaulaenge=42.0, windungen=6, draht_d=3.6, hub=10.0, **_rest):
    block = blocklaenge(windungen, draht_d)
    rest = float(einbaulaenge) - float(hub) - block
    return {
        "einbaulaenge": float(einbaulaenge),
        "blocklaenge": round(block, 2),
        "hub": float(hub),
        "restweg": round(rest, 2),
        "geht_auf_block": rest < 0.0,
    }


def baue(einbaulaenge=42.0, aussen_d=27.0, draht_d=3.6, windungen=6,
         schaft_d=6.0, teller_d=30.0, teller_t=4.0, hub=10.0, glaette=8,
         name="Ventilfeder"):
    """Feder und Federteller als :class:`Bauteil` (zwei Körper).

    einbaulaenge  Länge im eingebauten Zustand, Ventil geschlossen [mm]
    aussen_d      Außendurchmesser der Feder [mm]
    draht_d       Drahtdurchmesser [mm]
    windungen     tragende Windungen
    hub           größter Ventilhub [mm] — nur zur Prüfung auf Block
    glaette       Drahtstücke je Windung. 8 reicht und braucht rund 5 s;
                  eine Feder wird einmal gebaut und dann kopiert.
    """
    l = float(einbaulaenge)
    dd = float(draht_d)
    n = float(windungen)
    r_mitte = (float(aussen_d) - dd) / 2.0
    if r_mitte <= dd:
        raise ValueError("Der Federdurchmesser (%.1f) ist zu klein fuer "
                         "%.1f mm Draht." % (float(aussen_d), dd))
    block = blocklaenge(n, dd)
    if l <= block:
        raise ValueError(
            "Einbaulaenge %.1f mm liegt schon unter der Blocklaenge %.1f mm."
            % (l, block))

    # Die Wendel aus geraden Drahtstuecken, nicht als gezogenes Profil.
    # `makePipeShell` entlang einer Helix verzerrt das Profil: bei 11,7 mm
    # Wendelradius und 3,6 mm Draht kam ein Aussendurchmesser von 35,4 mm
    # heraus statt 27 — das Volumen stimmte dabei auf 0,3 % genau, die Form
    # also nicht. Aus Zylindern und Kugeln gebaut sind es exakt 27,00 mm.
    nutz_l = l - 2.0 * dd
    schritte = max(8, int(n * int(glaette)))
    punkte = []
    for i in range(schritte + 1):
        anteil = i / float(schritte)
        w = 2.0 * math.pi * n * anteil
        punkte.append(Vector(r_mitte * math.cos(w), r_mitte * math.sin(w),
                             dd / 2.0 + nutz_l * anteil))
    stuecke = [Part.makeSphere(dd / 2.0, punkte[0])]
    for i in range(schritte):
        a, b2 = punkte[i], punkte[i + 1]
        richtung = b2.sub(a)
        stuecke.append(Part.makeCylinder(dd / 2.0, richtung.Length, a,
                                         richtung))
        stuecke.append(Part.makeSphere(dd / 2.0, b2))
    feder = stuecke[0].multiFuse(stuecke[1:])

    # Angelegte Endwindungen, vereinfacht als flache Ringe.
    def ring(z):
        return Part.makeCylinder(r_mitte + dd / 2.0, dd,
                                 Vector(0, 0, z)).cut(
            Part.makeCylinder(r_mitte - dd / 2.0, dd + 2.0,
                              Vector(0, 0, z - 1.0)))

    # Die Endwindungen beruehren die Wendel nur tangential, und daran
    # scheitert die Vereinigung still: gemessen wurden 4490 mm^3 Wendel plus
    # 953 mm^3 Ring = 5392, nach dem zweiten fuse aber nur noch 953 — der
    # Koerper war weg, ohne Fehlermeldung. Deshalb wird jedes Verschmelzen
    # gegen das Volumen geprueft und sonst als eigener Koerper gefuehrt.
    koerper = [(name, feder)]
    for nr, z in ((1, 0.0), (2, l - dd)):
        teil = ring(z)
        versuch = None
        try:
            versuch = koerper[0][1].fuse(teil)
        except Exception:  # noqa: BLE001
            versuch = None
        erwartet = koerper[0][1].Volume + teil.Volume
        if versuch is not None and versuch.Volume > 0.9 * erwartet:
            koerper[0] = (name, versuch)
        else:
            koerper.append(("Endwindung %d" % nr, teil))

    # Federteller oben, mit Durchgang fuer den Schaft.
    teller = Part.makeCylinder(float(teller_d) / 2.0, float(teller_t),
                               Vector(0, 0, l))
    teller = teller.cut(Part.makeCylinder(float(schaft_d) / 2.0,
                                          float(teller_t) + 2.0,
                                          Vector(0, 0, l - 1.0)))

    koerper.append(("Federteller", teller))
    return Bauteil(
        name,
        koerper=koerper,
        punkte=[
            Punkt("unten", (0, 0, 0), (0, 0, -1), "flaeche", float(aussen_d),
                  "Auflage im Zylinderkopf"),
            Punkt("oben", (0, 0, l + float(teller_t)), (0, 0, 1), "flaeche",
                  float(teller_d), "Federteller am Schaftende"),
            Punkt("schaft", (0, 0, l), (0, 0, 1), "bohrung", float(schaft_d),
                  "Durchgang fuer den Ventilschaft"),
        ],
        kennwerte=kennwerte(l, windungen, dd, hub))


def selbsttest():
    """Prüft Geometrie, Blocklänge und den Hubweg."""
    l, dd, n, hub = 42.0, 3.6, 6, 10.0
    t = baue(einbaulaenge=l, draht_d=dd, windungen=n, hub=hub)

    feder = t.koerper[0][1]
    teller = [s for n, s in t.koerper if n == "Federteller"][0]
    windungen = [s for n, s in t.koerper if n.startswith("Endwindung")]
    if not feder.Solids:
        raise AssertionError("die Feder ist kein Solid")
    if not teller.Solids:
        raise AssertionError("der Federteller ist kein Solid")

    # Gemessen wird ueber alle Federkoerper zusammen — die Endwindungen
    # koennen eigene Solids sein, siehe oben.
    alle = [feder] + windungen
    zmin = min(x.BoundBox.ZMin for x in alle)
    zmax = max(x.BoundBox.ZMax for x in alle)
    dmax = max(max(x.BoundBox.XLength, x.BoundBox.YLength) for x in alle)
    if abs((zmax - zmin) - l) > 0.2:
        raise AssertionError("Federlaenge %.2f statt %.1f" % (zmax - zmin, l))
    if abs(dmax - 27.0) > 0.3:
        raise AssertionError("Federaussendurchmesser %.2f statt 27" % dmax)
    if feder.Volume < 3000.0:
        raise AssertionError("die Wendel ist mit %.0f mm^3 zu duenn — ist "
                             "sie beim Verschmelzen verschwunden?"
                             % feder.Volume)

    # Der Ventilschaft muss durch den Teller passen.
    schaft = Part.makeCylinder(6.0 / 2.0 - 0.1, 200.0, Vector(0, 0, -50.0))
    if teller.common(schaft).Volume > 1.0:
        raise AssertionError("der Federteller laesst den Schaft nicht durch")
    for x in alle:
        if x.common(schaft).Volume > 1.0:
            raise AssertionError("die Feder sitzt auf dem Schaft")

    # Die eigentliche Zusage: bei vollem Hub darf sie nicht auf Block gehen.
    k = t.kennwerte
    if k["geht_auf_block"]:
        raise AssertionError(
            "die Feder geht bei %.1f mm Hub auf Block (Einbaulaenge %.1f, "
            "Blocklaenge %.1f)" % (hub, l, k["blocklaenge"]))
    if k["restweg"] <= 0.0:
        raise AssertionError("kein Restweg bei vollem Hub")

    # Eine zu kurz eingebaute Feder muss auffallen.
    eng = kennwerte(einbaulaenge=30.0, windungen=6, draht_d=3.6, hub=10.0)
    if not eng["geht_auf_block"]:
        raise AssertionError("30 mm Einbaulaenge bei 28,8 mm Block und 10 mm "
                             "Hub muessten auf Block gehen")
    try:
        baue(einbaulaenge=20.0, draht_d=3.6, windungen=6)
        raise AssertionError("Einbaulaenge unter Blocklaenge blieb unbemerkt")
    except ValueError:
        pass

    return ("Ventilfeder-Selbsttest bestanden (%.0f mm eingebaut, Block "
            "%.1f mm, Restweg %.1f mm bei %.0f mm Hub, %d Koerper)"
            % (l, k["blocklaenge"], k["restweg"], hub, len(t.koerper)))
