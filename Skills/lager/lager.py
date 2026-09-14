# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Rillenkugellager: Innenring, Aussenring und Waelzkoerper als eigene Solids.

Frueher war das ein einzelner Ring mit einer angedeuteten Nut. Das sah aus
wie ein Lager, hatte aber weder Waelzkoerper noch Passung: die Bohrung war
exakt so gross wie die Welle, was geometrisch eine Nullpassung ist und in der
Kollisionspruefung als 3-5 % Ueberschneidung auftauchte.

``spiel`` ist der Schluessel dazu. Es geht an zwei Stellen ein: die Bohrung
wird um ``spiel`` groesser als ``innen_d``, und die Laufrille wird um
``spiel`` weiter als die Kugel. Damit beruehrt nichts das andere, und die
Baugruppenpruefung meldet das Lager nicht mehr als Kollision.
"""

import math

T2G_SKILL = {
    "name": "lager",
    "description": "Rillenkugellager: Innenring, Aussenring und Kugeln als "
                   "getrennte Solids, mit Laufrillen und Passungsspiel. "
                   "Die Bohrung ist um das Spiel groesser als innen_d, passt "
                   "also auf eine Welle mit genau diesem Durchmesser.",
    "params": [
        ("innen_d",  "Wellendurchmesser (Bohrung)", "mm", 12.0, 1.0, 400.0),
        ("aussen_d", "Aussendurchmesser",           "mm", 28.0, 2.0, 600.0),
        ("breite",   "Breite",                      "mm", 8.0,  0.5, 200.0),
        ("kugeln",   "Anzahl Waelzkoerper",         "Stk", 8,   3,   60),
        ("spiel",    "Passungsspiel",               "mm", 0.1,  0.0, 2.0),
    ],
    "dependencies": ["Part", "FreeCAD"],
    "pruefregeln": ["konnektivitaet"],
    "achse": "z",
}


def build(params):
    innen_d = float(params["innen_d"])
    aussen_d = max(float(params["aussen_d"]), innen_d + 4.0)
    breite = float(params["breite"])
    kugeln = max(3, int(params["kugeln"]))
    spiel = max(0.0, float(params["spiel"]))

    r_bohrung = innen_d / 2.0 + spiel      # geht auf eine Welle von innen_d
    r_aussen = aussen_d / 2.0
    r_mitte = (r_bohrung + r_aussen) / 2.0  # Teilkreis der Kugeln
    z_mitte = breite / 2.0

    # Die Kugel darf weder radial noch axial anstossen.
    r_kugel = min(0.30 * (r_aussen - r_bohrung), 0.40 * breite)
    r_rille = r_kugel + spiel               # Laufrille, um das Spiel weiter

    # Ringschultern bleiben stehen; die Rille schneidet den Durchgang frei.
    r_innenring_a = r_mitte - 0.15 * r_kugel
    r_aussenring_i = r_mitte + 0.15 * r_kugel + spiel

    def ring(r_i, r_a):
        k = Part.makeCylinder(r_a, breite)
        return k.cut(Part.makeCylinder(r_i, breite + 2.0,
                                       FreeCAD.Vector(0, 0, -1.0)))

    rille = Part.makeTorus(r_mitte, r_rille)
    rille.translate(FreeCAD.Vector(0, 0, z_mitte))

    innenring = ring(r_bohrung, r_innenring_a).cut(rille)
    aussenring = ring(r_aussenring_i, r_aussen).cut(rille)

    teile = [innenring.removeSplitter(), aussenring.removeSplitter()]
    for i in range(kugeln):
        w = 2.0 * math.pi * i / kugeln
        teile.append(Part.makeSphere(
            r_kugel, FreeCAD.Vector(r_mitte * math.cos(w),
                                    r_mitte * math.sin(w), z_mitte)))
    return teile
