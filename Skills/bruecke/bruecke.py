# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Parametrische Schwingtorbruecke (einfach gelagert, n_vert+8 Solids)."""

import math

T2G_SKILL = {
    "name": "bruecke",
    "description": "Parametrische Bruecke (einfach gelagert) mit 2 Pfeilern, "
                   "Deck, senkrechten Stae, Obergurt und Schwingdiagonalen.",
    "params": [
        ("span",     "Gesamtspannweite (X)",       "mm", 2000, 100,   20000),
        ("depth",    "Laetiefe (Y)",               "mm", 400,  50,    5000),
        ("pier_h",   "Pfeilhoehe",                 "mm", 400,  20,    5000),
        ("pier_w",   "Pfeerechte",                 "mm", 150,  20,    2000),
        ("deck_t",   "Deckdcke",                   "mm", 100,  10,    1000),
        ("n_vert",   "Anzahl senkrechter Stae",    "-",  5,    3,     50),
        ("truss_h",  "Trughoehe",                  "mm", 600,  20,    10000),
        ("chord_t",  "Obergurtquerschnitt",        "mm", 80,   10,    2000),
        ("bar_w",    "Stabquerschnitt (Sae)",      "mm", 80,   10,    2000),
        ("dia_w",    "Diagonalenquerschnitt",      "mm", 60,   10,    2000),
    ],
    "dependencies": ["Part"],
    "pruefregeln": ["kollision", "konnektivitaet"],
}


def _diagonal(x1, z1, x2, z2, w, cy):
    """Winkelstab mit quadratischem Querschnitt von (x1,z1) nach (x2,z2)."""
    dx = x2 - x1
    dz = z2 - z1
    length = math.hypot(dx, dz)
    bar = Part.makeBox(length, w, w, FreeCAD.Vector(0, -w / 2.0, -w / 2.0))
    bar.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0),
               math.degrees(math.atan2(-dz, dx)))
    bar.translate(FreeCAD.Vector(x1, cy, z1))
    return bar


def build(params):
    span = float(params["span"])
    depth = float(params["depth"])
    pier_h = float(params["pier_h"])
    pier_w = float(params["pier_w"])
    deck_t = float(params["deck_t"])
    n_vert = int(params["n_vert"])
    truss_h = float(params["truss_h"])
    chord_t = float(params["chord_t"])
    bar_w = float(params["bar_w"])
    dia_w = float(params["dia_w"])

    cy = depth / 2.0
    bot = pier_h + deck_t
    top = bot + truss_h

    # Pfeiler unter den Auensehmen Stae (span/8 und 7span/8)
    x_end_l = span / 8.0
    x_end_r = span - x_end_l
    shapes = [
        Part.makeBox(pier_w, depth, pier_h,
                     FreeCAD.Vector(x_end_l - pier_w / 2.0, 0.0, 0.0)),
        Part.makeBox(pier_w, depth, pier_h,
                     FreeCAD.Vector(x_end_r - pier_w / 2.0, 0.0, 0.0)),
        # Bogendecke
        Part.makeBox(span, depth, deck_t, FreeCAD.Vector(0.0, 0.0, pier_h)),
    ]

    # Senkrechte Stae gleichmaesig zwischen span/8 und 7span/8
    xs = [x_end_l + i * (x_end_r - x_end_l) / (n_vert - 1) for i in range(n_vert)]
    for xc in xs:
        shapes.append(Part.makeBox(bar_w, bar_w, truss_h,
                                   FreeCAD.Vector(xc - bar_w / 2.0,
                                                  cy - bar_w / 2.0, bot)))
    # Obergurt von der ersten bis zur letzten Stabmittelpunkt
    shapes.append(Part.makeBox(x_end_r - x_end_l, chord_t, chord_t,
                               FreeCAD.Vector(x_end_l, cy - chord_t / 2.0, top)))

    # Schwingdiagonale (Zick-Zack) zwischen Stae
    for k in range(n_vert - 1):
        if k % 2 == 0:
            p1 = (xs[k + 1], bot)
            p2 = (xs[k], top)
        else:
            p1 = (xs[k], top)
            p2 = (xs[k + 1], bot)
        shapes.append(_diagonal(p1[0], p1[1], p2[0], p2[1], dia_w, cy))

    return shapes
