# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kolben — Boden, Ringpartie, Schaft, Bolzenaugen.

Bewusst grob: ein Zylinder mit Ringnuten, ausgehöhltem Schaft und einer
Querbohrung für den Kolbenbolzen. Was zählt, sind die Anschlusspunkte.

Gebaut wird entlang **+Z**, mit dem Bolzen auf der **Y-Achse**. Der Ursprung
liegt in der Kolbenbolzenmitte — nicht am Boden. Das ist die Stelle, an der
der Kolben am Pleuel hängt, und damit die einzige, die beim Zusammenbau
zählt. Die Kompressionshöhe (Abstand Bolzenmitte bis Boden) ist ein
Eingabewert, kein Nebenprodukt.

Anschlusspunkte
    ``bolzen``   Bolzenmitte, Achse +Y, Art *welle*  (das Pleuelauge kommt
                 hier drauf)
    ``boden``    Kolbenbodenmitte, Achse +Z, Art *flaeche*
    ``laufbahn`` Mitte der Ringpartie, Achse +Z, Art *gleitbahn* (die
                 Zylinderlaufbahn dockt hier an)
"""

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def kennwerte(bohrung=86.0, kompressionshoehe=32.0, bolzen_d=22.0,
              schafthoehe=48.0, **_rest):
    """Maße, die andere Bauteile brauchen — ohne Geometrie."""
    d = float(bohrung)
    return {
        "bohrung": d,
        "kolben_d": round(d - 0.12, 3),        # Laufspiel
        "kompressionshoehe": float(kompressionshoehe),
        "bolzen_d": float(bolzen_d),
        "gesamthoehe": float(kompressionshoehe) + float(schafthoehe),
    }


def baue(bohrung=86.0, kompressionshoehe=32.0, bolzen_d=22.0,
         schafthoehe=48.0, boden_t=7.0, ringe=3, ringnut_h=1.5,
         ringnut_t=2.0, laufspiel=0.12, pleuel_b=17.0, pleuel_spiel=0.5,
         feuersteg=0.0, ringsteg=0.0, desachsierung=0.0,
         ventiltaschen=None, name="Kolben"):
    """Ein Kolben als :class:`Bauteil`.

    bohrung            Zylinderbohrung [mm]; der Kolben ist um das Laufspiel
                       kleiner
    kompressionshoehe  Bolzenmitte bis Kolbenboden [mm]
    bolzen_d           Kolbenbolzendurchmesser [mm]
    feuersteg          Abstand von der Bodenkante zur Oberflanke der ersten
                       Ringnut [mm]; 0 = ``boden_t``. Beim Ottomotor 4 bis
                       10 % der Bohrung. Er hält den ersten Ring aus der
                       heißesten Zone heraus und ist zugleich ein Spalt, der
                       unverbranntes Gemisch festhält — deshalb so klein wie
                       eben möglich.
    ringsteg           Höhe des Steges zwischen zwei Ringnuten [mm];
                       0 = 2 · ``ringnut_h``. Der erste Ringsteg trägt den
                       vollen Gasdruck und ist mit 4,0 bis 5,5 % der Bohrung
                       der kräftigste.
    desachsierung      Versatz der Bolzenachse gegen die Kolbenlängsachse
                       [mm], quer zur Bolzenachse. Er ändert den
                       Anlagewechsel des Schafts an der Zylinderwand und
                       senkt Laufgeräusch und Kavitationsgefahr. Üblich rund
                       1 % der Bohrung; das Vorzeichen zeigt zur Druckseite.
    schafthoehe        Bolzenmitte bis Schaftende [mm]
    boden_t            Dicke des Kolbenbodens [mm]
    ringe              Zahl der Kolbenringe
    pleuel_b           Breite des kleinen Pleuelauges [mm] — dafür bleibt
                       zwischen den Bolzennaben ein Schlitz frei
    ventiltaschen      Liste von ``(x, y, d, tiefe)`` oder
                       ``(x, y, d, tiefe, neigung)`` im
                       Kolbenkoordinatensystem: Mulden im Boden, damit die
                       Ventile bei der Überschneidung am oberen Totpunkt
                       nicht anschlagen. Ohne sie durchdringen sich Kolben
                       und Ventil — real ist genau das der Grund, warum es
                       Ventiltaschen gibt.

                       ``neigung`` [Grad] kippt die Mulde um die lokale
                       Y-Achse, **senkrecht zur Ventilachse**. Ein geneigtes
                       Ventil taucht mit seiner unteren Tellerkante schräg
                       ein; eine gerade Mulde müsste dafür so tief werden,
                       dass sie ein Drittel des Kolbens wegnimmt (gemessen
                       30 % bei 28 Grad Ventilwinkel). Gekippt bleibt sie
                       bei den üblichen 2…5 mm.
    """
    d = float(bohrung) - float(laufspiel)
    r = d / 2.0
    kh = float(kompressionshoehe)
    sh = float(schafthoehe)
    bd = float(bolzen_d)

    if kh <= float(boden_t) + bd / 2.0:
        raise ValueError(
            "Kompressionshoehe %.1f mm ist zu klein: Boden (%.1f) und halber "
            "Bolzen (%.1f) passen nicht darunter."
            % (kh, float(boden_t), bd / 2.0))

    # Grundkoerper: von -sh (Schaftende) bis +kh (Boden), Ursprung = Bolzen.
    koerper = Part.makeCylinder(r, kh + sh, Vector(0, 0, -sh))

    # Ringnuten. Ueber der ERSTEN liegt der Feuersteg, zwischen den
    # weiteren je ein Ringsteg — beides eigene Masse, keine Vielfachen der
    # Nuthoehe. Frueher war der Feuersteg mit der Bodendicke identisch und
    # der Ringsteg doppelte Nuthoehe (2 x 1,5 = 3 mm, also 0,023 x Bohrung
    # statt der geforderten 0,040…0,055).
    fs = float(feuersteg) or float(boden_t)
    rs = float(ringsteg) or 2.0 * float(ringnut_h)
    z = kh - fs
    for i in range(max(0, int(ringe))):
        z -= float(ringnut_h)
        nut = Part.makeCylinder(r + 1.0, float(ringnut_h), Vector(0, 0, z))
        kern = Part.makeCylinder(r - float(ringnut_t), float(ringnut_h) + 2.0,
                                 Vector(0, 0, z - 1.0))
        koerper = koerper.cut(nut.cut(kern))
        # Der erste Ringsteg traegt den vollen Gasdruck, die folgenden
        # weniger — sie duerfen schmaler sein.
        z -= rs if i == 0 else rs * 0.8

    # Schaft aushoehlen: von unten bis knapp unter den Boden.
    hohl_r = r - 4.0
    hohl_h = kh - float(boden_t) - 2.0 + sh
    if hohl_r > bd and hohl_h > 0:
        koerper = koerper.cut(Part.makeCylinder(hohl_r, hohl_h,
                                                Vector(0, 0, -sh)))
        # Die Bolzennaben bleiben stehen — aber NUR aussen. In der Mitte
        # muss das kleine Pleuelauge Platz haben; ein durchgehender
        # Nabenzylinder hat es um 7936 mm^3 durchdrungen.
        nabe = Part.makeCylinder(bd, d, Vector(float(desachsierung),
                                                -d / 2.0, 0),
                                 Vector(0, 1, 0))
        schlitz_b = float(pleuel_b) + 2.0 * float(pleuel_spiel)
        schlitz = Part.makeBox(d + 4.0, schlitz_b, d + 4.0,
                               Vector(-d / 2.0 - 2.0, -schlitz_b / 2.0,
                                      -d / 2.0 - 2.0))
        nabe = nabe.cut(schlitz)
        koerper = koerper.fuse(nabe.common(
            Part.makeCylinder(r, kh + sh, Vector(0, 0, -sh))))

    # Ventiltaschen im Boden.
    for tasche in (ventiltaschen or []):
        werte = [float(v) for v in tasche]
        tx, ty, td, tt = werte[:4]
        neigung = werte[4] if len(werte) > 4 else 0.0
        if td <= 0.0 or tt <= 0.0:
            continue
        mulde = Part.makeCylinder(td / 2.0, tt + 6.0,
                                  Vector(tx, ty, kh - tt))
        if abs(neigung) > 1e-9:
            # Um die lokale Y-Achse kippen, Drehpunkt in der Muldenmitte an
            # der Kolbenoberkante: dort sitzt das Ventil, und dort soll die
            # Mulde bleiben, wenn sie sich neigt.
            # Placement(Base, Rotation, Center): der DRITTE Wert ist der
            # Drehpunkt, der erste eine zusaetzliche Verschiebung. Beide
            # belegt, flog die Mulde aus dem Kolben heraus und nahm nichts
            # mehr weg.
            mulde.Placement = FreeCAD.Placement(
                Vector(0, 0, 0),
                FreeCAD.Rotation(Vector(0, 1, 0), float(neigung)),
                Vector(tx, ty, kh)).multiply(mulde.Placement)
        # KEIN common() zum Beschneiden: gegen einen Zylinder verschnitten
        # kam ein leerer Koerper zurueck, und die Mulde nahm gar nichts mehr
        # weg (gemessen: Kolben unveraendert, Ventil 21 % im Material).
        # Sie ragt stattdessen oben heraus, wo ohnehin nichts ist.
        vorher = koerper.Volume
        geschnitten = koerper.cut(mulde)
        if geschnitten.Volume < vorher - 1.0:
            koerper = geschnitten
        else:
            raise ValueError(
                "Die Ventiltasche bei (%.1f, %.1f) nimmt kein Material weg "
                "— dann sitzt sie neben dem Kolbenboden." % (tx, ty))

    # Bolzenbohrung quer durch — um die Desachsierung versetzt. Der Versatz
    # liegt QUER zur Bolzenachse, also in x; die Bolzenachse selbst laeuft
    # in y.
    da = float(desachsierung)
    koerper = koerper.cut(Part.makeCylinder(bd / 2.0, d + 4.0,
                                            Vector(da, -d / 2.0 - 2.0, 0),
                                            Vector(0, 1, 0)))

    return Bauteil(
        name,
        koerper=[(name, koerper.removeSplitter())],
        punkte=[
            Punkt("bolzen", (float(desachsierung), 0, 0), (0, 1, 0),
                  "welle", bd,
                  "Kolbenbolzenmitte – hier haengt das Pleuel"),
            Punkt("boden", (0, 0, kh), (0, 0, 1), "flaeche", d,
                  "Kolbenboden – begrenzt den Brennraum"),
            Punkt("laufbahn", (0, 0, kh - float(boden_t)), (0, 0, 1),
                  "gleitbahn", d, "Ringpartie – laeuft in der Zylinderbohrung"),
            # Eine Marke auf der lokalen +X-Seite. Sie traegt nichts und
            # paart mit nichts — sie sagt nach dem Andocken, WOHIN die
            # lokale X-Richtung gefallen ist. Das ist nicht vorhersagbar:
            # ``richte()`` legt die Drehung um den Bolzen fest, und ob
            # lokal +X dann laengs oder quer zur Kurbelwelle zeigt, kippt
            # zwischen den Baenken eines V-Motors um. Die gekippten
            # Ventiltaschen haengen daran.
            Punkt("quermarke", (r, 0, 0), (1, 0, 0), "flaeche", 0.0,
                  "Marke auf der lokalen +X-Seite – nur zur Orientierung"),
        ],
        kennwerte=kennwerte(bohrung, kh, bd, sh))


def selbsttest():
    """Prüft Maße und Anschlusspunkte gegen die Eingaben."""
    from kt_schnittstelle import pruefe_paarung

    t = baue(bohrung=86.0, kompressionshoehe=32.0, bolzen_d=22.0,
             schafthoehe=48.0)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Kolben ist kein Solid")
    b = shp.BoundBox
    if abs(max(b.XLength, b.ZLength) - 0.0) < 0:
        pass
    # Durchmesser = Bohrung minus Laufspiel.
    if abs(b.XLength - (86.0 - 0.12)) > 0.2:
        raise AssertionError("Kolbendurchmesser %.2f statt %.2f"
                             % (b.XLength, 86.0 - 0.12))
    # Hoehe = Kompressionshoehe + Schafthoehe, Ursprung in der Bolzenmitte.
    if abs(b.ZMax - 32.0) > 0.01 or abs(b.ZMin + 48.0) > 0.01:
        raise AssertionError("Kolben steht falsch: z %.2f..%.2f, erwartet "
                             "-48..32" % (b.ZMin, b.ZMax))
    # Der Bolzen muss wirklich durchgehen.
    stift = Part.makeCylinder(22.0 / 2.0 - 0.2, 200.0,
                              Vector(0, -100.0, 0), Vector(0, 1, 0))
    if shp.common(stift).Volume > 1.0:
        raise AssertionError("die Bolzenbohrung ist nicht frei")
    # Anschlusspunkte.
    for name in ("bolzen", "boden", "laufbahn"):
        t.punkt(name)
    if abs(t.punkt("boden").ort.z - 32.0) > 1e-9:
        raise AssertionError("Bodenpunkt sitzt nicht auf der "
                             "Kompressionshoehe")
    ok, text = pruefe_paarung(t.punkt("bolzen"),
                              Punkt("probe", (0, 0, 0), (0, -1, 0),
                                    "bohrung", 22.0))
    if not ok:
        raise AssertionError("Bolzenpunkt paart nicht: " + text)
    # Das kleine Pleuelauge muss zwischen die Naben passen.
    import kt_pleuel as P
    pleuel = P.baue(stichmass=150.0, bolzen_d=22.0, breite=22.0)
    import kt_schnittstelle as S
    gesetzt = S.andocke(pleuel, "kolbenbolzen", t.punkt("bolzen"))
    durch = shp.common(gesetzt.koerper[0][1]).Volume
    if durch > 50.0:
        raise AssertionError(
            "das kleine Pleuelauge steckt im Kolben (%.0f mm^3) — der "
            "Pleuelschlitz fehlt oder ist zu schmal" % durch)

    # Zu kleine Kompressionshoehe muss auffallen.
    try:
        baue(bohrung=86.0, kompressionshoehe=12.0, bolzen_d=22.0)
        raise AssertionError("zu kleine Kompressionshoehe blieb unbemerkt")
    except ValueError:
        pass
    # --- Feuersteg, Ringstege, Desachsierung -----------------------------
    # Die erste Ringnut muss GENAU einen Feuersteg unter der Bodenkante
    # liegen — das ist der Richtwert (4…10 % der Bohrung beim Ottomotor),
    # und er war frueher mit der Bodendicke verwechselt.
    fs, rst = 5.2, 3.9
    t2 = baue(bohrung=86.0, kompressionshoehe=32.0, feuersteg=fs,
              ringsteg=rst, ringnut_h=1.5, ringe=3)
    shp2 = t2.koerper[0][1]
    kh = 32.0
    # In der Nut fehlt Material: ein duenner Ring auf Hoehe der Nut trifft
    # weniger als einer auf Hoehe des Steges.
    def ring_bei(z):
        aussen = Part.makeCylinder(86.0 / 2.0, 0.4, Vector(0, 0, z))
        innen = Part.makeCylinder(86.0 / 2.0 - 1.0, 0.6,
                                  Vector(0, 0, z - 0.1))
        return shp2.common(aussen.cut(innen)).Volume
    voll = ring_bei(kh - fs / 2.0)              # mitten im Feuersteg
    leer = ring_bei(kh - fs - 0.75)             # mitten in der 1. Nut
    if not voll > leer * 3.0:
        raise AssertionError(
            "die erste Ringnut liegt nicht unter dem Feuersteg "
            "(Steg %.1f, Nut %.1f mm^3)" % (voll, leer))
    steg = ring_bei(kh - fs - 1.5 - rst / 2.0)  # mitten im 1. Ringsteg
    if not steg > leer * 3.0:
        raise AssertionError("der erste Ringsteg fehlt (%.1f gegen %.1f)"
                             % (steg, leer))

    # Desachsierung: der Bolzen sitzt versetzt, und der Anschlusspunkt sagt
    # es auch — sonst haengt das Pleuel woanders als die Bohrung sitzt.
    versatz = 0.9
    t3 = baue(bohrung=86.0, kompressionshoehe=32.0, desachsierung=versatz)
    if abs(t3.punkt("bolzen").ort.x - versatz) > 1e-9:
        raise AssertionError("der Anschlusspunkt folgt der Desachsierung "
                             "nicht (%.2f statt %.2f)"
                             % (t3.punkt("bolzen").ort.x, versatz))
    probe = Part.makeCylinder(22.0 / 2.0, 200.0,
                              Vector(versatz, -100.0, 0), Vector(0, 1, 0))
    if t3.koerper[0][1].common(probe).Volume > 1.0:
        raise AssertionError("die Bolzenbohrung sitzt nicht auf dem Versatz")

    return ("Kolben-Selbsttest bestanden (d %.2f mm, %.0f mm hoch, %.0f mm^3)"
            % (b.XLength, b.ZLength, shp.Volume))
