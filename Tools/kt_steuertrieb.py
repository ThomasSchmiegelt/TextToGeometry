# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Steuertrieb — Zahnradtrieb oder Kettentrieb, Übersetzung 2:1.

Die eigentliche Zusage ist die **Übersetzung 2:1**: die Nockenwelle muss sich
halb so schnell drehen wie die Kurbelwelle, sonst öffnen die Ventile im
falschen Takt. Alles andere ist Ausführung. Der Selbsttest misst deshalb
nicht die Optik, sondern das Zähnezahlverhältnis und — beim Zahnradtrieb —
den Achsabstand gegen ``m·(z1+z2)/2``.

Zahnradtrieb
    Zwei Stirnräder, das der Nockenwelle mit doppelter Zähnezahl. Läuft über
    das Add-on FCGear, also mit echter Evolventenverzahnung. Ein Zwischenrad
    kehrt die Drehrichtung wieder um.

Kettentrieb
    Zwei Kettenräder und die Kette als Gliederkette entlang ihrer Bahn: zwei
    Tangenten und zwei Umschlingungsbögen. Der Selbsttest prüft, dass die
    Kettenlänge zu einer ganzen Zahl Glieder passt — eine Kette mit halbem
    Glied gibt es nicht.

Gebaut wird in der **YZ-Ebene** (die Wellen laufen in X), Kurbelrad im
Ursprung, Nockenwellenrad bei ``z = achsabstand``.

Anschlusspunkte
    ``kurbel``    Sitz auf der Kurbelwelle, Achse -X, Art *bohrung*
    ``nocken``    Sitz auf der Nockenwelle, Achse -X, Art *bohrung*
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt

#: Bauarten, die die Maske anbietet.
ARTEN = ("zahnrad", "kette")


class SteuertriebFehler(Exception):
    pass


def kennwerte(art="kette", zaehne_kurbel=20, modul=3.0, teilung=9.525,
              achsabstand=0.0, **_rest):
    z1 = int(zaehne_kurbel)
    z2 = 2 * z1
    if str(art) == "zahnrad":
        a = float(modul) * (z1 + z2) / 2.0
    else:
        # Kettenraddurchmesser: d = p / sin(pi/z)
        d1 = float(teilung) / math.sin(math.pi / z1)
        d2 = float(teilung) / math.sin(math.pi / z2)
        a = float(achsabstand) or round((d1 + d2) / 2.0 + 60.0, 1)
    return {
        "art": str(art),
        "zaehne_kurbel": z1,
        "zaehne_nocken": z2,
        "uebersetzung": round(z2 / float(z1), 4),
        "achsabstand": round(a, 2),
    }


def kettenradmasse(zaehne, teilung):
    """Teilkreis- und Kopfkreisdurchmesser eines Kettenrades [mm].

    Teilkreis ``d = p / sin(180°/z)``, Kopfkreis nach DIN 8196 vereinfacht
    ``d_a = d + 0,8·p``.
    """
    z = int(zaehne)
    p = float(teilung)
    d = p / math.sin(math.pi / z)
    return d, d + 0.8 * p


def kettenlaenge(z1, z2, achsabstand, teilung):
    """Nötige Gliederzahl einer Kette, aufgerundet auf gerade Zahl.

    Die bekannte Näherung: ``L = 2a/p + (z1+z2)/2 + ((z2-z1)/(2π))²·p/a``.
    Gerade Gliederzahl, weil eine ungerade ein Kröpfglied bräuchte.
    """
    a = float(achsabstand)
    p = float(teilung)
    roh = (2.0 * a / p + (z1 + z2) / 2.0
           + ((z2 - z1) / (2.0 * math.pi)) ** 2 * p / a)
    glieder = int(math.ceil(roh))
    if glieder % 2:
        glieder += 1
    return glieder, round(roh, 2)


def _zahnrad(doc, zaehne, modul, breite, bohrung):
    """Ein Evolventenrad vom Add-on FCGear."""
    try:
        import freecad.gears.commands as gc
    except ImportError as e:
        raise SteuertriebFehler(
            "Fuer den Zahnradtrieb wird das Add-on freecad.gears gebraucht: "
            "%s" % e)
    vorher = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    g = gc.CreateInvoluteGear.create()
    try:
        g.num_teeth = int(zaehne)
        g.module = "%f mm" % float(modul)
        g.height = "%f mm" % float(breite)
        if float(bohrung) > 0:
            g.axle_hole = True
            g.axle_holesize = "%f mm" % float(bohrung)
        doc.recompute()
        return g.Shape.copy(), g.pitch_diameter.Value
    finally:
        try:
            doc.removeObject(g.Name)
        except Exception:  # noqa: BLE001
            pass
        if vorher is not None and vorher.Name != doc.Name:
            FreeCAD.setActiveDocument(vorher.Name)


def baue(art="kette", zaehne_kurbel=20, modul=3.0, teilung=9.525,
         breite=12.0, achsabstand=0.0, kurbel_d=30.0, nocken_d=26.0,
         rollen_d=6.35, doc=None, name="Steuertrieb"):
    """Steuertrieb als :class:`Bauteil`.

    art            "zahnrad" oder "kette"
    zaehne_kurbel  Zähnezahl am Kurbelwellenrad; das Nockenrad bekommt das
                   Doppelte — daher die 2:1
    modul          Verzahnungsmodul beim Zahnradtrieb [mm]
    teilung        Kettenteilung beim Kettentrieb [mm], üblich 9,525 (3/8")
    achsabstand    0 = aus den Raddurchmessern vorschlagen
    """
    art = str(art).lower().strip()
    if art not in ARTEN:
        raise SteuertriebFehler("Unbekannte Bauart %r. Moeglich: %s"
                                % (art, ", ".join(ARTEN)))
    z1 = max(9, int(zaehne_kurbel))
    z2 = 2 * z1
    k = kennwerte(art, z1, modul, teilung, achsabstand)
    a = k["achsabstand"]
    teile = []

    if art == "zahnrad":
        doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Steuer")
        s1, d1 = _zahnrad(doc, z1, modul, breite, kurbel_d)
        s2, d2 = _zahnrad(doc, z2, modul, breite, nocken_d)
        # Die Raeder liegen in der YZ-Ebene, die Wellen laufen in X.
        for shp, z, label in ((s1, 0.0, "Kurbelwellenrad (z=%d)" % z1),
                              (s2, a, "Nockenwellenrad (z=%d)" % z2)):
            t = shp.copy()
            t.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)
            t.translate(Vector(-float(breite) / 2.0, 0, z))
            teile.append((label, t))
        k["teilkreis_kurbel"] = round(d1, 2)
        k["teilkreis_nocken"] = round(d2, 2)
    else:
        d1, da1 = kettenradmasse(z1, teilung)
        d2, da2 = kettenradmasse(z2, teilung)
        # Das Rad wird auf FUSSKREIS gezeichnet, nicht auf Kopfkreis: die
        # Rollen liegen auf dem Teilkreis, und ein Rad mit Kopfkreis
        # verschluckt sie ganz (gemessen: 100 % Durchdringung). Auf
        # Fusskreis (d - Rollendurchmesser) liegen sie ihm tangential auf.
        for d, z, bohrung, label in (
                (d1, 0.0, float(kurbel_d), "Kettenrad Kurbel (z=%d)" % z1),
                (d2, a, float(nocken_d), "Kettenrad Nocken (z=%d)" % z2)):
            rad = Part.makeCylinder((d - float(rollen_d)) / 2.0,
                                    float(breite),
                                    Vector(-float(breite) / 2.0, 0, z),
                                    Vector(1, 0, 0))
            # Ohne Bohrung steckt das Rad auf der Welle statt auf ihr zu
            # sitzen — gemessen 30,3 % Durchdringung mit der Kurbelwelle.
            if bohrung > 0.0:
                rad = rad.cut(Part.makeCylinder(
                    bohrung / 2.0 + 0.05, float(breite) + 4.0,
                    Vector(-float(breite) / 2.0 - 2.0, 0, z),
                    Vector(1, 0, 0)))
            teile.append((label, rad))
        glieder, roh = kettenlaenge(z1, z2, a, teilung)
        k["glieder"] = glieder
        k["glieder_roh"] = roh
        k["teilkreis_kurbel"] = round(d1, 2)
        k["teilkreis_nocken"] = round(d2, 2)
        # Die Kette als Rollen entlang ihrer Bahn.
        teile.extend(_kettenbahn(d1 / 2.0, d2 / 2.0, a, glieder,
                                 float(teilung), float(rollen_d),
                                 float(breite)))

    return Bauteil(
        name, koerper=teile,
        punkte=[
            Punkt("kurbel", (0, 0, 0), (-1, 0, 0), "bohrung",
                  float(kurbel_d), "Sitz auf der Kurbelwelle"),
            Punkt("nocken", (0, 0, a), (-1, 0, 0), "bohrung",
                  float(nocken_d), "Sitz auf der Nockenwelle"),
        ],
        kennwerte=k)


def _kettenbahn(r1, r2, a, glieder, teilung, rollen_d, breite):
    """Die Kettenrollen entlang der Bahn: zwei Tangenten, zwei Bögen."""
    # Umschlingungswinkel der beiden Raeder
    try:
        beta = math.asin((r2 - r1) / a)
    except ValueError:
        beta = 0.0
    lang = math.pi + 2.0 * beta          # grosses Rad
    kurz = math.pi - 2.0 * beta          # kleines Rad
    tangente = math.sqrt(max(a * a - (r2 - r1) ** 2, 0.0))

    bahn = []
    # Bogen um das kleine Rad (Kurbel, im Ursprung)
    n1 = max(2, int(round(kurz * r1 / teilung)))
    for i in range(n1):
        w = -kurz / 2.0 + kurz * i / float(n1) + math.pi
        bahn.append(Vector(0.0, r1 * math.sin(w), r1 * math.cos(w)))
    # Tangente hinauf
    n2 = max(2, int(round(tangente / teilung)))
    for i in range(n2):
        t = i / float(n2)
        bahn.append(Vector(0.0, -(r1 + (r2 - r1) * t), a * t))
    # Bogen um das grosse Rad
    n3 = max(2, int(round(lang * r2 / teilung)))
    for i in range(n3):
        w = math.pi + lang * i / float(n3)
        bahn.append(Vector(0.0, r2 * math.sin(w), a + r2 * math.cos(w)))
    # Tangente hinunter
    for i in range(n2):
        t = i / float(n2)
        bahn.append(Vector(0.0, (r2 - (r2 - r1) * t), a * (1.0 - t)))

    # An den Uebergaengen zwischen Bogen und Tangente fallen Punkte
    # aufeinander — gemessen 95 % Durchdringung zweier Rollen. Wer naeher
    # liegt als eine halbe Teilung, faellt weg.
    gefiltert = []
    for p in bahn:
        if all(p.distanceToPoint(q) > teilung * 0.5 for q in gefiltert):
            gefiltert.append(p)
    if len(gefiltert) > 1 and \
            gefiltert[0].distanceToPoint(gefiltert[-1]) < teilung * 0.5:
        gefiltert.pop()

    rollen = []
    for i, p in enumerate(gefiltert):
        rollen.append(("Kettenrolle %d" % (i + 1),
                       Part.makeCylinder(float(rollen_d) / 2.0, breite * 0.6,
                                         Vector(-breite * 0.3, p.y, p.z),
                                         Vector(1, 0, 0))))
    return rollen


def selbsttest():
    """Prüft die Übersetzung, den Achsabstand und die Gliederzahl."""
    # Die Zusage: 2:1, gleich welche Bauart.
    for art in ARTEN:
        k = kennwerte(art, zaehne_kurbel=20, modul=3.0)
        if abs(k["uebersetzung"] - 2.0) > 1e-9:
            raise AssertionError("%s: Uebersetzung %.3f statt 2,0"
                                 % (art, k["uebersetzung"]))
        if k["zaehne_nocken"] != 2 * k["zaehne_kurbel"]:
            raise AssertionError("%s: das Nockenrad braucht die doppelte "
                                 "Zaehnezahl" % art)

    # Zahnradtrieb: Achsabstand = m*(z1+z2)/2.
    k = kennwerte("zahnrad", zaehne_kurbel=20, modul=3.0)
    if abs(k["achsabstand"] - 3.0 * (20 + 40) / 2.0) > 1e-6:
        raise AssertionError("Zahnradtrieb: Achsabstand %.2f statt 90"
                             % k["achsabstand"])

    # Kettenrad: d = p / sin(pi/z).
    d, da = kettenradmasse(20, 9.525)
    erwartet = 9.525 / math.sin(math.pi / 20)
    if abs(d - erwartet) > 1e-9:
        raise AssertionError("Kettenrad-Teilkreis %.3f statt %.3f"
                             % (d, erwartet))
    if da <= d:
        raise AssertionError("der Kopfkreis muss groesser sein als der "
                             "Teilkreis")

    # Gliederzahl: immer gerade, nie kleiner als die Rechnung.
    glieder, roh = kettenlaenge(20, 40, 160.0, 9.525)
    if glieder % 2:
        raise AssertionError("ungerade Gliederzahl %d — das braeuchte ein "
                             "Kroepfglied" % glieder)
    if glieder < roh:
        raise AssertionError("aufgerundet wurde nach unten: %d < %.2f"
                             % (glieder, roh))

    # Kettentrieb bauen und nachmessen.
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("SteuerTest")
    t = baue(art="kette", zaehne_kurbel=20, teilung=9.525, doc=doc)
    if len(t.koerper) < 4:
        raise AssertionError("die Kette hat zu wenige Glieder: %d Koerper"
                             % len(t.koerper))
    raeder = [s for n, s in t.koerper if n.startswith("Kettenrad")]
    if len(raeder) != 2:
        raise AssertionError("es fehlen Kettenraeder")
    d_klein = max(raeder[0].BoundBox.YLength, raeder[0].BoundBox.ZLength)
    d1, _da1 = kettenradmasse(20, 9.525)
    fuss = d1 - 6.35
    if abs(d_klein - fuss) > 0.2:
        raise AssertionError("Kettenrad %.2f statt Fusskreis %.2f"
                             % (d_klein, fuss))
    # Die Welle muss durch die Radbohrung passen.
    welle = Part.makeCylinder(30.0 / 2.0, 200.0, Vector(-100.0, 0, 0),
                              Vector(1, 0, 0))
    if raeder[0].common(welle).Volume > 1.0:
        raise AssertionError("das Kettenrad hat keine Bohrung fuer die Welle")

    # Die Rollen duerfen weder im Rad noch ineinander stecken.
    rollen = [s for n, s in t.koerper if n.startswith("Kettenrolle")]
    schlimm = max(raeder[0].common(r).Volume for r in rollen)
    if schlimm > 1.0:
        raise AssertionError("eine Kettenrolle steckt im Rad (%.1f mm^3)"
                             % schlimm)
    for i in range(len(rollen)):
        for j in range(i + 1, len(rollen)):
            if not rollen[i].BoundBox.intersect(rollen[j].BoundBox):
                continue
            if rollen[i].common(rollen[j]).Volume > 1.0:
                raise AssertionError("Kettenrolle %d und %d stecken "
                                     "ineinander" % (i + 1, j + 1))
    # Die beiden Anschlusspunkte muessen den Achsabstand haben.
    ab = t.punkt("kurbel").ort.distanceToPoint(t.punkt("nocken").ort)
    if abs(ab - t.kennwerte["achsabstand"]) > 1e-6:
        raise AssertionError("Anschlusspunkte %.2f auseinander, Achsabstand "
                             "ist %.2f" % (ab, t.kennwerte["achsabstand"]))

    # Unsinnige Bauart.
    try:
        baue(art="riemen")
        raise AssertionError("unbekannte Bauart blieb unbemerkt")
    except SteuertriebFehler:
        pass

    return ("Steuertrieb-Selbsttest bestanden (2:1, Kette mit %d Gliedern, "
            "Achsabstand %.1f mm)" % (t.kennwerte["glieder"],
                                      t.kennwerte["achsabstand"]))
