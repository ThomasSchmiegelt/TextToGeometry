# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Einlassventil — der große, leichte Flachteller.

Das Einlassventil ist das **größere** der beiden: es muss die Füllung
hereinlassen, und dafür zählt die Fläche. Es ist dabei das kühlere Ventil —
das einströmende Gemisch kühlt es — und darf deshalb leicht sein: dünner
Schaft, voller (nicht hohler) Werkstoff, gerader Übergang vom Teller zum
Schaft.

Übliche Teller (Anteil der Bohrung):

    zwei Ventile je Zylinder   0,45 · D
    vier Ventile je Zylinder   0,36 · D

Die Gesamtfläche ist beim Vierventiler trotz der kleineren Teller größer —
zwei Kreise mit 0,36·D haben mehr Fläche als einer mit 0,45·D.

Gebaut wird entlang **+Z**, Schaft nach oben, Ursprung in der
Tellerunterkante. Anschlusspunkte und Grundform kommen aus ``kt_ventil``;
hier stehen die Maße, die das Einlassventil zum Einlassventil machen.

Anschlusspunkte
    ``sitz``        Tellerunterkante, Achse -Z, Art *flaeche*
    ``schaft``      Schaftmitte, Achse +Z, Art *welle*
    ``schaft_ende`` Schaftende, Achse +Z, Art *flaeche*
"""

import kt_ventil

#: Tellerdurchmesser als Anteil der Bohrung, nach Ventilzahl.
ANTEIL = {2: 0.45, 4: 0.36}

#: Schaftdurchmesser als Anteil der BOHRUNG, nicht des Tellers. Dünner als
#: beim Auslass — das Einlassventil ist kühler und muss weniger Wärme
#: abführen. Am Teller gemessen käme Unsinn heraus: der Auslassteller ist
#: kleiner, sein Schaft aber dicker.
SCHAFT_ANTEIL = 0.070

#: Tragende Breite der Sitzflaeche [mm]. Der Einlass sitzt schmaler — er ist das kuehlere Ventil.
SITZBREITE = 1.5


def vorschlag(bohrung=86.0, ventile_je_zylinder=4):
    """Üblicher Tellerdurchmesser [mm]."""
    anteil = ANTEIL[4 if int(ventile_je_zylinder) >= 4 else 2]
    return round(float(bohrung) * anteil, 1)


def schaftvorschlag(bohrung=86.0):
    """Üblicher Schaftdurchmesser zu dieser Bohrung [mm]."""
    return round(max(5.0, float(bohrung) * SCHAFT_ANTEIL), 1)


def kennwerte(bohrung=86.0, ventile_je_zylinder=4, laenge=110.0, **_rest):
    d = vorschlag(bohrung, ventile_je_zylinder)
    k = kt_ventil.kennwerte(d, schaftvorschlag(bohrung), laenge)
    k["art"] = "einlass"
    k["hohl"] = False
    return k


def baue(bohrung=86.0, ventile_je_zylinder=4, teller_d=0.0, schaft_d=0.0,
         laenge=110.0, name="Einlassventil"):
    """Ein Einlassventil als :class:`kt_schnittstelle.Bauteil`.

    bohrung              Zylinderbohrung [mm] — daraus folgt der Teller
    ventile_je_zylinder  2 oder 4
    teller_d, schaft_d   0 = aus der Bohrung vorschlagen
    laenge               Tellerunterkante bis Schaftende [mm]
    """
    d = float(teller_d) or vorschlag(bohrung, ventile_je_zylinder)
    s = float(schaft_d) or schaftvorschlag(bohrung)
    t = kt_ventil.baue(teller_d=d, schaft_d=s, laenge=float(laenge),
                       sitzbreite=SITZBREITE,
                       kegel_form=1.0, hohl_d=0.0, name=name)
    t.kennwerte["art"] = "einlass"
    t.kennwerte["hohl"] = False
    return t


def selbsttest():
    """Prüft die Maße und dass der Schaft wirklich voll ist."""
    import Part
    from FreeCAD import Vector

    t = baue(bohrung=86.0, ventile_je_zylinder=4)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Einlassventil ist kein Solid")
    d = vorschlag(86.0, 4)
    if abs(shp.BoundBox.XLength - d) > 0.1:
        raise AssertionError("Teller %.2f statt %.1f mm"
                             % (shp.BoundBox.XLength, d))

    # Der Vierventilteller ist kleiner als der Zweiventilteller, die
    # Gesamtflaeche aber groesser — genau dafuer gibt es vier Ventile.
    if not vorschlag(86.0, 4) < vorschlag(86.0, 2):
        raise AssertionError("beim Vierventiler wird der Teller kleiner")
    flaeche4 = 2.0 * vorschlag(86.0, 4) ** 2
    flaeche2 = 1.0 * vorschlag(86.0, 2) ** 2
    if not flaeche4 > flaeche2:
        raise AssertionError("zwei kleine Teller muessen mehr Flaeche haben "
                             "als ein grosser, sonst waere der Aufwand "
                             "sinnlos")

    # Der Schaft ist VOLL: eine Probe mitten im Schaft muss ganz im
    # Material liegen. Ein Hohlschaft gehoert ans Auslassventil.
    s = t.kennwerte["schaft_d"]
    probe = Part.makeCylinder(s / 2.0 - 0.5, 20.0, Vector(0, 0, 45.0))
    if abs(shp.common(probe).Volume - probe.Volume) > 1.0:
        raise AssertionError("der Einlassschaft ist nicht voll")
    if len(shp.Shells) != 1:
        raise AssertionError("das Einlassventil hat einen Hohlraum (%d "
                             "Schalen)" % len(shp.Shells))

    # Sitzbreite und Tellerrand nach den Richtwerten.
    if abs(t.kennwerte["sitzbreite"] - SITZBREITE) > 1e-9:
        raise AssertionError("die Sitzbreite steht nicht in den Kennwerten")
    rand = t.kennwerte["tellerrand_h"] / d
    if not 0.04 <= rand <= 0.06:
        raise AssertionError("Tellerrand %.3f x Teller, Soll 0,04…0,06"
                             % rand)
    if not t.kennwerte["sitz_d"] < d:
        raise AssertionError("der Sitzdurchmesser muss unter dem Teller "
                             "liegen")

    for pflicht in ("sitz", "schaft", "schaft_ende"):
        t.punkt(pflicht)
    return ("Einlassventil-Selbsttest bestanden (Teller %.1f, Schaft %.1f, "
            "Sitz %.1f auf %.1f mm Breite, Rand %.2f mm, voll, %.0f mm^3)"
            % (d, s, t.kennwerte["sitz_d"], t.kennwerte["sitzbreite"],
               t.kennwerte["tellerrand_h"], shp.Volume))
