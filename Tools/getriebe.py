# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Baut ein vollstaendiges Vorgelegegetriebe aus Parametern.

Ein Getriebe ist durchgerechnet, nicht geraten: Achsabstand, Zaehnezahlen,
Radlagen, Gehaeusemasse folgen alle aus wenigen Eingaben. Ein Sprachmodell,
das siebzehn Teile einzeln mit x/y/z platziert, macht daraus siebzehn
Gelegenheiten, sich zu vertun.

Darum diese Funktion. Der Agent wertet aus, was der Benutzer will, und
bedient damit ein Werkzeug:

    werkzeug_aufrufen: getriebe.baue;gaenge=5;abstand=3;wand=4

``baue()`` liefert (Bezeichnung, Shape)-Paare, fertig platziert: Zahnraeder
in Eingriffsphase, Lager auf ihren Absaetzen, Gehaeuse um alles herum.
``pruefe()`` misst das Ergebnis nach und ist damit zugleich der Selbsttest.
"""

import math
import os
import sys

_HIER = os.path.dirname(os.path.abspath(__file__))
_WURZEL = os.path.dirname(_HIER)
for _p in (_WURZEL, _HIER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FreeCAD                                            # noqa: E402
import T2GSkills                                          # noqa: E402
import getriebe_auslegung as G                            # noqa: E402

#: Die vier Skills, aus denen ein Getriebe besteht.
SKILLS = ("zahnrad", "welle", "lager", "gehaeuse")


def _engine():
    eng = T2GSkills.SkillEngine(
        T2GSkills.SkillEngine._default_skills_dir()).load_all()
    fehlt = [n for n in SKILLS if n not in eng.registry.names()]
    if fehlt:
        raise RuntimeError("Es fehlen die Skills: %s" % ", ".join(fehlt))
    return eng


def baue(gaenge=5, modul=2.0, zaehne_summe=48, breite=10.0, luft=2.0,
         abstand=3.0, wand=4.0, welle_d=15.0, sitz_d=12.0, lager_d=28.0,
         lager_b=8.0, kugeln=8, spiel=0.1):
    """Ein vollstaendiges Getriebe als Liste von (Bezeichnung, Shape).

    gaenge        Zahl der Gangstufen
    modul         Verzahnungsmodul [mm]
    zaehne_summe  z1 + z2, fuer ALLE Gaenge gleich -- daher ein Achsabstand
    breite        Zahnbreite [mm]           luft     Luft zwischen den Radpaaren
    abstand       Freiraum Rad -> Gehaeuseinnenwand [mm]
    wand          Wandstaerke des Gehaeuses [mm]
    welle_d       Wellendurchmesser         sitz_d   Durchmesser der Lagersitze
    lager_d       Lageraussendurchmesser    lager_b  Lagerbreite
    kugeln        Waelzkoerper je Lager     spiel    Passungsspiel [mm]
    """
    gaenge = max(1, int(gaenge))
    kugeln = max(3, int(kugeln))
    eng = _engine()

    paare = G.gangpaare(int(zaehne_summe), gaenge)
    a = G.achsabstand(modul, *paare[0][:2])
    innen_l, innen_b, innen_h, achs_z = G.gehaeuse_aus_raedern(
        modul, paare, breite, luft, abstand, a)
    y = innen_b / 2.0
    z_unten, z_oben = achs_z, achs_z + a
    welle_l = innen_l + 2.0 * wand + 2.0 * (lager_b + 6.0)
    x0 = -(wand + lager_b + 6.0)
    sitz_l = lager_b + 2.0

    teile = []

    def lege_ab(shapes, label, pos):
        """Die Skills bauen entlang Z, das Getriebe laeuft entlang X."""
        for k, shp in enumerate(shapes):
            s = shp.copy()
            s.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0), 90)
            s.translate(FreeCAD.Vector(*pos))
            name = label if len(shapes) == 1 else "%s %d/%d" % (
                label, k + 1, len(shapes))
            teile.append((name, s))

    # --- Zahnraeder: das getriebene Rad um eine halbe Zahnteilung verdreht,
    #     sonst stossen die Zaehne aufeinander statt ineinander zu greifen.
    for k, (z1, z2, i) in enumerate(paare):
        x = abstand + k * (breite + luft)
        oben, _v, _p = eng.build("zahnrad", {
            "modul": modul, "zaehne": z1, "breite": breite,
            "bohrung": welle_d, "nabe_d": 0.0, "nabe_b": 0.0,
            "spiel": spiel, "phase": 0.0})
        unten, _v, _p = eng.build("zahnrad", {
            "modul": modul, "zaehne": z2, "breite": breite,
            "bohrung": welle_d, "nabe_d": 0.0, "nabe_b": 0.0,
            "spiel": spiel, "phase": 180.0 / z2})
        lege_ab(oben, "Gang %d treibend (z=%d)" % (k + 1, z1),
                (x, y, z_oben))
        lege_ab(unten, "Gang %d getrieben (z=%d, i=%.3f)" % (k + 1, z2, i),
                (x, y, z_unten))

    # --- Wellen
    for label, z in (("Eingangswelle", z_oben), ("Ausgangswelle", z_unten)):
        w, _v, _p = eng.build("welle", {
            "laenge": welle_l, "welle_d": welle_d, "sitz_d": sitz_d,
            "sitz_l": sitz_l})
        lege_ab(w, label, (x0, y, z))

    # --- Lager auf den abgesetzten Sitzen, nicht auf dem vollen Schaft
    rand = (sitz_l - lager_b) / 2.0
    for seite, x in (("links", x0 + rand),
                     ("rechts", x0 + welle_l - sitz_l + rand)):
        for welle, z in (("Eingang", z_oben), ("Ausgang", z_unten)):
            l, _v, _p = eng.build("lager", {
                "innen_d": sitz_d, "aussen_d": lager_d, "breite": lager_b,
                "kugeln": kugeln, "spiel": spiel})
            lege_ab(l, "Lager %s %s" % (welle, seite), (x, y, z))

    # --- Gehaeuse (baut selbst entlang X, wird also nicht gedreht)
    g, _v, _p = eng.build("gehaeuse", {
        "innen_l": innen_l, "innen_b": innen_b, "innen_h": innen_h,
        "wand": wand, "welle_d": lager_d + 1.0, "achsabstand": a,
        "achs_z": achs_z})
    teile.append(("Gehaeuse", g[0]))
    return teile


def kennwerte(gaenge=5, modul=2.0, zaehne_summe=48, breite=10.0, luft=2.0,
              abstand=3.0, wand=4.0):
    """Die Auslegung ohne Geometrie: Achsabstand, Gangpaare, Gehaeusemasse."""
    paare = G.gangpaare(int(zaehne_summe), int(gaenge))
    a = G.achsabstand(modul, *paare[0][:2])
    innen = G.gehaeuse_aus_raedern(modul, paare, breite, luft, abstand, a)
    return {
        "achsabstand": a,
        "gangpaare": [(z1, z2, round(i, 4)) for z1, z2, i in paare],
        "gehaeuse_innen": tuple(round(v, 2) for v in innen[:3]),
        "achs_z": round(innen[3], 2),
        "gehaeuse_aussen": (round(innen[0] + 2 * wand, 2),
                            round(innen[1] + 2 * wand, 2),
                            round(innen[2] + 2 * wand, 2)),
    }


def pruefe(teile=None, abstand=3.0, wand=4.0, toleranz=0.02, **kw):
    """Misst ein gebautes Getriebe nach; liefert eine Liste von Befunden.

    Jeder Eintrag ist (ok, Text). Das ist zugleich der Selbsttest des
    Werkzeugs: ``selbsttest()`` baut mit den Vorgaben und prueft.
    """
    if teile is None:
        teile = baue(abstand=abstand, wand=wand, **kw)
    befunde = []

    def sag(ok, text):
        befunde.append((bool(ok), text))

    raeder = [(n, s) for n, s in teile if n.startswith("Gang")]
    gehaeuse = [(n, s) for n, s in teile if n == "Gehaeuse"]
    sag(len(gehaeuse) == 1, "genau ein Gehaeuse")
    sag(all(s.Solids for _n, s in teile),
        "alle %d Solids sind Koerper" % len(teile))

    # Durchdringung, relativ zum kleineren Teil
    schlimm, wo = 0.0, ""
    for i in range(len(teile)):
        bi = teile[i][1].BoundBox
        for j in range(i + 1, len(teile)):
            if not bi.intersect(teile[j][1].BoundBox):
                continue
            try:
                v = float(teile[i][1].common(teile[j][1]).Volume or 0.0)
            except Exception:  # noqa: BLE001
                v = 0.0
            kleiner = min(teile[i][1].Volume, teile[j][1].Volume)
            anteil = v / kleiner if kleiner > 0 else 0.0
            if anteil > schlimm:
                schlimm, wo = anteil, "%s / %s" % (teile[i][0], teile[j][0])
    sag(schlimm < toleranz,
        "groesste Durchdringung %.1f %% (erlaubt %.0f %%)%s"
        % (schlimm * 100, toleranz * 100, (" bei " + wo) if wo else ""))

    # Freiraum der Raeder zur Gehaeuseinnenwand
    if gehaeuse and raeder:
        gb = gehaeuse[0][1].BoundBox
        innen = (gb.XMin + wand, gb.XMax - wand, gb.YMin + wand,
                 gb.YMax - wand, gb.ZMin + wand, gb.ZMax - wand)
        mind = None
        for _n, s in raeder:
            b = s.BoundBox
            for w in (b.XMin - innen[0], innen[1] - b.XMax,
                      b.YMin - innen[2], innen[3] - b.YMax,
                      b.ZMin - innen[4], innen[5] - b.ZMax):
                mind = w if mind is None else min(mind, w)
        sag(mind >= abstand - 0.01,
            "kleinster Abstand Rad->Innenwand %.2f mm (gefordert %.0f)"
            % (mind, abstand))
        aussen_ok = all(
            gb.XMin <= s.BoundBox.XMin and gb.XMax >= s.BoundBox.XMax
            and gb.YMin <= s.BoundBox.YMin and gb.YMax >= s.BoundBox.YMax
            and gb.ZMin <= s.BoundBox.ZMin and gb.ZMax >= s.BoundBox.ZMax
            for _n, s in raeder)
        sag(aussen_ok, "das Gehaeuse umschliesst alle Raeder")
    return befunde


def selbsttest():
    """Baut mit den Vorgaben und prueft; wirft bei einem Befund."""
    schlecht = [t for ok, t in pruefe() if not ok]
    if schlecht:
        raise AssertionError("; ".join(schlecht))
    return "Getriebe-Selbsttest bestanden"
