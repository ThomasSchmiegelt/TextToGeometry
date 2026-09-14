# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Rillenkugellager nach DIN 625-1 / ISO 15.

Der bisherige ``lager``-Skill nimmt Innen- und Außendurchmesser frei entgegen —
man kann damit ein Lager bauen, das es nicht gibt. Hier stehen stattdessen die
Normmaße: Bohrung ``d``, Außendurchmesser ``D``, Breite ``B`` und der kleinste
Kantenabstand ``r`` der drei gebräuchlichen Reihen.

    bezeichnung = waehle(welle_d=20)        # -> "6204"
    teile = baue("6204")                    # -> [(Bezeichnung, Shape), ...]

**Was genormt ist und was nicht:** DIN 625 legt d, D, B und r fest — sonst
nichts. Kugelzahl und Kugeldurchmesser sind Sache des Herstellers und stehen in
keiner Norm. Sie werden hier aus dem Laufkreis geschätzt (Kugel etwa 0,3 mal
die Ringbreite, Anzahl aus dem Teilkreisumfang bei rund 60 % Füllgrad). Wer
ein bestimmtes Lager nachbauen will, trägt ``kugeln`` von Hand ein.

Reihen: 60xx leicht, 62xx mittel, 63xx schwer. Die zweite Ziffer ist die Reihe,
die letzten beiden mal 5 der Bohrungsdurchmesser (ab 6204: 04*5 = 20 mm).
"""

import math

import FreeCAD
import Part

#: (Bezeichnung, d, D, B, r) in mm, nach DIN 625-1.
TABELLE = (
    # Reihe 60 -- leicht
    ("6000", 10.0, 26.0,  8.0, 0.3),
    ("6001", 12.0, 28.0,  8.0, 0.3),
    ("6002", 15.0, 32.0,  9.0, 0.3),
    ("6003", 17.0, 35.0, 10.0, 0.3),
    ("6004", 20.0, 42.0, 12.0, 0.6),
    ("6005", 25.0, 47.0, 12.0, 0.6),
    ("6006", 30.0, 55.0, 13.0, 1.0),
    ("6007", 35.0, 62.0, 14.0, 1.0),
    ("6008", 40.0, 68.0, 15.0, 1.0),
    ("6009", 45.0, 75.0, 16.0, 1.0),
    ("6010", 50.0, 80.0, 16.0, 1.0),
    # Reihe 62 -- mittel (Vorgabe)
    ("6200", 10.0, 30.0,  9.0, 0.6),
    ("6201", 12.0, 32.0, 10.0, 0.6),
    ("6202", 15.0, 35.0, 11.0, 0.6),
    ("6203", 17.0, 40.0, 12.0, 0.6),
    ("6204", 20.0, 47.0, 14.0, 1.0),
    ("6205", 25.0, 52.0, 15.0, 1.0),
    ("6206", 30.0, 62.0, 16.0, 1.0),
    ("6207", 35.0, 72.0, 17.0, 1.1),
    ("6208", 40.0, 80.0, 18.0, 1.1),
    ("6209", 45.0, 85.0, 19.0, 1.1),
    ("6210", 50.0, 90.0, 20.0, 1.1),
    # Reihe 63 -- schwer
    ("6300", 10.0, 35.0, 11.0, 0.6),
    ("6301", 12.0, 37.0, 12.0, 1.0),
    ("6302", 15.0, 42.0, 13.0, 1.0),
    ("6303", 17.0, 47.0, 14.0, 1.0),
    ("6304", 20.0, 52.0, 15.0, 1.1),
    ("6305", 25.0, 62.0, 17.0, 1.1),
    ("6306", 30.0, 72.0, 19.0, 1.1),
    ("6307", 35.0, 80.0, 21.0, 1.5),
    ("6308", 40.0, 90.0, 23.0, 1.5),
    ("6309", 45.0, 100.0, 25.0, 1.5),
    ("6310", 50.0, 110.0, 27.0, 2.0),
)

_NACH_NAME = {z[0]: z for z in TABELLE}


class LagerFehler(Exception):
    pass


def reihen():
    """Die vorhandenen Baureihen, z. B. ('60', '62', '63')."""
    return tuple(sorted({b[:2] for b, _d, _D, _B, _r in TABELLE}))


def masse(bezeichnung):
    """Normmaße eines Lagers als dict."""
    z = _NACH_NAME.get(str(bezeichnung).strip())
    if z is None:
        raise LagerFehler(
            "Unbekanntes Lager %r. Vorhanden: %s"
            % (bezeichnung, ", ".join(sorted(_NACH_NAME))))
    return {"bezeichnung": z[0], "d": z[1], "D": z[2], "B": z[3], "r": z[4]}


def waehle(welle_d, reihe="62"):
    """Das kleinste Lager der Reihe, dessen Bohrung die Welle aufnimmt.

    Passt keines mehr, kommt das größte der Reihe zurück — mit einer klaren
    Meldung wäre hier nichts gewonnen, der Aufrufer sieht am ``d``, dass es
    nicht passt.
    """
    reihe = str(reihe).strip()[:2] or "62"
    kandidaten = sorted((z for z in TABELLE if z[0].startswith("6" + reihe[-1])
                         or z[0][:2] == reihe),
                        key=lambda z: z[1])
    kandidaten = [z for z in kandidaten if z[0][:2] == reihe] or kandidaten
    if not kandidaten:
        raise LagerFehler("Unbekannte Reihe %r. Vorhanden: %s"
                          % (reihe, ", ".join(reihen())))
    for z in kandidaten:
        if z[1] >= float(welle_d) - 1e-9:
            return z[0]
    return kandidaten[-1][0]


def _geometrie(d, D, B, spiel=0.0):
    """Laufkreis und Kugelradius — eine Quelle für Zahl und Geometrie."""
    r_bohrung = d / 2.0 + spiel
    r_aussen = D / 2.0
    r_mitte = (r_bohrung + r_aussen) / 2.0
    r_kugel = min(0.30 * (r_aussen - r_bohrung), 0.40 * B)
    return r_bohrung, r_aussen, r_mitte, r_kugel


def kugelzahl(d, D, B=None, spiel=0.0):
    """Geschätzte Wälzkörperzahl — nicht genormt, siehe Modul-Docstring.

    Die geometrische Obergrenze ist erreicht, wenn sich benachbarte Kugeln
    berühren: ihre Mittelpunkte liegen auf dem Laufkreis im Abstand
    ``2·r_mitte·sin(pi/n)``, das muss größer als ``2·r_kugel`` bleiben, also
    ``n < pi / asin(r_kugel/r_mitte)``. Ein echtes Lager füllt den Kranz nicht
    aus (Käfig, Einfüllen), darum rund 70 % davon — für ein 6204 ergibt das 9
    Kugeln, das echte hat 8.
    """
    if B is None:
        B = (D - d) / 4.0
    _rb, _ra, r_mitte, r_kugel = _geometrie(d, D, B, spiel)
    if r_kugel <= 0.0 or r_mitte <= 0.0 or r_kugel >= r_mitte:
        return 7
    n_max = math.pi / math.asin(min(0.999, r_kugel / r_mitte))
    return max(6, min(20, int(n_max * 0.7)))


def baue(bezeichnung="6204", spiel=0.1, kugeln=0, werkstoff="lagerstahl",
         x=0.0, y=0.0, z=0.0, achse="z"):
    """Ein Rillenkugellager als (Bezeichnung, Shape)-Paare.

    Innenring, Außenring und die Kugeln sind getrennte Solids. ``spiel`` geht an
    zwei Stellen ein: die Bohrung wird um ``spiel`` größer als ``d``, und die
    Laufrille um ``spiel`` weiter als die Kugel. Eine Nullpassung ist
    geometrisch nicht von einem Fehler zu unterscheiden — deshalb nie null.
    """
    m = masse(bezeichnung)
    spiel = max(0.0, float(spiel))
    d, D, B = m["d"], m["D"], m["B"]

    r_bohrung, r_aussen, r_mitte, r_kugel = _geometrie(d, D, B, spiel)
    z_mitte = B / 2.0

    n = int(kugeln) if int(kugeln) >= 3 else kugelzahl(d, D, B, spiel)
    r_rille = r_kugel + spiel

    r_innen_a = r_mitte - 0.15 * r_kugel
    r_aussen_i = r_mitte + 0.15 * r_kugel + spiel

    def ring(r_i, r_a):
        k = Part.makeCylinder(r_a, B)
        return k.cut(Part.makeCylinder(r_i, B + 2.0,
                                       FreeCAD.Vector(0, 0, -1.0)))

    rille = Part.makeTorus(r_mitte, r_rille)
    rille.translate(FreeCAD.Vector(0, 0, z_mitte))

    teile = [("%s Innenring" % m["bezeichnung"],
              ring(r_bohrung, r_innen_a).cut(rille).removeSplitter()),
             ("%s Aussenring" % m["bezeichnung"],
              ring(r_aussen_i, r_aussen).cut(rille).removeSplitter())]
    for i in range(n):
        w = 2.0 * math.pi * i / n
        teile.append(("%s Kugel %d" % (m["bezeichnung"], i + 1),
                      Part.makeSphere(r_kugel, FreeCAD.Vector(
                          r_mitte * math.cos(w), r_mitte * math.sin(w),
                          z_mitte))))

    dreh = {"x": (FreeCAD.Vector(0, 1, 0), 90.0),
            "y": (FreeCAD.Vector(1, 0, 0), -90.0)}.get(str(achse).lower())
    aus = []
    for label, shp in teile:
        s = shp.copy()
        if dreh is not None:
            s.rotate(FreeCAD.Vector(0, 0, 0), dreh[0], dreh[1])
        s.translate(FreeCAD.Vector(float(x), float(y), float(z)))
        aus.append((label, s))
    return aus


def baue_mit_werkstoff(doc=None, **kw):
    """Wie ``baue``, legt die Teile aber ins Dokument und setzt den Werkstoff."""
    import werkstoff as W

    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Lager")
    teile = baue(**{k: v for k, v in kw.items() if k != "werkstoff"})
    objekte = []
    for label, shp in teile:
        o = doc.addObject("Part::Feature", "Lagerteil")
        o.Shape = shp
        o.Label = label
        objekte.append(o)
    doc.recompute()
    meldung = W.zuweisen(objekte, kw.get("werkstoff", "lagerstahl"))
    return objekte, meldung


def selbsttest():
    """Prüft Tabelle, Auswahl und Geometrie gegen die Norm."""
    if masse("6204") != {"bezeichnung": "6204", "d": 20.0, "D": 47.0,
                         "B": 14.0, "r": 1.0}:
        raise AssertionError("6204 stimmt nicht mit DIN 625 ueberein")
    if waehle(20.0) != "6204":
        raise AssertionError("waehle(20) sollte 6204 liefern, nicht %s"
                             % waehle(20.0))
    if waehle(20.0, "63") != "6304":
        raise AssertionError("waehle(20,'63') sollte 6304 liefern")
    if waehle(19.0) != "6204":
        raise AssertionError("waehle(19) muss auf das naechstgroessere gehen")

    teile = baue("6204", spiel=0.1)
    m = masse("6204")
    if len(teile) < 5:
        raise AssertionError("zu wenige Teile: %d" % len(teile))
    if any(not s.Solids for _n, s in teile):
        raise AssertionError("ein Teil ist kein Solid")
    aussen = [s for n, s in teile if "Aussenring" in n][0]
    da = max(aussen.BoundBox.XLength, aussen.BoundBox.YLength)
    if abs(da - m["D"]) > 0.2:
        raise AssertionError("Aussendurchmesser %.2f statt %.1f" % (da, m["D"]))
    if abs(aussen.BoundBox.ZLength - m["B"]) > 0.01:
        raise AssertionError("Breite verfehlt")
    # Nichts darf sich durchdringen, und die Welle muss hineinpassen.
    for i in range(len(teile)):
        for j in range(i + 1, len(teile)):
            if teile[i][1].common(teile[j][1]).Volume > 1e-3:
                raise AssertionError("%s steckt in %s"
                                     % (teile[i][0], teile[j][0]))
    welle = Part.makeCylinder(m["d"] / 2.0, m["B"] * 4,
                              FreeCAD.Vector(0, 0, -m["B"]))
    if max(s.common(welle).Volume for _n, s in teile) > 1e-3:
        raise AssertionError("Bohrung zu eng fuer eine %.0f-mm-Welle" % m["d"])
    return "Lager-Selbsttest bestanden (%d Teile, %s)" % (len(teile), "6204")
