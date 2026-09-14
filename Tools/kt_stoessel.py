# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Tassenstößel mit hydraulischem Ventilspielausgleich (HVA).

Gebaut wird entlang **+Z**. Der Ursprung liegt an der **Unterseite**, also
dort, wo der Stößel auf dem Ventilschaftende aufsitzt. Oben läuft der Nocken
auf dem Tassenboden.

Der HVA steckt im Stößel: ein Kolben, der sich unter Öldruck nachstellt und
das Ventilspiel auf null hält. Er ist hier als innerer Zylinder mit
Ölbohrung angedeutet — sein Zweck für die Konstruktion ist der
**Ausgleichsweg**, und den prüft der Selbsttest.

Der Kraftweg ist eine gerade Linie: Nocken → Tassenboden → HVA → Schaftende.
Deshalb müssen die drei Anschlusspunkte auf einer Achse liegen, und genau das
wird nachgemessen.

Anschlusspunkte
    ``nocken``  Tassenboden oben, Achse +Z, Art *flaeche* — hier läuft der
                Nocken
    ``ventil``  Unterseite, Achse -Z, Art *flaeche* — sitzt auf dem
                Schaftende
    ``fuehrung`` Mantel auf halber Höhe, Achse +Z, Art *gleitbahn* — läuft in
                der Bohrung des Zylinderkopfs
"""

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def kennwerte(tassen_d=33.0, hoehe=26.0, boden_t=4.0, hva_weg=4.0, **_rest):
    return {
        "tassen_d": float(tassen_d),
        "hoehe": float(hoehe),
        "boden_t": float(boden_t),
        "hva_weg": float(hva_weg),
    }


def baue(tassen_d=33.0, hoehe=26.0, boden_t=4.0, wand=2.5, hva_d=16.0,
         hva_weg=4.0, oelbohrung_d=3.0, ventil_d=6.0,
         name="Tassenstoessel"):
    """Tassenstößel mit HVA als :class:`Bauteil` (zwei Körper).

    tassen_d    Außendurchmesser der Tasse [mm]
    hoehe       Gesamthöhe [mm]
    boden_t     Dicke des Tassenbodens (Nockenlauffläche) [mm]
    wand        Mantelstärke [mm]
    hva_d       Durchmesser des Ausgleichskolbens [mm]
    hva_weg     Verstellweg des Ausgleichs [mm]
    ventil_d    Schaftdurchmesser des Ventils [mm] — nur als Kennmaß des
                Anschlusspunktes, damit eine falsche Paarung auffällt
    """
    r = float(tassen_d) / 2.0
    h = float(hoehe)
    bt = float(boden_t)
    if float(wand) <= 0 or r <= float(wand):
        raise ValueError("Mantelstaerke %.1f passt nicht zu Durchmesser %.1f."
                         % (float(wand), float(tassen_d)))
    if h <= bt + float(hva_weg) + 2.0:
        raise ValueError(
            "Hoehe %.1f mm reicht nicht fuer Boden (%.1f) und Ausgleichsweg "
            "(%.1f)." % (h, bt, float(hva_weg)))
    if float(hva_d) >= 2.0 * (r - float(wand)):
        raise ValueError("Der Ausgleichskolben (%.1f) passt nicht in die "
                         "Tasse." % float(hva_d))

    # Tasse: Becher, oben geschlossen (der Nocken laeuft auf dem Boden).
    tasse = Part.makeCylinder(r, h)
    tasse = tasse.cut(Part.makeCylinder(r - float(wand), h - bt))

    # Ausgleichskolben, von unten in die Tasse geschoben.
    hva = Part.makeCylinder(float(hva_d) / 2.0, h - bt - float(hva_weg))
    hva = hva.cut(Part.makeCylinder(float(oelbohrung_d) / 2.0, h,
                                    Vector(0, 0, -1.0)))

    return Bauteil(
        name,
        koerper=[(name, tasse.removeSplitter()), ("HVA-Element", hva)],
        punkte=[
            Punkt("nocken", (0, 0, h), (0, 0, 1), "flaeche", float(tassen_d),
                  "Tassenboden – hier laeuft der Nocken"),
            Punkt("ventil", (0, 0, 0), (0, 0, -1), "flaeche",
                  float(ventil_d),
                  "Unterseite – sitzt auf dem Ventilschaftende"),
            Punkt("fuehrung", (0, 0, h / 2.0), (0, 0, 1), "gleitbahn",
                  float(tassen_d),
                  "Mantel – laeuft in der Bohrung des Zylinderkopfs"),
        ],
        kennwerte=kennwerte(tassen_d, h, bt, hva_weg))


def selbsttest():
    """Prüft Maße, den geraden Kraftweg und den Ausgleichsweg."""
    d, h, bt, weg = 33.0, 26.0, 4.0, 4.0
    t = baue(tassen_d=d, hoehe=h, boden_t=bt, hva_weg=weg)

    tasse, hva = t.koerper[0][1], t.koerper[1][1]
    if not tasse.Solids or not hva.Solids:
        raise AssertionError("Tasse oder HVA ist kein Solid")

    b = tasse.BoundBox
    if abs(b.XLength - d) > 0.1:
        raise AssertionError("Tassendurchmesser %.2f statt %.1f"
                             % (b.XLength, d))
    if abs(b.ZLength - h) > 0.01:
        raise AssertionError("Hoehe %.2f statt %.1f" % (b.ZLength, h))

    # Der Boden muss oben sein — dort laeuft der Nocken.
    oben = Part.makeCylinder(d / 2.0 - 1.0, 1.0, Vector(0, 0, h - 1.0))
    if tasse.common(oben).Volume < 100.0:
        raise AssertionError("der Tassenboden ist nicht oben geschlossen")
    unten = Part.makeCylinder(d / 2.0 - 4.0, 1.0, Vector(0, 0, 0.5))
    if tasse.common(unten).Volume > 1.0:
        raise AssertionError("die Tasse ist unten zu, dort gehoert der HVA "
                             "hinein")

    # Der Kraftweg ist gerade: alle drei Punkte auf einer Achse.
    for name in ("nocken", "ventil", "fuehrung"):
        p = t.punkt(name)
        if abs(p.ort.x) > 1e-9 or abs(p.ort.y) > 1e-9:
            raise AssertionError("%s liegt nicht auf der Achse (%.3f, %.3f)"
                                 % (name, p.ort.x, p.ort.y))
        if abs(abs(p.achse.z) - 1.0) > 1e-9:
            raise AssertionError("%s zeigt nicht in Achsrichtung" % name)
    if t.punkt("nocken").achse.z * t.punkt("ventil").achse.z > 0:
        raise AssertionError("Nocken- und Ventilseite muessen in "
                             "entgegengesetzte Richtungen zeigen")

    # Der HVA muss Platz zum Nachstellen haben.
    if hva.BoundBox.ZLength > h - bt - weg + 0.01:
        raise AssertionError("der Ausgleichskolben fuellt die Tasse aus, "
                             "kein Weg zum Nachstellen")
    luft = (h - bt) - hva.BoundBox.ZLength
    if abs(luft - weg) > 0.05:
        raise AssertionError("Ausgleichsweg %.2f statt %.1f mm" % (luft, weg))

    # Der HVA darf in der Tasse nicht klemmen.
    if tasse.common(hva).Volume > 1.0:
        raise AssertionError("HVA und Tasse durchdringen sich")

    # Unsinnige Eingaben.
    for kw in ({"hoehe": 5.0}, {"hva_d": 40.0}, {"wand": 30.0}):
        try:
            baue(**kw)
            raise AssertionError("unsinnige Eingabe blieb unbemerkt: %r" % kw)
        except ValueError:
            pass

    return ("Stoessel-Selbsttest bestanden (d %.0f, %.0f mm hoch, "
            "Ausgleichsweg %.1f mm)" % (d, h, luft))
