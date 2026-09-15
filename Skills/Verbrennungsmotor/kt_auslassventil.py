# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Auslassventil — kleiner, tulpenförmig, mit hohlem Schaft.

Das Auslassventil ist das **heiße** Ventil: durch es strömt das verbrannte
Gas ab, der Tellerrand wird 700…800 °C warm, und die Wärme kann nur über den
Sitz und über den Schaft weg. Daraus folgt alles, worin es sich vom
Einlassventil unterscheidet:

* **kleiner** (0,38·D bzw. 0,31·D statt 0,45/0,36) — die Ausschiebearbeit
  leistet der Kolben, für den Auslass zählt die Fläche weniger.
* **dickerer Schaft** — er leitet die Wärme ab und trägt sie in die Führung.
* **Tulpenform** statt geradem Kegel: der Übergang zum Schaft ist hohl
  gewölbt, das bringt Material an den heißen Tellerrand.
* **hohler, natriumgefüllter Schaft** — der geschlossene Hohlraum ist zur
  Hälfte mit Natrium gefüllt, das bei 98 °C schmilzt und beim Auf und Ab die
  Wärme vom Teller zur Führung schaufelt. Hier wird der Hohlraum gebaut, die
  Füllung nicht; der Körper bleibt ein Solid mit einer zweiten Schale.

Gebaut wird entlang **+Z**, Schaft nach oben, Ursprung in der
Tellerunterkante. Grundform und Anschlusspunkte kommen aus ``kt_ventil``.

Anschlusspunkte
    ``sitz``        Tellerunterkante, Achse -Z, Art *flaeche*
    ``schaft``      Schaftmitte, Achse +Z, Art *welle*
    ``schaft_ende`` Schaftende, Achse +Z, Art *flaeche*
"""

import kt_ventil

#: Tellerdurchmesser als Anteil der Bohrung, nach Ventilzahl.
ANTEIL = {2: 0.38, 4: 0.31}

#: Schaftdurchmesser als Anteil der BOHRUNG — dicker als beim Einlass, denn
#: über ihn geht die Wärme weg. Am Teller gemessen käme das Gegenteil heraus:
#: der Auslassteller ist der kleinere.
SCHAFT_ANTEIL = 0.080

#: Anteil des Schaftdurchmessers, den die Natriumbohrung einnimmt.
HOHL_ANTEIL = 0.55


def vorschlag(bohrung=86.0, ventile_je_zylinder=4):
    """Üblicher Tellerdurchmesser [mm]."""
    anteil = ANTEIL[4 if int(ventile_je_zylinder) >= 4 else 2]
    return round(float(bohrung) * anteil, 1)


def schaftvorschlag(bohrung=86.0):
    """Üblicher Schaftdurchmesser zu dieser Bohrung [mm]."""
    return round(max(5.5, float(bohrung) * SCHAFT_ANTEIL), 1)


def kennwerte(bohrung=86.0, ventile_je_zylinder=4, laenge=110.0, **_rest):
    d = vorschlag(bohrung, ventile_je_zylinder)
    s = schaftvorschlag(bohrung)
    k = kt_ventil.kennwerte(d, s, laenge)
    k["art"] = "auslass"
    k["hohl"] = True
    k["hohl_d"] = round(s * HOHL_ANTEIL, 2)
    return k


def baue(bohrung=86.0, ventile_je_zylinder=4, teller_d=0.0, schaft_d=0.0,
         laenge=110.0, natriumgefuellt=True, name="Auslassventil"):
    """Ein Auslassventil als :class:`kt_schnittstelle.Bauteil`.

    bohrung              Zylinderbohrung [mm] — daraus folgt der Teller
    ventile_je_zylinder  2 oder 4
    teller_d, schaft_d   0 = aus der Bohrung vorschlagen
    laenge               Tellerunterkante bis Schaftende [mm]
    natriumgefuellt      False baut den Schaft voll (einfaches Serienventil)
    """
    d = float(teller_d) or vorschlag(bohrung, ventile_je_zylinder)
    s = float(schaft_d) or schaftvorschlag(bohrung)
    hohl = round(s * HOHL_ANTEIL, 2) if natriumgefuellt else 0.0
    # Bleibt zu wenig Wand, wird der Schaft lieber voll gebaut als duenn
    # gerechnet — ein 0,3-mm-Rohr gibt es nicht.
    if hohl and hohl / 2.0 >= s / 2.0 - 0.8:
        hohl = 0.0
    t = kt_ventil.baue(teller_d=d, schaft_d=s, laenge=float(laenge),
                       kegel_form=2.0, hohl_d=hohl, name=name)
    t.kennwerte["art"] = "auslass"
    t.kennwerte["hohl"] = bool(hohl)
    t.kennwerte["hohl_d"] = hohl
    return t


def selbsttest():
    """Prüft Maße, Tulpenform und den geschlossenen Hohlraum."""
    import kt_einlassventil

    t = baue(bohrung=86.0, ventile_je_zylinder=4)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Auslassventil ist kein Solid")
    d = vorschlag(86.0, 4)
    if abs(shp.BoundBox.XLength - d) > 0.1:
        raise AssertionError("Teller %.2f statt %.1f mm"
                             % (shp.BoundBox.XLength, d))

    # Kleiner als der Einlass, aber mit dickerem Schaft — das ist der
    # Unterschied, um den es geht.
    ein = kt_einlassventil.baue(bohrung=86.0, ventile_je_zylinder=4)
    if not d < ein.kennwerte["teller_d"]:
        raise AssertionError("das Auslassventil muss kleiner sein als das "
                             "Einlassventil (%.1f gegen %.1f)"
                             % (d, ein.kennwerte["teller_d"]))
    if not t.kennwerte["schaft_d"] > ein.kennwerte["schaft_d"]:
        raise AssertionError("der Auslassschaft muss dicker sein (%.1f gegen "
                             "%.1f)" % (t.kennwerte["schaft_d"],
                                        ein.kennwerte["schaft_d"]))

    # Der Hohlraum: eine zweite Schale, und er darf NIRGENDS nach aussen
    # durchbrechen — sonst liefe das Natrium aus und der Stoessel druecke
    # auf ein Loch.
    if not t.kennwerte["hohl"]:
        raise AssertionError("der Natriumschaft fehlt")
    if len(shp.Shells) != 2:
        raise AssertionError("der Hohlraum ist nicht geschlossen (%d "
                             "Schalen statt 2)" % len(shp.Shells))
    # Und er ist wirklich hohl: das Volumen liegt unter dem des vollen
    # Ventils mit denselben Massen.
    voll = baue(bohrung=86.0, ventile_je_zylinder=4, natriumgefuellt=False)
    fehlt = voll.koerper[0][1].Volume - shp.Volume
    if fehlt < 500.0:
        raise AssertionError("die Natriumbohrung nimmt nur %.0f mm^3 weg"
                             % fehlt)

    # Tulpenform: bei gleichem Teller und Schaft hat sie weniger Material
    # im Uebergang als der gerade Kegel.
    gerade = kt_ventil.baue(teller_d=d, schaft_d=t.kennwerte["schaft_d"],
                            laenge=110.0, kegel_form=1.0)
    tulpe = kt_ventil.baue(teller_d=d, schaft_d=t.kennwerte["schaft_d"],
                           laenge=110.0, kegel_form=2.0)
    if not tulpe.koerper[0][1].Volume < gerade.koerper[0][1].Volume:
        raise AssertionError("die Tulpenform ist nicht schlanker als der "
                             "gerade Kegel (%.0f gegen %.0f mm^3)"
                             % (tulpe.koerper[0][1].Volume,
                                gerade.koerper[0][1].Volume))

    for pflicht in ("sitz", "schaft", "schaft_ende"):
        t.punkt(pflicht)
    return ("Auslassventil-Selbsttest bestanden (Teller %.1f, Schaft %.1f, "
            "Natriumbohrung %.1f mm nimmt %.0f mm^3, Tulpe %.0f gegen %.0f "
            "mm^3)" % (d, t.kennwerte["schaft_d"], t.kennwerte["hohl_d"],
                       fehlt, tulpe.koerper[0][1].Volume,
                       gerade.koerper[0][1].Volume))
