# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Stirnrad mit gerader Verzahnung, Nabe und Bohrung."""

import math

T2G_SKILL = {
    "name": "zahnrad",
    "description": "Stirnrad: Modul, Zaehnezahl, Breite, Nabe und Bohrung. "
                   "Zahnflanken als Trapez angenaehert (kein Evolventenprofil).",
    "params": [
        ("modul",   "Modul",                "mm", 2.0,  0.3,  20.0),
        ("zaehne",  "Zaehnezahl",           "-",  20,   6,    200),
        ("breite",  "Zahnbreite",           "mm", 10.0, 1.0,  200.0),
        ("bohrung", "Bohrungsdurchmesser",  "mm", 15.0, 0.0,  400.0),
        ("nabe_d",  "Nabendurchmesser",     "mm", 26.0, 0.0,  600.0),
        ("nabe_b",  "Nabenbreite",          "mm", 16.0, 0.0,  300.0),
    ],
    "dependencies": ["Part", "FreeCAD"],
    "pruefregeln": ["konnektivitaet"],
    "achse": "z",
}


def _zahn_flaeche(r_fuss, r_teil, r_kopf, m, z, winkel):
    """Eine Zahnkontur als ebene Flaeche, um `winkel` gedreht."""
    # Zahndicke am Teilkreis ist die halbe Teilung: s = m*pi/2
    a_teil = math.pi / (2.0 * z)                 # halber Winkel am Teilkreis
    a_kopf = a_teil * 0.45 * r_teil / max(r_kopf, 1e-6)
    a_fuss = a_teil * 1.35 * r_teil / max(r_fuss, 1e-6)
    punkte = [(r_fuss, -a_fuss), (r_teil, -a_teil), (r_kopf, -a_kopf),
              (r_kopf, a_kopf), (r_teil, a_teil), (r_fuss, a_fuss)]
    ecken = []
    for r, a in punkte:
        w = a + winkel
        ecken.append(FreeCAD.Vector(r * math.cos(w), r * math.sin(w), 0))
    ecken.append(ecken[0])
    return Part.Face(Part.makePolygon(ecken))


def build(params):
    modul = float(params["modul"])
    zaehne = int(params["zaehne"])
    breite = float(params["breite"])
    bohrung = float(params["bohrung"])
    nabe_d = float(params["nabe_d"])
    nabe_b = float(params["nabe_b"])

    r_teil = modul * zaehne / 2.0
    r_kopf = r_teil + modul
    r_fuss = max(0.6 * modul, r_teil - 1.25 * modul)

    koerper = Part.makeCylinder(r_fuss, breite)
    for i in range(zaehne):
        zahn = _zahn_flaeche(r_fuss * 0.98, r_teil, r_kopf, modul, zaehne,
                             2.0 * math.pi * i / zaehne)
        koerper = koerper.fuse(zahn.extrude(FreeCAD.Vector(0, 0, breite)))

    # Nabe mittig zur Radbreite, falls sie ueber die Breite hinausragt
    if nabe_d > 2.0 * r_fuss and nabe_b > 0.0:
        z0 = (breite - nabe_b) / 2.0
        nabe = Part.makeCylinder(nabe_d / 2.0, nabe_b,
                                 FreeCAD.Vector(0, 0, z0))
        koerper = koerper.fuse(nabe)
    laenge = max(breite, nabe_b)

    if bohrung > 0.0:
        loch = Part.makeCylinder(bohrung / 2.0, laenge + 2.0,
                                 FreeCAD.Vector(0, 0, -1.0))
        koerper = koerper.cut(loch)
    return [koerper.removeSplitter()]
