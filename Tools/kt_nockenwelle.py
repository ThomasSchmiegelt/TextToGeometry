# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Nockenwelle — Lagerzapfen und Nocken in der richtigen Winkellage.

Gebaut wird entlang **+X**, Nocken 1 bei ``x = 0``. Winkelkonvention wie bei
der Kurbelwelle: 0° heißt Nockenspitze in **+Z**.

Der Nocken ist der Grundkreis plus eine Erhebung; die Erhebung ist genau der
**Ventilhub**. Das ist die Zusage dieses Bauteils und wird nachgemessen: der
größte Abstand von der Achse minus der Grundkreisradius muss der Hub sein.
Ein Nocken, dessen Erhebung nicht stimmt, macht die ganze Auslegung wertlos.

Die Nockenwelle dreht **halb so schnell** wie die Kurbelwelle. Die
Nockenwinkel sind deshalb die halben Kurbelwinkel — ein Zylinder, der bei
Kurbelwinkel 180° zündet, hat seinen Nocken bei 90° Nockenwinkel.

Anschlusspunkte
    ``nocken_1..n``   Nockenspitze, Achse radial nach außen, Art *flaeche*
    ``lager_1..m``    Lagerzapfen, Achse +X, Art *welle*
    ``antrieb``       Sitz für Kettenrad oder Zahnrad, Achse -X, Art *welle*
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def nockenwinkel(kurbelwinkel):
    """Nockenwinkel aus dem Kurbelwinkel — die halbe Drehzahl."""
    return [round((float(w) / 2.0) % 360.0, 3) for w in kurbelwinkel]


def nockenkontur(grundkreis_r, hub, breite, winkel_grad, flanke=60.0,
                 stuecke=48):
    """Ein Nocken als Solid: Grundkreis mit einer Erhebung.

    Die Erhebung wird über ``flanke`` Grad zu beiden Seiten der Spitze mit
    einem Kosinusverlauf aufgebaut — glatt und ohne Knick am Übergang.
    """
    rg = float(grundkreis_r)
    h = float(hub)
    fl = math.radians(float(flanke))
    punkte = []
    n = max(24, int(stuecke))
    for i in range(n):
        a = 2.0 * math.pi * i / n
        # Abstand zur Nockenspitze, auf -pi..pi gebracht
        d = (a + math.pi) % (2.0 * math.pi) - math.pi
        if abs(d) < fl:
            r = rg + h * 0.5 * (1.0 + math.cos(math.pi * d / fl))
        else:
            r = rg
        w = a + math.radians(float(winkel_grad)) + math.pi / 2.0
        punkte.append(Vector(0.0, -r * math.sin(a + math.radians(
            float(winkel_grad))), r * math.cos(a + math.radians(
                float(winkel_grad)))))
        del w
    punkte.append(punkte[0])
    flaeche = Part.Face(Part.Wire(Part.makePolygon(punkte)))
    return flaeche.extrude(Vector(float(breite), 0, 0))


def kennwerte(nocken=4, grundkreis_d=32.0, hub=10.0, **_rest):
    return {
        "nocken": int(nocken),
        "grundkreis_d": float(grundkreis_d),
        "hub": float(hub),
        "kopfkreis_d": float(grundkreis_d) + 2.0 * float(hub),
    }


def baue(winkel=None, grundkreis_d=32.0, hub=10.0, nocken_b=12.0,
         abstand=45.0, orte=None, lager_d=28.0, lager_b=18.0, welle_d=24.0,
         antrieb_d=26.0, antrieb_l=28.0, flanke=60.0, name="Nockenwelle"):
    """Eine Nockenwelle als :class:`Bauteil`.

    winkel        Liste der Nockenwinkel [Grad] — je Nocken einer
    grundkreis_d  Grundkreisdurchmesser [mm]
    hub           Nockenerhebung = Ventilhub [mm]
    nocken_b      Breite eines Nockens [mm]
    abstand       gleichmäßiger Abstand der Nocken [mm]
    orte          x-Lage jedes Nockens [mm]; überschreibt ``abstand``. Ein
                  Vierventiler hat zwei Nocken je Zylinder, und die sitzen
                  nicht im Zylinderabstand — mit gleichmäßiger Teilung wurde
                  eine 822 mm lange Welle daraus statt 224 mm.
    lager_d       Lagerzapfendurchmesser [mm]; ein Lager je zwei Nocken
    """
    winkel = list(winkel or [0.0, 180.0, 180.0, 0.0])
    n = len(winkel)
    if orte is not None:
        orte = [float(x) for x in orte]
        if len(orte) != n:
            raise ValueError("Zu jedem Nocken gehoert ein Ort: %d Winkel, "
                             "%d Orte." % (n, len(orte)))
    else:
        orte = [k * float(abstand) for k in range(n)]
    rg = float(grundkreis_d) / 2.0
    h = float(hub)
    if h <= 0.0:
        raise ValueError("Der Ventilhub muss positiv sein.")
    if float(welle_d) / 2.0 >= rg:
        raise ValueError(
            "Der Wellenschaft (%.1f) ist dicker als der Grundkreis (%.1f) — "
            "dann gaebe es keinen Nocken."
            % (float(welle_d), float(grundkreis_d)))

    teile = []
    punkte = []
    laenge = (max(orte) - min(orte)) + float(nocken_b) + 2.0 * float(lager_b)
    x0 = min(orte) - float(lager_b)

    # Durchgehender Schaft
    teile.append(("Schaft", Part.makeCylinder(
        float(welle_d) / 2.0, laenge, Vector(x0, 0, 0), Vector(1, 0, 0))))

    for k, w in enumerate(winkel):
        x = orte[k]
        teile.append(("Nocken %d" % (k + 1),
                      nockenkontur(rg, h, float(nocken_b), w, flanke)
                      .translated(Vector(x, 0, 0))
                      if hasattr(Part.Shape, "translated") else
                      _verschoben(nockenkontur(rg, h, float(nocken_b), w,
                                               flanke), Vector(x, 0, 0))))
        # Die Nockenspitze zeigt radial nach aussen.
        rad = Vector(0.0, -math.sin(math.radians(w)), math.cos(math.radians(w)))
        spitze = rad.multiply(rg + h)
        punkte.append(Punkt(
            "nocken_%d" % (k + 1),
            (x + float(nocken_b) / 2.0, spitze.y, spitze.z),
            (0.0, -math.sin(math.radians(w)), math.cos(math.radians(w))),
            "flaeche", float(nocken_b),
            "Nocken %d, %.1f Grad, Hub %.1f mm" % (k + 1, w, h)))

        # Lagerzapfen jeweils vor dem ersten und nach jedem zweiten Nocken.
        if k % 2 == 0:
            lx = x - float(lager_b) if k == 0 else \
                (orte[k - 1] + x) / 2.0 - float(lager_b) / 2.0
            teile.append(("Lager %d" % (k // 2 + 1), Part.makeCylinder(
                float(lager_d) / 2.0, float(lager_b), Vector(lx, 0, 0),
                Vector(1, 0, 0))))
            punkte.append(Punkt("lager_%d" % (k // 2 + 1),
                                (lx + float(lager_b) / 2.0, 0, 0), (1, 0, 0),
                                "welle", float(lager_d),
                                "Lagerzapfen %d" % (k // 2 + 1)))

    # Lager am Ende
    lx = max(orte) + float(nocken_b)
    teile.append(("Lager Ende", Part.makeCylinder(
        float(lager_d) / 2.0, float(lager_b), Vector(lx, 0, 0),
        Vector(1, 0, 0))))
    punkte.append(Punkt("lager_ende", (lx + float(lager_b) / 2.0, 0, 0),
                        (1, 0, 0), "welle", float(lager_d),
                        "letzter Lagerzapfen"))

    # Antriebszapfen vorn
    teile.append(("Antriebszapfen", Part.makeCylinder(
        float(antrieb_d) / 2.0, float(antrieb_l),
        Vector(x0 - float(antrieb_l), 0, 0), Vector(1, 0, 0))))
    punkte.append(Punkt("antrieb", (x0 - float(antrieb_l) / 2.0, 0, 0),
                        (-1, 0, 0), "welle", float(antrieb_d),
                        "Sitz fuer Kettenrad oder Zahnrad"))

    ganz = teile[0][1].multiFuse([t[1] for t in teile[1:]])
    return Bauteil(name, koerper=[(name, ganz)], punkte=punkte,
                   kennwerte=kennwerte(n, grundkreis_d, hub))


def _verschoben(shape, v):
    s = shape.copy()
    s.translate(v)
    return s


def selbsttest():
    """Prüft, dass die Nockenerhebung wirklich der Ventilhub ist."""
    rg, h = 16.0, 10.0
    winkel = [0.0, 90.0, 180.0, 270.0]
    t = baue(winkel=winkel, grundkreis_d=2 * rg, hub=h, nocken_b=12.0)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Nockenwelle ist kein Solid")

    # Die eigentliche Zusage: groesster Radius minus Grundkreis = Hub.
    b = shp.BoundBox
    r_max = max(abs(b.YMin), abs(b.YMax), abs(b.ZMin), abs(b.ZMax))
    if abs(r_max - (rg + h)) > 0.15:
        raise AssertionError(
            "Nockenhoehe %.2f statt %.2f — die Erhebung ist nicht der "
            "Ventilhub" % (r_max - rg, h))

    # Jeder Nocken muss an seinem Winkel stehen.
    for k, w in enumerate(winkel):
        p = t.punkt("nocken_%d" % (k + 1))
        gemessen = math.degrees(math.atan2(-p.ort.y, p.ort.z)) % 360.0
        if abs((gemessen - w + 180.0) % 360.0 - 180.0) > 0.5:
            raise AssertionError("Nocken %d steht bei %.1f statt %.1f Grad"
                                 % (k + 1, gemessen, w))
        radius = math.hypot(p.ort.y, p.ort.z)
        if abs(radius - (rg + h)) > 1e-6:
            raise AssertionError("Nocken %d: Spitze bei r=%.2f statt %.2f"
                                 % (k + 1, radius, rg + h))

    # Halbe Drehzahl: aus 180 Grad Kurbelwinkel werden 90 Grad Nockenwinkel.
    if nockenwinkel([0.0, 180.0, 360.0, 540.0]) != [0.0, 90.0, 180.0, 270.0]:
        raise AssertionError("die Umrechnung auf halbe Drehzahl stimmt nicht")

    # Anschlusspunkte.
    for pflicht in ("antrieb", "lager_1", "lager_ende"):
        t.punkt(pflicht)
    if t.punkt("antrieb").achse.x >= 0:
        raise AssertionError("der Antriebszapfen muss nach vorn zeigen")

    # Unsinnige Eingaben.
    for kw in ({"hub": 0.0}, {"welle_d": 40.0}):
        try:
            baue(winkel=winkel, grundkreis_d=2 * rg, **kw)
            raise AssertionError("unsinnige Eingabe blieb unbemerkt: %r" % kw)
        except ValueError:
            pass

    return ("Nockenwelle-Selbsttest bestanden (%d Nocken, Grundkreis %.0f, "
            "Hub %.1f mm, %.0f mm^3)" % (len(winkel), 2 * rg,
                                         r_max - rg, shp.Volume))
