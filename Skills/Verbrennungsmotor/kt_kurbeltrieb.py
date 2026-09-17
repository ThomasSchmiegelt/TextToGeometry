# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kurbeltrieb — Kurbelwelle, Pleuel und Kolben als eine Baugruppe.

    teile, proben, kw, zylinder_x = baue(bauform="V8", hub=86.0, ...)

Das ist der Motor ohne Kopf: was sich dreht und was auf und ab geht. Der
Ventiltrieb (``kt_ventiltrieb``) setzt darauf auf, und ``kt_motor`` fügt
beides zusammen.

Zusammengebaut wird über die Andockpunkte, nicht über gerechnete Koordinaten:

    Kurbelwelle.hubzapfen_k  ← Pleuel.hubzapfen
    Pleuel.kolbenbolzen      → Kolben.bolzen

Der **Kolben** läuft auf der Zylinderachse, nicht das Pleuel — das steht
schräg, und genau das ist der Schubkurbeltrieb. Gerichtet wird deshalb beides
mit ``kt_schnittstelle.richte()``: andocken, dann um den Anschluss drehen,
bis das andere Ende dort liegt, wo es hingehört.

Zurück kommen außer den Körpern auch ``zylinder_x`` — wo jeder Zylinder
wirklich steht. Beim V-Motor sind die beiden Pleuel eines Hubzapfens um die
halbe Breite versetzt; mit der Zapfenlage gerechnet standen die Ventile 28 mm
neben ihrem Kolben.
"""

import FreeCAD
from FreeCAD import Vector

import kt_bauformen as B
import kt_kinematik as K
import kt_kolben
import kt_kurbelwelle
import kt_pleuel
import kt_schnittstelle as S


def zapfenbreite(bauform, pleuel_breite, bankwinkel=0.0):
    """Breite eines Hubzapfens [mm].

    Beim V-Motor teilen sich zwei Pleuel einen Hubzapfen — er muss also
    doppelt so breit sein, und die beiden sitzen NEBENEINANDER.
    Übereinander gesetzt durchdrangen sie sich zu 53,6 %.

    Beim Reihenmotor trägt er eines, plus 4 mm Bund. Er **wächst mit der
    Pleuelbreite**: fest 26 mm getragen, stand bei 120 mm Bohrung ein
    30,7 mm breites Pleuel auf einem 26 mm breiten Zapfen über.
    """
    b = float(pleuel_breite)
    return (2.0 * b + 4.0) if B.ist_v(bauform, bankwinkel) else (b + 4.0)


def _flansch(flansch_d, flansch_t):
    """Nur wirkliche Werte durchreichen — 0 heisst "nicht angegeben".

    Ein blankes ``flansch_d=0.0`` an die Kurbelwelle weiterzugeben hiesse,
    den Flansch auf Durchmesser null zu setzen; genau diese Verwechslung
    hat in kt_auslegung einmal die ganze Tabelle mit Nullen ueberschrieben.
    """
    w = {}
    if float(flansch_d) > 0.0:
        w["flansch_d"] = float(flansch_d)
    if float(flansch_t) > 0.0:
        w["flansch_t"] = float(flansch_t)
    return w


def baue(bauform="R4", bohrung=86.0, hub=86.0, stichmass=150.5,
         kompressionshoehe=32.0, zylinderabstand=101.5, bolzen_d=22.0,
         hubzapfen_d=48.0, hauptlager_d=54.0, pleuel_breite=22.0,
         pleuel_auge_b=0.0, steuertrieb_d=30.0, zentrier_d=0.0,
         bankwinkel=0.0,
         wange_t=0.0, hauptlager_b=0.0, kolben_schafthoehe=0.0,
         kolben_boden_t=0.0, kolben_feuersteg=0.0, kolben_ringsteg=0.0,
         kolben_desachsierung=0.0, flansch_d=0.0, flansch_t=0.0,
         v8_kreuzebene=True, ventiltaschen=None):
    """Kurbelwelle, Pleuel und Kolben.

    Liefert ``(teile, proben, kurbelwelle, zylinder_x)``:

    teile       [(Bezeichnung, Shape), …]
    proben      [(Punkt A, Punkt B), …] für die Paarungsprüfung
    kurbelwelle das :class:`kt_schnittstelle.Bauteil` — der Ventiltrieb
                braucht seinen Steuertriebzapfen, der Motor den Flansch
    zylinder_x  {Zylindernummer: x-Lage} — wo der Kolben wirklich sitzt

    ``flansch_d`` / ``flansch_t`` überschreiben den Schwungradflansch der
    Kurbelwelle, wenn sie gesetzt sind (0 = die Vorgabe der Kurbelwelle
    behalten). Ein **Motorrad** hat keinen Schwungradflansch: dort sitzt am
    Kurbelwellenende das Primärritzel auf einem Zapfen, und ein 110-mm-
    Flansch stünde genau dort, wo das Ritzel hingehört.

    ``pleuel_auge_b`` ist die Breite des kleinen Auges, und der Kolben muss
    GENAU dafür seinen Schlitz frei lassen. Im Kolben stand dieses Maß
    früher fest auf 17 mm, im Pleuel ergab es sich zu 0,75·Breite = 16,5 —
    bei 86 mm Bohrung passte das zufällig, bei einer breiteren Pleuelstange
    nicht mehr. Jetzt kommt es aus ``kt_auslegung``, einmal für beide.
    """
    l = float(stichmass)
    pleuel_b = float(pleuel_breite)
    teile = []
    proben = []

    # Das Gegengewicht zeigt dem Hubzapfen entgegen — im UT also
    # geradewegs auf die Kolbenschuerze. Was dort frei bleibt, ist der
    # Abstand des Schuerzenendes von der Wellenachse im UT:
    #     (Stichmass - Kurbelradius) - Schafthoehe
    # Bei langem Hub ist das reichlich (86 x 86: 83,3 mm gegen 69,0), bei
    # kurzem nicht: 67 x 42,5 ergibt 34,4 mm gegen ein Gegengewicht von
    # 42,0 — gemessen 4,3 % Durchdringung mit Kolben 2. Deshalb wird das
    # Gegengewicht hier gedeckelt, wo Pleuellaenge und Kolben bekannt sind.
    schaft = float(kolben_schafthoehe) or round(float(bohrung) * 0.281, 2)
    gg_frei = round(l - float(hub) / 2.0 - schaft - 1.5, 2)

    kw = kt_kurbelwelle.baue(bauform=bauform, hub=hub,
                             zylinderabstand=zylinderabstand,
                             hauptlager_d=hauptlager_d,
                             hubzapfen_d=hubzapfen_d,
                             hubzapfen_b=zapfenbreite(bauform, pleuel_b,
                                                      bankwinkel),
                             bankwinkel=bankwinkel,
                             steuertrieb_d=float(steuertrieb_d),
                             zentrier_d=float(zentrier_d),
                             gegengewicht_r=gg_frei,
                             wange_t=float(wange_t) or 18.0,
                             hauptlager_b=float(hauptlager_b) or 26.0,
                             v8_kreuzebene=v8_kreuzebene,
                             **_flansch(flansch_d, flansch_t))
    teile.extend(kw.koerper)

    # Einmal gebaut und dann kopiert: eine Ventilfeder zu bauen dauert
    # Sekunden, und ein V12 mit vier Ventilen braeuchte achtundvierzig.
    auge_b = float(pleuel_auge_b) or round(pleuel_b * 0.75, 2)
    desachsierung = float(kolben_desachsierung)

    def kolben_mit(taschen):
        return kt_kolben.baue(bohrung=bohrung,
                              kompressionshoehe=kompressionshoehe,
                              bolzen_d=bolzen_d,
                              pleuel_b=round(auge_b + 0.5, 2),
                              schafthoehe=float(kolben_schafthoehe) or 48.0,
                              boden_t=float(kolben_boden_t) or 7.0,
                              feuersteg=float(kolben_feuersteg),
                              ringsteg=float(kolben_ringsteg),
                              desachsierung=float(kolben_desachsierung),
                              ventiltaschen=list(taschen or []))

    taschen = list(ventiltaschen or [])
    kolben_muster = kolben_mit(taschen)
    # Die Ventiltaschen sind um den Ventilwinkel GEKIPPT, und die Kipprichtung
    # haengt daran, wohin die lokale X-Richtung des Kolbens faellt. Das ist
    # nicht vorherzusagen — bei einem V8 mit 120 Grad Bankwinkel schlug es
    # zwischen den Baenken um, und die Tasche kippte zur falschen Seite
    # (25,8 % Durchdringung mit dem Einlassventil). Deshalb gibt es ein
    # zweites Muster mit umgekehrter Kippung, und je Zylinder wird gemessen,
    # welches passt.
    gekippt = any(len(t) > 4 and abs(float(t[4])) > 1e-9 for t in taschen)
    kolben_gespiegelt = kolben_mit(
        [(t[0], t[1], t[2], t[3], -float(t[4])) if len(t) > 4 else t
         for t in taschen]) if gekippt else kolben_muster
    pleuel_muster = kt_pleuel.baue(stichmass=l, hubzapfen_d=hubzapfen_d,
                                   bolzen_d=bolzen_d, breite=pleuel_b,
                                   klein_b=auge_b)

    lagen = B.zylinderlagen(bauform, zylinderabstand, v8_kreuzebene,
                            bankwinkel)
    versatz = B.hubzapfenversatz(bauform, v8_kreuzebene, bankwinkel)
    zylinder_x = {}

    for nr, (seite, _x, bankwinkel, zapfen) in enumerate(lagen, 1):
        # Welchen Hubzapfen? Bei geteiltem Zapfen die Haelfte der Bank.
        name = "hubzapfen_%d" % (zapfen + 1)
        if versatz and B.ist_v(bauform, bankwinkel):
            name = "hubzapfen_%d%s" % (zapfen + 1, "a" if seite == 0 else "b")
        ziel = kw.punkt(name)
        if B.ist_v(bauform, bankwinkel) and not versatz:
            # Ungeteilter Zapfen: die beiden Baenke nebeneinander setzen.
            ziel = S.Punkt(ziel.name,
                           Vector(ziel.ort).add(Vector(
                               (pleuel_b / 2.0) * (-1.0 if seite == 0
                                                   else 1.0), 0, 0)),
                           ziel.achse, ziel.art, ziel.mass, ziel.hinweis)

        # Der KOLBEN laeuft auf der Zylinderachse, nicht das Pleuel. Vorher
        # war das Pleuel parallel zur Zylinderachse gerichtet, und die
        # Kolben einer Bank lagen dadurch nicht auf einer Linie: bei Bank A
        # eines V8 auf (-100,8|143,8), (-143,8|100,8), (-57,8|100,8) statt
        # auf der Bankachse.
        richtung = K.zylinderachse(bankwinkel)
        # Desachsierung: der Bolzen sitzt im Kolben aussermittig, also muss
        # er um denselben Betrag NEBEN der Zylinderachse liegen, damit der
        # Kolben selbst auf ihr laeuft. Die Richtung des Versatzes ist quer
        # zur Bolzenachse, also in der Bankebene.
        quer = Vector(1, 0, 0).cross(richtung)
        if quer.Length < 1e-9:
            quer = Vector(0, 1, 0)
        quer.normalize()
        stuetz = Vector(quer).multiply(float(desachsierung))
        pleuel = S.richte(pleuel_muster, "hubzapfen", "kolbenbolzen", ziel,
                          K.pleuelrichtung(ziel.ort, richtung, l, stuetz))
        teile.extend([("Pleuel %d" % nr, s) for _n, s in pleuel.koerper])
        proben.append((pleuel.punkt("hubzapfen"), ziel))

        # Andocken legt die Verdrehung UM die Bolzenachse nicht fest — die
        # kuerzeste Drehung traf beim Reihenmotor zufaellig, beim V-Motor
        # nicht, und die Ventiltaschen standen schief zu den Ventilen
        # (11 bis 24 % Durchdringung). Deshalb wird der Kolben wie das
        # Pleuel ausgerichtet: sein Boden zeigt die Zylinderachse entlang.
        kolben = S.richte(kolben_muster, "bolzen", "boden",
                          pleuel.punkt("kolbenbolzen"), richtung)
        if gekippt:
            # Wohin ist die lokale +X-Richtung gefallen? Zeigt sie gegen
            # `quer`, kippen die Taschen verkehrt herum, und das gespiegelte
            # Muster ist das richtige.
            marke = Vector(kolben.punkt("quermarke").ort).sub(
                Vector(kolben.punkt("bolzen").ort))
            if marke.dot(quer) < 0.0:
                kolben = S.richte(kolben_gespiegelt, "bolzen", "boden",
                                  pleuel.punkt("kolbenbolzen"), richtung)
        teile.extend([("Kolben %d" % nr, s) for _n, s in kolben.koerper])
        proben.append((kolben.punkt("bolzen"), pleuel.punkt("kolbenbolzen")))
        zylinder_x[nr] = kolben.punkt("bolzen").ort.x

    return teile, proben, kw, zylinder_x


def selbsttest(bauform="V8"):
    """Baut einen Kurbeltrieb und misst die Zusagen nach."""
    import math

    import kt_auslegung

    # Aus der Tabelle bauen, nicht aus den Vorgabewerten dieser Funktion:
    # ein V8 teilt seine Hubzapfen breiter, und dann reicht der
    # Zylinderabstand von 1,18 x Bohrung nicht mehr.
    aus = kt_auslegung.auslegen(bohrung=86.0, hub=86.0, bauform=bauform)
    teile, proben, kw, zylinder_x = baue(
        bauform=bauform, bohrung=aus["bohrung"], hub=aus["hub"],
        stichmass=aus["stichmass"],
        kompressionshoehe=aus["kompressionshoehe"],
        zylinderabstand=aus["zylinderabstand"],
        bolzen_d=aus["kolbenbolzen_d"], hubzapfen_d=aus["hubzapfen_d"],
        hauptlager_d=aus["hauptlager_d"], pleuel_breite=aus["pleuel_breite"],
        pleuel_auge_b=aus["pleuel_auge_b"],
        steuertrieb_d=aus["steuertrieb_d"], wange_t=aus["wange_t"],
        hauptlager_b=aus["hauptlager_b"],
        kolben_schafthoehe=aus["kolben_schafthoehe"],
        kolben_boden_t=aus["kolben_boden_t"],
        kolben_feuersteg=aus["kolben_feuersteg"],
        kolben_ringsteg=aus["kolben_ringsteg"],
        kolben_desachsierung=aus["kolben_desachsierung"])
    z, bank = B.daten(bauform)
    if len(zylinder_x) != z:
        raise AssertionError("%d Zylinder statt %d" % (len(zylinder_x), z))
    for wort, soll in (("Kolben", z), ("Pleuel", z)):
        ist = sum(1 for n, _s in teile if n.startswith(wort))
        if ist != soll:
            raise AssertionError("%d %s fuer %d Zylinder" % (ist, wort, soll))
    if not all(s.Solids for _n, s in teile):
        raise AssertionError("nicht jeder Koerper ist ein Solid")

    # Jede Paarung muss wirklich aufeinanderliegen.
    for a, b in proben:
        ok, text = S.pruefe_paarung(a, b)
        if not ok:
            raise AssertionError(text)

    # Die Kolben einer Bank liegen auf ihrer Bankachse — beim 90-Grad-V8
    # also auf |y| = |z|. Das ist die Probe auf die Schubkurbel: mit einem
    # zur Zylinderachse parallelen Pleuel stimmt es nicht.
    if B.ist_v(bauform):
        lagen = B.zylinderlagen(bauform, aus["zylinderabstand"], True)
        for nr, (seite, _x, bw, _zapfen) in enumerate(lagen, 1):
            k = [s for n, s in teile if n == "Kolben %d" % nr][0]
            b = k.BoundBox
            y = (b.YMin + b.YMax) / 2.0
            zz = (b.ZMin + b.ZMax) / 2.0
            soll = math.tan(math.radians(bw))
            if abs(y - zz * soll) > 1.0:
                raise AssertionError(
                    "Kolben %d (Bank %d) liegt bei (%.1f|%.1f), nicht auf "
                    "der Bankachse" % (nr, seite + 1, y, zz))

    # Der Steuertriebzapfen und der Abtriebsflansch muessen da sein — der
    # Ventiltrieb und das Getriebe haengen daran.
    for pflicht in ("steuertrieb", "abtrieb"):
        kw.punkt(pflicht)
    return ("Kurbeltrieb-Selbsttest bestanden (%s, %d Koerper, %d Paarungen)"
            % (bauform, len(teile), len(proben)))
