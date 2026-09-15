# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Verbrennungsmotor — der ganze Kurbeltrieb als ein Skill.

Dieser Ordner ist ein Skill, der aus **vielen Dateien** besteht: je ein
Skript für jedes Bauteil, darüber die beiden Baugruppen, darüber der Motor.
Diese Datei ist nur der Einstieg, den die Skill-Maschine sucht
(``Skills/<name>/<name>.py`` mit ``T2G_SKILL`` und ``build(params)``) — sie
ruft ``kt_motor.baue()`` und reicht die Körper weiter.

    Schnittstelle   kt_schnittstelle   Punkt, Bauteil, andocke, richte
    Wissen          kt_bauformen       R2…V12: Zapfenwinkel, Zündfolgen
                    kt_kinematik       Schubkurbel, Nockenhub, Blockhöhe

    Bauteile        kt_kolben          kt_pleuel        kt_kurbelwelle
                    kt_einlassventil   kt_auslassventil kt_ventilfeder
                    kt_stoessel        kt_nockenwelle   kt_steuertrieb
                    (kt_ventil ist die gemeinsame Grundform der beiden
                     Ventile, kein eigenes Bauteil des Motors)

    Baugruppen      kt_kurbeltrieb     Kurbelwelle, Pleuel, Kolben
                    kt_ventiltrieb     Ventile, Federn, Stößel,
                                       Nockenwellen, Steuertrieb

    Ganzes          kt_motor           kennwerte, baue, pruefe

Warum so viele Dateien: ein Motor ist durchgerechnet, und jeder dieser
Punkte war schon einmal falsch. Jede Datei hat ihren eigenen
``selbsttest()``, und der misst die Zusage dieses Teils nach — die
Nockenerhebung ist wirklich der Ventilhub, das Stichmaß wirklich der
Augenabstand, die Kette läuft wirklich um alle Räder. Geht etwas kaputt,
sagt die Datei, wo.

Die **Kette** bleibt bewusst ein Bauteil, obwohl sie aus über siebzig Rollen
besteht: ihre Glieder sind alle gleich, und ihre Zusage ist die Bahn, nicht
das einzelne Glied. Die Ventile dagegen sind zwei Bauteile, weil Einlass und
Auslass sich wirklich unterscheiden — Größe, Schaftdicke, Tellerform und der
natriumgefüllte Hohlschaft des Auslassventils.
"""

import kt_bauformen
import kt_motor

T2G_SKILL = {
    "name": "Verbrennungsmotor",
    "description": (
        "Vollstaendiger Kurbeltrieb R2…V12: Kurbelwelle, Pleuel, Kolben, "
        "Ein- und Auslassventile mit Federn, Tassenstoessel mit HVA, "
        "Nockenwellen und Ketten- oder Zahnradsteuertrieb. Baut ueber "
        "Andockpunkte, nicht ueber gerechnete Koordinaten."
    ),
    "achse": "x",
    "params": [
        # (name, label, einheit, default, min, max)
        # Die Skill-Maske nimmt nur Zahlen — "V8" ist keine. Die Bauform
        # kommt deshalb aus Zylinderzahl und Bankwinkel: 8 und 90 ist der
        # V8, 4 und 0 der R4 (kt_bauformen.bauform_aus).
        ("zylinder", "Zylinderzahl", "Stk", 4, 2, 12),
        ("bankwinkel", "Bankwinkel (0 = Reihenmotor)", "Grad",
         0.0, 0.0, 120.0),
        ("bohrung", "Bohrung", "mm", 86.0, 40.0, 200.0),
        ("hub", "Hub", "mm", 86.0, 30.0, 200.0),
        ("stichmass", "Pleuelstichmass (0 = Vorschlag)", "mm", 0.0, 0.0, 500.0),
        ("kompressionshoehe", "Kompressionshoehe", "mm", 32.0, 10.0, 90.0),
        ("zylinderabstand", "Zylinderabstand (0 = Vorschlag)", "mm",
         0.0, 0.0, 300.0),
        ("ventile_je_zylinder", "Ventile je Zylinder", "Stk", 4, 2, 4),
        ("ventilhub", "Ventilhub", "mm", 10.0, 3.0, 20.0),
        ("ventilwinkel", "Ventilwinkel", "Grad", 12.0, 0.0, 30.0),
        ("spreizung", "Spreizung nach OT", "Grad", 110.0, 90.0, 130.0),
        ("steuertrieb_zahnrad", "Steuertrieb: 0 Kette, 1 Zahnrad", "-",
         0, 0, 1),
        ("mit_ventiltrieb", "Ventiltrieb bauen (1/0)", "-", 1, 0, 1),
        ("mit_getriebe", "Getriebe anflanschen (1/0)", "-", 0, 0, 1),
        ("getriebe_gaenge", "Gaenge des Getriebes", "Stk", 5, 1, 8),
    ],
    "dependencies": [],
    # Kein "kollision": ein Motor DARF sich beruehren — Kolben im Zylinder,
    # Nocken auf dem Stoessel, Kette auf dem Rad. Gemessen wird stattdessen
    # mit kt_motor.pruefe(), das Durchdringung von Beruehrung unterscheidet.
    "pruefregeln": [],
}


def _bauform(p):
    """Bauformname aus den Zahlen der Maske."""
    return kt_bauformen.bauform_aus(int(p.get("zylinder", 4)),
                                    float(p.get("bankwinkel", 0.0)))


def kennwerte(params=None):
    """Die Auslegung ohne Geometrie — für Maske und Bericht."""
    p = dict(params or {})
    return kt_motor.kennwerte(
        bauform=_bauform(p),
        bohrung=float(p.get("bohrung", 86.0)),
        hub=float(p.get("hub", 86.0)),
        stichmass=float(p.get("stichmass", 0.0)),
        kompressionshoehe=float(p.get("kompressionshoehe", 32.0)),
        zylinderabstand=float(p.get("zylinderabstand", 0.0)),
        ventile_je_zylinder=int(p.get("ventile_je_zylinder", 4)))


def build(params=None):
    """Der Motor als Liste von ``Part.Shape`` — der Skill-Einstieg."""
    p = dict(params or {})
    teile, _kenn, _proben = kt_motor.baue(
        bauform=_bauform(p),
        bohrung=float(p.get("bohrung", 86.0)),
        hub=float(p.get("hub", 86.0)),
        stichmass=float(p.get("stichmass", 0.0)),
        kompressionshoehe=float(p.get("kompressionshoehe", 32.0)),
        zylinderabstand=float(p.get("zylinderabstand", 0.0)),
        ventile_je_zylinder=int(p.get("ventile_je_zylinder", 4)),
        ventilhub=float(p.get("ventilhub", 10.0)),
        ventilwinkel=float(p.get("ventilwinkel", 12.0)),
        spreizung=float(p.get("spreizung", 110.0)),
        steuertrieb=("zahnrad" if int(p.get("steuertrieb_zahnrad", 0))
                     else "kette"),
        mit_ventiltrieb=bool(int(p.get("mit_ventiltrieb", 1))),
        mit_getriebe=bool(int(p.get("mit_getriebe", 0))),
        getriebe_gaenge=int(p.get("getriebe_gaenge", 5)))
    return [shape for _label, shape in teile]


def baue(**kw):
    """Wie ``kt_motor.baue`` — mit Bezeichnungen, für den Werkzeugweg."""
    return kt_motor.baue(**kw)[0]


def selbsttest():
    """Alle Teilskripte dieses Ordners, dann der Motor."""
    import kt_auslassventil
    import kt_bauformen
    import kt_einlassventil
    import kt_kinematik
    import kt_kolben
    import kt_kurbeltrieb
    import kt_kurbelwelle
    import kt_nockenwelle
    import kt_pleuel
    import kt_schnittstelle
    import kt_steuertrieb
    import kt_stoessel
    import kt_ventil
    import kt_ventilfeder
    import kt_ventiltrieb

    zeilen = []
    for modul in (kt_schnittstelle, kt_bauformen, kt_kinematik, kt_kolben,
                  kt_pleuel, kt_kurbelwelle, kt_ventil, kt_einlassventil,
                  kt_auslassventil, kt_ventilfeder, kt_stoessel,
                  kt_nockenwelle, kt_steuertrieb, kt_kurbeltrieb,
                  kt_ventiltrieb, kt_motor):
        zeilen.append(modul.selbsttest())
    return "Verbrennungsmotor: %d Teilskripte bestanden\n  %s" % (
        len(zeilen), "\n  ".join(zeilen))
