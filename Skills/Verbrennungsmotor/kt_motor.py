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
import Part
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


#: Primäruntersetzung eines Motorradmotors — Kurbelwelle auf
#: Getriebeeingangswelle. Üblich 1,6 bis 2,2.
PRIMAER_I = 1.9

#: Lage der Getriebeeingangswelle, gemessen von +Z (senkrecht über der
#: Kurbelwelle) in Richtung +Y. 135° heißt: nach hinten und nach unten —
#: dorthin, wo beim Motorrad der Platz ist.
PRIMAER_WINKEL = 135.0


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
         mit_getriebe=False, getriebe_gaenge=5, getriebe_welle_d=0.0,
         getriebe_modul=0.0, getriebe_zaehne_summe=0,
         getriebe_drehung=None, getriebe_lage="laengs", primaer_i=PRIMAER_I,
         primaer_winkel=PRIMAER_WINKEL, kettenrad_z=17,
         mit_kupplung=False, kupplung_scheiben=0, doc=None):
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
    getriebe_lage       "laengs" — Getriebe hinter dem Motor auf der
                        Kurbelwellenachse (Auto, längs eingebaut).
                        "parallel" — Getriebe NEBEN dem Motor, Achsen
                        parallel zur Kurbelwelle, angetrieben über ein
                        Zahnradpaar (Motorrad). Der Motor steht dort quer
                        im Rahmen, seine Kurbelwellenachse ist die Breite
                        des Fahrzeugs; das Getriebe darf axial nicht über
                        ihn hinausragen.
    primaer_i           Primäruntersetzung Kurbelwelle → Getriebe
    primaer_winkel      Lage der Eingangswelle, von +Z nach +Y [Grad]
    kettenrad_z         Zähne des Abtriebskettenrades
    mit_kupplung        True setzt die Einscheiben- oder
                        Zweischeibenkupplung aus Tools/kupplung.py an den
                        Schwungradflansch; das Getriebe rückt dann um ihre
                        Baulänge nach hinten
    kupplung_scheiben   1 oder 2; 0 = aus dem Hubraum entscheiden
    mit_getriebe        True flanscht das Getriebe aus getriebe_fcgear an
                        den Schwungradflansch — beide laufen in der
                        Normallage entlang X auf derselben Achse. Seine
                        Maße wachsen mit dem Hubraum (siehe
                        ``getriebe_auslegung``); getriebe_welle_d,
                        getriebe_modul und getriebe_zaehne_summe
                        überschreiben sie.
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

    # Die Zentrierbohrung im Schwungradflansch nimmt die Nase der
    # Getriebeeingangswelle auf; ihr Durchmesser folgt also dem Getriebe.
    zentrier_d = 0.0
    flansch_d = flansch_t = 0.0
    if mit_kupplung or mit_getriebe:
        g_vor = getriebe_auslegung(
            k["hubraum_cm3"], getriebe_welle_d, getriebe_modul,
            getriebe_zaehne_summe, getriebe_gaenge)
        zentrier_d = round(g_vor["welle_d"] + 1.0, 1)
        if str(getriebe_lage) == "parallel":
            # Ein MOTORRAD hat keinen Schwungradflansch. Am hinteren
            # Kurbelwellenende sitzt das Primaerritzel, und der 110-mm-
            # Flansch stand genau dort — gemessen 88,7 % Durchdringung
            # zwischen Ritzel und Kurbelwelle. An seine Stelle kommt ein
            # Zapfen vom Durchmesser des Hauptlagers, lang genug fuer das
            # Ritzel und seine Anlage.
            flansch_d = a["hauptlager_d"]
            flansch_t = round(g_vor["breite"] + 6.0, 1)
    teile, proben, kw, zylinder_x = kt_kurbeltrieb.baue(
        bauform=bauform, bohrung=bohrung, hub=hub, stichmass=l,
        kompressionshoehe=a["kompressionshoehe"], zylinderabstand=za,
        bolzen_d=a["kolbenbolzen_d"], hubzapfen_d=a["hubzapfen_d"],
        hauptlager_d=a["hauptlager_d"], pleuel_breite=a["pleuel_breite"],
        steuertrieb_d=a["steuertrieb_d"], pleuel_auge_b=a["pleuel_auge_b"],
        wange_t=a["wange_t"], hauptlager_b=a["hauptlager_b"],
        kolben_schafthoehe=a["kolben_schafthoehe"],
        kolben_boden_t=a["kolben_boden_t"],
        kolben_feuersteg=a["kolben_feuersteg"],
        kolben_ringsteg=a["kolben_ringsteg"],
        kolben_desachsierung=a["kolben_desachsierung"],
        flansch_d=flansch_d, flansch_t=flansch_t,
        zentrier_d=zentrier_d, bankwinkel=bankwinkel,
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

    kupplung_l = 0.0
    glocke_d = 0.0
    if mit_kupplung or mit_getriebe:
        g_soll = getriebe_auslegung(k["hubraum_cm3"], getriebe_welle_d,
                                    getriebe_modul, getriebe_zaehne_summe,
                                    getriebe_gaenge)
        if mit_kupplung:
            k_teile, kupplung_l = _kupplung_anflanschen(
                kw.punkt("abtrieb"), k, doc, g_soll["welle_d"],
                kupplung_scheiben)
            teile.extend(k_teile)
            # Die Glocke muss das groesste Teil der Kupplung umschliessen —
            # den Kupplungsdeckel bzw. das Schwungrad.
            glocke_d = max(k["kupplung"]["schwungrad_d"] + 14.0,
                           k["kupplung"]["belag_d"] + 40.0) + 20.0
    if mit_getriebe and str(getriebe_lage) == "parallel":
        # Motorrad: das Getriebe liegt NEBEN dem Motor und wird ueber ein
        # Zahnradpaar angetrieben, das zugleich die Vorgelegestufe ist.
        m_von = min(sh.BoundBox.XMin for _n, sh in teile)
        m_bis = max(sh.BoundBox.XMax for _n, sh in teile)
        teile.extend(_getriebe_parallel(
            kw, k, doc, getriebe_gaenge, getriebe_welle_d, getriebe_modul,
            getriebe_zaehne_summe, primaer_i, primaer_winkel, kettenrad_z,
            motor_von=m_von, motor_bis=m_bis))
    elif mit_getriebe:
        # MIT Kupplung waechst die Glocke um deren Baulaenge nach vorn, und
        # das Getriebe selbst rueckt nicht weg: die Antriebswelle laeuft
        # durch die Glocke bis ins Schwungrad, und die Kupplungsscheiben
        # sitzen auf ihr. Ohne Glocke stuende das Getriebe hinter der
        # Kupplung, statt sie zu tragen.
        teile.extend(_getriebe_anflanschen(
            kw.punkt("abtrieb"), k, doc, getriebe_gaenge,
            getriebe_welle_d, getriebe_modul, getriebe_zaehne_summe,
            getriebe_drehung, versatz_x=0.0,
            glocke_l=kupplung_l, glocke_d=glocke_d))
    return teile, k, proben


#: Normmodule nach DIN 780, Reihe 1. Ein Getriebe wird nicht mit Modul
#: 2,87 gebaut.
MODULE = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)

#: Bezugspunkt der Getriebeauslegung: ein 2,0-Liter-Motor bekommt eine
#: 20-mm-Eingangswelle und 72 mm Achsabstand. Daran haengt alles Weitere.
BEZUG_HUBRAUM = 2000.0
BEZUG_WELLE = 20.0

#: Achsabstand als Vielfaches des Wellendurchmessers. 3,6 trifft das
#: Pkw-Schaltgetriebe: 20 mm Welle, 72 mm Achsabstand.
ACHSABSTAND_JE_WELLE = 3.6

#: Kleinste Zaehnezahl im Getriebe. Unter 17 unterschneidet ein
#: 20-Grad-Evolventenrad, und der Kopf des Gegenrades graebt sich in den
#: Fuss — gemessen an einem Paar 12/57: 5,9 % Durchdringung.
Z_MIN = 17

#: Zahnbreite als Vielfaches des Moduls. 6 ist die untere Grenze; ein
#: Fahrzeuggetriebe legt seine Raeder mit b/m = 8 bis 10 aus, weil die
#: Zahnbreite unmittelbar die uebertragbare Kraft ist.
ZAHNBREITE_JE_MODUL = 8.0

#: Luft zwischen zwei Radpaaren als Vielfaches der Zahnbreite. Das ist kein
#: Freigang, sondern der Platz fuer die SCHALTMUFFE — dort sitzt beim
#: richtigen Getriebe die Synchroneinheit. Mit festen 6 mm war ein Gang nur
#: 24 mm lang, und das ganze Getriebe 223 mm gegen 728 mm Motor.
LUFT_JE_BREITE = 1.8

#: Drehung des Getriebes um die Kurbelwellenachse [Grad]. Die Vorgelegewelle
#: entsteht in +Y, also SEITLICH neben der Eingangswelle — dort steht bei
#: einem V-Motor die Bank. Sie gehoert auf die Achse senkrecht dazu, und
#: +90 Grad um X bringt sie dahin: (0, 1, 0) wird zu (0, 0, 1).
DREHUNG = 90.0


def getriebe_auslegung(hubraum_cm3, welle_d=0.0, modul=0.0, zaehne_summe=0,
                       gaenge=5):
    """Die Maße des Getriebes, passend zum Motor.

    Das Getriebe hat lange feste 20 mm Welle und Modul 2 bekommen, gleich ob
    davor ein Zweiliter-Vierzylinder oder ein Sechsliter-V12 stand. Das ist
    keine Auslegung, sondern ein Zufall.

    Was ein Getriebe wirklich bestimmt, ist das **Drehmoment**, und das geht
    im ersten Zugriff mit dem Hubraum. Eine Welle auf Torsion ausgelegt
    braucht ``d ∝ T^(1/3)``, also:

        d = 20 mm · (V_H / 2000 cm³)^(1/3)

    Ein Sechsliter bekommt damit 20 · 3^(1/3) = 28,8 mm statt 20. Der
    **Modul** folgt der Welle (rund ein Zehntel) und wird auf die Normreihe
    DIN 780 gerundet; die **Zahnbreite** ist das Sechsfache des Moduls.

    Der **Achsabstand** wächst mit: 3,6 · Wellendurchmesser, also 72 mm beim
    Zweiliter und 104 beim Sechsliter. Vorher stand er fest auf 48 mm — das
    ist selbst für den Zweiliter zu wenig, ein Pkw-Schaltgetriebe liegt bei
    70 bis 75. Aus Achsabstand und Modul folgt die **Zähnesumme**
    ``z1 + z2 = 2a/m``, und die ist es, die die Räder groß macht.

    Was ein Getriebe **lang** macht, ist nicht das Rad, sondern was zwischen
    den Rädern sitzt. Die Zahnbreite ist jetzt das Achtfache des Moduls
    (b/m = 8 ist Fahrzeugpraxis, 6 war die untere Grenze), und die Lücke
    zwischen zwei Radpaaren das 1,8-fache der Zahnbreite — dort sitzt die
    **Schaltmuffe**. Mit festen 6 mm Lücke war ein Gang 24 mm lang und das
    ganze Sechsganggetriebe 223 mm, gegen 728 mm Motor.

    Wand, Schraube und Lagerreihe folgen der Welle, damit das Gehäuse zum
    Inhalt passt.

    Das ist eine Faustformel und wird auch so genannt: sie ersetzt keine
    Zahnfußrechnung. Sie sorgt dafür, dass ein großer Motor kein
    Spielzeuggetriebe bekommt.
    """
    v = max(1.0, float(hubraum_cm3))
    d = float(welle_d) or round(BEZUG_WELLE * (v / BEZUG_HUBRAUM) ** (1.0 / 3.0), 1)
    m = float(modul)
    if not m:
        roh = d / 10.0
        m = min(MODULE, key=lambda x: abs(x - roh))
    breite = round(ZAHNBREITE_JE_MODUL * m, 1)
    luft = round(LUFT_JE_BREITE * breite, 1)
    if int(zaehne_summe) > 0:
        zsum = int(zaehne_summe)
    else:
        zsum = int(round(2.0 * ACHSABSTAND_JE_WELLE * d / m))
        # gangpaare() braucht Luft nach unten: Z_MIN je Rad, dazu je Gang
        # eine Stufe.
        zsum = max(zsum, 2 * Z_MIN + 2 * max(1, int(gaenge) - 1) + 2)
    return {
        "welle_d": d,
        "modul": m,
        "breite": breite,
        "luft": luft,
        "zaehne_summe": zsum,
        "achsabstand": round(m * zsum / 2.0, 2),
        "wand": round(max(4.0, 0.22 * d), 1),
        "schraube_d": round(max(6.0, 0.28 * d), 1),
        "lager_reihe": "63" if d >= 25.0 else "62",
        "z_min": Z_MIN,
        # Laengs eingebauter Motor: der Abtrieb muss dorthin zurueck, wo der
        # Antrieb herkommt. Das kann nur das Vorgelegegetriebe — Antriebs-
        # und Hauptwelle auf EINER Achse, die Vorgelegewelle darunter.
        "bauart": "vorgelege",
        "drehung": DREHUNG,
        "hubraum_cm3": round(v, 1),
    }


def _kupplung_anflanschen(abtrieb, k, doc, welle_d, scheiben=0):
    """Die Kupplung aus Tools/kupplung.py an den Schwungradflansch setzen.

    Sie wird entlang +X gebaut, x = 0 ist ihre Schwungradrückseite — also
    genau die Fläche, die am Flansch anliegt. Es genügt eine Verschiebung.

    Zurück kommt ``(teile, laenge)``; um ``laenge`` rückt das Getriebe nach
    hinten, denn die Kupplung sitzt zwischen beiden. Ohne diese Verschiebung
    stünde das Getriebe mitten in der Kupplung.
    """
    import kupplung as KU

    teile, a = KU.baue(hubraum_cm3=k.get("hubraum_cm3", 2000.0),
                       getriebewelle_d=float(welle_d),
                       flansch_d=float(abtrieb.mass),
                       scheiben=scheiben, doc=doc)
    versatz = FreeCAD.Vector(abtrieb.ort.x, 0.0, 0.0)
    aus = []
    laenge = 0.0
    for label, shp in teile:
        kopie = shp.copy()
        kopie.translate(versatz)
        laenge = max(laenge, kopie.BoundBox.XMax - abtrieb.ort.x)
        aus.append(("Kupplung: " + label, kopie))
    a["anschluss_x"] = round(abtrieb.ort.x, 2)
    a["laenge"] = round(laenge, 2)
    a["teile"] = len(aus)
    k["kupplung"] = a
    return aus, laenge


def _getriebe_parallel(kw, k, doc, gaenge=6, welle_d=0.0, modul=0.0,
                       zaehne_summe=0, primaer_i=PRIMAER_I,
                       primaer_winkel=PRIMAER_WINKEL, kettenrad_z=17,
                       motor_von=None, motor_bis=None):
    """Das Getriebe eines **Motorrads**: parallel zur Kurbelwelle.

    Beim längs eingebauten Automotor liegt das Getriebe hinter dem Motor auf
    derselben Achse. Beim Motorrad geht das nicht: der Motor steht quer im
    Rahmen, seine Kurbelwellenachse ist die **Breite** des Fahrzeugs, und
    was dort hinausragt, ragt seitlich heraus. Das Getriebe liegt deshalb
    **parallel daneben** — hinter und unter der Kurbelwelle, im Schatten des
    Motors — und darf axial nicht über ihn hinausstehen.

    Der Antrieb ist ein **Zahnradpaar**, der Primärtrieb:

        Kurbelwelle --(Primärritzel z1 / Primärrad z2)--> Eingangswelle

    Und dieses Paar ist zugleich die **Vorgelegestufe** — anders als beim
    Auto braucht es keine eigene Antriebskonstante im Getriebe. Deshalb ist
    das Getriebe hier ein **Zweiwellengetriebe**: je Gang ein Radpaar
    zwischen Eingangs- und Abtriebswelle, und die Gesamtübersetzung ist

        i = i_primär · (z_Losrad / z_Festrad)

    Am Ausgang sitzt kein Flansch, sondern ein **Kettenrad**: von dort geht
    die Kette zum Hinterrad.
    """
    import getriebe_fcgear as GF
    import kt_steuertrieb

    g = getriebe_auslegung(k.get("hubraum_cm3", BEZUG_HUBRAUM), welle_d,
                           modul, zaehne_summe, gaenge)
    g["bauart"] = "zweiwellen"
    g["lage"] = "parallel"

    # --- Primaertrieb -----------------------------------------------------
    # Der Achsabstand ist NICHT frei waehlbar: die Getriebewellen laufen
    # neben der Kurbelwelle, und dazwischen muessen die KURBELWANGEN und
    # das groesste Getrieberad aneinander vorbei. Mit einem fest gewaehlten
    # Zaehnepaar kam ein Abstand von 40 mm heraus, bei 42 mm Wangenradius —
    # das Getriebelager stak zu 100 % in der Kurbelwelle.
    a = k["auslegung"]
    r_wange = a["kurbelradius"] + a["hubzapfen_d"] / 2.0 + 2.0
    m_p = g["modul"]
    z_max_getriebe = g["zaehne_summe"] - g["z_min"]
    r_getrieberad = m_p * (z_max_getriebe + 2) / 2.0
    a_min = r_wange + r_getrieberad + 6.0
    # Zaehnezahlen aus dem noetigen Abstand, bei festgehaltener Uebersetzung.
    z_summe = max(int(math.ceil(2.0 * a_min / m_p)), 40)
    z1 = max(17, int(round(z_summe / (1.0 + float(primaer_i)))))
    z2 = z_summe - z1
    a_p = m_p * (z1 + z2) / 2.0
    # Das Kurbelwellenende: dort sitzt das Ritzel.
    nase = kw.punkt("abtrieb")
    w = math.radians(float(primaer_winkel))
    richtung = Vector(0.0, math.sin(w), math.cos(w))
    mitte = Vector(richtung).multiply(a_p)
    g["primaer"] = {"zaehne": [z1, z2], "i": round(z2 / float(z1), 4),
                    "modul": m_p, "achsabstand": round(a_p, 2),
                    "mindestabstand": round(a_min, 2),
                    "wangenradius": round(r_wange, 2),
                    "winkel": float(primaer_winkel)}

    teile = []

    # --- Das Getriebe selbst ---------------------------------------------
    roh = GF.baue(bauart="zweiwellen", gaenge=int(gaenge),
                  welle_d=g["welle_d"], modul=g["modul"], breite=g["breite"],
                  luft=g["luft"], zaehne_summe=g["zaehne_summe"],
                  wand=g["wand"], schraube_d=g["schraube_d"],
                  z_min=g["z_min"], lager_reihe=g["lager_reihe"], doc=doc)

    def spanne(passt):
        kaesten = [sh.BoundBox for n, sh in roh if passt(n)]
        return min(b.XMin for b in kaesten), max(b.XMax for b in kaesten)

    geh_von, geh_bis = spanne(lambda n: "Gehaeuse" in n)
    ein_von, ein_bis = spanne(lambda n: n.startswith("Eingangswelle"))
    ab_von, ab_bis = spanne(lambda n: n.startswith("Ausgangswelle"))
    ganz_von, ganz_bis = spanne(lambda n: True)

    # Am GANZEN Motor ausrichten und am GANZEN Getriebe messen. Vorher kam
    # der eine Wert von den Wellen und der andere von der Kurbelwelle, und
    # das Getriebe stand 6 mm vorn heraus — heraus heisst beim Motorrad:
    # breiter.
    mv = float(motor_von) if motor_von is not None \
        else kw.koerper[0][1].BoundBox.XMin
    mb = float(motor_bis) if motor_bis is not None else nase.ort.x
    motor_x = (mv, mb)

    # Das Primaerradpaar sitzt HINTEN, buendig mit dem Kurbelwellenende:
    # auf der Kurbelwelle das Ritzel (auf dem Zapfen, der beim Motorrad an
    # die Stelle des Schwungradflansches tritt), auf der Getriebeseite das
    # Rad auf der verlaengerten Eingangswelle.
    x_prim = nase.ort.x - g["breite"]
    # Das Getriebegehaeuse muss davor enden, sonst laeuft das Primaerrad
    # (Kopfkreis 58 mm) in die Gehaeusestirnwand.
    versatz_x = min(x_prim - 3.0 - geh_bis, mb - ganz_bis)
    versatz_x = max(versatz_x, mv - ganz_von)

    # Die Abtriebswelle endet an der Gehaeusewand: ihr Ende laege sonst in
    # der Ebene des Primaerrades, und das ist mit 114 mm Durchmesser breiter
    # als der Wellenabstand von 48 mm — gemessen 2,7 % Durchdringung. Am
    # Motorrad hat diese Welle dort auch nichts zu suchen, das Kettenrad
    # sitzt auf der anderen Seite.
    # Der Schnitt trifft die Welle, SOLANGE SIE NOCH IM URSPRUNG STEHT —
    # also bei geh_bis, nicht bei versatz_x + geh_bis. Mit dem globalen Wert
    # lag der Kasten 103 mm hinter der Welle und nahm nichts weg; die
    # Durchdringung blieb auf 2,7 %, was den Fehler verriet.
    kappen = Part.makeBox(400.0, 400.0, 400.0,
                          Vector(geh_bis, -200.0, -200.0))
    for label, shp in roh:
        kopie = shp.copy()
        if label.startswith("Ausgangswelle"):
            kopie = kopie.cut(kappen)
        kopie.rotate(Vector(0, 0, 0), Vector(1, 0, 0),
                     float(primaer_winkel) - 90.0)
        kopie.translate(Vector(versatz_x, mitte.y, mitte.z))
        teile.append(("Getriebe: " + label, kopie))

    # --- Primaertrieb -----------------------------------------------------
    # Das Ritzel laeuft auf dem Kurbelwellenzapfen, nicht auf einer
    # Getriebewelle: seine Bohrung ist die des Hauptlagers.
    for zahl, ort, bohrung, label in (
            (z1, Vector(0, 0, 0), a["hauptlager_d"] + 0.2,
             "Primaerritzel (z=%d)" % z1),
            (z2, mitte, g["welle_d"], "Primaerrad (z=%d)" % z2)):
        shp, _d, _da = GF.zahnrad(doc, zahl, m_p, g["breite"], bohrung)
        rad = shp.copy()
        rad.rotate(Vector(0, 0, 0), Vector(0, 1, 0), 90)
        if zahl == z2:
            # Halbe Zahnteilung Phase, sonst stossen die Zaehne aufeinander.
            rad.rotate(Vector(0, 0, 0), Vector(1, 0, 0), 180.0 / zahl)
        rad.translate(Vector(x_prim, ort.y, ort.z))
        teile.append(("Primaertrieb: " + label, rad))

    def wellenstueck(von, bis, achse, name):
        """Ein Stueck Welle zwischen Getriebe und dem, was daneben sitzt.

        Primaerrad und Kettenrad muessen axial NEBEN dem Gehaeuse stehen,
        die Wellen enden aber nur 8 mm hinter seiner Wand. Was fehlt, ist
        ein Stueck Welle — auf dem Motorrad traegt genau dieser Ueberhang
        den Kupplungskorb bzw. das Kettenrad.
        """
        if bis - von < 0.2:
            return
        teile.append((name, Part.makeCylinder(
            g["welle_d"] / 2.0, bis - von, Vector(von, achse.y, achse.z),
            Vector(1, 0, 0))))

    wellenstueck(versatz_x + ein_bis, x_prim + g["breite"], mitte,
                 "Getriebe: Eingangswelle Primaerueberhang")

    # --- Kettenrad am Abtrieb --------------------------------------------
    # Kein Flansch, sondern ein Kettenrad: von hier geht die Kette zum
    # Hinterrad. Es sitzt VORN, auf der anderen Seite als der Primaertrieb —
    # so wie am Motorrad die Kette links und die Kupplung rechts liegt.
    teilung = 15.875                      # 5/8", uebliche Motorradkette
    d_kr, _da = kt_steuertrieb.kettenradmasse(int(kettenrad_z), teilung)
    quer = FreeCAD.Rotation(Vector(1, 0, 0),
                            float(primaer_winkel) - 90.0).multVec(
                                Vector(0.0, g["achsabstand"], 0.0))
    kr_mitte = Vector(mitte.x + quer.x, mitte.y + quer.y, mitte.z + quer.z)
    kr_b = 10.0
    x_kr = max(mv + 2.0, versatz_x + geh_von - 3.0 - kr_b)
    kette = Part.makeCylinder((d_kr - teilung * 2.0 / 3.0) / 2.0, kr_b,
                              Vector(x_kr, kr_mitte.y, kr_mitte.z),
                              Vector(1, 0, 0))
    kette = kette.cut(Part.makeCylinder(
        g["welle_d"] / 2.0 + 0.1, kr_b + 4.0,
        Vector(x_kr - 2.0, kr_mitte.y, kr_mitte.z), Vector(1, 0, 0)))
    teile.append(("Abtrieb: Kettenrad (z=%d, %.3f mm Teilung)"
                  % (int(kettenrad_z), teilung), kette))
    wellenstueck(x_kr, versatz_x + ab_von, kr_mitte,
                 "Getriebe: Ausgangswelle Kettenradueberhang")
    g["kettenrad"] = {"zaehne": int(kettenrad_z), "teilung": teilung,
                      "teilkreis": round(d_kr, 2)}
    g.update({"gaenge": int(gaenge), "teile": len(teile),
              "x_von": round(min(s.BoundBox.XMin for _n, s in teile), 1),
              "x_bis": round(max(s.BoundBox.XMax for _n, s in teile), 1)})
    # Gesamtuebersetzung: Primaer mal Gangpaar.
    import getriebe_auslegung as GA
    paare = GA.gangpaare(g["zaehne_summe"], int(gaenge), g["z_min"])
    g["uebersetzungen"] = [round(g["primaer"]["i"] * i, 3)
                           for _z1, _z2, i in paare]
    k["getriebe"] = g
    return teile


def _getriebe_anflanschen(abtrieb, k, doc, gaenge=5, welle_d=0.0, modul=0.0,
                          zaehne_summe=0, drehung=None, versatz_x=0.0,
                          glocke_l=0.0, glocke_d=0.0):
    """Das Getriebe aus Tools/getriebe_fcgear.py hinter den Motor setzen.

    Beide laufen in der Normallage entlang X mit der Welle auf y = z = 0 —
    es genuegt also eine Verschiebung. Der Anschluss ist der
    Schwungradflansch der Kurbelwelle; dort beginnt die Eingangswelle des
    Getriebes.

    Die Maße kommen aus ``getriebe_auslegung()`` und wachsen mit dem
    Hubraum; was hier gesetzt wird, ueberschreibt sie.
    """
    import getriebe_fcgear as GF

    g = getriebe_auslegung(k.get("hubraum_cm3", BEZUG_HUBRAUM), welle_d,
                           modul, zaehne_summe, gaenge)
    if drehung is not None:
        g["drehung"] = float(drehung)
    teile = GF.baue(gaenge=int(gaenge), welle_d=g["welle_d"],
                    modul=g["modul"], breite=g["breite"], luft=g["luft"],
                    zaehne_summe=g["zaehne_summe"], wand=g["wand"],
                    schraube_d=g["schraube_d"], z_min=g["z_min"],
                    bauart=g["bauart"], glocke_l=float(glocke_l),
                    glocke_d=float(glocke_d),
                    lager_reihe=g["lager_reihe"], doc=doc)
    konstante, gangpaare = GF.gangpaare_vorgelege(
        g["zaehne_summe"], int(gaenge), g["z_min"])
    g["konstante"] = {"zaehne": [konstante[0], konstante[1]],
                      "i": round(konstante[2], 4)}
    g["uebersetzungen"] = [round(i, 3) for _f, _l, i in gangpaare] + [1.0]
    # Wo faengt die Eingangswelle des Getriebes in seinem eigenen Bild an?
    wellen = [s for n, s in teile if "welle" in n.lower()]
    if not wellen:
        return []
    # Mit Glocke ist deren VORDERSTE Ebene die Anschlussflaeche zum Motor,
    # nicht das Wellenende: dort liegt ihr Flansch am Block an. Ohne Glocke
    # bleibt es die Welle.
    glocke = [s for n, s in teile if n == "Kupplungsglocke"]
    if glocke:
        anfang = glocke[0].BoundBox.XMin
    else:
        anfang = min(s.BoundBox.XMin for s in wellen)
    versatz = FreeCAD.Vector(abtrieb.ort.x + float(versatz_x) - anfang,
                             0.0, 0.0)
    # Erst DREHEN, dann schieben: die Drehung geht um die Kurbelwellenachse
    # (x-Achse durch den Ursprung), und die ist im Getriebebild die
    # Eingangswelle. Andersherum wandert die Eingangswelle von der Achse.
    dreh = float(g.get("drehung") or 0.0)
    aus = []
    for label, shp in teile:
        kopie = shp.copy()
        if abs(dreh) > 1e-9:
            kopie.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0),
                         dreh)
        kopie.translate(versatz)
        aus.append(("Getriebe: " + label, kopie))
    g.update({"gaenge": int(gaenge), "teile": len(aus),
              "anschluss_x": round(abtrieb.ort.x + float(versatz_x), 2),
              "glocke_l": round(float(glocke_l), 2),
              "flansch_d": round(abtrieb.mass, 1)})
    k["getriebe"] = g
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

    # Das Getriebe muss zum Motor PASSEN, nicht nur an ihm haengen: seine
    # Eingangswelle folgt dem Drehmoment, und das geht mit dem Hubraum.
    if kenn and kenn.get("getriebe") \
            and kenn["getriebe"].get("lage") != "parallel":
        g = kenn["getriebe"]
        soll = getriebe_auslegung(kenn.get("hubraum_cm3", BEZUG_HUBRAUM))
        sag(abs(g["welle_d"] - soll["welle_d"]) < 0.15 or
            g["welle_d"] >= soll["welle_d"],
            "Getriebewelle %.1f mm zu %.1f cm^3 Hubraum (Vorschlag %.1f)"
            % (g["welle_d"], kenn.get("hubraum_cm3", 0.0), soll["welle_d"]))
        sag(g["modul"] in MODULE,
            "Modul %.2f ist ein Normmodul (DIN 780)" % g["modul"])
        sag(g.get("z_min", 0) >= 17,
            "kleinstes Rad %d Zaehne (ab 17 ohne Profilverschiebung)"
            % g.get("z_min", 0))
        sag(g["breite"] >= 8.0 * g["modul"] - 0.05,
            "Zahnbreite %.1f mm = %.1f x Modul (Fahrzeugpraxis 8…10)"
            % (g["breite"], g["breite"] / g["modul"]))
        # Ein Getriebe, das ein Drittel der Motorlaenge hat, ist keines.
        kasten = [sh for n, sh in teile if n.startswith("Getriebe")]
        motor = [sh for n, sh in teile if not n.startswith("Getriebe")]
        if kasten and motor:
            gl = max(s.BoundBox.XMax for s in kasten) - \
                min(s.BoundBox.XMin for s in kasten)
            ml = max(s.BoundBox.XMax for s in motor) - \
                min(s.BoundBox.XMin for s in motor)
            g["laenge"] = round(gl, 1)
            sag(gl > 0.5 * ml,
                "Getriebe %.0f mm lang zu %.0f mm Motor (%.0f %%)"
                % (gl, ml, 100.0 * gl / ml))
        sag(g["welle_d"] < g["flansch_d"],
            "die Getriebewelle (%.1f) passt in den Schwungradflansch (%.1f)"
            % (g["welle_d"], g["flansch_d"]))
        sag(abs(g["achsabstand"] - soll["achsabstand"]) < 0.5 or
            g["achsabstand"] >= soll["achsabstand"],
            "Achsabstand %.1f mm (Vorschlag %.1f zu %.1f mm Welle)"
            % (g["achsabstand"], soll["achsabstand"], g["welle_d"]))
        # Die eigentliche Zusage des Vorgelegegetriebes: Antriebs- und
        # Hauptwelle liegen auf DERSELBEN Achse. Vorher waren es zwei
        # parallele Wellen ohne gemeinsame Achse — damit kaeme der Abtrieb
        # seitlich heraus, und ein laengs eingebauter Motor braucht ihn
        # hinten auf der Kurbelwellenachse.
        if g.get("bauart") == "vorgelege":
            achsen = {}
            for n, sh in teile:
                for welle in ("Antriebswelle", "Hauptwelle",
                              "Vorgelegewelle"):
                    if n.endswith(welle):
                        b = sh.BoundBox
                        achsen[welle] = ((b.YMin + b.YMax) / 2.0,
                                         (b.ZMin + b.ZMax) / 2.0)
            if "Antriebswelle" in achsen and "Hauptwelle" in achsen:
                an, ha = achsen["Antriebswelle"], achsen["Hauptwelle"]
                ab = math.hypot(an[0] - ha[0], an[1] - ha[1])
                sag(ab < 0.5,
                    "Antriebs- und Hauptwelle liegen auf einer Achse "
                    "(%.2f mm auseinander)" % ab)
                sag(abs(an[0]) < 0.5 and abs(an[1]) < 0.5,
                    "die Antriebswelle liegt auf der Kurbelwellenachse "
                    "(y %.2f, z %.2f)" % an)

        # Die Vorgelegewelle gehoert SENKRECHT ueber oder unter die
        # Kurbelwellenachse, nicht seitlich daneben — dort steht beim
        # V-Motor die Zylinderbank. Gebaut wird sie in +Y; die Drehung um
        # die Kurbelwellenachse bringt sie auf die Senkrechte, und ob nach
        # oben oder unten, ist Sache des Einbaus (DREHUNG).
        wellen_g = [sh for n, sh in teile
                    if n.startswith("Getriebe") and "welle" in n.lower()
                    and "kurbel" not in n.lower()]
        if len(wellen_g) >= 2:
            lagen = [((b.YMin + b.YMax) / 2.0, (b.ZMin + b.ZMax) / 2.0)
                     for b in (sh.BoundBox for sh in wellen_g)]
            vorgelege = max(lagen, key=lambda p: abs(p[0]) + abs(p[1]))
            sag(abs(vorgelege[0]) < 1.0 and
                abs(abs(vorgelege[1]) - g["achsabstand"]) < 1.0,
                "die Vorgelegewelle steht senkrecht zur Kurbelwellenachse "
                "(y %.1f, z %.1f bei %.1f mm Achsabstand)"
                % (vorgelege[0], vorgelege[1], g["achsabstand"]))

    # Motorrad: das Getriebe muss AXIAL im Schatten des Motors bleiben.
    # Die Kurbelwellenachse ist beim Motorrad die Breite des Fahrzeugs —
    # was dort hinausragt, ragt seitlich heraus.
    if kenn and kenn.get("getriebe", {}).get("lage") == "parallel":
        g = kenn["getriebe"]
        motor = [sh for n, sh in teile
                 if not n.startswith(("Getriebe", "Primaertrieb", "Abtrieb"))]
        if motor:
            mx0 = min(sh.BoundBox.XMin for sh in motor)
            mx1 = max(sh.BoundBox.XMax for sh in motor)
            sag(g["x_von"] >= mx0 - 0.5 and g["x_bis"] <= mx1 + 0.5,
                "das Getriebe bleibt axial im Motor (x %.0f…%.0f in "
                "%.0f…%.0f)" % (g["x_von"], g["x_bis"], mx0, mx1))
        sag(abs(g["primaer"]["i"] - g["primaer"]["zaehne"][1]
                / float(g["primaer"]["zaehne"][0])) < 1e-3,
            "Primaertrieb z %d/%d, i = %.3f"
            % (g["primaer"]["zaehne"][0], g["primaer"]["zaehne"][1],
               g["primaer"]["i"]))
        sag(g["primaer"]["achsabstand"]
            >= g["primaer"]["mindestabstand"] - 0.5,
            "Primaerachsabstand %.1f mm (Kurbelwange %.1f + groesstes "
            "Getrieberad, mindestens %.1f)"
            % (g["primaer"]["achsabstand"], g["primaer"]["wangenradius"],
               g["primaer"]["mindestabstand"]))
        sag(bool(g.get("kettenrad")),
            "Abtrieb ist ein Kettenrad (z=%d, Teilkreis %.1f mm)"
            % (g["kettenrad"]["zaehne"], g["kettenrad"]["teilkreis"]))

    # Die Kupplung sitzt ZWISCHEN Motor und Getriebe — sie muss auf der
    # Kurbelwellenachse sitzen, ihre Nabe muss die Getriebeeingangswelle
    # aufnehmen, und das Getriebe darf nicht in ihr stehen.
    if kenn and kenn.get("kupplung"):
        ku = kenn["kupplung"]
        sag(ku["scheiben"] in (1, 2),
            "%s-Kupplung, %d Reibflaechen, Belag %.0f/%.0f mm"
            % (ku["bauart"], ku["reibflaechen"], ku["belag_d"],
               ku["belag_innen_d"]))
        if kenn.get("getriebe"):
            g = kenn["getriebe"]
            sag(abs(ku["getriebewelle_d"] - g["welle_d"]) < 0.05,
                "die Kupplungsnabe (%.1f) nimmt die Getriebewelle (%.1f) auf"
                % (ku["getriebewelle_d"], g["welle_d"]))
            # Die Kupplung sitzt IN der Glocke des Getriebes, und die
            # Antriebswelle laeuft durch ihre Naben.
            sag(g.get("glocke_l", 0.0) >= ku["laenge"] - 0.05,
                "die Kupplungsglocke (%.0f mm) umschliesst die Kupplung "
                "(%.0f mm)" % (g.get("glocke_l", 0.0), ku["laenge"]))
            glocke = [sh for n, sh in teile if n.endswith("Kupplungsglocke")]
            # Das Getriebe besteht aus genau DREI Gehaeuseteilen:
            # Kupplungsglocke, Oberteil, Unterteil. Der Stirnflansch ist
            # kein eigenes Bauteil, sondern gehoert je zur Haelfte an
            # Ober- und Unterteil — sonst liesse er sich nicht anschrauben.
            kasten = [n for n, _sh in teile
                      if n.startswith("Getriebe")
                      and ("Gehaeuse Ober" in n or "Gehaeuse Unter" in n
                           or n.endswith("Kupplungsglocke"))]
            sag(len(kasten) == 3,
                "das Getriebe hat drei Gehaeuseteile: %s"
                % ", ".join(sorted(n.split(": ")[-1] for n in kasten)))
            haelften = [sh for n, sh in teile
                        if n.startswith("Getriebe")
                        and ("Gehaeuse Ober" in n or "Gehaeuse Unter" in n)]
            if glocke and len(haelften) == 2:
                gb = glocke[0].BoundBox
                vorn = max(sh.BoundBox.XMin for sh in haelften)
                sag(abs(vorn - gb.XMax) < 0.5,
                    "beide Gehaeusehaelften reichen mit ihrem Flansch an "
                    "die Glocke (x %.1f gegen %.1f)" % (vorn, gb.XMax))

            # Die Schaltung: je Muffe eine Gabel, je Gabel eine Stange,
            # beidseits ein Synchronring, und unter jedem Losrad ein
            # Nadellager.
            def zaehle(wort):
                return sum(1 for n, _sh in teile
                           if n.startswith("Getriebe") and wort in n)
            muffen = zaehle("Schaltmuffe")
            sag(zaehle("Schaltgabel") == muffen,
                "%d Schaltgabeln zu %d Schaltmuffen"
                % (zaehle("Schaltgabel"), muffen))
            sag(zaehle("Synchronring") == 2 * muffen,
                "%d Synchronringe, zwei je Muffe" % zaehle("Synchronring"))
            sag(zaehle("Schaltstange") >= 1,
                "%d Schaltstangen" % zaehle("Schaltstange"))
            sag(zaehle("Nadellager") == g["gaenge"],
                "%d Nadellager, eines je Losrad"
                % zaehle("Nadellager"))
            naben = [sh for n, sh in teile
                     if "Scheibennabe" in n]
            welle = [sh for n, sh in teile if n.endswith("Antriebswelle")]
            if glocke and naben:
                gb = glocke[0].BoundBox
                drin = all(gb.XMin - 1.0 <= (b.XMin + b.XMax) / 2.0
                           <= gb.XMax + 1.0
                           for b in (s.BoundBox for s in naben))
                sag(drin, "die Kupplungsscheiben liegen in der Glocke "
                          "(x %.0f…%.0f)" % (gb.XMin, gb.XMax))
            if welle and naben:
                wb = welle[0].BoundBox
                durch = all(wb.XMin <= b.XMin and b.XMax <= wb.XMax
                            for b in (s.BoundBox for s in naben))
                sag(durch,
                    "die Antriebswelle (x %.0f…%.0f) traegt alle "
                    "Kupplungsnaben" % (wb.XMin, wb.XMax))
        sag(ku["belag_d"] <= ku["schwungrad_d"],
            "das Schwungrad (%.0f) traegt den Belag (%.0f)"
            % (ku["schwungrad_d"], ku["belag_d"]))

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
