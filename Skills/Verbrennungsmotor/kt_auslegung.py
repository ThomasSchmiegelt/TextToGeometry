# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Auslegung — die Tabelle der übergreifenden Maße.

Ein Maß, das zwei Bauteile brauchen, darf nicht zweimal dastehen. Der
Kolbenbolzendurchmesser steht im Kolben *und* im kleinen Pleuelauge; der
Hubzapfen in der Kurbelwelle *und* im großen Auge; der Steuertriebzapfen in
der Kurbelwelle *und* im Kettenrad. Solange jedes Skript seinen eigenen
Vorgabewert hat, passt es bei 86 mm Bohrung zufällig und bei 120 mm nicht
mehr — und das fällt erst auf, wenn man es nachmisst.

Diese Tabelle ist deshalb die **eine Quelle**: aus Bohrung, Hub und Bauform
folgt jedes übergreifende Maß, und ``kt_motor`` reicht es an beide Seiten
weiter. Was hier nicht steht, ist Sache des einzelnen Bauteils.

Die Verhältnisse sind die üblichen Größen des Motorenbaus, bezogen auf die
Bohrung (bzw. beim Stichmaß auf den Hub). Bei 86 mm Bohrung geben sie genau
die Werte, mit denen dieser Generator entwickelt und vermessen wurde —
Bolzen 22, Hubzapfen 48, Hauptlager 54, Kompressionshöhe 32 mm. Der Gewinn
ist, dass sie jetzt **mitwachsen**.

    a = auslegen(bohrung=120.0, hub=110.0, bauform="V8")
    a["kolbenbolzen_d"]   -> 31.2   (statt fest 22)

Jeder Wert lässt sich überschreiben: ``auslegen(bohrung=86.0,
kolbenbolzen_d=25.0)``. Dann rechnet die Tabelle alles Abhängige darauf um,
statt den Widerspruch stehen zu lassen.

``pruefe()`` misst die Tabelle gegen sich selbst: jedes Maß, das zwei Teile
gemeinsam haben, muss auf beiden Seiten dasselbe sein, und die
Größenverhältnisse müssen stimmen (der Bolzen passt in den Kolben, das große
Auge zwischen die Wangen). Das ist die Probe, die ein einzelnes Bauteil
nicht führen kann.
"""

import kt_bauformen as B

#: Verhältnisse, auf die Bohrung bezogen (Stichmaß auf den Hub). Jede Zeile
#: ist eine Faustformel des Motorenbaus, keine Norm — deshalb stehen sie hier
#: offen und nicht in den Bauteilen versteckt.
VERHAELTNISSE = {
    "stichmass": 1.75,            # x Hub; lambda = r/l landet bei ~0,29
    "zylinderabstand": 1.18,      # x Bohrung
    "kompressionshoehe": 0.372,   # x Bohrung
    "kolbenbolzen_d": 0.256,      # x Bohrung
    "hubzapfen_d": 0.558,         # x Bohrung
    "hauptlager_d": 0.628,        # x Bohrung
    "pleuel_breite": 0.256,       # x Bohrung
    "ventilhub": 0.116,           # x Bohrung
    "nocken_grundkreis_d": 0.372, # x Bohrung
    "steuertrieb_d": 0.349,       # x Bohrung; Zapfen an der Kurbelnase
    "nockenwelle_antrieb_d": 0.302,  # x Bohrung; Zapfen der Nockenwelle
    "stoessel_d": 0.384,          # x Bohrung
    "wange_t": 0.209,             # x Bohrung; Dicke einer Kurbelwange
    "hauptlager_b": 0.302,        # x Bohrung; Breite eines Hauptlagers
    # Kolben nach MAHLE, Kolben-Gestaltungsrichtlinien, Tabelle 2.1
    # (Viertakt-Ottomotor Pkw). Siehe Gestaltung/kolben.md.
    "kolben_schafthoehe": 0.28,   # x Bohrung; Bolzenmitte bis Schaftende
    "kolben_boden_t": 0.081,      # x Bohrung; Bodendicke, Soll 0,06…0,10
    "kolben_feuersteg": 0.06,     # x Bohrung; Soll 0,04…0,10 (Otto)
    "kolben_ringsteg": 0.045,     # x Bohrung; 1. Ringsteg, Soll 0,040…0,055
    "kolben_desachsierung": 0.01,  # x Bohrung; Versatz der Bolzenachse
    # Breite des kleinen Pleuelauges. An der BOHRUNG gemessen, nicht an der
    # Pleuelbreite: sie bestimmt den Nabenabstand im Kolben, und dafuer gibt
    # es einen Richtwert (NA/D = 0,20…0,35). Mit 0,75 x Pleuelbreite lag er
    # bei 0,198 und damit knapp darunter.
    "pleuel_auge_b": 0.235,       # x Bohrung
}

#: Grenzen aus der Literatur, die ``pruefe()`` nachmisst: Name -> (min, max)
#: als Anteil der Bohrung. Alles hier ist belegt, nichts geschaetzt.
GRENZEN = {
    "kolben_gesamtlaenge": (0.60, 0.70),   # GL/D, Otto 4-Takt Pkw
    "kompressionshoehe": (0.30, 0.45),     # KH/D
    "kolbenbolzen_d": (0.20, 0.26),        # BO/D
    "kolben_boden_t": (0.06, 0.10),        # s/D
    "kolben_feuersteg": (0.04, 0.10),      # Otto
    "kolben_ringsteg": (0.040, 0.055),     # 1. Ringsteg St/D
    "nabenabstand": (0.20, 0.35),          # NA/D
}

#: Maße, die zwei Bauteile teilen: (Maß, wer es braucht). Genau diese Paare
#: prüft ``pruefe()`` — und genau an diesen Stellen entstehen die Fehler,
#: die keine Einzelprüfung findet.
GETEILT = (
    ("kolbenbolzen_d", "Kolben (Bolzennabe)", "Pleuel (kleines Auge)"),
    ("hubzapfen_d", "Kurbelwelle (Hubzapfen)", "Pleuel (grosses Auge)"),
    ("pleuel_auge_b", "Pleuel (kleines Auge)", "Kolben (Schlitz)"),
    ("pleuel_breite", "Pleuel (grosses Auge)", "Kurbelwelle (Zapfenbreite)"),
    ("steuertrieb_d", "Kurbelwelle (Nase)", "Steuertrieb (Kettenrad)"),
    ("nockenwelle_antrieb_d", "Nockenwelle (Zapfen)",
     "Steuertrieb (Nockenrad)"),
    ("nocken_grundkreis_d", "Nockenwelle", "Ventiltrieb (Achshoehe)"),
)


class AuslegungFehler(Exception):
    pass


def auslegen(bohrung=86.0, hub=86.0, bauform="R4", ventile_je_zylinder=4,
             v8_kreuzebene=True, bankwinkel=0.0, **ueberschreiben):
    """Die vollständige Maßtabelle eines Motors.

    bohrung, hub          [mm] — daraus folgt alles Übrige
    bauform               R2 … V12
    ventile_je_zylinder   2 oder 4
    ueberschreiben        beliebiger Schlüssel der Tabelle; Abhängiges wird
                          darauf umgerechnet, nicht überstimmt

    Alle Längen in mm, alle Winkel in Grad.
    """
    import kt_auslassventil
    import kt_einlassventil
    import kt_nockenwelle

    d = float(bohrung)
    s = float(hub)
    if d <= 0.0 or s <= 0.0:
        raise AuslegungFehler("Bohrung und Hub muessen positiv sein.")
    z, bank = B.daten(bauform, bankwinkel)
    v = VERHAELTNISSE

    def w(name, bezug=None):
        """Verhältniswert, sofern nicht überschrieben."""
        if name in ueberschreiben and ueberschreiben[name]:
            return float(ueberschreiben[name])
        return round((s if bezug == "hub" else d) * v[name], 1)

    a = {
        "bauform": str(bauform),
        "zylinder": z,
        "bankwinkel": bank,
        "ventile_je_zylinder": int(ventile_je_zylinder),
        "bohrung": d,
        "hub": s,
        "kurbelradius": round(s / 2.0, 2),
        "stichmass": w("stichmass", "hub"),
        "zylinderabstand": w("zylinderabstand"),
        "kompressionshoehe": w("kompressionshoehe"),
        "kolbenbolzen_d": w("kolbenbolzen_d"),
        "hubzapfen_d": w("hubzapfen_d"),
        "hauptlager_d": w("hauptlager_d"),
        "pleuel_breite": w("pleuel_breite"),
        "ventilhub": w("ventilhub"),
        "nocken_grundkreis_d": w("nocken_grundkreis_d"),
        "steuertrieb_d": w("steuertrieb_d"),
        "nockenwelle_antrieb_d": w("nockenwelle_antrieb_d"),
        "stoessel_d": w("stoessel_d"),
        "wange_t": w("wange_t"),
        "hauptlager_b": w("hauptlager_b"),
        "kolben_schafthoehe": w("kolben_schafthoehe"),
        "kolben_boden_t": w("kolben_boden_t"),
        "kolben_feuersteg": w("kolben_feuersteg"),
        "kolben_ringsteg": w("kolben_ringsteg"),
        "kolben_desachsierung": w("kolben_desachsierung"),
    }

    # --- Abgeleitetes, das aus der Tabelle selbst folgt -------------------
    # Das kleine Pleuelauge und der Schlitz zwischen den Bolzennaben des
    # Kolbens sind DASSELBE Mass. Vorher stand im Kolben fest 17 mm und im
    # Pleuel 0,75 x Breite = 16,5 — bei 86 mm Bohrung passte das zufaellig,
    # bei einer breiteren Pleuelstange nicht.
    a["pleuel_auge_b"] = w("pleuel_auge_b")
    # Beim V-Motor teilen sich zwei Pleuel einen Zapfen, beim Reihenmotor
    # traegt er eines. Fest 26 mm stand hier frueher fuer den Reihenmotor —
    # bei 120 mm Bohrung ist das Pleuel aber 30,7 mm breit und haette
    # ueberstanden. Die Pruefung hat genau das gefunden.
    a["hubzapfen_b"] = round(2.0 * a["pleuel_breite"] + 4.0
                             if B.ist_v(bauform, bank)
                             else a["pleuel_breite"] + 4.0, 2)
    # Der Zylinderabstand muss ZWEIERLEI koennen: den Kolben Platz lassen
    # und zur Kurbelwelle passen. Die Welle baut ihre Zapfenteilung aus
    # Hauptlager + zwei Wangen + Hubzapfen; ist der Zylinderabstand kleiner,
    # geht das nicht auf. Gemessen bei 100 mm Bohrung: die Welle teilte mit
    # 91,6 mm, der Kolben ist 99,9 mm breit — Kolben 2 und 3 durchdrangen
    # sich zu 4,6 %, bei 120 mm zu 14 %. Beide Seiten lesen jetzt dasselbe.
    a["kurbel_mindestteilung"] = round(a["hauptlager_b"] + 2.0 * a["wange_t"]
                                       + a["hubzapfen_b"], 2)
    a["zylinder_mindestabstand"] = round(d + 6.0, 2)
    a["zylinderabstand"] = round(max(a["zylinderabstand"],
                                     a["kurbel_mindestteilung"],
                                     a["zylinder_mindestabstand"]), 2)
    a["kolben_gesamtlaenge"] = round(a["kompressionshoehe"]
                                     + a["kolben_schafthoehe"], 2)
    # Zapfenueberdeckung: wie weit Hubzapfen und Hauptlagerzapfen einander
    # axial gesehen ueberdecken. Positiv heisst, dass Material des einen in
    # Material des anderen uebergeht — daran haengt die Steifigkeit der
    # ganzen Welle (Contemporary Crankshaft Design).
    a["zapfenueberdeckung"] = round((a["hauptlager_d"] + a["hubzapfen_d"]
                                     - a["hub"]) / 2.0, 2)
    a["blockhoehe"] = round(a["kurbelradius"] + a["stichmass"]
                            + a["kompressionshoehe"], 2)
    a["lambda"] = round(a["kurbelradius"] / a["stichmass"], 4)

    # Ventile: die beiden Bauteile sagen selbst, wie gross sie sind.
    n = int(ventile_je_zylinder)
    a["einlass_teller_d"] = kt_einlassventil.vorschlag(d, n)
    a["einlass_schaft_d"] = kt_einlassventil.schaftvorschlag(d)
    a["auslass_teller_d"] = kt_auslassventil.vorschlag(d, n)
    a["auslass_schaft_d"] = kt_auslassventil.schaftvorschlag(d)
    # Der Stoessel muss den Ventilschaft aufnehmen und unter den Nocken
    # passen — er richtet sich nach dem dickeren der beiden Schaefte.
    a["ventil_schaft_d"] = max(a["einlass_schaft_d"], a["auslass_schaft_d"])
    # Der Tassendurchmesser folgt NICHT aus der Bohrung, sondern aus dem
    # Nocken: beim Flachstoessel wandert der Beruehrpunkt um dh/dphi zur
    # Seite, und die Tasse muss zweimal so breit sein. Bei 10 mm Hub und
    # 60 Grad Flanke sind das 15 mm Auswanderung und 30 mm Mindesttasse.
    a["nocken_auswanderung"] = kt_nockenwelle.auswanderung(
        a["nocken_grundkreis_d"] / 2.0, a["ventilhub"])
    a["stoessel_mindest_d"] = round(2.0 * a["nocken_auswanderung"], 2)
    a["stoessel_d"] = round(max(a["stoessel_d"],
                                a["stoessel_mindest_d"] + 0.06 * d), 2)

    for k in ueberschreiben:
        if k not in a:
            raise AuslegungFehler(
                "%r steht nicht in der Auslegung. Moeglich: %s"
                % (k, ", ".join(sorted(a))))
    # Nur WIRKLICHE Angaben ueberschreiben. Ein 0.0 heisst "nicht gesetzt" —
    # kt_motor reicht seine Vorgaben so durch, und mit einem stumpfen
    # update() stand danach ein Bolzendurchmesser von 0 in der Tabelle.
    a.update({k: val for k, val in ueberschreiben.items()
              if k in a and val not in (0, 0.0, None, "")})
    return a


def pruefe(a):
    """Misst die Tabelle gegen sich selbst; liefert [(ok, Text), …]."""
    befunde = []

    def sag(ok, text):
        befunde.append((bool(ok), text))

    # Die geteilten Masse sind je EIN Eintrag — das ist die Zusage dieser
    # Datei, und sie ist hier nachweisbar, nicht nur behauptet.
    fehlend = [name for name, _x, _y in GETEILT if name not in a]
    sag(not fehlend,
        "alle %d geteilten Masse stehen in der Tabelle%s"
        % (len(GETEILT), "" if not fehlend else ": fehlt " + ", ".join(fehlend)))

    # Groessenverhaeltnisse, die stimmen muessen, sonst passt nichts.
    sag(0.0 < a["kolbenbolzen_d"] < a["bohrung"] * 0.45,
        "der Kolbenbolzen (%.1f) passt in die Bohrung (%.1f)"
        % (a["kolbenbolzen_d"], a["bohrung"]))
    sag(a["hubzapfen_d"] < a["hauptlager_d"],
        "der Hubzapfen (%.1f) ist duenner als das Hauptlager (%.1f)"
        % (a["hubzapfen_d"], a["hauptlager_d"]))
    sag(a["kolbenbolzen_d"] < a["hubzapfen_d"],
        "der Kolbenbolzen (%.1f) ist duenner als der Hubzapfen (%.1f)"
        % (a["kolbenbolzen_d"], a["hubzapfen_d"]))
    sag(a["stichmass"] > a["kurbelradius"] * 2.0,
        "das Stichmass (%.1f) ist laenger als der Hub (%.1f)"
        % (a["stichmass"], 2.0 * a["kurbelradius"]))
    sag(0.20 <= a["lambda"] <= 0.35,
        "Schubstangenverhaeltnis lambda = %.3f (ueblich 0,20…0,35)"
        % a["lambda"])
    sag(a["zylinderabstand"] > a["bohrung"],
        "der Zylinderabstand (%.1f) ist groesser als die Bohrung (%.1f)"
        % (a["zylinderabstand"], a["bohrung"]))
    sag(a["zylinderabstand"] >= a.get("kurbel_mindestteilung", 0.0) - 0.01,
        "der Zylinderabstand (%.1f) passt zur Zapfenteilung der Welle (%.1f)"
        % (a["zylinderabstand"], a.get("kurbel_mindestteilung", 0.0)))
    sag(a["pleuel_auge_b"] < a["pleuel_breite"],
        "das kleine Auge (%.2f) ist schmaler als das grosse (%.1f)"
        % (a["pleuel_auge_b"], a["pleuel_breite"]))
    sag(a["hubzapfen_b"] >= a["pleuel_breite"],
        "der Hubzapfen (%.1f breit) traegt das Pleuel (%.1f)"
        % (a["hubzapfen_b"], a["pleuel_breite"]))
    # Die Ventile muessen nebeneinander in die Bohrung passen: zwei Teller
    # je Seite plus Steg.
    je_seite = max(1, a["ventile_je_zylinder"] // 2)
    breit = je_seite * max(a["einlass_teller_d"], a["auslass_teller_d"])
    sag(breit < a["bohrung"] * 1.02,
        "%d Ventile je Seite (%.1f mm) passen in die Bohrung (%.1f)"
        % (je_seite, breit, a["bohrung"]))
    sag(a.get("stoessel_mindest_d", 0.0) <= a["stoessel_d"],
        "die Tasse (%.1f) traegt die Auswanderung des Nockens (%.1f mm, "
        "braucht %.1f)" % (a["stoessel_d"], a.get("nocken_auswanderung", 0.0),
                           a.get("stoessel_mindest_d", 0.0)))
    sag(a["stoessel_d"] > a["ventil_schaft_d"] * 2.0,
        "der Stoessel (%.1f) nimmt den Ventilschaft (%.1f) auf"
        % (a["stoessel_d"], a["ventil_schaft_d"]))
    sag(a["nocken_grundkreis_d"] / 2.0 > a["ventilhub"],
        "der Nockengrundkreis (r %.1f) traegt den Hub (%.1f)"
        % (a["nocken_grundkreis_d"] / 2.0, a["ventilhub"]))
    # Die Kurbelwange traegt den Hubzapfen; ihr Radius darf den Kolben in
    # seiner tiefsten Lage nicht streifen. Bei 70 mm Bohrung und 66 mm Hub
    # war der feste 48-mm-Schaft zu lang: Wange und Kolben durchdrangen
    # sich zu 4,0 %.
    wange_r = a["kurbelradius"] + a["hubzapfen_d"] / 2.0 + 2.0
    kolben_unten = a["stichmass"] - a["kolben_schafthoehe"]
    sag(kolben_unten > wange_r,
        "die Kurbelwange (r %.1f) bleibt unter dem Kolbenschaft (%.1f)"
        % (wange_r, kolben_unten))
    # Die Grenzen der Literatur, Mass fuer Mass (siehe GRENZEN).
    schief = []
    for name, (lo, hi) in sorted(GRENZEN.items()):
        wert = a.get(name)
        if name == "nabenabstand":
            wert = a.get("pleuel_auge_b", 0.0) + 0.5
        if not wert:
            continue
        anteil = wert / a["bohrung"]
        if not lo - 1e-9 <= anteil <= hi + 1e-9:
            schief.append("%s %.3f (Soll %.2f…%.2f)" % (name, anteil, lo, hi))
    sag(not schief,
        "alle %d Kolbenmasse liegen in den Richtwerten%s"
        % (len(GRENZEN), "" if not schief else ": " + "; ".join(schief)))
    sag(a["zapfenueberdeckung"] > 0.0,
        "Zapfenueberdeckung %.1f mm (muss positiv sein, sonst haengt der "
        "Hubzapfen allein an der Wange)" % a["zapfenueberdeckung"])
    sag(a["einlass_teller_d"] > a["auslass_teller_d"],
        "der Einlassteller (%.1f) ist groesser als der Auslassteller (%.1f)"
        % (a["einlass_teller_d"], a["auslass_teller_d"]))
    sag(a["auslass_schaft_d"] > a["einlass_schaft_d"],
        "der Auslassschaft (%.1f) ist dicker als der Einlassschaft (%.1f)"
        % (a["auslass_schaft_d"], a["einlass_schaft_d"]))
    return befunde


def selbsttest():
    """Prüft, dass die Tabelle mitwächst und in sich stimmt."""
    # Bei 86 mm muss genau herauskommen, womit dieser Generator vermessen
    # wurde — sonst waere die Umstellung eine stille Aenderung.
    a = auslegen(bohrung=86.0, hub=86.0, bauform="R4")
    # Die Gesamtlaenge des Kolbens gehoert beim Viertakt-Ottomotor auf
    # 0,6…0,7 x Bohrung. Mit dem frueheren Schaft von 0,558 x D kam 0,93
    # heraus — das ist Dieselmass, und es kostete bei kleiner Bohrung die
    # Freiheit der Kurbelwange.
    if not 0.60 <= a["kolben_gesamtlaenge"] / 86.0 <= 0.70:
        raise AssertionError("Kolbengesamtlaenge %.3f x D, Soll 0,60…0,70"
                             % (a["kolben_gesamtlaenge"] / 86.0))
    soll = {"stichmass": 150.5, "zylinderabstand": 101.5,
            "kompressionshoehe": 32.0, "kolbenbolzen_d": 22.0,
            "hubzapfen_d": 48.0, "hauptlager_d": 54.0,
            "pleuel_breite": 22.0, "ventilhub": 10.0,
            "nocken_grundkreis_d": 32.0, "steuertrieb_d": 30.0,
            "nockenwelle_antrieb_d": 26.0, "blockhoehe": 225.5}
    for k, v in soll.items():
        if abs(a[k] - v) > 0.05:
            raise AssertionError("%s = %.2f statt %.2f — die Tabelle aendert "
                                 "die bisherigen Masse" % (k, a[k], v))

    # Alle Pruefungen muessen fuer jede Bauform und ueber den ganzen
    # Groessenbereich halten.
    for bauform in sorted(B.BAUFORMEN):
        for d, s in ((70.0, 66.0), (86.0, 86.0), (120.0, 110.0)):
            for nv in (2, 4):
                t = auslegen(bohrung=d, hub=s, bauform=bauform,
                             ventile_je_zylinder=nv)
                schlecht = [x for ok, x in pruefe(t) if not ok]
                if schlecht:
                    raise AssertionError(
                        "%s %.0fx%.0f, %d Ventile: %s"
                        % (bauform, d, s, nv, "; ".join(schlecht)))

    # Mitwachsen: doppelte Bohrung, doppelter Bolzen.
    gross = auslegen(bohrung=172.0, hub=86.0, bauform="R4")
    if abs(gross["kolbenbolzen_d"] - 2.0 * a["kolbenbolzen_d"]) > 0.2:
        raise AssertionError("der Bolzen waechst nicht mit der Bohrung")

    # Ueberschreiben: das Abhaengige muss folgen, nicht widersprechen.
    breit = auslegen(bohrung=86.0, hub=86.0, bauform="V8", pleuel_breite=30.0)
    # Das kleine Auge haengt an der BOHRUNG (Nabenabstand im Kolben), nicht
    # an der Pleuelbreite — es bleibt also stehen, wenn die Stange breiter
    # wird. Ueberschreiben laesst es sich trotzdem.
    if abs(breit["pleuel_auge_b"] - a["pleuel_auge_b"]) > 0.01:
        raise AssertionError("das kleine Auge folgt der Bohrung nicht "
                             "(%.2f statt %.2f)"
                             % (breit["pleuel_auge_b"], a["pleuel_auge_b"]))
    eigen = auslegen(bohrung=86.0, hub=86.0, bauform="R4",
                     pleuel_auge_b=19.0)
    if abs(eigen["pleuel_auge_b"] - 19.0) > 1e-9:
        raise AssertionError("das kleine Auge laesst sich nicht setzen")
    if abs(breit["hubzapfen_b"] - 64.0) > 0.01:
        raise AssertionError("die Zapfenbreite folgt der Pleuelbreite nicht "
                             "(%.2f statt 64)" % breit["hubzapfen_b"])

    # Unsinn muss auffallen.
    for kw in ({"bohrung": 0.0}, {"quatsch": 1.0}):
        try:
            auslegen(**kw)
            raise AssertionError("unsinnige Eingabe blieb unbemerkt: %r" % kw)
        except AuslegungFehler:
            pass

    return ("Auslegung-Selbsttest bestanden (%d Bauformen x 3 Groessen x 2 "
            "Ventilzahlen, %d geteilte Masse, bei 86 mm unveraendert)"
            % (len(B.BAUFORMEN), len(GETEILT)))
