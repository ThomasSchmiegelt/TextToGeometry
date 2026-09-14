# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kurbelwelle — Hauptlagerzapfen, Hubzapfen, Wangen, Gegengewichte.

Gebaut wird entlang **+X** (Wellenachse), Zapfen 1 bei ``x = 0``. Die
Hubzapfen stehen in den Winkeln aus :mod:`kt_bauformen` — dort steckt die
Motorenkunde, hier nur die Geometrie.

Winkelkonvention: 0° heißt Hubzapfen in **+Z** (oberer Totpunkt von Bank A).
Gedreht wird um die X-Achse, also liegt der Zapfen bei Winkel φ auf
``(0, -r·sin φ, r·cos φ)``.

Beim V-Motor mit Hubzapfenversatz wird jeder Hubzapfen geteilt: die eine
Hälfte trägt Bank A, die andere ist um den Versatz weitergedreht und trägt
Bank B. Das ist der Grund, warum ein 90°-V6 überhaupt gleichmäßig zünden
kann.

Anschlusspunkte
    ``hubzapfen_1..n``    Mitte jedes Hubzapfens, Achse **+X**, Art *welle*
    ``hubzapfen_1b..nb``  nur bei Versatz: die zweite Hälfte für Bank B
    ``hauptlager_1..m``   Mitte jedes Hauptlagers, Achse +X, Art *welle*
    ``abtrieb``           Schwungradflansch, Achse +X, Art *flaeche*
    ``steuertrieb``       Sitz für Kettenrad oder Zahnrad, Achse -X, *welle*
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

import kt_bauformen as B
from kt_schnittstelle import Bauteil, Punkt


def zapfenort(radius, winkel_grad):
    """Lage eines Hubzapfens in der YZ-Ebene [mm]."""
    w = math.radians(float(winkel_grad))
    return (0.0, -float(radius) * math.sin(w), float(radius) * math.cos(w))


def kennwerte(bauform="R4", hub=86.0, zylinderabstand=91.0,
              v8_kreuzebene=True, **_rest):
    z, bank = B.daten(bauform)
    n = B.zapfenzahl(bauform)
    return {
        "bauform": str(bauform).upper(),
        "hub": float(hub),
        "kurbelradius": float(hub) / 2.0,
        "hubzapfen": n,
        "hauptlager": n + 1,
        "zapfenwinkel": B.zapfenwinkel(bauform, v8_kreuzebene),
        "versatz": B.hubzapfenversatz(bauform, v8_kreuzebene),
        "laenge": round(n * float(zylinderabstand) + 2.0 * 30.0, 1),
    }


def baue(bauform="R4", hub=86.0, zylinderabstand=91.0, hauptlager_d=54.0,
         hubzapfen_d=48.0, hubzapfen_b=26.0, hauptlager_b=26.0, wange_t=18.0,
         wange_b=0.0, gegengewicht=True, flansch_d=110.0, flansch_t=12.0,
         steuertrieb_d=30.0, steuertrieb_l=30.0, v8_kreuzebene=True,
         name="Kurbelwelle"):
    """Eine Kurbelwelle als :class:`Bauteil`.

    bauform          R2 … V12 (siehe :mod:`kt_bauformen`)
    hub              Kolbenhub [mm]; der Kurbelradius ist die Hälfte
    zylinderabstand  Abstand der Zylindermitten [mm]
    hauptlager_d     Durchmesser der Hauptlagerzapfen [mm]
    hubzapfen_d      Durchmesser der Hubzapfen [mm]
    wange_t          Dicke einer Kurbelwange [mm]
    gegengewicht     Gegengewichte an den Wangen anformen
    """
    r = float(hub) / 2.0
    n = B.zapfenzahl(bauform)
    winkel = B.zapfenwinkel(bauform, v8_kreuzebene)
    versatz = B.hubzapfenversatz(bauform, v8_kreuzebene)
    abstand = float(zylinderabstand)
    r_haupt = float(hauptlager_d) / 2.0
    r_hub = float(hubzapfen_d) / 2.0
    # Die Wange muss den Hubzapfen tragen, mehr nicht. Mit 6 mm Ueberstand
    # streifte das Gegengewicht beim V10 die Kolbenschuerze (2,2 %).
    wb = float(wange_b) or (r + r_hub + 2.0) * 2.0

    if r_haupt <= 0 or r_hub <= 0:
        raise ValueError("Zapfendurchmesser muessen positiv sein.")
    if r <= 0:
        raise ValueError("Hub muss positiv sein.")

    teile = []
    punkte = []

    # Die Welle liegt entlang X. Zapfen k sitzt bei x = k * abstand.
    # Davor und dahinter je ein Hauptlager, dazwischen Wangen.
    x = -float(hauptlager_b) - float(wange_t)
    anfang = x

    def wange(x0, phi):
        """Eine Kurbelwange: Scheibe vom Hauptlager zum Hubzapfen."""
        _dy, y, z = zapfenort(r, phi)
        # Scheibe um die Wellenachse, dann auf die Zapfenseite verlaengert.
        grund = Part.makeCylinder(wb / 2.0, float(wange_t), Vector(x0, 0, 0),
                                  Vector(1, 0, 0))
        if not gegengewicht:
            # Ohne Gegengewicht nur der Steg zum Zapfen.
            steg = Part.makeBox(float(wange_t), wb * 0.45, r + r_hub + 4.0,
                                Vector(x0, -wb * 0.225, 0))
            dreh = FreeCAD.Placement(
                Vector(x0, 0, 0),
                FreeCAD.Rotation(Vector(1, 0, 0), float(phi)),
                Vector(-x0, 0, 0))
            steg.Placement = dreh.multiply(steg.Placement)
            ring = Part.makeCylinder(r_haupt + 3.0, float(wange_t),
                                     Vector(x0, 0, 0), Vector(1, 0, 0))
            return steg.fuse(ring)
        # Mit Gegengewicht: die Scheibe auf der Gegenseite behalten,
        # auf der Zapfenseite bis knapp hinter den Zapfen beschneiden.
        halb = Part.makeBox(float(wange_t) + 2.0, wb + 4.0, wb + 4.0,
                            Vector(x0 - 1.0, -wb / 2.0 - 2.0, 0.0))
        dreh = FreeCAD.Placement(
            Vector(x0, 0, 0), FreeCAD.Rotation(Vector(1, 0, 0), float(phi)),
            Vector(-x0, 0, 0))
        halb.Placement = dreh.multiply(halb.Placement)
        kappe = Part.makeCylinder(r + r_hub + 2.0, float(wange_t),
                                  Vector(x0, 0, 0), Vector(1, 0, 0))
        return grund.cut(halb).fuse(kappe.common(halb).cut(
            Part.makeCylinder(r_haupt, float(wange_t) + 2.0,
                              Vector(x0 - 1.0, 0, 0), Vector(1, 0, 0))))

    for k in range(n):
        phi = winkel[k]
        # Hauptlager vor dem Zapfen
        teile.append(("Hauptlager %d" % (k + 1),
                      Part.makeCylinder(r_haupt, float(hauptlager_b),
                                        Vector(x, 0, 0), Vector(1, 0, 0))))
        punkte.append(Punkt("hauptlager_%d" % (k + 1),
                            (x + float(hauptlager_b) / 2.0, 0, 0), (1, 0, 0),
                            "welle", float(hauptlager_d),
                            "Hauptlagerzapfen %d" % (k + 1)))
        x += float(hauptlager_b)
        # Wange, Hubzapfen, Wange
        teile.append(("Wange %dA" % (k + 1), wange(x, phi)))
        x += float(wange_t)
        _dx, y, z = zapfenort(r, phi)
        zapfen_x = x
        if versatz and B.ist_v(bauform):
            # Gesplitteter Hubzapfen: zwei Haelften, um den Versatz verdreht.
            halbe = float(hubzapfen_b) / 2.0
            for teil, (px, pw, kuerzel) in enumerate(
                    ((zapfen_x, phi, "a"),
                     (zapfen_x + halbe, phi + versatz, "b"))):
                _d, yy, zz = zapfenort(r, pw)
                teile.append(("Hubzapfen %d%s" % (k + 1, kuerzel),
                              Part.makeCylinder(r_hub, halbe,
                                                Vector(px, yy, zz),
                                                Vector(1, 0, 0))))
                punkte.append(Punkt(
                    "hubzapfen_%d%s" % (k + 1, kuerzel),
                    (px + halbe / 2.0, yy, zz), (1, 0, 0), "welle",
                    float(hubzapfen_d),
                    "Hubzapfen %d, Bank %s, %.1f Grad"
                    % (k + 1, "A" if kuerzel == "a" else "B", pw % 360.0)))
            punkte.append(Punkt("hubzapfen_%d" % (k + 1),
                                (zapfen_x + float(hubzapfen_b) / 2.0, y, z),
                                (1, 0, 0), "welle", float(hubzapfen_d),
                                "Hubzapfen %d (Mitte)" % (k + 1)))
        else:
            teile.append(("Hubzapfen %d" % (k + 1),
                          Part.makeCylinder(r_hub, float(hubzapfen_b),
                                            Vector(zapfen_x, y, z),
                                            Vector(1, 0, 0))))
            punkte.append(Punkt(
                "hubzapfen_%d" % (k + 1),
                (zapfen_x + float(hubzapfen_b) / 2.0, y, z), (1, 0, 0),
                "welle", float(hubzapfen_d),
                "Hubzapfen %d, %.1f Grad" % (k + 1, phi)))
        x += float(hubzapfen_b)
        teile.append(("Wange %dB" % (k + 1), wange(x, phi)))
        x += float(wange_t)

    # Letztes Hauptlager
    teile.append(("Hauptlager %d" % (n + 1),
                  Part.makeCylinder(r_haupt, float(hauptlager_b),
                                    Vector(x, 0, 0), Vector(1, 0, 0))))
    punkte.append(Punkt("hauptlager_%d" % (n + 1),
                        (x + float(hauptlager_b) / 2.0, 0, 0), (1, 0, 0),
                        "welle", float(hauptlager_d),
                        "Hauptlagerzapfen %d" % (n + 1)))
    x += float(hauptlager_b)

    # Schwungradflansch hinten
    teile.append(("Flansch", Part.makeCylinder(
        float(flansch_d) / 2.0, float(flansch_t), Vector(x, 0, 0),
        Vector(1, 0, 0))))
    punkte.append(Punkt("abtrieb", (x + float(flansch_t), 0, 0), (1, 0, 0),
                        "flaeche", float(flansch_d),
                        "Schwungradflansch"))

    # Steuertriebzapfen vorn
    teile.append(("Steuertriebzapfen", Part.makeCylinder(
        float(steuertrieb_d) / 2.0, float(steuertrieb_l),
        Vector(anfang - float(steuertrieb_l), 0, 0), Vector(1, 0, 0))))
    punkte.append(Punkt(
        "steuertrieb", (anfang - float(steuertrieb_l) / 2.0, 0, 0),
        (-1, 0, 0), "welle", float(steuertrieb_d),
        "Sitz fuer Kettenrad oder Zahnrad des Steuertriebs"))

    # Alles zu einem Koerper vereinen — eine Kurbelwelle ist ein Schmiedeteil.
    ganz = teile[0][1]
    if len(teile) > 1:
        ganz = ganz.multiFuse([t[1] for t in teile[1:]])

    bt = Bauteil(name, koerper=[(name, ganz)], punkte=punkte,
                 kennwerte=kennwerte(bauform, hub, zylinderabstand,
                                     v8_kreuzebene))
    bt.kennwerte["laenge"] = round(x + float(flansch_t)
                                   - (anfang - float(steuertrieb_l)), 1)
    bt.kennwerte["zylinderabstand"] = abstand
    return bt


def selbsttest():
    """Prüft Zapfenlagen gegen die Bauformtabelle."""
    r = 86.0 / 2.0

    for bauform in B.namen():
        t = baue(bauform=bauform, hub=86.0, zylinderabstand=91.0)
        shp = t.koerper[0][1]
        if not shp.Solids:
            raise AssertionError("%s: Kurbelwelle ist kein Solid" % bauform)
        n = B.zapfenzahl(bauform)
        winkel = B.zapfenwinkel(bauform)
        # Zu jedem Zapfen ein Anschlusspunkt, an der richtigen Winkellage.
        for k in range(n):
            p = t.punkt("hubzapfen_%d" % (k + 1))
            _x, y, z = zapfenort(r, winkel[k])
            if abs(p.ort.y - y) > 1e-6 or abs(p.ort.z - z) > 1e-6:
                raise AssertionError(
                    "%s Zapfen %d: (%.2f, %.2f) statt (%.2f, %.2f) bei %.1f "
                    "Grad" % (bauform, k + 1, p.ort.y, p.ort.z, y, z,
                              winkel[k]))
            # Die Zapfenachse ist die WELLENACHSE. Mit (0,1,0) deklariert
            # dockt das Pleuel quer an und liegt in der Kurbelwellenebene —
            # die Paarungspruefung merkt das nicht, weil beide Seiten dann
            # konsistent falsch sind. Gemessen hatte das Pleuel 62 mm
            # Ausdehnung laengs der Welle statt 22.
            if abs(p.achse.x - 1.0) > 1e-9:
                raise AssertionError(
                    "%s Zapfen %d: Achse %s statt der Wellenachse (1,0,0)"
                    % (bauform, k + 1, p.achse))
            # Der Kurbelradius muss stimmen.
            radius = math.hypot(p.ort.y, p.ort.z)
            if abs(radius - r) > 1e-6:
                raise AssertionError("%s Zapfen %d: Radius %.3f statt %.3f"
                                     % (bauform, k + 1, radius, r))
        # Ein Hauptlager mehr als Hubzapfen.
        if len([x for x in t.punkte if x.startswith("hauptlager_")]) != n + 1:
            raise AssertionError("%s: falsche Zahl Hauptlager" % bauform)
        for pflicht in ("abtrieb", "steuertrieb"):
            t.punkt(pflicht)

    # Gesplitteter Hubzapfen beim V6: zwei Haelften, um 60 Grad verdreht.
    t = baue(bauform="V6", hub=86.0)
    a = t.punkt("hubzapfen_1a")
    bb = t.punkt("hubzapfen_1b")
    wa = math.degrees(math.atan2(-a.ort.y, a.ort.z)) % 360.0
    wb = math.degrees(math.atan2(-bb.ort.y, bb.ort.z)) % 360.0
    delta = (wb - wa) % 360.0
    if abs(delta - B.hubzapfenversatz("V6")) > 0.01:
        raise AssertionError("V6: Zapfenhaelften %.1f Grad auseinander, "
                             "erwartet %.1f" % (delta,
                                                B.hubzapfenversatz("V6")))
    # Der kreuzebenige V8 braucht keinen Versatz und darf nicht splitten.
    t8 = baue(bauform="V8", hub=86.0)
    if "hubzapfen_1a" in t8.punkte:
        raise AssertionError("kreuzebeniger V8 darf keinen geteilten Zapfen "
                             "haben")
    hoehe = t8.koerper[0][1].BoundBox.ZLength
    if hoehe < 2 * r:
        raise AssertionError("V8: Welle nur %.1f mm hoch, der Hub allein "
                             "braucht %.1f" % (hoehe, 2 * r))
    t4 = baue(bauform="R4", hub=86.0)
    return ("Kurbelwelle-Selbsttest bestanden (10 Bauformen; R4 %.0f mm lang, "
            "%.0f mm^3)" % (t4.kennwerte["laenge"], t4.koerper[0][1].Volume))
