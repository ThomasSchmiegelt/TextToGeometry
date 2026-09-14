# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Getriebewelle: durchgehender Zylinder mit Lagersitzen an den Enden."""

T2G_SKILL = {
    "name": "welle",
    "description": "Welle mit abgesetzten Lagersitzen: Laenge, "
                   "Wellendurchmesser, Sitzdurchmesser und Sitzlaenge.",
    "params": [
        ("laenge",   "Gesamtlaenge",          "mm", 120.0, 5.0, 2000.0),
        ("welle_d",  "Wellendurchmesser",     "mm", 15.0,  2.0, 300.0),
        ("sitz_d",   "Lagersitzdurchmesser",  "mm", 12.0,  1.0, 300.0),
        ("sitz_l",   "Lagersitzlaenge",       "mm", 10.0,  0.0, 200.0),
    ],
    "dependencies": ["Part", "FreeCAD"],
    "pruefregeln": ["konnektivitaet"],
    "achse": "z",
}


def build(params):
    laenge = float(params["laenge"])
    welle_d = float(params["welle_d"])
    sitz_d = float(params["sitz_d"])
    sitz_l = min(float(params["sitz_l"]), laenge / 2.0 - 0.5)

    if sitz_l <= 0.0:
        return [Part.makeCylinder(welle_d / 2.0, laenge)]

    mitte = Part.makeCylinder(welle_d / 2.0, laenge - 2.0 * sitz_l,
                              FreeCAD.Vector(0, 0, sitz_l))
    links = Part.makeCylinder(sitz_d / 2.0, sitz_l)
    rechts = Part.makeCylinder(sitz_d / 2.0, sitz_l,
                               FreeCAD.Vector(0, 0, laenge - sitz_l))
    return [mitte.fuse(links).fuse(rechts).removeSplitter()]
