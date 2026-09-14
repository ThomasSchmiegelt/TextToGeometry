# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Andockpunkte: wie die Bauteile des Kurbeltriebs zueinander finden.

Jedes Bauteil-Skript liefert ein :class:`Bauteil` — seine Körper **und** seine
Anschlusspunkte. Zusammengebaut wird dann nicht über ausgerechnete
Koordinaten, sondern über diese Punkte:

    pleuel.andocke("hubzapfen", kurbelwelle.punkt("hubzapfen_1"))

Das ist der ganze Zweck der Übung. Wer die Teile mit von Hand gerechneten
x/y/z zusammensetzt, hat bei einem V8 mit Hubzapfenversatz vierzig
Gelegenheiten, sich zu vertun — und merkt es nicht, weil nichts widerspricht.
Ein Anschlusspunkt dagegen ist prüfbar: :func:`pruefe_paarung` misst, ob zwei
Punkte wirklich aufeinanderliegen.

Ein Punkt hat einen Ort, eine Achse und eine Art. Die Art sagt, was dort
zusammenkommt (``welle``, ``bohrung``, ``flaeche``, ``gleitbahn``); zwei
Punkte passen nur zusammen, wenn ihre Arten zueinander gehören.
"""

import math

import FreeCAD
from FreeCAD import Vector

#: Welche Art an welche passt. Absichtlich knapp gehalten.
PASST_AN = {
    "welle": ("bohrung",),
    "bohrung": ("welle",),
    "flaeche": ("flaeche",),
    "gleitbahn": ("gleitbahn",),
}


class SchnittstellenFehler(Exception):
    pass


class Punkt(object):
    """Ein Anschlusspunkt eines Bauteils.

    ort     Lage im Bauteilkoordinatensystem [mm]
    achse   Richtung, in die der Anschluss zeigt (Einheitsvektor)
    art     welle | bohrung | flaeche | gleitbahn
    mass    Kennmaß, an dem die Paarung hängt: Durchmesser oder Breite [mm]
    """

    def __init__(self, name, ort, achse=(0, 0, 1), art="welle", mass=0.0,
                 hinweis=""):
        self.name = str(name)
        self.ort = Vector(*ort) if not isinstance(ort, Vector) else Vector(ort)
        a = Vector(*achse) if not isinstance(achse, Vector) else Vector(achse)
        if a.Length < 1e-9:
            raise SchnittstellenFehler("Punkt %r hat keine Achse." % name)
        a.normalize()
        self.achse = a
        if art not in PASST_AN:
            raise SchnittstellenFehler(
                "Unbekannte Art %r bei %r. Erlaubt: %s"
                % (art, name, ", ".join(sorted(PASST_AN))))
        self.art = art
        self.mass = float(mass)
        self.hinweis = str(hinweis)

    def verschoben(self, platzierung):
        """Derselbe Punkt, durch eine Placement bewegt."""
        neu = Punkt(self.name, platzierung.multVec(self.ort),
                    platzierung.Rotation.multVec(self.achse),
                    self.art, self.mass, self.hinweis)
        return neu

    def __repr__(self):
        return ("Punkt(%r, (%.2f, %.2f, %.2f), Achse (%.2f, %.2f, %.2f), %s, "
                "d=%.1f)" % (self.name, self.ort.x, self.ort.y, self.ort.z,
                             self.achse.x, self.achse.y, self.achse.z,
                             self.art, self.mass))


class Bauteil(object):
    """Was ein Komponenten-Skript liefert: Körper plus Anschlusspunkte."""

    def __init__(self, name, koerper=None, punkte=None, kennwerte=None):
        self.name = str(name)
        #: Liste von (Bezeichnung, Shape)
        self.koerper = list(koerper or [])
        self.punkte = {}
        for p in (punkte or []):
            self.punkte[p.name] = p
        #: Zahlen, die andere Bauteile brauchen (Hub, Durchmesser, …)
        self.kennwerte = dict(kennwerte or {})

    def punkt(self, name):
        if name not in self.punkte:
            raise SchnittstellenFehler(
                "%s hat keinen Anschlusspunkt %r. Vorhanden: %s"
                % (self.name, name, ", ".join(sorted(self.punkte)) or "keine"))
        return self.punkte[name]

    def volumen(self):
        return sum(float(s.Volume or 0.0) for _n, s in self.koerper)

    def bewegt(self, platzierung):
        """Eine Kopie, komplett bewegt — Körper und Punkte zusammen.

        Dass beides dieselbe Bewegung erfährt, ist der Grund, warum die
        Schnittstellen nach dem Zusammenbau noch stimmen.
        """
        neu = Bauteil(self.name, kennwerte=self.kennwerte)
        for label, shp in self.koerper:
            s = shp.copy()
            s.Placement = platzierung.multiply(s.Placement)
            neu.koerper.append((label, s))
        for p in self.punkte.values():
            neu.punkte[p.name] = p.verschoben(platzierung)
        return neu

    def __repr__(self):
        return "Bauteil(%r, %d Koerper, Punkte: %s)" % (
            self.name, len(self.koerper), ", ".join(sorted(self.punkte)))


def _drehung(von, nach):
    """Rotation, die ``von`` auf ``nach`` dreht."""
    v = Vector(von)
    n = Vector(nach)
    v.normalize()
    n.normalize()
    punkt = v.dot(n)
    if punkt > 1.0 - 1e-12:
        return FreeCAD.Rotation()
    if punkt < -1.0 + 1e-12:
        # Gegenrichtung: irgendeine Achse senkrecht zu v nehmen.
        hilf = Vector(1, 0, 0) if abs(v.x) < 0.9 else Vector(0, 1, 0)
        achse = v.cross(hilf)
        achse.normalize()
        return FreeCAD.Rotation(achse, 180.0)
    achse = v.cross(n)
    achse.normalize()
    return FreeCAD.Rotation(achse, math.degrees(math.acos(punkt)))


def platzierung_fuer(eigener, ziel, gegenlaeufig=True, drehwinkel=0.0):
    """Die Bewegung, die ``eigener`` auf ``ziel`` legt.

    ``gegenlaeufig``: die Achsen zeigen einander an (Welle in Bohrung).
    ``drehwinkel``: zusätzliche Drehung um die Zielachse [Grad] — damit lässt
    sich ein Bauteil um seinen Anschluss verdrehen, ohne ihn zu verlieren.
    """
    ziel_achse = Vector(ziel.achse)
    if gegenlaeufig:
        ziel_achse = ziel_achse.negative()
    dreh = _drehung(eigener.achse, ziel_achse)
    if abs(float(drehwinkel)) > 1e-12:
        dreh = FreeCAD.Rotation(Vector(ziel.achse),
                                float(drehwinkel)).multiply(dreh)
    versatz = ziel.ort.sub(dreh.multVec(eigener.ort))
    return FreeCAD.Placement(versatz, dreh)


def andocke(bauteil, eigener_punkt, ziel_punkt, gegenlaeufig=True,
            drehwinkel=0.0):
    """``bauteil`` so bewegen, dass sein Punkt auf dem Zielpunkt liegt."""
    eigener = bauteil.punkt(eigener_punkt) if isinstance(eigener_punkt, str) \
        else eigener_punkt
    if eigener.art not in PASST_AN or \
            ziel_punkt.art not in PASST_AN[eigener.art]:
        raise SchnittstellenFehler(
            "%s.%s (%s) passt nicht an %s (%s)."
            % (bauteil.name, eigener.name, eigener.art, ziel_punkt.name,
               ziel_punkt.art))
    return bauteil.bewegt(platzierung_fuer(eigener, ziel_punkt, gegenlaeufig,
                                           drehwinkel))


def pruefe_paarung(a, b, ort_tol=0.01, winkel_tol=1.0, mass_tol=0.5):
    """Liegen zwei Anschlusspunkte wirklich aufeinander?

    Liefert (ok, Text). Geprüft werden Ort, Achsrichtung (parallel oder
    antiparallel) und das Kennmaß — ein 20er Zapfen in einer 25er Bohrung ist
    zwar konzentrisch, aber keine Paarung.
    """
    abstand = a.ort.distanceToPoint(b.ort)
    cos = max(-1.0, min(1.0, a.achse.dot(b.achse)))
    winkel = math.degrees(math.acos(abs(cos)))
    mass_ab = abs(a.mass - b.mass)
    fehler = []
    if abstand > ort_tol:
        fehler.append("Ort %.3f mm auseinander" % abstand)
    if winkel > winkel_tol:
        fehler.append("Achsen %.1f Grad verdreht" % winkel)
    if a.mass > 0.0 and b.mass > 0.0 and mass_ab > mass_tol:
        fehler.append("Kennmass %.1f gegen %.1f mm" % (a.mass, b.mass))
    if fehler:
        return False, "%s / %s: %s" % (a.name, b.name, ", ".join(fehler))
    return True, "%s / %s: passt (%.3f mm, %.1f Grad)" % (a.name, b.name,
                                                          abstand, winkel)


def selbsttest():
    """Prüft Andocken und Paarungsprüfung an einem gedachten Zapfen."""
    welle = Bauteil("Welle", punkte=[
        Punkt("zapfen", (0, 0, 50), (0, 0, 1), "welle", 20.0)])
    buchse = Bauteil("Buchse", punkte=[
        Punkt("auge", (100, 0, 0), (1, 0, 0), "bohrung", 20.0)])

    gesetzt = andocke(buchse, "auge", welle.punkt("zapfen"))
    ok, text = pruefe_paarung(gesetzt.punkt("auge"), welle.punkt("zapfen"))
    if not ok:
        raise AssertionError("Andocken misslungen: " + text)

    # Verdrehen um die Achse darf den Anschluss nicht verlieren.
    gedreht = andocke(buchse, "auge", welle.punkt("zapfen"), drehwinkel=37.0)
    ok, text = pruefe_paarung(gedreht.punkt("auge"), welle.punkt("zapfen"))
    if not ok:
        raise AssertionError("Verdrehen hat den Anschluss verloren: " + text)

    # Unpassende Arten muessen auffallen.
    try:
        andocke(welle, "zapfen", welle.punkt("zapfen"))
        raise AssertionError("welle an welle haette auffallen muessen")
    except SchnittstellenFehler:
        pass

    # Falsches Kennmass muss auffallen.
    dick = Punkt("auge", (100, 0, 0), (1, 0, 0), "bohrung", 25.0)
    ok, _t = pruefe_paarung(dick, welle.punkt("zapfen"))
    if ok:
        raise AssertionError("20 in 25 haette auffallen muessen")
    return "Schnittstellen-Selbsttest bestanden"
