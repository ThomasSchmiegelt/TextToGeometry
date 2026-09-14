# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Kurbeltriebsgenerator — setzt die Bauteile über ihre Andockpunkte zusammen.

    teile = baue(bauform="V8", bohrung=86.0, hub=86.0)

Hier wird nichts gerechnet, was ein Bauteil schon weiß. Der Kolben kennt
seine Kompressionshöhe, das Pleuel sein Stichmaß, die Kurbelwelle ihre
Zapfenwinkel — dieses Skript fügt sie zusammen und prüft, dass es passt.

Der Aufbau je Zylinder:

    Kurbelwelle.hubzapfen_k  ← Pleuel.hubzapfen
    Pleuel.kolbenbolzen      → Kolben.bolzen
    Ventil.schaft_ende       ← Stößel.ventil
    Nockenwelle.nocken_i     über dem Stößelboden

Die Blockhöhe folgt aus dem Kurbeltrieb und wird nicht geraten:

    Blockhöhe = Kurbelradius + Stichmaß + Kompressionshöhe

Das ist die Strecke von der Kurbelwellenmitte bis zum Kolbenboden im oberen
Totpunkt. Wer sie unabhängig eingibt, bekommt entweder einen Kolben, der oben
heraussteht, oder einen, der nie hinkommt.

Nur die Kurbelwelle ist ein einzelnes Bauteil; alles andere entsteht **einmal**
und wird kopiert. Eine Ventilfeder zu bauen dauert Sekunden, und ein V12 mit
vier Ventilen bräuchte achtundvierzig davon.
"""

import math

import FreeCAD
from FreeCAD import Vector

import kt_bauformen as B
import kt_kolben
import kt_kurbelwelle
import kt_nockenwelle
import kt_pleuel
import kt_schnittstelle as S
import kt_steuertrieb
import kt_stoessel
import kt_ventil
import kt_ventilfeder


class MotorFehler(Exception):
    pass


def blockhoehe(hub, stichmass, kompressionshoehe):
    """Kurbelwellenmitte bis Kolbenboden im oberen Totpunkt [mm]."""
    return float(hub) / 2.0 + float(stichmass) + float(kompressionshoehe)


def kennwerte(bauform="R4", bohrung=86.0, hub=86.0, stichmass=0.0,
              kompressionshoehe=32.0, zylinderabstand=0.0,
              ventile_je_zylinder=4, v8_kreuzebene=True,
              pleuel_breite=22.0, **_rest):
    """Die Auslegung auf einen Blick, ohne Geometrie."""
    l = float(stichmass) or kt_pleuel.stichmass_aus_hub(hub)
    za = float(zylinderabstand) or round(float(bohrung) * 1.18, 1)
    k = B.kennwerte(bauform, bohrung, hub, v8_kreuzebene)
    k.update({
        "bohrung": float(bohrung),
        "hub": float(hub),
        "stichmass": l,
        "lambda": round((float(hub) / 2.0) / l, 4),
        "kompressionshoehe": float(kompressionshoehe),
        "blockhoehe": round(blockhoehe(hub, l, kompressionshoehe), 2),
        "zylinderabstand": za,
        "ventile_je_zylinder": int(ventile_je_zylinder),
        "ventile_gesamt": int(ventile_je_zylinder) * k["zylinder"],
        # Bankversatz: beim V-Motor sitzen die beiden Pleuel NEBENEINANDER
        # auf demselben Hubzapfen, die Zylinderbaenke stehen deshalb um eine
        # Pleuelbreite gegeneinander versetzt. Das ist kein Schoenheitsfehler,
        # sondern folgt zwingend aus dem geteilten Zapfen.
        "bankversatz": _bankversatz(bauform, pleuel_breite, v8_kreuzebene),
        "nockenwellen": 2 if B.ist_v(bauform) else 1,
    })
    if B.ist_v(bauform):
        k["nockenwellen"] = 4 if int(ventile_je_zylinder) >= 4 else 2
    else:
        k["nockenwellen"] = 2 if int(ventile_je_zylinder) >= 4 else 1
    return k


def _nockenhub(winkel_grad, hub, grundkreis_r=16.0, flanke=60.0,
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


def _bankversatz(bauform, pleuel_breite, v8_kreuzebene=True):
    """Axialer Versatz der zweiten Zylinderbank [mm].

    Beim V-Motor sitzen die beiden Pleuel nebeneinander auf demselben
    Hubzapfen — die Bänke stehen deshalb zwangsläufig gegeneinander versetzt.
    Wie weit, hängt vom Zapfen ab:

    * ungeteilter Zapfen: um eine Pleuelbreite (V8, V10, V12)
    * geteilter Zapfen: um eine halbe Zapfenbreite, denn die beiden Hälften
      liegen selbst schon hintereinander (V4, V6) — gemessen 24 statt 22 mm
    """
    if not B.ist_v(bauform):
        return 0.0
    b = float(pleuel_breite)
    if B.hubzapfenversatz(bauform, v8_kreuzebene):
        return (2.0 * b + 4.0) / 2.0
    return b


def _kolbenweg(kurbelwinkel_grad, kurbelradius, stichmass):
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


def _pleuelrichtung(hubzapfen, achse, stichmass):
    """Richtung vom Hubzapfen zum Kolbenbolzen.

    Der Kolbenbolzen liegt auf der Zylinderachse (einer Geraden durch die
    Kurbelwellenmitte in Richtung ``achse``), im Abstand ``stichmass`` vom
    Hubzapfen. Das ist die Schubkurbel: aus

        |t·achse − P| = l

    folgt ``t = achse·P + sqrt((achse·P)² − |P|² + l²)``. Die positive
    Wurzel ist der Kolben oberhalb der Kurbel.
    """
    p = Vector(hubzapfen)
    a = Vector(achse)
    a.normalize()
    # Nur die Ebene senkrecht zur Kurbelwelle zaehlt; x bleibt, wie es ist.
    p_eben = Vector(0.0, p.y, p.z)
    ap = a.dot(p_eben)
    wurzel = ap * ap - p_eben.Length ** 2 + float(stichmass) ** 2
    if wurzel < 0.0:
        raise MotorFehler(
            "Das Stichmass %.1f mm reicht nicht bis zur Zylinderachse — der "
            "Kurbelradius ist zu gross." % float(stichmass))
    t = ap + math.sqrt(wurzel)
    bolzen = Vector(p.x, a.y * t, a.z * t)
    richtung = bolzen.sub(p)
    if richtung.Length < 1e-9:
        return Vector(a)
    richtung.normalize()
    return richtung


def _zylinderachse(bankwinkel_grad):
    """Richtung der Zylinderachse: aus der Senkrechten um den Bankwinkel."""
    w = math.radians(float(bankwinkel_grad))
    return Vector(0.0, math.sin(w), math.cos(w))


def baue(bauform="R4", bohrung=86.0, hub=86.0, stichmass=0.0,
         kompressionshoehe=32.0, zylinderabstand=0.0, bolzen_d=22.0,
         hubzapfen_d=48.0, hauptlager_d=54.0, ventile_je_zylinder=4,
         ventilhub=10.0, steuertrieb="kette", zaehne_kurbel=20,
         spreizung=110.0, ventilwinkel=12.0, pleuel_breite=22.0,
         v8_kreuzebene=True, mit_ventiltrieb=True, mit_getriebe=False,
         getriebe_gaenge=5, doc=None):
    """Ein vollständiger Kurbeltrieb als Liste von (Bezeichnung, Shape).

    bauform             R2 … V12
    bohrung, hub        [mm]
    stichmass           0 = aus dem Hub vorschlagen (1,75·Hub)
    kompressionshoehe   Kolbenbolzenmitte bis Kolbenboden [mm]
    zylinderabstand     0 = 1,18 · Bohrung
    ventile_je_zylinder 2 oder 4
    ventilhub           Nockenerhebung [mm]
    steuertrieb         "kette" oder "zahnrad"
    spreizung           Lage des Nockenscheitels nach OT [Grad Kurbelwinkel],
                        üblich 100…115
    ventilwinkel        Neigung der Ventile gegen die Zylinderachse [Grad],
                        Einlass und Auslass gegenläufig. Das ist das Dach des
                        Brennraums — und der Grund, warum die beiden
                        Nockenwellen nebeneinander Platz haben statt
                        ineinanderzustehen.
    mit_ventiltrieb     False baut nur Kurbelwelle, Pleuel und Kolben
    mit_getriebe        True flanscht das Getriebe aus getriebe_fcgear an
                        den Schwungradflansch — beide laufen in der
                        Normallage entlang X auf derselben Achse
    """
    k = kennwerte(bauform, bohrung, hub, stichmass, kompressionshoehe,
                  zylinderabstand, ventile_je_zylinder, v8_kreuzebene,
                  pleuel_breite)
    l = k["stichmass"]
    za = k["zylinderabstand"]
    z, bank = B.daten(bauform)
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Motor")

    teile = []
    proben = []          # (Punkt A, Punkt B) für die Paarungsprüfung

    # --- Kurbelwelle ------------------------------------------------------
    # Beim V-Motor teilen sich zwei Pleuel einen Hubzapfen — er muss also
    # doppelt so breit sein, und die beiden sitzen NEBENEINANDER. Uebereinander
    # gesetzt durchdrangen sie sich zu 53,6 %.
    pleuel_b = float(pleuel_breite)
    zapfen_b = (2.0 * pleuel_b + 4.0) if B.ist_v(bauform) else 26.0
    k["bankversatz"] = _bankversatz(bauform, pleuel_b, v8_kreuzebene)
    kw = kt_kurbelwelle.baue(bauform=bauform, hub=hub, zylinderabstand=za,
                             hauptlager_d=hauptlager_d,
                             hubzapfen_d=hubzapfen_d,
                             hubzapfen_b=zapfen_b,
                             v8_kreuzebene=v8_kreuzebene)
    teile.extend(kw.koerper)

    # --- Kolben und Pleuel, einmal gebaut und dann kopiert ---------------
    # Ventiltaschen: dieselben Versaetze wie die Ventile, aber im
    # Kolbenkoordinatensystem. Der Kolben wird ueber seinen Bolzen
    # angedockt, und der liegt spaeter auf der Kurbelwellenachse — aus
    # kolbenlokal +Y wird also die x-Richtung des Motors.
    einlass_probe = kt_ventil.vorschlag(bohrung, ventile_je_zylinder, True)
    auslass_probe = kt_ventil.vorschlag(bohrung, ventile_je_zylinder, False)
    je_seite_probe = max(1, int(ventile_je_zylinder) // 2)
    # Die Taschen werden SYMMETRISCH gesetzt, an allen vier Stellen. Welche
    # Seite beim V-Motor spaeter Ein- und welche Auslass ist, haengt von der
    # Bank ab — mit gerichteten Taschen landeten sie bei einer Bank
    # spiegelverkehrt, und das Ventil schlug in den Kolbenboden.
    taschen = []
    if mit_ventiltrieb:
        # Die Taschentiefe wird nicht geraten, sondern aus dem groessten Hub
        # bestimmt, den irgendein Ventil dieses Motors gerade hat. Mit einer
        # festen Tiefe von 4 mm blieben bei V10 und V12 noch 2,5 bis 9,3 %
        # Durchdringung — genau der Betrag, um den ein Ventil tiefer stand.
        lagen_probe = B.zylinderlagen(bauform, za, v8_kreuzebene)
        versatz_probe = B.hubzapfenversatz(bauform, v8_kreuzebene)
        kw_probe = B.zapfenwinkel(bauform, v8_kreuzebene)
        # Nicht der groesste Hub bestimmt die Tasche, sondern der
        # Ueberstand des Ventils UEBER dem Kolbenboden. Der Kolben ist dann
        # meist schon ein Stueck heruntergelaufen. Mit dem vollen Hub
        # gerechnet wurden die Taschen 13 mm tief statt der ueblichen 2...4.
        noetig = 0.0
        for _s, _x, bw, zapfen in lagen_probe:
            kwz = kw_probe[zapfen]
            if _s == 1 and versatz_probe:
                kwz += versatz_probe
            weg = _kolbenweg(kwz, float(hub) / 2.0, l)
            for art in ("einlass", "auslass"):
                vk = float(spreizung) * (1.0 if art == "einlass" else -1.0)
                w = ((kwz + vk) / 2.0
                     + (0.0 if art == "einlass" else 180.0)) % 360.0
                lift = _nockenhub(w, ventilhub, 16.0, stoessel_winkel=180.0)
                noetig = max(noetig, lift - weg)
        tiefe = round(max(1.0, noetig) + 1.5, 2)
        d_tasche = max(einlass_probe, auslass_probe) + 8.0
        for vz_quer in (-1.0, 1.0):
            for vz_laengs in (-1.0, 1.0):
                taschen.append((vz_quer * einlass_probe * 0.6,
                                vz_laengs * einlass_probe * 0.55,
                                d_tasche, tiefe))

    kolben_muster = kt_kolben.baue(bohrung=bohrung,
                                   kompressionshoehe=kompressionshoehe,
                                   bolzen_d=bolzen_d,
                                   ventiltaschen=taschen)
    pleuel_muster = kt_pleuel.baue(stichmass=l, hubzapfen_d=hubzapfen_d,
                                   bolzen_d=bolzen_d, breite=pleuel_b)

    lagen = B.zylinderlagen(bauform, za, v8_kreuzebene)
    versatz = B.hubzapfenversatz(bauform, v8_kreuzebene)
    zylinder_x = {}

    for nr, (seite, _x, bankwinkel, zapfen) in enumerate(lagen, 1):
        # Welchen Hubzapfen? Bei geteiltem Zapfen die Haelfte der Bank.
        name = "hubzapfen_%d" % (zapfen + 1)
        if versatz and B.ist_v(bauform):
            name = "hubzapfen_%d%s" % (zapfen + 1, "a" if seite == 0 else "b")
        ziel = kw.punkt(name)
        if B.ist_v(bauform) and not versatz:
            # Ungeteilter Zapfen: die beiden Baenke nebeneinander setzen.
            ziel = S.Punkt(ziel.name,
                           Vector(ziel.ort).add(Vector(
                               (pleuel_b / 2.0) * (-1.0 if seite == 0
                                                   else 1.0), 0, 0)),
                           ziel.achse, ziel.art, ziel.mass, ziel.hinweis)

        # Der KOLBEN laeuft auf der Zylinderachse, nicht das Pleuel. Das
        # Pleuel steht schraeg — genau das ist der Schubkurbeltrieb. Vorher
        # war das Pleuel parallel zur Zylinderachse gerichtet, und die
        # Kolben einer Bank lagen dadurch nicht auf einer Linie: bei Bank A
        # eines V8 auf (-100,8|143,8), (-143,8|100,8), (-57,8|100,8) statt
        # auf der Bankachse.
        richtung = _zylinderachse(bankwinkel)
        pleuel = _richte(pleuel_muster, "hubzapfen", "kolbenbolzen", ziel,
                         _pleuelrichtung(ziel.ort, richtung, l))
        teile.extend([("Pleuel %d" % nr, s) for _n, s in pleuel.koerper])
        proben.append((pleuel.punkt("hubzapfen"), ziel))

        # Andocken legt die Verdrehung UM die Bolzenachse nicht fest — die
        # kuerzeste Drehung traf beim Reihenmotor zufaellig, beim V-Motor
        # nicht, und die Ventiltaschen standen schief zu den Ventilen
        # (11 bis 24 % Durchdringung). Deshalb wird der Kolben wie das
        # Pleuel ausgerichtet: sein Boden zeigt die Zylinderachse entlang.
        kolben = _richte(kolben_muster, "bolzen", "boden",
                         pleuel.punkt("kolbenbolzen"), richtung)
        teile.extend([("Kolben %d" % nr, s) for _n, s in kolben.koerper])
        proben.append((kolben.punkt("bolzen"), pleuel.punkt("kolbenbolzen")))
        # Wo dieser Zylinder wirklich steht — nicht wo sein Hubzapfen sitzt.
        # Beim V-Motor sind die beiden Pleuel um die halbe Breite versetzt,
        # und die Ventile standen dadurch 28 mm neben ihrem Kolben.
        zylinder_x[nr] = kolben.punkt("bolzen").ort.x

    if not mit_ventiltrieb:
        return teile, k, proben

    # --- Ventiltrieb ------------------------------------------------------
    einlass_d = kt_ventil.vorschlag(bohrung, ventile_je_zylinder, True)
    auslass_d = kt_ventil.vorschlag(bohrung, ventile_je_zylinder, False)
    ventil_l = round(k["blockhoehe"] * 0.5 + 40.0, 1)
    muster = {
        "einlass": kt_ventil.baue(teller_d=einlass_d, laenge=ventil_l,
                                  name="Einlassventil"),
        "auslass": kt_ventil.baue(teller_d=auslass_d, laenge=ventil_l,
                                  name="Auslassventil"),
    }
    feder_muster = kt_ventilfeder.baue(einbaulaenge=42.0, hub=ventilhub)
    stoessel_muster = kt_stoessel.baue()

    # Wie hoch liegt die Nockenwellenachse? So, dass der Grundkreis den
    # Stoessel eines geschlossenen Ventils gerade beruehrt.
    nocken_grundkreis_r = 16.0
    stoessel_h = stoessel_muster.kennwerte["hoehe"]
    achshoehe = (k["blockhoehe"] + ventil_l + stoessel_h
                 + nocken_grundkreis_r)
    kurbelwinkel = B.zapfenwinkel(bauform, v8_kreuzebene)

    je_seite = max(1, int(ventile_je_zylinder) // 2)
    nockenachsen = {}
    for nr, (seite, _x, bankwinkel, zapfen) in enumerate(lagen, 1):
        richtung = _zylinderachse(bankwinkel)
        mitte = Vector(zylinder_x[nr], 0.0, 0.0)
        for j in range(int(ventile_je_zylinder)):
            art = "einlass" if j < je_seite else "auslass"
            # Vector.multiply() skaliert IN PLACE. `richtung` einmal zu
            # multiplizieren hat sie fuer die naechste Runde veraendert, und
            # die Ventile sind in Zehnerpotenzen davongeflogen: 2e5, 1.8e8,
            # 1.65e11. Deshalb hier jede Richtung frisch bauen.
            quer = Vector(1, 0, 0).cross(richtung)
            if quer.Length < 1e-9:
                quer = Vector(0, 1, 0)
            quer.normalize()
            # Ein- und Auslass liegen QUER zur Kurbelwelle (dort laufen die
            # beiden Nockenwellen), die beiden Ventile einer Sorte laengs.
            # Andersherum saessen beide Nockenwellen uebereinander.
            seitwaerts = (-1.0 if art == "einlass" else 1.0) * einlass_d * 0.6
            laengs = (-1.0 if (j % je_seite) == 0 else 1.0) * einlass_d * 0.55

            # Wie weit hat der Nocken dieses Ventil gerade geoeffnet? Der
            # Nockenwinkel ist der halbe Kurbelwinkel; der Auslass eilt um
            # eine halbe Umdrehung vor. Ohne diese Rechnung muesste die
            # Nockenwelle freigestellt werden und haette die Stoessel
            # durchdrungen (gemessen 28,3 %).
            # Die Spreizung: der Nockenscheitel liegt rund 110 Grad
            # Kurbelwinkel NACH dem oberen Totpunkt (Einlass) bzw. davor
            # (Auslass), nicht im Totpunkt selbst. Genau dafuer ist sie da —
            # ohne Spreizung stand Zylinder 4 im OT mit voll geoeffnetem
            # Einlassventil, und Kolben und Ventil durchdrangen sich zu
            # 51,7 %. Das ist keine Modellschwaeche, sondern der Grund,
            # warum es die Spreizung gibt.
            versatz_kw = float(spreizung) * (1.0 if art == "einlass" else -1.0)
            # Bank B sitzt beim geteilten Hubzapfen auf der um den Versatz
            # weitergedrehten Haelfte — ihr oberer Totpunkt liegt also
            # entsprechend spaeter. Mit dem Nennwinkel gerechnet oeffneten
            # ihre Ventile zur falschen Zeit und schlugen in den Kolben
            # (V6, V10, V12: 2,5 bis 10,4 % Durchdringung).
            kw_zyl = kurbelwinkel[zapfen]
            if seite == 1 and versatz:
                kw_zyl += versatz
            nw_winkel = ((kw_zyl + versatz_kw) / 2.0
                         + (0.0 if art == "einlass" else 180.0)) % 360.0
            # Der Stoessel steht in Richtung der Zylinderachse: ein Nocken
            # zeigt bei w auf (0, -sin w, cos w), die Zylinderachse liegt bei
            # bankwinkel — der Stoessel also bei 180 - bankwinkel.
            # Die Nockenwelle wird um denselben Winkel gekippt wie ihre
            # Ventile, im Wellenbild steht der Stoessel also wieder bei 180.
            hub_jetzt = _nockenhub(nw_winkel, ventilhub,
                                   nocken_grundkreis_r,
                                   stoessel_winkel=180.0)
            hoch = Vector(richtung).multiply(k["blockhoehe"] - hub_jetzt)
            quer_v = Vector(quer).multiply(seitwaerts)
            fuss = Vector(mitte).add(hoch).add(Vector(laengs, 0, 0)) \
                .add(quer_v)
            neigung = float(ventilwinkel) * (-1.0 if art == "einlass"
                                             else 1.0)
            v_richtung = FreeCAD.Rotation(Vector(1, 0, 0), neigung) \
                .multVec(Vector(richtung))
            nockenachsen.setdefault((seite, art), []).append(
                (Vector(mitte).add(Vector(quer).multiply(seitwaerts))
                 .add(Vector(laengs, 0, 0)), v_richtung, nw_winkel,
                 bankwinkel + neigung))
            # Zwei Flaechen, die sich beruehren, haben ENTGEGENGESETZTE
            # Normalen. Die Sitzflaeche des Ventils zeigt nach unten (in den
            # Brennraum), also muss der Sitz im Kopf nach oben zeigen — sonst
            # wird das Ventil beim Andocken umgedreht und haengt mit dem
            # Schaft nach unten im Block (gemessen: z 72,7…225,5 statt
            # aufwaerts).
            # Das Ventil steht geneigt: Einlass und Auslass kippen
            # gegenlaeufig aus der Zylinderachse. Ohne diesen Winkel stehen
            # beide Nockenwellen uebereinander und durchdringen sich.
            neigung = float(ventilwinkel) * (-1.0 if art == "einlass"
                                             else 1.0)
            v_richtung = FreeCAD.Rotation(Vector(1, 0, 0), neigung) \
                .multVec(Vector(richtung))
            ziel = S.Punkt("ventilsitz_%d_%d" % (nr, j + 1), fuss,
                           v_richtung, "flaeche",
                           muster[art].kennwerte["teller_d"])
            ventil = S.andocke(muster[art], "sitz", ziel)
            teile.extend([("%s %d.%d" % (muster[art].name, nr, j + 1), s)
                          for _n, s in ventil.koerper])
            st = S.andocke(stoessel_muster, "ventil",
                           ventil.punkt("schaft_ende"))
            teile.extend([("%s %d.%d" % (n, nr, j + 1), s)
                          for n, s in st.koerper])
            proben.append((st.punkt("ventil"), ventil.punkt("schaft_ende")))
            # Die Feder sitzt mit ihrem Teller am Schaftende. Hier stossen
            # NICHT zwei Flaechen gegeneinander: Tellerkante und Schaftende
            # zeigen beide nach oben, die Feder haengt darunter. Mit der
            # gegenlaeufigen Paarung wird sie umgedreht und steht ueber dem
            # Ventil (gemessen: z 382…424 statt 336…378).
            feder = S.andocke(feder_muster, "oben",
                              ventil.punkt("schaft_ende"),
                              gegenlaeufig=False)
            teile.extend([("%s %d.%d" % (n, nr, j + 1), s)
                          for n, s in feder.koerper])
            # Die Lage der Feder wird nicht als Paarung gefuehrt: Tellerrand
            # und Schaftdurchmesser sind verschiedene Masse, die Pruefung
            # meldete zu Recht 30 gegen 6 mm. Dass sie richtig sitzt, zeigt
            # die Durchdringungspruefung.

    # --- Nockenwellen -----------------------------------------------------
    # Eine je Bank und Ventilsorte, und jede genau dort, wo ihre Stoessel
    # stehen — die Lage kommt aus den Ventilen, nicht aus einer Schaetzung.
    hoehe = achshoehe
    nocken_lage = {}
    for lfd, ((seite, art), eintraege) in enumerate(
            sorted(nockenachsen.items()), 1):
        # Ein Nocken JE VENTIL, an der x-Lage seines Stoessels. Mit
        # gleichmaessiger Teilung bekam ein Vierventiler acht Nocken im
        # Zylinderabstand und eine 822 mm lange Welle.
        eintraege = sorted(eintraege, key=lambda e: e[0].x)
        winkel = [w for _o, _r, w, _k in eintraege]
        orte = [o.x for o, _r, _w, _k in eintraege]
        nw = kt_nockenwelle.baue(winkel=winkel, orte=orte, hub=ventilhub,
                                 grundkreis_d=2.0 * nocken_grundkreis_r)
        ort0, richtung0, _w, kippung = eintraege[0]
        achse = Vector(ort0).add(Vector(richtung0).multiply(hoehe))
        # Die Welle wird in x schon richtig gebaut, quer versetzt UND um
        # denselben Winkel gekippt wie ihre Ventile — dann stehen ihre
        # Nocken senkrecht auf den Stoesseln.
        versch = FreeCAD.Placement(
            Vector(0.0, achse.y, achse.z),
            FreeCAD.Rotation(Vector(1, 0, 0), kippung))
        gesetzt = nw.bewegt(versch)
        teile.extend([("Nockenwelle %d (%s)" % (lfd, art), s)
                      for _n, s in gesetzt.koerper])
        if art == "einlass":
            nocken_lage[seite] = Vector(0.0, achse.y, achse.z)

    # --- Steuertrieb: JE BANK einer ---------------------------------------
    # Ein V-Motor hat zwei Zylinderbaenke mit je eigenen Nockenwellen, und
    # jede braucht ihren Antrieb. Ein einzelner Kettentrieb kann nicht beide
    # erreichen.
    for seite in sorted(nocken_lage) or [0]:
        lage = nocken_lage.get(seite, Vector(0, 0, hoehe))
        abstand_nw = math.hypot(lage.y, lage.z) or hoehe
        st = kt_steuertrieb.baue(art=steuertrieb,
                                 zaehne_kurbel=zaehne_kurbel,
                                 achsabstand=abstand_nw, doc=doc)
        # Der Trieb wird in der YZ-Ebene nach +z gebaut; in die Bankebene
        # gedreht zeigt er auf die Nockenwelle dieser Bank.
        # Drehsinn nachgemessen: eine Drehung um +X fuehrt +z nach +y.
        kipp = math.degrees(math.atan2(lage.y, lage.z))
        gedreht = st.bewegt(FreeCAD.Placement(
            Vector(0, 0, 0), FreeCAD.Rotation(Vector(1, 0, 0), kipp)))
        # Die Kurbelraeder der beiden Baenke sitzen NEBENEINANDER auf der
        # Kurbelnase — uebereinander gesetzt durchdringen sie sich zu 100 %.
        nase = kw.punkt("steuertrieb")
        anzahl = max(1, len(nocken_lage))
        versatz_x = (seite - (anzahl - 1) / 2.0) * 16.0
        ziel_nase = S.Punkt(nase.name,
                            Vector(nase.ort).add(Vector(versatz_x, 0, 0)),
                            nase.achse, nase.art, nase.mass, nase.hinweis)
        gesetzt = S.andocke(gedreht, "kurbel", ziel_nase)
        teile.extend([("Bank %d: %s" % (seite + 1, n), sh)
                      for n, sh in gesetzt.koerper])
        k.setdefault("steuertriebe", []).append(st.kennwerte)
    k["steuertrieb"] = k.get("steuertriebe", [{}])[0]

    # --- Getriebe anflanschen --------------------------------------------
    if mit_getriebe:
        teile.extend(_getriebe_anflanschen(kw.punkt("abtrieb"), k, doc,
                                           getriebe_gaenge))

    return teile, k, proben


def _getriebe_anflanschen(abtrieb, k, doc, gaenge=5):
    """Das Getriebe aus Tools/getriebe_fcgear.py hinter den Motor setzen.

    Beide laufen in der Normallage entlang X mit der Welle auf y = z = 0 —
    es genuegt also eine Verschiebung. Der Anschluss ist der
    Schwungradflansch der Kurbelwelle; dort beginnt die Eingangswelle des
    Getriebes.
    """
    import getriebe_fcgear as GF

    welle_d = 20.0
    teile = GF.baue(gaenge=int(gaenge), welle_d=welle_d, doc=doc)
    # Wo faengt die Eingangswelle des Getriebes in seinem eigenen Bild an?
    wellen = [s for n, s in teile if "welle" in n.lower()]
    if not wellen:
        return []
    anfang = min(s.BoundBox.XMin for s in wellen)
    versatz = FreeCAD.Vector(abtrieb.ort.x - anfang, 0.0, 0.0)
    aus = []
    for label, shp in teile:
        kopie = shp.copy()
        kopie.translate(versatz)
        aus.append(("Getriebe: " + label, kopie))
    k["getriebe"] = {"gaenge": int(gaenge), "teile": len(aus),
                     "anschluss_x": round(abtrieb.ort.x, 2)}
    return aus


def _richte(bauteil, anschluss, ziel_punkt_name, ziel, richtung):
    """Bauteil andocken und um den Anschluss in eine Richtung drehen.

    Das Pleuel hängt am Hubzapfen und muss zur Zylinderachse zeigen. Erst
    andocken, dann um die Zapfenachse drehen, bis das andere Auge in der
    Zylinderachse liegt — die Drehung um den Anschluss verliert ihn nicht.
    """
    gesetzt = S.andocke(bauteil, anschluss, ziel)
    a = gesetzt.punkt(anschluss).ort
    b = gesetzt.punkt(ziel_punkt_name).ort
    ist = b.sub(a)
    achse = Vector(ziel.achse)
    # Anteile senkrecht zur Zapfenachse vergleichen.
    ist = ist.sub(achse.multiply(ist.dot(Vector(ziel.achse))))
    soll = Vector(richtung)
    soll = soll.sub(Vector(ziel.achse).multiply(
        soll.dot(Vector(ziel.achse))))
    if ist.Length < 1e-9 or soll.Length < 1e-9:
        return gesetzt
    ist.normalize()
    soll.normalize()
    cos = max(-1.0, min(1.0, ist.dot(soll)))
    winkel = math.degrees(math.acos(cos))
    if ist.cross(soll).dot(Vector(ziel.achse)) < 0:
        winkel = -winkel
    dreh = FreeCAD.Placement(a, FreeCAD.Rotation(Vector(ziel.achse), winkel),
                             Vector(0, 0, 0))
    return gesetzt.bewegt(FreeCAD.Placement(
        dreh.Base.sub(dreh.Rotation.multVec(dreh.Base)), dreh.Rotation))


def _zylindermitte(kw, lagen, index, zylinderabstand):
    """x-Lage der Zylindermitte, aus dem Hubzapfen der Kurbelwelle."""
    zapfen = lagen[index][3]
    p = kw.punkt("hubzapfen_%d" % (zapfen + 1))
    return Vector(p.ort.x, 0.0, 0.0)


def pruefe(teile=None, proben=None, kenn=None, toleranz=0.02, **kw):
    """Misst den Zusammenbau nach; liefert [(ok, Text), ...]."""
    if teile is None:
        teile, kenn, proben = baue(**kw)
    befunde = []

    def sag(ok, text):
        befunde.append((bool(ok), text))

    sag(all(s.Solids for _n, s in teile),
        "alle %d Koerper sind Solids" % len(teile))

    # Jede Paarung muss wirklich aufeinanderliegen.
    schlecht = []
    for a, b in (proben or []):
        ok, text = S.pruefe_paarung(a, b)
        if not ok:
            schlecht.append(text)
    sag(not schlecht,
        "alle %d Schnittstellen passen%s"
        % (len(proben or []), "" if not schlecht
           else ": " + "; ".join(schlecht[:3])))

    # Die Blockhoehe muss aus dem Kurbeltrieb folgen.
    if kenn:
        soll = blockhoehe(kenn["hub"], kenn["stichmass"],
                          kenn["kompressionshoehe"])
        sag(abs(kenn["blockhoehe"] - soll) < 1e-6,
            "Blockhoehe %.1f mm = Kurbelradius + Stichmass + "
            "Kompressionshoehe" % kenn["blockhoehe"])
        sag(0.20 <= kenn["lambda"] <= 0.35,
            "Schubstangenverhaeltnis lambda = %.3f (ueblich 0,20…0,35)"
            % kenn["lambda"])

    # Nichts darf sich durchdringen — die Schnittstellen koennen passen und
    # die Bauteile trotzdem ineinander stecken.
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

    # Bankversatz: die zweite Bank muss um genau eine Pleuelbreite
    # versetzt stehen, und jede Bank fuer sich in einer Reihe.
    if kenn and kenn.get("bankversatz"):
        reihen = {}
        for n, sh in teile:
            if not n.startswith("Kolben "):
                continue
            nr = int(n.split()[1])
            reihen.setdefault((nr - 1) % 2, []).append(
                (sh.BoundBox.XMin + sh.BoundBox.XMax) / 2.0)
        if len(reihen) == 2:
            a = sorted(reihen[0])
            b = sorted(reihen[1])
            versatz = [round(y - x, 2) for x, y in zip(a, b)]
            gleich = len(set(versatz)) == 1
            sag(gleich and abs(versatz[0] - kenn["bankversatz"]) < 0.5,
                "Bankversatz %s mm (erwartet %.1f)"
                % (sorted(set(versatz)), kenn["bankversatz"]))

    # Kolben und Pleuel: je Zylinder eines.
    if kenn:
        for wort, soll_n in (("Kolben", kenn["zylinder"]),
                             ("Pleuel", kenn["zylinder"])):
            ist = sum(1 for n, _s in teile if n.startswith(wort))
            sag(ist == soll_n, "%d %s fuer %d Zylinder"
                % (ist, wort, kenn["zylinder"]))

    return befunde


def selbsttest(bauformen=("R4", "V6")):
    """Baut die genannten Bauformen und prüft sie."""
    schlecht = []
    for bauform in bauformen:
        teile, kenn, proben = baue(bauform=bauform, mit_ventiltrieb=False)
        for ok, text in pruefe(teile, proben, kenn):
            if not ok:
                schlecht.append("%s: %s" % (bauform, text))
    if schlecht:
        raise AssertionError("; ".join(schlecht))
    return "Motor-Selbsttest bestanden (%s)" % ", ".join(bauformen)
