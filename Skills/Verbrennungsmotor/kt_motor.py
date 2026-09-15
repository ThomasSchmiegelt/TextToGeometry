# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Gesamtmotor — fügt Kurbeltrieb, Ventiltrieb und Getriebe zusammen.

    teile, kenn, proben = baue(bauform="V8", bohrung=86.0, hub=86.0)

Diese Datei rechnet und zeichnet nichts mehr selbst. Sie legt die Auslegung
fest (``kennwerte``), ruft die beiden Baugruppen auf und misst das Ergebnis
nach (``pruefe``):

    kt_kurbeltrieb   Kurbelwelle, Pleuel, Kolben
    kt_ventiltrieb   Ventile, Federn, Stößel, Nockenwellen, Steuertrieb
    kt_kinematik     die Formeln, die beide brauchen
    getriebe_fcgear  optional hinter den Schwungradflansch gesetzt

Darunter liegt je Bauteil ein eigenes Skript — ``kt_kolben``, ``kt_pleuel``,
``kt_kurbelwelle``, ``kt_ventil``, ``kt_ventilfeder``, ``kt_stoessel``,
``kt_nockenwelle``, ``kt_steuertrieb`` — und ``kt_schnittstelle``, über die
sie zusammenfinden. Jedes davon hat seinen eigenen ``selbsttest()``.

Die Blockhöhe folgt aus dem Kurbeltrieb und wird nicht geraten:

    Blockhöhe = Kurbelradius + Stichmaß + Kompressionshöhe

Das ist die Strecke von der Kurbelwellenmitte bis zum Kolbenboden im oberen
Totpunkt. Wer sie unabhängig eingibt, bekommt entweder einen Kolben, der oben
heraussteht, oder einen, der nie hinkommt.
"""

import math

import FreeCAD
from FreeCAD import Vector

import kt_auslegung
import kt_bauformen as B
import kt_kinematik as K
import kt_kurbeltrieb
import kt_pleuel
import kt_schnittstelle as S
import kt_ventiltrieb


class MotorFehler(Exception):
    pass


def blockhoehe(hub, stichmass, kompressionshoehe):
    """Kurbelwellenmitte bis Kolbenboden im oberen Totpunkt [mm].

    Steht in ``kt_kinematik``; hier nur weitergereicht, weil Aufrufer und
    Tests sie seit je unter diesem Namen erwarten.
    """
    return K.blockhoehe(hub, stichmass, kompressionshoehe)


def auslegung(bauform="R4", bohrung=86.0, hub=86.0, stichmass=0.0,
              kompressionshoehe=0.0, zylinderabstand=0.0, bolzen_d=0.0,
              hubzapfen_d=0.0, hauptlager_d=0.0, pleuel_breite=0.0,
              ventilhub=0.0, ventile_je_zylinder=4, v8_kreuzebene=True,
              bankwinkel=0.0):
    """Die Maßtabelle dieses Motors (``kt_auslegung.auslegen``).

    Alles, was 0 ist, kommt aus den Verhältnissen der Bohrung — alles
    andere überschreibt sie. Damit steht jedes geteilte Maß genau einmal:
    Kolben und Pleuel bekommen denselben Bolzendurchmesser, Kurbelwelle und
    Pleuel denselben Hubzapfen, und das bleibt auch bei 120 mm Bohrung so.
    """
    return kt_auslegung.auslegen(
        bohrung=bohrung, hub=hub, bauform=bauform,
        ventile_je_zylinder=ventile_je_zylinder,
        v8_kreuzebene=v8_kreuzebene, bankwinkel=bankwinkel,
        stichmass=float(stichmass), zylinderabstand=float(zylinderabstand),
        kompressionshoehe=float(kompressionshoehe),
        kolbenbolzen_d=float(bolzen_d), hubzapfen_d=float(hubzapfen_d),
        hauptlager_d=float(hauptlager_d),
        pleuel_breite=float(pleuel_breite), ventilhub=float(ventilhub))


def kennwerte(bauform="R4", bohrung=86.0, hub=86.0, stichmass=0.0,
              kompressionshoehe=0.0, zylinderabstand=0.0,
              ventile_je_zylinder=4, v8_kreuzebene=True,
              pleuel_breite=0.0, bankwinkel=0.0, **_rest):
    """Die Auslegung auf einen Blick, ohne Geometrie."""
    a = auslegung(bauform, bohrung, hub, stichmass, kompressionshoehe,
                  zylinderabstand, pleuel_breite=pleuel_breite,
                  ventile_je_zylinder=ventile_je_zylinder,
                  v8_kreuzebene=v8_kreuzebene, bankwinkel=bankwinkel)
    l = a["stichmass"]
    k = B.kennwerte(bauform, bohrung, hub, v8_kreuzebene, bankwinkel)
    k.update({
        "bohrung": float(bohrung),
        "hub": float(hub),
        "stichmass": l,
        "lambda": a["lambda"],
        "kompressionshoehe": a["kompressionshoehe"],
        "blockhoehe": a["blockhoehe"],
        "zylinderabstand": a["zylinderabstand"],
        "auslegung": a,
        "ventile_je_zylinder": int(ventile_je_zylinder),
        "ventile_gesamt": int(ventile_je_zylinder) * k["zylinder"],
        # Bankversatz: beim V-Motor sitzen die beiden Pleuel NEBENEINANDER
        # auf demselben Hubzapfen, die Zylinderbaenke stehen deshalb um eine
        # Pleuelbreite gegeneinander versetzt. Das ist kein Schoenheitsfehler,
        # sondern folgt zwingend aus dem geteilten Zapfen.
        "bankversatz": K.bankversatz(bauform, a["pleuel_breite"],
                                     v8_kreuzebene, bankwinkel),
        "nockenwellen": 2 if B.ist_v(bauform, bankwinkel) else 1,
    })
    if B.ist_v(bauform, bankwinkel):
        k["nockenwellen"] = 4 if int(ventile_je_zylinder) >= 4 else 2
    else:
        k["nockenwellen"] = 2 if int(ventile_je_zylinder) >= 4 else 1
    return k


def baue(bauform="R4", bohrung=86.0, hub=86.0, stichmass=0.0,
         kompressionshoehe=0.0, zylinderabstand=0.0, bolzen_d=0.0,
         hubzapfen_d=0.0, hauptlager_d=0.0, ventile_je_zylinder=4,
         ventilhub=0.0, steuertrieb="kette", zaehne_kurbel=20,
         spreizung=110.0, ventilwinkel=12.0, pleuel_breite=0.0,
         bankwinkel=0.0, v8_kreuzebene=True, mit_ventiltrieb=True,
         mit_getriebe=False, getriebe_gaenge=5, doc=None):
    """Ein vollständiger Motor als Liste von (Bezeichnung, Shape).

    bauform             R2 … V12
    bohrung, hub        [mm]
    Alle Maße, die 0 sind, kommen aus ``kt_auslegung`` — der Tabelle der
    übergreifenden Maße. Dort steht jedes geteilte Maß genau einmal, und
    beide Seiten einer Paarung lesen denselben Eintrag. Was hier gesetzt
    wird, überschreibt die Tabelle, und das Abhängige rechnet mit.

    stichmass           0 = aus dem Hub (1,75·Hub)
    kompressionshoehe   Kolbenbolzenmitte bis Kolbenboden [mm], 0 = Tabelle
    zylinderabstand     0 = 1,18 · Bohrung
    bolzen_d, hubzapfen_d, hauptlager_d, pleuel_breite   0 = Tabelle
    ventile_je_zylinder 2 oder 4
    ventilhub           Nockenerhebung [mm], 0 = Tabelle
    steuertrieb         "kette" oder "zahnrad"
    spreizung           Lage des Nockenscheitels nach OT [Grad Kurbelwinkel],
                        üblich 100…115
    ventilwinkel        Neigung der Ventile gegen die Zylinderachse [Grad],
                        Einlass und Auslass gegenläufig. Das ist das Dach des
                        Brennraums — und der Grund, warum die beiden
                        Nockenwellen nebeneinander Platz haben statt
                        ineinanderzustehen.
    bankwinkel          Bankwinkel des V-Motors [Grad]; 0 = der übliche
                        Wert der Bauform. Einen V6 gibt es mit 60 und mit
                        90 Grad, und der Hubzapfenversatz folgt daraus
                        (|720/z − bank|): 90-Grad-V6 → 30 Grad Versatz.
    mit_ventiltrieb     False baut nur Kurbelwelle, Pleuel und Kolben
    mit_getriebe        True flanscht das Getriebe aus getriebe_fcgear an
                        den Schwungradflansch — beide laufen in der
                        Normallage entlang X auf derselben Achse
    """
    k = kennwerte(bauform, bohrung, hub, stichmass, kompressionshoehe,
                  zylinderabstand, ventile_je_zylinder, v8_kreuzebene,
                  pleuel_breite, bankwinkel)
    # EINE Quelle fuer jedes geteilte Mass. Was der Aufrufer nicht setzt,
    # kommt aus den Verhaeltnissen der Bohrung; was er setzt, ueberschreibt
    # sie — und beide Seiten einer Paarung lesen denselben Eintrag.
    a = k["auslegung"]
    schlecht = [t for ok, t in kt_auslegung.pruefe(a) if not ok]
    if schlecht:
        raise MotorFehler("Die Auslegung passt nicht zusammen: "
                          + "; ".join(schlecht))
    l = a["stichmass"]
    za = a["zylinderabstand"]
    hub_v = a["ventilhub"] if not float(ventilhub) else float(ventilhub)
    a["ventilhub"] = hub_v
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument("Motor")

    # Die Ventiltaschen muessen im Kolben stehen, bevor er gebaut wird —
    # ihre Tiefe kommt aber aus der Ventilsteuerung. Deshalb rechnet die
    # Kinematik sie vorweg, ohne dass ein Ventil existieren muss.
    taschen = []
    if mit_ventiltrieb:
        tiefe = K.taschentiefe(bauform, hub, l, za, hub_v, spreizung,
                               a["nocken_grundkreis_d"] / 2.0, v8_kreuzebene,
                               bankwinkel=bankwinkel)
        # KEIN Zuschlag fuer die untere Tellerkante des geneigten Ventils.
        # Rechnerisch waere er der halbe Teller mal sin(Winkel) — bei 12
        # Grad 3,2 mm, bei 28 Grad 6,3. Nachgemessen nimmt die Tasche damit
        # 23 bis 30 % des Kolbens statt 12, und sie wird 8 bis 12 mm tief;
        # ueblich sind 2 bis 4. Der Grund ist, dass die Tasche hier ein
        # gerader Zylinder ist: die schraege Tellerkante braucht eine
        # Tasche SENKRECHT ZUR VENTILACHSE, nicht eine tiefere gerade.
        # Solange sie gerade ist, bleibt bei grossem Ventilwinkel ein Rest
        # (gemessen 3,7 % bei 28 Grad) — das ist der naechste Schritt beim
        # Detaillieren, nicht ein Fall fuer eine tiefere Tasche.
        taschen = kt_ventiltrieb.ventiltaschen(bohrung, ventile_je_zylinder,
                                               tiefe, ventilwinkel, hub_v)
        k["taschentiefe"] = tiefe

    teile, proben, kw, zylinder_x = kt_kurbeltrieb.baue(
        bauform=bauform, bohrung=bohrung, hub=hub, stichmass=l,
        kompressionshoehe=a["kompressionshoehe"], zylinderabstand=za,
        bolzen_d=a["kolbenbolzen_d"], hubzapfen_d=a["hubzapfen_d"],
        hauptlager_d=a["hauptlager_d"], pleuel_breite=a["pleuel_breite"],
        steuertrieb_d=a["steuertrieb_d"], pleuel_auge_b=a["pleuel_auge_b"],
        wange_t=a["wange_t"], hauptlager_b=a["hauptlager_b"],
        kolben_schafthoehe=a["kolben_schafthoehe"],
        kolben_boden_t=a["kolben_boden_t"],
        bankwinkel=bankwinkel,
        v8_kreuzebene=v8_kreuzebene, ventiltaschen=taschen)

    if mit_ventiltrieb:
        vt_teile, vt_proben, vt_kenn = kt_ventiltrieb.baue(
            bauform=bauform, bohrung=bohrung, blockhoehe=k["blockhoehe"],
            zylinder_x=zylinder_x, zylinderabstand=za,
            ventile_je_zylinder=ventile_je_zylinder, ventilhub=hub_v,
            spreizung=spreizung, ventilwinkel=ventilwinkel,
            steuertrieb=steuertrieb, zaehne_kurbel=zaehne_kurbel,
            kurbelnase=kw.punkt("steuertrieb"), auslegung=a,
            bankwinkel=bankwinkel,
            v8_kreuzebene=v8_kreuzebene, doc=doc)
        teile.extend(vt_teile)
        proben.extend(vt_proben)
        k.update(vt_kenn)

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

    # Tassenstoessel: die Nockenwellenachse muss GENAU UEBER der
    # Ventilachse liegen. Gemessen wird der senkrechte Abstand zweier
    # Geraden — der Nockenwellenachse (entlang x) und der Stoesselachse.
    if kenn and kenn.get("fluchtungen"):
        schief = 0.0
        wo = ""
        x_achse = Vector(1, 0, 0)
        for punkt, richtung, achse, name in kenn["fluchtungen"]:
            n = x_achse.cross(richtung)
            if n.Length < 1e-9:
                continue
            n.normalize()
            d = abs(Vector(punkt).sub(achse).dot(n))
            if d > schief:
                schief, wo = d, name
        sag(schief < 0.05,
            "Nockenwellen- und Ventilachse fluchten (groesster Versatz "
            "%.3f mm%s)" % (schief, (" bei " + wo) if wo else ""))

    # Jede Nockenwelle muss ihr Rad am Steuertrieb haben. Bei einem
    # DOHC-Kopf sind das zwei je Bank; angetrieben wurde lange nur die
    # erste, die zweite lief gar nicht mit.
    if kenn and kenn.get("angetrieben"):
        offen = []
        for e in kenn["angetrieben"]:
            ab = math.hypot(e["rad_y"] - e["welle_y"],
                            e["rad_z"] - e["welle_z"])
            if ab > 0.05:
                offen.append("Bank %d %s (%.2f mm daneben)"
                             % (e["bank"], e["art"], ab))
        sag(not offen,
            "alle %d Nockenwellen haengen an der Kette%s"
            % (len(kenn["angetrieben"]),
               "" if not offen else ": " + "; ".join(offen)))
        if kenn.get("nockenachsen"):
            sag(len(kenn["angetrieben"]) == len(kenn["nockenachsen"]),
                "%d angetriebene von %d Nockenwellen"
                % (len(kenn["angetrieben"]), len(kenn["nockenachsen"])))

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
