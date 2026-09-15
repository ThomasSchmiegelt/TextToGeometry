# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kinematik des Kurbeltriebs — Rechnung ohne Geometrie.

Hier steht, was ein Kurbeltrieb tut, nicht wie er aussieht: wo der Kolben
bei einem Kurbelwinkel steht, in welche Richtung das Pleuel dabei zeigt, wie
weit ein Nocken einen Flachstößel gerade anhebt, wie hoch der Block sein muss
und wie weit die zweite Bank eines V-Motors versetzt steht.

Getrennt gehalten, weil es in jedem dieser Punkte schon einmal falsch war und
sich eine Formel prüfen lässt, ohne einen Motor zu bauen. Der Selbsttest
rechnet gegen bekannte Werte: im oberen und unteren Totpunkt muss die
Schubkurbel 0 und 2·r ergeben, der Nockenhub genau die Erhebung, und der
Bankversatz eines V8 eine Pleuelbreite.

Gebraucht wird nur ``FreeCAD.Vector`` als Vektorrechnung, keine Formkörper.
"""

import math

import FreeCAD  # noqa: F401  (Vector kommt von hier)
from FreeCAD import Vector

import kt_bauformen as B


class KinematikFehler(Exception):
    pass


def blockhoehe(hub, stichmass, kompressionshoehe):
    """Kurbelwellenmitte bis Kolbenboden im oberen Totpunkt [mm]."""
    return float(hub) / 2.0 + float(stichmass) + float(kompressionshoehe)


def zylinderachse(bankwinkel_grad):
    """Richtung der Zylinderachse: aus der Senkrechten um den Bankwinkel."""
    w = math.radians(float(bankwinkel_grad))
    return Vector(0.0, math.sin(w), math.cos(w))


def kolbenweg(kurbelwinkel_grad, kurbelradius, stichmass):
    """Wie weit der Kolben vom oberen Totpunkt heruntergelaufen ist [mm].

    Die Schubkurbel:  s = r(1 - cos phi) + l(1 - sqrt(1 - lambda^2 sin^2 phi)),
    mit lambda = r/l. Bei phi = 0 ist der Kolben oben, s = 0.
    """
    phi = math.radians(float(kurbelwinkel_grad))
    r = float(kurbelradius)
    l = float(stichmass)
    lam = r / l if l else 0.0
    wurzel = max(0.0, 1.0 - (lam * math.sin(phi)) ** 2)
    return r * (1.0 - math.cos(phi)) + l * (1.0 - math.sqrt(wurzel))


def pleuelrichtung(hubzapfen, achse, stichmass, versatz=None):
    """Richtung vom Hubzapfen zum Kolbenbolzen.

    Der Kolbenbolzen liegt auf einer Geraden in Richtung ``achse``, im
    Abstand ``stichmass`` vom Hubzapfen. Das ist die Schubkurbel: aus

        |Q + t·achse − P| = l

    folgt ``t = achse·R + sqrt((achse·R)² − |R|² + l²)`` mit ``R = P − Q``.
    Die positive Wurzel ist der Kolben oberhalb der Kurbel.

    ``versatz`` ist der Stützpunkt Q der Geraden. Ohne ihn geht sie durch
    die Kurbelwellenmitte — das ist der Normalfall. Mit ihm liegt sie um
    die **Desachsierung** daneben: der Kolbenbolzen sitzt im Kolben
    außermittig, und wenn der Kolben selbst auf der Zylinderachse laufen
    soll, muss der Bolzen genau um diesen Betrag daneben liegen. Ohne
    diesen Stützpunkt wandert stattdessen der ganze Kolben von der
    Zylinderachse weg — gemessen bei einem V8 auf (−128,0 | 129,1) statt
    auf der Bankachse.
    """
    p = Vector(hubzapfen)
    a = Vector(achse)
    a.normalize()
    q = Vector(versatz) if versatz is not None else Vector(0, 0, 0)
    # Nur die Ebene senkrecht zur Kurbelwelle zaehlt; x bleibt, wie es ist.
    p_eben = Vector(0.0, p.y - q.y, p.z - q.z)
    ap = a.dot(p_eben)
    wurzel = ap * ap - p_eben.Length ** 2 + float(stichmass) ** 2
    if wurzel < 0.0:
        raise KinematikFehler(
            "Das Stichmass %.1f mm reicht nicht bis zur Zylinderachse — der "
            "Kurbelradius ist zu gross." % float(stichmass))
    t = ap + math.sqrt(wurzel)
    bolzen = Vector(p.x, q.y + a.y * t, q.z + a.z * t)
    richtung = bolzen.sub(p)
    if richtung.Length < 1e-9:
        return Vector(a)
    richtung.normalize()
    return richtung


def nockenhub(winkel_grad, hub, grundkreis_r=16.0, flanke=60.0,
               stoessel_winkel=180.0, schritte=180):
    """Hub, den der Nocken einem FLACHSTÖSSEL gerade gibt [mm].

    Bei einem Flachstößel ist der Hub nicht der radiale Abstand in
    Stößelrichtung, sondern die größte Projektion der ganzen Nockenkontur auf
    diese Richtung: der Berührpunkt wandert seitlich aus. Mit dem radialen
    Maß gerechnet blieb eine Durchdringung von 4,8 % zwischen Nockenwelle und
    Stößel — die Welle sass zu tief.

    ``stoessel_winkel`` ist die Richtung, in der der Stößel steht — beim
    Reihenmotor 180° (senkrecht nach unten), bei einer um den Bankwinkel
    geneigten Bank entsprechend gedreht. Mit festen 180° gerechnet stimmte
    der Hub bei V-Motoren nicht, und die Nockenwelle durchdrang die Stößel.
    """
    rg = float(grundkreis_r)
    h = float(hub)
    fl = float(flanke)
    spitze = math.radians(float(winkel_grad))
    stoessel = math.radians(float(stoessel_winkel))
    groesste = rg
    for i in range(int(schritte)):
        a = 2.0 * math.pi * i / float(schritte)
        d = math.degrees((a - spitze + math.pi) % (2.0 * math.pi) - math.pi)
        r = rg + (h * 0.5 * (1.0 + math.cos(math.pi * d / fl))
                  if abs(d) < fl else 0.0)
        groesste = max(groesste, r * math.cos(a - stoessel))
    return max(0.0, groesste - rg)


def bankversatz(bauform, pleuel_breite, v8_kreuzebene=True,
                bankwinkel=0.0):
    """Axialer Versatz der zweiten Zylinderbank [mm].

    Beim V-Motor sitzen die beiden Pleuel nebeneinander auf demselben
    Hubzapfen — die Bänke stehen deshalb zwangsläufig gegeneinander versetzt.
    Wie weit, hängt vom Zapfen ab:

    * ungeteilter Zapfen: um eine Pleuelbreite (V8, V10, V12)
    * geteilter Zapfen: um eine halbe Zapfenbreite, denn die beiden Hälften
      liegen selbst schon hintereinander (V4, V6) — gemessen 24 statt 22 mm
    """
    if not B.ist_v(bauform, bankwinkel):
        return 0.0
    b = float(pleuel_breite)
    if B.hubzapfenversatz(bauform, v8_kreuzebene, bankwinkel):
        return (2.0 * b + 4.0) / 2.0
    return b


def nockenwinkel(kurbelwinkel_grad, spreizung, art):
    """Nockenwinkel eines Ventils [Grad Nockenwelle].

    Der Nocken dreht halb so schnell wie die Kurbel. Der Scheitel liegt um
    die **Spreizung** nach dem oberen Totpunkt (Einlass) bzw. davor
    (Auslass); der Auslassnocken eilt zusätzlich um eine halbe
    Nockenwellenumdrehung vor, weil er im vorangegangenen Takt arbeitet.
    """
    versatz = float(spreizung) * (1.0 if art == "einlass" else -1.0)
    return ((float(kurbelwinkel_grad) + versatz) / 2.0
            + (0.0 if art == "einlass" else 180.0)) % 360.0


def taschentiefe(bauform, hub, stichmass, zylinderabstand, ventilhub,
                 spreizung=110.0, grundkreis_r=16.0, v8_kreuzebene=True,
                 luft=1.5, bankwinkel=0.0):
    """Nötige Tiefe der Ventiltaschen im Kolbenboden [mm].

    Nicht der volle Ventilhub bestimmt sie, sondern der **Überstand des
    Ventils über dem Kolbenboden**: wenn das Ventil weit offen ist, ist der
    Kolben meist schon ein Stück heruntergelaufen. Mit dem vollen Hub
    gerechnet wurden die Taschen 13 mm tief statt der üblichen 2…4.

    Gerechnet wird über alle Zylinder und beide Ventilsorten, damit eine
    Tiefe für alle Kolben reicht.
    """
    lagen = B.zylinderlagen(bauform, zylinderabstand, v8_kreuzebene,
                            bankwinkel)
    versatz = B.hubzapfenversatz(bauform, v8_kreuzebene, bankwinkel)
    winkel = B.zapfenwinkel(bauform, v8_kreuzebene)
    noetig = 0.0
    for seite, _x, _bw, zapfen in lagen:
        kwz = winkel[zapfen] + (versatz if (seite == 1 and versatz) else 0.0)
        weg = kolbenweg(kwz, float(hub) / 2.0, float(stichmass))
        for art in ("einlass", "auslass"):
            w = nockenwinkel(kwz, spreizung, art)
            noetig = max(noetig, nockenhub(w, ventilhub, grundkreis_r,
                                           stoessel_winkel=180.0) - weg)
    return round(max(1.0, noetig) + float(luft), 2)


def selbsttest():
    """Rechnet die Kinematik gegen bekannte Werte nach."""
    r, l = 43.0, 150.5

    # Schubkurbel: OT ist 0, UT ist der ganze Hub, und dazwischen liegt der
    # Kolben IMMER tiefer als die reine Kosinusnaeherung — das ist der
    # Pleuelanteil.
    if abs(kolbenweg(0.0, r, l)) > 1e-9:
        raise AssertionError("im oberen Totpunkt muss der Weg 0 sein")
    if abs(kolbenweg(180.0, r, l) - 2.0 * r) > 1e-9:
        raise AssertionError("im unteren Totpunkt muss der Weg 2*r sein")
    if not kolbenweg(90.0, r, l) > r:
        raise AssertionError("bei 90 Grad steht der Kolben unter der "
                             "Kreisnaeherung — der Pleuelanteil fehlt")

    # Blockhoehe.
    if abs(blockhoehe(86.0, 150.5, 32.0) - (43.0 + 150.5 + 32.0)) > 1e-9:
        raise AssertionError("Blockhoehe ist Kurbelradius + Stichmass + "
                             "Kompressionshoehe")

    # Nockenhub: der Flachstoessel steht dem Nockenscheitel gegenueber, also
    # bei 180 Grad. Steht der Scheitel dort, ist der Hub die volle Erhebung.
    if abs(nockenhub(180.0, 10.0, 16.0, stoessel_winkel=180.0) - 10.0) > 0.05:
        raise AssertionError("bei 180 Grad muss der volle Hub anliegen")
    if nockenhub(0.0, 10.0, 16.0, stoessel_winkel=180.0) > 0.01:
        raise AssertionError("ein abgewandter Nocken darf nicht anheben")
    # Und er ist nie negativ und nie groesser als die Erhebung.
    for w in range(0, 360, 5):
        h = nockenhub(float(w), 10.0, 16.0, stoessel_winkel=180.0)
        if h < -1e-9 or h > 10.0 + 1e-6:
            raise AssertionError("Nockenhub %.3f bei %d Grad liegt ausserhalb"
                                 % (h, w))

    # Pleuelrichtung: beim Reihenmotor mit dem Zapfen im OT zeigt das Pleuel
    # senkrecht nach oben.
    senkrecht = zylinderachse(0.0)
    ri = pleuelrichtung(Vector(0.0, 0.0, r), senkrecht, l)
    if abs(ri.y) > 1e-9 or ri.z < 0.99:
        raise AssertionError("im oberen Totpunkt steht das Pleuel senkrecht, "
                             "gemessen (%.3f, %.3f, %.3f)"
                             % (ri.x, ri.y, ri.z))
    # Steht der Zapfen quer, muss das Pleuel schraeg stehen — und zwar
    # genau so schraeg, dass sein anderes Ende auf der Zylinderachse liegt.
    quer = pleuelrichtung(Vector(0.0, r, 0.0), senkrecht, l)
    ende = Vector(0.0, r, 0.0).add(Vector(quer).multiply(l))
    if abs(ende.y) > 1e-6:
        raise AssertionError("der Kolbenbolzen liegt %.4f mm neben der "
                             "Zylinderachse" % ende.y)
    # Zu kurzes Pleuel muss auffallen.
    try:
        pleuelrichtung(Vector(0.0, 100.0, 0.0), senkrecht, 20.0)
        raise AssertionError("ein zu kurzes Pleuel blieb unbemerkt")
    except KinematikFehler:
        pass

    # Zylinderachse: 0 Grad senkrecht, 45 Grad genau auf der Winkelhalbierenden.
    a45 = zylinderachse(45.0)
    if abs(a45.y - a45.z) > 1e-9:
        raise AssertionError("bei 45 Grad muss y gleich z sein")

    # Bankversatz: Reihenmotor 0, V8 (ungeteilter Zapfen) eine Pleuelbreite,
    # V6 (geteilter Zapfen) die halbe Zapfenbreite.
    if bankversatz("R4", 22.0) != 0.0:
        raise AssertionError("ein Reihenmotor hat keinen Bankversatz")
    if abs(bankversatz("V8", 22.0) - 22.0) > 1e-9:
        raise AssertionError("V8: Versatz ist eine Pleuelbreite")
    if abs(bankversatz("V6", 22.0) - 24.0) > 1e-9:
        raise AssertionError("V6: Versatz ist die halbe Zapfenbreite")

    # Nockenwinkel: halbe Drehzahl, Auslass eine halbe Umdrehung vor.
    if abs(nockenwinkel(0.0, 0.0, "einlass")) > 1e-9:
        raise AssertionError("ohne Spreizung liegt der Einlassscheitel im OT")
    if abs(nockenwinkel(0.0, 0.0, "auslass") - 180.0) > 1e-9:
        raise AssertionError("der Auslassnocken eilt um 180 Grad vor")

    tiefe = taschentiefe("V8", 86.0, 150.5, 101.5, 10.0)
    if not 2.0 < tiefe < 8.0:
        raise AssertionError("Ventiltaschen %.1f mm tief — ueblich sind 2…4"
                             % tiefe)
    return ("Kinematik-Selbsttest bestanden (Hub 0…%.1f mm, Nockenhub bis "
            "%.1f mm, Taschen %.1f mm)"
            % (kolbenweg(180.0, r, l), nockenhub(180.0, 10.0, 16.0), tiefe))
