# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Auslegung eines Stirnradgetriebes: Durchmesser, Achsabstand, Gehäusemaße.

Reine Rechenhilfe, keine Geometrie — nutzbar als Werkzeug der Workbench.

Der wichtigste Punkt steckt in :func:`gangpaare`: Alle Gänge eines
Vorgelegegetriebes sitzen auf **denselben zwei Wellen**, also muss jedes
Radpaar denselben Achsabstand haben. Das heißt ``z1 + z2 = konstant``. Wer die
Zähnezahlen frei wählt (12/36, 14/42, 16/48 …), bekommt für jeden Gang einen
anderen Achsabstand — solche Räder lassen sich nicht auf zwei parallele Wellen
setzen.
"""

import math


def teilkreis(modul, zaehne):
    """Teilkreisdurchmesser d = m · z [mm]."""
    return float(modul) * int(zaehne)


def kopfkreis(modul, zaehne):
    """Kopfkreisdurchmesser d_a = m · (z + 2) [mm]."""
    return float(modul) * (int(zaehne) + 2.0)


def fusskreis(modul, zaehne, kopfspiel=0.25):
    """Fußkreisdurchmesser d_f = m · (z − 2 − 2·c) [mm], c = Kopfspielfaktor."""
    return float(modul) * (int(zaehne) - 2.0 - 2.0 * float(kopfspiel))


def achsabstand(modul, z1, z2):
    """Achsabstand a = m · (z1 + z2) / 2 [mm]."""
    return float(modul) * (int(z1) + int(z2)) / 2.0


def uebersetzung(z1, z2):
    """Übersetzung i = z2 / z1 (>1 bedeutet Untersetzung)."""
    return float(z2) / float(z1)


def gangpaare(zaehne_summe, gaenge, z_min=12):
    """Zähnezahlpaare für ``gaenge`` Stufen mit gleichem Achsabstand.

    Alle Paare erfüllen ``z1 + z2 == zaehne_summe``, laufen also auf demselben
    Achsabstand. Zurück kommt eine Liste ``[(z1, z2, i), …]``, vom längsten
    zum kürzesten Gang.
    """
    summe = int(zaehne_summe)
    n = int(gaenge)
    if n < 1:
        raise ValueError("mindestens ein Gang")
    if summe < 2 * int(z_min) + 2 * (n - 1):
        raise ValueError("Zähnesumme zu klein für %d Gänge" % n)
    schritt = max(1, (summe - 2 * int(z_min)) // (2 * n) or 1)
    paare = []
    for k in range(n):
        z1 = int(z_min) + k * schritt
        z2 = summe - z1
        if z2 < int(z_min):
            raise ValueError("Zähnezahl unter Minimum bei Gang %d" % (k + 1))
        paare.append((z1, z2, uebersetzung(z1, z2)))
    return paare


def radbreite_gesamt(gaenge, breite, luft):
    """Axiale Baulänge aller Radpaare inklusive Luft dazwischen [mm]."""
    n = int(gaenge)
    return n * float(breite) + max(0, n - 1) * float(luft)


def gehaeuse_innenmass(modul, zaehne_summe, gaenge, breite, luft, abstand):
    """Innenmaße des Gehäuses (Länge, Breite, Höhe) [mm].

    ``abstand`` ist der geforderte Freiraum rings um die Räder. Länge folgt der
    Wellenachse, Höhe dem Achsabstand plus den beiden Kopfkreisradien.
    """
    a = achsabstand(modul, zaehne_summe // 2, zaehne_summe - zaehne_summe // 2)
    d_max = kopfkreis(modul, zaehne_summe - int(zaehne_summe * 0.25))
    laenge = radbreite_gesamt(gaenge, breite, luft) + 2.0 * float(abstand)
    breite_innen = d_max + 2.0 * float(abstand)
    hoehe = a + d_max + 2.0 * float(abstand)
    return laenge, breite_innen, hoehe


def gehaeuse_aussenmass(innen, wand):
    """Außenmaße aus Innenmaßen und Wandstärke [mm]."""
    w = float(wand)
    return tuple(float(x) + 2.0 * w for x in innen)


def selbsttest():
    """Prüft die Formeln gegen von Hand gerechnete Werte."""
    # Modul 2, 20 Zähne: d = 40, d_a = 44, d_f = 2*(20-2-0.5) = 35
    assert abs(teilkreis(2, 20) - 40.0) < 1e-9
    assert abs(kopfkreis(2, 20) - 44.0) < 1e-9
    assert abs(fusskreis(2, 20) - 35.0) < 1e-9

    # Achsabstand 12/36 bei m=2: 2*48/2 = 48
    assert abs(achsabstand(2, 12, 36) - 48.0) < 1e-9
    assert abs(uebersetzung(12, 36) - 3.0) < 1e-9

    # Fünf Gänge mit gleicher Zähnesumme -> gleicher Achsabstand
    paare = gangpaare(48, 5)
    assert len(paare) == 5, paare
    for z1, z2, i in paare:
        assert z1 + z2 == 48, (z1, z2)
        assert abs(achsabstand(2, z1, z2) - 48.0) < 1e-9
        assert abs(i - z2 / z1) < 1e-12
    # vom laengsten zum kuerzesten Gang
    assert paare[0][2] > paare[-1][2], paare

    # Baulaenge: 5 Raeder a 10 mm mit 2 mm Luft = 50 + 8 = 58
    assert abs(radbreite_gesamt(5, 10, 2) - 58.0) < 1e-9

    # Gehaeuse: Innenlaenge = 58 + 2*3 = 64
    innen = gehaeuse_innenmass(2, 48, 5, 10, 2, 3)
    assert abs(innen[0] - 64.0) < 1e-9, innen
    aussen = gehaeuse_aussenmass(innen, 4)
    for i, a in zip(innen, aussen):
        assert abs(a - (i + 8.0)) < 1e-9
    return True


def gehaeuse_aus_raedern(modul, paare, breite, luft, abstand, achsabstand):
    """Exakte Innenmaße und Achslage aus dem tatsächlichen Radsatz.

    Anders als :func:`gehaeuse_innenmass`, das nur grob abschätzt, rechnet
    dies mit den größten wirklich vorkommenden Kopfkreisen je Welle. Das ist
    nötig, weil die Achsen bei ungleich großen Rädern **nicht** mittig liegen.

    Rückgabe: ``(innen_l, innen_b, innen_h, achs_z_unten)``.
    """
    r_oben = max(kopfkreis(modul, z1) for z1, _z2, _i in paare) / 2.0
    r_unten = max(kopfkreis(modul, z2) for _z1, z2, _i in paare) / 2.0
    innen_l = radbreite_gesamt(len(paare), breite, luft) + 2.0 * float(abstand)
    innen_b = 2.0 * max(r_oben, r_unten) + 2.0 * float(abstand)
    innen_h = r_unten + float(achsabstand) + r_oben + 2.0 * float(abstand)
    achs_z = float(abstand) + r_unten
    return innen_l, innen_b, innen_h, achs_z


def selbsttest_raeder():
    """Prüft die genaue Gehäuserechnung am Fünfgang-Satz."""
    paare = gangpaare(48, 5)
    a = achsabstand(2, *paare[0][:2])
    il, ib, ih, az = gehaeuse_aus_raedern(2, paare, 10, 2, 3, a)
    # groesstes Rad unten: z=36 -> d_a = 76, r = 38; oben z=20 -> r = 22
    assert abs(il - 64.0) < 1e-9, il
    assert abs(ib - (76.0 + 6.0)) < 1e-9, ib
    assert abs(ih - (38.0 + 48.0 + 22.0 + 6.0)) < 1e-9, ih
    assert abs(az - 41.0) < 1e-9, az
    # das groesste Rad passt unten hinein und oben heraus nicht an
    assert az - 38.0 >= 3.0 - 1e-9
    assert ih - (az + a) - 22.0 >= 3.0 - 1e-9
    return True
