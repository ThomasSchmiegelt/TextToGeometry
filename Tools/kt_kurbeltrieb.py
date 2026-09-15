# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kurbeltrieb — Kurbelwelle, Pleuel und Kolben als eine Baugruppe.

    teile, proben, kw, zylinder_x = baue(bauform="V8", hub=86.0, ...)

Das ist der Motor ohne Kopf: was sich dreht und was auf und ab geht. Der
Ventiltrieb (``kt_ventiltrieb``) setzt darauf auf, und ``kt_motor`` fügt
beides zusammen.

Zusammengebaut wird über die Andockpunkte, nicht über gerechnete Koordinaten:

    Kurbelwelle.hubzapfen_k  ← Pleuel.hubzapfen
    Pleuel.kolbenbolzen      → Kolben.bolzen

Der **Kolben** läuft auf der Zylinderachse, nicht das Pleuel — das steht
schräg, und genau das ist der Schubkurbeltrieb. Gerichtet wird deshalb beides
mit ``kt_schnittstelle.richte()``: andocken, dann um den Anschluss drehen,
bis das andere Ende dort liegt, wo es hingehört.

Zurück kommen außer den Körpern auch ``zylinder_x`` — wo jeder Zylinder
wirklich steht. Beim V-Motor sind die beiden Pleuel eines Hubzapfens um die
halbe Breite versetzt; mit der Zapfenlage gerechnet standen die Ventile 28 mm
neben ihrem Kolben.
"""

import FreeCAD
from FreeCAD import Vector

import kt_bauformen as B
import kt_kinematik as K
import kt_kolben
import kt_kurbelwelle
import kt_pleuel
import kt_schnittstelle as S


def zapfenbreite(bauform, pleuel_breite):
    """Breite eines Hubzapfens [mm].

    Beim V-Motor teilen sich zwei Pleuel einen Hubzapfen — er muss also
    doppelt so breit sein, und die beiden sitzen NEBENEINANDER.
    Übereinander gesetzt durchdrangen sie sich zu 53,6 %.
    """
    return (2.0 * float(pleuel_breite) + 4.0) if B.ist_v(bauform) else 26.0


def baue(bauform="R4", bohrung=86.0, hub=86.0, stichmass=150.5,
         kompressionshoehe=32.0, zylinderabstand=101.5, bolzen_d=22.0,
         hubzapfen_d=48.0, hauptlager_d=54.0, pleuel_breite=22.0,
         v8_kreuzebene=True, ventiltaschen=None):
    """Kurbelwelle, Pleuel und Kolben.

    Liefert ``(teile, proben, kurbelwelle, zylinder_x)``:

    teile       [(Bezeichnung, Shape), …]
    proben      [(Punkt A, Punkt B), …] für die Paarungsprüfung
    kurbelwelle das :class:`kt_schnittstelle.Bauteil` — der Ventiltrieb
                braucht seinen Steuertriebzapfen, der Motor den Flansch
    zylinder_x  {Zylindernummer: x-Lage} — wo der Kolben wirklich sitzt
    """
    l = float(stichmass)
    pleuel_b = float(pleuel_breite)
    teile = []
    proben = []

    kw = kt_kurbelwelle.baue(bauform=bauform, hub=hub,
                             zylinderabstand=zylinderabstand,
                             hauptlager_d=hauptlager_d,
                             hubzapfen_d=hubzapfen_d,
                             hubzapfen_b=zapfenbreite(bauform, pleuel_b),
                             v8_kreuzebene=v8_kreuzebene)
    teile.extend(kw.koerper)

    # Einmal gebaut und dann kopiert: eine Ventilfeder zu bauen dauert
    # Sekunden, und ein V12 mit vier Ventilen braeuchte achtundvierzig.
    kolben_muster = kt_kolben.baue(bohrung=bohrung,
                                   kompressionshoehe=kompressionshoehe,
                                   bolzen_d=bolzen_d,
                                   ventiltaschen=list(ventiltaschen or []))
    pleuel_muster = kt_pleuel.baue(stichmass=l, hubzapfen_d=hubzapfen_d,
                                   bolzen_d=bolzen_d, breite=pleuel_b)

    lagen = B.zylinderlagen(bauform, zylinderabstand, v8_kreuzebene)
    versatz = B.hubzapfenversatz(bauform, v8_kreuzebene)
    zylinder_x = {}

    for nr, (seite, _x, bankwinkel, zapfen) in enumerate(lagen, 1):
        # Welchen Hubzapfen? Bei geteiltem Zapfen die Haelfte der Bank.
        name = "hubzapfen_%d" % (zapfen + 1)
        if versatz and B.ist_v(bauform):
            name = "hubzapfen_%d%s" % (zapfen + 1, "a" if seite == 0 else "b")
        ziel = kw.punkt(name)
        if B.ist_v(bauform) and not versatz:
            # Ungeteilter Zapfen: die beiden Baenke nebeneinander setzen.
            ziel = S.Punkt(ziel.name,
                           Vector(ziel.ort).add(Vector(
                               (pleuel_b / 2.0) * (-1.0 if seite == 0
                                                   else 1.0), 0, 0)),
                           ziel.achse, ziel.art, ziel.mass, ziel.hinweis)

        # Der KOLBEN laeuft auf der Zylinderachse, nicht das Pleuel. Vorher
        # war das Pleuel parallel zur Zylinderachse gerichtet, und die
        # Kolben einer Bank lagen dadurch nicht auf einer Linie: bei Bank A
        # eines V8 auf (-100,8|143,8), (-143,8|100,8), (-57,8|100,8) statt
        # auf der Bankachse.
        richtung = K.zylinderachse(bankwinkel)
        pleuel = S.richte(pleuel_muster, "hubzapfen", "kolbenbolzen", ziel,
                          K.pleuelrichtung(ziel.ort, richtung, l))
        teile.extend([("Pleuel %d" % nr, s) for _n, s in pleuel.koerper])
        proben.append((pleuel.punkt("hubzapfen"), ziel))

        # Andocken legt die Verdrehung UM die Bolzenachse nicht fest — die
        # kuerzeste Drehung traf beim Reihenmotor zufaellig, beim V-Motor
        # nicht, und die Ventiltaschen standen schief zu den Ventilen
        # (11 bis 24 % Durchdringung). Deshalb wird der Kolben wie das
        # Pleuel ausgerichtet: sein Boden zeigt die Zylinderachse entlang.
        kolben = S.richte(kolben_muster, "bolzen", "boden",
                          pleuel.punkt("kolbenbolzen"), richtung)
        teile.extend([("Kolben %d" % nr, s) for _n, s in kolben.koerper])
        proben.append((kolben.punkt("bolzen"), pleuel.punkt("kolbenbolzen")))
        zylinder_x[nr] = kolben.punkt("bolzen").ort.x

    return teile, proben, kw, zylinder_x


def selbsttest(bauform="V8"):
    """Baut einen Kurbeltrieb und misst die Zusagen nach."""
    import math

    teile, proben, kw, zylinder_x = baue(bauform=bauform)
    z, bank = B.daten(bauform)
    if len(zylinder_x) != z:
        raise AssertionError("%d Zylinder statt %d" % (len(zylinder_x), z))
    for wort, soll in (("Kolben", z), ("Pleuel", z)):
        ist = sum(1 for n, _s in teile if n.startswith(wort))
        if ist != soll:
            raise AssertionError("%d %s fuer %d Zylinder" % (ist, wort, soll))
    if not all(s.Solids for _n, s in teile):
        raise AssertionError("nicht jeder Koerper ist ein Solid")

    # Jede Paarung muss wirklich aufeinanderliegen.
    for a, b in proben:
        ok, text = S.pruefe_paarung(a, b)
        if not ok:
            raise AssertionError(text)

    # Die Kolben einer Bank liegen auf ihrer Bankachse — beim 90-Grad-V8
    # also auf |y| = |z|. Das ist die Probe auf die Schubkurbel: mit einem
    # zur Zylinderachse parallelen Pleuel stimmt es nicht.
    if B.ist_v(bauform):
        lagen = B.zylinderlagen(bauform, 101.5, True)
        for nr, (seite, _x, bw, _zapfen) in enumerate(lagen, 1):
            k = [s for n, s in teile if n == "Kolben %d" % nr][0]
            b = k.BoundBox
            y = (b.YMin + b.YMax) / 2.0
            zz = (b.ZMin + b.ZMax) / 2.0
            soll = math.tan(math.radians(bw))
            if abs(y - zz * soll) > 1.0:
                raise AssertionError(
                    "Kolben %d (Bank %d) liegt bei (%.1f|%.1f), nicht auf "
                    "der Bankachse" % (nr, seite + 1, y, zz))

    # Der Steuertriebzapfen und der Abtriebsflansch muessen da sein — der
    # Ventiltrieb und das Getriebe haengen daran.
    for pflicht in ("steuertrieb", "abtrieb"):
        kw.punkt(pflicht)
    return ("Kurbeltrieb-Selbsttest bestanden (%s, %d Koerper, %d Paarungen)"
            % (bauform, len(teile), len(proben)))
