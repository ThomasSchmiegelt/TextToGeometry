# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Getriebegehaeuse: Hohlquader mit Wellendurchbruechen."""

T2G_SKILL = {
    "name": "gehaeuse",
    "description": "Gehaeuse als Hohlquader. Die Innenmasse sind der "
                   "Freiraum um die Raeder, die Wandstaerke kommt aussen "
                   "hinzu. Zwei Wellendurchbrueche in den Stirnwaenden, "
                   "Hoehe der unteren Achse frei waehlbar.",
    "params": [
        ("innen_l",     "Innenlaenge (Wellenachse)", "mm", 64.0, 10.0, 2000.0),
        ("innen_b",     "Innenbreite",               "mm", 82.0, 10.0, 2000.0),
        ("innen_h",     "Innenhoehe",                "mm", 130.0, 10.0, 2000.0),
        ("wand",        "Wandstaerke",               "mm", 4.0,  1.0,  100.0),
        ("welle_d",     "Durchbruch fuer die Welle", "mm", 16.0, 1.0,  300.0),
        ("achsabstand", "Achsabstand der Wellen",    "mm", 48.0, 1.0,  1000.0),
        ("achs_z",      "Hoehe der unteren Welle",   "mm", 41.0, 0.0,  2000.0),
    ],
    "dependencies": ["Part", "FreeCAD"],
    "pruefregeln": ["konnektivitaet"],
}


def build(params):
    il = float(params["innen_l"])
    ib = float(params["innen_b"])
    ih = float(params["innen_h"])
    wand = float(params["wand"])
    welle_d = float(params["welle_d"])
    a = float(params["achsabstand"])

    aussen = Part.makeBox(il + 2.0 * wand, ib + 2.0 * wand, ih + 2.0 * wand,
                          FreeCAD.Vector(-wand, -wand, -wand))
    innen = Part.makeBox(il, ib, ih)
    koerper = aussen.cut(innen)

    # Die untere Achse wird ausdruecklich angegeben: bei ungleich grossen
    # Raedern liegt sie nicht mittig, sonst ragt das groesste Rad unten heraus.
    y = ib / 2.0
    z_unten = float(params["achs_z"])
    z_oben = z_unten + a
    for z in (z_unten, z_oben):
        bohrung = Part.makeCylinder(
            welle_d / 2.0, il + 4.0 * wand,
            FreeCAD.Vector(-2.0 * wand, y, z), FreeCAD.Vector(1, 0, 0))
        koerper = koerper.cut(bohrung)
    return [koerper.removeSplitter()]
