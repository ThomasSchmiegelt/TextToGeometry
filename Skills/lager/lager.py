# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Waelzlager, vereinfacht als Ring mit angedeuteter Laufbahn."""

T2G_SKILL = {
    "name": "lager",
    "description": "Lager als Ring: Innen- und Aussendurchmesser, Breite, "
                   "mit umlaufender Nut als Laufbahn.",
    "params": [
        ("innen_d", "Innendurchmesser",  "mm", 12.0, 1.0,  400.0),
        ("aussen_d", "Aussendurchmesser", "mm", 28.0, 2.0,  600.0),
        ("breite",  "Breite",            "mm", 8.0,  0.5,  200.0),
        ("nut_t",   "Nuttiefe aussen",   "mm", 1.0,  0.0,  20.0),
    ],
    "dependencies": ["Part", "FreeCAD"],
    "pruefregeln": ["konnektivitaet"],
    "achse": "z",
}


def build(params):
    innen_d = float(params["innen_d"])
    aussen_d = max(float(params["aussen_d"]), innen_d + 2.0)
    breite = float(params["breite"])
    nut_t = min(float(params["nut_t"]), (aussen_d - innen_d) / 4.0)

    ring = Part.makeCylinder(aussen_d / 2.0, breite)
    ring = ring.cut(Part.makeCylinder(innen_d / 2.0, breite + 2.0,
                                      FreeCAD.Vector(0, 0, -1.0)))
    if nut_t > 0.0:
        nut_b = breite / 3.0
        aussen_nut = Part.makeCylinder(aussen_d / 2.0 + 1.0, nut_b,
                                       FreeCAD.Vector(0, 0, (breite - nut_b) / 2.0))
        innen_nut = Part.makeCylinder(aussen_d / 2.0 - nut_t, nut_b + 2.0,
                                      FreeCAD.Vector(0, 0, (breite - nut_b) / 2.0 - 1.0))
        ring = ring.cut(aussen_nut.cut(innen_nut))
    return [ring.removeSplitter()]
