# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Werkstoffe an Bauteile hängen — und den Fallstrick dabei umgehen.

In FreeCAD 1.1 hat jedes ``Part::Feature`` die Property ``ShapeMaterial``:

    import Materials
    obj.ShapeMaterial = Materials.MaterialManager().getMaterial(uuid)

Der Haken: ``PropertyMaterial::Save()`` schreibt **nur die UUID** ins Dokument.
Ein zur Laufzeit zusammengebautes Material, das in keiner Bibliothek liegt,
ist nach dem nächsten Öffnen weg (``MaterialNotFound``). Ein Werkstoff muss
also als Karte in einer Bibliothek stehen, sonst ist das Zuweisen Theater.

Wälzlagerstahl **100Cr6 gibt es in FreeCAD nicht** — unter den mitgelieferten
Karten ist kein Lagerstahl. Dieses Modul legt ihn deshalb beim ersten Aufruf
in der Benutzerbibliothek an. Klappt das nicht (Rechte, ältere API), fällt es
hörbar auf ``CalculiX-Steel`` zurück: ``zuweisen()`` sagt dann, was es
wirklich gesetzt hat, statt still etwas anderes zu nehmen.
"""

import FreeCAD

#: Karten, die FreeCAD mitbringt — als Rückfallebene und für Wellen/Räder.
BEKANNT = {
    "stahl": "90bbd8ef-8623-4d78-b3bf-e0bdb9b74dd3",        # Steel-Generic
    "calculix-steel": "92589471-a6cb-4bbc-b748-d425a17dea7d",
}

#: Wälzlagerstahl, wie er in der Benutzerbibliothek angelegt wird.
LAGERSTAHL = {
    "name": "Steel-100Cr6",
    "beschreibung": "Waelzlagerstahl 100Cr6 (AISI 52100), gehaertet",
    "dichte": "7810 kg/m^3",
    "e_modul": "210000 MPa",
    "querzahl": "0.30",
}

_zwischenspeicher = {}


def _manager():
    import Materials
    return Materials.MaterialManager()


def _finde_nach_namen(mm, name):
    for m in mm.Materials.values():
        if (getattr(m, "Name", "") or "") == name:
            return m
    return None


def _benutzer_bibliothek(mm):
    """Name und Pfad der beschreibbaren Bibliothek, sonst (None, None).

    Gemessen auf dieser Installation: die Bibliothek heisst "User" und liegt
    unter ``~/.local/share/FreeCAD/v1-1/Material`` — also NICHT unter
    ``~/.local/share/FreeCAD/Material``, wie man vermuten würde.
    """
    try:
        for eintrag in mm.MaterialLibraries:
            name = eintrag[0] if isinstance(eintrag, (list, tuple)) else eintrag
            if str(name).lower() in ("user", "benutzer"):
                pfad = eintrag[1] if isinstance(eintrag, (list, tuple)) else ""
                return str(name), str(pfad)
    except Exception:  # noqa: BLE001
        pass
    return None, None


def lege_lagerstahl_an():
    """100Cr6 in der Benutzerbibliothek anlegen; liefert das Material oder None."""
    mm = _manager()
    da = _finde_nach_namen(mm, LAGERSTAHL["name"])
    if da is not None:
        return da
    bib, _pfad = _benutzer_bibliothek(mm)
    if bib is None or not hasattr(mm, "save"):
        return None
    try:
        vorlage = mm.getMaterial(BEKANNT["calculix-steel"])
        neu = mm.inheritMaterial(vorlage.UUID)
        neu.Name = LAGERSTAHL["name"]
        neu.Description = LAGERSTAHL["beschreibung"]
        for schluessel, wert in (("Density", LAGERSTAHL["dichte"]),
                                 ("YoungsModulus", LAGERSTAHL["e_modul"]),
                                 ("PoissonRatio", LAGERSTAHL["querzahl"])):
            try:
                neu.setPhysicalValue(schluessel, wert)
            except Exception:  # noqa: BLE001 - Kennwert ist nicht lebenswichtig
                continue
        mm.save(bib, neu, "Standard/Metal/Steel/%s.FCMat" % LAGERSTAHL["name"],
                True, False, False)
        return _finde_nach_namen(_manager(), LAGERSTAHL["name"]) or neu
    except Exception:  # noqa: BLE001 - Rückfall ist vorgesehen, kein Fehler
        return None


def hole(name="lagerstahl"):
    """(Material, tatsächlicher Name). Fällt hörbar zurück, statt still zu tauschen."""
    schluessel = (name or "").strip().lower()
    if schluessel in _zwischenspeicher:
        return _zwischenspeicher[schluessel]
    mm = _manager()
    mat = None
    if schluessel in ("lagerstahl", "100cr6", "52100"):
        mat = lege_lagerstahl_an()
    if mat is None and schluessel in BEKANNT:
        mat = mm.getMaterial(BEKANNT[schluessel])
    if mat is None:
        mat = _finde_nach_namen(mm, name)
    if mat is None:
        mat = mm.getMaterial(BEKANNT["calculix-steel"])
    ergebnis = (mat, getattr(mat, "Name", "?"))
    _zwischenspeicher[schluessel] = ergebnis
    return ergebnis


def zuweisen(objekte, name="lagerstahl"):
    """Werkstoff an ein Objekt oder eine Liste hängen; liefert den Namen.

    Nur ``Part::Feature`` hat ``ShapeMaterial`` — bei allem anderen passiert
    nichts, und das ist in Ordnung.
    """
    if not isinstance(objekte, (list, tuple)):
        objekte = [objekte]
    mat, echt = hole(name)
    gesetzt = 0
    for o in objekte:
        try:
            o.ShapeMaterial = mat
            gesetzt += 1
        except Exception:  # noqa: BLE001 - kein Part::Feature, kein Drama
            continue
    return "%s an %d von %d Bauteil(en)" % (echt, gesetzt, len(objekte))


def selbsttest():
    """Prüft, dass ein Werkstoff gefunden und gesetzt werden kann."""
    import Part
    doc = FreeCAD.newDocument("WerkstoffTest")
    try:
        mat, echt = hole("lagerstahl")
        if mat is None:
            raise AssertionError("kein Werkstoff gefunden")
        o = doc.addObject("Part::Feature", "Probe")
        o.Shape = Part.makeBox(10, 10, 10)
        meldung = zuweisen(o, "lagerstahl")
        if "1 von 1" not in meldung:
            raise AssertionError("nicht zugewiesen: %s" % meldung)
        if getattr(o.ShapeMaterial, "Name", "") != echt:
            raise AssertionError("falscher Werkstoff am Objekt")
        return "Werkstoff-Selbsttest bestanden (%s)" % echt
    finally:
        FreeCAD.closeDocument(doc.Name)
