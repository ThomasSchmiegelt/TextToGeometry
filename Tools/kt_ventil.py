# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Ventil — Teller mit Sitzfase, Schaft, Keilnut am Schaftende.

Gebaut wird entlang **+Z**, Schaft nach oben. Der Ursprung liegt in der
**Tellerunterkante** (der Brennraumseite) — das ist die Fläche, die im
Zylinderkopf sitzt und den Brennraum begrenzt.

Die Sitzfase hat 45°; der wirksame Sitzdurchmesser liegt darunter und ist als
Kennwert ausgewiesen, weil der Zylinderkopf ihn braucht.

Anschlusspunkte
    ``sitz``        Tellerrand am Ventilsitz, Achse -Z, Art *flaeche*
    ``schaft``      Schaftmitte auf halber Höhe, Achse +Z, Art *welle*
                    (läuft in der Schaftführung)
    ``schaft_ende`` Schaftende oben, Achse +Z, Art *flaeche* — hier drückt
                    der Stößel, und hier sitzt der Federteller
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def vorschlag(bohrung=86.0, ventile_je_zylinder=4, einlass=True):
    """Übliche Tellerdurchmesser als Anteil der Bohrung.

    Zwei Ventile: Einlass etwa 0,45·D, Auslass 0,38·D. Vier Ventile: die
    Teller werden kleiner, dafür ist die Gesamtfläche größer — Einlass
    0,36·D, Auslass 0,31·D.
    """
    d = float(bohrung)
    if int(ventile_je_zylinder) >= 4:
        return round(d * (0.36 if einlass else 0.31), 1)
    return round(d * (0.45 if einlass else 0.38), 1)


def kennwerte(teller_d=31.0, schaft_d=6.0, laenge=110.0, fase=45.0, **_rest):
    d = float(teller_d)
    # Der wirksame Sitzdurchmesser liegt eine Fasenbreite innen.
    return {
        "teller_d": d,
        "schaft_d": float(schaft_d),
        "laenge": float(laenge),
        "sitz_d": round(d - 2.0, 2),
        "sitzwinkel": float(fase),
    }


def baue(teller_d=31.0, schaft_d=6.0, laenge=110.0, teller_t=3.0, fase=45.0,
         fase_b=2.0, kegel_h=9.0, nut_t=0.8, nut_h=3.0, name="Ventil"):
    """Ein Ventil als :class:`Bauteil`.

    teller_d   Tellerdurchmesser [mm]
    schaft_d   Schaftdurchmesser [mm]
    laenge     Gesamtlänge von der Tellerunterkante bis zum Schaftende [mm]
    teller_t   Dicke des Tellerrandes [mm]
    fase       Sitzwinkel [Grad], üblich 45
    kegel_h    Höhe des Übergangs Teller → Schaft [mm]
    nut_t      Tiefe der Keilnut am Schaftende [mm]
    """
    rt = float(teller_d) / 2.0
    rs = float(schaft_d) / 2.0
    l = float(laenge)
    if rs >= rt:
        raise ValueError("Der Schaft (%.1f) ist nicht duenner als der Teller "
                         "(%.1f)." % (float(schaft_d), float(teller_d)))
    if l <= float(teller_t) + float(kegel_h) + float(nut_h) + 5.0:
        raise ValueError("Ventillaenge %.1f mm ist zu kurz fuer Teller, "
                         "Kegel und Keilnut." % l)

    # Tellerrand mit Sitzfase: ein Kegelstumpf, unten schmaler.
    fb = float(fase_b)
    unten_r = rt - fb * math.tan(math.radians(float(fase)) / 1.0) * 0.0 - fb
    teller = Part.makeCone(max(unten_r, rs + 0.5), rt, fb, Vector(0, 0, 0))
    teller = teller.fuse(Part.makeCylinder(rt, float(teller_t),
                                           Vector(0, 0, fb)))
    # Uebergang zum Schaft
    kegel = Part.makeCone(rt, rs, float(kegel_h),
                          Vector(0, 0, fb + float(teller_t)))
    schaft_z = fb + float(teller_t) + float(kegel_h)
    schaft = Part.makeCylinder(rs, l - schaft_z, Vector(0, 0, schaft_z))

    koerper = teller.fuse(kegel).fuse(schaft)

    # Keilnut am Schaftende
    if float(nut_t) > 0.0:
        z0 = l - float(nut_h) - 2.0
        nut = Part.makeCylinder(rs + 1.0, float(nut_h), Vector(0, 0, z0))
        kern = Part.makeCylinder(rs - float(nut_t), float(nut_h) + 2.0,
                                 Vector(0, 0, z0 - 1.0))
        koerper = koerper.cut(nut.cut(kern))

    return Bauteil(
        name,
        koerper=[(name, koerper.removeSplitter())],
        punkte=[
            Punkt("sitz", (0, 0, 0), (0, 0, -1), "flaeche", float(teller_d),
                  "Tellerunterkante – sitzt im Zylinderkopf"),
            Punkt("schaft", (0, 0, schaft_z + (l - schaft_z) / 2.0),
                  (0, 0, 1), "welle", float(schaft_d),
                  "Schaftmitte – laeuft in der Schaftfuehrung"),
            Punkt("schaft_ende", (0, 0, l), (0, 0, 1), "flaeche",
                  float(schaft_d),
                  "Schaftende – hier drueckt der Stoessel"),
        ],
        kennwerte=kennwerte(teller_d, schaft_d, l, fase))


def selbsttest():
    """Prüft Maße, Sitzfase und Anschlusspunkte."""
    t = baue(teller_d=31.0, schaft_d=6.0, laenge=110.0)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Ventil ist kein Solid")
    b = shp.BoundBox
    if abs(b.XLength - 31.0) > 0.1:
        raise AssertionError("Tellerdurchmesser %.2f statt 31" % b.XLength)
    if abs(b.ZLength - 110.0) > 0.01:
        raise AssertionError("Ventillaenge %.2f statt 110" % b.ZLength)
    if abs(b.ZMin) > 1e-9:
        raise AssertionError("Der Ursprung liegt nicht an der "
                             "Tellerunterkante (z %.3f)" % b.ZMin)

    # Der Schaft muss wirklich duenn sein: eine Huelse um den Schaft darf
    # kein Material treffen.
    huelse = Part.makeCylinder(6.0 / 2.0 + 3.0, 40.0,
                               Vector(0, 0, 60.0)).cut(
        Part.makeCylinder(6.0 / 2.0 + 0.1, 42.0, Vector(0, 0, 59.0)))
    if shp.common(huelse).Volume > 1.0:
        raise AssertionError("um den Schaft steht Material, wo keines "
                             "hingehoert")

    # Punkte.
    for name in ("sitz", "schaft", "schaft_ende"):
        t.punkt(name)
    if abs(t.punkt("schaft_ende").ort.z - 110.0) > 1e-9:
        raise AssertionError("Schaftende sitzt nicht auf der Ventillaenge")
    if t.punkt("sitz").achse.z > 0:
        raise AssertionError("die Sitzflaeche muss nach unten zeigen")

    # Vorschlaege: vier Ventile sind kleiner als zwei.
    if not (vorschlag(86.0, 4, True) < vorschlag(86.0, 2, True)):
        raise AssertionError("Vierventiler brauchen kleinere Teller")
    if not (vorschlag(86.0, 4, False) < vorschlag(86.0, 4, True)):
        raise AssertionError("das Auslassventil ist kleiner als das Einlass")

    # Unsinnige Eingaben muessen auffallen.
    for kw in ({"teller_d": 6.0, "schaft_d": 6.0}, {"laenge": 15.0}):
        try:
            baue(**kw)
            raise AssertionError("unsinnige Eingabe blieb unbemerkt: %r" % kw)
        except ValueError:
            pass
    return ("Ventil-Selbsttest bestanden (Teller %.0f, Schaft %.0f, %.0f mm "
            "lang, %.0f mm^3)" % (b.XLength, 6.0, b.ZLength, shp.Volume))
