# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Ventiltrieb — Ventile, Federn, Tassenstößel, Nockenwellen, Steuertrieb.

    teile, proben, kenn = baue(bauform="V8", zylinder_x={...}, ...)

Baut auf dem Kurbeltrieb auf: der braucht nur zu sagen, wo seine Zylinder
stehen (``zylinder_x``) und wo sein Steuertriebzapfen sitzt.

Die Reihenfolge ist keine Willkür, sondern eine Kette von Abhängigkeiten:

1. Der **Nockenwinkel** folgt aus dem Kurbelwinkel des Zylinders und der
   Spreizung — damit steht fest, wie weit das Ventil gerade offen ist.
2. Das **Ventil** wird um diesen Hub aus seinem Sitz herausgeschoben, entlang
   **seiner eigenen** Achse (geneigt um den Ventilwinkel), nicht entlang der
   Zylinderachse.
3. Der **Stößel** sitzt auf dem Schaftende, die **Feder** darunter.
4. Die **Nockenwellenachse** kommt aus dem Stößel: bei einem Tassenstößel
   liegt sie genau über der Ventilachse. Aus der Zylinderachse abgeleitet
   sah das Ergebnis aus wie ein Schlepphebelmotor.
5. Der **Steuertrieb** läuft je Bank über *alle* Nockenwellen dieser Bank —
   ein DOHC-Kopf hat zwei, und beide müssen angetrieben werden.

Drei Dinge, die hier schon einmal falsch waren und die der Motor nachmisst:
Ventilwinkel (ohne ihn stehen die Nockenwellen ineinander), Kippwinkel der
Nockenwelle (``neigung − bankwinkel``, nicht die Summe — mit der Summe stand
sie bei V-Motoren 90 Grad daneben), und die Fluchtung von Nockenwellen- und
Ventilachse.
"""

import math

import FreeCAD
from FreeCAD import Vector

import kt_auslassventil
import kt_bauformen as B
import kt_einlassventil
import kt_kinematik as K
import kt_nockenwelle
import kt_schnittstelle as S
import kt_steuertrieb
import kt_stoessel
import kt_ventilfeder


class VentiltriebFehler(Exception):
    pass


#: Grundkreisradius der Nockenwelle [mm]. Bestimmt zusammen mit Ventil- und
#: Stößellänge die Höhe der Nockenwellenachse über dem Block.
GRUNDKREIS_R = 16.0


def ventiltaschen(bohrung, ventile_je_zylinder, tiefe, ventilwinkel=0.0,
                  ventilhub=10.0):
    """Lage und Maß der Ventiltaschen im Kolbenboden.

    Die Taschen werden **symmetrisch** gesetzt, an allen vier Stellen.
    Welche Seite beim V-Motor später Ein- und welche Auslass ist, hängt von
    der Bank ab — mit gerichteten Taschen landeten sie bei einer Bank
    spiegelverkehrt, und das Ventil schlug in den Kolbenboden.

    Der Kolben wird über seinen Bolzen angedockt, und der liegt später auf
    der Kurbelwellenachse: aus kolbenlokal +Y wird die x-Richtung des Motors.

    ``ventilwinkel`` und ``ventilhub`` weiten die Tasche um den seitlichen
    Weg, den ein geneigtes Ventil beim Öffnen macht.
    """
    ein = kt_einlassventil.vorschlag(bohrung, ventile_je_zylinder)
    aus = kt_auslassventil.vorschlag(bohrung, ventile_je_zylinder)
    # Ein geneigtes Ventil taucht SCHRAEG in den Kolbenboden: sein Teller
    # wandert um hub*sin(winkel) zur Seite. Ohne diesen Zuschlag lief das
    # Ventil bei 28 Grad neben seiner Tasche in den Kolben (3,7 %).
    seitwaerts = abs(float(ventilhub)) * math.sin(math.radians(
        abs(float(ventilwinkel))))
    d = max(ein, aus) + 8.0 + 2.0 * seitwaerts
    # QUADRATISCHES Raster, obwohl die Ventile auf einem rechteckigen
    # sitzen (0,6 quer, 0,55 laengs). Ob kolbenlokal +X auf die Motorachse
    # oder quer dazu faellt, haengt davon ab, wie ``richte()`` den Kolben um
    # seinen Bolzen dreht — und das kippt zwischen den Baenken. Mit einem
    # rechteckigen Raster lag die Tasche dann 1,55 mm daneben, und bei
    # 120 Grad Bankwinkel streifte der Einlassteller den Rand. Quadratisch
    # ist das Raster gegen den Achsentausch unempfindlich.
    # Die Mulde steht SENKRECHT ZUR VENTILACHSE, also um den Ventilwinkel
    # gekippt — und zwar nach aussen, weg von der Kolbenmitte: genau so
    # neigen sich Ein- und Auslassventil aus der Zylinderachse. Dadurch
    # bleibt sie flach (4,8 statt 12 mm) und deckt die schraege
    # Tellerkante trotzdem ab.
    versatz = ein * 0.6
    return [(quer * versatz, laengs * versatz, d, float(tiefe),
             quer * float(ventilwinkel))
            for quer in (-1.0, 1.0) for laengs in (-1.0, 1.0)]


def achshoehe(blockhoehe, ventil_l, stoessel_h, grundkreis_r=GRUNDKREIS_R):
    """Höhe der Nockenwellenachse über der Kurbelwellenmitte [mm].

    So hoch, dass der Grundkreis den Stößel eines geschlossenen Ventils
    gerade berührt.
    """
    return (float(blockhoehe) + float(ventil_l) + float(stoessel_h)
            + float(grundkreis_r))


def ventillaenge(blockhoehe):
    """Übliche Ventillänge zu dieser Blockhöhe [mm]."""
    return round(float(blockhoehe) * 0.5 + 40.0, 1)


def baue(bauform="R4", bohrung=86.0, blockhoehe=225.5, zylinder_x=None,
         zylinderabstand=101.5, ventile_je_zylinder=4, ventilhub=10.0,
         spreizung=110.0, ventilwinkel=12.0, steuertrieb="kette",
         zaehne_kurbel=20, kurbelnase=None, auslegung=None,
         bankwinkel=0.0, v8_kreuzebene=True, doc=None):
    """Der ganze Ventiltrieb.

    zylinder_x   {Zylindernummer: x-Lage} aus ``kt_kurbeltrieb.baue``
    kurbelnase   der Punkt ``steuertrieb`` der Kurbelwelle; ohne ihn wird
                 der Steuertrieb weggelassen
    auslegung    die Maßtabelle aus ``kt_auslegung``. Daher kommen die
                 Maße, die zwei Bauteile teilen — Grundkreis (Nockenwelle
                 und Achshöhe), Zapfendurchmesser (Nockenwelle und
                 Kettenrad), Kurbelnase (Kurbelwelle und Kettenrad). Ohne
                 sie gelten die Vorgaben dieses Moduls.

    Liefert ``(teile, proben, kenn)``. ``kenn`` enthält ``nockenachsen``,
    ``angetrieben``, ``fluchtungen`` und ``steuertriebe`` — die Zahlen, die
    ``kt_motor.pruefe()` nachmisst.
    """
    zylinder_x = dict(zylinder_x or {})
    a = dict(auslegung or {})
    grundkreis_r = float(a.get("nocken_grundkreis_d",
                               2.0 * GRUNDKREIS_R)) / 2.0
    nw_zapfen_d = float(a.get("nockenwelle_antrieb_d", 26.0))
    kurbel_zapfen_d = float(a.get("steuertrieb_d", 30.0))
    stoessel_d = float(a.get("stoessel_d", 33.0))
    # Nur noch fuer die Stoesselgroesse: der dickere der beiden Schaefte.
    schaft_d = float(a.get("ventil_schaft_d", 6.0))
    lagen = B.zylinderlagen(bauform, zylinderabstand, v8_kreuzebene,
                            bankwinkel)
    versatz = B.hubzapfenversatz(bauform, v8_kreuzebene, bankwinkel)
    kurbelwinkel = B.zapfenwinkel(bauform, v8_kreuzebene)
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Ventiltrieb")

    teile = []
    proben = []
    kenn = {}

    ventil_l = ventillaenge(blockhoehe)
    # Ein- und Auslassventil sind zwei verschiedene Bauteile mit je eigenem
    # Skript: der Einlass gross und leicht, der Auslass kleiner, mit
    # dickerem, natriumgefuelltem Schaft und Tulpenteller.
    muster = {
        "einlass": kt_einlassventil.baue(
            bohrung=bohrung, ventile_je_zylinder=ventile_je_zylinder,
            laenge=ventil_l),
        "auslass": kt_auslassventil.baue(
            bohrung=bohrung, ventile_je_zylinder=ventile_je_zylinder,
            laenge=ventil_l),
    }
    einlass_d = muster["einlass"].kennwerte["teller_d"]
    auslass_d = muster["auslass"].kennwerte["teller_d"]
    # Feder und Federteller richten sich nach dem VENTIL, nicht nach einer
    # Vorgabe: bei 120 mm Bohrung ist der Auslassschaft 9,6 mm dick, der
    # Teller war fuer 6 mm gebohrt — 4,9 % Durchdringung.
    feder_muster = {
        art: kt_ventilfeder.baue(
            einbaulaenge=round(0.42 * float(ventil_l), 1),
            aussen_d=round(muster[art].kennwerte["teller_d"] * 0.87, 1),
            draht_d=round(muster[art].kennwerte["teller_d"] * 0.116, 2),
            schaft_d=muster[art].kennwerte["schaft_d"],
            teller_d=round(muster[art].kennwerte["teller_d"] * 0.97, 1),
            hub=ventilhub)
        for art in ("einlass", "auslass")
    }
    # JE Ventilsorte ein Stoesselmuster. Ein- und Auslassventil haben
    # verschieden dicke Schaefte (6,0 gegen 6,9 mm bei 86 mm Bohrung), und
    # das Kennmass des Anschlusspunktes muss zu SEINEM Ventil passen — mit
    # einem gemeinsamen Muster meldete die Paarungspruefung zu Recht
    # "Kennmass 6,9 gegen 6,0 mm".
    stoessel_muster = {
        art: kt_stoessel.baue(tassen_d=stoessel_d,
                              ventil_d=muster[art].kennwerte["schaft_d"])
        for art in ("einlass", "auslass")
    }
    hoehe = achshoehe(blockhoehe, ventil_l,
                      stoessel_muster["einlass"].kennwerte["hoehe"],
                      grundkreis_r)

    je_seite = max(1, int(ventile_je_zylinder) // 2)
    nockenachsen = {}
    fluchtungen = []

    # --- Ventile, Federn, Stoessel ---------------------------------------
    for nr, (seite, _x, bankwinkel, zapfen) in enumerate(lagen, 1):
        richtung = K.zylinderachse(bankwinkel)
        mitte = Vector(zylinder_x.get(nr, 0.0), 0.0, 0.0)
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

            # Bank B sitzt beim geteilten Hubzapfen auf der um den Versatz
            # weitergedrehten Haelfte — ihr oberer Totpunkt liegt also
            # entsprechend spaeter. Mit dem Nennwinkel gerechnet oeffneten
            # ihre Ventile zur falschen Zeit und schlugen in den Kolben
            # (V6, V10, V12: 2,5 bis 10,4 % Durchdringung).
            kw_zyl = kurbelwinkel[zapfen]
            if seite == 1 and versatz:
                kw_zyl += versatz
            nw_winkel = K.nockenwinkel(kw_zyl, spreizung, art)
            # Die Nockenwelle wird um denselben Winkel gekippt wie ihre
            # Ventile, im Wellenbild steht der Stoessel also bei 180 Grad.
            hub_jetzt = K.nockenhub(nw_winkel, ventilhub, grundkreis_r,
                                    stoessel_winkel=180.0)
            # Das Ventil steht geneigt: Einlass und Auslass kippen
            # gegenlaeufig aus der Zylinderachse. Ohne diesen Winkel stehen
            # beide Nockenwellen uebereinander und durchdringen sich.
            neigung = float(ventilwinkel) * (-1.0 if art == "einlass"
                                             else 1.0)
            v_richtung = FreeCAD.Rotation(Vector(1, 0, 0), neigung) \
                .multVec(Vector(richtung))
            # Ein Ventil oeffnet entlang SEINER EIGENEN Achse, nicht entlang
            # der Zylinderachse. Mit dem Hub auf der Zylinderachse gerechnet
            # wandert die Nockenwellenachse mit dem Hub, und die Wellen
            # passten je Zylinder nicht mehr auf ihre Stoessel (11 %
            # Durchdringung bei den V-Motoren).
            hoch = Vector(richtung).multiply(float(blockhoehe))
            quer_v = Vector(quer).multiply(seitwaerts)
            fuss = Vector(mitte).add(hoch).add(Vector(laengs, 0, 0)) \
                .add(quer_v).sub(Vector(v_richtung).multiply(hub_jetzt))
            # Zwei Flaechen, die sich beruehren, haben ENTGEGENGESETZTE
            # Normalen. Die Sitzflaeche des Ventils zeigt nach unten (in den
            # Brennraum), also muss der Sitz im Kopf nach oben zeigen — sonst
            # wird das Ventil beim Andocken umgedreht und haengt mit dem
            # Schaft nach unten im Block (gemessen: z 72,7…225,5 statt
            # aufwaerts).
            ziel = S.Punkt("ventilsitz_%d_%d" % (nr, j + 1), fuss,
                           v_richtung, "flaeche",
                           muster[art].kennwerte["teller_d"])
            ventil = S.andocke(muster[art], "sitz", ziel)
            teile.extend([("%s %d.%d" % (muster[art].name, nr, j + 1), s)
                          for _n, s in ventil.koerper])
            st = S.andocke(stoessel_muster[art], "ventil",
                           ventil.punkt("schaft_ende"))
            teile.extend([("%s %d.%d" % (n, nr, j + 1), s)
                          for n, s in st.koerper])
            proben.append((st.punkt("ventil"), ventil.punkt("schaft_ende")))
            # Bei einem Tassenstoesselmotor liegt die Nockenwellenachse
            # GENAU UEBER der Ventilachse — der Nocken drueckt senkrecht auf
            # den Tassenboden.
            nocken_achse = Vector(st.punkt("nocken").ort).add(
                Vector(v_richtung).multiply(grundkreis_r + hub_jetzt))
            # Der Kippwinkel der Nockenwelle: im Wellenbild zeigt 180 Grad
            # nach -Z; nach der Drehung um kippung muss das -v_richtung
            # sein. Aus Rot(X, d)*(0,0,-1) = (0, sin d, -cos d) und
            # -v_richtung = (0, -sin phi, -cos phi) folgt d = -phi, und phi
            # ist der Winkel von v_richtung, also bankwinkel - neigung.
            # Mit bankwinkel + neigung gerechnet stimmte es nur fuer
            # Reihenmotoren (bankwinkel = 0); bei den V-Motoren stand die
            # Welle 90 Grad daneben und drueckte in die Stoessel.
            nockenachsen.setdefault((seite, art), []).append(
                (nocken_achse, v_richtung, nw_winkel, neigung - bankwinkel))
            # Fuer die Pruefung: Stoesselachse und die Achse, auf der die
            # Nockenwelle liegen wird.
            fluchtungen.append((Vector(st.punkt("nocken").ort),
                                Vector(v_richtung), Vector(nocken_achse),
                                "%s %d.%d" % (art, nr, j + 1)))
            # Die Feder sitzt mit ihrem Teller am Schaftende. Hier stossen
            # NICHT zwei Flaechen gegeneinander: Tellerkante und Schaftende
            # zeigen beide nach oben, die Feder haengt darunter. Mit der
            # gegenlaeufigen Paarung wird sie umgedreht und steht ueber dem
            # Ventil (gemessen: z 382…424 statt 336…378).
            feder = S.andocke(feder_muster[art], "oben",
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
    nocken_lage = {}
    for lfd, ((seite, art), eintraege) in enumerate(
            sorted(nockenachsen.items()), 1):
        # Ein Nocken JE VENTIL, an der x-Lage seines Stoessels. Mit
        # gleichmaessiger Teilung bekam ein Vierventiler acht Nocken im
        # Zylinderabstand und eine 822 mm lange Welle.
        eintraege = sorted(eintraege, key=lambda e: e[0].x)
        nw = kt_nockenwelle.baue(winkel=[w for _o, _r, w, _k in eintraege],
                                 orte=[o.x for o, _r, _w, _k in eintraege],
                                 hub=ventilhub,
                                 grundkreis_d=2.0 * grundkreis_r,
                                 antrieb_d=nw_zapfen_d)
        ort0, _richtung0, _w, kippung = eintraege[0]
        # Die Welle wird in x schon richtig gebaut, quer versetzt UND um
        # denselben Winkel gekippt wie ihre Ventile — dann stehen ihre
        # Nocken senkrecht auf den Stoesseln.
        gesetzt = nw.bewegt(FreeCAD.Placement(
            Vector(0.0, ort0.y, ort0.z),
            FreeCAD.Rotation(Vector(1, 0, 0), kippung)))
        teile.extend([("Nockenwelle %d (%s)" % (lfd, art), s)
                      for _n, s in gesetzt.koerper])
        nocken_lage.setdefault(seite, []).append(
            (art, Vector(0.0, ort0.y, ort0.z)))
        kenn.setdefault("nockenachsen", []).append(
            {"bank": seite + 1, "art": art,
             "y": round(ort0.y, 2), "z": round(ort0.z, 2)})

    kenn["fluchtungen"] = fluchtungen
    if kurbelnase is None:
        return teile, proben, kenn

    # --- Steuertrieb: JE BANK einer, ueber ALLE Nockenwellen --------------
    # Ein V-Motor hat zwei Zylinderbaenke mit je eigenen Nockenwellen, und
    # jede braucht ihren Antrieb. Innerhalb einer Bank haengen bei einem
    # DOHC-Kopf BEIDE Wellen an derselben Kette — Einlass und Auslass. Wird
    # nur eine angetrieben, laeuft die andere gar nicht.
    anzahl = max(1, len(nocken_lage))
    for seite in sorted(nocken_lage) or [0]:
        wellen = nocken_lage.get(seite) or [("einlass", Vector(0, 0, hoehe))]
        # Der Trieb wird gleich in Dokumentkoordinaten gebaut: die Lagen
        # der Nockenwellen sind schon die richtigen. Frueher wurde ein
        # ebener Trieb um X gekippt — mit zwei Wellen je Bank, die
        # verschieden weit von der Kurbel stehen, geht das nicht mehr auf.
        lagen_nw = [(w.y, w.z) for _art, w in wellen]
        abstand_nw = max(math.hypot(y, z) for y, z in lagen_nw) or hoehe
        # Die Kettenteilung folgt dem ENGSTEN Wellenabstand dieser Bank —
        # bei einem DOHC-Kopf ist das der zwischen den beiden Nockenwellen.
        # Mit fester 3/8"-Teilung ist das Nockenrad 121 mm gross, und bei
        # kleinem Ventilwinkel stehen die Wellen nur 37 mm auseinander: die
        # beiden Raeder durchdrangen sich zu 51,9 %.
        orte = [(0.0, 0.0)] + lagen_nw
        eng = min(math.hypot(orte[i][0] - orte[j][0],
                             orte[i][1] - orte[j][1])
                  for i in range(len(orte)) for j in range(i + 1, len(orte)))
        teilung = kt_steuertrieb.auslegen_kette(
            zaehne_kurbel, eng, kurbel_zapfen_d, nw_zapfen_d)
        if teilung is None and steuertrieb == "kette":
            raise VentiltriebFehler(
                "Ein Kettentrieb ueber beide Nockenwellen ist hier nicht zu "
                "bauen: die Wellen stehen %.1f mm auseinander, und das "
                "Nockenrad hat die doppelte Zaehnezahl des Kurbelrades, ist "
                "also rund doppelt so gross wie dieses — das braucht seine "
                "%.1f mm Zapfen plus Wand. Mehr Ventilwinkel (die Wellen "
                "ruecken auseinander) oder ein duennerer Kurbelzapfen."
                % (eng, kurbel_zapfen_d))
        st = kt_steuertrieb.baue(art=steuertrieb,
                                 zaehne_kurbel=zaehne_kurbel,
                                 teilung=teilung or 9.525,
                                 achsabstand=abstand_nw,
                                 kurbel_d=kurbel_zapfen_d,
                                 nocken_d=nw_zapfen_d,
                                 nocken_lagen=lagen_nw, doc=doc)
        # Die Kurbelraeder der beiden Baenke sitzen NEBENEINANDER auf der
        # Kurbelnase — uebereinander gesetzt durchdringen sie sich zu 100 %.
        versatz_x = (seite - (anzahl - 1) / 2.0) * 16.0
        ziel_nase = S.Punkt(kurbelnase.name,
                            Vector(kurbelnase.ort).add(Vector(versatz_x, 0, 0)),
                            kurbelnase.achse, kurbelnase.art,
                            kurbelnase.mass, kurbelnase.hinweis)
        gesetzt = S.andocke(st, "kurbel", ziel_nase)
        teile.extend([("Bank %d: %s" % (seite + 1, n), sh)
                      for n, sh in gesetzt.koerper])
        proben.append((gesetzt.punkt("kurbel"), ziel_nase))
        kenn.setdefault("steuertriebe", []).append(st.kennwerte)
        # Fuer die Pruefung: jede Nockenwelle mit dem Ort ihres Rades.
        for nr, (art, w) in enumerate(wellen, 1):
            rad = gesetzt.punkt("nocken" if nr == 1 else "nocken_%d" % nr)
            kenn.setdefault("angetrieben", []).append(
                {"bank": seite + 1, "art": art,
                 "welle_y": round(w.y, 3), "welle_z": round(w.z, 3),
                 "rad_y": round(rad.ort.y, 3), "rad_z": round(rad.ort.z, 3)})

    kenn["steuertrieb"] = kenn.get("steuertriebe", [{}])[0]
    kenn["achshoehe"] = round(hoehe, 2)
    return teile, proben, kenn


def selbsttest(bauform="V8"):
    """Baut einen Ventiltrieb über einem Kurbeltrieb und misst nach."""
    import kt_auslegung
    import kt_kurbeltrieb

    a = kt_auslegung.auslegen(bohrung=86.0, hub=86.0, bauform=bauform)
    k_teile, _pr, kw, zylinder_x = kt_kurbeltrieb.baue(
        bauform=bauform, bohrung=a["bohrung"], hub=a["hub"],
        stichmass=a["stichmass"], kompressionshoehe=a["kompressionshoehe"],
        zylinderabstand=a["zylinderabstand"],
        bolzen_d=a["kolbenbolzen_d"], hubzapfen_d=a["hubzapfen_d"],
        hauptlager_d=a["hauptlager_d"], pleuel_breite=a["pleuel_breite"],
        pleuel_auge_b=a["pleuel_auge_b"], steuertrieb_d=a["steuertrieb_d"],
        wange_t=a["wange_t"], hauptlager_b=a["hauptlager_b"],
        kolben_schafthoehe=a["kolben_schafthoehe"],
        kolben_boden_t=a["kolben_boden_t"])
    teile, proben, kenn = baue(bauform=bauform, blockhoehe=a["blockhoehe"],
                               zylinder_x=zylinder_x,
                               zylinderabstand=a["zylinderabstand"],
                               ventilhub=a["ventilhub"], auslegung=a,
                               kurbelnase=kw.punkt("steuertrieb"))
    z, _bank = B.daten(bauform)
    for wort, soll in (("Einlassventil", z * 2), ("Auslassventil", z * 2)):
        ist = sum(1 for n, _s in teile if n.startswith(wort))
        if ist != soll:
            raise AssertionError("%d %s statt %d" % (ist, wort, soll))
    wellen = [n for n, _s in teile if n.startswith("Nockenwelle")]
    if len(wellen) != (4 if B.ist_v(bauform) else 2):
        raise AssertionError("%d Nockenwellen: %s" % (len(wellen), wellen))
    if len(kenn.get("angetrieben", [])) != len(wellen):
        raise AssertionError("%d von %d Nockenwellen angetrieben"
                             % (len(kenn.get("angetrieben", [])), len(wellen)))
    for e in kenn["angetrieben"]:
        ab = math.hypot(e["rad_y"] - e["welle_y"], e["rad_z"] - e["welle_z"])
        if ab > 0.05:
            raise AssertionError("Bank %d %s: Kettenrad %.2f mm neben der "
                                 "Welle" % (e["bank"], e["art"], ab))
    # Nockenwellen- und Ventilachse muessen fluchten (Tassenstoessel).
    schief = 0.0
    x_achse = Vector(1, 0, 0)
    for punkt, richtung, achse, _name in kenn["fluchtungen"]:
        n = x_achse.cross(richtung)
        if n.Length < 1e-9:
            continue
        n.normalize()
        schief = max(schief, abs(Vector(punkt).sub(achse).dot(n)))
    if schief > 0.05:
        raise AssertionError("Nockenwellenachse %.3f mm neben der "
                             "Ventilachse" % schief)
    del k_teile
    return ("Ventiltrieb-Selbsttest bestanden (%s, %d Koerper, %d Wellen "
            "alle angetrieben, Fluchtung %.3f mm)"
            % (bauform, len(teile), len(wellen), schief))
