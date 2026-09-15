# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Bauformen des Kurbeltriebs: Zylinderzahl, Bankwinkel, Kurbelversatz.

Reine Rechnung, keine Geometrie. Hier steht, was einen R5 von einem V8
unterscheidet — und das ist mehr als die Zylinderzahl:

* **Reihenmotoren** haben einen Hubzapfen je Zylinder, alle in einer Ebene
  verteilt. Der Zündabstand ist 720°/z, also R3 240°, R4 180°, R6 120°.
  R2 und R4 haben deshalb zwei Zapfen auf derselben Winkellage.
* **V-Motoren** teilen sich einen Hubzapfen zwischen zwei gegenüberliegenden
  Zylindern. Es gibt also nur z/2 Zapfen.
* Damit der Zündabstand gleichmäßig bleibt, muss der Bankwinkel zum
  Zapfenabstand passen: ``bankwinkel = 720 / z``. Das ist der Grund, warum
  ein V6 60° hat und ein V12 auch, ein V8 dagegen 90°.
* Passt der Bankwinkel nicht dazu, hilft ein **Hubzapfenversatz**
  (split pin): ``versatz = |720/z - bankwinkel|``. Das ist die klassische
  Beziehung; sie liefert für den bekannten 90°-V6 die ebenso bekannten 30°.
  Auch ein 60°-V6 braucht danach Versatz (60°) — mit 120°-Zapfen und 60°
  Bänken sind die Zündabstände sonst ungleich, das ist der Grund für die
  gesplitteten Hubzapfen heutiger 60°-V6. Der V8 mit Kreuzebenenkurbel
  braucht keinen, weil seine Zapfen über zwei Ebenen verteilt sind.

Der Kreuzebenen-V8 ist die eine Bauform, die aus dem Schema fällt: seine vier
Hubzapfen stehen auf 0°, 90°, 270°, 180° statt auf einer Ebene. Das gibt
gleichmäßige Zündabstände von 90° und den bekannten Massenausgleich — und den
typischen Klang.
"""

#: Bauform -> (Zylinder, Bankwinkel in Grad; 0 = Reihe)
BAUFORMEN = {
    "R2": (2, 0.0),
    "R3": (3, 0.0),
    "R4": (4, 0.0),
    "R5": (5, 0.0),
    "R6": (6, 0.0),
    "V4": (4, 90.0),
    "V6": (6, 60.0),
    "V8": (8, 90.0),
    "V10": (10, 72.0),
    "V12": (12, 60.0),
}

#: Hubzapfenwinkel des kreuzebenigen V8, in Zapfenreihenfolge [Grad].
V8_KREUZ = (0.0, 90.0, 270.0, 180.0)


class BauformFehler(Exception):
    pass


def namen():
    """Alle Bauformen, in sinnvoller Reihenfolge für eine Auswahlliste."""
    return ("R2", "R3", "R4", "R5", "R6", "V4", "V6", "V8", "V10", "V12")


def bauform_aus(zylinder, bankwinkel=0.0):
    """Name der Bauform aus Zylinderzahl und Bankwinkel.

    Für den Weg über die Skill-Maske: die nimmt nur Zahlen, und ``"V8"`` ist
    keine. Aus 8 Zylindern und 90° Bankwinkel wird der V8, aus 4 Zylindern
    und 0° der R4. Der Bankwinkel wird dabei auf den gebräuchlichen Wert der
    Bauform gebracht — einen V8 mit 63° gibt es nicht, und ein stillschweigend
    falscher Winkel wäre schlimmer als eine Meldung.
    """
    z = int(zylinder)
    reihe = float(bankwinkel) < 1.0
    for name, (zahl, winkel) in BAUFORMEN.items():
        if zahl == z and (winkel == 0.0) == reihe:
            return name
    moeglich = ", ".join("%s (%d Zyl., %.0f Grad)" % (n, k[0], k[1])
                         for n, k in sorted(BAUFORMEN.items()))
    raise BauformFehler(
        "%d Zylinder mit %.0f Grad Bankwinkel ist keine der Bauformen: %s"
        % (z, float(bankwinkel), moeglich))


def daten(bauform, bankwinkel=0.0):
    """(Zylinderzahl, Bankwinkel) einer Bauform.

    ``bankwinkel`` > 0 überschreibt den Tabellenwert. Den gibt es wirklich:
    einen V6 baut Renault mit 60°, VW mit 90°, Honda mit 55°; einen V12
    gibt es mit 60° und mit 65°. Der Bankwinkel ist eine Bauentscheidung
    (Bauraum, Massenausgleich), keine Eigenschaft der Zylinderzahl.

    Er schlägt dabei überall durch, wo er hingehört: der Hubzapfenversatz
    ist ``|720/z − bank|``, ein 90-Grad-V6 bekommt also 30° Versatz, ein
    60-Grad-V6 keinen. Ein Reihenmotor bleibt ein Reihenmotor — bei ihm
    wird der Wert nicht angenommen.
    """
    b = str(bauform).upper().strip()
    if b not in BAUFORMEN:
        raise BauformFehler("Unbekannte Bauform %r. Bekannt: %s"
                            % (bauform, ", ".join(namen())))
    z, tabelle = BAUFORMEN[b]
    w = float(bankwinkel or 0.0)
    if tabelle <= 0.0 or w <= 0.0:
        return z, tabelle
    if not 30.0 <= w <= 120.0:
        raise BauformFehler(
            "Bankwinkel %.1f Grad ist keiner: ueblich sind 60 bis 90, "
            "moeglich 30 bis 120." % w)
    return z, w


def ist_v(bauform, bankwinkel=0.0):
    return daten(bauform, bankwinkel)[1] > 0.0


def zapfenzahl(bauform, bankwinkel=0.0):
    """Wie viele Hubzapfen die Kurbelwelle hat.

    Beim V-Motor teilen sich zwei gegenüberliegende Zylinder einen Zapfen.
    """
    z, winkel = daten(bauform, bankwinkel)
    return z // 2 if winkel > 0.0 else z


def zuendabstand(bauform):
    """Gleichmäßiger Zündabstand im Viertakt [Grad Kurbelwinkel]."""
    z, _w = daten(bauform)
    return 720.0 / z


def hubzapfenversatz(bauform, v8_kreuzebene=True, bankwinkel=0.0):
    """Nötiger Versatz innerhalb eines Hubzapfens [Grad], 0 = keiner.

    Ein V-Motor läuft nur dann gleichmäßig, wenn Bankwinkel und Zündabstand
    zusammenpassen. Tun sie es nicht, wird der Hubzapfen gesplittet.
    """
    z, bank = daten(bauform, bankwinkel)
    if bank <= 0.0:
        return 0.0
    if str(bauform).upper() == "V8" and v8_kreuzebene and \
            abs(bank - BAUFORMEN["V8"][1]) < 1e-9:
        return 0.0
    noetig = abs(720.0 / z - bank)
    return round(noetig, 3) if noetig > 1e-9 else 0.0


#: Hubzapfenwinkel je Bauform, in Zapfenreihenfolge [Grad].
#:
#: Bewusst eine Tabelle und keine Formel. Die Folgen sind Konstruktionspraxis
#: und folgen keiner durchgaengigen Regel: ein Reihensechszylinder hat die
#: spiegelbildliche Folge 0-240-120-120-240-0 (das ist sein Massenausgleich),
#: ein flachebeniger V8 steht mit 0-180-180-0 absichtlich NICHT gleichmaessig
#: verteilt, waehrend der kreuzebenige mit 0-90-270-180 ueber zwei Ebenen
#: geht. Eine Formel, die das alles trifft, gibt es nicht — wer eine schreibt,
#: bekommt irgendwo stillschweigend etwas Falsches.
ZAPFENWINKEL = {
    "R2": (0.0, 0.0),                       # 360-Grad-Kurbel, beide zusammen
    "R3": (0.0, 240.0, 120.0),
    "R4": (0.0, 180.0, 180.0, 0.0),
    "R5": (0.0, 144.0, 288.0, 72.0, 216.0),
    "R6": (0.0, 240.0, 120.0, 120.0, 240.0, 0.0),
    "V4": (0.0, 180.0),
    "V6": (0.0, 240.0, 120.0),
    "V8": (0.0, 90.0, 270.0, 180.0),        # kreuzebenig
    "V10": (0.0, 72.0, 144.0, 216.0, 288.0),
    "V12": (0.0, 240.0, 120.0, 120.0, 240.0, 0.0),
}

#: Der flachebenige V8 weicht ab: zwei Reihenvierzylinder, eine Ebene.
V8_FLACH = (0.0, 180.0, 180.0, 0.0)


def zapfenwinkel(bauform, v8_kreuzebene=True):
    """Winkellage jedes Hubzapfens [Grad], Zapfen 1 bei 0°."""
    b = str(bauform).upper().strip()
    daten(b)                      # wirft bei unbekannter Bauform
    if b == "V8" and not v8_kreuzebene:
        return list(V8_FLACH)
    if b not in ZAPFENWINKEL:
        # Fuer nachtraeglich eingetragene Bauformen: gleichmaessig verteilen.
        n = zapfenzahl(b)
        return [round((360.0 * k / n) % 360.0, 3) for k in range(n)]
    return list(ZAPFENWINKEL[b])


def zylinderlagen(bauform, bohrungsabstand, v8_kreuzebene=True,
                  bankwinkel=0.0):
    """Je Zylinder (Bank, x entlang der Kurbelwelle, Bankwinkel, Zapfen-Index).

    Bank 0 ist die erste Reihe, Bank 1 die zweite. Der Bankwinkel ist der
    Winkel der Zylinderachse gegen die Senkrechte: beim Reihenmotor 0, beim
    V-Motor ±bank/2 — die Zylinderbänke stehen symmetrisch zur Mitte.
    """
    z, bank = daten(bauform, bankwinkel)
    abstand = float(bohrungsabstand)
    lagen = []
    if bank <= 0.0:
        for k in range(z):
            lagen.append((0, k * abstand, 0.0, k))
        return lagen
    halb = bank / 2.0
    for k in range(z):
        zapfen = k // 2
        seite = k % 2
        lagen.append((seite, zapfen * abstand,
                      -halb if seite == 0 else +halb, zapfen))
    return lagen


#: Übliche Zündfolgen. Auch das ist Tabelle und keine Rechnung.
#:
#: Aus den Hubzapfenwinkeln allein folgt die Zündfolge NICHT: zwei Zylinder
#: auf derselben Winkellage zünden 360° auseinander, und welcher von beiden
#: zuerst drankommt, entscheidet die Nockenwelle. Ein erster Versuch, das aus
#: der Kurbel abzuleiten, ergab für den R4 die Folge 1-4-2-3 statt der
#: üblichen 1-3-4-2 — richtig gerechnet, aber kein Motor baut das so.
#:
#: Je Bauform gibt es mehrere gültige Folgen; hier steht eine gebräuchliche.
#: Die Zylindernummerierung ist: Reihe von vorn durchgezählt, V-Motor
#: abwechselnd Bank A / Bank B.
ZUENDFOLGEN = {
    "R2": (1, 2),
    "R3": (1, 3, 2),
    "R4": (1, 3, 4, 2),
    "R5": (1, 2, 4, 5, 3),
    "R6": (1, 5, 3, 6, 2, 4),
    "V4": (1, 3, 2, 4),
    "V6": (1, 4, 3, 6, 2, 5),
    "V8": (1, 8, 7, 3, 6, 5, 4, 2),
    "V10": (1, 6, 5, 10, 2, 7, 3, 8, 4, 9),
    "V12": (1, 7, 5, 11, 3, 9, 6, 12, 2, 8, 4, 10),
}


def zuendfolge(bauform, v8_kreuzebene=True):
    """Eine gebräuchliche Zündfolge als Zylindernummern (1-basiert).

    Aus der Kurbelwelle allein lässt sich das nicht ableiten — siehe
    :data:`ZUENDFOLGEN`. Für eine Bauform ohne Eintrag wird schlicht
    durchgezählt, und das ist dann auch nur eine Reihenfolge, keine Zündfolge.
    """
    b = str(bauform).upper().strip()
    z, _bank = daten(b)
    if b == "V8" and not v8_kreuzebene:
        # Flachebeniger V8: die Baenke zuenden abwechselnd.
        return [1, 4, 6, 7, 8, 5, 3, 2]
    if b in ZUENDFOLGEN:
        return list(ZUENDFOLGEN[b])
    return list(range(1, z + 1))


def kennwerte(bauform, bohrung=86.0, hub=86.0, v8_kreuzebene=True,
              bankwinkel=0.0):
    """Die Auslegung auf einen Blick, ohne Geometrie."""
    z, bank = daten(bauform, bankwinkel)
    import math
    einzel = math.pi * (float(bohrung) / 2.0) ** 2 * float(hub) / 1000.0
    return {
        "bauform": str(bauform).upper(),
        "zylinder": z,
        "bankwinkel": bank,
        "hubzapfen": zapfenzahl(bauform, bankwinkel),
        "zapfenwinkel": zapfenwinkel(bauform, v8_kreuzebene),
        "hubzapfenversatz": hubzapfenversatz(bauform, v8_kreuzebene,
                                             bankwinkel),
        "zuendabstand": round(zuendabstand(bauform), 2),
        "zuendfolge": zuendfolge(bauform, v8_kreuzebene),
        "hubraum_cm3": round(einzel * z, 1),
        "einzelhubraum_cm3": round(einzel, 1),
    }


def selbsttest():
    """Prüft die Tabelle gegen bekannte Werte des Motorenbaus."""
    if zapfenzahl("R6") != 6 or zapfenzahl("V6") != 3:
        raise AssertionError("Zapfenzahl falsch: V-Motoren teilen sich Zapfen")
    if zapfenzahl("V12") != 6 or zapfenzahl("V8") != 4:
        raise AssertionError("Zapfenzahl V8/V12 falsch")

    for bauform, erwartet in (("R4", 180.0), ("R6", 120.0), ("R3", 240.0),
                              ("R5", 144.0), ("V8", 90.0), ("V12", 60.0)):
        if abs(zuendabstand(bauform) - erwartet) > 1e-6:
            raise AssertionError("%s: Zuendabstand %.1f statt %.1f"
                                 % (bauform, zuendabstand(bauform), erwartet))

    # Kein Versatz noetig, wo Bankwinkel und Zuendabstand zusammenfallen.
    for bauform, erwartet in (("V12", 0.0),    # 720/12 = 60 = Bankwinkel
                              ("V10", 0.0),    # 720/10 = 72 = Bankwinkel
                              ("V6", 60.0),    # 720/6 = 120, Bank 60
                              ("V4", 90.0)):   # 720/4 = 180, Bank 90
        if abs(hubzapfenversatz(bauform) - erwartet) > 1e-6:
            raise AssertionError("%s: Versatz %.1f statt %.1f"
                                 % (bauform, hubzapfenversatz(bauform),
                                    erwartet))
    # Gegenprobe an einer Bauform, die es so hier nicht gibt: ein 90-Grad-V6
    # braucht die bekannten 30 Grad Versatz.
    BAUFORMEN["V6-90"] = (6, 90.0)
    try:
        if abs(hubzapfenversatz("V6-90") - 30.0) > 1e-6:
            raise AssertionError("90-Grad-V6 braucht 30 Grad Versatz, "
                                 "meldet %.1f" % hubzapfenversatz("V6-90"))
    finally:
        del BAUFORMEN["V6-90"]

    # Zu jeder Bauform so viele Zapfenwinkel wie Zapfen.
    for bauform in namen():
        w = zapfenwinkel(bauform)
        if len(w) != zapfenzahl(bauform):
            raise AssertionError("%s: %d Winkel fuer %d Zapfen"
                                 % (bauform, len(w), zapfenzahl(bauform)))
        if any(g < 0.0 or g >= 360.0 for g in w):
            raise AssertionError("%s: Winkel ausserhalb 0..360: %s"
                                 % (bauform, w))

    # Kreuzebenen-V8: vier Zapfen ueber zwei Ebenen.
    w = zapfenwinkel("V8", True)
    if sorted(w) != [0.0, 90.0, 180.0, 270.0]:
        raise AssertionError("Kreuzebenen-V8 hat 0/90/180/270, nicht %s" % w)
    flach = zapfenwinkel("V8", False)
    if len(set(flach)) != 2 or sorted(set(flach)) != [0.0, 180.0]:
        raise AssertionError("flachebeniger V8 gehoert in EINE Ebene: %s"
                             % flach)

    # R5: fuenf Zapfen, gleichmaessig ueber 360 Grad, also 72 Grad Abstand.
    r5 = sorted(zapfenwinkel("R5"))
    abstaende = {round(r5[i + 1] - r5[i], 1) for i in range(len(r5) - 1)}
    if abstaende != {72.0}:
        raise AssertionError("R5 braucht 72 Grad Zapfenabstand, hat %s"
                             % abstaende)

    # R6 und V12 sind spiegelbildlich — das ist ihr Massenausgleich.
    for bauform in ("R6", "V12"):
        w = zapfenwinkel(bauform)
        if list(w) != list(reversed(w)):
            raise AssertionError("%s: Zapfenfolge nicht spiegelbildlich: %s"
                                 % (bauform, w))

    # R4: zwei aeussere Zapfen oben, zwei innere unten.
    if list(zapfenwinkel("R4")) != [0.0, 180.0, 180.0, 0.0]:
        raise AssertionError("R4: 0/180/180/0 erwartet, %s"
                             % zapfenwinkel("R4"))

    # Zylinderlagen: V-Motor mit zwei Baenken, Reihe mit einer.
    lagen = zylinderlagen("V8", 100.0)
    baenke = {b for b, _x, _w, _z in lagen}
    if baenke != {0, 1}:
        raise AssertionError("V8 braucht zwei Baenke")
    if len({x for _b, x, _w, _z in lagen}) != 4:
        raise AssertionError("V8: vier Zapfenebenen erwartet")
    if len(zylinderlagen("R6", 100.0)) != 6:
        raise AssertionError("R6 braucht sechs Zylinder")

    # Zuendfolge: jeder Zylinder genau einmal, und zwar die gebraeuchliche.
    for bauform in namen():
        f = zuendfolge(bauform)
        z, _b = daten(bauform)
        if sorted(f) != list(range(1, z + 1)):
            raise AssertionError("%s: Zuendfolge unvollstaendig: %s"
                                 % (bauform, f))
    for bauform, erwartet in (("R3", [1, 3, 2]), ("R4", [1, 3, 4, 2]),
                              ("R5", [1, 2, 4, 5, 3]),
                              ("R6", [1, 5, 3, 6, 2, 4])):
        if zuendfolge(bauform) != erwartet:
            raise AssertionError("%s: Zuendfolge %s statt %s"
                                 % (bauform, zuendfolge(bauform), erwartet))
    if sorted(zuendfolge("V8", False)) != list(range(1, 9)):
        raise AssertionError("flachebeniger V8: Zuendfolge unvollstaendig")

    k = kennwerte("R4", bohrung=86.0, hub=86.0)
    if abs(k["hubraum_cm3"] - 1998.0) > 2.0:
        raise AssertionError("R4 86x86 sind rund 1998 cm^3, nicht %.0f"
                             % k["hubraum_cm3"])
    # --- Freier Bankwinkel -----------------------------------------------
    # Ein V6 mit 90 Grad braucht 30 Grad Hubzapfenversatz, einer mit 60 Grad
    # keinen — genau das ist der Sinn des gesplitteten Zapfens.
    if abs(daten("V6", 90.0)[1] - 90.0) > 1e-9:
        raise AssertionError("der Bankwinkel laesst sich nicht setzen")
    if abs(hubzapfenversatz("V6", bankwinkel=90.0) - 30.0) > 1e-6:
        raise AssertionError(
            "90-Grad-V6: Versatz %.2f statt 30 Grad"
            % hubzapfenversatz("V6", bankwinkel=90.0))
    # Und ein 60-Grad-V6 braucht 60 Grad: |720/6 - 60|. Gleichmaessig
    # zuenden ohne Versatz tut nur, wessen Bankwinkel gleich dem
    # Zuendabstand ist — V8 mit 90, V10 mit 72, V12 mit 60 Grad.
    if abs(hubzapfenversatz("V6", bankwinkel=60.0) - 60.0) > 1e-6:
        raise AssertionError("60-Grad-V6: Versatz %.2f statt 60 Grad"
                             % hubzapfenversatz("V6", bankwinkel=60.0))
    for gleich in ("V10", "V12"):
        z, bank = daten(gleich)
        if abs(720.0 / z - bank) > 1e-9:
            continue
        if hubzapfenversatz(gleich) != 0.0:
            raise AssertionError("%s zuendet gleichmaessig und braucht "
                                 "keinen Versatz" % gleich)
    # Ein V8 mit 60 Grad ist nicht mehr der kreuzebenige Standard und
    # braucht 30 Grad Versatz.
    if abs(hubzapfenversatz("V8", True, 60.0) - 30.0) > 1e-6:
        raise AssertionError("60-Grad-V8: Versatz %.2f statt 30"
                             % hubzapfenversatz("V8", True, 60.0))
    # Bei einem Reihenmotor wird der Wert NICHT angenommen.
    if daten("R4", 90.0)[1] != 0.0:
        raise AssertionError("ein Reihenmotor hat keinen Bankwinkel")
    # Und die Baenke stehen weiter symmetrisch zur Senkrechten.
    lagen = zylinderlagen("V6", 101.5, bankwinkel=90.0)
    winkel = sorted({w for _s, _x, w, _z in lagen})
    if abs(winkel[0] + 45.0) > 1e-9 or abs(winkel[-1] - 45.0) > 1e-9:
        raise AssertionError("90-Grad-V6: Bankachsen bei %s statt -45/+45"
                             % winkel)
    # Unsinnige Winkel muessen auffallen.
    for w in (5.0, 200.0):
        try:
            daten("V8", w)
            raise AssertionError("Bankwinkel %.0f blieb unbemerkt" % w)
        except BauformFehler:
            pass

    return "Bauformen-Selbsttest bestanden (%d Bauformen)" % len(BAUFORMEN)
