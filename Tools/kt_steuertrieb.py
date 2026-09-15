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
    Ein Kettenrad je Welle und die Kette als Gliederkette entlang ihrer
    Bahn: je eine äußere Tangente zwischen zwei benachbarten Rädern und ein
    Umschlingungsbogen auf jedem Rad. Es sind **beliebig viele** Räder — ein
    DOHC-Kopf hat zwei Nockenwellen, und beide müssen angetrieben werden;
    mit nur zwei Rädern lief eine davon leer mit. Der Selbsttest prüft, dass
    die Kettenlänge zu einer ganzen Zahl Glieder passt — eine Kette mit
    halbem Glied gibt es nicht.

Gebaut wird in der **YZ-Ebene** (die Wellen laufen in X), Kurbelrad im
Ursprung, Nockenwellenrad bei ``z = achsabstand``.

Anschlusspunkte
    ``kurbel``      Sitz auf der Kurbelwelle, Achse +X, Art *bohrung*
    ``nocken``      Sitz auf der ersten Nockenwelle, Achse +X, Art *bohrung*
    ``nocken_2..``  je eine weitere Nockenwelle
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
         rollen_d=6.35, nocken_lagen=None, doc=None, name="Steuertrieb"):
    """Steuertrieb als :class:`Bauteil`.

    art            "zahnrad" oder "kette"
    zaehne_kurbel  Zähnezahl am Kurbelwellenrad; das Nockenrad bekommt das
                   Doppelte — daher die 2:1
    modul          Verzahnungsmodul beim Zahnradtrieb [mm]
    teilung        Kettenteilung beim Kettentrieb [mm], üblich 9,525 (3/8")
    achsabstand    0 = aus den Raddurchmessern vorschlagen
    nocken_lagen   Liste von (y, z) je Nockenwelle. Ein DOHC-Kopf hat ZWEI,
                   und die Kette muss beide antreiben. Ohne Angabe wird eine
                   einzelne bei (0, achsabstand) angenommen.
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
        lagen = [(float(y), float(z)) for y, z in (nocken_lagen or [(0.0, a)])]
        # Die Raeder liegen in der YZ-Ebene, die Wellen laufen in X. Jede
        # Nockenwelle bekommt ihr eigenes Rad; die Zwischenraeder, die den
        # Achsabstand ueberbruecken, sind nicht dargestellt (siehe Docstring).
        eintraege = [(s1, (0.0, 0.0), "Kurbelwellenrad (z=%d)" % z1)]
        for nr, ort in enumerate(lagen, 1):
            eintraege.append((s2, ort,
                              "Nockenwellenrad %d (z=%d)" % (nr, z2)))
        for shp, (ry, rz), label in eintraege:
            t = shp.copy()
            t.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)
            t.translate(Vector(-float(breite) / 2.0, ry, rz))
            teile.append((label, t))
        k["nockenraeder"] = len(lagen)
        k["teilkreis_kurbel"] = round(d1, 2)
        k["teilkreis_nocken"] = round(d2, 2)
    else:
        d1, da1 = kettenradmasse(z1, teilung)
        d2, da2 = kettenradmasse(z2, teilung)
        lagen = list(nocken_lagen or [(0.0, a)])
        # Das Rad wird auf FUSSKREIS gezeichnet, nicht auf Kopfkreis: die
        # Rollen liegen auf dem Teilkreis, und ein Rad mit Kopfkreis
        # verschluckt sie ganz (gemessen: 100 % Durchdringung). Auf
        # Fusskreis (d - Rollendurchmesser) liegen sie ihm tangential auf.
        eintraege = [(d1, (0.0, 0.0), float(kurbel_d),
                      "Kettenrad Kurbel (z=%d)" % z1)]
        for nr, (ny, nz) in enumerate(lagen, 1):
            eintraege.append((d2, (float(ny), float(nz)), float(nocken_d),
                              "Kettenrad Nocken %d (z=%d)" % (nr, z2)))
        for d, (ry, rz), bohrung, label in eintraege:
            rad = Part.makeCylinder((d - float(rollen_d)) / 2.0,
                                    float(breite),
                                    Vector(-float(breite) / 2.0, ry, rz),
                                    Vector(1, 0, 0))
            # Ohne Bohrung steckt das Rad auf der Welle statt auf ihr zu
            # sitzen — gemessen 30,3 % Durchdringung mit der Kurbelwelle.
            if bohrung > 0.0:
                rad = rad.cut(Part.makeCylinder(
                    bohrung / 2.0 + 0.05, float(breite) + 4.0,
                    Vector(-float(breite) / 2.0 - 2.0, ry, rz),
                    Vector(1, 0, 0)))
            teile.append((label, rad))
        # Die Kette laeuft um ALLE Raeder — Kurbel und jede Nockenwelle.
        raeder = [((0.0, 0.0), d1 / 2.0)]
        for ny, nz in lagen:
            raeder.append(((float(ny), float(nz)), d2 / 2.0))
        if len(lagen) == 1:
            glieder, roh = kettenlaenge(z1, z2, a, teilung)
        else:
            # Die Zweiradformel gilt nicht mehr, sobald die Kette um drei
            # Raeder laeuft. Die Laenge kommt dann aus der Bahn selbst.
            roh = _bahnlaenge(_umlauf(raeder)) / float(teilung)
            glieder = int(math.ceil(roh))
            if glieder % 2:
                glieder += 1
        k["glieder"] = glieder
        k["glieder_roh"] = round(roh, 2)
        k["teilkreis_kurbel"] = round(d1, 2)
        k["teilkreis_nocken"] = round(d2, 2)
        k["nockenraeder"] = len(lagen)
        k["kettenlaenge"] = round(_bahnlaenge(_umlauf(raeder)), 1)
        teile.extend(_kettenbahn(raeder, float(teilung), float(rollen_d),
                                 float(breite)))

    # Die Bohrungsachsen zeigen zur Welle hin, also nach +X: der Zapfen
    # zeigt mit -X auf das Rad, das Rad mit +X auf den Zapfen. Standen beide
    # auf -X, drehte ``andocke`` den ganzen Trieb um 180 Grad um Z und
    # spiegelte ihn damit in y — bei einem V-Motor landete der Trieb der
    # einen Bank auf der anderen.
    punkte = [Punkt("kurbel", (0, 0, 0), (1, 0, 0), "bohrung",
                    float(kurbel_d), "Sitz auf der Kurbelwelle")]
    for nr, (ny, nz) in enumerate(lagen, 1):
        punkte.append(Punkt(
            "nocken" if nr == 1 else "nocken_%d" % nr,
            (0, float(ny), float(nz)), (1, 0, 0), "bohrung", float(nocken_d),
            "Sitz auf Nockenwelle %d" % nr))
    return Bauteil(name, koerper=teile, punkte=punkte, kennwerte=k)


def _tangente(c1, r1, c2, r2):
    """Äußere Tangente zweier Kreise: Normale und die beiden Berührpunkte.

    Beide Kreise werden mit derselben Normalen ``n`` berührt. Aus
    ``(C2-C1)·n = -(r2-r1)`` folgt die Normale; von den zwei Lösungen ist
    die zu nehmen, die beim Umlauf nach aussen zeigt.
    """
    dy, dz = c2[0] - c1[0], c2[1] - c1[1]
    abstand = math.hypot(dy, dz)
    if abstand < 1e-9:
        raise SteuertriebFehler("Zwei Kettenraeder liegen aufeinander.")
    u = (dy / abstand, dz / abstand)
    perp = (-u[1], u[0])
    k = (r2 - r1) / abstand
    k = max(-0.999, min(0.999, k))
    w = math.sqrt(max(0.0, 1.0 - k * k))
    # Aussen liegt beim Umlauf gegen den Uhrzeigersinn rechts der Fahrtrichtung.
    n = (-k * u[0] - w * perp[0], -k * u[1] - w * perp[1])
    p1 = (c1[0] + r1 * n[0], c1[1] + r1 * n[1])
    p2 = (c2[0] + r2 * n[0], c2[1] + r2 * n[1])
    return n, p1, p2


def _umlauf(raeder):
    """Die Räder in Umlaufreihenfolge (gegen den Uhrzeigersinn in der YZ-Ebene).

    Die Kette umschlingt sie von außen, also in der Reihenfolge der Punkte
    auf ihrer konvexen Hülle. Bei drei Rädern — Kurbel, Auslassnockenwelle,
    Einlassnockenwelle — ist die Hülle immer das Dreieck selbst, es genügt
    also die Sortierung nach dem Winkel um den Schwerpunkt. Das erste Rad
    (die Kurbel) bleibt am Anfang der Liste.
    """
    n = len(raeder)
    if n < 3:
        return list(raeder)
    sy = sum(r[0][0] for r in raeder) / float(n)
    sz = sum(r[0][1] for r in raeder) / float(n)
    sortiert = sorted(raeder, key=lambda r: math.atan2(r[0][1] - sz,
                                                       r[0][0] - sy))
    i = sortiert.index(raeder[0])
    return sortiert[i:] + sortiert[:i]


def _bahnlaenge(raeder):
    """Umfang der Kettenbahn: alle Tangenten plus alle Umschlingungsbögen."""
    n = len(raeder)
    tangenten = [_tangente(raeder[i][0], raeder[i][1],
                           raeder[(i + 1) % n][0], raeder[(i + 1) % n][1])
                 for i in range(n)]
    laenge = 0.0
    for i in range(n):
        _n, p1, p2 = tangenten[i]
        laenge += math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        a_ein = math.atan2(tangenten[(i - 1) % n][0][1],
                           tangenten[(i - 1) % n][0][0])
        a_aus = math.atan2(tangenten[i][0][1], tangenten[i][0][0])
        laenge += ((a_aus - a_ein) % (2.0 * math.pi)) * raeder[i][1]
    return laenge


def _kettenbahn(raeder, teilung, rollen_d, breite):
    """Die Kettenrollen um beliebig viele Räder.

    ``raeder`` ist eine Liste von ((y, z), radius) in Umlaufreihenfolge. Die
    Kette läuft auf den äusseren Tangenten und umschlingt jedes Rad zwischen
    zwei Tangenten — bei einem DOHC-Kopf also Kurbelrad, Auslass- und
    Einlassnockenwelle. Mit nur zwei Rädern wird die eine Nockenwelle nicht
    angetrieben, und genau das war der Fall.
    """
    if len(raeder) < 2:
        raise SteuertriebFehler("Eine Kette braucht mindestens zwei Raeder.")
    raeder = _umlauf(list(raeder))
    n = len(raeder)

    tangenten = []
    for i in range(n):
        j = (i + 1) % n
        tangenten.append(_tangente(raeder[i][0], raeder[i][1],
                                   raeder[j][0], raeder[j][1]))

    bahn = []

    def gerade(von, nach):
        laenge = math.hypot(nach[0] - von[0], nach[1] - von[1])
        stuecke = max(1, int(round(laenge / teilung)))
        for i in range(stuecke):
            t = i / float(stuecke)
            bahn.append((von[0] + (nach[0] - von[0]) * t,
                         von[1] + (nach[1] - von[1]) * t))

    def bogen(mitte, radius, start, ende):
        sweep = (ende - start) % (2.0 * math.pi)
        stuecke = max(1, int(round(sweep * radius / teilung)))
        for i in range(stuecke):
            w = start + sweep * i / float(stuecke)
            bahn.append((mitte[0] + radius * math.cos(w),
                         mitte[1] + radius * math.sin(w)))

    for i in range(n):
        vorher = tangenten[(i - 1) % n]
        jetzt = tangenten[i]
        mitte, radius = raeder[i]
        # Umschlingung: vom Berührpunkt der ankommenden Tangente zum
        # Berührpunkt der abgehenden.
        a_ein = math.atan2(vorher[0][1], vorher[0][0])
        a_aus = math.atan2(jetzt[0][1], jetzt[0][0])
        bogen(mitte, radius, a_ein, a_aus)
        gerade(jetzt[1], jetzt[2])

    # Zu dicht liegende Rollen fallen weg — Mindestabstand ist der
    # Rollendurchmesser, nicht die halbe Teilung.
    mindest = max(float(rollen_d) * 1.02, teilung * 0.5)
    gefiltert = []
    for pt in bahn:
        if all(math.hypot(pt[0] - q[0], pt[1] - q[1]) > mindest
               for q in gefiltert):
            gefiltert.append(pt)
    if len(gefiltert) > 1 and math.hypot(
            gefiltert[0][0] - gefiltert[-1][0],
            gefiltert[0][1] - gefiltert[-1][1]) < mindest:
        gefiltert.pop()

    rollen = []
    for i, pt in enumerate(gefiltert):
        rollen.append(("Kettenrolle %d" % (i + 1),
                       Part.makeCylinder(float(rollen_d) / 2.0, breite * 0.6,
                                         Vector(-breite * 0.3, pt[0], pt[1]),
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

    # --- Zwei Nockenwellen: BEIDE muessen an der Kette haengen -----------
    # Ein DOHC-Kopf hat Einlass- und Auslassnockenwelle. Mit nur zwei
    # Kettenraedern wurde die zweite gar nicht angetrieben.
    lagen = [(-60.0, 190.0), (60.0, 190.0)]
    d2 = kettenradmasse(40, 9.525)[0]
    t2 = baue(art="kette", zaehne_kurbel=20, teilung=9.525,
              nocken_lagen=lagen, doc=doc)
    raeder2 = [s for n, s in t2.koerper if n.startswith("Kettenrad")]
    if len(raeder2) != 3:
        raise AssertionError("bei zwei Nockenwellen braucht es drei "
                             "Kettenraeder, gebaut wurden %d" % len(raeder2))
    if t2.kennwerte.get("nockenraeder") != 2:
        raise AssertionError("die zweite Nockenwelle fehlt in den Kennwerten")
    # Auf jeder Nockenwelle muss wirklich ein Rad sitzen.
    for nr, (ny, nz) in enumerate(lagen, 1):
        p = t2.punkt("nocken" if nr == 1 else "nocken_%d" % nr)
        if abs(p.ort.y - ny) > 1e-9 or abs(p.ort.z - nz) > 1e-9:
            raise AssertionError("Anschlusspunkt %d liegt bei (%.1f, %.1f) "
                                 "statt (%.1f, %.1f)"
                                 % (nr, p.ort.y, p.ort.z, ny, nz))
        treffer = [s for s in raeder2
                   if abs((s.BoundBox.YMin + s.BoundBox.YMax) / 2.0 - ny) < 0.1
                   and abs((s.BoundBox.ZMin + s.BoundBox.ZMax) / 2.0 - nz) < 0.1]
        if len(treffer) != 1:
            raise AssertionError("auf Nockenwelle %d sitzt kein Kettenrad"
                                 % nr)
    # Die Kette muss jedes Rad wirklich umschlingen: um jedes Rad herum
    # gehoeren Rollen, und zwar auf seinem Teilkreis.
    rollen2 = [s for n, s in t2.koerper if n.startswith("Kettenrolle")]
    for nr, (ny, nz) in enumerate([(0.0, 0.0)] + lagen):
        r_soll = (kettenradmasse(20, 9.525)[0] if nr == 0 else d2) / 2.0
        nah = 0
        for s in rollen2:
            b = s.BoundBox
            dy = (b.YMin + b.YMax) / 2.0 - ny
            dz = (b.ZMin + b.ZMax) / 2.0 - nz
            if abs(math.hypot(dy, dz) - r_soll) < 0.5:
                nah += 1
        if nah < 4:
            raise AssertionError("Rad %d wird von der Kette nur mit %d "
                                 "Rollen umschlungen" % (nr + 1, nah))
    # Und sie darf weiterhin nirgends im Material stecken.
    for rad in raeder2:
        for r in rollen2:
            if rad.BoundBox.intersect(r.BoundBox) and \
                    rad.common(r).Volume > 1.0:
                raise AssertionError("eine Kettenrolle steckt im Rad")

    # Unsinnige Bauart.
    try:
        baue(art="riemen")
        raise AssertionError("unbekannte Bauart blieb unbemerkt")
    except SteuertriebFehler:
        pass

    return ("Steuertrieb-Selbsttest bestanden (2:1, Kette mit %d Gliedern, "
            "Achsabstand %.1f mm; zwei Nockenwellen: %d Raeder, %.0f mm "
            "Kette)" % (t.kennwerte["glieder"], t.kennwerte["achsabstand"],
                        len(raeder2), t2.kennwerte["kettenlaenge"]))
