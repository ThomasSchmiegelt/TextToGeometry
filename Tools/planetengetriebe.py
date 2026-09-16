# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Planetengetriebe — Sonne, Planeten, Steg, Hohlrad.

    teile, a = baue(zaehne_sonne=24, zaehne_planet=21, planeten=3)

Ein Planetengetriebe hat **drei** Wellen auf **einer** Achse: Sonnenrad,
Steg (Planetenträger) und Hohlrad. Welche davon antreibt, welche abtreibt und
welche festgehalten wird, bestimmt die Übersetzung — dasselbe Getriebe kann
ins Langsame, ins Schnelle oder rückwärts übersetzen. Das ist der Grund,
warum es in Automatikgetrieben, Nabenschaltungen und Windkraftanlagen sitzt:
die Leistung teilt sich auf mehrere Planeten auf, und alles bleibt koaxial.

## Die vier Bedingungen

Ein Planetensatz lässt sich nicht aus beliebigen Zähnezahlen bauen. Vier
Bedingungen müssen zugleich gelten, und drei davon sind rein geometrisch:

**1. Achsbedingung** (Konzentrizität) — Sonne und Hohlrad müssen denselben
Mittelpunkt haben, also

    z_Hohlrad = z_Sonne + 2 · z_Planet

**2. Montagebedingung** — die Planeten sollen gleichmäßig über den Umfang
verteilt stehen; das geht nur, wenn

    (z_Sonne + z_Hohlrad) / Planetenzahl   ganzzahlig ist.

Sonst passt der letzte Planet nicht mehr in die Verzahnung.

**3. Nachbarbedingung** — zwei benachbarte Planeten dürfen sich nicht
berühren. Ihr Mittenabstand ist ``2 · a · sin(π/p)``, ihr Kopfkreis
``m · (z_Planet + 2)``, also

    (z_Sonne + z_Planet) · sin(π / p)  >  z_Planet + 2

**4. Übersetzung** — die Willis-Gleichung. Mit der **Standübersetzung**

    i₀ = − z_Hohlrad / z_Sonne        (Steg festgehalten)

folgt für die drei gebräuchlichen Fälle:

    Hohlrad fest:   i = 1 − i₀ = 1 + z_Hohlrad/z_Sonne     (2 … ∞)
    Sonne fest:     i = 1 + z_Sonne/z_Hohlrad              (1 … 2)
    Steg fest:      i = i₀ = − z_Hohlrad/z_Sonne           (−∞ … −1)

Das Minuszeichen heißt Drehrichtungsumkehr. Mit Sonne 30 und Hohlrad 80:
i₀ = −2,67, Hohlrad fest 3,67, Sonne fest 1,375 — das sind die Werte aus dem
Lehrbuch, und ``selbsttest()`` rechnet sie nach.

## Geometrie

Gebaut wird entlang **+X**, alle drei Wellen auf ``y = z = 0``. Der
Achsabstand Sonne–Planet ist ``a = m · (z_Sonne + z_Planet) / 2``; das
Hohlrad ist ein **innenverzahnter** Ring, hier als Ring mit dem Fußkreis der
Innenverzahnung dargestellt.

Anschlusspunkte (als Kennwerte ausgewiesen, nicht als Körper):
    ``sonne``    Wellenbohrung des Sonnenrades
    ``steg``     Abtriebswelle des Planetenträgers
    ``hohlrad``  Außendurchmesser des Hohlrades
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

import getriebe_fcgear as GF

#: Kleinste Zähnezahl ohne Profilverschiebung (20-Grad-Evolvente).
Z_MIN = 17


class PlanetenFehler(Exception):
    pass


def achsbedingung(zaehne_sonne, zaehne_planet):
    """Zähnezahl des Hohlrades: ``z_H = z_S + 2 · z_P``."""
    return int(zaehne_sonne) + 2 * int(zaehne_planet)


def montagebedingung(zaehne_sonne, zaehne_hohlrad, planeten):
    """Lassen sich ``planeten`` Räder gleichmäßig verteilen?"""
    return (int(zaehne_sonne) + int(zaehne_hohlrad)) % int(planeten) == 0


def nachbarbedingung(zaehne_sonne, zaehne_planet, planeten):
    """Stoßen die Planeten aneinander? True = sie haben Platz."""
    p = int(planeten)
    if p < 2:
        return True
    return ((int(zaehne_sonne) + int(zaehne_planet))
            * math.sin(math.pi / p) > int(zaehne_planet) + 2)


def standuebersetzung(zaehne_sonne, zaehne_hohlrad):
    """i₀ = −z_H / z_S — die Übersetzung bei festgehaltenem Steg."""
    return -float(zaehne_hohlrad) / float(zaehne_sonne)


def uebersetzung(zaehne_sonne, zaehne_hohlrad, fest="hohlrad"):
    """Übersetzung je nachdem, welches Glied festgehalten wird.

    fest = "hohlrad" | "sonne" | "steg"
    """
    i0 = standuebersetzung(zaehne_sonne, zaehne_hohlrad)
    art = str(fest).lower().strip()
    if art == "hohlrad":
        return 1.0 - i0
    if art == "sonne":
        return 1.0 + float(zaehne_sonne) / float(zaehne_hohlrad)
    if art == "steg":
        return i0
    raise PlanetenFehler(
        "Festgehalten wird 'hohlrad', 'sonne' oder 'steg', nicht %r" % fest)


def auslegen(zaehne_sonne=24, zaehne_planet=21, planeten=3, modul=2.0,
             breite=0.0, welle_d=0.0):
    """Die vollständige Auslegung samt aller vier Bedingungen."""
    zs, zp, p = int(zaehne_sonne), int(zaehne_planet), int(planeten)
    zh = achsbedingung(zs, zp)
    m = float(modul)
    b = float(breite) or round(8.0 * m, 1)
    a = {
        "zaehne_sonne": zs,
        "zaehne_planet": zp,
        "zaehne_hohlrad": zh,
        "planeten": p,
        "modul": m,
        "breite": b,
        "achsabstand": round(m * (zs + zp) / 2.0, 3),
        "teilkreis_sonne": round(m * zs, 2),
        "teilkreis_planet": round(m * zp, 2),
        "teilkreis_hohlrad": round(m * zh, 2),
        "welle_d": float(welle_d) or round(max(8.0, m * zs * 0.45), 1),
        "standuebersetzung": round(standuebersetzung(zs, zh), 4),
        "i_hohlrad_fest": round(uebersetzung(zs, zh, "hohlrad"), 4),
        "i_sonne_fest": round(uebersetzung(zs, zh, "sonne"), 4),
        "i_steg_fest": round(uebersetzung(zs, zh, "steg"), 4),
        "montage_ok": montagebedingung(zs, zh, p),
        "nachbar_ok": nachbarbedingung(zs, zp, p),
    }
    a["hohlrad_aussen_d"] = round(m * (zh + 6), 2)
    return a


def vorschlag(i_soll, planeten=3, modul=2.0, z_min=Z_MIN, z_max=90):
    """Zähnezahlen, die eine gewünschte Übersetzung treffen — bei fest
    gehaltenem Hohlrad, dem häufigsten Fall.

    Gesucht wird die Kombination, die ``i = 1 + z_H/z_S`` am nächsten kommt
    **und alle drei geometrischen Bedingungen erfüllt**. Ohne diese Prüfung
    kommt leicht ein Satz heraus, dessen Planeten sich berühren oder der
    sich gar nicht montieren lässt.
    """
    beste = None
    for zs in range(int(z_min), int(z_max) + 1):
        for zp in range(int(z_min), int(z_max) + 1):
            zh = achsbedingung(zs, zp)
            if zh > int(z_max) * 2:
                continue
            if not montagebedingung(zs, zh, planeten):
                continue
            if not nachbarbedingung(zs, zp, planeten):
                continue
            i = uebersetzung(zs, zh, "hohlrad")
            fehler = abs(i - float(i_soll))
            if beste is None or fehler < beste[0]:
                beste = (fehler, zs, zp, zh, i)
    if beste is None:
        raise PlanetenFehler(
            "Kein Satz mit %d Planeten erfuellt alle Bedingungen." % planeten)
    _f, zs, zp, zh, i = beste
    return {"zaehne_sonne": zs, "zaehne_planet": zp, "zaehne_hohlrad": zh,
            "i": round(i, 4), "abweichung": round(i - float(i_soll), 4)}


def _rad(doc, zaehne, modul, breite, bohrung):
    """Ein Evolventenrad ueber FCGear, Achse X."""
    shp, _d, d_a = GF.zahnrad(doc, int(zaehne), float(modul), float(breite),
                              float(bohrung))
    k = shp.copy()
    k.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)
    return k, d_a


def baue(zaehne_sonne=24, zaehne_planet=21, planeten=3, modul=2.0,
         breite=0.0, welle_d=0.0, steg_t=0.0, spiel=0.1, doc=None):
    """Das Planetengetriebe als ``(teile, auslegung)``.

    Gebaut wird entlang **+X**: erst der vordere Stegwange, dann die
    Verzahnungsebene mit Sonne, Planeten und Hohlrad, dann die hintere
    Stegwange mit der Abtriebswelle.
    """
    a = auslegen(zaehne_sonne, zaehne_planet, planeten, modul, breite,
                 welle_d)
    if not a["montage_ok"]:
        raise PlanetenFehler(
            "Montagebedingung verletzt: (%d + %d) / %d ist nicht ganzzahlig "
            "— die Planeten stehen nicht gleichmaessig."
            % (a["zaehne_sonne"], a["zaehne_hohlrad"], a["planeten"]))
    if not a["nachbar_ok"]:
        raise PlanetenFehler(
            "Nachbarbedingung verletzt: %d Planeten mit z=%d beruehren "
            "einander auf dem Achsabstand %.1f mm."
            % (a["planeten"], a["zaehne_planet"], a["achsabstand"]))

    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Planeten")
    b = a["breite"]
    st = float(steg_t) or round(max(6.0, 0.35 * b), 1)
    teile = []
    x0 = st                      # Verzahnungsebene beginnt hinter der Wange

    # --- Sonnenrad --------------------------------------------------------
    sonne, _da = _rad(doc, a["zaehne_sonne"], modul, b, a["welle_d"])
    sonne.translate(Vector(x0, 0, 0))
    teile.append(("Sonnenrad (z=%d)" % a["zaehne_sonne"], sonne))

    # --- Planeten ---------------------------------------------------------
    # Die Phase ist NICHT frei: das Planetenrad muss an seiner Stelle in die
    # Sonne greifen. Fuer gleichmaessig verteilte Planeten ist die noetige
    # Verdrehung des Planeten gerade z_S/z_P mal seinem Stellwinkel.
    bolzen_d = max(6.0, a["welle_d"] * 0.5)
    for k in range(a["planeten"]):
        w = 2.0 * math.pi * k / a["planeten"]
        phase = math.degrees(w) * a["zaehne_sonne"] / float(a["zaehne_planet"])
        planet, _dp = _rad(doc, a["zaehne_planet"], modul, b,
                           bolzen_d + 2.0 * spiel)
        planet.rotate(Vector(0, 0, 0), Vector(1, 0, 0), phase)
        planet.translate(Vector(x0, a["achsabstand"] * math.cos(w),
                                a["achsabstand"] * math.sin(w)))
        teile.append(("Planetenrad %d (z=%d)" % (k + 1, a["zaehne_planet"]),
                      planet))
        # Der Planetenbolzen traegt ihn im Steg.
        teile.append((
            "Planetenbolzen %d" % (k + 1),
            Part.makeCylinder(bolzen_d / 2.0, b + 2.0 * st,
                              Vector(0.0, a["achsabstand"] * math.cos(w),
                                     a["achsabstand"] * math.sin(w)),
                              Vector(1, 0, 0))))

    # --- Hohlrad ----------------------------------------------------------
    # Innenverzahnt; hier als Ring vom Fusskreis der Innenverzahnung nach
    # aussen. Der Fusskreis der INNENverzahnung liegt AUSSEN vom Teilkreis.
    r_innen = modul * a["zaehne_hohlrad"] / 2.0 + modul
    hohl = Part.makeCylinder(a["hohlrad_aussen_d"] / 2.0, b,
                             Vector(x0, 0, 0), Vector(1, 0, 0))
    hohl = hohl.cut(Part.makeCylinder(r_innen, b + 2.0,
                                      Vector(x0 - 1.0, 0, 0),
                                      Vector(1, 0, 0)))
    teile.append(("Hohlrad (z=%d, innenverzahnt)" % a["zaehne_hohlrad"],
                  hohl))

    # --- Steg (Planetentraeger) ------------------------------------------
    r_steg = a["achsabstand"] + modul * (a["zaehne_planet"] + 2) / 2.0 + 2.0
    for nr, x in (("vorn", 0.0), ("hinten", x0 + b)):
        wange = Part.makeCylinder(r_steg, st, Vector(x, 0, 0),
                                  Vector(1, 0, 0))
        # Die Sonnenwelle geht hindurch …
        wange = wange.cut(Part.makeCylinder(
            a["welle_d"] / 2.0 + spiel, st + 2.0,
            Vector(x - 1.0, 0, 0), Vector(1, 0, 0)))
        # … und die Planetenbolzen sitzen in BOHRUNGEN. Ohne sie stak der
        # Bolzen zu 21,4 % im Vollmaterial der Wange; genau diese Bohrungen
        # sind es, die den Steg zum Planetentraeger machen.
        for k in range(a["planeten"]):
            w = 2.0 * math.pi * k / a["planeten"]
            wange = wange.cut(Part.makeCylinder(
                bolzen_d / 2.0 + spiel, st + 2.0,
                Vector(x - 1.0, a["achsabstand"] * math.cos(w),
                       a["achsabstand"] * math.sin(w)),
                Vector(1, 0, 0)))
        teile.append(("Stegwange %s" % nr, wange))

    # --- Wellen -----------------------------------------------------------
    teile.append(("Sonnenwelle",
                  Part.makeCylinder(a["welle_d"] / 2.0, x0 + b + st + 30.0,
                                    Vector(-30.0, 0, 0), Vector(1, 0, 0))))
    teile.append(("Stegwelle",
                  Part.makeCylinder(a["welle_d"] / 2.0 + 6.0, 30.0,
                                    Vector(x0 + b + st, 0, 0),
                                    Vector(1, 0, 0))))
    a["baulaenge"] = round(x0 + b + st + 30.0, 1)
    return teile, a


def pruefe(teile, a):
    """Misst den Planetensatz nach; liefert [(ok, Text), …]."""
    befunde = []

    def sag(ok, text):
        befunde.append((bool(ok), text))

    sag(all(s.Solids for _n, s in teile),
        "alle %d Koerper sind Solids" % len(teile))

    # Die drei geometrischen Bedingungen, jede einzeln.
    sag(a["zaehne_hohlrad"] == a["zaehne_sonne"] + 2 * a["zaehne_planet"],
        "Achsbedingung: %d = %d + 2 x %d"
        % (a["zaehne_hohlrad"], a["zaehne_sonne"], a["zaehne_planet"]))
    sag(a["montage_ok"],
        "Montagebedingung: (%d + %d) / %d = %.2f"
        % (a["zaehne_sonne"], a["zaehne_hohlrad"], a["planeten"],
           (a["zaehne_sonne"] + a["zaehne_hohlrad"]) / float(a["planeten"])))
    luft = ((a["zaehne_sonne"] + a["zaehne_planet"])
            * math.sin(math.pi / a["planeten"]) - (a["zaehne_planet"] + 2))
    sag(a["nachbar_ok"],
        "Nachbarbedingung: %.1f Zaehne Luft zwischen den Planeten" % luft)

    # Willis: die drei Uebersetzungen muessen zueinander passen.
    sag(abs(a["i_hohlrad_fest"] - (1.0 - a["standuebersetzung"])) < 1e-6,
        "Hohlrad fest: i = 1 - i0 = %.4f" % a["i_hohlrad_fest"])
    sag(a["i_hohlrad_fest"] > 2.0,
        "Hohlrad fest uebersetzt ins Langsame (i = %.3f > 2)"
        % a["i_hohlrad_fest"])
    sag(1.0 < a["i_sonne_fest"] < 2.0,
        "Sonne fest: 1 < i = %.3f < 2" % a["i_sonne_fest"])
    sag(a["i_steg_fest"] < -1.0,
        "Steg fest: i = %.3f, Drehrichtung umgekehrt" % a["i_steg_fest"])

    # Die Planeten muessen gleichmaessig stehen.
    planeten = [s for n, s in teile if n.startswith("Planetenrad")]
    sag(len(planeten) == a["planeten"],
        "%d Planetenraeder" % len(planeten))
    if len(planeten) >= 2:
        winkel = sorted(
            math.degrees(math.atan2((b.ZMin + b.ZMax) / 2.0,
                                    (b.YMin + b.YMax) / 2.0)) % 360.0
            for b in (s.BoundBox for s in planeten))
        soll = 360.0 / len(planeten)
        ab = [round((winkel[(i + 1) % len(winkel)] - winkel[i]) % 360.0, 1)
              for i in range(len(winkel))]
        sag(max(abs(x - soll) for x in ab) < 1.0,
            "die Planeten stehen %s Grad auseinander (Soll %.0f)"
            % (sorted(set(ab)), soll))

    # Nichts darf sich durchdringen — ausser den kaemmenden Verzahnungen.
    kaemmt = ("Sonnenrad", "Planetenrad", "Hohlrad")
    schlimm, wo = 0.0, ""
    for i in range(len(teile)):
        for j in range(i + 1, len(teile)):
            n1, s1 = teile[i]
            n2, s2 = teile[j]
            if not s1.BoundBox.intersect(s2.BoundBox):
                continue
            if any(n1.startswith(e) for e in kaemmt) and \
                    any(n2.startswith(e) for e in kaemmt):
                continue
            v = s1.common(s2).Volume
            klein = min(s1.Volume, s2.Volume)
            anteil = v / klein if klein else 0.0
            if anteil > schlimm:
                schlimm, wo = anteil, "%s / %s" % (n1, n2)
    sag(schlimm < 0.02,
        "groesste Durchdringung %.1f %%%s"
        % (schlimm * 100, (" bei " + wo) if wo else ""))
    return befunde


def selbsttest():
    """Prüft die vier Bedingungen und die Willis-Gleichung."""
    # Das Lehrbuchbeispiel: Sonne 30, Hohlrad 80.
    if abs(standuebersetzung(30, 80) + 2.6667) > 1e-3:
        raise AssertionError("i0 stimmt nicht: %.4f" % standuebersetzung(30, 80))
    if abs(uebersetzung(30, 80, "hohlrad") - 3.6667) > 1e-3:
        raise AssertionError("Hohlrad fest: %.4f statt 3,667"
                             % uebersetzung(30, 80, "hohlrad"))
    if abs(uebersetzung(30, 80, "sonne") - 1.375) > 1e-3:
        raise AssertionError("Sonne fest: %.4f statt 1,375"
                             % uebersetzung(30, 80, "sonne"))

    # Achsbedingung.
    if achsbedingung(24, 21) != 66:
        raise AssertionError("Achsbedingung: %d statt 66" % achsbedingung(24, 21))

    # Montagebedingung: (24+66)/3 = 30 ganzzahlig, (24+66)/4 = 22,5 nicht.
    if not montagebedingung(24, 66, 3):
        raise AssertionError("3 Planeten muessten passen")
    if montagebedingung(24, 66, 4):
        raise AssertionError("4 Planeten duerfen NICHT passen")

    # Nachbarbedingung: viele grosse Planeten stossen aneinander.
    if not nachbarbedingung(24, 21, 3):
        raise AssertionError("drei Planeten haben Platz")
    if nachbarbedingung(24, 60, 6):
        raise AssertionError("sechs Planeten mit z=60 muessen sich beruehren")

    # Der Vorschlag muss alle drei Bedingungen halten.
    v = vorschlag(4.0, planeten=3, z_max=60)
    if not montagebedingung(v["zaehne_sonne"], v["zaehne_hohlrad"], 3):
        raise AssertionError("Vorschlag verletzt die Montagebedingung")
    if not nachbarbedingung(v["zaehne_sonne"], v["zaehne_planet"], 3):
        raise AssertionError("Vorschlag verletzt die Nachbarbedingung")
    if abs(v["abweichung"]) > 0.1:
        raise AssertionError("Vorschlag trifft i=4 nicht: %.3f" % v["i"])

    # Und ein unmoeglicher Satz muss abgewiesen werden, nicht gebaut.
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("PlanetenTest")
    try:
        baue(zaehne_sonne=24, zaehne_planet=21, planeten=4, doc=doc)
        raise AssertionError("unmoegliche Planetenzahl blieb unbemerkt")
    except PlanetenFehler:
        pass

    teile, a = baue(zaehne_sonne=24, zaehne_planet=21, planeten=3,
                    modul=2.0, doc=doc)
    schlecht = [t for ok, t in pruefe(teile, a) if not ok]
    if schlecht:
        raise AssertionError("; ".join(schlecht))
    return ("Planetengetriebe-Selbsttest bestanden (z %d/%d/%d, %d Planeten, "
            "i0 %.3f, Hohlrad fest %.3f, %d Teile, %.0f mm lang)"
            % (a["zaehne_sonne"], a["zaehne_planet"], a["zaehne_hohlrad"],
               a["planeten"], a["standuebersetzung"], a["i_hohlrad_fest"],
               len(teile), a["baulaenge"]))
