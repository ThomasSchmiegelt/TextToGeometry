# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Einscheiben-Trockenkupplung — Schwungrad bis Ausrücklager.

    teile = baue(hubraum_cm3=5995)

Die Kupplung sitzt zwischen Kurbelwelle und Getriebe und hat zwei Aufgaben:
das Drehmoment **trennen** (zum Schalten und Anfahren) und es **übertragen**.
Aus der zweiten folgt ihre Größe.

Aufbau, vom Motor her:

    Schwungrad ── Kupplungsscheibe ── Druckplatte ── Membranfeder ── Deckel
       │              │                                                │
    Kurbelwellen-  Nabe auf der                            am Schwungrad
    flansch        Getriebeeingangswelle                   verschraubt

Das **Schwungrad** sitzt am Kurbelwellenflansch und trägt den Zahnkranz für
den Anlasser. Die **Kupplungsscheibe** läuft mit ihrer Nabe auf der
Verzahnung der Getriebeeingangswelle — axial verschiebbar, damit sie gelöst
werden kann — und trägt beidseits Reibbeläge. Die **Druckplatte** presst sie
gegen das Schwungrad; die Kraft kommt von der **Membranfeder** (geschlitzte
Tellerfeder), und das **Ausrücklager** drückt deren Zungen nach innen, um zu
trennen.

Warum eine Membranfeder und keine Schraubenfedern: sie hält ihre Kraft über
einen großen Weg nahezu konstant, also bleibt die Anpresskraft auch dann
gleich, wenn die Beläge verschlissen sind.

## Auslegung

Das übertragbare Moment einer Reibkupplung:

    M = z · μ · F_N · r_m

mit ``z`` Zahl der Reibflächen (bei einer Scheibe **zwei**, denn sie reibt
auf beiden Seiten), ``μ`` Reibungszahl, ``F_N`` Anpresskraft und ``r_m``
mittlerem Reibradius:

    r_m = (D_a + D_i) / 4

Da ``F_N`` mit der Fläche geht (∝ D²) und ``r_m`` mit D, geht das Moment mit
**D³**. Der Belagdurchmesser wächst deshalb mit der dritten Wurzel des
Drehmoments — dieselbe Abhängigkeit wie beim Getriebewellendurchmesser:

    D_a = 215 mm · (V_H / 2000 cm³)^(1/3)

215 mm bei zwei Litern ist eine gängige Größe. Ab etwa 280 mm geht der
Fahrzeugbau zur **Zweischeibenkupplung** über, weil eine einzelne Scheibe
dann zu schwer wird und zu träge hochdreht; der Generator sagt das als
Hinweis, baut aber weiter eine Scheibe.

Anschlusspunkte
    ``kurbelwelle``    Schwungradrückseite, Achse -X, Art *flaeche*
    ``getriebewelle``  Nabenbohrung der Scheibe, Achse +X, Art *bohrung*
    ``ausruecker``     Anlagefläche des Ausrücklagers, Achse +X, *flaeche*
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

#: Bezugsgrößen: ein Zweilitermotor bekommt 215 mm Belagdurchmesser.
BEZUG_HUBRAUM = 2000.0
BEZUG_BELAG_D = 215.0

#: Ab hier baut der Fahrzeugbau zwei Scheiben statt einer.
EINSCHEIBEN_GRENZE = 280.0

#: Verhältnis Innen- zu Außendurchmesser des Reibbelags. Unter 0,55 bringt
#: der innere Teil kaum noch Moment (kleiner Radius), über 0,75 fehlt Fläche.
INNEN_ANTEIL = 0.65

#: Reibungszahl eines trockenen organischen Belags.
REIBUNGSZAHL = 0.30


class KupplungFehler(Exception):
    pass


def auslegen(hubraum_cm3=2000.0, belag_d=0.0, moment_nm=0.0,
             getriebewelle_d=0.0, flansch_d=0.0, scheiben=0):
    """Die Maße der Kupplung, passend zum Motor.

    hubraum_cm3       Hubraum; daraus folgt der Belagdurchmesser
    belag_d           0 = aus dem Hubraum
    moment_nm         Motormoment [Nm]; nur für die Kennwerte, nicht für die
                      Geometrie — ohne Drehzahl und Mitteldruck wäre es
                      geraten
    getriebewelle_d   Durchmesser der Getriebeeingangswelle [mm]
    flansch_d         Schwungradflansch der Kurbelwelle [mm]
    scheiben          1 oder 2; 0 = selbst entscheiden

    Die **Scheibenzahl** folgt aus dem Durchmesser, und der aus dem Moment.
    Weil ``M = z · μ · F · r_m`` **linear** in der Zahl der Reibflächen ist
    und mit ``D³`` geht, macht die zweite Scheibe den Belag um den Faktor
    ``2^(1/3) = 0,794`` kleiner. Genau das ist der Grund, warum große Motoren
    zwei Scheiben bekommen und nicht einen Riesenbelag: eine 310-mm-Scheibe
    wiegt zu viel und dreht zu träge hoch, zwei 246er tun dasselbe.
    """
    v = max(1.0, float(hubraum_cm3))
    z_scheiben = int(scheiben)
    if z_scheiben not in (1, 2):
        roh = BEZUG_BELAG_D * (v / BEZUG_HUBRAUM) ** (1.0 / 3.0)
        z_scheiben = 2 if roh > EINSCHEIBEN_GRENZE else 1
    # Vier Reibflaechen statt zwei: derselbe Zusammenhang, halbierte Last
    # je Flaeche.
    da = float(belag_d) or round(
        BEZUG_BELAG_D * (v / BEZUG_HUBRAUM / z_scheiben) ** (1.0 / 3.0), 1)
    di = round(da * INNEN_ANTEIL, 1)
    rm = round((da + di) / 4.0, 2)
    welle = float(getriebewelle_d) or round(0.13 * da, 1)
    a = {
        "hubraum_cm3": round(v, 1),
        "belag_d": da,
        "belag_innen_d": di,
        "reibradius_m": rm,
        "scheiben": z_scheiben,
        "reibflaechen": 2 * z_scheiben,
        "reibungszahl": REIBUNGSZAHL,
        "belag_t": round(max(2.5, 0.016 * da), 2),
        "scheibe_t": round(max(1.5, 0.009 * da), 2),
        "schwungrad_d": round(da + 0.16 * da, 1),
        "schwungrad_t": round(max(18.0, 0.11 * da), 1),
        "zahnkranz_b": round(max(8.0, 0.045 * da), 1),
        "druckplatte_t": round(max(10.0, 0.055 * da), 1),
        "feder_t": round(max(1.8, 0.011 * da), 2),
        "zungen": 18,
        "daempferfedern": 6,
        "getriebewelle_d": welle,
        "flansch_d": float(flansch_d) or round(da * 0.5, 1),
        "zweischeibig_ab": EINSCHEIBEN_GRENZE,
    }
    # Flaeche und damit die noetige Anpresskraft fuer ein gegebenes Moment.
    a["reibflaeche_cm2"] = round(
        math.pi * ((da / 2.0) ** 2 - (di / 2.0) ** 2) / 100.0, 1)
    if float(moment_nm) > 0.0:
        a["moment_nm"] = float(moment_nm)
        a["anpresskraft_n"] = round(
            float(moment_nm) * 1000.0
            / (a["reibflaechen"] * REIBUNGSZAHL * rm), 0)
    a["hinweis"] = ("" if da <= EINSCHEIBEN_GRENZE else
                    "Belagdurchmesser %.0f mm auch mit %d Scheibe(n) noch "
                    "ueber %.0f mm." % (da, z_scheiben, EINSCHEIBEN_GRENZE))
    a["bauart"] = "Einscheiben" if z_scheiben == 1 else "Zweischeiben"
    return a


def moment(anpresskraft_n, reibradius_m, reibflaechen=2,
           reibungszahl=REIBUNGSZAHL):
    """Übertragbares Moment einer Reibkupplung [Nm]: M = z · μ · F · r_m."""
    return (int(reibflaechen) * float(reibungszahl) * float(anpresskraft_n)
            * float(reibradius_m) / 1000.0)


def _ring(d_aussen, d_innen, dicke, x):
    """Ein Ring, Achse X, von x bis x + dicke."""
    k = Part.makeCylinder(float(d_aussen) / 2.0, float(dicke),
                          Vector(x, 0, 0), Vector(1, 0, 0))
    if float(d_innen) > 0.0:
        k = k.cut(Part.makeCylinder(float(d_innen) / 2.0,
                                    float(dicke) + 2.0,
                                    Vector(x - 1.0, 0, 0), Vector(1, 0, 0)))
    return k


def _membranfeder(d_aussen, d_innen, dicke, zungen, hoehe, x):
    """Geschlitzte Tellerfeder: ein flacher Kegel mit Schlitzen nach innen.

    Die Schlitze machen aus dem Tellerrand die Ausrückzungen. Ohne sie wäre
    es eine gewöhnliche Tellerfeder, die sich nicht betätigen ließe.
    """
    ra, ri = float(d_aussen) / 2.0, float(d_innen) / 2.0
    kegel = Part.makeCone(ra, ri, float(hoehe), Vector(x, 0, 0),
                          Vector(1, 0, 0))
    innen = Part.makeCone(ra - float(dicke), ri - float(dicke), float(hoehe),
                          Vector(x + float(dicke), 0, 0), Vector(1, 0, 0))
    feder = kegel.cut(innen)
    # Schlitze: schmale Quader radial von innen bis knapp unter den Rand.
    n = max(6, int(zungen))
    schlitz_b = max(1.5, ri * 2.0 * math.pi / n * 0.35)
    for k in range(n):
        w = 2.0 * math.pi * k / n
        stab = Part.makeBox(float(hoehe) + 4.0, schlitz_b, ra * 0.75,
                            Vector(x - 2.0, -schlitz_b / 2.0, 0.0))
        dreh = FreeCAD.Placement(Vector(0, 0, 0),
                                 FreeCAD.Rotation(Vector(1, 0, 0),
                                                  math.degrees(w)))
        stab.Placement = dreh.multiply(stab.Placement)
        feder = feder.cut(stab)
    return feder


def baue(hubraum_cm3=2000.0, belag_d=0.0, getriebewelle_d=0.0,
         flansch_d=0.0, scheiben=0, doc=None):
    """Die Kupplung als Liste von (Bezeichnung, Shape).

    Gebaut wird entlang **+X**, x = 0 ist die **Schwungradrückseite** — also
    die Fläche, die am Kurbelwellenflansch anliegt.

    Bei zwei Scheiben liegt zwischen ihnen die **Zwischenplatte**; sie dreht
    mit dem Schwungrad und gibt der zweiten Scheibe ihre Gegenfläche.
    """
    a = auslegen(hubraum_cm3, belag_d, 0.0, getriebewelle_d, flansch_d,
                 scheiben)
    teile = []
    x = 0.0

    # --- Schwungrad mit Anlasserzahnkranz --------------------------------
    sr_t = a["schwungrad_t"]
    schwung = _ring(a["schwungrad_d"], 0.0, sr_t, x)
    # Flanschbohrungen zur Kurbelwelle.
    for k in range(8):
        w = 2.0 * math.pi * k / 8.0
        r = a["flansch_d"] / 2.0 * 0.8
        schwung = schwung.cut(Part.makeCylinder(
            5.0, sr_t + 2.0, Vector(x - 1.0, r * math.cos(w), r * math.sin(w)),
            Vector(1, 0, 0)))
    # Mittige Aussparung, ABGESETZT: aussen so weit, dass die Nabe der
    # Kupplungsscheibe hineinragen kann, innen nur noch der Sitz fuer das
    # Pilotlager der Getriebeeingangswelle. Ohne die weite Stufe stak die
    # Nabe zu 19,9 % im Schwungrad — real ist dort eine Vertiefung, denn
    # die Scheibe muss ja bis an die Reibflaeche heran.
    nabe_frei = a["getriebewelle_d"] + 16.0 + 2.0
    schwung = schwung.cut(Part.makeCylinder(
        nabe_frei / 2.0, sr_t * 0.45,
        Vector(x + sr_t * 0.55, 0, 0), Vector(1, 0, 0)))
    schwung = schwung.cut(Part.makeCylinder(
        a["getriebewelle_d"] / 2.0 + 1.0, sr_t * 0.7,
        Vector(x + sr_t * 0.3, 0, 0), Vector(1, 0, 0)))
    teile.append(("Schwungrad", schwung))
    teile.append(("Anlasserzahnkranz",
                  _ring(a["schwungrad_d"] + 14.0, a["schwungrad_d"],
                        a["zahnkranz_b"], x + sr_t - a["zahnkranz_b"])))
    x += sr_t

    # --- Kupplungsscheibe(n) ---------------------------------------------
    bt, st = a["belag_t"], a["scheibe_t"]
    nabe_d = a["getriebewelle_d"] + 16.0
    scheibe_b = bt * 2.0 + st
    zwischen_t = a["druckplatte_t"] * 0.8
    for nr in range(1, a["scheiben"] + 1):
        zusatz = "" if a["scheiben"] == 1 else " %d" % nr
        teile.append(("Reibbelag%s motorseitig" % zusatz,
                      _ring(a["belag_d"], a["belag_innen_d"], bt, x)))
        traeger = _ring(a["belag_d"] - 4.0, nabe_d, st, x + bt)
        teile.append(("Reibbelag%s getriebeseitig" % zusatz,
                      _ring(a["belag_d"], a["belag_innen_d"], bt,
                            x + bt + st)))
        # Nabe mit der Verzahnung fuer die Getriebeeingangswelle: sie muss
        # AXIAL VERSCHIEBBAR sein, sonst liesse sich die Kupplung nicht
        # loesen.
        teile.append(("Scheibennabe%s" % zusatz,
                      _ring(nabe_d, a["getriebewelle_d"],
                            scheibe_b + 8.0, x - 4.0)))
        # Torsionsdaempfer: Federn zwischen Nabe und Belagtraeger. Sie
        # nehmen die Drehschwingungen des Motors auf — beim V12 die
        # Zuendstoesse.
        r_d = (nabe_d + a["belag_innen_d"]) / 4.0 + 6.0
        for k in range(int(a["daempferfedern"])):
            w = 2.0 * math.pi * k / a["daempferfedern"]
            mitte = Vector(x + bt - st * 0.3, r_d * math.cos(w),
                           r_d * math.sin(w))
            achse = Vector(0, -math.sin(w), math.cos(w))
            teile.append((
                "Daempferfeder%s %d" % (zusatz, k + 1),
                Part.makeCylinder(st * 1.6, st * 4.0, mitte, achse)))
            # FENSTER im Belagtraeger: dort liegt die Feder, und dort darf
            # kein Blech sein. Ohne die Fenster steckte die Feder zu 33 %
            # im Traeger — real sind es ausgestanzte Fenster in Traeger und
            # Nabenflansch, in denen die Feder sitzt und sich staucht.
            fenster = Part.makeCylinder(st * 1.6 + 0.3, st * 4.0 + 1.0,
                                        mitte.sub(achse.multiply(0.5)),
                                        Vector(0, -math.sin(w), math.cos(w)))
            traeger = traeger.cut(fenster)
        teile.append(("Belagtraeger%s" % zusatz, traeger))
        x += scheibe_b
        # Zwischen zwei Scheiben die Zwischenplatte: sie dreht mit dem
        # Schwungrad und ist die Gegenflaeche der zweiten Scheibe.
        if nr < a["scheiben"]:
            teile.append(("Zwischenplatte",
                          _ring(a["belag_d"] + 6.0,
                                a["belag_innen_d"] - 6.0, zwischen_t, x)))
            x += zwischen_t

    # --- Druckplatte, Membranfeder, Deckel -------------------------------
    dp_t = a["druckplatte_t"]
    teile.append(("Druckplatte",
                  _ring(a["belag_d"] + 6.0, a["belag_innen_d"] - 6.0,
                        dp_t, x)))
    x += dp_t
    feder_h = dp_t * 1.2
    teile.append(("Membranfeder",
                  _membranfeder(a["belag_d"] + 4.0,
                                a["getriebewelle_d"] + 26.0,
                                a["feder_t"], a["zungen"], feder_h, x)))
    # Der Deckel greift ueber die Feder und ist am Schwungrad verschraubt.
    deckel_x = x + feder_h
    deckel = _ring(a["schwungrad_d"], a["belag_d"] - 10.0, 6.0, deckel_x)
    mantel = _ring(a["schwungrad_d"], a["schwungrad_d"] - 12.0,
                   deckel_x - sr_t, sr_t)
    teile.append(("Kupplungsdeckel", deckel.fuse(mantel).removeSplitter()))

    # --- Ausruecklager ---------------------------------------------------
    al_d = a["getriebewelle_d"] + 34.0
    teile.append(("Ausruecklager",
                  _ring(al_d, a["getriebewelle_d"] + 4.0, 16.0,
                        deckel_x + 8.0)))

    return teile, a


def pruefe(teile, a):
    """Misst die Kupplung nach; liefert [(ok, Text), …]."""
    befunde = []

    def sag(ok, text):
        befunde.append((bool(ok), text))

    sag(all(s.Solids for _n, s in teile),
        "alle %d Koerper sind Solids" % len(teile))
    namen = [n for n, _s in teile]
    for pflicht in ("Schwungrad", "Druckplatte", "Membranfeder",
                    "Kupplungsdeckel", "Ausruecklager"):
        sag(pflicht in namen, "%s ist da" % pflicht)
    for wort, soll in (("Belagtraeger", a["scheiben"]),
                       ("Scheibennabe", a["scheiben"]),
                       ("Daempferfeder",
                        a["daempferfedern"] * a["scheiben"])):
        ist = sum(1 for n in namen if n.startswith(wort))
        sag(ist == soll, "%d x %s (erwartet %d)" % (ist, wort, soll))
    sag(("Zwischenplatte" in namen) == (a["scheiben"] > 1),
        "Zwischenplatte nur bei zwei Scheiben (%d Scheiben)" % a["scheiben"])

    # Jede Scheibe reibt auf BEIDEN Seiten — das ist der Grund fuer z = 2
    # je Scheibe, und genau darum halbiert die zweite Scheibe die Last.
    belaege = [s for n, s in teile if n.startswith("Reibbelag")]
    sag(len(belaege) == a["reibflaechen"],
        "%d Reibflaechen bei %d Scheibe(n)"
        % (len(belaege), a["scheiben"]))
    if belaege:
        sag(max(s.Volume for s in belaege)
            - min(s.Volume for s in belaege) < 1.0,
            "alle Belaege sind gleich gross")

    # Der mittlere Reibradius muss zwischen innen und aussen liegen.
    sag(a["belag_innen_d"] / 2.0 < a["reibradius_m"] < a["belag_d"] / 2.0,
        "mittlerer Reibradius %.1f mm liegt zwischen %.1f und %.1f"
        % (a["reibradius_m"], a["belag_innen_d"] / 2.0, a["belag_d"] / 2.0))

    # Das Schwungrad muss groesser sein als der Belag, sonst haengt der
    # Belag ueber.
    sag(a["schwungrad_d"] > a["belag_d"],
        "das Schwungrad (%.0f) traegt den Belag (%.0f)"
        % (a["schwungrad_d"], a["belag_d"]))

    # Nichts darf sich durchdringen — ausser dem, was aufeinander PRESST.
    # Was aufeinander PRESST, darf sich beruehren. Die Daempferfedern
    # gehoeren NICHT dazu — sie sitzen in Fenstern, und ob die Fenster da
    # sind, ist genau die Frage.
    erlaubt = ("Reibbelag", "Druckplatte", "Schwungrad", "Scheibennabe",
               "Zwischenplatte")
    schlimm, wo = 0.0, ""
    for i in range(len(teile)):
        for j in range(i + 1, len(teile)):
            n1, s1 = teile[i]
            n2, s2 = teile[j]
            if not s1.BoundBox.intersect(s2.BoundBox):
                continue
            if any(n1.startswith(e) for e in erlaubt) and \
                    any(n2.startswith(e) for e in erlaubt):
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
    """Prüft Auslegung, Moment und Geometrie."""
    # Das Moment geht mit D^3: doppelter Hubraum, 2^(1/3) mal der Belag.
    a1 = auslegen(2000.0)
    a2 = auslegen(16000.0, scheiben=1)
    if abs(a1["belag_d"] - BEZUG_BELAG_D) > 0.1:
        raise AssertionError("Bezugsfall stimmt nicht: %.1f statt %.1f"
                             % (a1["belag_d"], BEZUG_BELAG_D))
    if abs(a2["belag_d"] - 2.0 * a1["belag_d"]) > 1.0:
        raise AssertionError("achtfacher Hubraum muss den Belag verdoppeln "
                             "(%.1f statt %.1f)"
                             % (a2["belag_d"], 2.0 * a1["belag_d"]))
    if a1["scheiben"] != 1:
        raise AssertionError("ein Zweiliter braucht nur eine Scheibe")

    # Die zweite Scheibe macht den Belag um 2^(1/3) kleiner — das ist der
    # Grund, warum grosse Motoren zwei bekommen und nicht einen Riesenbelag.
    eine = auslegen(5995.0, scheiben=1)
    zwei = auslegen(5995.0, scheiben=2)
    if zwei["scheiben"] != 2 or zwei["reibflaechen"] != 4:
        raise AssertionError("die Zweischeibenkupplung hat vier Reibflaechen")
    erwartet = eine["belag_d"] * 0.5 ** (1.0 / 3.0)
    if abs(zwei["belag_d"] - erwartet) > 1.0:
        raise AssertionError("zwei Scheiben: Belag %.1f statt %.1f mm"
                             % (zwei["belag_d"], erwartet))
    if auslegen(5995.0)["scheiben"] != 2:
        raise AssertionError("ueber der Grenze muss von selbst auf zwei "
                             "Scheiben gegangen werden")
    # Und beide uebertragen dasselbe Moment bei gleicher Anpresskraft.
    m1 = moment(10000.0, eine["reibradius_m"], eine["reibflaechen"])
    m2 = moment(10000.0, zwei["reibradius_m"], zwei["reibflaechen"])
    if not m2 > m1:
        raise AssertionError("vier Reibflaechen muessen mehr uebertragen "
                             "als zwei (%.0f gegen %.0f Nm)" % (m2, m1))

    # M = z * mue * F * r_m, und die Umkehrung muss dasselbe geben.
    a = auslegen(5995.0, moment_nm=600.0)
    zurueck = moment(a["anpresskraft_n"], a["reibradius_m"],
                     a["reibflaechen"], a["reibungszahl"])
    if abs(zurueck - 600.0) > 1.0:
        raise AssertionError("Moment und Anpresskraft passen nicht "
                             "zusammen: %.1f statt 600 Nm" % zurueck)

    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("KupplungTest")
    teile, a = baue(hubraum_cm3=5995.0, getriebewelle_d=28.8,
                    flansch_d=110.0, doc=doc)
    schlecht = [t for ok, t in pruefe(teile, a) if not ok]
    if schlecht:
        raise AssertionError("; ".join(schlecht))

    b = teile[0][1].BoundBox
    for _n, s in teile[1:]:
        b.add(s.BoundBox)
    return ("Kupplung-Selbsttest bestanden (%s, Belag %.0f/%.0f mm, "
            "%d Reibflaechen, r_m %.1f, %d Teile, %.0f lang x %.0f breit)"
            % (a["bauart"], a["belag_d"], a["belag_innen_d"],
               a["reibflaechen"], a["reibradius_m"], len(teile),
               b.XLength, b.YLength))
